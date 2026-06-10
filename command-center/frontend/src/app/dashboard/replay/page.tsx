"use client";

import { useEffect, useState } from "react";
import {
  replayApi,
  type ReplayRun,
  type ReplayEpisode,
  type TrajPoint,
  type SafetyEvent,
} from "@/lib/api";
import { TrajectoryViewer } from "@/components/replay/TrajectoryViewer";
import { ReplayTimeline } from "@/components/replay/ReplayTimeline";
import { ReplaySideBySide } from "@/components/replay/ReplaySideBySide";
import { ChevronRight } from "lucide-react";

function Badge({ ok }: { ok: boolean }) {
  return (
    <span className={`text-[8px] px-1 border font-mono ${ok ? "border-green-500/40 text-green-400" : "border-red-500/40 text-red-400"}`}>
      {ok ? "✓" : "✗"}
    </span>
  );
}

function EpisodeRow({
  ep,
  active,
  onClick,
}: {
  ep: ReplayEpisode;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left flex items-center gap-2 px-3 py-1.5 font-mono text-[9px] transition-colors
        ${active ? "bg-foreground/10 text-foreground" : "text-muted-foreground hover:bg-foreground/5 hover:text-foreground"}`}
    >
      <ChevronRight size={10} className={active ? "opacity-100" : "opacity-0"} />
      <Badge ok={ep.success} />
      <span className="flex-1 truncate">{ep.scene} / s{ep.seed}</span>
      <span className="text-muted-foreground/40">{ep.n_steps}stp</span>
      {ep.n_events > 0 && <span className="text-amber-400">{ep.n_events}ev</span>}
    </button>
  );
}

export default function ReplayPage() {
  const [runs, setRuns] = useState<ReplayRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const [episodes, setEpisodes] = useState<ReplayEpisode[]>([]);
  const [selectedEp, setSelectedEp] = useState<string | null>(null);

  const [trajectory, setTrajectory] = useState<TrajPoint[]>([]);
  const [events, setEvents] = useState<SafetyEvent[]>([]);
  const [epMeta, setEpMeta] = useState<Record<string, unknown> | null>(null);

  const [step, setStep] = useState(0);
  const [compareRun, setCompareRun] = useState<string | null>(null);
  const [showCompare, setShowCompare] = useState(false);

  const [loading, setLoading] = useState(false);
  const [epLoading, setEpLoading] = useState(false);

  // Load run list
  useEffect(() => {
    replayApi.runs()
      .then(r => { setRuns(r); if (r.length) setSelectedRun(r[0].run_id); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  // Load episodes when run changes
  useEffect(() => {
    if (!selectedRun) return;
    setEpisodes([]);
    setSelectedEp(null);
    replayApi.episodes(selectedRun)
      .then(eps => { setEpisodes(eps); if (eps.length) setSelectedEp(eps[0].ep_id); })
      .catch(() => {});
  }, [selectedRun]);

  // Load episode data when selection changes
  useEffect(() => {
    if (!selectedRun || !selectedEp) return;
    setEpLoading(true);
    setStep(0);
    Promise.all([
      replayApi.trajectory(selectedRun, selectedEp),
      replayApi.events(selectedRun, selectedEp),
      replayApi.meta(selectedRun, selectedEp),
    ])
      .then(([traj, evs, meta]) => {
        setTrajectory(traj);
        setEvents(evs);
        setEpMeta(meta);
      })
      .catch(() => {})
      .finally(() => setEpLoading(false));
  }, [selectedRun, selectedEp]);

  const currentEp = episodes.find(e => e.ep_id === selectedEp);
  const baselineRun = runs.find(r => !r.fleetsafe && r.run_id !== selectedRun);
  const fleetsafeRun = runs.find(r => r.fleetsafe && r.run_id !== selectedRun);

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left panel — run + episode selector */}
      <aside className="w-56 shrink-0 border-r border-border flex flex-col overflow-hidden">
        <div className="px-3 pt-3 pb-2 border-b border-border">
          <div className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider mb-2">Runs</div>
          {loading ? (
            <div className="text-[9px] text-muted-foreground/30 font-mono">Loading…</div>
          ) : (
            <div className="flex flex-col gap-0.5">
              {runs.map(r => (
                <button
                  key={r.run_id}
                  onClick={() => { setSelectedRun(r.run_id); setShowCompare(false); }}
                  className={`text-left w-full px-2 py-1.5 font-mono text-[9px] transition-colors truncate
                    ${selectedRun === r.run_id
                      ? "bg-foreground/10 text-foreground"
                      : "text-muted-foreground hover:bg-foreground/5 hover:text-foreground"}`}
                  title={r.run_id}
                >
                  <span className={`mr-1 ${r.fleetsafe ? "text-green-400" : "text-amber-400/70"}`}>
                    {r.fleetsafe ? "FS" : "BL"}
                  </span>
                  {r.model} <span className="text-muted-foreground/40">({r.n_episodes}ep)</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Episode list */}
        <div className="flex-1 overflow-y-auto">
          <div className="px-3 pt-2 pb-1 font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">
            Episodes
          </div>
          {episodes.map(ep => (
            <EpisodeRow
              key={ep.ep_id}
              ep={ep}
              active={selectedEp === ep.ep_id}
              onClick={() => { setSelectedEp(ep.ep_id); setShowCompare(false); }}
            />
          ))}
        </div>
      </aside>

      {/* Main area */}
      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">
        {/* Episode header */}
        {currentEp && (
          <div className="flex items-center gap-4 flex-wrap">
            <div className="font-mono text-xs">
              <span className="text-muted-foreground/50">scene </span>
              <span className="text-foreground">{currentEp.scene}</span>
              <span className="text-muted-foreground/50"> · seed </span>
              <span className="text-foreground">{currentEp.seed}</span>
            </div>
            <Badge ok={currentEp.success} />
            {currentEp.spl > 0 && (
              <span className="font-mono text-[10px] text-muted-foreground">
                SPL <span className="text-foreground">{currentEp.spl.toFixed(3)}</span>
              </span>
            )}
            {currentEp.intervention_count > 0 && (
              <span className="font-mono text-[10px] text-amber-400">
                {currentEp.intervention_count} interventions
              </span>
            )}
            {currentEp.collision_count > 0 && (
              <span className="font-mono text-[10px] text-red-400">
                {currentEp.collision_count} collisions
              </span>
            )}

            <div className="ml-auto flex items-center gap-2">
              {(baselineRun || fleetsafeRun) && (
                <button
                  onClick={() => {
                    const other = fleetsafeRun ?? baselineRun;
                    if (other) { setCompareRun(other.run_id); setShowCompare(v => !v); }
                  }}
                  className="font-mono text-[9px] px-2 py-1 border border-border hover:border-foreground/40 text-muted-foreground hover:text-foreground transition-colors"
                >
                  {showCompare ? "single view" : "side-by-side"}
                </button>
              )}
            </div>
          </div>
        )}

        {/* Episode meta quick stats */}
        {epMeta && !showCompare && (
          <div className="flex flex-wrap gap-4 font-mono text-[9px] text-muted-foreground border-b border-border pb-3">
            {(["steps_taken", "collision_count", "intervention_count", "inference_latency_ms_mean"] as const).map(k => {
              const v = epMeta[k];
              if (v === undefined) return null;
              return (
                <span key={k}>
                  {k.replace(/_/g, " ")}{" "}
                  <span className="text-foreground">
                    {typeof v === "number" ? (v % 1 === 0 ? v : v.toFixed(1)) : String(v)}
                  </span>
                </span>
              );
            })}
          </div>
        )}

        {/* Main content — single or compare */}
        {showCompare && compareRun && selectedRun && selectedEp ? (
          <ReplaySideBySide
            runA={selectedRun}
            runB={compareRun}
            epId={selectedEp}
          />
        ) : (
          <>
            {epLoading ? (
              <div className="font-mono text-[10px] text-muted-foreground/30">Loading episode…</div>
            ) : (
              <div className="flex gap-4 items-start flex-wrap">
                <TrajectoryViewer
                  trajectory={trajectory}
                  events={events}
                  currentStep={step}
                  color="#22c55e"
                />

                {/* Event list */}
                {events.length > 0 && (
                  <div className="flex flex-col gap-1 min-w-[180px]">
                    <div className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider mb-1">Events</div>
                    {events.map((ev, i) => (
                      <button
                        key={i}
                        onClick={() => setStep(ev.step)}
                        className="text-left font-mono text-[9px] px-2 py-1 border border-border hover:border-foreground/40 transition-colors flex items-center gap-2"
                      >
                        <span className={`
                          ${ev.type === "intervention" ? "text-amber-400" :
                            ev.type === "near_miss" ? "text-orange-400" : "text-red-400"}
                        `}>
                          {ev.type.replace("_", " ")}
                        </span>
                        <span className="text-muted-foreground/50">@{ev.step}</span>
                        <span className="text-muted-foreground/40">{ev.min_dist_m.toFixed(2)}m</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {trajectory.length > 0 && (
              <div className="max-w-[380px]">
                <ReplayTimeline
                  totalSteps={trajectory.length}
                  currentStep={step}
                  events={events}
                  onSeek={setStep}
                />
              </div>
            )}
          </>
        )}

        {!selectedRun && !loading && (
          <div className="font-mono text-[10px] text-muted-foreground/30 mt-8">
            No runs with episode data found. Run a benchmark first.
          </div>
        )}
      </div>
    </div>
  );
}
