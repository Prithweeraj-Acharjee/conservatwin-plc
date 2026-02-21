"""
ConservaTwin PLC — Watchdog Function Block
==========================================
Monitors PLC scan cycle health.
If the scan cycle takes longer than the configured threshold, the watchdog
trips an alarm. This mirrors the watchdog timer in hardware PLCs that
resets a hardware circuit every scan.
"""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class WatchdogBlock:
    """
    Scan-cycle health monitor.

    max_scan_ms : maximum allowable scan time in milliseconds
    trip_count  : number of consecutive overruns before alarm trips
    """
    name:          str   = "WATCHDOG"
    max_scan_ms:   float = 500.0
    trip_count:    int   = 3

    _overrun_cnt:  int  = field(default=0,     repr=False, init=False)
    _tripped:      bool = field(default=False, repr=False, init=False)
    _last_scan_ms: float = field(default=0.0,  repr=False, init=False)
    _total_scans:  int  = field(default=0,     repr=False, init=False)
    _max_seen_ms:  float = field(default=0.0,  repr=False, init=False)

    def update(self, scan_ms: float) -> bool:
        """
        Call at end of each scan cycle with actual scan duration.
        Returns True if watchdog is tripped (overrun condition).
        """
        self._total_scans += 1
        self._last_scan_ms = scan_ms
        self._max_seen_ms = max(self._max_seen_ms, scan_ms)

        if scan_ms > self.max_scan_ms:
            self._overrun_cnt += 1
            if self._overrun_cnt >= self.trip_count:
                self._tripped = True
        else:
            self._overrun_cnt = max(0, self._overrun_cnt - 1)

        return self._tripped

    def reset(self) -> None:
        """Reset watchdog (called after operator acknowledges)."""
        self._tripped    = False
        self._overrun_cnt = 0

    @property
    def tripped(self) -> bool:
        return self._tripped

    def as_dict(self) -> dict:
        return {
            'name':        self.name,
            'max_scan_ms': self.max_scan_ms,
            'last_scan_ms': round(self._last_scan_ms, 2),
            'max_seen_ms': round(self._max_seen_ms, 2),
            'overrun_cnt': self._overrun_cnt,
            'total_scans': self._total_scans,
            'tripped':     self._tripped,
        }
