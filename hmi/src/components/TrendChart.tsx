"use client";
import {
    LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
    ResponsiveContainer, ReferenceLine
} from "recharts";
import { ScanState } from "@/hooks/usePLCSocket";

interface Props {
    history: ScanState[];
    zone: "a" | "b" | "c";
}

const COLORS = {
    temp: "#00dc5a",
    rh: "#00aaff",
    cv_temp: "#ffb800",
    cv_rh: "#ff6b35",
};

const ZONE_TARGETS = {
    a: { temp: [18, 22], rh: [45, 55] },
    b: { temp: [19, 23], rh: [40, 50] },
    c: { temp: [16, 20], rh: [45, 50] },
};

export default function TrendChart({ history, zone }: Props) {
    const targets = ZONE_TARGETS[zone];

    const data = history.map((s, i) => {
        const p = s.plant?.[zone === "a" ? "zone_a" : zone === "b" ? "zone_b" : "vault"];
        const tempPid = s.pids?.[`${zone}_temp`];
        const rhPid = s.pids?.[`${zone}_rh`];
        return {
            i,
            temp: p?.temp ?? null,
            rh: p?.rh ?? null,
            cv_temp: tempPid?.cv ?? null,
            cv_rh: rhPid?.cv ?? null,
        };
    });

    const tooltipStyle = {
        background: "#131920", border: "1px solid #1e2d3d", borderRadius: 6,
        padding: "8px 12px", fontSize: 12, color: "#c8d8e8", fontFamily: "var(--font-mono)",
    };

    return (
        <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12, padding: "14px 16px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                <span className="label-dim">Zone {zone.toUpperCase()} — Trend (last {history.length} scans)</span>
                <div style={{ display: "flex", gap: 12 }}>
                    {([["temp", "Temp °C", COLORS.temp], ["rh", "RH %", COLORS.rh], ["cv_temp", "CV-T%", COLORS.cv_temp], ["cv_rh", "CV-RH%", COLORS.cv_rh]] as [string, string, string][]).map(([k, l, c]) => (
                        <div key={k} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                            <div style={{ width: 10, height: 2, background: c, borderRadius: 1 }} />
                            <span style={{ color: "var(--text-secondary)", fontSize: 10 }}>{l}</span>
                        </div>
                    ))}
                </div>
            </div>
            <ResponsiveContainer width="100%" height={160}>
                <LineChart data={data} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                    <CartesianGrid stroke="#1a2232" strokeDasharray="3 3" />
                    <XAxis dataKey="i" hide />
                    <YAxis yAxisId="left" domain={[10, 35]} tick={{ fill: "#3a5060", fontSize: 10 }} />
                    <YAxis yAxisId="right" domain={[20, 80]} orientation="right" tick={{ fill: "#3a5060", fontSize: 10 }} />
                    <Tooltip contentStyle={tooltipStyle} formatter={(v, n) => [(v as number)?.toFixed(2) ?? "—", n as string]} />
                    {/* Target reference lines */}
                    <ReferenceLine yAxisId="left" y={targets.temp[0]} stroke={COLORS.temp} strokeDasharray="4 4" opacity={0.35} />
                    <ReferenceLine yAxisId="left" y={targets.temp[1]} stroke={COLORS.temp} strokeDasharray="4 4" opacity={0.35} />
                    <ReferenceLine yAxisId="right" y={targets.rh[0]} stroke={COLORS.rh} strokeDasharray="4 4" opacity={0.35} />
                    <ReferenceLine yAxisId="right" y={targets.rh[1]} stroke={COLORS.rh} strokeDasharray="4 4" opacity={0.35} />
                    <Line yAxisId="left" type="monotone" dataKey="temp" stroke={COLORS.temp} dot={false} strokeWidth={2} isAnimationActive={false} />
                    <Line yAxisId="right" type="monotone" dataKey="rh" stroke={COLORS.rh} dot={false} strokeWidth={2} isAnimationActive={false} />
                    <Line yAxisId="left" type="monotone" dataKey="cv_temp" stroke={COLORS.cv_temp} dot={false} strokeWidth={1} strokeDasharray="5 3" isAnimationActive={false} />
                    <Line yAxisId="right" type="monotone" dataKey="cv_rh" stroke={COLORS.cv_rh} dot={false} strokeWidth={1} strokeDasharray="5 3" isAnimationActive={false} />
                </LineChart>
            </ResponsiveContainer>
        </div>
    );
}
