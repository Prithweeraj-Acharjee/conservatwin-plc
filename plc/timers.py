"""
ConservaTwin PLC — Timers Module
=================================
Implements IEC 61131-3-style scan-based timers.

CRITICAL SEMANTIC: Timers update ONLY when their .update(dt) method is called
during a scan cycle. They never accumulate time autonomously. This mirrors
real PLC behavior where timers are driven by scan edges, not wall-clock threads.

Timer types:
  TON  — On-delay: output goes HIGH after IN has been continuously HIGH for PT
  TOF  — Off-delay: output stays HIGH for PT after IN goes LOW
  RTO  — Retentive on-delay: accumulates ET across resets; only CLR resets ET
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TON:
    """
    On-Delay Timer (IEC 61131-3 TON).

    Inputs:
      IN : bool  — enable input (must stay TRUE to accumulate)
      PT : float — preset time in seconds

    Outputs (read-only):
      Q  : bool  — TRUE when ET >= PT
      ET : float — elapsed time in seconds (resets when IN goes FALSE)
    """
    PT: float = 1.0
    _et: float = field(default=0.0, repr=False, init=False)
    _q:  bool  = field(default=False, repr=False, init=False)

    def update(self, IN: bool, dt: float) -> tuple[bool, float]:
        """
        Call once per scan cycle.
        Returns (Q, ET).
        dt must be the scan interval in seconds.
        """
        if IN:
            self._et = min(self._et + dt, self.PT)
        else:
            self._et = 0.0
        self._q = self._et >= self.PT
        return self._q, self._et

    @property
    def Q(self) -> bool:
        return self._q

    @property
    def ET(self) -> float:
        return self._et

    def as_dict(self) -> dict:
        return {'type': 'TON', 'PT': self.PT, 'ET': round(self._et, 3), 'Q': self._q}


@dataclass
class TOF:
    """
    Off-Delay Timer (IEC 61131-3 TOF).

    IN  : enable input
    PT  : preset time
    Q   : TRUE while IN is TRUE OR ET < PT after IN went FALSE
    ET  : elapsed time since IN went FALSE (0 while IN is TRUE)
    """
    PT: float = 1.0
    _et:   float = field(default=0.0,   repr=False, init=False)
    _q:    bool  = field(default=False, repr=False, init=False)
    _prev: bool  = field(default=False, repr=False, init=False)

    def update(self, IN: bool, dt: float) -> tuple[bool, float]:
        if IN:
            self._et = 0.0
            self._q  = True
        else:
            if self._prev:       # falling edge of IN → start timing
                self._et = 0.0
            self._et = min(self._et + dt, self.PT)
            self._q  = self._et < self.PT
        self._prev = IN
        return self._q, self._et

    @property
    def Q(self) -> bool:
        return self._q

    @property
    def ET(self) -> float:
        return self._et

    def as_dict(self) -> dict:
        return {'type': 'TOF', 'PT': self.PT, 'ET': round(self._et, 3), 'Q': self._q}


@dataclass
class RTO:
    """
    Retentive On-Delay Timer (IEC 61131-3 RTO).

    ET accumulates across multiple IN=TRUE intervals.
    Only a CLR=TRUE resets ET.
    Q goes TRUE (and stays) once ET >= PT.
    """
    PT: float = 1.0
    _et: float = field(default=0.0,  repr=False, init=False)
    _q:  bool  = field(default=False, repr=False, init=False)

    def update(self, IN: bool, CLR: bool, dt: float) -> tuple[bool, float]:
        if CLR:
            self._et = 0.0
            self._q  = False
        elif IN and not self._q:
            self._et = min(self._et + dt, self.PT)
            if self._et >= self.PT:
                self._q = True
        return self._q, self._et

    @property
    def Q(self) -> bool:
        return self._q

    @property
    def ET(self) -> float:
        return self._et

    def as_dict(self) -> dict:
        return {'type': 'RTO', 'PT': self.PT, 'ET': round(self._et, 3), 'Q': self._q}


@dataclass
class TimerBank:
    """
    All named timers used across the PLC program.
    Each timer is accessible by a logical name.
    Serialisable for historian and WebSocket snapshot.
    """
    # Zone A timers
    a_rh_high_ton:      TON = field(default_factory=lambda: TON(PT=300.0))   # 5 min high-RH
    a_rh_slew_ton:      TON = field(default_factory=lambda: TON(PT=60.0))    # 1 min slew warning
    a_temp_alarm_tof:   TOF = field(default_factory=lambda: TOF(PT=30.0))    # 30 s alarm hold
    a_recovery_rto:     RTO = field(default_factory=lambda: RTO(PT=600.0))   # 10 min recovery

    # Zone B timers
    b_temp_high_rto:    RTO = field(default_factory=lambda: RTO(PT=1800.0))  # 30 min cumulative
    b_rh_low_ton:       TON = field(default_factory=lambda: TON(PT=120.0))   # 2 min low-RH
    b_rh_high_ton:      TON = field(default_factory=lambda: TON(PT=240.0))   # 4 min high-RH
    b_temp_alarm_tof:   TOF = field(default_factory=lambda: TOF(PT=30.0))

    # Zone C (Vault) — fastest escalation
    c_temp_alarm_ton:   TON = field(default_factory=lambda: TON(PT=15.0))    # 15 s alarm
    c_rh_alarm_ton:     TON = field(default_factory=lambda: TON(PT=15.0))
    c_recovery_rto:     RTO = field(default_factory=lambda: RTO(PT=300.0))   # 5 min recovery

    # Watchdog timer
    watchdog_ton:       TON = field(default_factory=lambda: TON(PT=2.0))     # 2 s overrun

    def as_dict(self) -> dict:
        return {name: getattr(self, name).as_dict() for name in self.__dataclass_fields__}
