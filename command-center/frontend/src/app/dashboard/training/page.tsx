"use client";

import { useEffect, useState } from "react";
import { evidenceApi, type TrainingStatus } from "@/lib/api";
import { CheckCircle, XCircle, AlertTriangle, RefreshCw, ExternalLink } from "lucide-react";

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    ok:             "border-green-500/40 text-green-400",
    checkpoint:     "border-green-500/30 text-green-400/70",
    no_runs:        "border-amber-500/30 text-amber-400",
    not_configured: "border-border text-muted-foreground/40",
    shim_only:      "border-amber-500/20 text-amber-400/60",
    not_started:    "border-border text-muted-foreground/30",
    error:          "border-red-500/30 text-red-400",
  };
  return (
    <span className={`font-mono text-[8px] font-semibold px-1.5 py-0.5 border ${map[status] ?? "border-border text-muted-foreground"}`}>
      {status.replace(/_/g, " ").toUpperCase()}
    </span>
  );
}

function Card({ title, status, children }: { title: string; status: string; children: React.ReactNode }) {
  return (
    <div className="border border-border p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="font-mono text-[10px] font-semibold text-foreground/70 uppercase tracking-wider">{title}</span>
        <StatusBadge status={status} />
      </div>
      {children}
    </div>
  );
}

export default function TrainingPage() {
  const [data, setData] = useState<TrainingStatus | null>(null);
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true);
    try { setData(await evidenceApi.trainingStatus()); } catch { /* */ }
    finally { setLoading(false); }
  }

  useEffect(() => { load(); }, []);

  if (loading) return <div className="p-6 font-mono text-[9px] text-muted-foreground/30">Loading…</div>;
  if (!data)   return <div className="p-6 font-mono text-[9px] text-red-400/60">Failed to load training status.</div>;

  const { ppo, wandb, huggingface } = data;

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="px-6 py-4 border-b border-border shrink-0 flex items-center gap-4">
        <span className="font-mono text-sm font-bold tracking-widest text-foreground/80">TRAINING STATUS</span>
        <button onClick={load} className="ml-auto flex items-center gap-1 font-mono text-[8px] text-muted-foreground/40 hover:text-muted-foreground border border-border px-2 py-1 transition-colors">
          <RefreshCw size={9} /> Refresh
        </button>
      </div>

      <div className="grid grid-cols-1 gap-4 p-6 max-w-3xl">

        {/* PPO */}
        <Card title="PPO Reinforcement Learning" status={ppo.status}>
          {ppo.warning && (
            <div className="flex items-start gap-2 font-mono text-[8px] text-amber-400/70 border border-amber-500/20 px-2 py-1.5">
              <AlertTriangle size={9} className="shrink-0 mt-0.5" /> {ppo.warning}
            </div>
          )}
          <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 font-mono text-[8px]">
            <span className="text-muted-foreground/40">Adapter (shim)</span>
            <span className={ppo.shim_exists ? "text-green-400/70" : "text-red-400/60"}>
              {ppo.shim_exists ? "✓ exists" : "✗ not found"}
            </span>
            <span className="text-muted-foreground/40">Checkpoints</span>
            <span className={ppo.checkpoint_count > 0 ? "text-green-400/70" : "text-muted-foreground/30"}>
              {ppo.checkpoint_count > 0 ? `${ppo.checkpoint_count} found` : "none"}
            </span>
            <span className="text-muted-foreground/40">Training active</span>
            <span className={ppo.training_active ? "text-red-400 animate-pulse" : "text-muted-foreground/30"}>
              {ppo.training_active ? "YES" : "no"}
            </span>
            <span className="text-muted-foreground/40">RL scripts</span>
            <span className={ppo.has_rl_scripts ? "text-foreground/50" : "text-muted-foreground/30"}>
              {ppo.has_rl_scripts ? "present" : "not found"}
            </span>
          </div>
          {ppo.notes.map((n: string, i: number) => (
            <div key={i} className="font-mono text-[7px] text-muted-foreground/30">• {n}</div>
          ))}
        </Card>

        {/* W&B */}
        <Card title="Weights & Biases" status={wandb.status}>
          {wandb.warning && (
            <div className="flex items-start gap-2 font-mono text-[8px] text-amber-400/70 border border-amber-500/20 px-2 py-1.5">
              <AlertTriangle size={9} className="shrink-0 mt-0.5" /> {wandb.warning}
            </div>
          )}
          {wandb.status === "not_configured" && (
            <div className="font-mono text-[8px] text-muted-foreground/30">
              To configure: set <code className="text-foreground/40">WANDB_API_KEY</code> env var or run{" "}
              <code className="text-foreground/40">wandb login</code>
            </div>
          )}
          {wandb.runs && wandb.runs.length > 0 && (
            <div className="flex flex-col gap-1">
              {wandb.runs.map((r: Record<string, unknown>, i: number) => (
                <div key={i} className="flex gap-2 font-mono text-[8px]">
                  <span className={`shrink-0 ${r.state === "finished" ? "text-green-400/60" : r.state === "running" ? "text-amber-400 animate-pulse" : "text-muted-foreground/30"}`}>
                    {String(r.state)}
                  </span>
                  <span className="text-foreground/50 truncate">{String(r.name)}</span>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* HuggingFace */}
        <Card title="HuggingFace Hub" status={huggingface.status}>
          {huggingface.warning && (
            <div className="flex items-start gap-2 font-mono text-[8px] text-amber-400/70 border border-amber-500/20 px-2 py-1.5">
              <AlertTriangle size={9} className="shrink-0 mt-0.5" /> {huggingface.warning}
            </div>
          )}
          {huggingface.status === "not_configured" && (
            <div className="font-mono text-[8px] text-muted-foreground/30">
              To configure: set <code className="text-foreground/40">HF_TOKEN</code> env var
            </div>
          )}
          {huggingface.runs && huggingface.runs.length > 0 && (
            <div className="flex flex-col gap-1">
              {huggingface.runs.map((r: Record<string, unknown>, i: number) => (
                <div key={i} className="flex gap-2 font-mono text-[8px]">
                  <ExternalLink size={8} className="text-muted-foreground/30 shrink-0 mt-0.5" />
                  <span className="text-foreground/50 truncate">{String(r.model_id)}</span>
                  {r.downloads != null && <span className="text-muted-foreground/30">{String(r.downloads)} ↓</span>}
                </div>
              ))}
            </div>
          )}
        </Card>

      </div>
    </div>
  );
}
