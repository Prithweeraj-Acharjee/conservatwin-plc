"""
ConservaTwin PLC — PID Function Block
=======================================
ISA-88-style PID with:
  - Anti-windup (integral clamping)
  - Bumpless transfer (Manual → Auto)
  - Output clamping
  - Derivative on measurement (not on error) to avoid derivative kick on SP change

PLC semantics: update() is called exactly once per scan cycle.
All state persists between scans (integral, prev_pv).
"""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class PIDBlock:
    """
    Parallel-form PID function block (ISA standard).

    Args:
        name   : logical name for diagnostics
        kp     : proportional gain
        ki     : integral gain (1/Ti in per-second units)
        kd     : derivative gain (Td in seconds)
        out_min: output lower clamp
        out_max: output upper clamp
    """
    name:    str   = "PID"
    kp:      float = 1.0
    ki:      float = 0.1
    kd:      float = 0.05
    out_min: float = 0.0
    out_max: float = 100.0

    _integral:  float = field(default=0.0,  repr=False, init=False)
    _prev_pv:   float = field(default=0.0,  repr=False, init=False)
    _output:    float = field(default=0.0,  repr=False, init=False)
    _p_term:    float = field(default=0.0,  repr=False, init=False)
    _i_term:    float = field(default=0.0,  repr=False, init=False)
    _d_term:    float = field(default=0.0,  repr=False, init=False)
    _initialised: bool = field(default=False, repr=False, init=False)

    def update(self, sp: float, pv: float, dt: float, auto: bool = True) -> float:
        """
        Call once per scan cycle.

        sp   : setpoint
        pv   : process variable (from I image)
        dt   : scan interval in seconds
        auto : True = Auto mode, False = Manual (output not updated)

        Returns control output (clamped to [out_min, out_max]).
        """
        # Track latest sp/pv/mode for HMI serialisation
        self._sp = sp
        self._pv = pv
        self._mode = 'auto' if auto else 'manual'

        if not self._initialised:
            self._prev_pv = pv
            self._initialised = True

        if not auto:
            # Bumpless transfer: track PV so no bump when switching to Auto
            self._prev_pv = pv
            self._integral = self._output / max(self.ki, 1e-9)
            return self._output

        error = sp - pv

        # Proportional
        self._p_term = self.kp * error

        # Integral with anti-windup
        self._integral += error * dt
        raw_i = self.ki * self._integral
        # Clamp integral contribution (anti-windup)
        raw_i = max(self.out_min, min(self.out_max, raw_i))
        self._i_term = raw_i
        # Back-calculate integral to prevent wind-up beyond clamps
        if self.ki > 0:
            self._integral = raw_i / self.ki

        # Derivative on measurement (avoids derivative kick on SP change)
        dpv = (pv - self._prev_pv) / max(dt, 1e-9)
        self._d_term = -self.kd * dpv
        self._prev_pv = pv

        raw_out = self._p_term + self._i_term + self._d_term
        self._output = max(self.out_min, min(self.out_max, raw_out))
        return self._output

    @property
    def output(self) -> float:
        return self._output

    def as_dict(self) -> dict:
        sp   = getattr(self, '_sp',   0.0)
        pv   = getattr(self, '_pv',   0.0)
        mode = getattr(self, '_mode', 'auto')
        return {
            'name':   self.name,
            'kp': self.kp, 'ki': self.ki, 'kd': self.kd,
            'sp':     round(sp, 3),
            'pv':     round(pv, 3),
            'cv':     round(self._output, 3),
            'error':  round(sp - pv, 3),
            'mode':   mode,
            'output': round(self._output, 3),
            'p_term': round(self._p_term, 3),
            'i_term': round(self._i_term, 3),
            'd_term': round(self._d_term, 3),
        }



@dataclass
class PIDBank:
    """All PID blocks, one per zone per controlled variable."""
    # Zone A: temp SP=20, RH SP=45
    a_temp: PIDBlock = field(default_factory=lambda: PIDBlock(
        name="A_TEMP", kp=2.0, ki=0.05, kd=0.5, out_min=-100.0, out_max=100.0))
    a_rh:   PIDBlock = field(default_factory=lambda: PIDBlock(
        name="A_RH",   kp=3.0, ki=0.08, kd=0.2, out_min=-100.0, out_max=100.0))

    # Zone B: temp SP=21, RH SP=50
    b_temp: PIDBlock = field(default_factory=lambda: PIDBlock(
        name="B_TEMP", kp=2.0, ki=0.05, kd=0.5, out_min=-100.0, out_max=100.0))
    b_rh:   PIDBlock = field(default_factory=lambda: PIDBlock(
        name="B_RH",   kp=3.0, ki=0.08, kd=0.2, out_min=-100.0, out_max=100.0))

    # Zone C (Vault): strictest — higher gains
    c_temp: PIDBlock = field(default_factory=lambda: PIDBlock(
        name="C_TEMP", kp=4.0, ki=0.15, kd=0.8, out_min=-100.0, out_max=100.0))
    c_rh:   PIDBlock = field(default_factory=lambda: PIDBlock(
        name="C_RH",   kp=5.0, ki=0.20, kd=0.3, out_min=-100.0, out_max=100.0))

    def as_dict(self) -> dict:
        return {name: getattr(self, name).as_dict() for name in self.__dataclass_fields__}
