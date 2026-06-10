"use client";

import { useEffect, useRef, useState } from "react";
import { safetyWsUrl, type FleetSafetyEvent } from "@/lib/api";

export function useSafetyEvents(): FleetSafetyEvent[] {
  const [events, setEvents] = useState<FleetSafetyEvent[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let alive = true;

    function connect() {
      const ws = new WebSocket(safetyWsUrl());
      wsRef.current = ws;
      ws.onmessage = (e) => {
        if (!alive) return;
        try {
          const msg = JSON.parse(e.data);
          if (msg.type === "history") {
            setEvents(msg.events ?? []);
          } else if (msg.type === "event") {
            setEvents(prev => [msg.event, ...prev].slice(0, 300));
          }
        } catch { /* ignore */ }
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

  return events;
}
