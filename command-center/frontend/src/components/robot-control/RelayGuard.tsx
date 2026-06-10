"use client";

import { Check, X, Loader2 } from "lucide-react";
import type { RelayGuardResult } from "@/lib/api";

interface Props {
  result: RelayGuardResult | null;
  loading: boolean;
  onCheck: () => void;
  onConfirmRelay: () => void;
  busy: boolean;
}

export function RelayGuard({ result, loading, onCheck, onConfirmRelay, busy }: Props) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">
          Relay Guard
        </span>
        <button
          onClick={onCheck}
          disabled={loading || busy}
          className="font-mono text-[8px] text-muted-foreground/40 hover:text-muted-foreground border border-border px-2 py-0.5 transition-colors disabled:opacity-30"
        >
          {loading ? <Loader2 size={9} className="animate-spin" /> : "Re-check"}
        </button>
      </div>

      {!result && !loading && (
        <div className="font-mono text-[8px] text-muted-foreground/30">Run safety check first.</div>
      )}

      {loading && (
        <div className="font-mono text-[8px] text-muted-foreground/40 flex items-center gap-1">
          <Loader2 size={9} className="animate-spin" /> Checking…
        </div>
      )}

      {result && (
        <>
          {result.dry_run && (
            <div className="font-mono text-[8px] text-amber-400/60 border border-amber-500/20 px-2 py-1">
              DRY RUN — checks are simulated
            </div>
          )}
          <div className="flex flex-col gap-1">
            {result.checks.map(c => (
              <div key={c.id} className="flex items-start gap-1.5">
                {c.pass
                  ? <Check size={9} className="text-green-400 mt-0.5 shrink-0" />
                  : <X size={9} className="text-red-400 mt-0.5 shrink-0" />}
                <div className="flex flex-col">
                  <span className={`font-mono text-[8px] leading-tight ${c.pass ? "text-foreground/70" : "text-red-400"}`}>
                    {c.label}
                  </span>
                  <span className="font-mono text-[7px] text-muted-foreground/30">{c.detail}</span>
                </div>
              </div>
            ))}
          </div>

          {result.pass ? (
            <button
              onClick={onConfirmRelay}
              disabled={busy}
              className="mt-1 flex items-center justify-center gap-2 px-3 py-2 border border-red-500/60
                text-red-400 font-mono text-[9px] font-semibold hover:bg-red-500/10 transition-colors
                disabled:opacity-30 animate-pulse"
            >
              Confirm — Enable Relay
            </button>
          ) : (
            <div className="font-mono text-[8px] text-red-400/60 border border-red-500/20 px-2 py-1">
              Fix failing checks before enabling relay.
            </div>
          )}
        </>
      )}
    </div>
  );
}
