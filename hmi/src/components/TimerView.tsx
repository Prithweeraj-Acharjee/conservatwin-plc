"use client";
import { TimerState } from "@/hooks/usePLCSocket";

interface Props {
    timers: Record<string, TimerState> | undefined;
}

function TimerBar({ name, t }: { name: string; t: TimerState }) {
    const pct = t.preset_ms > 0 ? Math.min(100, (t.elapsed_ms / t.preset_ms) * 100) : 0;
    const remaining = Math.max(0, t.preset_ms - t.elapsed_ms);
    return (
        <div style={{ padding: "8px 10px", background: "var(--bg-secondary)", borderRadius: 6, border: "1px solid var(--border)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-secondary)" }}>{name}</span>
                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                    <span style={{
                        padding: "1px 5px", borderRadius: 2, fontSize: 9, fontWeight: 700,
                        background: t.running ? "rgba(0,220,90,0.15)" : "var(--bg-elevated)",
                        border: `1px solid ${t.running ? "var(--green-mid)" : "var(--border)"}`,
                        color: t.running ? "var(--green)" : "var(--text-dim)",
                    }}>{t.running ? "RUN" : "STOP"}</span>
                    {t.done && (
                        <span style={{
                            padding: "1px 5px", borderRadius: 2, fontSize: 9, fontWeight: 700,
                            background: "rgba(0,170,255,0.15)", border: "1px solid #00aaff44", color: "var(--blue)",
                        }}>DN</span>
                    )}
                </div>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4, color: "var(--text-secondary)", fontSize: 10 }}>
                <span style={{ fontFamily: "var(--font-mono)" }}>ACC: <span style={{ color: "var(--text-primary)" }}>{(t.elapsed_ms / 1000).toFixed(2)}s</span></span>
                <span style={{ fontFamily: "var(--font-mono)" }}>PRE: <span style={{ color: "var(--text-primary)" }}>{(t.preset_ms / 1000).toFixed(2)}s</span></span>
                <span style={{ fontFamily: "var(--font-mono)" }}>REM: <span style={{ color: "var(--text-dim)" }}>{(remaining / 1000).toFixed(2)}s</span></span>
            </div>
            <div style={{ height: 4, background: "var(--gauge-track)", borderRadius: 2, overflow: "hidden" }}>
                <div style={{
                    height: "100%", width: `${pct}%`,
                    background: t.done ? "var(--blue)" : t.running ? "var(--green)" : "var(--border-bright)",
                    borderRadius: 2, transition: "width 0.3s ease",
                    boxShadow: t.done ? "0 0 6px var(--blue)" : t.running ? "0 0 6px var(--green)" : "none",
                }} />
            </div>
        </div>
    );
}

export default function TimerView({ timers }: Props) {
    if (!timers) return null;
    const entries = Object.entries(timers);

    return (
        <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12, padding: "14px 16px" }}>
            <div className="label-dim" style={{ marginBottom: 10 }}>PLC Timers ({entries.length})</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 6 }}>
                {entries.map(([name, t]) => (
                    <TimerBar key={name} name={name} t={t} />
                ))}
            </div>
            {entries.length === 0 && (
                <span style={{ color: "var(--text-dim)", fontSize: 12 }}>No timers active</span>
            )}
        </div>
    );
}
