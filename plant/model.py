"""
ConservaTwin Plant — Museum Digital Twin
==========================================
Physics-based differential-equation model for three museum gallery zones.

Each zone models:
  - Thermal dynamics (RC circuit: Temp changes based on HVAC power + envelope loss)
  - Moisture dynamics (RH changes from HVAC + envelope leakage + disturbances)
  - RH slew rate (first-order derivative of RH)

Actuator effects, disturbances, and degradation are applied each update step.

The model is deterministic given the same dt, actuator commands, and disturbance seeds.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Dict, Any, Optional

# ─── Zone physical parameters ──────────────────────────────────────────────────

@dataclass
class ZoneParams:
    """Physical constants for one gallery zone."""
    name:            str
    zone_key:        str
    volume_m3:       float   # room volume
    thermal_mass:    float   # J/K — higher = slower temp change
    envelope_r:      float   # thermal resistance to outdoor (K/W)
    moisture_cap:    float   # kg — effective moisture capacity
    envelope_leak:   float   # kg/s per %RH difference — moisture leakage rate
    sp_temp:         float   # °C setpoint
    sp_rh:           float   # % setpoint


ZONE_PARAMS = {
    'A': ZoneParams(
        name="Gallery A — Troubles of My Head",
        zone_key='A',
        volume_m3=300,  thermal_mass=2.5e6, envelope_r=0.08,
        moisture_cap=180, envelope_leak=0.00008,
        sp_temp=20.0, sp_rh=45.0
    ),
    'B': ZoneParams(
        name="Gallery B — Basquiat: Soul That Saw the Inside",
        zone_key='B',
        volume_m3=400,  thermal_mass=3.0e6, envelope_r=0.06,
        moisture_cap=220, envelope_leak=0.00010,
        sp_temp=21.0, sp_rh=50.0
    ),
    'C': ZoneParams(
        name="Vault / Archive",
        zone_key='C',
        volume_m3=80,   thermal_mass=5.0e6, envelope_r=0.15,  # best insulation
        moisture_cap=60,  envelope_leak=0.00002,               # tightest envelope
        sp_temp=18.0, sp_rh=45.0
    ),
}

# Actuator power constants (W or kg/s)
HEATER_POWER     = 5000.0   # W
COOLER_POWER     = 5000.0   # W
HUMIDIFIER_RATE  = 0.008    # kg/s of water vapor
DEHUMID_RATE     = 0.008    # kg/s water removal
FAN_EFFICIENCY   = 1.3      # fan improves HVAC heat transfer by 30%

# CV thresholds for proportional actuation
CV_DEADBAND = 5.0           # % — below this partial power

# Thermal: J = mass * Cp * dT → dT/dt = Q / thermal_mass (simplified)
# Moisture: Air density ~1.2 kg/m³, ~0.012 kg water per kg air at 50%RH
def rh_to_kg_m3(rh_pct: float, temp_c: float) -> float:
    """Approximate absolute humidity kg/m³ from RH% and temperature."""
    # Saturation vapor pressure (Antoine-like)
    e_sat = 0.6112 * math.exp(17.67 * temp_c / (temp_c + 243.5))  # kPa
    e     = (rh_pct / 100.0) * e_sat
    return (0.622 * e) / (101.325 - e) * 1.2   # kg/m³


@dataclass
class ZoneState:
    """Mutable state for one gallery zone."""
    temp:        float   # °C
    rh:          float   # %
    rh_prev:     float   # previous scan RH (for slew rate)
    rh_slew:     float   # %/min
    door_open:   bool   = False
    valid:       bool   = True
    degradation: float  = 1.0   # 1.0 = healthy, 0.0 = fully failed
    _rh_prev_ts: float  = field(default_factory=time.time)


class ZoneModel:
    """
    Single gallery zone differential equation model.
    Update() is called once per PLC scan cycle.
    """

    def __init__(self, params: ZoneParams, seed: int = 42):
        self.params = params
        self._rng   = random.Random(seed)
        self.state  = ZoneState(
            temp     = params.sp_temp + self._rng.gauss(0, 0.3),
            rh       = params.sp_rh   + self._rng.gauss(0, 1.0),
            rh_prev  = params.sp_rh,
            rh_slew  = 0.0,
        )
        self._sim_time: float = 0.0   # accumulated simulated time (seconds)

    def update(
        self,
        dt: float,
        actuators: Dict[str, Any],
        outdoor_temp: float,
        outdoor_rh:   float,
        visitor_count: int = 0,
        door_open: bool = False,
    ) -> None:
        """
        Advance zone state by dt seconds.

        actuators dict keys: heat, cool, humidify, dehumidify, fan, temp_cv, rh_cv
        """
        p  = self.params
        st = self.state
        self._sim_time += dt

        fan_factor = FAN_EFFICIENCY if actuators.get('fan', False) else 1.0

        # ── Temperature dynamics ────────────────────────────────────────────
        # HVAC power: proportional to |CV| above deadband
        temp_cv = actuators.get('temp_cv', 0.0)
        hvac_heat_w = 0.0
        hvac_cool_w = 0.0

        if actuators.get('heat', False):
            power_frac = min(1.0, max(0.0, (temp_cv - CV_DEADBAND) / (100.0 - CV_DEADBAND)))
            hvac_heat_w = HEATER_POWER * power_frac * st.degradation * fan_factor
        if actuators.get('cool', False):
            power_frac = min(1.0, max(0.0, (-temp_cv - CV_DEADBAND) / (100.0 - CV_DEADBAND)))
            hvac_cool_w = COOLER_POWER * power_frac * st.degradation * fan_factor

        # Envelope heat loss/gain (outdoor coupling)
        q_envelope = (outdoor_temp - st.temp) / p.envelope_r   # W

        # Visitor heat load
        q_visitor = visitor_count * 80.0   # ~80W per person metabolic

        # Door open: increased envelope coupling 10×
        door_mult = 10.0 if door_open else 1.0
        q_envelope_door = q_envelope * door_mult

        q_net = hvac_heat_w - hvac_cool_w + q_envelope_door + q_visitor
        dT_dt = q_net / p.thermal_mass
        st.temp += dT_dt * dt
        st.temp = max(-5.0, min(40.0, st.temp))   # physical clamp

        # ── Moisture dynamics ───────────────────────────────────────────────
        rh_cv = actuators.get('rh_cv', 0.0)
        dm_dt = 0.0   # kg/s moisture change

        if actuators.get('humidify', False):
            power_frac = min(1.0, max(0.0, (rh_cv - CV_DEADBAND) / (100.0 - CV_DEADBAND)))
            dm_dt += HUMIDIFIER_RATE * power_frac * st.degradation
        if actuators.get('dehumidify', False):
            power_frac = min(1.0, max(0.0, (-rh_cv - CV_DEADBAND) / (100.0 - CV_DEADBAND)))
            dm_dt -= DEHUMID_RATE * power_frac * st.degradation

        # Envelope moisture leakage (outdoor RH coupling)
        rh_diff    = outdoor_rh - st.rh
        dm_envelope = p.envelope_leak * rh_diff * door_mult

        # Visitor moisture load (~40g water vapor per hour per person)
        dm_visitor = visitor_count * (40e-3 / 3600.0)

        # Noise: small stochastic disturbance
        noise = self._rng.gauss(0, 0.003)

        dm_total = dm_dt + dm_envelope + dm_visitor + noise

        # Convert moisture mass flow to %RH change
        # ΔRH ≈ Δm / (moisture_cap × dRH/dm)  — linearised
        # moisture_cap in kg, at SP: ~0.4%RH per gram of water
        drh_dt = dm_total / p.moisture_cap * 1000.0   # %/s
        rh_new = st.rh + drh_dt * dt
        rh_new = max(0.0, min(100.0, rh_new))

        # RH slew rate (%/min)
        rh_slew_raw = (rh_new - st.rh_prev) / (dt / 60.0)   # per minute
        st.rh_slew  = rh_slew_raw
        st.rh_prev  = st.rh
        st.rh       = rh_new
        st.door_open = door_open

    def get_sensor_values(self) -> Dict[str, Any]:
        return {
            'temp':     round(self.state.temp, 3),
            'rh':       round(self.state.rh,   3),
            'rh_slew':  round(self.state.rh_slew, 3),
            'door_open': self.state.door_open,
            'valid':    self.state.valid,
        }

    def freeze_sensor(self) -> None:
        """Fault injection: mark sensor as invalid (frozen)."""
        self.state.valid = False

    def restore_sensor(self) -> None:
        self.state.valid = True

    def degrade(self, amount: float = 0.1) -> None:
        """Reduce actuator effectiveness (degradation model)."""
        self.state.degradation = max(0.1, self.state.degradation - amount)


class MuseumPlant:
    """
    Top-level plant: three gallery zones + disturbance generator.
    This is what the PLCRuntime talks to.
    """

    def __init__(self, seed: int = 42):
        self._rng = random.Random(seed)
        self.zones = {
            'A': ZoneModel(ZONE_PARAMS['A'], seed=seed),
            'B': ZoneModel(ZONE_PARAMS['B'], seed=seed + 1),
            'C': ZoneModel(ZONE_PARAMS['C'], seed=seed + 2),
        }
        self._actuators: Dict[str, Dict] = {
            'A': {}, 'B': {}, 'C': {}
        }
        self._sim_time: float = 0.0
        self._visitor_count: int = 0
        self._door_states: Dict[str, bool] = {'A': False, 'B': False, 'C': False}

    def set_actuators(self, actuators: Dict[str, Dict]) -> None:
        """Called by PLC runtime to push Q image actuator state."""
        self._actuators = actuators

    def get_sensor_values(self) -> Dict[str, Dict]:
        """Called by PLC runtime to pull I image sensor values."""
        return {k: v.get_sensor_values() for k, v in self.zones.items()}

    def get_display_values(self) -> Dict[str, Any]:
        """Extended display info including actuator states."""
        return {
            zone_key: {
                **self.zones[zone_key].get_sensor_values(),
                'actuators': self._actuators.get(zone_key, {}),
                'name':      ZONE_PARAMS[zone_key].name,
                'sp_temp':   ZONE_PARAMS[zone_key].sp_temp,
                'sp_rh':     ZONE_PARAMS[zone_key].sp_rh,
                'degradation': self.zones[zone_key].state.degradation,
            }
            for zone_key in ['A', 'B', 'C']
        }

    def step(self, dt: float) -> None:
        """
        Advance plant by dt seconds.
        Called by API layer once per simulated scan interval.
        """
        self._sim_time += dt
        outdoor_temp, outdoor_rh = self._outdoor_conditions()

        # Dynamic visitor count (sinusoidal day/night cycle)
        hour = (self._sim_time / 3600.0) % 24
        if 9 <= hour <= 18:
            self._visitor_count = int(15 + 10 * math.sin(
                math.pi * (hour - 9) / 9))
        else:
            self._visitor_count = 0

        for zone_key, zone in self.zones.items():
            act = self._actuators.get(zone_key, {})
            zone.update(
                dt           = dt,
                actuators    = act,
                outdoor_temp = outdoor_temp,
                outdoor_rh   = outdoor_rh,
                visitor_count = self._visitor_count,
                door_open    = self._door_states[zone_key],
            )

    def _outdoor_conditions(self) -> tuple[float, float]:
        """Sinusoidal outdoor weather + Gaussian noise."""
        t = self._sim_time
        # Daily temperature cycle: 15°C avg, ±5°C amplitude, 24h period
        outdoor_temp = 15.0 + 5.0 * math.sin(2 * math.pi * t / 86400.0)
        outdoor_temp += self._rng.gauss(0, 0.5)
        # Humidity: 60% avg, ±15% amplitude, anti-correlated with temp
        outdoor_rh = 60.0 - 10.0 * math.sin(2 * math.pi * t / 86400.0)
        outdoor_rh += self._rng.gauss(0, 2.0)
        outdoor_rh = max(10.0, min(95.0, outdoor_rh))
        return outdoor_temp, outdoor_rh

    def open_door(self, zone: str, open_: bool) -> None:
        """Inject door-open disturbance."""
        if zone.upper() in self._door_states:
            self._door_states[zone.upper()] = open_

    def freeze_sensor(self, zone: str) -> None:
        if zone.upper() in self.zones:
            self.zones[zone.upper()].freeze_sensor()

    def restore_sensor(self, zone: str) -> None:
        if zone.upper() in self.zones:
            self.zones[zone.upper()].restore_sensor()

    def degrade_zone(self, zone: str, amount: float = 0.15) -> None:
        if zone.upper() in self.zones:
            self.zones[zone.upper()].degrade(amount)
