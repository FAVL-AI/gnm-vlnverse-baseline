"use client";

import { Activity, AlertTriangle } from "lucide-react";

interface WdStatus {
  running: boolean;
  last_check: number | null;
  last_ok: number | null;
  consecutive_failures: number;
  total_triggers: number;
  log: { ts: number; event: string; detail: string }[];
}

interface Props {
  status: WdStatus | null;
  onStart: () => void;
  onStop: () => void;
  busy: boolean;
}

function age(ts: number | null): string {
  if (!ts) return "never";
  const s = Math.floor(Date.now() / 1000 - ts);
  return s < 5 ? "just now" : s < 60 ? `${s}s` : `${Math.floor(s / 60)}m`;
}

export function WatchdogStatus({ status, onStart, onStop, busy }: Props) {
  const running = status?.running ?? false;
  const healthy = running && (status?.consecutive_failures ?? 0) === 0;
  const triggered = (status?.total_triggers ?? 0) > 0;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <Activity size={10} className={healthy ? "text-green-400/60" : running ? "text-amber-400" : "text-muted-foreground/30"} />
        <span className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">
          Watchdog
        </span>
        <span className={`ml-auto font-mono text-[8px] font-semibold ${
          healthy ? "text-green-400/70" : running ? "text-amber-400" : "text-muted-foreground/30"
        }`}>
          {running ? (healthy ? "OK" : "⚠ DEGRADED") : "STOPPED"}
        </span>
      </div>

      {status && (
        <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 font-mono text-[8px]">
          <span className="text-muted-foreground/40">last check</span>
          <span className="text-foreground/50">{age(status.last_check)}</span>
          <span className="text-muted-foreground/40">last ok</span>
          <span className="text-foreground/50">{age(status.last_ok)}</span>
          <span className="text-muted-foreground/40">failures</span>
          <span className={status.consecutive_failures > 0 ? "text-red-400" : "text-muted-foreground/30"}>
            {status.consecutive_failures}
          </span>
          <span className="text-muted-foreground/40">triggers</span>
          <span className={triggered ? "text-red-400 font-semibold" : "text-muted-foreground/30"}>
            {status.total_triggers}
          </span>
        </div>
      )}

      {triggered && status?.log.length && (
        <div className="font-mono text-[7px] text-red-400/60 border border-red-500/20 px-2 py-1 truncate">
          last: {status.log[status.log.length - 1].detail}
        </div>
      )}

      <div className="flex gap-2">
        {!running ? (
          <button
            onClick={onStart}
            disabled={busy}
            className="font-mono text-[8px] px-2 py-1 border border-border text-muted-foreground/50 hover:text-muted-foreground hover:border-foreground/30 transition-colors disabled:opacity-30"
          >
            Arm watchdog
          </button>
        ) : (
          <button
            onClick={onStop}
            disabled={busy}
            className="font-mono text-[8px] px-2 py-1 border border-amber-500/30 text-amber-400/60 hover:border-amber-500 transition-colors disabled:opacity-30"
          >
            Disarm
          </button>
        )}
      </div>
    </div>
  );
}
