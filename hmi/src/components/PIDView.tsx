"use client";
import { PIDState } from "@/hooks/usePLCSocket";

interface Props {
    pids: Record<string, PIDState> | undefined;
}




function PIDCard({ name, pid }: { name: string; pid: PIDState }) {
    const zoneChar = name[0]; // 'a', 'b', or 'c'
    const colorMap: Record<string, string> = {
        a: "var(--green)",
        b: "var(--blue)",
        c: "#c080ff",
    };
    const color = colorMap[zoneChar] ?? "var(--green)";
    const error = pid.sp - pid.pv;
    const cvPct = Math.abs(pid.cv);

    return (
        <div style={{
            background: "var(--bg-secondary)", borderRadius: 8, padding: "10px 12px",
            border: `1px solid ${color}22`, borderTop: `2px solid ${color}`,
        }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-secondary)" }}>{name}</span>
                <span style={{
                    padding: "1px 6px", borderRadius: 3, fontSize: 9, fontWeight: 700,
                    background: pid.mode === "auto" ? "rgba(0,220,90,0.15)" : "rgba(255,184,0,0.15)",
                    border: `1px solid ${pid.mode === "auto" ? "var(--green-mid)" : "var(--amber)"}`,
                    color: pid.mode === "auto" ? "var(--green)" : "var(--amber)",
                }}>{pid.mode.toUpperCase()}</span>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginBottom: 8 }}>
                {([["SP", pid.sp, color], ["PV", pid.pv, "var(--text-primary)"], ["ERR", error, Math.abs(error) > 2 ? "var(--amber)" : "var(--text-dim)"]] as [string, number, string][]).map(([l, v, c]) => (
                    <div key={l} style={{ textAlign: "center" }}>
                        <div style={{ fontSize: 9, color: "var(--text-dim)", marginBottom: 2, letterSpacing: "0.08em" }}>{l}</div>
                        <div style={{ fontFamily: "var(--font-mono)", fontSize: 14, color: c, fontWeight: 600 }}>{v.toFixed(1)}</div>
                    </div>
                ))}
            </div>

            {/* CV bar */}
            <div style={{ marginTop: 4 }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
                    <span style={{ fontSize: 9, color: "var(--text-dim)", letterSpacing: "0.08em" }}>CV OUT</span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color }}>
                        {Math.sign(pid.cv) < 0 ? "-" : "+"}{Math.abs(pid.cv).toFixed(1)}%
                    </span>
                </div>
                <div style={{ display: "flex", height: 6, gap: 1 }}>
                    {/* Negative side */}
                    <div style={{ flex: 1, background: "var(--gauge-track)", borderRadius: "3px 0 0 3px", overflow: "hidden", display: "flex", justifyContent: "flex-end" }}>
                        {pid.cv < 0 && (
                            <div style={{ width: `${cvPct}%`, background: "var(--blue)", borderRadius: "3px 0 0 3px", boxShadow: "0 0 4px var(--blue)" }} />
                        )}
                    </div>
                    {/* Center divider */}
                    <div style={{ width: 2, background: "var(--border-bright)" }} />
                    {/* Positive side */}
                    <div style={{ flex: 1, background: "var(--gauge-track)", borderRadius: "0 3px 3px 0", overflow: "hidden" }}>
                        {pid.cv >= 0 && (
                            <div style={{ width: `${cvPct}%`, background: color, borderRadius: "0 3px 3px 0", boxShadow: `0 0 4px ${color}` }} />
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}

export default function PIDView({ pids }: Props) {
    if (!pids) return null;
    const entries = Object.entries(pids);

    return (
        <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12, padding: "14px 16px" }}>
            <div className="label-dim" style={{ marginBottom: 10 }}>PID Function Blocks ({entries.length})</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 8 }}>
                {entries.map(([name, pid]) => (
                    <PIDCard key={name} name={name} pid={pid} />
                ))}
            </div>
            {entries.length === 0 && (
                <span style={{ color: "var(--text-dim)", fontSize: 12 }}>No PID blocks active</span>
            )}
        </div>
    );
}
