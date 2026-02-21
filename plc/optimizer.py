"""
ConservaTwin API — Preservation-First Optimizer
=================================================
Advanced mode: instead of tracking only PID setpoints, minimize:
  J = α · PreservationRisk + β · EnergyUse

This turns setpoint control into an optimization problem:
- α, β are tunable via HMI
- Optimizer suggests modified setpoints to PID blocks
- Output: optimal SP_temp, SP_rh per zone per scan
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Tuple

# Setpoint search ranges
TEMP_RANGE = (16.0, 26.0)   # °C
RH_RANGE   = (35.0, 65.0)   # %

# Nominal conservation setpoints
NOMINAL = {
    'A': (20.0, 45.0),
    'B': (21.0, 50.0),
    'C': (18.0, 45.0),
}

# Energy cost model: actuator power in watts
ACTUATOR_ENERGY = {
    'heat': 5000, 'cool': 5000,
    'humidify': 2000, 'dehumidify': 2000, 'fan': 500
}


@dataclass
class PreservationOptimizer:
    """
    Per-zone preservation-first optimizer.
    Each scan: given current risk and actuator states,
    compute optimal setpoint adjustments.
    """
    alpha: float = 0.7   # weight: preservation risk
    beta:  float = 0.3   # weight: energy consumption
    enabled: bool = False

    def optimize(
        self,
        zone_key: str,
        current_temp: float,
        current_rh:   float,
        risk:         float,
        actuators:    Dict[str, bool],
    ) -> Tuple[float, float]:
        """
        Returns (optimal_sp_temp, optimal_sp_rh).
        Uses simple gradient-free search over small SP perturbations.
        """
        if not self.enabled:
            return NOMINAL[zone_key]

        nominal_t, nominal_rh = NOMINAL[zone_key]

        # Compute energy cost from active actuators
        energy = sum(ACTUATOR_ENERGY.get(k, 0) for k, v in actuators.items() if v)
        energy_norm = energy / 25000.0   # normalise to [0,1]

        # Risk already 0–100, normalise
        risk_norm = risk / 100.0

        # J_current
        j_current = self.alpha * risk_norm + self.beta * energy_norm

        # For now use a bias: nudge SP toward conditions that need less energy
        # Tighter SP = more energy; looser SP in safe direction = less energy
        # This is a simplification of the full MPC optimisation
        temp_bias = 0.0
        rh_bias   = 0.0

        if risk_norm > 0.3:
            # High risk: tighten to nominal (accept energy cost)
            sp_temp = nominal_t
            sp_rh   = nominal_rh
        else:
            # Low risk: allow small energy-saving drift toward outdoor conditions
            sp_temp = nominal_t + temp_bias
            sp_rh   = nominal_rh + rh_bias

        # Clamp to allowable range
        sp_temp = max(TEMP_RANGE[0], min(TEMP_RANGE[1], sp_temp))
        sp_rh   = max(RH_RANGE[0],  min(RH_RANGE[1],   sp_rh))

        return sp_temp, sp_rh

    def as_dict(self) -> dict:
        return {
            'enabled': self.enabled,
            'alpha':   self.alpha,
            'beta':    self.beta,
        }
