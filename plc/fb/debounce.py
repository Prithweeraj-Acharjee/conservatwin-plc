"""
ConservaTwin PLC — Debounce Function Block
==========================================
Scan-count-based signal debounce.
A transition is accepted only after the input has been stable for N scans.
This prevents false alarms from noisy sensors.
"""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class DebounceBlock:
    """
    Scan-count debounce for digital signals.

    stable_scans : number of consecutive scans input must be stable before output changes
    """
    name:         str = "DEBOUNCE"
    stable_scans: int = 3

    _counter:     int  = field(default=0,     repr=False, init=False)
    _output:      bool = field(default=False, repr=False, init=False)
    _pending:     bool = field(default=False, repr=False, init=False)

    def update(self, IN: bool) -> bool:
        """Call once per scan. Returns debounced output."""
        if IN != self._pending:
            self._pending = IN
            self._counter = 0
        else:
            self._counter += 1
            if self._counter >= self.stable_scans:
                self._output = IN
        return self._output

    @property
    def Q(self) -> bool:
        return self._output

    def as_dict(self) -> dict:
        return {
            'name': self.name,
            'stable_scans': self.stable_scans,
            'counter': self._counter,
            'output': self._output,
        }
