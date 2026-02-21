"use client";
import { ScanState } from "@/hooks/usePLCSocket";

interface Props { state: ScanState | null }

/** Build a byte from 8 boolean bits (bit 0 = MSB) */
function boolsToByte(bits: (boolean | undefined)[]): number {
    return bits.slice(0, 8).reduce<number>((acc, b, i) => acc | ((b ? 1 : 0) << (7 - i)), 0);
}

function BitRow({ byte, label, value }: { byte: string; label: string; value: number }) {
    const labels = label.split("|");
    return (
        <tr>
            <td style={{ padding: "2px 8px", color: "var(--text-secondary)", fontFamily: "var(--font-mono)", fontSize: 11, whiteSpace: "nowrap" }}>{byte}</td>
            {Array.from({ length: 8 }, (_, i) => {
                const bit = (value >> (7 - i)) & 1;
                return (
                    <td key={i} style={{ padding: "2px 4px", textAlign: "center" }}>
                        <div title={labels[i] ?? `bit.${7 - i}`} style={{
                            width: 22, height: 22, borderRadius: 3, display: "flex", alignItems: "center", justifyContent: "center",
                            background: bit ? "rgba(0,220,90,0.15)" : "var(--bg-secondary)",
                            border: `1px solid ${bit ? "var(--green-mid)" : "var(--border)"}`,
                            color: bit ? "var(--green)" : "var(--text-dim)",
                            fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700,
                            boxShadow: bit ? "0 0 6px var(--green-mid)" : "none",
                            cursor: "default",
                        }}>{bit}</div>
                    </td>
                );
            })}
            <td style={{ padding: "2px 6px", color: "var(--text-dim)", fontSize: 10, whiteSpace: "nowrap" }}>
                0x{value.toString(16).padStart(2, "0").toUpperCase()}
            </td>
        </tr>
    );
}

export default function IOTableView({ state }: Props) {
    if (!state) return null;

    const pa = state.plant?.zone_a;
    const pb = state.plant?.zone_b;
    const pc = state.plant?.vault;

    // ── Derive live I / Q byte images from plant data ──────────────────────────
    // I0: ZA_TempValid | ZA_RHValid | ZB_TempValid | ZB_RHValid | ZC_TempValid | ZC_RHValid | ZA_DoorOpen | ZB_DoorOpen
    const i0 = boolsToByte([
        true,            // ZA TempValid (assume valid unless sensor freeze)
        true,            // ZA RHValid
        true,            // ZB TempValid
        true,            // ZB RHValid
        true,            // ZC TempValid
        true,            // ZC RHValid
        pa?.door_open,   // ZA DoorOpen
        pb?.door_open,   // ZB DoorOpen
    ]);
    // I1: ZC_DoorOpen | ...
    const i1 = boolsToByte([
        pc?.door_open,   // ZC DoorOpen
        false,           // EStop_HW
        false,           // FireAlarm
        false, false, false, false, false,
    ]);

    // Q0: ZA_Heat | ZA_Cool | ZA_Humid | ZA_Dehumid | ZB_Heat | ZB_Cool | ZB_Humid | ZB_Dehumid
    const q0 = boolsToByte([
        pa?.actuators?.heat,
        pa?.actuators?.cool,
        pa?.actuators?.humidify,
        pa?.actuators?.dehumidify,
        pb?.actuators?.heat,
        pb?.actuators?.cool,
        pb?.actuators?.humidify,
        pb?.actuators?.dehumidify,
    ]);
    // Q1: ZC_Heat | ZC_Cool | ZC_Humid | ZC_Dehumid | ZA_Fan | ZB_Fan | ZC_Fan
    const q1 = boolsToByte([
        pc?.actuators?.heat,
        pc?.actuators?.cool,
        pc?.actuators?.humidify,
        pc?.actuators?.dehumidify,
        pa?.actuators?.fan,
        pb?.actuators?.fan,
        pc?.actuators?.fan,
        false,
    ]);

    const sections = [
        {
            heading: "INPUT IMAGE  (I)", color: "var(--blue)", bytes: [
                { byte: "I0", label: "ZA_TempValid|ZA_RHValid|ZB_TempValid|ZB_RHValid|ZC_TempValid|ZC_RHValid|ZA_DoorOpen|ZB_DoorOpen", value: i0 },
                { byte: "I1", label: "ZC_DoorOpen|EStop_HW|FireAlarm|—|—|—|—|—", value: i1 },
            ]
        },
        {
            heading: "OUTPUT IMAGE (Q)", color: "var(--green)", bytes: [
                { byte: "Q0", label: "ZA_Heat|ZA_Cool|ZA_Humid|ZA_Dehumid|ZB_Heat|ZB_Cool|ZB_Humid|ZB_Dehumid", value: q0 },
                { byte: "Q1", label: "ZC_Heat|ZC_Cool|ZC_Humid|ZC_Dehumid|ZA_Fan|ZB_Fan|ZC_Fan|—", value: q1 },
            ]
        },
    ];

    return (
        <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12, padding: "14px 16px", overflowX: "auto" }}>
            <div className="label-dim" style={{ marginBottom: 10 }}>I/Q Memory Image — Live Bit View</div>
            {sections.map((sec) => (
                <div key={sec.heading} style={{ marginBottom: 14 }}>
                    <div style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: sec.color, marginBottom: 6, letterSpacing: "0.08em" }}>
                        {sec.heading}
                    </div>
                    <table style={{ borderCollapse: "separate", borderSpacing: "0 2px", width: "100%" }}>
                        <thead>
                            <tr>
                                <th style={{ padding: "0 8px", textAlign: "left", color: "var(--text-dim)", fontSize: 10, fontWeight: 400 }}>Byte</th>
                                {Array.from({ length: 8 }, (_, i) => (
                                    <th key={i} style={{ textAlign: "center", color: "var(--text-dim)", fontSize: 10, fontWeight: 400, width: 30 }}>.{7 - i}</th>
                                ))}
                                <th style={{ padding: "0 6px", color: "var(--text-dim)", fontSize: 10, fontWeight: 400 }}>Hex</th>
                            </tr>
                        </thead>
                        <tbody>
                            {sec.bytes.map((b) => (
                                <BitRow key={b.byte} byte={b.byte} label={b.label} value={b.value} />
                            ))}
                        </tbody>
                    </table>
                </div>
            ))}

            {/* Live actuator summary */}
            {state.plant && (
                <div style={{ marginTop: 8, borderTop: "1px solid var(--border)", paddingTop: 10 }}>
                    <div className="label-dim" style={{ marginBottom: 8 }}>Actuator Summary (from Plant)</div>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                        {(["zone_a", "zone_b", "vault"] as const).map((z) => {
                            const p = state.plant[z];
                            const label = z === "zone_a" ? "ZA" : z === "zone_b" ? "ZB" : "ZC";
                            return Object.entries(p.actuators).map(([k, v]) => (
                                <span key={`${z}-${k}`} style={{
                                    padding: "2px 7px", borderRadius: 3, fontSize: 10, fontWeight: 600, fontFamily: "var(--font-mono)",
                                    background: v ? "rgba(0,220,90,0.12)" : "var(--bg-secondary)",
                                    border: `1px solid ${v ? "var(--green-mid)" : "var(--border)"}`,
                                    color: v ? "var(--green)" : "var(--text-dim)",
                                }}>
                                    {label}.{k.toUpperCase()}
                                </span>
                            ));
                        })}
                    </div>
                </div>
            )}
        </div>
    );
}
