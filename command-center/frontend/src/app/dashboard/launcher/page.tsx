"use client";

import { useEffect, useState, useCallback } from "react";
import { api, type ScriptInfo, type JobStatus } from "@/lib/api";
import { LiveTerminal } from "@/components/LiveTerminal";

const PRESET_ORDER = ["smoke", "dev", "paper", "real_robot"];
const BACKEND_LABEL: Record<string, string> = {
  mock: "mock", mujoco: "MuJoCo", isaaclab: "Isaac Sim", real: "Real robot",
};

const STATUS_COLOUR: Record<JobStatus["status"], string> = {
  queued:  "text-muted-foreground border-border",
  running: "text-green-400 border-green-500/40",
  done:    "text-foreground border-foreground/30",
  error:   "text-red-400 border-red-400/40",
  killed:  "text-amber-400 border-amber-400/40",
};

function elapsed(job: JobStatus): string {
  if (!job.started_at) return "";
  const end = job.finished_at ?? Date.now() / 1000;
  const s = Math.round(end - job.started_at);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

export default function LauncherPage() {
  const [scripts, setScripts]     = useState<ScriptInfo[]>([]);
  const [jobs, setJobs]           = useState<JobStatus[]>([]);
  const [activeJob, setActiveJob] = useState<string | null>(null);
  const [launching, setLaunching] = useState<string | null>(null);
  const [error, setError]         = useState<string | null>(null);

  const loadJobs = useCallback(async () => {
    try { setJobs(await api.jobs()); } catch { /* backend offline */ }
  }, []);

  useEffect(() => {
    api.scripts().then(setScripts).catch(() => {});
    loadJobs();
  }, [loadJobs]);

  // Poll job status while any job is running
  useEffect(() => {
    const running = jobs.some(j => j.status === "queued" || j.status === "running");
    if (!running) return;
    const id = setInterval(loadJobs, 2000);
    return () => clearInterval(id);
  }, [jobs, loadJobs]);

  async function launch(key: string) {
    setLaunching(key);
    setError(null);
    try {
      const job = await api.launch(key);
      setActiveJob(job.job_id);
      await loadJobs();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Launch failed");
    } finally {
      setLaunching(null);
    }
  }

  async function kill(job_id: string) {
    await api.killJob(job_id);
    await loadJobs();
  }

  // Group scripts by preset
  const grouped = PRESET_ORDER.reduce<Record<string, ScriptInfo[]>>((acc, p) => {
    acc[p] = scripts.filter(s => s.preset === p);
    return acc;
  }, {});

  const presetLabel: Record<string, string> = {
    smoke: "Smoke test", dev: "Development", paper: "Publication grade", real_robot: "Real robot",
  };

  const activeJobObj = jobs.find(j => j.job_id === activeJob);

  return (
    <div className="p-6 flex flex-col gap-6 max-w-4xl">
      <div>
        <h1 className="font-mono text-lg font-semibold tracking-tight">Launcher</h1>
        <p className="font-mono text-xs text-muted-foreground mt-0.5">
          Launch benchmark scripts safely with live log streaming.
        </p>
      </div>

      {error && (
        <div className="border border-red-400/40 bg-red-400/5 px-4 py-2 font-mono text-xs text-red-400">
          {error}
        </div>
      )}

      {/* Script presets */}
      {PRESET_ORDER.map(preset => {
        const group = grouped[preset] ?? [];
        if (!group.length) return null;
        return (
          <section key={preset}>
            <h2 className="font-mono text-[10px] text-muted-foreground uppercase tracking-widest mb-3">
              {presetLabel[preset] ?? preset}
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-px bg-border border border-border">
              {group.map(s => {
                const running = jobs.find(j => j.script_key === s.key && (j.status === "running" || j.status === "queued"));
                const isLaunching = launching === s.key;
                return (
                  <div key={s.key} className="bg-card p-4 flex flex-col gap-2">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="font-mono text-sm font-medium">{s.label}</div>
                        <div className="font-mono text-[10px] text-muted-foreground mt-0.5">{s.description}</div>
                      </div>
                      <span className="font-mono text-[9px] border border-border px-1.5 py-0.5 text-muted-foreground/60 uppercase shrink-0">
                        {BACKEND_LABEL[s.backend] ?? s.backend}
                      </span>
                    </div>

                    <div className="flex items-center gap-2 mt-1">
                      <button
                        onClick={() => launch(s.key)}
                        disabled={!!isLaunching || !!running}
                        className="font-mono text-[10px] uppercase tracking-widest px-3 py-1.5 border transition-colors disabled:opacity-40 border-foreground/30 text-foreground hover:bg-foreground hover:text-background disabled:cursor-not-allowed"
                      >
                        {isLaunching ? "Launching…" : running ? "Running" : "Launch"}
                      </button>
                      {running && (
                        <>
                          <button
                            onClick={() => { setActiveJob(running.job_id); }}
                            className="font-mono text-[10px] text-muted-foreground hover:text-foreground transition-colors"
                          >
                            View logs
                          </button>
                          <button
                            onClick={() => kill(running.job_id)}
                            className="font-mono text-[10px] text-red-400/60 hover:text-red-400 transition-colors ml-auto"
                          >
                            Kill
                          </button>
                        </>
                      )}
                      {s.estimated_s && (
                        <span className="font-mono text-[10px] text-muted-foreground/40 ml-auto">
                          ~{s.estimated_s < 60 ? `${s.estimated_s}s` : `${Math.round(s.estimated_s/60)}m`}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        );
      })}

      {/* Live terminal */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-mono text-[10px] text-muted-foreground uppercase tracking-widest">
            Terminal
            {activeJobObj && (
              <span className={`ml-2 ${STATUS_COLOUR[activeJobObj.status]}`}>
                — {activeJobObj.label} · {activeJobObj.status} {elapsed(activeJobObj)}
              </span>
            )}
          </h2>
          {activeJob && activeJobObj?.status === "running" && (
            <button
              onClick={() => kill(activeJob)}
              className="font-mono text-[10px] text-red-400/60 hover:text-red-400 border border-red-400/20 px-2 py-1 transition-colors"
            >
              Kill
            </button>
          )}
        </div>
        <LiveTerminal jobId={activeJob} />
      </section>

      {/* Job history */}
      {jobs.length > 0 && (
        <section>
          <h2 className="font-mono text-[10px] text-muted-foreground uppercase tracking-widest mb-3">
            Job history
          </h2>
          <div className="border border-border overflow-auto">
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="border-b border-border bg-muted/30">
                  {["ID","Script","Status","Duration"].map(h => (
                    <th key={h} className="px-3 py-2 text-left font-normal text-muted-foreground text-[10px] uppercase tracking-wide">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {jobs.map(j => (
                  <tr
                    key={j.job_id}
                    className={`border-b border-border cursor-pointer hover:bg-accent/30 transition-colors ${activeJob === j.job_id ? "bg-accent/20" : ""}`}
                    onClick={() => setActiveJob(j.job_id)}
                  >
                    <td className="px-3 py-2 text-muted-foreground">{j.job_id}</td>
                    <td className="px-3 py-2">{j.label}</td>
                    <td className={`px-3 py-2 ${STATUS_COLOUR[j.status]}`}>{j.status}</td>
                    <td className="px-3 py-2 text-muted-foreground">{elapsed(j) || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
