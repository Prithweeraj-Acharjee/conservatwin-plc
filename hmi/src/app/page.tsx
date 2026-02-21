"use client";
import { useState, useCallback, useEffect } from "react";
import { usePLCSocket } from "@/hooks/usePLCSocket";
import ZoneCard from "@/components/ZoneCard";
import TrendChart from "@/components/TrendChart";
import AlarmBanner from "@/components/AlarmBanner";
import IOTableView from "@/components/IOTableView";
import TimerView from "@/components/TimerView";
import PIDView from "@/components/PIDView";
import FaultInjector from "@/components/FaultInjector";
import GalleryPanel from "@/components/curator/GalleryPanel";
import HistorianReplay from "@/components/HistorianReplay";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Tab = "overview" | "trends" | "io" | "timers" | "pid" | "faults" | "replay";
type AppMode = "operator" | "curator";

const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "trends", label: "Trends" },
  { id: "io", label: "I/O Map" },
  { id: "timers", label: "Timers" },
  { id: "pid", label: "PID" },
  { id: "faults", label: "Faults" },
  { id: "replay", label: "⏱ Replay" },
];

const CONN_COLORS: Record<string, string> = {
  connected: "var(--green)",
  connecting: "var(--amber)",
  error: "var(--red)",
  closed: "var(--red)",
};

// ── Gallery metadata — purely presentational, never touches PLC ────────────
const GALLERY_META = [
  {
    zone: "A" as const,
    galleryName: "Gallery A",
    artworkTitle: "Impressionist Collection",
    medium: "Oil on canvas, 19th–20th century",
    emphasis:
      "Organic binders in oil paint are highly susceptible to humidity swings above 60 % RH. Temperature stability prevents micro-cracking of the ground layer.",
    imagePath: undefined,
  },
  {
    zone: "B" as const,
    galleryName: "Gallery B",
    artworkTitle: "Basquiat Exhibition",
    medium: "Mixed media — acrylic, oil stick, collage",
    emphasis:
      "Acrylic polymer emulsions off-gas at elevated temperatures. UV exposure must be kept below 50 lux. Collage elements are dimensionally unstable above 55 % RH.",
    imagePath: undefined,
  },
  {
    zone: "C" as const,
    galleryName: "Archival Vault",
    artworkTitle: "Permanent Collection Storage",
    medium: "Paper, photography, textiles, works on paper",
    emphasis:
      "Archival-grade storage requires 45 % RH ± 3 % and 15 °C ± 1 °C. Acid-free enclosures slow hydrolysis. Door openings must be minimised to prevent RH spikes.",
    imagePath: undefined,
  },
];

export default function ScadaDashboard() {
  const { state, connection, history, sendCommand } = usePLCSocket();
  const [tab, setTab] = useState<Tab>("overview");
  const [appMode, setAppMode] = useState<AppMode>("operator");
  const [estopActive, setEstopActive] = useState(false);
  const [clockTime, setClockTime] = useState("");

  useEffect(() => {
    setClockTime(new Date().toLocaleTimeString());
    const t = setInterval(() => setClockTime(new Date().toLocaleTimeString()), 1000);
    return () => clearInterval(t);
  }, []);

  // ── Zone mode control ─────────────────────────────────────────────────────
  const setZoneMode = useCallback(async (zone: string, mode: "auto" | "manual") => {
    await sendCommand("/command/mode", { zone, mode });
  }, [sendCommand]);

  // ── Alarm ACK ─────────────────────────────────────────────────────────────
  const ackAlarm = useCallback(async (zone: string) => {
    await sendCommand("/command/ack-alarm", { zone });
  }, [sendCommand]);

  // ── E-Stop ────────────────────────────────────────────────────────────────
  const toggleEstop = useCallback(async () => {
    const next = !estopActive;
    setEstopActive(next);
    await sendCommand("/command/estop", { active: next });
  }, [estopActive, sendCommand]);

  // ── Fault injection ───────────────────────────────────────────────────────
  const injectFault = useCallback(async (fault: string, zone: string) => {
    await fetch(`${API_URL}/inject-fault`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fault, zone }),
    });
  }, []);

  // ── CSV export ────────────────────────────────────────────────────────────
  const exportCSV = () => window.open(`${API_URL}/export-csv`, "_blank");

  const scanNum = state?.scan_number ?? 0;
  const wdOk = !state?.watchdog?.tripped;
  const overruns = state?.watchdog?.overruns ?? 0;
  const lastScanMs = state?.watchdog?.last_scan_ms?.toFixed(1) ?? "—";

  // PID modes per zone derived from state
  const zoneMode = (zone: "A" | "B" | "C"): "auto" | "manual" => {
    const zKey = zone === "A" ? "a" : zone === "B" ? "b" : "c";
    const pid = state?.pids?.[`${zKey}_temp`];
    return pid?.mode ?? "auto";
  };

  const activeAlarmCount = state?.active_alarms?.length ?? 0;

  // Derive per-zone alarm info for Curator mode
  const zoneAlarms: Record<string, { hasAlarm: boolean; message?: string }> = {
    A: { hasAlarm: false },
    B: { hasAlarm: false },
    C: { hasAlarm: false },
  };
  for (const alarm of state?.active_alarms ?? []) {
    const z = alarm.zone?.toUpperCase();
    if (z === "A" || z === "B" || z === "C") {
      zoneAlarms[z] = { hasAlarm: true, message: alarm.message };
    }
  }

  const isCurator = appMode === "curator";

  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: "100vh", background: "var(--bg-primary)" }}>

      {/* ── Top bar ──────────────────────────────────────────────────────── */}
      <header style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "0 20px", height: isCurator ? 56 : 48,
        background: isCurator ? "var(--bg-secondary)" : "var(--bg-secondary)",
        borderBottom: isCurator ? "1px solid var(--border-brass)" : "1px solid var(--border)",
        position: "sticky", top: 0, zIndex: 100,
        transition: "height 0.35s ease, border-color 0.35s ease",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          {/* Logo mark — varies by mode */}
          {isCurator ? (
            // Museum logotype in curator mode
            <svg width={28} height={28} viewBox="0 0 28 28" fill="none">
              <rect x="2" y="10" width="24" height="16" rx="1" stroke="var(--brass)" strokeWidth="1" opacity="0.7" />
              <path d="M4 10 L14 3 L24 10" stroke="var(--brass)" strokeWidth="1" strokeLinejoin="round" opacity="0.7" />
              <rect x="10" y="14" width="8" height="12" fill="none" stroke="var(--brass)" strokeWidth="1" opacity="0.5" />
            </svg>
          ) : (
            <svg width={24} height={24} viewBox="0 0 24 24" fill="none">
              <rect x="2" y="2" width="20" height="20" rx="4" stroke="var(--green)" strokeWidth="1.5" />
              <path d="M7 12h4l2-4 2 8 2-4h1" stroke="var(--green)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          )}
          <div>
            {isCurator ? (
              <>
                <div style={{
                  fontFamily: "var(--font-heading)", fontSize: 14, fontWeight: 200,
                  color: "var(--brass)", letterSpacing: "0.2em", textTransform: "uppercase",
                }}>ConservaTwin</div>
                <div style={{ fontSize: 9, color: "var(--text-dim)", letterSpacing: "0.18em", textTransform: "uppercase" }}>
                  Museum Conservation Monitor
                </div>
              </>
            ) : (
              <>
                <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text-green)", letterSpacing: "0.04em" }}>ConservaTwin PLC</div>
                <div style={{ fontSize: 9, color: "var(--text-dim)", letterSpacing: "0.1em" }}>MUSEUM SCADA  |  DIGITAL TWIN  |  v1.0</div>
              </>
            )}
          </div>
        </div>

        {/* Right cluster */}
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>

          {/* In curator mode: show minimal status only */}
          {isCurator ? (
            <>
              {/* Connection dot */}
              <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                <span style={{
                  width: 6, height: 6, borderRadius: "50%", display: "inline-block",
                  background: CONN_COLORS[connection],
                  boxShadow: `0 0 5px ${CONN_COLORS[connection]}`,
                }} />
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--text-dim)" }}>
                  {connection === "connected" ? "LIVE" : connection.toUpperCase()}
                </span>
              </div>

              {/* Active alarms pill */}
              {activeAlarmCount > 0 && (
                <div style={{
                  padding: "3px 10px", borderRadius: 2,
                  background: "var(--red-dim)", border: "1px solid var(--red-dim)",
                }}>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--red)" }}>
                    {activeAlarmCount} Condition{activeAlarmCount > 1 ? "s" : ""} Flagged
                  </span>
                </div>
              )}

              {/* Clock */}
              <span suppressHydrationWarning style={{
                fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-dim)",
              }}>
                {clockTime}
              </span>
            </>
          ) : (
            <>
              {/* Connection */}
              <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                <span style={{
                  width: 7, height: 7, borderRadius: "50%", display: "inline-block",
                  background: CONN_COLORS[connection],
                  boxShadow: `0 0 6px ${CONN_COLORS[connection]}`,
                  ...(connection === "connected" ? {} : { animation: "led-pulse 1s ease-in-out infinite" }),
                }} />
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: CONN_COLORS[connection] }}>
                  {connection.toUpperCase()}
                </span>
              </div>

              {/* Scan counter */}
              <div style={{ fontSize: 10, color: "var(--text-secondary)" }}>
                <span className="mono">SCAN#{scanNum.toString().padStart(6, " ")}</span>
              </div>

              {/* Watchdog */}
              <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                <span style={{ width: 7, height: 7, borderRadius: "50%", background: wdOk ? "var(--green)" : "var(--red)", boxShadow: wdOk ? "0 0 6px var(--green)" : "0 0 6px var(--red)" }} />
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: wdOk ? "var(--text-secondary)" : "var(--red)" }}>
                  WD:{lastScanMs}ms ✕{overruns}
                </span>
              </div>

              {/* Active alarms */}
              {activeAlarmCount > 0 && (
                <div style={{ padding: "2px 8px", borderRadius: 4, background: "var(--red-dim)", border: "1px solid var(--red)33" }}>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--red)", fontWeight: 700 }}>
                    ⚠ {activeAlarmCount} ALARM{activeAlarmCount > 1 ? "S" : ""}
                  </span>
                </div>
              )}

              {/* CSV export */}
              <button onClick={exportCSV} style={{
                padding: "4px 10px", borderRadius: 4, fontSize: 10, fontWeight: 600, cursor: "pointer",
                border: "1px solid var(--border-bright)", background: "var(--bg-elevated)",
                color: "var(--text-secondary)", letterSpacing: "0.06em",
              }}>
                ↓ CSV
              </button>

              {/* E-Stop */}
              <button onClick={toggleEstop} style={{
                padding: "4px 14px", borderRadius: 4, fontSize: 11, fontWeight: 800, cursor: "pointer",
                border: `2px solid ${estopActive ? "#ff3b30" : "#993322"}`,
                background: estopActive ? "var(--red)" : "var(--red-dim)",
                color: estopActive ? "#000" : "var(--red)",
                letterSpacing: "0.06em", transition: "all 0.15s",
              }}>
                {estopActive ? "● ESTOP ACTIVE" : "○ ESTOP"}
              </button>
            </>
          )}

          {/* ── Mode toggle — always visible ────────────────────────────── */}
          <button
            onClick={() => setAppMode(isCurator ? "operator" : "curator")}
            title={isCurator ? "Switch to Operator mode" : "Switch to Curator/Gallery mode"}
            style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "5px 14px", borderRadius: 2, cursor: "pointer",
              border: `1px solid ${isCurator ? "var(--border-brass)" : "var(--border-bright)"}`,
              background: isCurator ? "var(--brass-subtle)" : "var(--bg-elevated)",
              color: isCurator ? "var(--brass)" : "var(--text-secondary)",
              fontFamily: "var(--font-heading)", fontSize: 10,
              letterSpacing: "0.16em", textTransform: "uppercase",
              transition: "all 0.25s ease",
            }}
          >
            {isCurator ? (
              <>
                <span style={{ fontSize: 11 }}>⚙</span>
                Operator
              </>
            ) : (
              <>
                <span style={{ fontSize: 11 }}>◈</span>
                Gallery View
              </>
            )}
          </button>
        </div>
      </header>

      {/* ── CURATOR MODE ─────────────────────────────────────────────────── */}
      {isCurator && (
        <main className="mode-fade" style={{ flex: 1, padding: "32px 28px 40px", overflowY: "auto" }}>
          {/* Page header */}
          <div style={{
            textAlign: "center", marginBottom: 40,
            borderBottom: "1px solid var(--border)", paddingBottom: 28,
          }}>
            <div style={{
              fontFamily: "var(--font-heading)", fontSize: 9,
              letterSpacing: "0.28em", textTransform: "uppercase",
              color: "var(--brass)", marginBottom: 10, opacity: 0.8,
            }}>
              Environmental Conservation Monitor
            </div>
            <h1 style={{
              fontFamily: "var(--font-heading)", fontSize: 28, fontWeight: 100,
              letterSpacing: "0.12em", color: "var(--text-primary)",
              textTransform: "uppercase", marginBottom: 10,
            }}>
              Gallery Climate Status
            </h1>
            <p style={{
              fontSize: 12, color: "var(--text-dim)", lineHeight: 1.7,
              maxWidth: 460, margin: "0 auto", fontStyle: "italic",
            }}>
              Live environmental readings from the conservation control system.
              All data is monitored automatically — no manual intervention required.
            </p>
          </div>

          {/* Gallery panels */}
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
            gap: 24,
            maxWidth: 1200,
            margin: "0 auto",
          }}>
            {GALLERY_META.map((meta, i) => {
              const plantKey = meta.zone === "A" ? "zone_a" : meta.zone === "B" ? "zone_b" : "vault";
              const plant = state?.plant?.[plantKey];
              const risk = meta.zone === "A" ? state?.risk_a : meta.zone === "B" ? state?.risk_b : state?.risk_c;
              const alarmInfo = zoneAlarms[meta.zone];
              return (
                <GalleryPanel
                  key={meta.zone}
                  zone={meta.zone}
                  galleryName={meta.galleryName}
                  artworkTitle={meta.artworkTitle}
                  medium={meta.medium}
                  emphasis={meta.emphasis}
                  imagePath={meta.imagePath}
                  plant={plant}
                  risk={risk}
                  hasAlarm={alarmInfo.hasAlarm}
                  alarmMessage={alarmInfo.message}
                  animIndex={i}
                />
              );
            })}
          </div>

          {/* Curator footer note */}
          <div style={{
            textAlign: "center", marginTop: 48,
            fontFamily: "var(--font-heading)", fontSize: 9,
            letterSpacing: "0.18em", textTransform: "uppercase",
            color: "var(--text-dim)", opacity: 0.5,
          }}>
            ConservaTwin Conservation System — For queries contact the registrar
          </div>
        </main>
      )}

      {/* ── OPERATOR MODE ────────────────────────────────────────────────── */}
      {!isCurator && (
        <>
          {/* ── Alarm banner ─────────────────────────────────────────────── */}
          <div style={{ padding: "10px 20px 0" }}>
            <AlarmBanner alarms={state?.active_alarms ?? []} onAck={ackAlarm} />
          </div>

          {/* ── Tab bar ──────────────────────────────────────────────────── */}
          <div style={{
            display: "flex", gap: 2, padding: "10px 20px 0",
            borderBottom: "1px solid var(--border)", marginTop: 10,
          }}>
            {TABS.map((t) => (
              <button key={t.id} onClick={() => setTab(t.id)}
                style={{
                  padding: "6px 16px", borderRadius: "6px 6px 0 0", fontSize: 12, fontWeight: 600, cursor: "pointer",
                  border: `1px solid ${tab === t.id ? "var(--border-bright)" : "transparent"}`,
                  borderBottom: "none",
                  background: tab === t.id ? "var(--bg-card)" : "transparent",
                  color: tab === t.id ? "var(--green)" : "var(--text-secondary)",
                  transition: "all 0.15s", marginBottom: -1,
                }}>
                {t.label}
              </button>
            ))}
          </div>

          {/* ── Main content ─────────────────────────────────────────────── */}
          <main className="mode-fade" style={{ flex: 1, padding: "16px 20px 24px", overflowY: "auto" }}>

            {/* OVERVIEW ─────────────────────────────────────────────────── */}
            {tab === "overview" && (
              <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                {/* Zone cards */}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 16 }}>
                  {([
                    { zone: "A" as const, label: "Gallery A", exhibit: "Impressionist Collection", risk: state?.risk_a, plant: state?.plant?.zone_a },
                    { zone: "B" as const, label: "Gallery B", exhibit: "Basquiat Exhibition", risk: state?.risk_b, plant: state?.plant?.zone_b },
                    { zone: "C" as const, label: "Vault", exhibit: "Archival Storage", risk: state?.risk_c, plant: state?.plant?.vault },
                  ]).map(({ zone, label, exhibit, risk, plant }) => (
                    <ZoneCard
                      key={zone} zone={zone} label={label} exhibit={exhibit}
                      risk={risk} plant={plant}
                      mode={zoneMode(zone)}
                      onSetMode={(m) => setZoneMode(zone, m)}
                    />
                  ))}
                </div>

                {/* PRI summary bar */}
                {state && (
                  <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12, padding: "12px 16px" }}>
                    <div className="label-dim" style={{ marginBottom: 10 }}>Preservation Risk Index — All Zones</div>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
                      {([
                        { label: "Gallery A", risk: state.risk_a, color: "var(--green)" },
                        { label: "Gallery B", risk: state.risk_b, color: "var(--blue)" },
                        { label: "Vault C", risk: state.risk_c, color: "#c080ff" },
                      ]).map(({ label, risk, color }) => {
                        const pri = risk?.pri ?? 0;
                        const pct = Math.min(100, pri);
                        const barColor = pri > 70 ? "var(--red)" : pri > 40 ? "var(--amber)" : color;
                        return (
                          <div key={label}>
                            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                              <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>{label}</span>
                              <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: barColor, fontWeight: 700 }}>{pri.toFixed(1)}</span>
                            </div>
                            <div style={{ height: 8, background: "var(--gauge-track)", borderRadius: 4, overflow: "hidden" }}>
                              <div style={{ height: "100%", width: `${pct}%`, background: barColor, borderRadius: 4, transition: "width 0.4s ease", boxShadow: `0 0 6px ${barColor}` }} />
                            </div>
                            <div style={{ fontSize: 10, color: "var(--text-dim)", marginTop: 2, textTransform: "capitalize" }}>{risk?.risk_level ?? "—"}</div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Quick trend rows */}
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  <TrendChart history={history} zone="a" />
                </div>
              </div>
            )}

            {/* TRENDS ─────────────────────────────────────────────────────── */}
            {tab === "trends" && (
              <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                <TrendChart history={history} zone="a" />
                <TrendChart history={history} zone="b" />
                <TrendChart history={history} zone="c" />
              </div>
            )}

            {/* I/O MAP ────────────────────────────────────────────────────── */}
            {tab === "io" && <IOTableView state={state} />}

            {/* TIMERS ─────────────────────────────────────────────────────── */}
            {tab === "timers" && <TimerView timers={state?.timers} />}

            {/* PID ────────────────────────────────────────────────────────── */}
            {tab === "pid" && <PIDView pids={state?.pids} />}

            {/* FAULT INJECTION ────────────────────────────────────────────── */}
            {tab === "faults" && <FaultInjector onInjectFault={injectFault} />}

            {/* HISTORIAN REPLAY ───────────────────────────────────────────── */}
            {tab === "replay" && <HistorianReplay />}

          </main>

          {/* ── Status bar ───────────────────────────────────────────────── */}
          <footer style={{
            height: 26, display: "flex", alignItems: "center", gap: 16, padding: "0 20px",
            background: "var(--bg-secondary)", borderTop: "1px solid var(--border)",
            fontSize: 10, color: "var(--text-dim)", fontFamily: "var(--font-mono)",
          }}>
            <span>ConservaTwin PLC v1.0</span>
            <span style={{ color: "var(--border-bright)" }}>|</span>
            <span>Backend: {API_URL}</span>
            <span style={{ color: "var(--border-bright)" }}>|</span>
            <span>WS: {process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws"}</span>
            <span style={{ color: "var(--border-bright)" }}>|</span>
            <span style={{ color: wdOk ? "var(--green)" : "var(--red)" }}>
              {wdOk ? "● SYSTEM NOMINAL" : "⚠ WATCHDOG TRIPPED"}
            </span>
            <span suppressHydrationWarning style={{ marginLeft: "auto", color: "var(--text-dim)" }}>
              {clockTime}
            </span>
          </footer>
        </>
      )}
    </div>
  );
}
