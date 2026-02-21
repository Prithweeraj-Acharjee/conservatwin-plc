"use client";
/**
 * HistorianReplay — Historian Replay Tab
 * =======================================
 * • Fetches time bounds and builds a timeline scrubber
 * • Playback at 1×/5×/10× real-time speed
 * • Shows a "frozen" zone summary at the scrubbed timestamp
 * • Shows the alarm event log (rising-edge query from historian)
 */

import { useEffect, useRef, useState, useCallback } from "react";

const API_URL =
    typeof window !== "undefined"
        ? (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
        : "http://localhost:8000";

// ── Types ─────────────────────────────────────────────────────────────────────

interface HistRow {
    scan_number: number;
    timestamp: number;
    risk_a: number;
    risk_b: number;
    risk_c: number;
    temp_a: number;
    rh_a: number;
    temp_b: number;
    rh_b: number;
    temp_c: number;
    rh_c: number;
    alarms_json?: string;
}

interface AlarmEvent {
    timestamp: number;
    scan_number: number;
    key: string;
    zone: string;
    message: string;
    severity: string;
    acked: boolean;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtTime(ts: number): string {
    if (!ts) return "—";
    return new Date(ts * 1000).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
    });
}

function fmtDate(ts: number): string {
    if (!ts) return "—";
    return new Date(ts * 1000).toLocaleDateString([], {
        month: "short",
        day: "numeric",
    });
}

function pri(risk: number): number {
    return Math.round(risk * 100 * 10) / 10;
}

function priColor(p: number): string {
    if (p > 70) return "var(--red)";
    if (p > 40) return "var(--amber)";
    return "var(--green)";
}

function severityColor(sev: string): string {
    switch (sev) {
        case "critical":
            return "var(--red)";
        case "alarm":
            return "var(--amber)";
        default:
            return "#6a9ecc";
    }
}

// ── Sub-components ────────────────────────────────────────────────────────────

function ZoneMini({
    label,
    temp,
    rh,
    risk,
    color,
}: {
    label: string;
    temp: number;
    rh: number;
    risk: number;
    color: string;
}) {
    const p = pri(risk);
    const c = priColor(p);
    return (
        <div
            style={{
                background: "var(--bg-elevated)",
                border: `1px solid ${color}33`,
                borderRadius: 8,
                padding: "12px 16px",
                display: "flex",
                flexDirection: "column",
                gap: 8,
                minWidth: 160,
                flex: 1,
            }}
        >
            <div
                style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                }}
            >
                <span
                    style={{
                        fontSize: 10,
                        color,
                        fontWeight: 700,
                        letterSpacing: "0.08em",
                        textTransform: "uppercase",
                        fontFamily: "var(--font-mono)",
                    }}
                >
                    {label}
                </span>
                <span
                    style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: 12,
                        color: c,
                        fontWeight: 700,
                    }}
                >
                    PRI {p.toFixed(1)}
                </span>
            </div>
            <div
                style={{
                    height: 5,
                    background: "var(--gauge-track)",
                    borderRadius: 3,
                    overflow: "hidden",
                }}
            >
                <div
                    style={{
                        height: "100%",
                        width: `${Math.min(100, p)}%`,
                        background: c,
                        borderRadius: 3,
                        transition: "width 0.3s ease",
                    }}
                />
            </div>
            <div style={{ display: "flex", gap: 16 }}>
                <div>
                    <div
                        style={{
                            fontSize: 9,
                            color: "var(--text-dim)",
                            textTransform: "uppercase",
                            letterSpacing: "0.06em",
                        }}
                    >
                        Temp
                    </div>
                    <div
                        style={{
                            fontFamily: "var(--font-mono)",
                            fontSize: 15,
                            color: "var(--text-primary)",
                            fontWeight: 600,
                        }}
                    >
                        {temp?.toFixed(1) ?? "—"}
                        <span style={{ fontSize: 10, color: "var(--text-dim)" }}> °C</span>
                    </div>
                </div>
                <div>
                    <div
                        style={{
                            fontSize: 9,
                            color: "var(--text-dim)",
                            textTransform: "uppercase",
                            letterSpacing: "0.06em",
                        }}
                    >
                        RH
                    </div>
                    <div
                        style={{
                            fontFamily: "var(--font-mono)",
                            fontSize: 15,
                            color: "var(--text-primary)",
                            fontWeight: 600,
                        }}
                    >
                        {rh?.toFixed(1) ?? "—"}
                        <span style={{ fontSize: 10, color: "var(--text-dim)" }}> %</span>
                    </div>
                </div>
            </div>
        </div>
    );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function HistorianReplay() {
    // Time bounds
    const [minTs, setMinTs] = useState(0);
    const [maxTs, setMaxTs] = useState(0);
    const [boundsLoaded, setBoundsLoaded] = useState(false);

    // Scrubber position (Unix timestamp)
    const [cursor, setCursor] = useState(0);

    // Playback
    const [playing, setPlaying] = useState(false);
    const [speed, setSpeed] = useState<1 | 5 | 10>(1);
    const playRef = useRef(false);
    const rafRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    // Data at cursor
    const [frame, setFrame] = useState<HistRow | null>(null);
    const [loadingFrame, setLoadingFrame] = useState(false);

    // Alarm events
    const [events, setEvents] = useState<AlarmEvent[]>([]);
    const [eventsLoaded, setEventsLoaded] = useState(false);

    // ── Fetch time bounds on mount ────────────────────────────────────────────
    useEffect(() => {
        fetch(`${API_URL}/history/bounds`)
            .then((r) => r.json())
            .then((d) => {
                if (d.min_ts && d.max_ts) {
                    setMinTs(d.min_ts);
                    setMaxTs(d.max_ts);
                    setCursor(d.min_ts);
                    setBoundsLoaded(true);
                }
            })
            .catch(console.error);
    }, []);

    // ── Fetch alarm events ────────────────────────────────────────────────────
    useEffect(() => {
        fetch(`${API_URL}/history/events?limit=300`)
            .then((r) => r.json())
            .then((d: AlarmEvent[]) => {
                // Sort oldest first for display
                setEvents([...d].sort((a, b) => a.timestamp - b.timestamp));
                setEventsLoaded(true);
            })
            .catch(console.error);
    }, []);

    // ── Fetch historian row(s) near cursor ────────────────────────────────────
    const fetchFrame = useCallback(async (ts: number) => {
        setLoadingFrame(true);
        try {
            const windowSec = 2; // ± 1s window to find a row
            const r = await fetch(
                `${API_URL}/history/range?start_ts=${ts - windowSec}&end_ts=${ts + windowSec
                }&step=1`
            );
            const rows: HistRow[] = await r.json();
            if (rows.length > 0) {
                // Pick nearest row
                const nearest = rows.reduce((prev, cur) =>
                    Math.abs(cur.timestamp - ts) < Math.abs(prev.timestamp - ts)
                        ? cur
                        : prev
                );
                setFrame(nearest);
            } else {
                setFrame(null);
            }
        } catch {
            setFrame(null);
        } finally {
            setLoadingFrame(false);
        }
    }, []);

    // Debounce scrubber fetches
    const fetchDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const scheduleFetch = useCallback(
        (ts: number) => {
            if (fetchDebounceRef.current) clearTimeout(fetchDebounceRef.current);
            fetchDebounceRef.current = setTimeout(() => fetchFrame(ts), 120);
        },
        [fetchFrame]
    );

    // Fetch on cursor change (scrubber or playback)
    useEffect(() => {
        if (boundsLoaded && cursor > 0) {
            scheduleFetch(cursor);
        }
    }, [cursor, boundsLoaded, scheduleFetch]);

    // ── Playback loop ─────────────────────────────────────────────────────────
    useEffect(() => {
        playRef.current = playing;
    }, [playing]);

    const startPlayback = useCallback(() => {
        setPlaying(true);
        const TICK_MS = 200; // UI update every 200ms
        const step = () => {
            if (!playRef.current) return;
            setCursor((prev) => {
                const next = prev + TICK_MS / 1000; // advance by TICK_MS real milliseconds × speed
                /* advance "speed" seconds of historian data per real second */
                const advance = (TICK_MS / 1000) * speed;
                const nextTs = prev + advance;
                if (nextTs >= maxTs) {
                    setPlaying(false);
                    return maxTs;
                }
                return nextTs;
            });
            rafRef.current = setTimeout(step, TICK_MS);
        };
        rafRef.current = setTimeout(step, 200);
    }, [speed, maxTs]);

    const stopPlayback = useCallback(() => {
        setPlaying(false);
        if (rafRef.current) clearTimeout(rafRef.current);
    }, []);

    useEffect(() => {
        return () => {
            if (rafRef.current) clearTimeout(rafRef.current);
        };
    }, []);

    // Fix the closure: re-key the loop when playing/speed changes
    useEffect(() => {
        if (playing) {
            if (rafRef.current) clearTimeout(rafRef.current);
            const TICK_MS = 200;
            const step = () => {
                if (!playRef.current) return;
                setCursor((prev) => {
                    const nextTs = prev + (TICK_MS / 1000) * speed;
                    if (nextTs >= maxTs) {
                        setPlaying(false);
                        return maxTs;
                    }
                    return nextTs;
                });
                rafRef.current = setTimeout(step, TICK_MS);
            };
            rafRef.current = setTimeout(step, TICK_MS);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [playing, speed]);

    const stepForward = () =>
        setCursor((p) => Math.min(maxTs, p + 10));
    const stepBack = () =>
        setCursor((p) => Math.max(minTs, p - 10));

    const span = maxTs - minTs || 1;
    const pct = maxTs > minTs ? ((cursor - minTs) / span) * 100 : 0;

    // Alarm events within a ±60s window around cursor
    const windowEvents = events.filter(
        (e) => Math.abs(e.timestamp - cursor) <= 60
    );

    // ── Render ────────────────────────────────────────────────────────────────
    if (!boundsLoaded) {
        return (
            <div
                style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    height: 200,
                    color: "var(--text-dim)",
                    fontFamily: "var(--font-mono)",
                    fontSize: 12,
                }}
            >
                Loading historian…
            </div>
        );
    }

    if (maxTs === 0) {
        return (
            <div
                style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    height: 200,
                    color: "var(--text-dim)",
                    fontFamily: "var(--font-mono)",
                    fontSize: 12,
                    flexDirection: "column",
                    gap: 8,
                }}
            >
                <span style={{ fontSize: 24 }}>📂</span>
                No historian data yet. Let the system run for a few seconds.
            </div>
        );
    }

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {/* ── Header ─────────────────────────────────────────────────────── */}
            <div
                style={{
                    background: "var(--bg-card)",
                    border: "1px solid var(--border)",
                    borderRadius: 12,
                    padding: "14px 18px",
                }}
            >
                <div
                    style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        marginBottom: 12,
                    }}
                >
                    <div>
                        <div
                            className="label-dim"
                            style={{ marginBottom: 2, fontSize: 9 }}
                        >
                            HISTORIAN REPLAY
                        </div>
                        <div
                            style={{
                                fontFamily: "var(--font-mono)",
                                fontSize: 13,
                                color: "var(--text-primary)",
                                fontWeight: 600,
                            }}
                        >
                            {fmtDate(cursor)} — {fmtTime(cursor)}
                        </div>
                        <div
                            style={{
                                fontFamily: "var(--font-mono)",
                                fontSize: 9,
                                color: "var(--text-dim)",
                                marginTop: 2,
                            }}
                        >
                            Range: {fmtDate(minTs)} {fmtTime(minTs)} → {fmtDate(maxTs)}{" "}
                            {fmtTime(maxTs)}
                        </div>
                    </div>

                    {/* Playback controls */}
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        {/* Speed selector */}
                        {(
                            [
                                [1, "1×"],
                                [5, "5×"],
                                [10, "10×"],
                            ] as [1 | 5 | 10, string][]
                        ).map(([s, label]) => (
                            <button
                                key={s}
                                onClick={() => setSpeed(s)}
                                style={{
                                    padding: "3px 10px",
                                    borderRadius: 4,
                                    fontSize: 10,
                                    fontWeight: 700,
                                    cursor: "pointer",
                                    border: `1px solid ${speed === s ? "var(--green)" : "var(--border)"
                                        }`,
                                    background:
                                        speed === s ? "var(--green)18" : "var(--bg-elevated)",
                                    color:
                                        speed === s ? "var(--green)" : "var(--text-secondary)",
                                    fontFamily: "var(--font-mono)",
                                }}
                            >
                                {label}
                            </button>
                        ))}

                        <div
                            style={{ width: 1, height: 20, background: "var(--border)" }}
                        />

                        {/* ◀ 10s */}
                        <button
                            onClick={stepBack}
                            disabled={playing}
                            style={btnStyle(false)}
                            title="Step back 10 s"
                        >
                            ◀◀
                        </button>

                        {/* Play / Pause */}
                        <button
                            onClick={playing ? stopPlayback : startPlayback}
                            style={{
                                ...btnStyle(false),
                                background: playing ? "var(--amber)22" : "var(--green)22",
                                border: `1px solid ${playing ? "var(--amber)" : "var(--green)"
                                    }`,
                                color: playing ? "var(--amber)" : "var(--green)",
                                fontWeight: 800,
                                minWidth: 64,
                            }}
                        >
                            {playing ? "⏸ PAUSE" : "▶ PLAY"}
                        </button>

                        {/* ▶ 10s */}
                        <button
                            onClick={stepForward}
                            disabled={playing}
                            style={btnStyle(false)}
                            title="Step forward 10 s"
                        >
                            ▶▶
                        </button>

                        {/* Reset */}
                        <button
                            onClick={() => {
                                stopPlayback();
                                setCursor(minTs);
                            }}
                            style={btnStyle(false)}
                            title="Reset to start"
                        >
                            ↺
                        </button>
                    </div>
                </div>

                {/* ── Timeline scrubber ─────────────────────────────────────────── */}
                <div style={{ position: "relative", marginBottom: 4 }}>
                    {/* Track */}
                    <div
                        style={{
                            position: "relative",
                            height: 20,
                            display: "flex",
                            alignItems: "center",
                        }}
                    >
                        {/* Filled portion */}
                        <div
                            style={{
                                position: "absolute",
                                left: 0,
                                width: `${pct}%`,
                                height: 6,
                                background: "linear-gradient(90deg, var(--green), var(--blue))",
                                borderRadius: 3,
                                pointerEvents: "none",
                                zIndex: 1,
                            }}
                        />
                        {/* Alarm event markers on timeline */}
                        {events.map((ev, i) => {
                            const ep =
                                maxTs > minTs
                                    ? ((ev.timestamp - minTs) / (maxTs - minTs)) * 100
                                    : 0;
                            return (
                                <div
                                    key={i}
                                    title={`${ev.zone}: ${ev.message} @ ${fmtTime(ev.timestamp)}`}
                                    style={{
                                        position: "absolute",
                                        left: `${ep}%`,
                                        width: 2,
                                        height: 12,
                                        background: severityColor(ev.severity),
                                        borderRadius: 1,
                                        zIndex: 2,
                                        opacity: 0.7,
                                        transform: "translateX(-50%)",
                                        pointerEvents: "none",
                                    }}
                                />
                            );
                        })}

                        {/* Range input on top */}
                        <input
                            type="range"
                            min={minTs}
                            max={maxTs}
                            step={0.2}
                            value={cursor}
                            onChange={(e) => {
                                stopPlayback();
                                setCursor(Number(e.target.value));
                            }}
                            style={{
                                position: "absolute",
                                left: 0,
                                right: 0,
                                width: "100%",
                                opacity: 0,
                                cursor: "pointer",
                                zIndex: 3,
                                height: 20,
                            }}
                        />
                        {/* Visible track */}
                        <div
                            style={{
                                width: "100%",
                                height: 6,
                                background: "var(--gauge-track)",
                                borderRadius: 3,
                            }}
                        />
                    </div>

                    {/* Thumb indicator */}
                    <div
                        style={{
                            position: "absolute",
                            left: `${pct}%`,
                            top: 0,
                            transform: "translateX(-50%)",
                            width: 14,
                            height: 20,
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            pointerEvents: "none",
                            zIndex: 4,
                        }}
                    >
                        <div
                            style={{
                                width: 3,
                                height: 16,
                                background: "var(--text-primary)",
                                borderRadius: 2,
                                boxShadow: "0 0 6px rgba(255,255,255,0.4)",
                            }}
                        />
                    </div>
                </div>

                {/* Timeline edges */}
                <div
                    style={{
                        display: "flex",
                        justifyContent: "space-between",
                        fontFamily: "var(--font-mono)",
                        fontSize: 9,
                        color: "var(--text-dim)",
                        marginTop: 6,
                    }}
                >
                    <span>{fmtTime(minTs)}</span>
                    <span style={{ color: "var(--text-secondary)", fontSize: 9 }}>
                        {loadingFrame ? "⟳ fetching…" : frame ? `SCAN #${frame.scan_number}` : "no data"}
                    </span>
                    <span>{fmtTime(maxTs)}</span>
                </div>
            </div>

            {/* ── Zone snapshot at cursor ────────────────────────────────────── */}
            <div
                style={{
                    background: "var(--bg-card)",
                    border: "1px solid var(--border)",
                    borderRadius: 12,
                    padding: "14px 18px",
                }}
            >
                <div className="label-dim" style={{ marginBottom: 12 }}>
                    Zone State at Selected Time
                </div>
                {frame ? (
                    <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                        <ZoneMini
                            label="Gallery A"
                            temp={frame.temp_a}
                            rh={frame.rh_a}
                            risk={frame.risk_a}
                            color="var(--green)"
                        />
                        <ZoneMini
                            label="Gallery B"
                            temp={frame.temp_b}
                            rh={frame.rh_b}
                            risk={frame.risk_b}
                            color="var(--blue)"
                        />
                        <ZoneMini
                            label="Vault C"
                            temp={frame.temp_c}
                            rh={frame.rh_c}
                            risk={frame.risk_c}
                            color="#c080ff"
                        />
                    </div>
                ) : (
                    <div
                        style={{
                            color: "var(--text-dim)",
                            fontFamily: "var(--font-mono)",
                            fontSize: 11,
                        }}
                    >
                        {loadingFrame ? "Loading frame…" : "No data at this timestamp. Try scrubbing closer to an active period."}
                    </div>
                )}
            </div>

            {/* ── Alarm event log ────────────────────────────────────────────── */}
            <div
                style={{
                    background: "var(--bg-card)",
                    border: "1px solid var(--border)",
                    borderRadius: 12,
                    padding: "14px 18px",
                    overflow: "hidden",
                }}
            >
                <div
                    style={{
                        display: "flex",
                        justifyContent: "space-between",
                        marginBottom: 12,
                    }}
                >
                    <div className="label-dim">Alarm Event Log</div>
                    <div
                        style={{
                            fontFamily: "var(--font-mono)",
                            fontSize: 9,
                            color: "var(--text-dim)",
                        }}
                    >
                        {eventsLoaded
                            ? `${events.length} events total · ${windowEvents.length} near cursor (±60 s)`
                            : "Loading…"}
                    </div>
                </div>

                {/* Table */}
                <div style={{ overflowX: "auto" }}>
                    <table
                        style={{
                            width: "100%",
                            borderCollapse: "collapse",
                            fontFamily: "var(--font-mono)",
                            fontSize: 11,
                        }}
                    >
                        <thead>
                            <tr>
                                {["Time", "Zone", "Key", "Message", "Severity", "Acked"].map(
                                    (h) => (
                                        <th
                                            key={h}
                                            style={{
                                                textAlign: "left",
                                                padding: "4px 10px",
                                                fontSize: 9,
                                                color: "var(--text-dim)",
                                                textTransform: "uppercase",
                                                letterSpacing: "0.06em",
                                                borderBottom: "1px solid var(--border)",
                                                fontWeight: 600,
                                            }}
                                        >
                                            {h}
                                        </th>
                                    )
                                )}
                            </tr>
                        </thead>
                        <tbody>
                            {events.length === 0 ? (
                                <tr>
                                    <td
                                        colSpan={6}
                                        style={{
                                            padding: "16px 10px",
                                            color: "var(--text-dim)",
                                            textAlign: "center",
                                            fontSize: 11,
                                        }}
                                    >
                                        {eventsLoaded
                                            ? "No alarm events recorded yet."
                                            : "Loading events…"}
                                    </td>
                                </tr>
                            ) : (
                                events.map((ev, i) => {
                                    const isNear = Math.abs(ev.timestamp - cursor) <= 60;
                                    return (
                                        <tr
                                            key={i}
                                            style={{
                                                background: isNear
                                                    ? `${severityColor(ev.severity)}12`
                                                    : "transparent",
                                                borderLeft: isNear
                                                    ? `2px solid ${severityColor(ev.severity)}`
                                                    : "2px solid transparent",
                                            }}
                                        >
                                            <td style={tdStyle}>
                                                <div style={{ color: "var(--text-primary)" }}>
                                                    {fmtTime(ev.timestamp)}
                                                </div>
                                                <div
                                                    style={{ fontSize: 9, color: "var(--text-dim)" }}
                                                >
                                                    {fmtDate(ev.timestamp)}
                                                </div>
                                            </td>
                                            <td style={tdStyle}>
                                                <span
                                                    style={{
                                                        padding: "1px 6px",
                                                        borderRadius: 3,
                                                        background: "var(--bg-elevated)",
                                                        border: "1px solid var(--border)",
                                                        fontSize: 10,
                                                        fontWeight: 700,
                                                        color: "var(--text-secondary)",
                                                    }}
                                                >
                                                    {ev.zone}
                                                </span>
                                            </td>
                                            <td
                                                style={{
                                                    ...tdStyle,
                                                    color: "var(--text-dim)",
                                                    fontSize: 10,
                                                }}
                                            >
                                                {ev.key}
                                            </td>
                                            <td
                                                style={{
                                                    ...tdStyle,
                                                    color: "var(--text-primary)",
                                                }}
                                            >
                                                {ev.message}
                                            </td>
                                            <td style={tdStyle}>
                                                <span
                                                    style={{
                                                        color: severityColor(ev.severity),
                                                        fontWeight: 700,
                                                        textTransform: "uppercase",
                                                        fontSize: 10,
                                                    }}
                                                >
                                                    {ev.severity}
                                                </span>
                                            </td>
                                            <td style={tdStyle}>
                                                <span
                                                    style={{
                                                        color: ev.acked
                                                            ? "var(--green)"
                                                            : "var(--text-dim)",
                                                        fontSize: 10,
                                                    }}
                                                >
                                                    {ev.acked ? "✔ ACK" : "—"}
                                                </span>
                                            </td>
                                        </tr>
                                    );
                                })
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}

// ── Shared styles ──────────────────────────────────────────────────────────────

const tdStyle: React.CSSProperties = {
    padding: "6px 10px",
    borderBottom: "1px solid var(--border)",
    verticalAlign: "middle",
};

function btnStyle(_active: boolean): React.CSSProperties {
    return {
        padding: "4px 10px",
        borderRadius: 4,
        fontSize: 10,
        fontWeight: 700,
        cursor: "pointer",
        border: "1px solid var(--border-bright)",
        background: "var(--bg-elevated)",
        color: "var(--text-secondary)",
        fontFamily: "var(--font-mono)",
        letterSpacing: "0.04em",
    };
}
