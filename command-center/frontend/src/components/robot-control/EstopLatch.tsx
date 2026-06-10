"use client";

import { AlertTriangle, ShieldOff, ShieldCheck } from "lucide-react";

interface LatchStatus {
  latched: boolean;
  reason: string;
  latch_ts: number | null;
  clear_count: number;
}

interface Props {
  status: LatchStatus | null;
  onLatch: () => void;
  onClear: () => void;
  busy: boolean;
}

function fmtAge(ts: number | null): string {
  if (!ts) return "";
  const s = Math.floor(Date.now() / 1000 - ts);
  return s < 60 ? `${s}s ago` : `${Math.floor(s / 60)}m ago`;
}

export function EstopLatch({ status, onLatch, onClear, busy }: Props) {
  const latched = status?.latched ?? false;

  return (
    <div className={`border p-3 flex flex-col gap-2 ${
      latched ? "border-red-500/60 bg-red-500/5" : "border-border"
    }`}>
      <div className="flex items-center gap-2">
        {latched
          ? <ShieldOff size={11} className="text-red-400 shrink-0" />
          : <ShieldCheck size={11} className="text-green-400/60 shrink-0" />}
        <span className={`font-mono text-[9px] font-semibold tracking-wider uppercase ${
          latched ? "text-red-400" : "text-muted-foreground/50"
        }`}>
          {latched ? "E-STOP LATCHED" : "E-stop clear"}
        </span>
        {latched && status?.latch_ts && (
          <span className="ml-auto font-mono text-[7px] text-red-400/50">
            {fmtAge(status.latch_ts)}
          </span>
        )}
      </div>

      {latched && status?.reason && (
        <div className="font-mono text-[8px] text-red-400/70 truncate">
          reason: {status.reason}
        </div>
      )}

      <div className="flex gap-2 mt-1">
        <button
          onClick={onLatch}
          disabled={busy || latched}
          className="flex items-center gap-1.5 px-3 py-1.5 border border-red-500/60 text-red-400
            font-mono text-[8px] font-semibold hover:bg-red-500/10 transition-colors
            disabled:opacity-30 disabled:pointer-events-none"
        >
          <AlertTriangle size={9} /> Latch E-Stop
        </button>
        {latched && (
          <button
            onClick={onClear}
            disabled={busy}
            className="flex items-center gap-1.5 px-3 py-1.5 border border-amber-500/40 text-amber-400
              font-mono text-[8px] hover:border-amber-500 transition-colors disabled:opacity-30"
          >
            <ShieldCheck size={9} /> Clear Latch
          </button>
        )}
      </div>

      {status?.clear_count != null && status.clear_count > 0 && (
        <div className="font-mono text-[7px] text-muted-foreground/25">
          cleared {status.clear_count}× this session
        </div>
      )}
    </div>
  );
}
