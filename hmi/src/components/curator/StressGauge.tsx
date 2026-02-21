"use client";
// ── StressGauge ────────────────────────────────────────────────────────────
// Visual only — data sourced exclusively from PLC WebSocket scan snapshot.
// This component renders the "Artwork Stress Level" arc ring gauge.
// It does NOT write to any PLC memory or influence scan logic.

interface Props {
    pri: number;       // 0–100 from ZoneRisk.pri
    size?: number;     // SVG size in px
}

function bandColor(pri: number): string {
    if (pri > 70) return "var(--red)";
    if (pri > 35) return "var(--amber)";
    return "var(--green)";
}

function stressLabel(pri: number): string {
    if (pri > 70) return "Critical Stress";
    if (pri > 35) return "Elevated Stress";
    return "Stable";
}

export default function StressGauge({ pri, size = 120 }: Props) {
    const cx = size / 2;
    const cy = size / 2 + 8;
    const r = size * 0.36;
    const arcLen = Math.PI * r;           // semicircle length
    const filled = arcLen * Math.min(1, pri / 100);
    const color = bandColor(pri);
    const strokeW = size * 0.065;

    return (
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
            <svg width={size} height={size * 0.62} viewBox={`0 0 ${size} ${size * 0.62}`}>
                {/* Track arc */}
                <path
                    d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
                    fill="none"
                    stroke="var(--gauge-track)"
                    strokeWidth={strokeW}
                    strokeLinecap="round"
                />
                {/* Fill arc */}
                <path
                    d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
                    fill="none"
                    stroke={color}
                    strokeWidth={strokeW}
                    strokeLinecap="round"
                    strokeDasharray={`${filled} ${arcLen}`}
                    style={{
                        transition: "stroke-dasharray 1s ease, stroke 0.8s ease",
                        filter: `drop-shadow(0 0 3px ${color}44)`,
                    }}
                />
                {/* Value */}
                <text
                    x={cx} y={cy - 6}
                    textAnchor="middle"
                    fill={color}
                    fontSize={size * 0.175}
                    fontFamily="var(--font-mono)"
                    fontWeight="500"
                    style={{ transition: "fill 0.8s ease" }}
                >
                    {pri.toFixed(0)}
                </text>
                <text
                    x={cx} y={cy + 10}
                    textAnchor="middle"
                    fill="var(--text-dim)"
                    fontSize={size * 0.08}
                    fontFamily="var(--font-heading)"
                    style={{ textTransform: "uppercase", letterSpacing: "0.12em" }}
                >
                    / 100
                </text>
            </svg>
            <div style={{
                fontFamily: "var(--font-heading)",
                fontSize: 10,
                letterSpacing: "0.14em",
                textTransform: "uppercase",
                color,
                opacity: 0.85,
                transition: "color 0.8s ease",
            }}>
                {stressLabel(pri)}
            </div>
        </div>
    );
}
