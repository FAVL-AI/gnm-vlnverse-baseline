"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type RunDetail } from "@/lib/api";
import { MetricCard } from "@/components/MetricCard";

function pct(v: number | undefined) {
  if (v == null) return "—";
  return (v * 100).toFixed(1) + "%";
}
function ms(v: number | undefined) {
  if (v == null) return "—";
  return v.toFixed(1) + " ms";
}
function num(v: unknown) {
  if (typeof v === "number") return v.toFixed(3);
  return String(v ?? "—");
}

export default function RunDetailPage({ params }: { params: { runId: string } }) {
  const [detail, setDetail]   = useState<RunDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [tab, setTab]         = useState<"metrics" | "scene" | "episodes" | "files">("metrics");

  useEffect(() => {
    api.run(params.runId)
      .then(setDetail)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [params.runId]);

  if (loading) {
    return <div className="p-6 font-mono text-xs text-muted-foreground">Loading…</div>;
  }
  if (!detail) {
    return <div className="p-6 font-mono text-xs text-red-400">Run not found: {params.runId}</div>;
  }

  const { metrics: m, metadata: md, by_scene, episodes, files } = detail;
  const mm = m as Record<string, unknown>;

  const TAB_STYLE = (t: string) =>
    `font-mono text-[10px] uppercase tracking-widest px-3 py-2 border-b-2 transition-colors cursor-pointer ${
      tab === t
        ? "border-foreground text-foreground"
        : "border-transparent text-muted-foreground hover:text-foreground"
    }`;

  return (
    <div className="p-6 flex flex-col gap-5 max-w-5xl">
      {/* Breadcrumb */}
      <div className="font-mono text-[10px] text-muted-foreground flex items-center gap-1.5">
        <Link href="/dashboard/artifacts" className="hover:text-foreground transition-colors">Artifacts</Link>
        <span>/</span>
        <span className="text-foreground">{params.runId}</span>
      </div>

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="font-mono text-base font-semibold tracking-tight">{params.runId}</h1>
          <div className="flex items-center gap-3 mt-1.5 font-mono text-[10px] text-muted-foreground">
            <span className="uppercase">{detail.model}</span>
            <span>·</span>
            <span className={detail.fleetsafe ? "text-foreground" : "text-muted-foreground"}>
              {detail.fleetsafe ? "FleetSafe" : "Baseline"}
            </span>
            <span>·</span>
            <span>{detail.backend}</span>
            <span>·</span>
            <span>{detail.timestamp_utc}</span>
          </div>
        </div>
        <span className="font-mono text-[9px] border border-border px-2 py-1 text-muted-foreground/60 uppercase shrink-0">
          {detail.claim_scope}
        </span>
      </div>

      {/* Headline metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-border border border-border">
        <MetricCard label="Episodes"    value={detail.n_episodes}            unit=""    className="bg-card" />
        <MetricCard label="SPL"         value={pct(detail.spl_mean)}         unit=""    className="bg-card" />
        <MetricCard label="Success"     value={pct(detail.success_rate)}     unit=""    className="bg-card" />
        <MetricCard label="Collision"   value={pct(detail.collision_rate)}   unit=""    className="bg-card" />
        <MetricCard label="Intervention"value={pct(detail.intervention_rate_mean)} unit="" className="bg-card" />
        <MetricCard label="Latency"     value={ms(detail.inference_latency_ms_mean)} unit="" className="bg-card" />
        <MetricCard label="Git"         value={String(mm.git_commit ?? "—")} unit=""    className="bg-card" />
        <MetricCard label="Version"     value={String(mm.benchmark_version ?? "—")} unit="" className="bg-card" />
      </div>

      {/* Tabs */}
      <div className="flex gap-0 border-b border-border">
        {(["metrics","scene","episodes","files"] as const).map(t => (
          <button key={t} className={TAB_STYLE(t)} onClick={() => setTab(t)}>
            {t === "scene" ? "By scene" : t}
          </button>
        ))}
      </div>

      {/* Tab: all metrics */}
      {tab === "metrics" && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-px bg-border border border-border">
          {Object.entries(mm)
            .filter(([, v]) => typeof v === "number")
            .map(([k, v]) => (
              <MetricCard key={k} label={k} value={num(v)} unit="" className="bg-card" />
            ))}
        </div>
      )}

      {/* Tab: by scene */}
      {tab === "scene" && (
        <div className="border border-border overflow-auto">
          <table className="w-full text-xs font-mono">
            <thead>
              <tr className="border-b border-border bg-muted/30 text-muted-foreground">
                {["Scene","Episodes","SPL","Success","Collision"].map(h => (
                  <th key={h} className="px-3 py-2 text-left font-normal text-[10px] uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Object.entries(by_scene as Record<string, Record<string,number>>).map(([scene, agg]) => (
                <tr key={scene} className="border-b border-border hover:bg-accent/30">
                  <td className="px-3 py-2 font-medium">{scene}</td>
                  <td className="px-3 py-2 text-muted-foreground">{agg.n_episodes}</td>
                  <td className="px-3 py-2">{pct(agg.spl_mean)}</td>
                  <td className="px-3 py-2">{pct(agg.success_rate)}</td>
                  <td className="px-3 py-2 text-red-400/80">{pct(agg.collision_rate)}</td>
                </tr>
              ))}
              {Object.keys(by_scene).length === 0 && (
                <tr><td colSpan={5} className="px-3 py-6 text-center text-muted-foreground">No per-scene data.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Tab: episodes */}
      {tab === "episodes" && (
        <div className="border border-border overflow-auto">
          <table className="w-full text-xs font-mono">
            <thead>
              <tr className="border-b border-border bg-muted/30 text-muted-foreground">
                {["#","Scene","Seed","SPL","Success","Collisions","Interventions","Latency"].map(h => (
                  <th key={h} className="px-3 py-2 text-left font-normal text-[10px] uppercase tracking-wide whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {episodes.map((ep, i) => {
                const e = ep as Record<string, unknown>;
                const metrics = (e.metrics ?? e) as Record<string, unknown>;
                return (
                  <tr key={i} className="border-b border-border hover:bg-accent/30">
                    <td className="px-3 py-2 text-muted-foreground">{i + 1}</td>
                    <td className="px-3 py-2">{String(e.scene ?? metrics.scene ?? "—")}</td>
                    <td className="px-3 py-2 text-muted-foreground">{String(e.seed ?? metrics.seed ?? "—")}</td>
                    <td className="px-3 py-2">{pct(metrics.spl as number)}</td>
                    <td className="px-3 py-2">{String(metrics.success ?? "—")}</td>
                    <td className="px-3 py-2 text-red-400/70">{String(metrics.collision_count ?? "—")}</td>
                    <td className="px-3 py-2 text-muted-foreground">{String(metrics.intervention_count ?? "—")}</td>
                    <td className="px-3 py-2 text-muted-foreground">{ms(metrics.inference_latency_ms_mean as number)}</td>
                  </tr>
                );
              })}
              {episodes.length === 0 && (
                <tr><td colSpan={8} className="px-3 py-6 text-center text-muted-foreground">No episode files found.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Tab: files */}
      {tab === "files" && (
        <div className="border border-border overflow-auto">
          <table className="w-full text-xs font-mono">
            <thead>
              <tr className="border-b border-border bg-muted/30 text-muted-foreground">
                {["Path","Size",""].map(h => (
                  <th key={h} className="px-3 py-2 text-left font-normal text-[10px] uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {files.map(f => (
                <tr key={f.rel} className="border-b border-border hover:bg-accent/30">
                  <td className="px-3 py-2 text-muted-foreground/80">{f.rel}</td>
                  <td className="px-3 py-2 text-muted-foreground/50">{(f.size / 1024).toFixed(1)} KB</td>
                  <td className="px-3 py-2">
                    <a
                      href={api.fileUrl(params.runId, f.rel)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-muted-foreground hover:text-foreground transition-colors"
                    >
                      download
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
