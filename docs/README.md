# ConservaTwin PLC — Architecture & I/O Reference

## System Overview

ConservaTwin PLC is a PLC-authentic digital twin of a three-zone museum conservation facility. It implements a strict three-layer separation:

```
┌─────────────────────────────────────────────────────────────┐
│  HMI / SCADA (Next.js 16 + TypeScript)                      │
│  • WebSocket client (live scan data)                         │
│  • REST commands (mode, ack, estop, fault injection)         │
└────────────────────▲──────────────────────────┬────────────┘
                     │ WS /ws  REST /command/*  │
┌────────────────────┴──────────────────────────▼────────────┐
│  API Layer (FastAPI / uvicorn)                               │
│  • Bridges PLC runtime ↔ HMI                                │
│  • Historian (SQLite WAL) — 7-day rolling window             │
│  • REST endpoints: /history/range, /history/events, /bounds  │
└──────────── plc.runtime ◄──plant.model ────────────────────┘
             (scan loop)       (physics ODE)
```

### Scan Cycle (200ms nominal)
1. `read_inputs()` — copy plant sensor values → I image
2. `safety.execute()` — E-Stop, power fault, watchdog check
3. Zone programs — `zone_a`, `zone_b`, `vault` (only if safe)
4. `write_outputs()` — Q image actuator commands → plant
5. Snapshot → historian queue → WebSocket broadcast

---

## Three Gallery Zones

| Zone | Name | Artwork Medium | SP Temp | SP RH | Tolerance |
|------|------|----------------|---------|-------|-----------|
| A | Gallery A | Collage / Paper / Adhesive | 20 °C | 45 % | ±2 °C, ±5 % |
| B | Gallery B | Acrylic / Oil / Canvas | 21 °C | 50 % | ±2 °C, ±5 % |
| C | Vault / Archive | Paper, Photography, Textiles | 18 °C | 45 % | ±1 °C, ±3 % |

---

## I/O Map — Input Image (I)

| Address | Tag | Description |
|---------|-----|-------------|
| I0.0 | A_TEMP_VALID | Zone A temperature sensor valid |
| I0.1 | A_TEMP_HIGH | Zone A temp > SP+2 |
| I0.2 | A_TEMP_LOW | Zone A temp < SP-2 |
| I0.3 | A_RH_VALID | Zone A RH sensor valid |
| I0.4 | A_RH_HIGH | Zone A RH > SP+5 |
| I0.5 | A_RH_LOW | Zone A RH < SP-5 |
| I0.6 | A_RH_SLEW_WARN | Zone A RH slew rate warning |
| I0.7 | A_DOOR_OPEN | Zone A access door open |
| IW2 | A_TEMP_W | Zone A temperature × 100 (fixed-point) |
| IW4 | A_RH_W | Zone A RH × 100 |
| IW6 | A_SLEW_W | Zone A RH slew rate × 100 |
| I8.0 | B_TEMP_VALID | Zone B temperature sensor valid |
| I8.3 | B_RH_VALID | Zone B RH sensor valid |
| I8.6 | B_CUMTEMP_WARN | Cumulative temp overexposure warning |
| I8.7 | B_DOOR_OPEN | Zone B door open |
| IW10 | B_TEMP_W | Zone B temperature × 100 |
| IW12 | B_RH_W | Zone B RH × 100 |
| IW14 | B_CUMTEMP_W | Cumulative overexposure minutes × 10 |
| I16.0 | C_TEMP_VALID | Vault temperature sensor valid |
| I16.3 | C_RH_VALID | Vault RH sensor valid |
| I16.7 | C_DOOR_OPEN | Vault door open |
| IW18 | C_TEMP_W | Vault temperature × 100 |
| IW20 | C_RH_W | Vault RH × 100 |
| I24.0 | ESTOP | Hardware E-stop (NC contact) |
| I24.1 | WATCHDOG_OK | PLC watchdog heartbeat |
| I24.2 | PWR_OK | Power supply healthy |
| I24.3 | FIRE_ALARM | Building fire alarm integration |

---

## I/O Map — Output Image (Q)

| Address | Tag | Description |
|---------|-----|-------------|
| Q0.0 | A_HEAT | Zone A heating coil |
| Q0.1 | A_COOL | Zone A cooling coil |
| Q0.2 | A_HUMIDIFY | Zone A humidifier |
| Q0.3 | A_DEHUMIDIFY | Zone A dehumidifier |
| Q0.4 | A_FAN | Zone A circulation fan |
| Q0.5 | A_ALARM_LIGHT | Zone A alarm indicator |
| QW2 | A_TEMP_CV_W | Zone A temp PID control value × 100 |
| QW4 | A_RH_CV_W | Zone A RH PID control value × 100 |
| Q4.0 | B_HEAT | Zone B heating coil |
| Q4.1 | B_COOL | Zone B cooling coil |
| Q4.2 | B_HUMIDIFY | Zone B humidifier |
| Q4.3 | B_DEHUMIDIFY | Zone B dehumidifier |
| Q4.4 | B_FAN | Zone B fan |
| Q4.5 | B_ALARM_LIGHT | Zone B alarm indicator |
| QW10 | B_TEMP_CV_W | Zone B temp PID CV × 100 |
| QW12 | B_RH_CV_W | Zone B RH PID CV × 100 |
| Q8.0 | C_HEAT | Vault heating coil |
| Q8.1 | C_COOL | Vault cooling coil |
| Q8.2 | C_HUMIDIFY | Vault humidifier |
| Q8.3 | C_DEHUMIDIFY | Vault dehumidifier |
| Q8.4 | C_FAN | Vault fan |
| Q8.5 | C_ALARM_LIGHT | Vault alarm indicator |
| QW18 | C_TEMP_CV_W | Vault temp PID CV × 100 |
| QW20 | C_RH_CV_W | Vault RH PID CV × 100 |
| Q24.0 | SAFE_STATE | All actuators forced off |
| Q24.1 | ESTOP_ACK | E-Stop acknowledged |

---

## I/O Map — Marker Memory (M)

| Address | Tag | Description |
|---------|-----|-------------|
| M0.0 | A_AUTO | Zone A in Auto mode (1=Auto, 0=Manual) |
| M0.1–4 | A_MANUAL_* | Manual actuator overrides for Zone A |
| M0.5 | A_ALARM_ACK | Zone A alarm acknowledge pulse |
| M4.0–5 | B_AUTO, B_MANUAL_*, B_ALARM_ACK | Zone B mode and manual bits |
| M8.0–5 | C_AUTO, C_MANUAL_*, C_ALARM_ACK | Vault mode and manual bits |
| M12.0 | ESTOP_CMD | Software E-Stop from HMI |
| M12.1 | PRES_FIRST_MODE | Preservation-first optimizer enable |
| M12.2 | REPLAY_MODE | Historian replay active |
| M12.3 | FAULT_INJECT | Test harness fault injection active |
| M12.4 | GLOBAL_ACK | Acknowledge all zone alarms |
| M16.0–3 | Zone A alarm latches | A_ALARM_LATCHED, A_TEMP, A_RH, A_SLEW |
| M17.0–3 | Zone B alarm latches | B_ALARM_LATCHED, B_TEMP, B_RH, B_CUMTEMP |
| M18.0–2 | Zone C alarm latches | C_ALARM_LATCHED, C_TEMP, C_RH |
| M19.0 | WATCHDOG_ALARM | Scan overrun watchdog tripped |
| M19.1–3 | SENSOR_*_INVALID | Sensor fault latch per zone |
| MW20 | A_RISK_W | Zone A PRI × 100 |
| MW22 | B_RISK_W | Zone B PRI × 100 |
| MW24 | C_RISK_W | Vault PRI × 100 |

---

## Alarm Table

| Key | Zone | Message | Severity | Latch | Timer |
|-----|------|---------|----------|-------|-------|
| a_temp | A | Temperature deviation | alarm | Yes | immediate |
| a_rh | A | RH out of range | alarm | Yes | TON 5 min |
| a_slew | A | RH slew rate exceeded | warning | Yes | TON 1 min |
| a_sensor | A | Sensor fault / freeze | critical | Yes | immediate |
| b_temp | B | Temperature deviation | alarm | Yes | immediate |
| b_rh | B | RH out of range | alarm | Yes | TON 2–4 min |
| b_cumtemp | B | Cumulative temp exceedance | alarm | Yes | cumulative > 30 min |
| b_sensor | B | Sensor fault / freeze | critical | Yes | immediate |
| c_temp | C | Temperature deviation | alarm | Yes | TON 15 s |
| c_rh | C | RH out of range | alarm | Yes | TON 15 s |
| c_sensor | C | Sensor fault / freeze | critical | Yes | immediate |
| watchdog | SYS | PLC watchdog overrun | critical | Yes | immediate |
| estop | SYS | Emergency stop active | critical | Yes | never auto-clears |

---

## Preservation Risk Index (PRI)

Each zone maintains a continuous **PRI** value (0–100) that accumulates under adverse conditions and decays slowly during stable operation:

| Zone | Primary Drivers | Key Threshold |
|------|----------------|---------------|
| A | RH slew rate, sustained high RH | Slew > 2 %/min |
| B | Cumulative temp overexposure, RH extremes | Temp high > 30 min |
| C | Any temperature or RH deviation (harshest) | ±1 °C, ±3 % |

- **PRI > 30** → alarm threshold  
- **PRI > 60** → critical threshold

---

## REST API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | System health + scan counter |
| GET | `/state` | Full PLC state (REST polling fallback) |
| GET | `/export-csv` | Download historian CSV |
| GET | `/history/recent?n=300` | Last N scan rows |
| GET | `/history/range?start_ts&end_ts&step` | Historian rows in time range |
| GET | `/history/events?limit=200` | Alarm event log (rising edges) |
| GET | `/history/bounds` | Min/max timestamps in historian |
| POST | `/command/mode` | Set zone Auto/Manual |
| POST | `/command/ack-alarm` | Acknowledge zone alarm |
| POST | `/command/manual` | Set manual actuator bit |
| POST | `/command/estop` | Software E-Stop |
| POST | `/inject-fault` | Test harness fault injection |
| POST | `/optimizer/config` | Configure Preservation-First optimizer |

---

## Running the System

### Backend
```powershell
cd conservatwin-plc
pip install -r requirements.txt
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

### HMI
```powershell
cd hmi
npm install
npm run dev
# Open http://localhost:3000
```

### Test Harness (backend must be running)
```powershell
cd conservatwin-plc
python tests/test_harness.py
# Results saved to tests/test_report.html and tests/test_report.json
```

---

## Directory Structure

```
conservatwin-plc/
├── api/
│   ├── main.py          FastAPI app, WebSocket, REST endpoints
│   └── historian.py     SQLite historian (WAL mode, 7-day prune)
├── plant/
│   └── model.py         Physics ODE model (3 zones)
├── plc/
│   ├── memory.py        I/Q/M image tables (IEC 61131-3 addressing)
│   ├── runtime.py       PLC scan cycle engine
│   ├── timers.py        TON/TOF/RTO timer function blocks
│   ├── optimizer.py     Preservation-first optimizer (α·Risk + β·Energy)
│   ├── fb/
│   │   ├── alarm.py     AlarmLatch function block
│   │   ├── debounce.py  Sensor debounce function block
│   │   ├── pid.py       PID function block (anti-windup)
│   │   ├── risk.py      ZoneA/B/C Preservation Risk Index blocks
│   │   └── watchdog.py  Scan overrun watchdog
│   └── program/
│       ├── safety.py    Safety network (E-Stop, interlocks)
│       ├── zone_a.py    Gallery A control logic
│       ├── zone_b.py    Gallery B control logic
│       └── vault.py     Vault (Zone C) control logic
├── hmi/                 Next.js 16 SCADA frontend
│   └── src/
│       ├── app/         Root layout + main SCADA page
│       ├── components/  ZoneCard, AlarmBanner, TrendChart, etc.
│       └── hooks/       usePLCSocket (WebSocket + REST)
├── tests/
│   └── test_harness.py  Automated fault injection test suite
├── docs/
│   └── README.md        This file
├── historian.db         SQLite historian database
└── requirements.txt     Python dependencies
```
