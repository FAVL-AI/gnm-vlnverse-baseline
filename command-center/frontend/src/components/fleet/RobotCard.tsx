"use client";

import type { RobotSnapshot } from "@/lib/api";

const ZONE_DOT: Record<string, string> = {
  GREEN: "bg-green-500",
  AMBER: "bg-amber-400",
  RED:   "bg-red-500",
};
const ZONE_TEXT: Record<string, string> = {
  GREEN: "text-green-400",
  AMBER: "text-amber-400",
  RED:   "text-red-400",
};

function Battery({ pct, charging }: { pct: number | null; charging: boolean }) {
  if (pct === null) return <span className="text-muted-foreground/30">—</span>;
  const col = pct > 60 ? "text-green-400" : pct > 25 ? "text-amber-400" : "text-red-400";
  return (
    <span className={col}>
      {charging && <span className="text-amber-300 mr-0.5">⚡</span>}
      {pct.toFixed(0)}%
    </span>
  );
}

interface Props {
  robot: RobotSnapshot;
  estopped: boolean;
  selected?: boolean;
  onClick?: () => void;
  onEstop?: () => void;
  onClearEstop?: () => void;
}

export function RobotCard({ robot: r, estopped, selected, onClick, onEstop, onClearEstop }: Props) {
  const zone = r.zone ?? "GREEN";
  const offline = r.status === "offline";

  return (
    <div
      onClick={onClick}
      className={`border p-3 flex flex-col gap-2 cursor-pointer transition-colors font-mono
        ${selected ? "border-foreground/60 bg-foreground/5" : "border-border hover:border-foreground/30"}
        ${offline ? "opacity-50" : ""}
        ${estopped ? "border-red-500/60" : ""}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className={`w-2 h-2 rounded-full shrink-0 ${estopped ? "bg-red-500 animate-pulse" : ZONE_DOT[zone]}`} />
          <span className="text-[10px] font-semibold truncate text-foreground">{r.name}</span>
        </div>
        <span className={`text-[8px] px-1 border shrink-0
          ${estopped ? "border-red-500/60 text-red-400" :
            r.source === "ros2" ? "border-green-500/40 text-green-500" :
            "border-border text-muted-foreground/30"}`}>
          {estopped ? "E-STOP" : r.source}
        </span>
      </div>

      {/* Zone + risk */}
      <div className="flex items-center gap-3 text-[9px]">
        <span className={`${ZONE_TEXT[zone]} font-semibold`}>{zone}</span>
        <span className="text-muted-foreground">risk <span className="text-foreground">{(r.risk * 100).toFixed(0)}%</span></span>
        {r.intervention_active && (
          <span className="text-red-400 animate-pulse font-semibold">CBF</span>
        )}
      </div>

      {/* Odom + vel */}
      <div className="grid grid-cols-2 gap-x-3 text-[8px] text-muted-foreground">
        <span>x <span className="text-foreground">{(r.odom?.x ?? 0).toFixed(2)}</span></span>
        <span>vx <span className="text-foreground">{(r.cmd_vel?.vx ?? 0).toFixed(2)}</span></span>
        <span>y <span className="text-foreground">{(r.odom?.y ?? 0).toFixed(2)}</span></span>
        <span>det <span className="text-foreground">{r.detection_count}</span></span>
      </div>

      {/* Battery + latency */}
      <div className="flex items-center gap-3 text-[8px] text-muted-foreground">
        <span>bat <Battery pct={r.battery_pct} charging={r.battery_charging} /></span>
        <span className="ml-auto">{r.latency_ms.toFixed(0)} ms</span>
      </div>

      {/* E-stop controls */}
      <div className="flex gap-1 pt-1 border-t border-border">
        {estopped ? (
          <button
            onClick={e => { e.stopPropagation(); onClearEstop?.(); }}
            className="flex-1 text-[8px] px-2 py-1 border border-green-500/40 text-green-400 hover:border-green-500 hover:text-green-300 transition-colors"
          >
            clear E-STOP
          </button>
        ) : (
          <button
            onClick={e => { e.stopPropagation(); onEstop?.(); }}
            className="flex-1 text-[8px] px-2 py-1 border border-red-500/30 text-red-400/60 hover:border-red-500 hover:text-red-400 transition-colors"
          >
            E-STOP
          </button>
        )}
      </div>
    </div>
  );
}
