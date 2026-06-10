"use client";

import { useEffect, useRef, useState } from "react";

export type Detection = { id: number; role: string; x: number; y: number };
export type Track     = { id: number; x: number; y: number; vx: number; vy: number };

export type TelemetryData = {
  zone: "GREEN" | "AMBER" | "RED";
  risk: number;
  crowding_risk: number;
  occlusion_risk: number;
  detection_count: number;
  tracked_count: number;
  intervention_active: boolean;
  cmd_vel: { vx: number; vy: number; wz: number };
  odom: { x: number; y: number; heading: number };
  battery_pct: number | null;
  battery_charging: boolean;
  latency_ms: number;
  perception_latency_ms: number;
  sim_fps: number;
  detections: Detection[];
  tracks: Track[];
  source: "ros2" | "mock";
  timestamp: number;
};

const BASE_WS = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
  .replace(/^http/, "ws");

export function useTelemetry(): TelemetryData | null {
  const [data, setData] = useState<TelemetryData | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let alive = true;

    function connect() {
      const ws = new WebSocket(`${BASE_WS}/api/ws/telemetry`);
      wsRef.current = ws;
      ws.onmessage = (e) => {
        if (!alive) return;
        try { setData(JSON.parse(e.data)); } catch { /* ignore */ }
      };
      ws.onclose = () => {
        if (alive) setTimeout(connect, 2000);
      };
    }

    connect();
    return () => {
      alive = false;
      wsRef.current?.close();
    };
  }, []);

  return data;
}
