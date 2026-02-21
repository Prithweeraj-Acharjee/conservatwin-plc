"""
ConservaTwin PLC — Zone A Control Program
==========================================
Gallery A — "Troubles of My Head"
Artwork: Collage / Paper / Adhesive / Mixed Media
Setpoints: Temp 20°C ±2, RH 45% ±5

PLC SEMANTICS:
  - Reads ONLY from I image
  - Writes ONLY to Q image
  - Mode changes via M bits
  - No direct UI interaction
  - All logic is deterministic given same I/M state

Control strategy:
  1. Sensor validity check → gate all outputs if invalid
  2. RH slew rate monitoring → RH slew interlock
  3. PID-based temp/RH control
  4. Manual mode allows HMI override via M bits
  5. Alarm latching for temp/RH/slew violations
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from plc.memory import PLCMemory, I, Q, M
    from plc.timers import TimerBank
    from plc.fb.pid import PIDBank
    from plc.fb.alarm import AlarmBank
    from plc.fb.debounce import DebounceBlock
    from plc.fb.risk import ZoneARiskBlock

from plc.memory import I, Q, M

# Setpoints
SP_TEMP = 20.0   # °C
SP_RH   = 45.0   # %RH
SLEW_WARN_RATE = 2.0    # %/min — threshold for RH slew warning
SLEW_TRIP_RATE = 5.0    # %/min — hard interlock

# Fixed-point scale: sensor values in I image are stored ×100
FP_SCALE = 100.0


def execute(mem, timers, pids, alarms, debounce_sensors, risk, dt: float,
            opt_sp_temp: float = SP_TEMP, opt_sp_rh: float = SP_RH) -> None:
    """
    Zone A scan cycle program.
    Call exactly once per PLC scan cycle.

    Args:
        mem      : PLCMemory
        timers   : TimerBank
        pids     : PIDBank
        alarms   : AlarmBank
        debounce_sensors: dict with 'a_temp', 'a_rh' DebounceBlocks
        risk     : ZoneARiskBlock
        dt       : scan interval in seconds
        opt_sp_temp : optimizer-suggested temp setpoint (defaults to SP_TEMP)
        opt_sp_rh   : optimizer-suggested RH setpoint (defaults to SP_RH)
    """
    # ── 1. Read I image ───────────────────────────────────────────────────────
    temp_valid_raw = mem.I.read_bit(*I.A_TEMP_VALID)
    rh_valid_raw   = mem.I.read_bit(*I.A_RH_VALID)

    # Debounce sensor valid signals to prevent false validity trips
    temp_valid = debounce_sensors['a_temp'].update(temp_valid_raw)
    rh_valid   = debounce_sensors['a_rh'].update(rh_valid_raw)

    temp_fp  = mem.I.read_word(I.A_TEMP_W)         # ×100 fixed-point
    rh_fp    = mem.I.read_word(I.A_RH_W)
    slew_fp  = mem.I.read_word(I.A_SLEW_W)

    temp = temp_fp / FP_SCALE
    rh   = rh_fp   / FP_SCALE
    rh_slew = slew_fp / FP_SCALE                    # %/min

    # ── 2. Mode selection (M bits) ────────────────────────────────────────────
    auto_mode = mem.M.read_bit(*M.A_AUTO)
    alarm_ack = mem.M.read_bit(*M.A_ALARM_ACK)
    global_ack = mem.M.read_bit(*M.GLOBAL_ACK)
    ack        = alarm_ack or global_ack

    # ── 3. Sensor validity gate ───────────────────────────────────────────────
    sensor_fault = (not temp_valid) or (not rh_valid)
    alarms.a_sensor.update(SET=sensor_fault, ACK=ack)
    mem.M.write_bit(*M.SENSOR_A_INVALID, sensor_fault)

    if sensor_fault:
        # Safe state: turn off all actuators
        _safe_state_a(mem)
        return

    # ── 4. RH slew rate interlock ─────────────────────────────────────────────
    slew_warn = abs(rh_slew) > SLEW_WARN_RATE
    slew_trip = abs(rh_slew) > SLEW_TRIP_RATE
    mem.I.write_bit(*I.A_RH_SLEW_WARN, slew_warn)

    # RH slew alarm latch
    slew_alarm_q, _ = timers.a_rh_slew_ton.update(IN=slew_warn, dt=dt)
    alarms.a_slew.update(SET=slew_alarm_q, ACK=ack)
    mem.M.write_bit(*M.A_SLEW_ALARM, alarms.a_slew.Q)

    # ── 5. Temperature alarm detection ───────────────────────────────────────
    temp_alarm_set = (temp > opt_sp_temp + 2.0) or (temp < opt_sp_temp - 2.0)
    alarms.a_temp.update(SET=temp_alarm_set, ACK=ack)
    mem.M.write_bit(*M.A_TEMP_ALARM, alarms.a_temp.Q)
    mem.I.write_bit(*I.A_TEMP_HIGH, temp > opt_sp_temp + 2.0)
    mem.I.write_bit(*I.A_TEMP_LOW,  temp < opt_sp_temp - 2.0)

    # ── 6. RH alarm detection ─────────────────────────────────────────────────
    rh_alarm_set = (rh > opt_sp_rh + 5.0) or (rh < opt_sp_rh - 5.0)

    # TON: high-RH sustained duration alarm
    rh_high_ton_q, _ = timers.a_rh_high_ton.update(IN=(rh > opt_sp_rh + 5.0), dt=dt)
    alarms.a_rh.update(SET=rh_alarm_set or rh_high_ton_q, ACK=ack)
    mem.M.write_bit(*M.A_RH_ALARM, alarms.a_rh.Q)
    mem.I.write_bit(*I.A_RH_HIGH, rh > opt_sp_rh + 5.0)
    mem.I.write_bit(*I.A_RH_LOW,  rh < opt_sp_rh - 5.0)

    # Alarm latched flag
    any_alarm = alarms.a_temp.Q or alarms.a_rh.Q or alarms.a_slew.Q or alarms.a_sensor.Q
    mem.M.write_bit(*M.A_ALARM_LATCHED, any_alarm)
    mem.Q.write_bit(*Q.A_ALARM_LIGHT, any_alarm)

    # ── 7. PID control ────────────────────────────────────────────────────────
    # Modifications: if slew is tripping, inhibit humidifier/dehumidifier to slow rate
    slew_inhibit = slew_trip

    temp_cv = pids.a_temp.update(sp=opt_sp_temp, pv=temp, dt=dt, auto=auto_mode)
    rh_cv   = pids.a_rh.update(  sp=opt_sp_rh,   pv=rh,   dt=dt, auto=auto_mode)

    mem.Q.write_word(Q.A_TEMP_CV_W, int(temp_cv * FP_SCALE))
    mem.Q.write_word(Q.A_RH_CV_W,   int(rh_cv   * FP_SCALE))

    # ── 8. Output Q bits ─────────────────────────────────────────────────────
    if auto_mode:
        mem.Q.write_bit(*Q.A_HEAT,        temp_cv > 5.0)
        mem.Q.write_bit(*Q.A_COOL,        temp_cv < -5.0)
        mem.Q.write_bit(*Q.A_FAN,         abs(temp_cv) > 1.0 or abs(rh_cv) > 1.0)
        mem.Q.write_bit(*Q.A_HUMIDIFY,    (rh_cv > 5.0)  and (not slew_inhibit))
        mem.Q.write_bit(*Q.A_DEHUMIDIFY,  (rh_cv < -5.0) and (not slew_inhibit))
    else:
        # Manual mode: direct M-bit control
        mem.Q.write_bit(*Q.A_HEAT,       mem.M.read_bit(*M.A_MANUAL_HEAT))
        mem.Q.write_bit(*Q.A_COOL,       mem.M.read_bit(*M.A_MANUAL_COOL))
        mem.Q.write_bit(*Q.A_HUMIDIFY,   mem.M.read_bit(*M.A_MANUAL_HUMIDIFY) and not slew_inhibit)
        mem.Q.write_bit(*Q.A_DEHUMIDIFY, mem.M.read_bit(*M.A_MANUAL_DEHUMID) and not slew_inhibit)
        mem.Q.write_bit(*Q.A_FAN,        False)

    # ── 9. Preservation Risk Index ────────────────────────────────────────────
    risk_val, risk_alarm, risk_crit = risk.update(
        temp=temp, rh=rh, rh_slew=rh_slew, dt=dt,
        sp_temp=opt_sp_temp, sp_rh=opt_sp_rh
    )
    mem.M.write_word(M.A_RISK_W, int(risk_val * FP_SCALE))

    # ── 10. Recovery timer ───────────────────────────────────────────────────
    conditions_ok = not temp_alarm_set and not rh_alarm_set and not slew_warn
    timers.a_recovery_rto.update(
        IN=conditions_ok,
        CLR=any_alarm,
        dt=dt
    )


def _safe_state_a(mem) -> None:
    """Force all Zone A actuators off (safe state on sensor fault)."""
    mem.Q.write_bit(*Q.A_HEAT,       False)
    mem.Q.write_bit(*Q.A_COOL,       False)
    mem.Q.write_bit(*Q.A_HUMIDIFY,   False)
    mem.Q.write_bit(*Q.A_DEHUMIDIFY, False)
    mem.Q.write_bit(*Q.A_FAN,        False)
    mem.Q.write_bit(*Q.A_ALARM_LIGHT, True)
