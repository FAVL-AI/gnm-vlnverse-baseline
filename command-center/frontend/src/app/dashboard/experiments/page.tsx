"use client";

import { useEffect, useState, useCallback } from "react";
import { experimentsApi, type ExperimentRun, type RegistrySummary, type EvidenceStatus } from "@/lib/api";
import { RefreshCw, ChevronDown, ChevronRight } from "lucide-react";

const STATUS_STYLE: Record<string, { color: string; bg: string; symbol: string }> = {
  PROVEN:        { color: "text-green-400",          bg: "bg-green-500/10 border-green-500/30",  symbol: "✓" },
  PRELIMINARY:   { color: "text-amber-400",           bg: "bg-amber-500/10 border-amber-500/30",  symbol: "~" },
  SYNTHETIC:     { color: "text-blue-400",            bg: "bg-blue-500/10 border-blue-500/30",    symbol: "s" },
  RECORDED_ONLY: { color: "text-purple-400",          bg: "bg-purple-500/10 border-purple-500/30",symbol: "r" },
  NOT_VALIDATED: { color: "text-muted-foreground/40", bg: "bg-card border-border",               symbol: "✗" },
};

const BACKBONE_COLOR: Record<string, string> = {
  ViNT:  "text-blue-400",
  NoMaD: "text-purple-400",
  GNM:   "text-green-400",
  MOCK:  "text-muted-foreground/30",
};

function StatusBadge({ status }: { status: EvidenceStatus }) {
  const s = STATUS_STYLE[status] ?? STATUS_STYLE.NOT_VALIDATED;
  return (
    <span className={`font-mono text-[7px] font-semibold px-1.5 py-0.5 border ${s.bg} ${s.color}`}>
      {s.symbol} {status}
    </span>
  );
}

function MetricCell({ val, metricKey }: { val: number | null; metricKey: string }) {
  if (val == null) return <span className="text-muted-foreground/20">—</span>;
  const isRate = metricKey.includes("rate") || metricKey === "success_rate" || metricKey === "collision_rate";
  return (
    <span className={`font-mono text-[8px] ${
      metricKey === "success_rate"  ? (val > 0.1 ? "text-green-400/70" : "text-muted-foreground/40") :
      metricKey === "collision_rate"? (val > 0 ? "text-red-400/70" : "text-green-400/60") :
      "text-foreground/50"
    }`}>
      {isRate ? `${(val * 100).toFixed(1)}%` : val.toFixed(3)}
    </span>
  );
}

function RunRow({ run, expanded, onToggle }: {
  run: ExperimentRun;
  expanded: boolean;
  onToggle: () => void;
}) {
  const bbColor = BACKBONE_COLOR[run.backbone] ?? "text-foreground/60";
  return (
    <>
      <tr
        className="border-b border-border/30 hover:bg-accent/30 cursor-pointer"
        onClick={onToggle}
      >
        <td className="px-3 py-1.5 w-5">
          {expanded
            ? <ChevronDown size={9} className="text-muted-foreground/40" />
            : <ChevronRight size={9} className="text-muted-foreground/30" />}
        </td>
        <td className="px-2 py-1.5 font-mono text-[8px] text-muted-foreground/40 truncate max-w-[140px]">
          {run.run_id}
        </td>
        <td className={`px-2 py-1.5 font-mono text-[8px] font-semibold ${bbColor}`}>{run.backbone}</td>
        <td className="px-2 py-1.5 font-mono text-[8px] text-foreground/60">
          {run.safety_mode === "FleetSafe_full" ? "FleetSafe" : "Baseline"}
        </td>
        <td className="px-2 py-1.5 font-mono text-[8px] text-muted-foreground/50">{run.backend}</td>
        <td className="px-2 py-1.5">
          <MetricCell val={run.paper_metrics.success_rate ?? null} metricKey="success_rate" />
        </td>
        <td className="px-2 py-1.5">
          <MetricCell val={run.paper_metrics.collision_rate ?? null} metricKey="collision_rate" />
        </td>
        <td className="px-2 py-1.5">
          <MetricCell val={run.paper_metrics.intervention_rate_mean ?? null} metricKey="intervention_rate_mean" />
        </td>
        <td className="px-2 py-1.5 font-mono text-[8px] text-muted-foreground/40">{run.n_episodes}</td>
        <td className="px-2 py-1.5"><StatusBadge status={run.evidence_status} /></td>
      </tr>
      {expanded && (
        <tr className="border-b border-border/20 bg-card/50">
          <td colSpan={10} className="px-6 py-3">
            <div className="grid grid-cols-4 gap-4 font-mono text-[7px]">
              <div>
                <div className="text-muted-foreground/40 mb-1">Identifiers</div>
                <div className="text-foreground/50">git: {run.git_commit}</div>
                <div className="text-foreground/50">seed: {run.seed}</div>
                <div className="text-foreground/50">scene: {run.scene}</div>
              </div>
              <div>
                <div className="text-muted-foreground/40 mb-1">SPL / Latency</div>
                <div className="text-foreground/50">SPL: {run.paper_metrics.spl_mean?.toFixed(3) ?? "—"}</div>
                <div className="text-foreground/50">L_cmd: {run.paper_metrics.inference_latency_ms_mean?.toFixed(2) ?? "—"}ms</div>
                <div className="text-foreground/50">d_min: {run.paper_metrics.min_obstacle_distance_m_mean?.toFixed(2) ?? "—"}m</div>
              </div>
              <div>
                <div className="text-muted-foreground/40 mb-1">Zone Safety</div>
                <div className="text-foreground/50">T_red: {run.paper_metrics.steps_red_mean?.toFixed(1) ?? "—"} steps</div>
                <div className="text-foreground/50">violations: {run.paper_metrics.near_violation_count_mean?.toFixed(1) ?? "—"}</div>
                <div className="text-foreground/50">ρ_crowd: {run.paper_metrics.crowding_risk_score_mean?.toFixed(3) ?? "—"}</div>
              </div>
              <div>
                <div className="text-muted-foreground/40 mb-1">Artifacts</div>
                <div className={run.hashes.aggregate_metrics ? "text-green-400/50" : "text-red-400/40"}>
                  metrics: {run.hashes.aggregate_metrics
                    ? `#${run.hashes.aggregate_metrics.slice(0, 8)}`
                    : "no hash"}
                </div>
                <div className="text-muted-foreground/30">
                  video: {run.artifacts.video_path ? "present" : "none"}
                </div>
                <div className="text-muted-foreground/30">
                  bag: {run.artifacts.bag_path ? "present" : "none"}
                </div>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export default function ExperimentsPage() {
  const [runs, setRuns]         = useState<ExperimentRun[]>([]);
  const [summary, setSummary]   = useState<RegistrySummary | null>(null);
  const [loading, setLoading]   = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [bbFilter, setBbFilter] = useState("");
  const [modeFilter, setModeFilter] = useState("");
  const [backendFilter, setBackendFilter] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [r, s] = await Promise.all([
        experimentsApi.runs({
          backbone:    bbFilter || undefined,
          safety_mode: modeFilter || undefined,
          backend:     backendFilter || undefined,
        }),
        experimentsApi.summary(),
      ]);
      setRuns(r);
      setSummary(s);
    } catch { /* */ }
    finally { setLoading(false); }
  }, [bbFilter, modeFilter, backendFilter]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="px-6 py-3 border-b border-border shrink-0 flex items-center gap-4 flex-wrap">
        <span className="font-mono text-sm font-bold tracking-widest text-foreground/80">
          EXPERIMENT REGISTRY
        </span>
        {summary && (
          <div className="flex gap-3">
            {Object.entries(summary.by_status).map(([s, n]) => (
              <span key={s} className={`font-mono text-[8px] ${STATUS_STYLE[s]?.color ?? "text-foreground/40"}`}>
                {STATUS_STYLE[s]?.symbol} {n} {s}
              </span>
            ))}
          </div>
        )}

        <div className="flex gap-2 ml-auto">
          {[
            { value: bbFilter, onChange: setBbFilter, placeholder: "All backbones", options: summary?.backbones ?? [] },
          ].map(({ value, onChange, placeholder, options }) => (
            <select key={placeholder} value={value} onChange={e => onChange(e.target.value)}
              className="bg-background border border-border font-mono text-[8px] text-muted-foreground px-2 py-1">
              <option value="">{placeholder}</option>
              {options.map(o => <option key={o} value={o}>{o}</option>)}
            </select>
          ))}
          <select value={modeFilter} onChange={e => setModeFilter(e.target.value)}
            className="bg-background border border-border font-mono text-[8px] text-muted-foreground px-2 py-1">
            <option value="">All modes</option>
            <option value="nominal_only">Baseline</option>
            <option value="FleetSafe_full">FleetSafe</option>
          </select>
          <select value={backendFilter} onChange={e => setBackendFilter(e.target.value)}
            className="bg-background border border-border font-mono text-[8px] text-muted-foreground px-2 py-1">
            <option value="">All backends</option>
            <option value="mujoco">MuJoCo</option>
            <option value="isaaclab">IsaacLab</option>
            <option value="mock">Mock</option>
          </select>
          <button onClick={load} disabled={loading}
            className="flex items-center gap-1 font-mono text-[8px] text-muted-foreground/40 hover:text-muted-foreground border border-border px-2 py-1 transition-colors disabled:opacity-30">
            <RefreshCw size={9} className={loading ? "animate-spin" : ""} /> Refresh
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto">
        <table className="w-full border-collapse text-left">
          <thead className="sticky top-0 bg-card border-b border-border">
            <tr>
              <th className="px-3 py-2 w-5" />
              {["Run ID","Backbone","Safety","Backend","SR (%)","CR (%)","IR","N","Status"].map(h => (
                <th key={h} className="px-2 py-2 font-mono text-[8px] text-muted-foreground/50">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={10} className="px-4 py-4 font-mono text-[8px] text-muted-foreground/20">Loading…</td></tr>
            )}
            {!loading && runs.length === 0 && (
              <tr><td colSpan={10} className="px-4 py-4 font-mono text-[8px] text-muted-foreground/20">No runs found.</td></tr>
            )}
            {runs.filter(r => r.backbone !== "MOCK").map(r => (
              <RunRow
                key={r.run_id}
                run={r}
                expanded={expanded === r.run_id}
                onToggle={() => setExpanded(expanded === r.run_id ? null : r.run_id)}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
