"use client";

import { Play, Square, Loader2 } from "lucide-react";

const STATE_ORDER = [
  "IDLE", "VERIFYING", "STARTING_FLEETSAFE",
  "ENABLING_RELAY", "RUNNING_PATH", "STOPPING", "DONE",
];

interface DemoStatus {
  state: string;
  log: string[];
  start_ts: number | null;
  end_ts: number | null;
}

interface Props {
  status: DemoStatus | null;
  onStart: () => void;
  onAbort: () => void;
  busy: boolean;
  estopLatched: boolean;
}

function StateStep({ label, current, done, error }: { label: string; current: boolean; done: boolean; error: boolean }) {
  return (
    <div className={`flex items-center gap-1.5 font-mono text-[8px] ${
      error ? "text-red-400" :
      current ? "text-amber-400 animate-pulse" :
      done ? "text-green-400/70" :
      "text-muted-foreground/25"
    }`}>
      <span>{done ? "✓" : current ? "→" : "·"}</span>
      <span>{label}</span>
    </div>
  );
}

export function DemoMode({ status, onStart, onAbort, busy, estopLatched }: Props) {
  const state = status?.state ?? "IDLE";
  const isRunning = !["IDLE", "DONE", "ERROR"].includes(state);
  const isError = state === "ERROR";
  const isDone = state === "DONE";
  const stateIdx = STATE_ORDER.indexOf(state);

  const elapsed = status?.start_ts && status?.end_ts
    ? ((status.end_ts - status.start_ts)).toFixed(1)
    : status?.start_ts
    ? ((Date.now() / 1000 - status.start_ts)).toFixed(1)
    : null;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">
          Demo Mode
        </span>
        <span className={`font-mono text-[8px] font-semibold px-1.5 py-0.5 border ${
          isError ? "border-red-500/40 text-red-400" :
          isDone ? "border-green-500/30 text-green-400/70" :
          isRunning ? "border-amber-500/40 text-amber-400" :
          "border-border text-muted-foreground/30"
        }`}>
          {state}
        </span>
      </div>

      {/* State pipeline */}
      <div className="flex flex-col gap-0.5 pl-1">
        {STATE_ORDER.filter(s => s !== "IDLE").map((s, i) => (
          <StateStep
            key={s}
            label={s.toLowerCase().replace(/_/g, " ")}
            current={state === s}
            done={stateIdx > STATE_ORDER.indexOf(s) && !isError}
            error={isError && state === s}
          />
        ))}
      </div>

      {elapsed && (
        <div className="font-mono text-[8px] text-muted-foreground/40">
          elapsed: {elapsed}s
        </div>
      )}

      {/* Recent log */}
      {status?.log && status.log.length > 0 && (
        <div className="flex flex-col gap-0.5 max-h-24 overflow-y-auto">
          {status.log.slice(-6).map((line, i) => (
            <div key={i} className={`font-mono text-[7px] leading-4 ${
              /error|emergency/i.test(line) ? "text-red-400/70" :
              /relay enabled|done/i.test(line) ? "text-green-400/60" :
              "text-muted-foreground/35"
            }`}>{line}</div>
          ))}
        </div>
      )}

      {estopLatched && (
        <div className="font-mono text-[8px] text-red-400/60 border border-red-500/20 px-2 py-1">
          Clear e-stop latch before starting demo.
        </div>
      )}

      <div className="flex gap-2">
        {!isRunning ? (
          <button
            onClick={onStart}
            disabled={busy || estopLatched}
            className="flex items-center gap-1.5 px-3 py-2 border border-green-500/30 text-green-400/70
              font-mono text-[8px] hover:border-green-500 hover:text-green-400 transition-colors
              disabled:opacity-30 disabled:pointer-events-none"
          >
            {busy ? <Loader2 size={9} className="animate-spin" /> : <Play size={9} />}
            Run Demo
          </button>
        ) : (
          <button
            onClick={onAbort}
            disabled={busy}
            className="flex items-center gap-1.5 px-3 py-2 border border-red-500/50 text-red-400
              font-mono text-[8px] hover:bg-red-500/10 transition-colors disabled:opacity-30"
          >
            <Square size={9} /> Abort
          </button>
        )}
      </div>
    </div>
  );
}
