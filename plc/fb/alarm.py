"""
ConservaTwin PLC — Alarm Latch Function Block
==============================================
IEC 61131-3 style latched alarm with acknowledge.

Semantics:
  SET   : alarm condition (from I or computed logic)
  ACK   : acknowledge bit from M memory (operator action via HMI)
  LATCH : internal latch — stays TRUE after SET goes FALSE until ACK is TRUE
  Q     : output (TRUE when latched and not yet acknowledged)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List


@dataclass
class AlarmLatch:
    """
    Latched alarm function block.

    SET goes high → alarm latches → Q=TRUE → operator sets ACK=TRUE → latch clears.
    If SET is still TRUE when ACK is asserted, latch immediately re-latches.
    """
    name:  str  = "ALARM"
    priority: int = 2   # 1=Critical, 2=High, 3=Medium, 4=Low

    _latched:  bool  = field(default=False, repr=False, init=False)
    _acked:    bool  = field(default=False, repr=False, init=False)

    def update(self, SET: bool, ACK: bool) -> bool:
        """
        Call once per scan cycle.
        Returns Q output (latched and not yet cleared).
        """
        if SET:
            self._latched = True
            self._acked   = False
        if ACK and self._latched and not SET:
            self._latched = False
            self._acked   = True
        return self._latched

    @property
    def Q(self) -> bool:
        return self._latched

    @property
    def acknowledged(self) -> bool:
        return self._acked

    def as_dict(self) -> dict:
        return {
            'name': self.name,
            'priority': self.priority,
            'latched': self._latched,
            'acknowledged': self._acked,
        }


@dataclass
class AlarmBank:
    """All alarm latch instances used across the PLC program."""
    # Zone A
    a_temp:    AlarmLatch = field(default_factory=lambda: AlarmLatch("A_TEMP",    priority=2))
    a_rh:      AlarmLatch = field(default_factory=lambda: AlarmLatch("A_RH",      priority=2))
    a_slew:    AlarmLatch = field(default_factory=lambda: AlarmLatch("A_RH_SLEW", priority=2))
    a_sensor:  AlarmLatch = field(default_factory=lambda: AlarmLatch("A_SENSOR",  priority=1))

    # Zone B
    b_temp:    AlarmLatch = field(default_factory=lambda: AlarmLatch("B_TEMP",    priority=2))
    b_rh:      AlarmLatch = field(default_factory=lambda: AlarmLatch("B_RH",      priority=2))
    b_cumtemp: AlarmLatch = field(default_factory=lambda: AlarmLatch("B_CUMTEMP", priority=1))
    b_sensor:  AlarmLatch = field(default_factory=lambda: AlarmLatch("B_SENSOR",  priority=1))

    # Zone C (Vault) — strictest
    c_temp:    AlarmLatch = field(default_factory=lambda: AlarmLatch("C_TEMP",    priority=1))
    c_rh:      AlarmLatch = field(default_factory=lambda: AlarmLatch("C_RH",      priority=1))
    c_sensor:  AlarmLatch = field(default_factory=lambda: AlarmLatch("C_SENSOR",  priority=1))

    # System
    watchdog:  AlarmLatch = field(default_factory=lambda: AlarmLatch("WATCHDOG",  priority=1))
    estop:     AlarmLatch = field(default_factory=lambda: AlarmLatch("ESTOP",     priority=1))

    def active_alarms(self) -> List[dict]:
        """Return list of all currently latched alarms, sorted by priority."""
        result = []
        for name in self.__dataclass_fields__:
            a: AlarmLatch = getattr(self, name)
            if a.Q:
                result.append(a.as_dict())
        return sorted(result, key=lambda x: x['priority'])

    def as_dict(self) -> dict:
        return {name: getattr(self, name).as_dict() for name in self.__dataclass_fields__}
