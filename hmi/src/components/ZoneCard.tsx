"use client";
import { ZoneRisk, PlantDisplay } from "@/hooks/usePLCSocket";


interface Props {
    zone: "A" | "B" | "C";
    label: string;
    exhibit: string;
    risk: ZoneRisk | undefined;
    plant: PlantDisplay[keyof PlantDisplay] | undefined;
    mode: "auto" | "manual";
    onSetMode: (mode: "auto" | "manual") => void;
}

const ZONE_TARGETS: Record<string, { temp: [number, number]; rh: [number, number] }> = {
    A: { temp: [18, 22], rh: [45, 55] },
    B: { temp: [19, 23], rh: [40, 50] },
    C: { temp: [16, 20], rh: [45, 50] },
};

function riskColor(level: string): string {
    if (level === "critical") return "var(--red)";
    if (level === "high") return "#ff6b35";
    if (level === "medium") return "var(--amber)";
    return "var(--green)";
}

function inRange(val: number, min: number, max: number) {
    return val >= min && val <= max;
}

function GaugeTick({ value, min, max, label, unit, target }: {
    value: number; min: number; max: number; label: string; unit: string;
    target: [number, number];
}) {
    const pct = Math.max(0, Math.min(100, ((value - min) / (max - min)) * 100));
    const tLow = ((target[0] - min) / (max - min)) * 100;
    const tHigh = ((target[1] - min) / (max - min)) * 100;
    const ok = inRange(value, target[0], target[1]);
    return (
        <div style={{ marginBottom: 10 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                <span className="label-dim">{label}</span>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 15, color: ok ? "var(--green)" : "var(--amber)", fontWeight: 600 }}>
                    {value.toFixed(1)}{unit}
                </span>
            </div>
            <div style={{ position: "relative", height: 8, background: "var(--gauge-track)", borderRadius: 4, overflow: "hidden" }}>
                {/* Target zone highlight */}
                <div style={{
                    position: "absolute", top: 0, height: "100%",
                    left: `${tLow}%`, width: `${tHigh - tLow}%`,
                    background: "rgba(0, 220, 90, 0.18)", borderRadius: 2,
                }} />
                {/* Fill bar */}
                <div style={{
                    position: "absolute", top: 0, left: 0, height: "100%",
                    width: `${pct}%`,
                    background: ok ? "var(--green)" : "var(--amber)",
                    borderRadius: 4,
                    transition: "width 0.3s ease",
                    boxShadow: ok ? "0 0 6px var(--green)" : "0 0 6px var(--amber)",
                }} />
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 2, color: "var(--text-dim)", fontSize: 10 }}>
                <span>{min}{unit}</span>
                <span style={{ color: "var(--text-secondary)" }}>↔ {target[0]}–{target[1]}{unit}</span>
                <span>{max}{unit}</span>
            </div>
        </div>
    );
}

function PRIArc({ value }: { value: number }) {
    const radius = 36;
    const cx = 48, cy = 48;
    const circumference = Math.PI * radius; // half circle
    const pct = Math.min(1, value / 100);
    const dash = circumference * pct;
    const color = value > 70 ? "var(--red)" : value > 40 ? "var(--amber)" : "var(--green)";
    return (
        <svg width={96} height={56} viewBox="0 0 96 56" style={{ display: "block", margin: "0 auto" }}>
            <path d={`M 12 48 A ${radius} ${radius} 0 0 1 84 48`} fill="none" stroke="var(--gauge-track)" strokeWidth={8} strokeLinecap="round" />
            <path d={`M 12 48 A ${radius} ${radius} 0 0 1 84 48`} fill="none" stroke={color}
                strokeWidth={8} strokeLinecap="round" strokeDasharray={`${dash} ${circumference}`}
                style={{ filter: `drop-shadow(0 0 6px ${color})`, transition: "stroke-dasharray 0.4s ease, stroke 0.4s ease" }} />
            <text x={cx} y={cy - 4} textAnchor="middle" fill={color} fontSize={14} fontFamily="var(--font-mono)" fontWeight="bold">
                {value.toFixed(0)}
            </text>
            <text x={cx} y={cy + 10} textAnchor="middle" fill="var(--text-secondary)" fontSize={9} fontFamily="var(--font-hmi)" style={{ textTransform: "uppercase" }}>
                PRI
            </text>
        </svg>
    );
}

export default function ZoneCard({ zone, label, exhibit, risk, plant, mode, onSetMode }: Props) {
    const targets = ZONE_TARGETS[zone];
    const pri = risk?.pri ?? 0;
    const level = risk?.risk_level ?? "low";
    const rc = riskColor(level);

    return (
        <div style={{
            background: "var(--bg-card)",
            border: `1px solid var(--border)`,
            borderRadius: 12,
            padding: "16px 18px",
            position: "relative",
            overflow: "hidden",
        }}>
            {/* Zone accent bar */}
            <div style={{
                position: "absolute", top: 0, left: 0, right: 0, height: 3,
                background: `linear-gradient(90deg, ${rc}, transparent)`,
            }} />

            {/* Header */}
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 14 }}>
                <div>
                    <div style={{ fontSize: 11, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.1em", fontWeight: 600 }}>
                        Zone {zone}
                    </div>
                    <div style={{ fontSize: 16, fontWeight: 700, color: "var(--text-primary)", lineHeight: 1.2 }}>{label}</div>
                    <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 2 }}>{exhibit}</div>
                </div>
                <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6 }}>
                    <PRIArc value={pri} />
                    <span style={{
                        display: "inline-block", padding: "2px 8px", borderRadius: 4,
                        background: rc + "22", border: `1px solid ${rc}`, color: rc,
                        fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em",
                    }}>
                        {level}
                    </span>
                </div>
            </div>

            {/* Gauges */}
            {plant ? (
                <>
                    <GaugeTick value={plant.temp} min={10} max={35} label="Temperature" unit="°C" target={targets.temp} />
                    <GaugeTick value={plant.rh} min={20} max={80} label="Relative Humidity" unit="%" target={targets.rh} />
                </>
            ) : (
                <div style={{ color: "var(--text-dim)", fontSize: 12, marginBottom: 10 }}>No plant data</div>
            )}

            {/* Actuators */}
            {plant && (
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 10, marginBottom: 12 }}>
                    {Object.entries(plant.actuators).map(([k, v]) => (
                        <span key={k} style={{
                            padding: "2px 7px", borderRadius: 3, fontSize: 10, fontWeight: 600, fontFamily: "var(--font-mono)",
                            background: v ? "rgba(0,220,90,0.12)" : "var(--bg-secondary)",
                            border: `1px solid ${v ? "var(--green-mid)" : "var(--border)"}`,
                            color: v ? "var(--green)" : "var(--text-dim)",
                            textTransform: "uppercase",
                        }}>
                            {k}
                        </span>
                    ))}
                    {plant.door_open && (
                        <span style={{
                            padding: "2px 7px", borderRadius: 3, fontSize: 10, fontWeight: 700,
                            background: "var(--amber-dim)", border: "1px solid var(--amber)", color: "var(--amber)",
                        }}>
                            DOOR OPEN
                        </span>
                    )}
                </div>
            )}

            {/* Mode control */}
            <div style={{ display: "flex", gap: 6 }}>
                <button onClick={() => onSetMode("auto")}
                    style={{
                        flex: 1, padding: "5px 0", borderRadius: 5, fontSize: 11, fontWeight: 700, cursor: "pointer",
                        border: `1px solid ${mode === "auto" ? "var(--green)" : "var(--border)"}`,
                        background: mode === "auto" ? "rgba(0,220,90,0.12)" : "var(--bg-secondary)",
                        color: mode === "auto" ? "var(--green)" : "var(--text-secondary)",
                        transition: "all 0.15s",
                    }}>AUTO</button>
                <button onClick={() => onSetMode("manual")}
                    style={{
                        flex: 1, padding: "5px 0", borderRadius: 5, fontSize: 11, fontWeight: 700, cursor: "pointer",
                        border: `1px solid ${mode === "manual" ? "var(--amber)" : "var(--border)"}`,
                        background: mode === "manual" ? "var(--amber-dim)" : "var(--bg-secondary)",
                        color: mode === "manual" ? "var(--amber)" : "var(--text-secondary)",
                        transition: "all 0.15s",
                    }}>MANUAL</button>
            </div>
        </div>
    );
}
