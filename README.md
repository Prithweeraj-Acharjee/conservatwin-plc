<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0d1117,50:161b22,100:1f6feb&height=200&section=header&text=ConservaTwin%20PLC&fontSize=40&fontColor=ffffff&animation=fadeIn&fontAlignY=35&desc=PLC-Driven%20Museum%20Conservation%20Digital%20Twin&descSize=16&descAlignY=55" width="100%" />

[![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)]()
[![PLC](https://img.shields.io/badge/PLC-PID_Control-FF6600?style=for-the-badge)]()
[![SCADA](https://img.shields.io/badge/SCADA-HMI-2196F3?style=for-the-badge)]()

</div>

---

## About

**ConservaTwin PLC** is a PLC-driven digital twin designed to model and monitor environmental control in museum and archival spaces. The system simulates temperature and relative humidity dynamics across multiple gallery zones using closed-loop PID control logic.

Rather than relying only on threshold alarms, ConservaTwin introduces a **Preservation Risk Index (PRI)** to quantify long-term environmental stress on artworks based on deviation from optimal ranges, stability, and rate-of-change.

---

## Features

- **PID Control System** - closed-loop proportional-integral-derivative control for HVAC simulation
- **Multi-Zone SCADA HMI** - supervisory control and data acquisition interface for multiple gallery zones
- **Preservation Risk Index (PRI)** - quantifies environmental stress using deviation, stability, and rate metrics
- **Zone-Based Monitoring** - independent control for different gallery environments
- **Risk-Aware Decision Making** - alerts based on PRI thresholds, not just raw sensor values

---

## PRI Calculation

The Preservation Risk Index combines three factors:

```
PRI = w1 * Deviation + w2 * Instability + w3 * RateOfChange

Where:
  Deviation   = |current - optimal| / tolerance
  Instability = std_dev(readings) over time window
  RateOfChange = |delta| per unit time
```

This enables risk-aware conservation decisions that account for both acute and chronic environmental threats.

---

## Architecture

```
Simulated Sensors (Temp + RH per zone)
              |
              v
      PID Controller
     /        |        \
  Zone 1    Zone 2    Zone N
     \        |        /
              v
      PRI Risk Engine
              |
              v
      SCADA HMI Dashboard
```

---

## Tech Stack

<div align="center">

| Category | Technology |
|----------|-----------|
| **Language** | Python |
| **Control** | PID Controllers |
| **Interface** | SCADA HMI |
| **Modeling** | Digital Twin Simulation |
| **Visualization** | Matplotlib, Plotly |

</div>

---

## Getting Started

```bash
# Clone the repository
git clone https://github.com/Prithweeraj-Acharjee/conservatwin-plc.git
cd conservatwin-plc

# Install dependencies
pip install -r requirements.txt

# Run the simulation
python main.py
```

---

## Author

**Prithweeraj Acharjee Porag**

[![GitHub](https://img.shields.io/badge/GitHub-Prithweeraj--Acharjee-181717?style=flat-square&logo=github)](https://github.com/Prithweeraj-Acharjee)
[![Portfolio](https://img.shields.io/badge/Portfolio-prithwee.vercel.app-000000?style=flat-square&logo=vercel)](https://prithwee.vercel.app)

---

## License

This project is open source and available under the [MIT License](LICENSE).

<div align="center">
<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0d1117,50:161b22,100:1f6feb&height=100&section=footer" width="100%" />
</div>
