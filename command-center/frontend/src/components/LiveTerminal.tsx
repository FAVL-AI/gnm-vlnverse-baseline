"use client";

import { useEffect, useRef, useState } from "react";
import { logsWsUrl } from "@/lib/api";

interface LiveTerminalProps {
  jobId: string | null;
  initialLines?: string[];
}

export function LiveTerminal({ jobId, initialLines = [] }: LiveTerminalProps) {
  const [lines, setLines] = useState<string[]>(initialLines);
  const bottomRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    setLines(initialLines);
  }, [jobId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!jobId) return;
    if (wsRef.current) {
      wsRef.current.close();
    }
    const ws = new WebSocket(logsWsUrl(jobId));
    wsRef.current = ws;

    ws.onmessage = (e) => {
      const text: string = e.data;
      setLines(prev => [...prev, text]);
    };
    ws.onerror = () => setLines(prev => [...prev, "[ws] connection error\n"]);
    ws.onclose = () => setLines(prev => [...prev, "[ws] disconnected\n"]);

    return () => ws.close();
  }, [jobId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines]);

  if (!jobId) {
    return (
      <div className="border border-border bg-black/80 font-mono text-xs text-muted-foreground/30 p-4 h-64 flex items-center justify-center tracking-wide">
        [ No active job — launch a script to see logs ]
      </div>
    );
  }

  return (
    <div className="border border-border bg-black/90 font-mono text-xs overflow-auto h-80 p-3 text-green-400/80 leading-relaxed">
      {lines.map((l, i) => (
        <span key={i} style={{ whiteSpace: "pre-wrap", wordBreak: "break-all" }}>{l}</span>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
