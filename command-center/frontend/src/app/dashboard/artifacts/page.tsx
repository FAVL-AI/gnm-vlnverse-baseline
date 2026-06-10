"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type RunSummary } from "@/lib/api";

function pct(v: number) { return (v * 100).toFixed(1) + "%"; }
function ms(v: number)  { return v.toFixed(1) + " ms"; }

const BACKENDS = ["all", "mujoco", "isaaclab", "mock", "real"] as const;
const MODELS   = ["all", "gnm", "vint", "nomad", "base"] as const;

export default function ArtifactsPage() {
  const [runs, setRuns]         = useState<RunSummary[]>([]);
  const [loading, setLoading]   = useState(true);
  const [backend, setBackend]   = useState<string>("all");
  const [model, setModel]       = useState<string>("all");
  const [mode, setMode]         = useState<string>("all");
  const [search, setSearch]     = useState("");

  useEffect(() => {
    api.runs()
      .then(setRuns)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const filtered = runs.filter(r => {
    if (backend !== "all" && r.backend !== backend) return false;
    if (model   !== "all" && r.model   !== model)   return false;
    if (mode    !== "all") {
      if (mode === "fleetsafe" && !r.fleetsafe)  return false;
      if (mode === "baseline"  &&  r.fleetsafe)  return false;
    }
    if (search && !r.run_id.includes(search) && !r.model.includes(search)) return false;
    return true;
  });

  return (
    <div className="p-6 flex flex-col gap-6 max-w-6xl">
      <div>
        <h1 className="font-mono text-lg font-semibold tracking-tight">Artifacts</h1>
        <p className="font-mono text-xs text-muted-foreground mt-0.5">
          {loading ? "Indexing…" : `${runs.length} runs · ${filtered.length} shown`}
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 items-center">
        <input
          className="font-mono text-xs border border-border bg-transparent px-3 py-1.5 focus:outline-none focus:border-foreground/40 placeholder:text-muted-foreground/40 w-48"
          placeholder="search run_id…"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        {[
          { label: "Backend", value: backend, set: setBackend, opts: BACKENDS },
          { label: "Model",   value: model,   set: setModel,   opts: MODELS },
          { label: "Mode",    value: mode,    set: setMode,    opts: ["all","fleetsafe","baseline"] },
        ].map(({ label, value, set, opts }) => (
          <select
            key={label}
            value={value}
            onChange={e => set(e.target.value)}
            className="font-mono text-xs border border-border bg-card text-foreground px-3 py-1.5 focus:outline-none focus:border-foreground/40"
          >
            {opts.map(o => <option key={o} value={o}>{label}: {o}</option>)}
          </select>
        ))}
        {(backend !== "all" || model !== "all" || mode !== "all" || search) && (
          <button
            onClick={() => { setBackend("all"); setModel("all"); setMode("all"); setSearch(""); }}
            className="font-mono text-[10px] text-muted-foreground hover:text-foreground border border-border px-2 py-1.5 transition-colors"
          >
            Clear
          </button>
        )}
      </div>

      {/* Table */}
      <div className="border border-border overflow-auto">
        <table className="w-full text-xs font-mono">
          <thead>
            <tr className="border-b border-border bg-muted/30 text-muted-foreground">
              {["Run ID","Model","Mode","Backend","N","SPL","Success","Collision","Interv.","Latency","Claim",""].map(h => (
                <th key={h} className="px-3 py-2 text-left font-normal text-[10px] uppercase tracking-wide whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={12} className="px-3 py-8 text-center text-muted-foreground">Indexing results…</td></tr>
            )}
            {!loading && filtered.length === 0 && (
              <tr><td colSpan={12} className="px-3 py-8 text-center text-muted-foreground">No runs match filters.</td></tr>
            )}
            {filtered.map(r => (
              <tr key={r.run_id} className="border-b border-border hover:bg-accent/30 transition-colors">
                <td className="px-3 py-2 max-w-[180px]">
                  <Link href={`/dashboard/artifacts/${r.run_id}`} className="hover:underline truncate block">
                    {r.run_id}
                  </Link>
                </td>
                <td className="px-3 py-2 uppercase">{r.model}</td>
                <td className="px-3 py-2">
                  <span className={`px-1.5 py-0.5 text-[9px] border ${r.fleetsafe ? "border-foreground/40" : "border-border text-muted-foreground"}`}>
                    {r.fleetsafe ? "FS" : "base"}
                  </span>
                </td>
                <td className="px-3 py-2 text-muted-foreground">{r.backend}</td>
                <td className="px-3 py-2 text-muted-foreground">{r.n_episodes}</td>
                <td className="px-3 py-2">{pct(r.spl_mean)}</td>
                <td className="px-3 py-2">{pct(r.success_rate)}</td>
                <td className="px-3 py-2 text-red-400/80">{pct(r.collision_rate)}</td>
                <td className="px-3 py-2 text-muted-foreground">{pct(r.intervention_rate_mean)}</td>
                <td className="px-3 py-2 text-muted-foreground">{ms(r.inference_latency_ms_mean)}</td>
                <td className="px-3 py-2 text-[10px] text-muted-foreground/60">{r.claim_scope}</td>
                <td className="px-3 py-2">
                  <Link href={`/dashboard/artifacts/${r.run_id}`} className="text-muted-foreground hover:text-foreground transition-colors">
                    →
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
