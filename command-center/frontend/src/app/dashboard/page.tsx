"use client";

import { useEffect, useState } from "react";
import { api, type RunSummary } from "@/lib/api";
import { MetricCard } from "@/components/MetricCard";
import { ViewportPanel } from "@/components/ViewportPanel";
import { TelemetryPanel } from "@/components/TelemetryPanel";
import Link from "next/link";

function pct(v: number) { return (v * 100).toFixed(1) + "%"; }
function ms(v: number)  { return v.toFixed(1) + " ms"; }

export default function DashboardHome() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.runs()
      .then(setRuns)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const total = runs.length;
  const avg = (key: keyof RunSummary) =>
    total ? runs.reduce((s, r) => s + (r[key] as number), 0) / total : 0;

  const fsRuns   = runs.filter(r => r.fleetsafe);
  const baseRuns = runs.filter(r => !r.fleetsafe);
  const recentRuns = runs.slice(0, 6);

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Main grid — viewport left, data right */}
      <div className="flex flex-1 min-h-0 overflow-hidden">

        {/* Left — Simulation viewport + telemetry */}
        <div className="flex flex-col w-[55%] shrink-0 border-r border-border">
          <ViewportPanel className="flex-1 min-h-0" />
          <div className="border-t border-border">
            <TelemetryPanel />
          </div>
        </div>

        {/* Right — Metrics + recent runs */}
        <div className="flex-1 flex flex-col overflow-auto">

          {/* Headline metrics */}
          <div className="p-4 border-b border-border">
            <div className="flex items-baseline justify-between mb-3">
              <span className="font-mono text-[10px] text-muted-foreground uppercase tracking-widest">
                Aggregate · {loading ? "…" : total + " runs"}
              </span>
              <Link href="/dashboard/artifacts" className="font-mono text-[10px] text-muted-foreground hover:text-foreground transition-colors">
                All runs →
              </Link>
            </div>
            <div className="grid grid-cols-3 gap-px bg-border border border-border">
              <MetricCard label="SPL"       value={pct(avg("spl_mean"))}              unit="" className="bg-card" />
              <MetricCard label="Success"   value={pct(avg("success_rate"))}          unit="" className="bg-card" />
              <MetricCard label="Collision" value={pct(avg("collision_rate"))}        unit="" className="bg-card" />
              <MetricCard label="Interv."   value={pct(avg("intervention_rate_mean"))} unit="" className="bg-card" />
              <MetricCard label="Latency"   value={ms(avg("inference_latency_ms_mean"))} unit="" className="bg-card" />
              <MetricCard label="Runs"      value={total}                             unit="" className="bg-card" />
            </div>
          </div>

          {/* FS vs Baseline comparison */}
          {fsRuns.length > 0 && baseRuns.length > 0 && (
            <div className="p-4 border-b border-border">
              <div className="font-mono text-[10px] text-muted-foreground uppercase tracking-widest mb-3">
                FleetSafe Δ
              </div>
              <div className="grid grid-cols-3 gap-px bg-border border border-border">
                {(["spl_mean","success_rate","collision_rate"] as (keyof RunSummary)[]).map(k => {
                  const fsAvg   = fsRuns.reduce((s,r) => s + (r[k] as number), 0) / fsRuns.length;
                  const baseAvg = baseRuns.reduce((s,r) => s + (r[k] as number), 0) / baseRuns.length;
                  const delta   = fsAvg - baseAvg;
                  const label   = k === "spl_mean" ? "ΔSPL" : k === "success_rate" ? "ΔSuccess" : "ΔCollision";
                  const goodUp  = k !== "collision_rate";
                  const colour  = delta === 0 ? "" : (goodUp ? delta > 0 : delta < 0) ? "text-green-500" : "text-red-400";
                  return (
                    <MetricCard
                      key={k}
                      label={label}
                      value={(delta >= 0 ? "+" : "") + pct(delta)}
                      unit=""
                      className={`bg-card ${colour}`}
                    />
                  );
                })}
              </div>
            </div>
          )}

          {/* Recent runs */}
          <div className="flex-1 overflow-auto p-4">
            <div className="font-mono text-[10px] text-muted-foreground uppercase tracking-widest mb-3">
              Recent runs
            </div>
            <div className="border border-border">
              <table className="w-full text-[10px] font-mono">
                <thead>
                  <tr className="border-b border-border bg-muted/30">
                    {["Model","Mode","Backend","SPL","Collision","Latency"].map(h => (
                      <th key={h} className="px-2 py-1.5 text-left font-normal text-muted-foreground uppercase tracking-wide">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {loading && (
                    <tr><td colSpan={6} className="px-2 py-4 text-center text-muted-foreground">Loading…</td></tr>
                  )}
                  {recentRuns.map(r => (
                    <tr key={r.run_id} className="border-b border-border hover:bg-accent/30 transition-colors">
                      <td className="px-2 py-1.5 uppercase font-medium">
                        <Link href={`/dashboard/artifacts/${r.run_id}`} className="hover:underline">{r.model}</Link>
                      </td>
                      <td className="px-2 py-1.5">
                        <span className={`text-[9px] px-1 border ${r.fleetsafe ? "border-foreground/30 text-foreground" : "border-border text-muted-foreground"}`}>
                          {r.fleetsafe ? "FS" : "base"}
                        </span>
                      </td>
                      <td className="px-2 py-1.5 text-muted-foreground">{r.backend}</td>
                      <td className="px-2 py-1.5">{pct(r.spl_mean)}</td>
                      <td className="px-2 py-1.5 text-red-400/70">{pct(r.collision_rate)}</td>
                      <td className="px-2 py-1.5 text-muted-foreground">{ms(r.inference_latency_ms_mean)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
