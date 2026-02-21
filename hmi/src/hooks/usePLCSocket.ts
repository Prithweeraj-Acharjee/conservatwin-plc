"use client";
import { useState, useEffect, useRef, useCallback } from "react";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws";
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface ZoneRisk {
    pri: number;
    risk_level: string;
    contributors: Record<string, number>;
}

export interface PIDState {
    sp: number;
    pv: number;
    cv: number;
    error: number;
    mode: "auto" | "manual";
}

export interface TimerState {
    elapsed_ms: number;
    preset_ms: number;
    done: boolean;
    running: boolean;
}

export interface AlarmState {
    latched: boolean;
    active: boolean;
    acked: boolean;
    tag: string;
    message: string;
    zone: string;
    severity: "warning" | "alarm" | "critical";
}

export interface PlantDisplay {
    zone_a: { temp: number; rh: number; airflow: number; door_open: boolean; actuators: Record<string, boolean> };
    zone_b: { temp: number; rh: number; airflow: number; door_open: boolean; actuators: Record<string, boolean> };
    vault: { temp: number; rh: number; airflow: number; door_open: boolean; actuators: Record<string, boolean> };
}

export interface ScanState {
    scan_number: number;
    timestamp: number;
    pids: Record<string, PIDState>;
    timers: Record<string, TimerState>;
    alarms: Record<string, AlarmState>;
    risk_a: ZoneRisk;
    risk_b: ZoneRisk;
    risk_c: ZoneRisk;
    watchdog: { overruns: number; max_scan_ms: number; last_scan_ms: number; tripped: boolean };
    plant: PlantDisplay;
    active_alarms: AlarmState[];
}

export type ConnectionState = "connecting" | "connected" | "error" | "closed";

interface UsePLCSocket {
    state: ScanState | null;
    connection: ConnectionState;
    history: ScanState[];
    sendCommand: (endpoint: string, body: object) => Promise<void>;
}

const MAX_HISTORY = 300;

export function usePLCSocket(): UsePLCSocket {
    const [state, setState] = useState<ScanState | null>(null);
    const [connection, setConnection] = useState<ConnectionState>("connecting");
    const [history, setHistory] = useState<ScanState[]>([]);
    const wsRef = useRef<WebSocket | null>(null);
    const pingRef = useRef<ReturnType<typeof setInterval> | null>(null);

    const connect = useCallback(() => {
        if (wsRef.current?.readyState === WebSocket.OPEN) return;
        setConnection("connecting");
        const ws = new WebSocket(WS_URL);
        wsRef.current = ws;

        ws.onopen = () => {
            setConnection("connected");
            pingRef.current = setInterval(() => {
                if (ws.readyState === WebSocket.OPEN) ws.send("ping");
            }, 10_000);
        };

        ws.onmessage = (e) => {
            try {
                const data = JSON.parse(e.data);
                if (data.type === "pong") return;
                const snap = data as ScanState;
                setState(snap);
                setHistory((h) => {
                    const next = [...h, snap];
                    return next.length > MAX_HISTORY ? next.slice(next.length - MAX_HISTORY) : next;
                });
            } catch {
                // ignore parse errors
            }
        };

        ws.onerror = () => setConnection("error");
        ws.onclose = () => {
            setConnection("closed");
            if (pingRef.current) clearInterval(pingRef.current);
            // Auto-reconnect after 2s
            setTimeout(connect, 2000);
        };
    }, []);

    useEffect(() => {
        connect();
        return () => {
            wsRef.current?.close();
            if (pingRef.current) clearInterval(pingRef.current);
        };
    }, [connect]);

    const sendCommand = useCallback(async (endpoint: string, body: object) => {
        await fetch(`${API_URL}${endpoint}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
    }, []);

    return { state, connection, history, sendCommand };
}
