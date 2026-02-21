"use client";
import { useState } from "react";

const FAULT_TYPES = [
    { id: "sensor_freeze", label: "Sensor Freeze", color: "var(--amber)", desc: "Sensor stops updating; PLC detects via debounce" },
    { id: "door_open", label: "Door Stuck Open", color: "#ff6b35", desc: "Continuous disturbance injection to zone" },
    { id: "estop", label: "E-Stop Trigger", color: "var(--red)", desc: "Software E-stop, safe-state all outputs" },
    { id: "power_fault", label: "Power Fault", color: "var(--red)", desc: "Simulates power loss to HVAC rack" },
    { id: "degrade", label: "HVAC Degrade", color: "#c080ff", desc: "Reduces actuator effectiveness by 20%" },
    { id: "clear", label: "Clear All Faults", color: "var(--green)", desc: "Restore sensor + close door + clear flags" },
];

interface Props {
    onInjectFault: (fault: string, zone: string) => void;
}

export default function FaultInjector({ onInjectFault }: Props) {
    const [zone, setZone] = useState("A");
    const [lastFault, setLastFault] = useState<{ fault: string; zone: string; t: string } | null>(null);

    function inject(faultId: string) {
        onInjectFault(faultId, zone);
        setLastFault({ fault: faultId, zone, t: new Date().toLocaleTimeString() });
    }

    return (
        <div style={{
            background: "var(--bg-card)", border: "1px solid var(--border)",
            borderRadius: 12, padding: "14px 16px",
        }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                <div className="label-dim">Fault Injection — Test Harness</div>
                <div style={{ display: "flex", gap: 6 }}>
                    {(["A", "B", "C"] as const).map((z) => (
                        <button key={z} onClick={() => setZone(z)}
                            style={{
                                padding: "3px 10px", borderRadius: 4, fontSize: 11, fontWeight: 700, cursor: "pointer",
                                border: `1px solid ${zone === z ? "var(--green)" : "var(--border)"}`,
                                background: zone === z ? "rgba(0,220,90,0.12)" : "var(--bg-secondary)",
                                color: zone === z ? "var(--green)" : "var(--text-secondary)",
                            }}>Zone {z}</button>
                    ))}
                </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(190px, 1fr))", gap: 8 }}>
                {FAULT_TYPES.map((f) => (
                    <button key={f.id} onClick={() => inject(f.id)}
                        style={{
                            padding: "10px 12px", borderRadius: 8, cursor: "pointer", textAlign: "left",
                            border: `1px solid ${f.color}33`,
                            background: `${f.color}0d`,
                            transition: "all 0.15s",
                        }}
                        onMouseEnter={(e) => { e.currentTarget.style.border = `1px solid ${f.color}88`; e.currentTarget.style.background = `${f.color}1a`; }}
                        onMouseLeave={(e) => { e.currentTarget.style.border = `1px solid ${f.color}33`; e.currentTarget.style.background = `${f.color}0d`; }}
                    >
                        <div style={{ color: f.color, fontSize: 12, fontWeight: 700, marginBottom: 3 }}>{f.label}</div>
                        <div style={{ color: "var(--text-dim)", fontSize: 10, lineHeight: 1.4 }}>{f.desc}</div>
                    </button>
                ))}
            </div>

            {lastFault && (
                <div style={{ marginTop: 10, padding: "6px 10px", borderRadius: 5, background: "var(--bg-secondary)", border: "1px solid var(--border)" }}>
                    <span style={{ fontSize: 10, color: "var(--text-secondary)" }}>
                        Last injection: <span style={{ fontFamily: "var(--font-mono)", color: "var(--amber)" }}>{lastFault.fault}</span>
                        {" → Zone "}<span style={{ fontFamily: "var(--font-mono)", color: "var(--text-primary)" }}>{lastFault.zone}</span>
                        {" at "}<span style={{ color: "var(--text-dim)" }}>{lastFault.t}</span>
                    </span>
                </div>
            )}
        </div>
    );
}
