"use client";

import { Eye, EyeOff } from "lucide-react";
import type { YoloStatus } from "@/lib/api";

interface Props {
  status: YoloStatus | null;
  onStart: () => void;
  onStop: () => void;
  busy: boolean;
}

export function YoloMode({ status, onStart, onStop, busy }: Props) {
  const active = status?.active ?? false;
  const mode   = status?.mode ?? "mock";

  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <span className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">
          Perception Mode
        </span>
        <span className={`font-mono text-[8px] font-semibold px-1.5 py-0.5 border ${
          active
            ? "border-green-500/40 text-green-400"
            : "border-amber-500/30 text-amber-400/70"
        }`}>
          {mode.toUpperCase()}
        </span>
        {status?.dry_run && (
          <span className="font-mono text-[7px] text-amber-400/40">[dry]</span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 font-mono text-[8px] mb-3">
        <span className="text-muted-foreground/40">Model</span>
        <span className="text-foreground/50 truncate">{status?.model_path ?? "—"}</span>
        <span className="text-muted-foreground/40">Package</span>
        <span className="text-foreground/50">{status?.package ?? "—"}</span>
        {active && status?.uptime_s != null && (
          <>
            <span className="text-muted-foreground/40">Uptime</span>
            <span className="text-green-400/60">{status.uptime_s.toFixed(0)}s</span>
          </>
        )}
      </div>

      <div className="flex gap-2">
        {!active ? (
          <button
            onClick={onStart}
            disabled={busy}
            className="flex items-center gap-1 font-mono text-[8px] px-2 py-1 border border-green-500/40 text-green-400/70 hover:bg-green-500/10 transition-colors disabled:opacity-30"
          >
            <Eye size={9} /> Start YOLO
          </button>
        ) : (
          <button
            onClick={onStop}
            disabled={busy}
            className="flex items-center gap-1 font-mono text-[8px] px-2 py-1 border border-amber-500/40 text-amber-400 hover:bg-amber-500/10 transition-colors disabled:opacity-30"
          >
            <EyeOff size={9} /> Stop YOLO
          </button>
        )}
      </div>

      {active && (
        <div className="mt-2 font-mono text-[7px] text-green-400/40 leading-relaxed">
          Publishing: /fleetsafe/detections · /fleetsafe/tracks
        </div>
      )}
      {!active && (
        <div className="mt-2 font-mono text-[7px] text-muted-foreground/25 leading-relaxed">
          Mock detections active — start YOLO for real camera inference
        </div>
      )}
    </div>
  );
}
