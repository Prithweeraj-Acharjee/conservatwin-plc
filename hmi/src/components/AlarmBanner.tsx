"use client";
import { AlarmState } from "@/hooks/usePLCSocket";

interface Props {
    alarms: AlarmState[];
    onAck: (zone: string) => void;
}

const SEV_COLORS: Record<string, string> = {
    critical: "var(--red)",
    alarm: "var(--amber)",
    warning: "#ffb800aa",
};

export default function AlarmBanner({ alarms, onAck }: Props) {
    const active = alarms.filter((a) => a.latched);

    if (active.length === 0) {
        return (
            <div style={{
                background: "var(--bg-card)", border: "1px solid var(--green-mid)",
                borderRadius: 8, padding: "10px 16px",
                display: "flex", alignItems: "center", gap: 10,
            }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--green)", display: "inline-block", boxShadow: "0 0 8px var(--green)" }} />
                <span style={{ color: "var(--green)", fontSize: 12, fontWeight: 600, letterSpacing: "0.06em" }}>ALL CLEAR — NO ACTIVE ALARMS</span>
            </div>
        );
    }

    // Group by zone
    const byZone = active.reduce<Record<string, AlarmState[]>>((acc, a) => {
        (acc[a.zone] = acc[a.zone] || []).push(a);
        return acc;
    }, {});

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {Object.entries(byZone).map(([zone, zAlarms]) => (
                <div key={zone} style={{
                    background: "var(--bg-card)",
                    border: `1px solid ${SEV_COLORS[zAlarms[0].severity] ?? "var(--amber)"}44`,
                    borderLeft: `3px solid ${SEV_COLORS[zAlarms[0].severity] ?? "var(--amber)"}`,
                    borderRadius: 8, padding: "10px 14px",
                    display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12,
                }}>
                    <div style={{ flex: 1 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                            <span className="led-pulse" style={{
                                width: 8, height: 8, borderRadius: "50%", display: "inline-block",
                                background: SEV_COLORS[zAlarms[0].severity] ?? "var(--amber)",
                                boxShadow: `0 0 8px ${SEV_COLORS[zAlarms[0].severity] ?? "var(--amber)"}`,
                            }} />
                            <span style={{ color: SEV_COLORS[zAlarms[0].severity] ?? "var(--amber)", fontWeight: 700, fontSize: 11, letterSpacing: "0.08em" }}>
                                ZONE {zone} — {zAlarms[0].severity.toUpperCase()}
                            </span>
                        </div>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                            {zAlarms.map((a) => (
                                <span key={a.tag} style={{
                                    padding: "2px 8px", borderRadius: 3, fontSize: 11, fontFamily: "var(--font-mono)",
                                    background: `${SEV_COLORS[a.severity]}18`,
                                    border: `1px solid ${SEV_COLORS[a.severity]}44`,
                                    color: SEV_COLORS[a.severity] ?? "var(--amber)",
                                }}>
                                    {a.tag}: {a.message}
                                </span>
                            ))}
                        </div>
                    </div>
                    <button onClick={() => onAck(zone)}
                        style={{
                            padding: "5px 14px", borderRadius: 5, fontSize: 11, fontWeight: 700,
                            cursor: "pointer", border: "1px solid var(--amber)", background: "var(--amber-dim)",
                            color: "var(--amber)", flexShrink: 0, letterSpacing: "0.06em", transition: "all 0.15s",
                        }}
                        onMouseEnter={(e) => { e.currentTarget.style.background = "var(--amber)"; e.currentTarget.style.color = "#000"; }}
                        onMouseLeave={(e) => { e.currentTarget.style.background = "var(--amber-dim)"; e.currentTarget.style.color = "var(--amber)"; }}
                    >ACK</button>
                </div>
            ))}
        </div>
    );
}
