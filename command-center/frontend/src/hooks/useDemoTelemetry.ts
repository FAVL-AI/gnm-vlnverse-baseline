"use client";

import { useEffect, useRef, useState } from "react";

const BASE_WS = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
  .replace(/^http/, "ws");

export type DemoZone = "GREEN" | "AMBER" | "RED";

export type DemoFrame = {
  type: "frame";
  step: number;
  model: string;
  fleetsafe_on: boolean;
  // Robot state
  robot_x: number;
  robot_y: number;
  robot_yaw: number;
  // Nominal command from GNM/ViNT
  raw_vx: number;
  raw_vy: number;
  raw_wz: number;
  // Safe command from FleetSafe CBF-QP
  safe_vx: number;
  safe_vy: number;
  safe_wz: number;
  // Safety state
  intervened: boolean;
  min_dist_m: number;
  h_min: number;
  cbf_zone: DemoZone;
  intervention_count: number;
  // Navigation output
  waypoints: [number, number][];
  // Timing
  inference_ms: number;
  cbf_ms: number;
  // Episode
  collision: boolean;
  goal_reached: boolean;
  dist_to_goal: number;
  // Camera image (data URI)
  camera_b64: string;
};

export type DemoStatus = {
  type: "status";
  state: string;
  msg: string;
};

export type DemoDone = {
  type: "done";
  collision: boolean;
  steps: number;
  summary: Record<string, unknown>;
};

export type DemoMessage = DemoFrame | DemoStatus | DemoDone | { type: string; [k: string]: unknown };

export type DemoServerStatus = {
  status: "idle" | "starting" | "running" | "done" | "error";
  model: string;
  scene: string;
  fleetsafe: boolean;
  mock: boolean;
  pid: number | null;
  started_at: number | null;
  frame_count: number;
  intervention_count: number;
  error_msg: string | null;
  last_frame: DemoFrame | null;
};

export function useDemoTelemetry(): {
  frame: DemoFrame | null;
  serverStatus: DemoServerStatus | null;
  connected: boolean;
  messages: DemoMessage[];
} {
  const [frame, setFrame]               = useState<DemoFrame | null>(null);
  const [serverStatus, setServerStatus] = useState<DemoServerStatus | null>(null);
  const [connected, setConnected]       = useState(false);
  const [messages, setMessages]         = useState<DemoMessage[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let alive = true;

    function connect() {
      const ws = new WebSocket(`${BASE_WS}/api/demo/ws`);
      wsRef.current = ws;

      ws.onopen  = () => { if (alive) setConnected(true); };
      ws.onclose = () => {
        if (alive) {
          setConnected(false);
          setTimeout(connect, 2500);
        }
      };
      ws.onmessage = (e) => {
        if (!alive) return;
        try {
          const msg: DemoMessage = JSON.parse(e.data);
          if (msg.type === "frame") {
            setFrame(msg as DemoFrame);
          }
          // Server snapshot (sent on connect and on status change)
          if ("status" in msg && "frame_count" in msg) {
            setServerStatus(msg as unknown as DemoServerStatus);
          }
          if (msg.type !== "ping") {
            setMessages((prev) => [...prev.slice(-200), msg]);
          }
        } catch { /* ignore */ }
      };
    }

    connect();
    return () => {
      alive = false;
      wsRef.current?.close();
    };
  }, []);

  return { frame, serverStatus, connected, messages };
}
