"""
ConservaTwin API — SQLite Historian + CSV Export
=================================================
Logs every PLC scan snapshot to SQLite.
Provides replay capability and CSV export.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import List, Optional, Dict, Any

import os

logger = logging.getLogger("api.historian")

# DATA_DIR env var allows Railway volume persistence:
#   Set DATA_DIR=/data in Railway, mount a volume at /data
_data_dir = Path(os.environ.get("DATA_DIR", str(Path(__file__).parent.parent)))
DB_PATH = _data_dir / "historian.db"

# Keep at most this many days of data (prune on startup)
PRUNE_KEEP_DAYS = 7


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # WAL mode: allows concurrent reads during writes
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    """Create historian table if not exists."""
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scan_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_number  INTEGER NOT NULL,
            timestamp    REAL    NOT NULL,
            scan_ms      REAL,
            i_image      BLOB,
            q_image      BLOB,
            m_image      BLOB,
            pids_json    TEXT,
            timers_json  TEXT,
            alarms_json  TEXT,
            risk_a       REAL,
            risk_b       REAL,
            risk_c       REAL,
            temp_a       REAL,
            rh_a         REAL,
            temp_b       REAL,
            rh_b         REAL,
            temp_c       REAL,
            rh_c         REAL,
            plant_json   TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scan ON scan_log(scan_number)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts   ON scan_log(timestamp)")
    conn.commit()
    conn.close()
    logger.info(f"Historian DB initialised at {DB_PATH}")


class Historian:
    """
    Writes one row per PLC scan to SQLite.
    Uses a queue for thread-safe async writes.
    """

    def __init__(self):
        init_db()
        self._conn   = _get_conn()
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._task:  Optional[asyncio.Task] = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._writer_loop())
        logger.info("Historian writer started")
        # Prune old data on startup (non-blocking)
        pruned = self.prune(keep_days=PRUNE_KEEP_DAYS)
        if pruned > 0:
            logger.info(f"Historian pruned {pruned} rows older than {PRUNE_KEEP_DAYS} days")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        self._conn.close()

    def log(self, snap, plant_display: Dict[str, Any]) -> None:
        """
        Called from scan callback (sync context).
        Puts snapshot in queue; async writer commits to DB.
        """
        try:
            self._queue.put_nowait((snap, plant_display))
        except asyncio.QueueFull:
            logger.warning("Historian queue full — dropping scan")

    async def _writer_loop(self) -> None:
        while True:
            snap, plant = await self._queue.get()
            try:
                self._write(snap, plant)
            except Exception as e:
                logger.error(f"Historian write error: {e}")

    def _write(self, snap, plant: Dict) -> None:
        mem_snap = snap.mem_snap
        pz = lambda z, k: plant.get(z, {}).get(k, 0.0)

        self._conn.execute("""
            INSERT INTO scan_log
            (scan_number, timestamp, scan_ms,
             i_image, q_image, m_image,
             pids_json, timers_json, alarms_json,
             risk_a, risk_b, risk_c,
             temp_a, rh_a, temp_b, rh_b, temp_c, rh_c,
             plant_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            snap.scan_number, snap.timestamp, snap.scan_ms,
            mem_snap['I'], mem_snap['Q'], mem_snap['M'],
            json.dumps(snap.pids),
            json.dumps(snap.timers),
            json.dumps(snap.alarms),
            snap.risk_a.get('risk', 0.0),
            snap.risk_b.get('risk', 0.0),
            snap.risk_c.get('risk', 0.0),
            pz('A', 'temp'), pz('A', 'rh'),
            pz('B', 'temp'), pz('B', 'rh'),
            pz('C', 'temp'), pz('C', 'rh'),
            json.dumps(plant),
        ))
        self._conn.commit()

    def prune(self, keep_days: int = 7) -> int:
        """Delete rows older than keep_days. Returns number of rows deleted."""
        cutoff = time.time() - keep_days * 86400
        cur = self._conn.execute(
            "DELETE FROM scan_log WHERE timestamp < ?", (cutoff,)
        )
        self._conn.commit()
        return cur.rowcount

    def export_csv(self) -> str:
        """Generate CSV string from all logged scans."""
        buf  = io.StringIO()
        rows = self._conn.execute("""
            SELECT scan_number, timestamp, scan_ms,
                   risk_a, risk_b, risk_c,
                   temp_a, rh_a, temp_b, rh_b, temp_c, rh_c
            FROM scan_log ORDER BY scan_number
        """).fetchall()

        writer = csv.writer(buf)
        writer.writerow([
            'scan_number', 'timestamp', 'scan_ms',
            'risk_A', 'risk_B', 'risk_C',
            'temp_A', 'rh_A', 'temp_B', 'rh_B', 'temp_C', 'rh_C'
        ])
        for row in rows:
            writer.writerow(list(row))
        return buf.getvalue()

    def get_recent(self, n: int = 300) -> List[Dict]:
        """Return last N scan rows as dicts (for trend charts)."""
        rows = self._conn.execute("""
            SELECT scan_number, timestamp,
                   risk_a, risk_b, risk_c,
                   temp_a, rh_a, temp_b, rh_b, temp_c, rh_c
            FROM scan_log ORDER BY scan_number DESC LIMIT ?
        """, (n,)).fetchall()
        return [dict(r) for r in reversed(rows)]

    def get_range(self, start_ts: float, end_ts: float, step: int = 1) -> List[Dict]:
        """
        Return scan rows between two Unix timestamps.
        step: return every Nth row (for downsampling over long ranges).
        """
        rows = self._conn.execute("""
            SELECT scan_number, timestamp,
                   risk_a, risk_b, risk_c,
                   temp_a, rh_a, temp_b, rh_b, temp_c, rh_c,
                   alarms_json, plant_json
            FROM scan_log
            WHERE timestamp >= ? AND timestamp <= ?
            ORDER BY scan_number
        """, (start_ts, end_ts)).fetchall()
        if step <= 1:
            return [dict(r) for r in rows]
        return [dict(r) for r in rows[::step]]

    def get_alarm_events(self, limit: int = 500) -> List[Dict]:
        """
        Scan alarms_json column and return rows where any alarm became latched.
        Returns a list of {timestamp, scan_number, zone, key, message, severity}.
        Only emits one event per alarm activation (rising edge — latched transitions
        from False→True).
        """
        rows = self._conn.execute("""
            SELECT scan_number, timestamp, alarms_json
            FROM scan_log
            ORDER BY scan_number DESC
            LIMIT ?
        """, (limit * 10,)).fetchall()   # fetch more rows to find enough events

        events: List[Dict] = []
        # Track last known latched state per alarm key
        prev_latched: Dict[str, bool] = {}

        # Process in chronological order
        for row in reversed(rows):
            ts = row["timestamp"]
            sn = row["scan_number"]
            try:
                alarms = json.loads(row["alarms_json"] or "{}")
            except Exception:
                continue
            for key, ad in alarms.items():
                latched = bool(ad.get("latched", False))
                was_latched = prev_latched.get(key, False)
                if latched and not was_latched:
                    # Rising edge — new alarm activation
                    events.append({
                        "timestamp":   ts,
                        "scan_number": sn,
                        "key":         key,
                        "zone":        ad.get("zone", "?"),
                        "message":     ad.get("message", key),
                        "severity":    ad.get("severity", "warning"),
                        "acked":       bool(ad.get("acked", False)),
                    })
                prev_latched[key] = latched

        # Return most-recent events first, capped at limit
        events.sort(key=lambda e: e["timestamp"], reverse=True)
        return events[:limit]

    def get_replay_snapshots(self, start_scan: int = 1) -> List[Dict]:
        """Return all rows for deterministic replay."""
        rows = self._conn.execute("""
            SELECT scan_number, timestamp, i_image, q_image, m_image,
                   plant_json
            FROM scan_log
            WHERE scan_number >= ?
            ORDER BY scan_number
        """, (start_scan,)).fetchall()
        return [dict(r) for r in rows]

    def get_row_count(self) -> int:
        r = self._conn.execute("SELECT COUNT(*) FROM scan_log").fetchone()
        return r[0] if r else 0

    def get_time_bounds(self) -> Dict[str, float]:
        """Return the min/max timestamps in the historian."""
        r = self._conn.execute(
            "SELECT MIN(timestamp), MAX(timestamp) FROM scan_log"
        ).fetchone()
        return {"min_ts": r[0] or 0.0, "max_ts": r[1] or 0.0}
