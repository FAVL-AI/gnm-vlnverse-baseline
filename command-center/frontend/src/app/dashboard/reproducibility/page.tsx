"use client";

import { useEffect, useState, useCallback } from "react";
import { experimentsApi, type ClaimValidation, type EvidenceStatus } from "@/lib/api";
import { RefreshCw, CheckCircle, XCircle, AlertTriangle, Circle } from "lucide-react";

const STATUS_CONFIG: Record<string, { icon: typeof CheckCircle; color: string; bg: string }> = {
  PROVEN:        { icon: CheckCircle,   color: "text-green-400",          bg: "border-green-500/30 bg-green-500/5"  },
  PRELIMINARY:   { icon: AlertTriangle, color: "text-amber-400",           bg: "border-amber-500/30 bg-amber-500/5"  },
  SYNTHETIC:     { icon: Circle,        color: "text-blue-400",            bg: "border-blue-500/30 bg-blue-500/5"   },
  RECORDED_ONLY: { icon: Circle,        color: "text-purple-400",          bg: "border-purple-500/30 bg-purple-500/5"},
  NOT_VALIDATED: { icon: XCircle,       color: "text-red-400/60",          bg: "border-red-500/20 bg-red-500/3"     },
  PARTIAL:       { icon: AlertTriangle, color: "text-amber-400/70",        bg: "border-amber-500/20 bg-amber-500/3" },
};

function ClaimCard({ claim }: {
  claim: ClaimValidation["claims"][0];
}) {
  const cfg = STATUS_CONFIG[claim.status] ?? STATUS_CONFIG.NOT_VALIDATED;
  const Icon = cfg.icon;
  return (
    <div className={`border p-3 ${cfg.bg}`}>
      <div className="flex items-start gap-2.5">
        <Icon size={12} className={`${cfg.color} shrink-0 mt-0.5`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="font-mono text-[9px] font-semibold text-foreground/80">{claim.claim}</span>
            <span className={`font-mono text-[7px] font-semibold px-1.5 py-0.5 border ${cfg.bg} ${cfg.color}`}>
              {claim.status}
            </span>
          </div>
          <div className="font-mono text-[8px] text-foreground/50 mb-1">{claim.evidence}</div>
          {claim.gap && (
            <div className="font-mono text-[8px] text-amber-400/60 flex gap-1">
              <span>→</span><span>{claim.gap}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ReadinessGauge({ pct }: { pct: number }) {
  const color = pct >= 80 ? "bg-green-500" : pct >= 50 ? "bg-amber-500" : "bg-red-500/60";
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-1.5 bg-border rounded-full overflow-hidden">
        <div className={`h-full ${color} transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <span className={`font-mono text-[9px] font-semibold ${
        pct >= 80 ? "text-green-400" : pct >= 50 ? "text-amber-400" : "text-red-400/70"
      }`}>{pct.toFixed(0)}%</span>
    </div>
  );
}

export default function ReproducibilityPage() {
  const [data, setData]   = useState<ClaimValidation | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try { setData(await experimentsApi.claims()); } catch { /* */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const summary = data?.summary;

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {/* Header */}
      <div className="px-6 py-3 border-b border-border shrink-0 flex items-center gap-4">
        <span className="font-mono text-sm font-bold tracking-widest text-foreground/80">REPRODUCIBILITY</span>
        <span className="font-mono text-[9px] text-muted-foreground/40">paper claim ↔ evidence audit</span>
        <button onClick={load} disabled={loading}
          className="ml-auto flex items-center gap-1 font-mono text-[8px] text-muted-foreground/40 hover:text-muted-foreground border border-border px-2 py-1 transition-colors disabled:opacity-30">
          <RefreshCw size={9} className={loading ? "animate-spin" : ""} /> Refresh
        </button>
      </div>

      <div className="p-6 flex flex-col gap-6 max-w-3xl">

        {/* Readiness summary */}
        {summary && (
          <div className="border border-border p-4">
            <div className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider mb-3">
              Publication Readiness
            </div>
            <ReadinessGauge pct={summary.readiness_pct} />
            <div className="grid grid-cols-4 gap-3 mt-3">
              {[
                { label: "Proven",        n: summary.proven,        color: "text-green-400"   },
                { label: "Preliminary",   n: summary.preliminary,   color: "text-amber-400"   },
                { label: "Recorded only", n: summary.recorded_only, color: "text-purple-400"  },
                { label: "Not validated", n: summary.not_validated, color: "text-red-400/60"  },
              ].map(({ label, n, color }) => (
                <div key={label} className="font-mono">
                  <div className={`text-[18px] font-semibold ${color}`}>{n}</div>
                  <div className="text-[8px] text-muted-foreground/40">{label}</div>
                </div>
              ))}
            </div>
            <div className="mt-3 font-mono text-[8px] text-muted-foreground/30 leading-relaxed">
              Readiness = (PROVEN + 0.5 × PRELIMINARY) / total claims.
              Target: ≥80% for conference submission.
            </div>
          </div>
        )}

        {/* Claim-by-claim audit */}
        <div>
          <div className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider mb-3">
            Paper Claim Audit
          </div>
          {loading && <div className="font-mono text-[8px] text-muted-foreground/20">Loading…</div>}
          <div className="flex flex-col gap-2">
            {data?.claims.map((c, i) => (
              <ClaimCard key={i} claim={c} />
            ))}
          </div>
        </div>

        {/* Promotion path */}
        <div className="border border-border p-4">
          <div className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider mb-3">
            Evidence Promotion Path
          </div>
          <div className="flex flex-col gap-1.5 font-mono text-[8px]">
            {[
              { from: "NOT_VALIDATED", arrow: "→ run 1 seed" },
              { from: "PRELIMINARY",   arrow: "→ run ≥10 seeds, ≥3 scenes, hash-verify" },
              { from: "SYNTHETIC",     arrow: "→ record real robot session" },
              { from: "RECORDED_ONLY", arrow: "→ analyze session, compute metrics" },
              { from: "PROVEN",        arrow: "✓ publication-ready" },
            ].map(({ from, arrow }) => (
              <div key={from} className="flex items-center gap-2">
                <span className={`w-28 shrink-0 ${STATUS_CONFIG[from]?.color ?? "text-foreground/50"}`}>
                  {from}
                </span>
                <span className="text-muted-foreground/30">{arrow}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Reproducibility requirements */}
        <div className="border border-border p-4">
          <div className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider mb-3">
            Reproducibility Requirements
          </div>
          <div className="font-mono text-[8px] text-foreground/50 leading-relaxed space-y-1">
            <div>1. <span className="text-foreground/70">git checkout</span> &lt;commit&gt; from run manifest</div>
            <div>2. <span className="text-foreground/70">python benchmarks/.../run_benchmark.py</span> with same backbone/seed/scene</div>
            <div>3. <span className="text-foreground/70">sha256sum</span> output matches manifest hash</div>
            <div>4. Evidence ledger entry must exist with matching ID and SHA256</div>
          </div>
          <div className="mt-3 font-mono text-[7px] text-muted-foreground/30">
            See /dashboard/experiments → expand any run for git commit + artifact hash.
            Export bundle via /dashboard/publication → Export Bundle for reviewer submission.
          </div>
        </div>

      </div>
    </div>
  );
}
