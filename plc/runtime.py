"""
ConservaTwin PLC — Main Runtime Engine
========================================
The PLCRuntime is the heart of the system.

Scan Cycle (executed deterministically every SCAN_INTERVAL_MS):
  1. read_inputs()     — copy from plant to I image
  2. safety_program()  — E-Stop, interlocks, watchdog check
  3. zone_programs()   — Zone A, B, Vault logic (if safety OK)
  4. write_outputs()   — copy Q image to plant
  5. log_scan()        — snapshot to historian

Scan overrun detection: if a scan takes longer than SCAN_INTERVAL_MS,
the watchdog function block is notified and may trip an alarm.
"""

from __future__ import annotations

import asyncio
import time
import logging
from dataclasses import dataclass, field
from typing import Optional, Callable, List, Dict, Any

from plc.memory import PLCMemory, I, Q, M
from plc.timers import TimerBank
from plc.fb.pid import PIDBank
from plc.fb.alarm import AlarmBank
from plc.fb.debounce import DebounceBlock
from plc.fb.watchdog import WatchdogBlock
from plc.fb.risk import ZoneARiskBlock, ZoneBRiskBlock, ZoneCRiskBlock
from plc.optimizer import PreservationOptimizer
from plc import program

logger = logging.getLogger("plc.runtime")

FP_SCALE = 100.0


@dataclass
class ScanSnapshot:
    """Immutable record of one complete PLC scan."""
    scan_number:  int
    timestamp:    float
    scan_ms:      float
    mem_snap:     Dict[str, bytes]
    timers:       Dict[str, Any]
    pids:         Dict[str, Any]
    alarms:       Dict[str, Any]
    risk_a:       Dict[str, Any]
    risk_b:       Dict[str, Any]
    risk_c:       Dict[str, Any]
    watchdog:     Dict[str, Any]


class PLCRuntime:
    """
    Software PLC scan cycle engine.

    Attributes:
        scan_interval_ms : target scan period in milliseconds (100–500)
        mem              : PLCMemory (I, Q, M image tables)
        plant            : plant model (ZoneModel triple)
        on_scan_complete : callback for every completed scan (historian, WebSocket)
    """

    def __init__(
        self,
        plant,                          # plant.model.MuseumPlant instance
        scan_interval_ms: float = 200,  # 200 ms default scan
        on_scan_complete: Optional[Callable[[ScanSnapshot], None]] = None,
    ):
        self.plant = plant
        self.scan_interval_ms = scan_interval_ms
        self.scan_interval_s  = scan_interval_ms / 1000.0
        self.on_scan_complete = on_scan_complete

        # PLC memory
        self.mem = PLCMemory()

        # Timers
        self.timers = TimerBank()

        # Function blocks
        self.pids    = PIDBank()
        self.alarms  = AlarmBank()
        self.riskA   = ZoneARiskBlock()
        self.riskB   = ZoneBRiskBlock()
        self.riskC   = ZoneCRiskBlock()
        self.watchdog = WatchdogBlock(max_scan_ms=scan_interval_ms * 3)
        self.optimizer = PreservationOptimizer()

        # Debounce blocks: one per sensor validity signal
        self.debounce = {
            'a_temp': DebounceBlock("A_TEMP_VALID", stable_scans=3),
            'a_rh':   DebounceBlock("A_RH_VALID",   stable_scans=3),
            'b_temp': DebounceBlock("B_TEMP_VALID",  stable_scans=3),
            'b_rh':   DebounceBlock("B_RH_VALID",    stable_scans=3),
            'c_temp': DebounceBlock("C_TEMP_VALID",  stable_scans=3),
            'c_rh':   DebounceBlock("C_RH_VALID",    stable_scans=3),
        }

        # Runtime state
        self._scan_number: int  = 0
        self._running:     bool = False
        self._task: Optional[asyncio.Task] = None
        self._scan_callbacks: List[Callable] = []
        if on_scan_complete:
            self._scan_callbacks.append(on_scan_complete)

        # Initialize M bits — all zones in Auto by default
        self.mem.M.write_bit(*M.A_AUTO, True)
        self.mem.M.write_bit(*M.B_AUTO, True)
        self.mem.M.write_bit(*M.C_AUTO, True)
        # Power OK by default
        self.mem.I.write_bit(*I.PWR_OK, True)
        self.mem.I.write_bit(*I.WATCHDOG_OK, True)

    # ── Public control ─────────────────────────────────────────────────────────

    def add_scan_callback(self, cb: Callable[[ScanSnapshot], None]) -> None:
        self._scan_callbacks.append(cb)

    async def start(self) -> None:
        """Start the async scan cycle task."""
        self._running = True
        self._task = asyncio.create_task(self._scan_loop())
        logger.info(f"PLC Runtime started — scan interval {self.scan_interval_ms}ms")

    async def stop(self) -> None:
        """Stop the scan cycle gracefully."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("PLC Runtime stopped")

    # ── Scan loop ──────────────────────────────────────────────────────────────

    async def _scan_loop(self) -> None:
        """Main deterministic scan loop."""
        while self._running:
            t_start = time.perf_counter()
            self._execute_scan()
            elapsed_ms = (time.perf_counter() - t_start) * 1000.0

            # Watchdog overrun check
            is_overrun = elapsed_ms > self.watchdog.max_scan_ms
            global_ack = self.mem.M.read_bit(*M.GLOBAL_ACK)
            
            # Watchdog FB update returns True if tripped
            self.watchdog.update(elapsed_ms)
            
            # Alarm latch update: 
            # SET: use instant overrun state so latch can clear when normal
            # ACK: if global ack, also reset the internal watchdog block
            if global_ack:
                self.watchdog.reset()
            
            self.alarms.watchdog.update(SET=is_overrun, ACK=global_ack)
            
            if self.watchdog.tripped or self.alarms.watchdog.Q:
                self.mem.M.write_bit(*M.WATCHDOG_ALARM, True)
                if is_overrun:
                    logger.warning(f"WATCHDOG TRIPPED — scan took {elapsed_ms:.1f}ms")
            else:
                self.mem.M.write_bit(*M.WATCHDOG_ALARM, False)

            # Clear any temporary pulse bits (ACKs) at end of scan
            self.clear_ack()

            # Sleep for remainder of scan interval
            remaining = self.scan_interval_s - (elapsed_ms / 1000.0)
            if remaining > 0:
                await asyncio.sleep(remaining)

    def _execute_scan(self) -> None:
        """
        Execute one complete PLC scan cycle.
        This is the deterministic core — same inputs always produce same outputs.
        """
        self._scan_number += 1
        ts = time.time()
        dt = self.scan_interval_s

        # ── Phase 1: Read inputs (plant → I image) ─────────────────────────
        self._read_inputs()

        # ── Phase 2: Safety network ────────────────────────────────────────
        from plc.program import safety
        safe = safety.execute(mem=self.mem, alarms=self.alarms, dt=dt)

        # ── Phase 3: Zone programs (only if safe) ─────────────────────────
        if safe:
            # Optimizer may suggest adjusted setpoints each scan
            pd = self.plant.get_display_values()
            opt_a = self.optimizer.optimize(
                'A', pd['A']['temp'], pd['A']['rh'],
                self.riskA.risk, pd['A']['actuators'])
            opt_b = self.optimizer.optimize(
                'B', pd['B']['temp'], pd['B']['rh'],
                self.riskB.risk, pd['B']['actuators'])
            opt_c = self.optimizer.optimize(
                'C', pd['C']['temp'], pd['C']['rh'],
                self.riskC.risk, pd['C']['actuators'])

            from plc.program import zone_a, zone_b, vault
            zone_a.execute(
                mem=self.mem, timers=self.timers, pids=self.pids,
                alarms=self.alarms, debounce_sensors=self.debounce,
                risk=self.riskA, dt=dt,
                opt_sp_temp=opt_a[0], opt_sp_rh=opt_a[1])
            zone_b.execute(
                mem=self.mem, timers=self.timers, pids=self.pids,
                alarms=self.alarms, debounce_sensors=self.debounce,
                risk=self.riskB, dt=dt,
                opt_sp_temp=opt_b[0], opt_sp_rh=opt_b[1])
            vault.execute(
                mem=self.mem, timers=self.timers, pids=self.pids,
                alarms=self.alarms, debounce_sensors=self.debounce,
                risk=self.riskC, dt=dt,
                opt_sp_temp=opt_c[0], opt_sp_rh=opt_c[1])

        # ── Phase 4: Write outputs (Q image → plant) ──────────────────────
        self._write_outputs()

        # ── Phase 5: Build snapshot and notify callbacks ───────────────────
        snap = ScanSnapshot(
            scan_number = self._scan_number,
            timestamp   = ts,
            scan_ms     = self.scan_interval_ms,
            mem_snap    = self.mem.snapshot(),
            timers      = self.timers.as_dict(),
            pids        = self.pids.as_dict(),
            alarms      = self.alarms.as_dict(),
            risk_a      = self.riskA.as_dict(),
            risk_b      = self.riskB.as_dict(),
            risk_c      = self.riskC.as_dict(),
            watchdog    = self.watchdog.as_dict(),
        )
        for cb in self._scan_callbacks:
            try:
                cb(snap)
            except Exception as e:
                logger.error(f"Scan callback error: {e}")

    def _read_inputs(self) -> None:
        """Copy plant sensor values into I image table."""
        zones = self.plant.get_sensor_values()

        for zone_key, zone_prefix, iw_temp, iw_rh, iw_slew, byte_base in [
            ('A', 'a', I.A_TEMP_W, I.A_RH_W, I.A_SLEW_W, 0),
            ('B', 'b', I.B_TEMP_W, I.B_RH_W, None,       8),
            ('C', 'c', I.C_TEMP_W, I.C_RH_W, None,       16),
        ]:
            z = zones[zone_key]
            temp = z['temp']
            rh   = z['rh']
            valid = z['valid']
            door  = z.get('door_open', False)

            self.mem.I.write_word(iw_temp, int(temp * FP_SCALE))
            self.mem.I.write_word(iw_rh,   int(rh   * FP_SCALE))
            self.mem.I.write_bit(byte_base, 0, valid)   # TEMP_VALID
            self.mem.I.write_bit(byte_base, 3, valid)   # RH_VALID
            self.mem.I.write_bit(byte_base, 7, door)    # DOOR_OPEN

            if iw_slew is not None and 'rh_slew' in z:
                self.mem.I.write_word(iw_slew, int(z['rh_slew'] * FP_SCALE))

    def _write_outputs(self) -> None:
        """Copy Q image actuator commands to plant."""
        actuators = {
            'A': {
                'heat':       self.mem.Q.read_bit(*Q.A_HEAT),
                'cool':       self.mem.Q.read_bit(*Q.A_COOL),
                'humidify':   self.mem.Q.read_bit(*Q.A_HUMIDIFY),
                'dehumidify': self.mem.Q.read_bit(*Q.A_DEHUMIDIFY),
                'fan':        self.mem.Q.read_bit(*Q.A_FAN),
                'temp_cv':    self.mem.Q.read_word(Q.A_TEMP_CV_W) / FP_SCALE,
                'rh_cv':      self.mem.Q.read_word(Q.A_RH_CV_W)   / FP_SCALE,
            },
            'B': {
                'heat':       self.mem.Q.read_bit(*Q.B_HEAT),
                'cool':       self.mem.Q.read_bit(*Q.B_COOL),
                'humidify':   self.mem.Q.read_bit(*Q.B_HUMIDIFY),
                'dehumidify': self.mem.Q.read_bit(*Q.B_DEHUMIDIFY),
                'fan':        self.mem.Q.read_bit(*Q.B_FAN),
                'temp_cv':    self.mem.Q.read_word(Q.B_TEMP_CV_W) / FP_SCALE,
                'rh_cv':      self.mem.Q.read_word(Q.B_RH_CV_W)   / FP_SCALE,
            },
            'C': {
                'heat':       self.mem.Q.read_bit(*Q.C_HEAT),
                'cool':       self.mem.Q.read_bit(*Q.C_COOL),
                'humidify':   self.mem.Q.read_bit(*Q.C_HUMIDIFY),
                'dehumidify': self.mem.Q.read_bit(*Q.C_DEHUMIDIFY),
                'fan':        self.mem.Q.read_bit(*Q.C_FAN),
                'temp_cv':    self.mem.Q.read_word(Q.C_TEMP_CV_W) / FP_SCALE,
                'rh_cv':      self.mem.Q.read_word(Q.C_RH_CV_W)   / FP_SCALE,
            },
        }
        self.plant.set_actuators(actuators)

    # ── HMI command interface (M-bit writes from API) ─────────────────────────

    def set_mode(self, zone: str, mode: str) -> None:
        """Set zone to 'auto' or 'manual' mode via M bits."""
        zone = zone.upper()
        auto = (mode.lower() == 'auto')
        bit_map = {'A': M.A_AUTO, 'B': M.B_AUTO, 'C': M.C_AUTO}
        if zone in bit_map:
            self.mem.M.write_bit(*bit_map[zone], auto)
            logger.info(f"Zone {zone} mode → {'AUTO' if auto else 'MANUAL'}")

    def ack_alarm(self, zone: str) -> None:
        """Assert acknowledge bit for a zone alarm via M bit."""
        zone = zone.upper()
        ack_map = {'A': M.A_ALARM_ACK, 'B': M.B_ALARM_ACK, 'C': M.C_ALARM_ACK}
        if zone == 'ALL' or zone == 'SYS':
            self.mem.M.write_bit(*M.GLOBAL_ACK, True)
        elif zone in ack_map:
            self.mem.M.write_bit(*ack_map[zone], True)

    def clear_ack(self) -> None:
        """Clear all ACK bits (called after scan processes them)."""
        for bit in [M.A_ALARM_ACK, M.B_ALARM_ACK, M.C_ALARM_ACK, M.GLOBAL_ACK]:
            self.mem.M.write_bit(*bit, False)

    def set_estop(self, active: bool) -> None:
        self.mem.M.write_bit(*M.ESTOP_CMD, active)

    def set_manual_bit(self, zone: str, actuator: str, value: bool) -> None:
        """Set manual actuator control via M bits."""
        zone     = zone.upper()
        actuator = actuator.lower()
        bit_map = {
            ('A', 'heat'):       M.A_MANUAL_HEAT,
            ('A', 'cool'):       M.A_MANUAL_COOL,
            ('A', 'humidify'):   M.A_MANUAL_HUMIDIFY,
            ('A', 'dehumidify'): M.A_MANUAL_DEHUMID,
            ('B', 'heat'):       M.B_MANUAL_HEAT,
            ('B', 'cool'):       M.B_MANUAL_COOL,
            ('B', 'humidify'):   M.B_MANUAL_HUMIDIFY,
            ('B', 'dehumidify'): M.B_MANUAL_DEHUMID,
            ('C', 'heat'):       M.C_MANUAL_HEAT,
            ('C', 'cool'):       M.C_MANUAL_COOL,
            ('C', 'humidify'):   M.C_MANUAL_HUMIDIFY,
            ('C', 'dehumidify'): M.C_MANUAL_DEHUMID,
        }
        key = (zone, actuator)
        if key in bit_map:
            self.mem.M.write_bit(*bit_map[key], value)

    def inject_fault(self, fault_type: str, zone: str = 'A') -> None:
        """Test harness: inject fault condition via I image manipulation."""
        zone = zone.upper()
        if fault_type == 'sensor_freeze':
            # Mark sensor invalid
            valid_map = {'A': (I.A_TEMP_VALID, I.A_RH_VALID),
                         'B': (I.B_TEMP_VALID, I.B_RH_VALID),
                         'C': (I.C_TEMP_VALID, I.C_RH_VALID)}
            if zone in valid_map:
                for bit in valid_map[zone]:
                    self.mem.I.write_bit(*bit, False)
        elif fault_type == 'door_open':
            door_map = {'A': I.A_DOOR_OPEN, 'B': I.B_DOOR_OPEN, 'C': I.C_DOOR_OPEN}
            if zone in door_map:
                self.mem.I.write_bit(*door_map[zone], True)
        elif fault_type == 'estop':
            self.mem.I.write_bit(*I.ESTOP, True)
        elif fault_type == 'power_fault':
            self.mem.I.write_bit(*I.PWR_OK, False)
        elif fault_type == 'clear':
            # Clear all injected faults
            for bit in [I.A_TEMP_VALID, I.A_RH_VALID, I.B_TEMP_VALID, I.B_RH_VALID,
                        I.C_TEMP_VALID, I.C_RH_VALID, I.A_DOOR_OPEN, I.B_DOOR_OPEN,
                        I.C_DOOR_OPEN, I.ESTOP]:
                self.mem.I.write_bit(*bit, True)
            self.mem.I.write_bit(*I.PWR_OK, True)

    def get_full_state(self) -> Dict[str, Any]:
        """Return complete PLC state for WebSocket broadcast."""
        return {
            'scan_number': self._scan_number,
            'timestamp':   time.time(),
            'memory':      self.mem.as_dict(),
            'timers':      self.timers.as_dict(),
            'pids':        self.pids.as_dict(),
            'alarms':      self.alarms.as_dict(),
            'risk_a':      self.riskA.as_dict(),
            'risk_b':      self.riskB.as_dict(),
            'risk_c':      self.riskC.as_dict(),
            'watchdog':    self.watchdog.as_dict(),
            'plant':       self.plant.get_display_values(),
            'optimizer':   self.optimizer.as_dict(),
        }
