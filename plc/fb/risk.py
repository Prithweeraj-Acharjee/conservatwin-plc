"""
ConservaTwin PLC — Preservation Risk Index (PRI) Function Block
================================================================
Core innovation: computes a per-zone risk accumulator that drives alarms
and the Preservation-First control optimizer.

Each gallery has unique risk weights reflecting conservation science:

Zone A — "Troubles of My Head" (Collage/Paper/Adhesive):
  Risk drivers:  RH slew rate, high-RH duration
  Paper is most vulnerable to rapid moisture changes → slew rate heavily penalized

Zone B — "Basquiat: Soul That Saw the Inside" (Acrylic/Oil/Canvas):
  Risk drivers:  cumulative high-temp exposure, RH extremes
  Pigment layers crack in low RH (brittleness) or mold in high RH

Vault / Archive (Zone C):
  Any deviation heavily penalized — strictest preservation environment

Risk accumulates each scan and decays slowly when conditions are stable.
This means transient spikes leave a "memory" in the risk index,
accurately modeling real conservation physics.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Tuple


# ─── Risk weight constants ─────────────────────────────────────────────────────

class ZoneAWeights:
    SLEW_RATE         = 0.6   # primary driver: fast RH change
    HIGH_RH_DURATION  = 0.4   # secondary: sustained high RH
    TEMP_DEV          = 0.2   # minor contribution

class ZoneBWeights:
    HIGH_TEMP         = 0.5   # primary: temp overexposure
    RH_LOW            = 0.35  # brittleness risk
    RH_HIGH           = 0.35  # mold risk (both contribute)

class ZoneCWeights:
    TEMP_DEV          = 0.8   # vault is ultra-sensitive
    RH_DEV            = 0.8

# Risk accumulation / decay constants
ACCUMULATE_RATE = 0.02    # risk added per scan per unit of stress
DECAY_RATE      = 0.001   # risk removed per scan when stable
MAX_RISK        = 100.0   # maximum risk index value
RISK_ALARM_THR  = 30.0    # threshold that triggers alarm
RISK_CRITICAL_THR = 60.0  # critical threshold


@dataclass
class ZoneARiskBlock:
    """
    Zone A PRI — Gallery "Troubles of My Head"
    Collage/Paper/Adhesive: slew rate and sustained high RH are primary risks.
    """
    name: str = "ZONE_A_RISK"
    _risk: float = field(default=0.0, repr=False, init=False)

    def update(
        self,
        temp:     float,
        rh:       float,
        rh_slew:  float,   # %RH per minute
        dt:       float,   # scan dt in seconds
        sp_temp:  float = 20.0,
        sp_rh:    float = 45.0,
    ) -> Tuple[float, bool, bool]:
        """
        Returns: (risk_index, alarm_active, critical_active)
        rh_slew: absolute slew rate magnitude in %/min
        """
        stress = 0.0

        # RH slew rate stress (exponential penalty above 2%/min threshold)
        slew_threshold = 2.0   # %/min — below this is safe
        if abs(rh_slew) > slew_threshold:
            slew_excess = abs(rh_slew) - slew_threshold
            stress += ZoneAWeights.SLEW_RATE * (slew_excess ** 1.5)

        # High RH duration stress
        rh_excess = max(0.0, rh - (sp_rh + 5.0))   # above setpoint + tolerance
        stress += ZoneAWeights.HIGH_RH_DURATION * rh_excess

        # Temperature deviation
        temp_dev = abs(temp - sp_temp) - 2.0   # outside ±2°C tolerance
        if temp_dev > 0:
            stress += ZoneAWeights.TEMP_DEV * temp_dev

        # Accumulate / decay
        if stress > 0.01:
            self._risk += stress * ACCUMULATE_RATE * dt
        else:
            self._risk -= DECAY_RATE * dt

        self._risk = max(0.0, min(MAX_RISK, self._risk))
        return self._risk, self._risk >= RISK_ALARM_THR, self._risk >= RISK_CRITICAL_THR

    @property
    def risk(self) -> float:
        return self._risk

    def as_dict(self) -> dict:
        alarm    = self._risk >= RISK_ALARM_THR
        critical = self._risk >= RISK_CRITICAL_THR
        return {'name': self.name, 'risk': round(self._risk, 3),
                'alarm': alarm, 'critical': critical,
                'alarm_thr': RISK_ALARM_THR, 'critical_thr': RISK_CRITICAL_THR}


@dataclass
class ZoneBRiskBlock:
    """
    Zone B PRI — Gallery "Basquiat: Soul That Saw the Inside"
    Acrylic/Oil/Canvas: cumulative temp overexposure and RH extremes.
    """
    name: str = "ZONE_B_RISK"
    _risk: float = field(default=0.0, repr=False, init=False)
    _cumulative_temp_min: float = field(default=0.0, repr=False, init=False)

    def update(
        self,
        temp:    float,
        rh:      float,
        dt:      float,
        sp_temp: float = 21.0,
        sp_rh:   float = 50.0,
    ) -> Tuple[float, bool, bool, float]:
        """
        Returns: (risk_index, alarm_active, critical_active, cumulative_temp_min)
        """
        stress = 0.0

        # Cumulative temperature overexposure
        temp_excess = max(0.0, temp - (sp_temp + 2.0))
        if temp_excess > 0:
            self._cumulative_temp_min += (dt / 60.0)   # convert to minutes
        stress += ZoneBWeights.HIGH_TEMP * temp_excess

        # RH — both extremes are risks
        rh_low_dev  = max(0.0, (sp_rh - 5.0) - rh)    # below SP-5
        rh_high_dev = max(0.0, rh - (sp_rh + 5.0))    # above SP+5

        # Brittleness risk (low RH)
        if rh_low_dev > 0:
            stress += ZoneBWeights.RH_LOW * (rh_low_dev ** 1.2)

        # Mold/bloom risk (high RH)
        if rh_high_dev > 0:
            stress += ZoneBWeights.RH_HIGH * (rh_high_dev ** 1.2)

        # Chronic cumulative temp alarm (separate from instant stress)
        if self._cumulative_temp_min > 30.0:
            stress += 0.5   # sustained overexposure penalty

        if stress > 0.01:
            self._risk += stress * ACCUMULATE_RATE * dt
        else:
            self._risk -= DECAY_RATE * dt

        self._risk = max(0.0, min(MAX_RISK, self._risk))
        return (self._risk,
                self._risk >= RISK_ALARM_THR,
                self._risk >= RISK_CRITICAL_THR,
                self._cumulative_temp_min)

    @property
    def risk(self) -> float:
        return self._risk

    @property
    def cumulative_temp_min(self) -> float:
        return self._cumulative_temp_min

    def as_dict(self) -> dict:
        alarm    = self._risk >= RISK_ALARM_THR
        critical = self._risk >= RISK_CRITICAL_THR
        return {
            'name': self.name, 'risk': round(self._risk, 3),
            'cumulative_temp_min': round(self._cumulative_temp_min, 2),
            'alarm': alarm, 'critical': critical,
            'alarm_thr': RISK_ALARM_THR, 'critical_thr': RISK_CRITICAL_THR
        }


@dataclass
class ZoneCRiskBlock:
    """
    Vault / Zone C PRI — strictest preservation environment.
    Any deviation from setpoint is immediately and heavily penalized.
    """
    name: str = "ZONE_C_RISK"
    _risk: float = field(default=0.0, repr=False, init=False)

    def update(
        self,
        temp:    float,
        rh:      float,
        dt:      float,
        sp_temp: float = 18.0,
        sp_rh:   float = 45.0,
    ) -> Tuple[float, bool, bool]:
        stress = 0.0

        # Vault allows ZERO tolerance — any deviation is stress
        temp_dev = abs(temp - sp_temp)
        rh_dev   = abs(rh - sp_rh)

        stress += ZoneCWeights.TEMP_DEV * (temp_dev ** 1.8)
        stress += ZoneCWeights.RH_DEV   * (rh_dev   ** 1.8)

        if stress > 0.001:
            self._risk += stress * ACCUMULATE_RATE * dt
        else:
            self._risk -= DECAY_RATE * dt * 0.5   # vault decays slower too

        self._risk = max(0.0, min(MAX_RISK, self._risk))
        return self._risk, self._risk >= RISK_ALARM_THR, self._risk >= RISK_CRITICAL_THR

    @property
    def risk(self) -> float:
        return self._risk

    def as_dict(self) -> dict:
        alarm    = self._risk >= RISK_ALARM_THR
        critical = self._risk >= RISK_CRITICAL_THR
        return {'name': self.name, 'risk': round(self._risk, 3),
                'alarm': alarm, 'critical': critical,
                'alarm_thr': RISK_ALARM_THR, 'critical_thr': RISK_CRITICAL_THR}
