# ConservaTwin — Museum Conservation Digital Twin

ConservaTwin is a PLC-driven digital twin designed to model and monitor environmental control in museum and archival spaces. The system simulates temperature and relative humidity dynamics across multiple gallery zones and applies closed-loop control logic to maintain conservation-grade conditions.

Rather than relying only on threshold alarms, ConservaTwin introduces a **Preservation Risk Index (PRI)** to quantify long-term environmental stress on artworks based on deviation from optimal ranges, stability, and rate-of-change. This enables risk-aware decision making for cultural heritage preservation.

The project is designed to behave like a real industrial control system, including alarms, fault handling, and operator acknowledgment, while remaining fully simulated and safe to deploy publicly.

---

## System Overview

Each gallery zone operates as an independent control system with:
- Simulated sensors (temperature and relative humidity)
- PLC-style control logic (PID-based)
- Actuators (heating, cooling, dehumidification)
- Alarm and fault handling
- Historical logging and replay

A SCADA-style Human–Machine Interface (HMI) provides real-time visualization, alarm acknowledgment, and historical trend analysis.

---

## Key Features

- Multi-zone temperature and humidity control  
- PLC-style PID control loops  
- Preservation Risk Index (PRI) for long-term exposure assessment  
- Alarm management with proper acknowledgment semantics  
- Sensor fault detection and fail-safe behavior  
- Historical trending and replay mode  
- Professional SCADA-style HMI  
- Public demo mode (read-only)

---

## Architecture

- **Simulated PLC Runtime**
  - Control Logic (PID, interlocks, alarms)
  - Plant Model (thermal & hygrometric dynamics)
  - Historian (time-indexed data)

- **Backend API (WebSocket / REST)**
  - Bridges PLC runtime ↔ HMI
  - State streaming and replay

- **Frontend HMI (Next.js)**
  - Real-time monitoring, alarms, trends

---

## How Data Is Generated

Sensor values are **not random**.

Each zone uses a simplified physical plant model that includes:
- Thermal inertia
- Environmental decay
- Actuator-driven change rates
- Optional bounded sensor noise

This produces smooth, deterministic behavior similar to real HVAC-controlled spaces and allows realistic testing of control logic and failure modes.

---

## Alarm & ACK Behavior

- Alarms indicate active fault or unsafe conditions
- Acknowledging an alarm confirms operator awareness
- ACK does **not** clear the fault
- Alarms clear only when the underlying condition is resolved

This matches standard industrial SCADA behavior.

---

## Demo Mode

The public deployment operates in **DEMO MODE**:
- Control actions are disabled
- Data is simulated or replayed
- No physical equipment is connected

---

## Technology Stack

- **PLC Logic & Simulation**: Structured-text–style control modeling
- **Backend**: Python (FastAPI), WebSocket, REST API
- **Frontend HMI**: Next.js, React, TypeScript
- **Visualization**: Recharts
- **Deployment**: Vercel (HMI), Render (API)

---

## Disclaimer

This project demonstrates a **simulated PLC-driven digital twin**.  
No real museum HVAC systems or physical equipment are connected.  
The system is intended for educational, research, and portfolio purposes.

---

## Motivation

Museum conservation requires extreme environmental stability, and damage often results from long-term exposure rather than immediate failures. ConservaTwin explores how control systems can move beyond simple alarms toward exposure-aware, risk-based monitoring.

---

## Author

Developed as an independent engineering and artist's project focused on control systems, digital twins, and cultural heritage technology.
