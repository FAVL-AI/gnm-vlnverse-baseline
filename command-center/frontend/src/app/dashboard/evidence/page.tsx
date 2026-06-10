"use client";

import { useEffect, useState, useCallback } from "react";
import { evidenceApi, type EvidenceManifest, type LedgerEntry, type EvidenceStats } from "@/lib/api";
import { AlertTriangle, CheckCircle, XCircle, Hash, RefreshCw, Filter } from "lucide-react";

const SOURCE_COLORS: Record<string, string> = {
  mujoco:      "text-blue-400",
  isaaclab:    "text-purple-400",
  real_robot:  "text-green-400",
  dashboard:   "text-amber-400",
  wandb:       "text-orange-400",
  huggingface: "text-yellow-400",
};

const GT_LABELS: Record<string, { label: string; color: string }> = {
  perfect_sim_state:   { label: "Perfect Sim GT",    color: "text-blue-400"   },
  semantic_scene_spec: { label: "Semantic Spec",      color: "text-purple-400" },
  sensor_derived:      { label: "Sensor-derived",     color: "text-amber-400"  },
  human_labeled:       { label: "Human Labeled",      color: "text-green-400"  },
  none:                { label: "No GT",              color: "text-muted-foreground/40" },
};

function MissingBadge({ warning }: { warning: string }) {
  return (
    <div className="flex items-start gap-2 border border-red-500/30 bg-red-500/5 px-3 py-2">
      <AlertTriangle size={11} className="text-red-400 shrink-0 mt-0.5" />
      <span className="font-mono text-[8px] text-red-400/80">{warning}</span>
    </div>
  );
}

function CategoryRow({ name, cat }: { name: string; cat: EvidenceManifest["categories"][string] }) {
  const gt = GT_LABELS[cat.ground_truth_type] ?? { label: cat.ground_truth_type, color: "text-muted-foreground" };
  return (
    <div className={`flex items-start gap-3 py-2 border-b border-border/40 ${!cat.present ? "opacity-75" : ""}`}>
      <div className="shrink-0 mt-0.5">
        {cat.present
          ? <CheckCircle size={10} className="text-green-400/70" />
          : <XCircle size={10} className="text-red-400/60" />}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-mono text-[9px] font-semibold text-foreground/70">{name}</span>
          <span className={`font-mono text-[8px] ${gt.color}`}>{gt.label}</span>
          <span className="font-mono text-[8px] text-muted-foreground/40">{cat.count} items</span>
        </div>
        <div className="font-mono text-[8px] text-muted-foreground/40 mt-0.5">{cat.description}</div>
        {cat.missing_warning && <div className="mt-1 font-mono text-[8px] text-red-400/70">{cat.missing_warning}</div>}
      </div>
    </div>
  );
}

function LedgerRow({ e }: { e: LedgerEntry }) {
  const color = SOURCE_COLORS[e.source] ?? "text-muted-foreground/50";
  const ts = new Date(e.timestamp * 1000).toLocaleTimeString("en-US", { hour12: false });
  return (
    <div className="flex gap-2 py-1 border-b border-border/30 font-mono text-[8px] min-w-0">
      <span className="text-muted-foreground/30 shrink-0 w-16">{ts}</span>
      <span className={`shrink-0 w-20 truncate ${color}`}>{e.source}</span>
      <span className="shrink-0 w-32 truncate text-foreground/60">{e.claim_scope}</span>
      <span className="flex-1 truncate text-muted-foreground/50">{e.description}</span>
      {e.sha256
        ? <span className="shrink-0 text-green-400/40 flex items-center gap-0.5"><Hash size={7} />{e.sha256.slice(0, 8)}</span>
        : <span className="shrink-0 text-muted-foreground/20">no hash</span>}
    </div>
  );
}

export default function EvidencePage() {
  const [manifest, setManifest]   = useState<EvidenceManifest | null>(null);
  const [ledger, setLedger]       = useState<LedgerEntry[]>([]);
  const [stats, setStats]         = useState<EvidenceStats | null>(null);
  const [loading, setLoading]     = useState(true);
  const [rebuilding, setRebuilding] = useState(false);
  const [sourceFilter, setSourceFilter] = useState<string>("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [m, l, s] = await Promise.all([
        evidenceApi.manifest(),
        evidenceApi.ledger(sourceFilter || undefined),
        evidenceApi.stats(),
      ]);
      setManifest(m); setLedger(l); setStats(s);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [sourceFilter]);

  useEffect(() => { load(); }, [load]);

  async function rebuild() {
    setRebuilding(true);
    try { setManifest(await evidenceApi.rebuildManifest()); } catch { /* */ }
    finally { setRebuilding(false); }
  }

  const missing = manifest
    ? Object.entries(manifest.categories).filter(([, v]) => !v.present).map(([k]) => k)
    : [];

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="px-6 py-3 border-b border-border shrink-0 flex items-center gap-4">
        <span className="font-mono text-sm font-bold tracking-widest text-foreground/80">EVIDENCE LEDGER</span>
        {stats && (
          <>
            <span className="font-mono text-[10px] text-muted-foreground/50">{stats.total} entries</span>
            <span className="font-mono text-[10px] text-green-400/60">{stats.hashed} hashed</span>
          </>
        )}
        {manifest && (
          <span className="font-mono text-[10px] text-amber-400/70">
            {manifest.summary.defensibility_score} categories present
          </span>
        )}
        <button onClick={rebuild} disabled={rebuilding} className="ml-auto flex items-center gap-1 font-mono text-[8px] text-muted-foreground/40 hover:text-muted-foreground border border-border px-2 py-1 transition-colors disabled:opacity-30">
          <RefreshCw size={9} className={rebuilding ? "animate-spin" : ""} /> Rebuild Manifest
        </button>
      </div>

      <div className="flex flex-1 overflow-hidden">

        {/* Left: manifest categories */}
        <div className="w-80 shrink-0 border-r border-border flex flex-col overflow-hidden">
          {/* Missing warnings */}
          {missing.length > 0 && (
            <div className="p-3 border-b border-border flex flex-col gap-1.5">
              <div className="font-mono text-[9px] text-red-400/70 uppercase tracking-wider">Missing Evidence</div>
              {missing.map(k => (
                <MissingBadge key={k} warning={manifest!.categories[k].missing_warning!} />
              ))}
            </div>
          )}

          {/* Categories */}
          <div className="flex-1 overflow-y-auto px-4 py-3">
            <div className="font-mono text-[9px] text-muted-foreground/40 uppercase tracking-wider mb-2">Dataset Inventory</div>
            {manifest
              ? Object.entries(manifest.categories).map(([k, v]) => (
                  <CategoryRow key={k} name={k} cat={v} />
                ))
              : <div className="font-mono text-[8px] text-muted-foreground/20">Loading…</div>}
          </div>
        </div>

        {/* Right: ledger entries */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="px-4 py-2 border-b border-border shrink-0 flex items-center gap-3">
            <Filter size={10} className="text-muted-foreground/40" />
            <select
              value={sourceFilter}
              onChange={e => setSourceFilter(e.target.value)}
              className="bg-background border border-border font-mono text-[8px] text-muted-foreground px-2 py-1"
            >
              <option value="">All sources</option>
              {["mujoco", "isaaclab", "real_robot", "dashboard", "wandb", "huggingface"].map(s => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            <span className="font-mono text-[8px] text-muted-foreground/30">{ledger.length} entries shown</span>
          </div>
          <div className="flex-1 overflow-y-auto px-4 py-2">
            {loading
              ? <div className="font-mono text-[8px] text-muted-foreground/20">Loading ledger…</div>
              : ledger.length === 0
              ? <div className="font-mono text-[8px] text-muted-foreground/20">No ledger entries yet. Actions recorded here as evidence accumulates.</div>
              : ledger.map((e, i) => <LedgerRow key={i} e={e} />)}
          </div>
        </div>
      </div>
    </div>
  );
}
