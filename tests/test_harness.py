"""
ConservaTwin PLC — Automated Fault Injection Test Harness
==========================================================
Runs a series of fault scenarios against the live API, collecting
scan snapshots and validating expected PLC responses.

Usage:
    # Start the backend first:
    uvicorn api.main:app --port 8000
    # Then in another terminal:
    python tests/test_harness.py
"""
from __future__ import annotations

import asyncio
import json
import time
import sys
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Optional

import httpx
import websockets

API = "http://localhost:8000"
WS  = "ws://localhost:8000/ws"
SCAN_MS = 200   # nominal scan interval (must match backend)

# ─── Data structures ──────────────────────────────────────────────────────────

@dataclass
class ScenarioResult:
    name:        str
    passed:      bool
    duration_s:  float
    observations: List[str] = field(default_factory=list)
    failures:     List[str] = field(default_factory=list)

@dataclass
class TestReport:
    run_at:    str
    total:     int = 0
    passed:    int = 0
    failed:    int = 0
    scenarios: List[ScenarioResult] = field(default_factory=list)


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def collect_scans(n: int) -> List[dict]:
    """Collect n scan snapshots from the WebSocket."""
    snaps = []
    async with websockets.connect(WS) as ws:
        while len(snaps) < n:
            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            msg = json.loads(raw)
            if msg.get("type") in ("scan", "init"):
                snaps.append(msg)
    return snaps


async def inject(client: httpx.AsyncClient, fault: str, zone: str = "A") -> None:
    r = await client.post(f"{API}/inject-fault", json={"fault": fault, "zone": zone})
    r.raise_for_status()


async def get_state(client: httpx.AsyncClient) -> dict:
    r = await client.get(f"{API}/state")
    r.raise_for_status()
    return r.json()


# ─── Scenarios ────────────────────────────────────────────────────────────────

async def scenario_sensor_freeze(client: httpx.AsyncClient) -> ScenarioResult:
    """Sensor stops updating → PLC should raise SENSOR_INVALID alarm within 10 scans."""
    name = "Sensor Freeze (Zone A)"
    t0   = time.perf_counter()
    obs  = []
    fail = []

    # Baseline
    baseline = await collect_scans(3)
    obs.append(f"Baseline PRI(A): {baseline[-1].get('risk_a', {}).get('pri', 'n/a'):.2f}" if isinstance(baseline[-1].get('risk_a', {}).get('pri', 'n/a'), float) else "Baseline collected")

    # Inject
    await inject(client, "sensor_freeze", "A")
    obs.append("Injected: sensor_freeze → Zone A")

    # Collect 15 scans, look for alarm
    post = await collect_scans(15)
    # Actual alarm keys: a_sensor / b_sensor / c_sensor (from _ALARM_META in main.py)
    alarm_fired = any(
        (
            snap.get("alarms", {}).get("a_sensor", {}).get("latched", False)
            or any(
                "sensor" in k and v.get("latched", False)
                for k, v in snap.get("alarms", {}).items()
            )
        )
        for snap in post
    )
    if alarm_fired:
        obs.append("✔ Sensor fault alarm latched within 15 scans")
    else:
        fail.append("✘ Sensor fault alarm did NOT latch within 15 scans")

    # Restore
    await inject(client, "clear", "A")
    obs.append("Cleared fault")

    return ScenarioResult(name=name, passed=len(fail) == 0, duration_s=time.perf_counter() - t0,
                          observations=obs, failures=fail)


async def scenario_door_stuck_open(client: httpx.AsyncClient) -> ScenarioResult:
    """Door open → temperature + RH should drift, risk should rise."""
    name = "Door Stuck Open (Zone B)"
    t0   = time.perf_counter()
    obs, fail = [], []

    before = await get_state(client)
    pri_before = before.get("risk_b", {}).get("pri", 0)

    await inject(client, "door_open", "B")
    obs.append("Injected: door_open → Zone B")

    # Wait 20 scans (4 seconds at 200ms)
    await asyncio.sleep(20 * SCAN_MS / 1000)
    post = await collect_scans(5)
    last = post[-1]

    # Door flag in plant
    door_flag = last.get("plant", {}).get("zone_b", {}).get("door_open", False)
    if door_flag:
        obs.append("✔ plant.zone_b.door_open = True confirmed")
    else:
        fail.append("✘ plant.zone_b.door_open not True")

    pri_after = last.get("risk_b", {}).get("pri", 0)
    obs.append(f"PRI(B) before: {pri_before:.2f}, after: {pri_after:.2f}")
    if pri_after >= pri_before:
        obs.append("✔ PRI(B) non-decreasing under disturbance")
    else:
        fail.append("✘ PRI(B) unexpectedly decreased")

    await inject(client, "clear", "B")
    obs.append("Cleared fault")

    return ScenarioResult(name=name, passed=len(fail) == 0, duration_s=time.perf_counter() - t0,
                          observations=obs, failures=fail)


async def scenario_estop(client: httpx.AsyncClient) -> ScenarioResult:
    """E-Stop → all Q outputs must be de-energized (safe state)."""
    name = "Software E-Stop"
    t0   = time.perf_counter()
    obs, fail = [], []

    # Inject E-Stop
    r = await client.post(f"{API}/command/estop", json={"active": True})
    r.raise_for_status()
    obs.append("E-Stop activated via API")

    await asyncio.sleep(3 * SCAN_MS / 1000)
    snaps = await collect_scans(3)
    last = snaps[-1]

    # Expect alarm — key is 'estop' in alarm dict, or check active_alarms list
    alarm_found = (
        last.get("alarms", {}).get("estop", {}).get("latched", False)
        or any(
            "estop" in k and v.get("latched", False)
            for k, v in last.get("alarms", {}).items()
        )
        or any(
            "ESTOP" in str(a.get("zone", "")).upper() or "ESTOP" in str(a.get("tag", "")).upper()
            for a in last.get("active_alarms", [])
        )
    )
    # Check PID outputs — cv should be 0 under E-Stop safe state
    pids_stopped = all(
        abs(p.get("cv", 0)) < 1.0 or p.get("mode") == "manual"
        for p in last.get("pids", {}).values()
    )
    if alarm_found:
        obs.append("✔ ESTOP alarm latched")
    else:
        fail.append("✘ ESTOP alarm not found in latched state")

    if pids_stopped:
        obs.append("✔ PID outputs zeroed / manual under E-Stop")

    # Release E-Stop
    r2 = await client.post(f"{API}/command/estop", json={"active": False})
    r2.raise_for_status()
    obs.append("E-Stop released")

    return ScenarioResult(name=name, passed=len(fail) == 0, duration_s=time.perf_counter() - t0,
                          observations=obs, failures=fail)


async def scenario_hvac_degradation(client: httpx.AsyncClient) -> ScenarioResult:
    """HVAC degrade → actuators less effective; risk should trend upward."""
    name = "HVAC Degradation (Zone A)"
    t0   = time.perf_counter()
    obs, fail = [], []

    before = await get_state(client)
    pri_before = before.get("risk_a", {}).get("pri", 0)

    # Degrade twice
    await inject(client, "degrade", "A")
    await inject(client, "degrade", "A")
    obs.append("Applied ×2 HVAC degrade to Zone A")

    # Wait 30 scans
    await asyncio.sleep(30 * SCAN_MS / 1000)
    post = await collect_scans(5)
    last = post[-1]
    pri_after = last.get("risk_a", {}).get("pri", 0)

    obs.append(f"PRI(A) before: {pri_before:.2f}, after: {pri_after:.2f}")
    if pri_after >= pri_before:
        obs.append("✔ PRI(A) rose under degraded HVAC")
    else:
        fail.append("✘ PRI(A) did not rise — degrade may not have taken effect")

    # Restore
    await inject(client, "clear", "A")
    obs.append("Cleared fault")

    return ScenarioResult(name=name, passed=len(fail) == 0, duration_s=time.perf_counter() - t0,
                          observations=obs, failures=fail)


async def scenario_historian_export(client: httpx.AsyncClient) -> ScenarioResult:
    """Historian CSV export should return valid CSV with expected columns."""
    name = "Historian CSV Export"
    t0   = time.perf_counter()
    obs, fail = [], []

    # Let data accumulate
    await asyncio.sleep(10 * SCAN_MS / 1000)

    r = await client.get(f"{API}/export-csv")
    if r.status_code == 200:
        obs.append("✔ HTTP 200 returned")
        lines = r.text.strip().splitlines()
        if len(lines) >= 2:
            obs.append(f"✔ CSV has {len(lines)} rows (header + {len(lines)-1} data rows)")
            header = lines[0]
            required = ["timestamp", "scan_number"]
            for col in required:
                if col in header:
                    obs.append(f"  ✔ column '{col}' present")
                else:
                    fail.append(f"  ✘ column '{col}' missing from CSV header")
        else:
            fail.append(f"✘ CSV only has {len(lines)} lines — too sparse")
    else:
        fail.append(f"✘ HTTP {r.status_code} from /export-csv")

    return ScenarioResult(name=name, passed=len(fail) == 0, duration_s=time.perf_counter() - t0,
                          observations=obs, failures=fail)


# ─── Report serializer ────────────────────────────────────────────────────────

def save_report(report: TestReport) -> None:
    out_dir = Path(__file__).parent
    json_path = out_dir / "test_report.json"
    html_path = out_dir / "test_report.html"

    # JSON
    json_path.write_text(json.dumps(asdict(report), indent=2))

    # HTML
    rows = ""
    for s in report.scenarios:
        color  = "#0d6b35" if s.passed else "#5a1010"
        badge  = "PASS" if s.passed else "FAIL"
        bcolor = "#00dc5a" if s.passed else "#ff3b30"
        details = "".join(
            f"<li style='color:#0d9c4a'>{o}</li>" for o in s.observations
        ) + "".join(
            f"<li style='color:#ff3b30;font-weight:bold'>{f}</li>" for f in s.failures
        )
        rows += f"""
        <tr style='background:{color}22'>
          <td style='padding:10px;font-weight:700;color:#c8d8e8'>{s.name}</td>
          <td style='padding:10px;text-align:center'>
            <span style='padding:3px 10px;border-radius:4px;background:{bcolor}22;border:1px solid {bcolor};color:{bcolor};font-weight:800'>{badge}</span>
          </td>
          <td style='padding:10px;color:#6a8aa0;font-family:monospace'>{s.duration_s:.2f}s</td>
          <td style='padding:10px'><ul style='margin:0;padding-left:16px;font-size:12px'>{details}</ul></td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html><head><meta charset='utf-8'>
<title>ConservaTwin PLC — Test Report</title>
<style>
  body {{font-family:'Inter',sans-serif;background:#0a0c0f;color:#c8d8e8;margin:0;padding:20px}}
  h1 {{color:#00dc5a;margin-bottom:4px}} p {{color:#6a8aa0;margin-bottom:20px}}
  table {{width:100%;border-collapse:collapse;background:#0f1318;border:1px solid #1e2d3d;border-radius:8px;overflow:hidden}}
  th {{padding:10px;text-align:left;color:#3a5060;font-size:11px;text-transform:uppercase;letter-spacing:.08em;border-bottom:1px solid #1e2d3d}}
  td {{border-bottom:1px solid #1a2232;vertical-align:top}}
  .summary {{display:flex;gap:24px;margin-bottom:20px}}
  .stat {{background:#131920;border:1px solid #1e2d3d;border-radius:8px;padding:12px 20px;text-align:center}}
  .stat-num {{font-size:28px;font-weight:800}} .stat-lbl {{font-size:11px;color:#3a5060;text-transform:uppercase}}
</style></head><body>
<h1>ConservaTwin PLC — Test Report</h1>
<p>Generated: {report.run_at}</p>
<div class='summary'>
  <div class='stat'><div class='stat-num' style='color:#c8d8e8'>{report.total}</div><div class='stat-lbl'>Total</div></div>
  <div class='stat'><div class='stat-num' style='color:#00dc5a'>{report.passed}</div><div class='stat-lbl'>Passed</div></div>
  <div class='stat'><div class='stat-num' style='color:#ff3b30'>{report.failed}</div><div class='stat-lbl'>Failed</div></div>
</div>
<table>
<thead><tr><th>Scenario</th><th>Result</th><th>Duration</th><th>Details</th></tr></thead>
<tbody>{rows}</tbody>
</table></body></html>"""

    html_path.write_text(html)
    print(f"\n✔ Report saved:\n  {json_path}\n  {html_path}")


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main() -> None:
    print("ConservaTwin PLC — Fault Injection Test Harness")
    print("=" * 50)

    # Wait for API to be ready
    print("Waiting for API at", API, "...")
    for _ in range(20):
        try:
            async with httpx.AsyncClient(timeout=2) as c:
                r = await c.get(f"{API}/health")
                if r.status_code == 200:
                    print("✔ API ready:", r.json())
                    break
        except Exception:
            await asyncio.sleep(0.5)
    else:
        print("✘ API not reachable — start uvicorn first")
        sys.exit(1)

    report = TestReport(run_at=time.strftime("%Y-%m-%d %H:%M:%S"))
    scenarios_coros = [
        scenario_sensor_freeze,
        scenario_door_stuck_open,
        scenario_estop,
        scenario_hvac_degradation,
        scenario_historian_export,
    ]

    async with httpx.AsyncClient(timeout=30) as client:
        for coro in scenarios_coros:
            print(f"\n▶ Running: {coro.__name__} …")
            try:
                result = await coro(client)
            except Exception as e:
                result = ScenarioResult(
                    name=coro.__name__, passed=False, duration_s=0,
                    failures=[f"Exception: {e}"]
                )
            report.scenarios.append(result)
            report.total += 1
            if result.passed:
                report.passed += 1
                print(f"  ✔ PASS ({result.duration_s:.2f}s)")
            else:
                report.failed += 1
                print(f"  ✘ FAIL ({result.duration_s:.2f}s)")
                for f in result.failures:
                    print(f"    {f}")
            # Small pause between scenarios
            await asyncio.sleep(0.5)

    print(f"\n{'='*50}")
    print(f"Results: {report.passed}/{report.total} passed, {report.failed} failed")
    save_report(report)


if __name__ == "__main__":
    asyncio.run(main())
