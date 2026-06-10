"use client";

import { useState } from "react";
import { useSafetyEvents } from "@/hooks/useSafetyEvents";
import { useFleet } from "@/hooks/useFleet";
import { InterventionFeed } from "@/components/safety/InterventionFeed";
import { fleetApi } from "@/lib/api";
import { AlertTriangle, ShieldCheck } from "lucide-react";

const SEV_BADGE: Record<string, string> = {
  critical: "border-red-500/60 text-red-400",
  warning:  "border-amber-400/40 text-amber-400",
  info:     "border-border text-muted-foreground/50",
};

export default function SafetyPage() {
  const events = useSafetyEvents();
  const fleet  = useFleet();
  const [filter, setFilter] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const robots = fleet?.robots ?? [];
  const estopped = fleet?.estopped ?? [];

  const visible = filter
    ? events.filter(e => e.robot_id === filter || e.event_type === filter)
    : events;

  const criticalCount = events.filter(e => e.severity === "critical").length;
  const interventionCount = events.filter(e => e.event_type === "intervention").length;

  async function doEstop(robot_id: string) {
    setBusy(true);
    try { await fleetApi.estop(robot_id); } catch { /* ignore */ }
    finally { setBusy(false); }
  }

  async function doClear(robot_id: string) {
    setBusy(true);
    try { await fleetApi.clearEstop(robot_id); } catch { /* ignore */ }
    finally { setBusy(false); }
  }

  async function doEstopAll() {
    setBusy(true);
    try { await fleetApi.estopAll(); } catch { /* ignore */ }
    finally { setBusy(false); }
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left: event feed */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Toolbar */}
        <div className="flex items-center gap-4 px-4 py-2 border-b border-border shrink-0 flex-wrap">
          <span className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">
            Safety Console
          </span>

          {/* Quick stats */}
          <div className="flex items-center gap-3 font-mono text-[9px]">
            <span className="text-muted-foreground">
              total <span className="text-foreground">{events.length}</span>
            </span>
            {criticalCount > 0 && (
              <span className="text-red-400">{criticalCount} critical</span>
            )}
            {interventionCount > 0 && (
              <span className="text-amber-400">{interventionCount} interventions</span>
            )}
          </div>

          {/* Filters */}
          <div className="flex items-center gap-1 ml-auto">
            {["intervention", "near_miss", "collision", "estop"].map(t => (
              <button key={t}
                onClick={() => setFilter(filter === t ? null : t)}
                className={`font-mono text-[8px] px-1.5 py-0.5 border transition-colors
                  ${filter === t ? "border-foreground/60 text-foreground" : "border-border text-muted-foreground/40 hover:border-foreground/30"}`}>
                {t.replace("_", " ")}
              </button>
            ))}
          </div>
        </div>

        {/* Feed */}
        <div className="flex-1 overflow-hidden">
          <InterventionFeed events={visible} autoScroll={false} />
        </div>
      </div>

      {/* Right sidebar: robot controls */}
      <aside className="w-48 shrink-0 border-l border-border flex flex-col overflow-hidden">
        <div className="px-3 py-2 border-b border-border font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">
          Controls
        </div>

        <div className="flex-1 overflow-y-auto p-2 flex flex-col gap-3">
          {/* Global e-stop */}
          <button
            onClick={doEstopAll}
            disabled={busy}
            className="w-full flex items-center gap-2 justify-center px-3 py-2.5 border border-red-500/50 text-red-400 font-mono text-[9px] font-semibold hover:border-red-500 hover:text-red-300 transition-colors disabled:opacity-30"
          >
            <AlertTriangle size={11} />
            ALL E-STOP
          </button>

          {/* Per-robot controls */}
          <div className="border-t border-border pt-2 flex flex-col gap-2">
            <div className="font-mono text-[8px] text-muted-foreground/40 uppercase tracking-wider">Per Robot</div>
            {robots.map(r => {
              const stopped = estopped.includes(r.robot_id);
              return (
                <div key={r.robot_id} className="flex flex-col gap-1">
                  <div className="font-mono text-[8px] text-muted-foreground truncate">{r.name}</div>
                  {stopped ? (
                    <button
                      onClick={() => doClear(r.robot_id)}
                      disabled={busy}
                      className="w-full flex items-center gap-1.5 justify-center px-2 py-1 border border-green-500/40 text-green-400 font-mono text-[8px] hover:border-green-500 transition-colors disabled:opacity-30"
                    >
                      <ShieldCheck size={9} /> Clear
                    </button>
                  ) : (
                    <button
                      onClick={() => doEstop(r.robot_id)}
                      disabled={busy}
                      className="w-full flex items-center gap-1.5 justify-center px-2 py-1 border border-red-500/30 text-red-400/60 font-mono text-[8px] hover:border-red-500 hover:text-red-400 transition-colors disabled:opacity-30"
                    >
                      <AlertTriangle size={9} /> E-STOP
                    </button>
                  )}
                </div>
              );
            })}
          </div>

          {/* SEV legend */}
          <div className="border-t border-border pt-2 flex flex-col gap-1">
            <div className="font-mono text-[8px] text-muted-foreground/40 uppercase tracking-wider mb-1">Severity</div>
            {Object.entries(SEV_BADGE).map(([s, cls]) => (
              <span key={s} className={`font-mono text-[8px] px-1 border ${cls} self-start`}>{s}</span>
            ))}
          </div>
        </div>
      </aside>
    </div>
  );
}
