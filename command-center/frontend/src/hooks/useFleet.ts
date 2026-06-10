"use client";

import { useEffect, useRef, useState } from "react";
import { fleetWsUrl, type FleetSnapshot } from "@/lib/api";

export function useFleet(): FleetSnapshot | null {
  const [data, setData] = useState<FleetSnapshot | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let alive = true;

    function connect() {
      const ws = new WebSocket(fleetWsUrl());
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
