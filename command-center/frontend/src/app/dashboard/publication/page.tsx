"use client";

import { useEffect, useState, useCallback } from "react";
import { experimentsApi, isaacApi, type PaperMetricRow, type CompareResult2, type EvidenceStatus, type SimEvidenceStatus, type PhotorealStatus } from "@/lib/api";
import { RefreshCw, Download, CheckCircle, XCircle, AlertTriangle, Circle } from "lucide-react";

const STATUS_SYMBOL: Record<EvidenceStatus, string> = {
  PROVEN:        "✓",
  PRELIMINARY:   "~",
  SYNTHETIC:     "s",
  RECORDED_ONLY: "r",
  NOT_VALIDATED: "✗",
};
const STATUS_COLOR: Record<EvidenceStatus, string> = {
  PROVEN:        "text-green-400",
  PRELIMINARY:   "text-amber-400",
  SYNTHETIC:     "text-blue-400",
  RECORDED_ONLY: "text-purple-400",
  NOT_VALIDATED: "text-muted-foreground/30",
};

const MAIN_METRICS = [
  { key: "success_rate",            label: "SR (%)",   pct: true  },
  { key: "collision_rate",          label: "CR (%)",   pct: true  },
  { key: "spl_mean",                label: "SPL",      pct: false },
  { key: "intervention_rate_mean",  label: "IR",       pct: true  },
  { key: "inference_latency_ms_mean",label:"L_cmd (ms)",pct: false },
];

function fmt(val: number | null, pct: boolean): string {
  if (val == null) return "—";
  return pct ? `${(val * 100).toFixed(1)}` : val.toFixed(3);
}

function DeltaCell({ delta }: { delta: number | null }) {
  if (delta == null) return <span className="text-muted-foreground/20">—</span>;
  const pos = delta > 0;
  return (
    <span className={`font-mono text-[8px] ${pos ? "text-green-400/70" : "text-red-400/70"}`}>
      {pos ? "+" : ""}{delta.toFixed(1)}%
    </span>
  );
}

const SIM_STATUS_CFG: Record<string, { color: string; icon: typeof CheckCircle }> = {
  PROVEN:        { color: "text-green-400",    icon: CheckCircle   },
  RECORDED:      { color: "text-green-400/70", icon: CheckCircle   },
  PRELIMINARY:   { color: "text-amber-400",    icon: AlertTriangle },
  RECORDED_ONLY: { color: "text-purple-400",   icon: Circle        },
  MISSING:       { color: "text-red-400/60",   icon: XCircle       },
  NOT_RUN:       { color: "text-muted-foreground/30", icon: Circle },
  NOT_VALIDATED: { color: "text-muted-foreground/30", icon: XCircle },
  NOT_CONFIGURED:{ color: "text-muted-foreground/30", icon: Circle },
  NOT_AVAILABLE: { color: "text-muted-foreground/30", icon: Circle },
  SYNTHETIC:     { color: "text-blue-400",     icon: Circle        },
};

function SimStatusBadge({ status }: { status: string }) {
  const cfg = SIM_STATUS_CFG[status] ?? SIM_STATUS_CFG.NOT_RUN;
  const Icon = cfg.icon;
  return (
    <span className={`flex items-center gap-1 font-mono text-[8px] font-semibold ${cfg.color}`}>
      <Icon size={9} />{status}
    </span>
  );
}

function SimEvidencePanel({ data }: { data: SimEvidenceStatus }) {
  const barColor = data.overall_pct >= 80 ? "bg-green-500" : data.overall_pct >= 50 ? "bg-amber-500" : "bg-red-500/60";
  return (
    <div className="border border-border p-4">
      <div className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider mb-3">
        Simulation Evidence Status (v1.0)
      </div>
      {/* Overall bar */}
      <div className="flex items-center gap-3 mb-3">
        <div className="flex-1 h-1.5 bg-border rounded-full overflow-hidden">
          <div className={`h-full ${barColor} transition-all`} style={{ width: `${data.overall_pct}%` }} />
        </div>
        <span className={`font-mono text-[9px] font-semibold ${data.overall_pct >= 80 ? "text-green-400" : data.overall_pct >= 50 ? "text-amber-400" : "text-red-400/70"}`}>
          {data.overall_pct.toFixed(0)}%
        </span>
      </div>

      {/* Item grid */}
      <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 mb-3">
        {data.items.map(it => (
          <div key={it.name} className="flex items-center justify-between gap-2">
            <span className="font-mono text-[8px] text-muted-foreground/50 truncate">{it.name.replace(/_/g, " ")}</span>
            <SimStatusBadge status={it.status} />
          </div>
        ))}
      </div>

      {/* Isaac detail */}
      {data.isaac.status === "RECORDED" && (
        <div className="border-t border-border/30 pt-2 mt-2 font-mono text-[7px] text-muted-foreground/40 space-y-0.5">
          <div>Isaac: procedural={data.isaac.procedural}  photoreal={data.isaac.photoreal}  runtime={data.isaac.isaac_sim}</div>
          {data.isaac.do_not_claim?.map((s, i) => (
            <div key={i} className="text-red-400/50">✗ do not claim: {s}</div>
          ))}
        </div>
      )}
      {data.isaac.guidance && data.isaac.status === "NOT_RUN" && (
        <div className="font-mono text-[7px] text-muted-foreground/30 mt-1">{data.isaac.guidance}</div>
      )}

      {/* PPO detail */}
      {data.ppo.run_id && (
        <div className="border-t border-border/30 pt-2 mt-2 font-mono text-[7px] text-muted-foreground/40">
          PPO smoke: run={data.ppo.run_id}  reward={data.ppo.mean_reward?.toFixed(3)}  steps={data.ppo.n_steps}
          <div className="text-red-400/50 mt-0.5">✗ do not claim: PPO trained — smoke run only</div>
        </div>
      )}

      {/* Matrix detail */}
      {data.smoke_matrix.status !== "NOT_RUN" && (
        <div className="border-t border-border/30 pt-2 mt-2 font-mono text-[7px] text-muted-foreground/40">
          Matrix: {data.smoke_matrix.n_ok}/{data.smoke_matrix.n_total} runs OK
          {data.smoke_matrix.readiness_pct != null && ` · readiness=${data.smoke_matrix.readiness_pct}%`}
        </div>
      )}
    </div>
  );
}

export default function PublicationPage() {
  const [table, setTable]   = useState<PaperMetricRow[]>([]);
  const [deltas, setDeltas] = useState<CompareResult2[]>([]);
  const [simEvidence, setSimEvidence] = useState<SimEvidenceStatus | null>(null);
  const [photoreal, setPhotoreal]     = useState<PhotorealStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportResult, setExportResult] = useState<string | null>(null);
  const [backendFilter, setBackendFilter] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [t, d, se, pr] = await Promise.all([
        experimentsApi.table(backendFilter || undefined),
        experimentsApi.deltas(),
        experimentsApi.simEvidence(),
        isaacApi.photorealStatus(),
      ]);
      setTable(t.table);
      setDeltas(d);
      setSimEvidence(se);
      setPhotoreal(pr);
    } catch { /* */ }
    finally { setLoading(false); }
  }, [backendFilter]);

  useEffect(() => { load(); }, [load]);

  async function handleExport() {
    setExporting(true);
    try {
      const r = await experimentsApi.export();
      setExportResult(r.ok ? r.output_dir : "Export failed");
    } catch (e) { setExportResult(`Error: ${String(e)}`); }
    finally { setExporting(false); }
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {/* Header */}
      <div className="px-6 py-3 border-b border-border shrink-0 flex items-center gap-4">
        <span className="font-mono text-sm font-bold tracking-widest text-foreground/80">PUBLICATION METRICS</span>
        <span className="font-mono text-[9px] text-muted-foreground/40">
          backbone × safety mode — paper Table 1
        </span>

        <select value={backendFilter} onChange={e => setBackendFilter(e.target.value)}
          className="ml-auto bg-background border border-border font-mono text-[8px] text-muted-foreground px-2 py-1">
          <option value="">All backends</option>
          <option value="mujoco">MuJoCo</option>
          <option value="isaaclab">IsaacLab</option>
        </select>

        <button onClick={load} disabled={loading}
          className="flex items-center gap-1 font-mono text-[8px] text-muted-foreground/40 hover:text-muted-foreground border border-border px-2 py-1 transition-colors disabled:opacity-30">
          <RefreshCw size={9} className={loading ? "animate-spin" : ""} /> Refresh
        </button>

        <button onClick={handleExport} disabled={exporting}
          className="flex items-center gap-1 font-mono text-[8px] text-foreground/60 border border-border px-2 py-1 hover:bg-accent transition-colors disabled:opacity-30">
          <Download size={9} /> {exporting ? "Exporting…" : "Export Bundle"}
        </button>
      </div>

      {exportResult && (
        <div className="px-6 py-2 border-b border-border font-mono text-[8px] text-green-400/70 bg-green-500/5">
          Bundle written: {exportResult}
        </div>
      )}

      <div className="p-6 flex flex-col gap-6 max-w-5xl">

        {/* Simulation evidence status panel (v1.0) */}
        {simEvidence && <SimEvidencePanel data={simEvidence} />}

        {/* Viewport / Photoreal evidence panel */}
        <div className="border border-border p-4 flex flex-col gap-3">
          <div className="flex items-center gap-4">
            <span className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">
              Isaac Sim Viewport Capture
            </span>
            {photoreal && (
              <span className={`font-mono text-[9px] font-semibold ${
                photoreal.status === "PROVEN"    ? "text-green-400" :
                photoreal.status === "PROCEDURAL"? "text-amber-400" :
                photoreal.status === "NOT_RUN"   ? "text-muted-foreground/30" :
                                                   "text-red-400/60"
              }`}>
                {photoreal.status}
              </span>
            )}
            <span className="ml-auto font-mono text-[8px] text-muted-foreground/30">
              run_hospital.sh --capture
            </span>
          </div>

          <div className="flex gap-6 items-start">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={isaacApi.screenshotUrl()}
              alt="Hospital scene preview"
              className="max-h-52 border border-border object-contain bg-background shrink-0"
              onError={e => { (e.target as HTMLImageElement).style.display = "none"; }}
            />
            <div className="flex flex-col gap-2 justify-center font-mono text-[8px] min-w-0">
              {photoreal ? (
                <>
                  {/* Three required labels */}
                  <div className="flex flex-col gap-1">
                    <div className={`flex items-center gap-2 font-semibold ${photoreal.usd_loaded ? "text-green-400/80" : "text-amber-500/70"}`}>
                      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${photoreal.usd_loaded ? "bg-green-400" : "bg-amber-500"}`} />
                      USD asset: {photoreal.usd_loaded
                        ? `FOUND${photoreal.usd_size_kb ? ` (${photoreal.usd_size_kb} KB)` : ""}`
                        : "MISSING — generate first"}
                    </div>
                    <div className={`flex items-center gap-2 font-semibold ${
                      photoreal.status === "PROVEN" ? "text-green-400/80" : "text-amber-400/70"
                    }`}>
                      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                        photoreal.status === "PROVEN" ? "bg-green-400" : "bg-amber-400"
                      }`} />
                      Render: {photoreal.status}
                    </div>
                    <div className="flex items-center gap-2 font-semibold text-red-400/60">
                      <span className="w-1.5 h-1.5 rounded-full shrink-0 bg-red-400/50" />
                      Photoreal: {photoreal.photoreal_claimed === false ? "NOT CLAIMED" : "CLAIMED"}
                    </div>
                  </div>

                  <div className="border-t border-border/30 pt-1.5 text-muted-foreground/40 space-y-0.5">
                    <div>scene     : {photoreal.scene ?? "—"}</div>
                    <div>scenario  : {photoreal.scenario ?? "—"}</div>
                    <div>method    : {photoreal.capture_method ?? "—"}</div>
                    <div>isaac     : {photoreal.isaac_version ?? "—"}</div>
                    <div>captured  : {photoreal.timestamp ?? "—"}</div>
                  </div>

                  {photoreal.honest_label && (
                    <div className="text-[7px] text-muted-foreground/30 leading-relaxed max-w-xs">
                      {photoreal.honest_label}
                    </div>
                  )}
                </>
              ) : (
                <div className="text-muted-foreground/25 space-y-0.5">
                  <div>No capture data.</div>
                  <div className="text-[7px]">Run: python scripts/isaaclab/gen_proof_run.py</div>
                  <div className="text-[7px]">Then: python scripts/isaaclab/export_latest_capture_for_web.py</div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Main comparison table */}
        <div>
          <div className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider mb-3">
            Table 1 — Backbone × Safety Mode
          </div>
          <div className="overflow-x-auto">
            <table className="border-collapse text-left">
              <thead>
                <tr className="border-b border-border">
                  <th className="px-3 py-2 font-mono text-[8px] text-muted-foreground/50">Backbone</th>
                  <th className="px-3 py-2 font-mono text-[8px] text-muted-foreground/50">Safety</th>
                  {MAIN_METRICS.map(m => (
                    <th key={m.key} className="px-3 py-2 font-mono text-[8px] text-muted-foreground/50">{m.label}</th>
                  ))}
                  <th className="px-3 py-2 font-mono text-[8px] text-muted-foreground/50">N</th>
                  <th className="px-3 py-2 font-mono text-[8px] text-muted-foreground/50">Status</th>
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr><td colSpan={MAIN_METRICS.length + 4} className="px-3 py-3 font-mono text-[8px] text-muted-foreground/20">Loading…</td></tr>
                )}
                {table.filter(r => r.backbone !== "MOCK").map((row, i) => (
                  <tr key={i} className={`border-b border-border/30 ${
                    row.safety_mode === "FleetSafe_full" ? "bg-green-500/3" : ""
                  }`}>
                    <td className="px-3 py-1.5 font-mono text-[8px] font-semibold text-foreground/70">{row.backbone}</td>
                    <td className="px-3 py-1.5 font-mono text-[8px] text-foreground/50">
                      {row.safety_mode === "FleetSafe_full" ? "FleetSafe" : "Baseline"}
                    </td>
                    {MAIN_METRICS.map(m => {
                      const mdata = row.metrics[m.key];
                      const statusColor = STATUS_COLOR[mdata?.status as EvidenceStatus] ?? "text-foreground/50";
                      const sym = STATUS_SYMBOL[mdata?.status as EvidenceStatus] ?? "?";
                      return (
                        <td key={m.key} className="px-3 py-1.5">
                          <span className={`font-mono text-[8px] ${statusColor}`}>
                            {fmt(mdata?.value ?? null, m.pct)}{sym}
                          </span>
                          {mdata?.ci_95 && (
                            <span className="font-mono text-[7px] text-muted-foreground/30 ml-1">
                              [{fmt(mdata.ci_95[0], m.pct)}–{fmt(mdata.ci_95[1], m.pct)}]
                            </span>
                          )}
                        </td>
                      );
                    })}
                    <td className="px-3 py-1.5 font-mono text-[8px] text-muted-foreground/40">{row.n_runs}</td>
                    <td className="px-3 py-1.5">
                      <span className={`font-mono text-[7px] ${STATUS_COLOR[row.evidence_status]}`}>
                        {STATUS_SYMBOL[row.evidence_status]} {row.evidence_status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-2 font-mono text-[7px] text-muted-foreground/30">
            ✓ PROVEN  ~ PRELIMINARY  s SYNTHETIC  r RECORDED_ONLY  ✗ NOT_VALIDATED
          </div>
        </div>

        {/* Delta analysis */}
        <div>
          <div className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider mb-3">
            Table 2 — FleetSafe Δ vs Baseline
          </div>
          <table className="border-collapse text-left">
            <thead>
              <tr className="border-b border-border">
                {["Backbone","Backend","Δ SR","Δ CR","Δ IR","Δ SPL","N_base","N_fs","Status"].map(h => (
                  <th key={h} className="px-3 py-2 font-mono text-[8px] text-muted-foreground/50">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {deltas.filter(d => d.backbone !== "MOCK").map((d, i) => (
                <tr key={i} className="border-b border-border/30">
                  <td className="px-3 py-1.5 font-mono text-[8px] font-semibold text-foreground/70">{d.backbone}</td>
                  <td className="px-3 py-1.5 font-mono text-[8px] text-muted-foreground/50">{d.backend}</td>
                  <td className="px-3 py-1.5"><DeltaCell delta={d.delta_pct.success_rate ?? null} /></td>
                  <td className="px-3 py-1.5"><DeltaCell delta={d.delta_pct.collision_rate != null ? -(d.delta_pct.collision_rate) : null} /></td>
                  <td className="px-3 py-1.5"><DeltaCell delta={d.delta_pct.intervention_rate_mean != null ? -(d.delta_pct.intervention_rate_mean) : null} /></td>
                  <td className="px-3 py-1.5"><DeltaCell delta={d.delta_pct.spl_mean ?? null} /></td>
                  <td className="px-3 py-1.5 font-mono text-[8px] text-muted-foreground/40">{d.n_baseline}</td>
                  <td className="px-3 py-1.5 font-mono text-[8px] text-muted-foreground/40">{d.n_fleetsafe}</td>
                  <td className="px-3 py-1.5">
                    <span className={`font-mono text-[7px] ${STATUS_COLOR[d.evidence_status]}`}>
                      {STATUS_SYMBOL[d.evidence_status]} {d.evidence_status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-2 font-mono text-[7px] text-muted-foreground/30">
            Δ CR and Δ IR shown as improvement (positive = safer). All values PRELIMINARY — increase to ≥10 seeds for PROVEN.
          </div>
        </div>

      </div>
    </div>
  );
}
