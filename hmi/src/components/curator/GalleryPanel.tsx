"use client";
// ── GalleryPanel ───────────────────────────────────────────────────────────
// Visual only — data sourced exclusively from PLC WebSocket scan snapshot.
// This component presents one museum zone as a calm gallery panel.
// It does NOT write to any PLC memory or trigger any backend command.

import StressGauge from "./StressGauge";
import { ZoneRisk } from "@/hooks/usePLCSocket";

interface PlantZone {
    temp: number;
    rh: number;
    door_open: boolean;
    valid?: boolean;
}

interface Props {
    zone: "A" | "B" | "C";
    galleryName: string;         // e.g. "Gallery A"
    artworkTitle: string;        // e.g. "Troubles of My Head"
    medium: string;         // e.g. "Collage / Mixed media"
    emphasis: string;         // conservation note
    imagePath?: string;         // "/galleries/gallery-a.jpg" when available
    plant: PlantZone | undefined;
    risk: ZoneRisk | undefined;
    hasAlarm: boolean;
    alarmMessage?: string;
    animIndex: number;         // 0,1,2 for staggered rise-in
}

const ZONE_GRADIENTS: Record<string, string> = {
    A: "linear-gradient(160deg, #1c1610 0%, #0e0c08 50%, #16120a 100%)",
    B: "linear-gradient(160deg, #12141a 0%, #0c0e12 50%, #10121a 100%)",
    C: "linear-gradient(160deg, #111210 0%, #0c0d0c 50%, #101210 100%)",
};

const ZONE_ACCENT: Record<string, string> = {
    A: "var(--brass)",
    B: "var(--blue)",
    C: "var(--green)",
};

function MetricCell({ label, value, unit, ok }: { label: string; value: string; unit: string; ok: boolean }) {
    return (
        <div style={{ textAlign: "center" }}>
            <div style={{
                fontFamily: "var(--font-heading)",
                fontSize: 9,
                letterSpacing: "0.18em",
                textTransform: "uppercase",
                color: "var(--text-dim)",
                marginBottom: 4,
            }}>{label}</div>
            <div style={{
                fontFamily: "var(--font-mono)",
                fontSize: 28,
                fontWeight: 300,
                color: ok ? "var(--text-primary)" : "var(--amber)",
                lineHeight: 1,
                transition: "color 1s ease",
            }}>
                {value}
                <span style={{ fontSize: 12, color: "var(--text-dim)", marginLeft: 2 }}>{unit}</span>
            </div>
        </div>
    );
}

export default function GalleryPanel({
    zone, galleryName, artworkTitle, medium, emphasis,
    imagePath, plant, risk, hasAlarm, alarmMessage, animIndex,
}: Props) {
    const pri = risk?.pri ?? 0;
    const accent = ZONE_ACCENT[zone];
    const gradient = ZONE_GRADIENTS[zone];
    const temp = plant?.temp?.toFixed(1) ?? "—";
    const rh = plant?.rh?.toFixed(1) ?? "—";
    const sensorFault = plant && plant.valid === false;

    return (
        <div
            className="panel-rise"
            style={{
                position: "relative",
                background: gradient,
                border: "1px solid var(--border)",
                borderTop: `2px solid ${accent}`,
                borderRadius: 4,
                overflow: "hidden",
                display: "flex",
                flexDirection: "column",
                animationDelay: `${animIndex * 0.12}s`,
                animationFillMode: "both",
            }}
        >
            {/* ── Hero image area ─────────────────────────────────────────── */}
            <div style={{
                position: "relative",
                height: 200,
                overflow: "hidden",
                background: imagePath ? undefined : gradient,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
            }}>
                {imagePath ? (
                    <img
                        src={imagePath}
                        alt={artworkTitle}
                        style={{ width: "100%", height: "100%", objectFit: "cover", filter: "brightness(0.45)" }}
                    />
                ) : (
                    /* Placeholder — replace with real artwork photos */
                    <div style={{
                        position: "absolute", inset: 0,
                        display: "flex", alignItems: "center", justifyContent: "center",
                    }}>
                        <div style={{
                            width: 48, height: 48, borderRadius: "50%",
                            border: `1px solid ${accent}44`,
                            display: "flex", alignItems: "center", justifyContent: "center",
                        }}>
                            <div style={{ width: 16, height: 16, background: `${accent}44`, borderRadius: "50%" }} />
                        </div>
                    </div>
                )}

                {/* Gallery label overlay */}
                <div style={{
                    position: "absolute", bottom: 0, left: 0, right: 0,
                    background: "linear-gradient(transparent, rgba(10,8,5,0.95))",
                    padding: "32px 24px 16px",
                }}>
                    <div style={{
                        fontFamily: "var(--font-heading)",
                        fontSize: 10,
                        letterSpacing: "0.2em",
                        textTransform: "uppercase",
                        color: accent,
                        marginBottom: 4,
                    }}>{galleryName}</div>
                    <div style={{
                        fontFamily: "var(--font-heading)",
                        fontSize: 20,
                        fontWeight: 200,
                        letterSpacing: "0.06em",
                        color: "var(--text-primary)",
                        lineHeight: 1.2,
                    }}>{artworkTitle}</div>
                    <div style={{
                        fontFamily: "var(--font-body)",
                        fontSize: 11,
                        color: "var(--text-secondary)",
                        marginTop: 4,
                        fontStyle: "italic",
                    }}>{medium}</div>
                </div>
            </div>

            {/* ── Main content ────────────────────────────────────────────── */}
            <div style={{ padding: "20px 24px", flex: 1, display: "flex", flexDirection: "column", gap: 20 }}>

                {/* Environmental metrics */}
                <div style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1px 1fr",
                    gap: 0,
                    padding: "16px 0",
                    borderTop: "1px solid var(--border)",
                    borderBottom: "1px solid var(--border)",
                }}>
                    <MetricCell label="Temperature" value={temp} unit="°C" ok={!sensorFault} />
                    <div style={{ background: "var(--border)" }} />
                    <MetricCell label="Rel. Humidity" value={rh} unit="%" ok={!sensorFault} />
                </div>

                {/* Stress gauge */}
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
                    <StressGauge pri={pri} size={130} />
                    <div style={{
                        fontFamily: "var(--font-heading)",
                        fontSize: 9,
                        letterSpacing: "0.14em",
                        textTransform: "uppercase",
                        color: "var(--text-dim)",
                        textAlign: "center",
                    }}>
                        Artwork Stress Level
                    </div>
                    <div style={{
                        fontSize: 11,
                        color: "var(--text-dim)",
                        textAlign: "center",
                        lineHeight: 1.5,
                        fontStyle: "italic",
                        maxWidth: 220,
                    }}>
                        Represents cumulative environmental stress on materials.
                    </div>
                </div>

                {/* Conservation note */}
                <div style={{
                    padding: "10px 14px",
                    background: "var(--bg-secondary)",
                    borderRadius: 2,
                    borderLeft: `2px solid ${accent}44`,
                }}>
                    <div style={{
                        fontFamily: "var(--font-heading)",
                        fontSize: 9,
                        letterSpacing: "0.18em",
                        textTransform: "uppercase",
                        color: "var(--text-dim)",
                        marginBottom: 4,
                    }}>Conservation Focus</div>
                    <div style={{ fontSize: 11, color: "var(--text-secondary)", lineHeight: 1.5 }}>{emphasis}</div>
                </div>

                {/* Alarm / status line */}
                {hasAlarm ? (
                    <div
                        className="alarm-flash"
                        style={{
                            display: "flex", alignItems: "center", gap: 8,
                            padding: "10px 14px",
                            borderRadius: 2,
                            border: "1px solid var(--red-dim)",
                        }}
                    >
                        <span className="alarm-pulse" style={{
                            width: 8, height: 8, borderRadius: "50%",
                            background: "var(--red)", flexShrink: 0,
                        }} />
                        <span style={{ fontSize: 11, color: "var(--red)", lineHeight: 1.4 }}>
                            {alarmMessage ?? "Attention: environmental condition requires review"}
                        </span>
                    </div>
                ) : (
                    <div style={{
                        display: "flex", alignItems: "center", gap: 8,
                        padding: "10px 14px",
                        borderRadius: 2,
                        border: "1px solid var(--border)",
                    }}>
                        <span style={{
                            width: 6, height: 6, borderRadius: "50%",
                            background: "var(--green)",
                            flexShrink: 0,
                            boxShadow: "0 0 6px var(--green)",
                        }} />
                        <span style={{ fontSize: 11, color: "var(--text-dim)" }}>
                            All conditions stable
                        </span>
                    </div>
                )}

                {/* Door open notice */}
                {plant?.door_open && (
                    <div style={{ fontSize: 10, color: "var(--amber)", letterSpacing: "0.08em", textAlign: "center" }}>
                        ⬡ ACCESS DOOR OPEN
                    </div>
                )}
            </div>
        </div>
    );
}
