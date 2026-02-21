"""
ConservaTwin API — FastAPI Main Application
============================================
Two-process architecture:
  Process 1: This FastAPI backend (PLC runtime + plant + historian + WebSocket)
  Process 2: Next.js HMI (reads from WebSocket + REST API)

WebSocket /ws: Broadcasts full PLC state at every scan cycle
REST endpoints:
  POST /command/mode        — set zone Auto/Manual
  POST /command/ack-alarm   — acknowledge alarm
  POST /command/manual      — set manual actuator bit
  POST /command/estop       — software E-stop
  POST /inject-fault        — test harness fault injection
  GET  /export-csv          — historian CSV download
  GET  /history/recent      — last N scan rows (for retrospective trends)
  GET  /state               — current full PLC state (REST polling fallback)
  GET  /health              — health check
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, JSONResponse
from pydantic import BaseModel

from plant.model import MuseumPlant
from plc.runtime import PLCRuntime, ScanSnapshot
from api.historian import Historian

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("api.main")

# ─── Global objects ──────────────────────────────────────────────────────────
plant:     MuseumPlant  = None
plc:       PLCRuntime   = None
historian: Historian    = None
ws_clients: List[WebSocket] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    global plant, plc, historian

    plant     = MuseumPlant(seed=42)
    historian = Historian()
    await historian.start()

    # Plant step task — advances physics model every 200ms in sync with PLC
    async def plant_step_loop():
        dt = plc.scan_interval_s if plc else 0.2
        while True:
            plant.step(dt)
            await asyncio.sleep(dt)

    plant_task = asyncio.create_task(plant_step_loop())

    # Scan callback: writes to historian and broadcasts over WebSocket
    def on_scan(snap: ScanSnapshot):
        pd = plant.get_display_values()
        historian.log(snap, pd)
        # Schedule WebSocket broadcast (non-blocking)
        asyncio.get_event_loop().call_soon_threadsafe(
            asyncio.ensure_future, _broadcast(snap, pd)
        )

    plc = PLCRuntime(plant=plant, scan_interval_ms=200, on_scan_complete=on_scan)
    await plc.start()

    logger.info("ConservaTwin PLC system online")
    yield

    # Shutdown
    await plc.stop()
    plant_task.cancel()
    await historian.stop()
    logger.info("ConservaTwin PLC system offline")


import os

app = FastAPI(title="ConservaTwin PLC API", version="1.0.0", lifespan=lifespan)

# ── CORS — allow Vercel frontend + localhost dev ───────────────────────────────
_raw_origins = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,https://hmi-sepia.vercel.app"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _raw_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Alarm tag → (zone letter, human description, severity) ────────────────────
_ALARM_META: dict[str, tuple[str, str, str]] = {
    'a_temp':    ('A', 'Temperature deviation',    'alarm'),
    'a_rh':      ('A', 'RH out of range',          'alarm'),
    'a_slew':    ('A', 'RH slew rate exceeded',    'warning'),
    'a_sensor':  ('A', 'Sensor fault / freeze',    'critical'),
    'b_temp':    ('B', 'Temperature deviation',    'alarm'),
    'b_rh':      ('B', 'RH out of range',          'alarm'),
    'b_cumtemp': ('B', 'Cumulative temp exceedance', 'alarm'),
    'b_sensor':  ('B', 'Sensor fault / freeze',    'critical'),
    'c_temp':    ('C', 'Temperature deviation',    'alarm'),
    'c_rh':      ('C', 'RH out of range',          'alarm'),
    'c_sensor':  ('C', 'Sensor fault / freeze',    'critical'),
    'watchdog':  ('SYS', 'PLC watchdog overrun',   'critical'),
    'estop':     ('SYS', 'Emergency stop active',  'critical'),
}

def _reshape_plant(plant_display: dict) -> dict:
    """Remap plant keys A/B/C → zone_a/zone_b/vault for frontend."""
    return {
        'zone_a': plant_display.get('A', {}),
        'zone_b': plant_display.get('B', {}),
        'vault':  plant_display.get('C', {}),
    }

def _reshape_alarms(raw_alarms: dict) -> dict:
    """Enrich alarm dicts with tag, message, zone, severity for frontend."""
    out = {}
    for key, ad in raw_alarms.items():
        meta = _ALARM_META.get(key, ('?', key, 'warning'))
        out[key] = {
            **ad,
            'tag':      ad.get('name', key),
            'message':  meta[1],
            'zone':     meta[0],
            'severity': meta[2],
            'acked':    ad.get('acknowledged', False),
        }
    return out

def _reshape_risk(raw_risk: dict, label: str) -> dict:
    """Remap risk fields to PRI / risk_level / contributors for frontend."""
    risk_val = raw_risk.get('risk', 0.0)
    pri = round(risk_val * 100.0, 1)          # normalise 0-100
    if raw_risk.get('critical', False):
        level = 'critical'
    elif raw_risk.get('alarm', False):
        level = 'high'
    elif pri > 25:
        level = 'medium'
    else:
        level = 'low'
    return {
        'pri':        pri,
        'risk_level': level,
        'contributors': {label: round(risk_val, 4)},
    }


async def _broadcast(snap: ScanSnapshot, plant_display: dict):
    """Broadcast scan state to all connected WebSocket clients."""
    if not ws_clients:
        return
    reshaped_plant  = _reshape_plant(plant_display)
    reshaped_alarms = _reshape_alarms(snap.alarms)
    active_alarms   = [v for v in reshaped_alarms.values() if v.get('latched', False)]

    payload = json.dumps({
        'type':        'scan',
        'scan_number': snap.scan_number,
        'timestamp':   snap.timestamp,
        'pids':        snap.pids,
        'timers':      snap.timers,
        'alarms':      reshaped_alarms,
        'risk_a':      _reshape_risk(snap.risk_a, 'zone_a'),
        'risk_b':      _reshape_risk(snap.risk_b, 'zone_b'),
        'risk_c':      _reshape_risk(snap.risk_c, 'vault'),
        'watchdog':    {
            'overruns':    snap.watchdog.get('overrun_cnt', 0),
            'max_scan_ms': snap.watchdog.get('max_seen_ms', 0),
            'last_scan_ms': snap.watchdog.get('last_scan_ms', 0),
            'tripped':     snap.watchdog.get('tripped', False),
        },
        'plant':         reshaped_plant,
        'active_alarms': active_alarms,
    })
    dead = []
    for ws in ws_clients:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in ws_clients:
            ws_clients.remove(ws)



# ─── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="ConservaTwin PLC",
    description="PLC-authentic digital twin for museum conservation",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── WebSocket ────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    ws_clients.append(websocket)
    logger.info(f"WebSocket client connected ({len(ws_clients)} total)")
    try:
        # Send current state immediately on connect
        if plc:
            state = plc.get_full_state()
            await websocket.send_text(json.dumps({'type': 'init', **state}))
        while True:
            # Keep alive — wait for any client messages (e.g., ping)
            msg = await websocket.receive_text()
            if msg == 'ping':
                await websocket.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        if websocket in ws_clients:
            ws_clients.remove(websocket)
        logger.info(f"WebSocket client disconnected ({len(ws_clients)} remaining)")


# ─── Pydantic models ──────────────────────────────────────────────────────────

class ModeCommand(BaseModel):
    zone: str       # 'A', 'B', or 'C'
    mode: str       # 'auto' or 'manual'

class AlarmAckCommand(BaseModel):
    zone: str       # 'A', 'B', 'C', or 'ALL'

class ManualCommand(BaseModel):
    zone:     str   # 'A', 'B', 'C'
    actuator: str   # 'heat', 'cool', 'humidify', 'dehumidify'
    value:    bool

class EStopCommand(BaseModel):
    active: bool

class FaultCommand(BaseModel):
    fault: str      # 'sensor_freeze', 'door_open', 'estop', 'power_fault', 'clear', 'degrade'
    zone:  str = 'A'


# ─── REST endpoints ───────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "scan_number": plc._scan_number if plc else 0,
        "historian_rows": historian.get_row_count() if historian else 0,
        "ws_clients": len(ws_clients),
    }


@app.get("/state")
async def get_state():
    """REST polling fallback — returns current full PLC state."""
    if not plc:
        raise HTTPException(503, "PLC not running")
    return plc.get_full_state()


@app.post("/command/mode")
async def set_mode(cmd: ModeCommand):
    """Set zone Auto/Manual mode via M bit."""
    if not plc:
        raise HTTPException(503, "PLC not running")
    plc.set_mode(cmd.zone, cmd.mode)
    return {"ok": True, "zone": cmd.zone, "mode": cmd.mode}


@app.post("/command/ack-alarm")
async def ack_alarm(cmd: AlarmAckCommand):
    """Acknowledge alarm for zone (or ALL) via M bit."""
    if not plc:
        raise HTTPException(503, "PLC not running")
    plc.ack_alarm(cmd.zone)
    # ACK bit is a pulse — clear it after next scan
    async def clear_ack():
        await asyncio.sleep(plc.scan_interval_s * 2)
        plc.clear_ack()
    asyncio.create_task(clear_ack())
    return {"ok": True, "zone": cmd.zone}


@app.post("/command/manual")
async def manual_command(cmd: ManualCommand):
    """Set manual actuator bit via M memory."""
    if not plc:
        raise HTTPException(503, "PLC not running")
    plc.set_manual_bit(cmd.zone, cmd.actuator, cmd.value)
    return {"ok": True, "zone": cmd.zone, "actuator": cmd.actuator, "value": cmd.value}


@app.post("/command/estop")
async def estop(cmd: EStopCommand):
    """Software E-Stop command via M bit."""
    if not plc:
        raise HTTPException(503, "PLC not running")
    plc.set_estop(cmd.active)
    return {"ok": True, "estop": cmd.active}


@app.post("/inject-fault")
async def inject_fault(cmd: FaultCommand):
    """
    Test harness fault injection endpoint.
    fault types: sensor_freeze, door_open, estop, power_fault, degrade, clear
    """
    if not plc or not plant:
        raise HTTPException(503, "PLC not running")

    fault = cmd.fault.lower()
    zone  = cmd.zone.upper()

    if fault == 'sensor_freeze':
        plant.freeze_sensor(zone)
        plc.inject_fault('sensor_freeze', zone)
    elif fault == 'door_open':
        plant.open_door(zone, True)
        plc.inject_fault('door_open', zone)
    elif fault == 'estop':
        plc.inject_fault('estop', zone)
    elif fault == 'power_fault':
        plc.inject_fault('power_fault', zone)
    elif fault == 'degrade':
        plant.degrade_zone(zone, amount=0.2)
    elif fault == 'clear':
        plant.restore_sensor(zone)
        plant.open_door(zone, False)
        plc.inject_fault('clear', zone)
    else:
        raise HTTPException(400, f"Unknown fault type: {fault}")

    return {"ok": True, "fault": fault, "zone": zone}


@app.get("/export-csv")
async def export_csv():
    """Export historian to CSV."""
    if not historian:
        raise HTTPException(503, "Historian not running")
    csv_data = historian.export_csv()
    return PlainTextResponse(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=conservatwin_historian.csv"}
    )


@app.get("/history/recent")
async def get_recent_history(n: int = 300):
    """Return last N scan rows for trend charts."""
    if not historian:
        raise HTTPException(503, "Historian not running")
    return historian.get_recent(n)


@app.get("/history/events")
async def get_alarm_events(limit: int = 200):
    """
    Return historical alarm activation events (rising edges only).
    Each event: {timestamp, scan_number, key, zone, message, severity, acked}.
    """
    if not historian:
        raise HTTPException(503, "Historian not running")
    return historian.get_alarm_events(limit=limit)


@app.get("/history/range")
async def get_history_range(
    start_ts: float = 0.0,
    end_ts:   float = 0.0,
    step:     int   = 5,
):
    """
    Return historian rows between start_ts and end_ts (Unix timestamps).
    step: return every Nth row for downsampling over long ranges.
    If end_ts == 0, uses current time.
    """
    if not historian:
        raise HTTPException(503, "Historian not running")
    import time as _time
    if end_ts == 0.0:
        end_ts = _time.time()
    if start_ts == 0.0:
        start_ts = end_ts - 3600  # default: last 1 hour
    return historian.get_range(start_ts, end_ts, step=max(1, step))


@app.get("/history/bounds")
async def get_history_bounds():
    """Return min/max timestamps in the historian DB (for replay scrubber)."""
    if not historian:
        raise HTTPException(503, "Historian not running")
    return historian.get_time_bounds()


@app.post("/optimizer/config")
async def set_optimizer_config(alpha: float = 0.7, beta: float = 0.3, enabled: bool = True):
    """Configure preservation-first optimizer."""
    if not plc:
        raise HTTPException(503, "PLC not running")
    # Write to M bit
    from plc.memory import M
    plc.mem.M.write_bit(*M.PRES_FIRST_MODE, enabled)
    return {"ok": True, "alpha": alpha, "beta": beta, "enabled": enabled}
