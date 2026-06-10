"use client";

import { useCallback, useEffect, useState } from "react";
import { missionApi, fleetApi, type Mission, type RobotSnapshot } from "@/lib/api";
import { Plus, X, RefreshCw } from "lucide-react";

const STATUS_STYLE: Record<string, string> = {
  queued:      "text-muted-foreground/50 border-border",
  dispatching: "text-amber-400 border-amber-400/30",
  running:     "text-green-400 border-green-500/30",
  done:        "text-foreground/40 border-border",
  failed:      "text-red-400 border-red-500/30",
  cancelled:   "text-muted-foreground/30 border-border",
};

const HOSPITAL_SCENES = [
  "hospital_corridor", "hospital_waiting_room", "hospital_narrow_passage",
  "hospital_crowded_junction", "hospital_elevator_lobby", "hospital_reception",
];

function fmt(ts: number | null): string {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleTimeString("en-US", { hour12: false });
}

export default function MissionsPage() {
  const [missions, setMissions] = useState<Mission[]>([]);
  const [robots, setRobots] = useState<RobotSnapshot[]>([]);
  const [loading, setLoading] = useState(false);

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ robot_id: "", scene: HOSPITAL_SCENES[0], goal: "", priority: 5 });
  const [submitting, setSubmitting] = useState(false);

  const refresh = useCallback(() => {
    missionApi.list().then(setMissions).catch(() => {});
  }, []);

  useEffect(() => {
    fleetApi.robots().then(setRobots).catch(() => {});
    missionApi.list()
      .then(setMissions)
      .catch(() => {})
      .finally(() => setLoading(false));
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, [refresh]);

  async function handleCreate() {
    if (!form.robot_id || !form.scene) return;
    setSubmitting(true);
    try {
      const m = await missionApi.create({
        robot_id: form.robot_id,
        scene: form.scene,
        goal_description: form.goal,
        priority: form.priority,
      });
      if (m) setMissions(prev => [m, ...prev]);
      setShowForm(false);
    } catch { /* ignore */ }
    finally { setSubmitting(false); }
  }

  async function handleCancel(id: string) {
    try {
      await missionApi.cancel(id);
      setMissions(prev => prev.map(x => x.mission_id === id ? { ...x, status: "cancelled" as const } : x));
    } catch { /* ignore */ }
  }

  const byStatus = (s: string) => missions.filter(m => m.status === s);

  return (
    <div className="flex flex-col gap-6 p-6 max-w-4xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-mono text-sm font-semibold tracking-wider uppercase">Mission Queue</h1>
          <p className="font-mono text-[9px] text-muted-foreground/50 mt-0.5">
            {missions.filter(m => m.status === "queued").length} queued ·{" "}
            {missions.filter(m => m.status === "running").length} running ·{" "}
            {missions.filter(m => m.status === "done").length} done
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={refresh} className="text-muted-foreground hover:text-foreground transition-colors">
            <RefreshCw size={13} />
          </button>
          <button
            onClick={() => setShowForm(v => !v)}
            className="font-mono text-[9px] px-3 py-1.5 border border-border hover:border-foreground/40 text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1.5"
          >
            <Plus size={11} /> New Mission
          </button>
        </div>
      </div>

      {/* Create form */}
      {showForm && (
        <div className="border border-border p-4 flex flex-col gap-3">
          <div className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">New Mission</div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1">
              <label className="font-mono text-[8px] text-muted-foreground/50">Robot</label>
              <select
                value={form.robot_id}
                onChange={e => setForm(f => ({ ...f, robot_id: e.target.value }))}
                className="bg-background border border-border font-mono text-[9px] text-foreground px-2 py-1.5"
              >
                <option value="">select robot…</option>
                {robots.map(r => <option key={r.robot_id} value={r.robot_id}>{r.name}</option>)}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="font-mono text-[8px] text-muted-foreground/50">Scene</label>
              <select
                value={form.scene}
                onChange={e => setForm(f => ({ ...f, scene: e.target.value }))}
                className="bg-background border border-border font-mono text-[9px] text-foreground px-2 py-1.5"
              >
                {HOSPITAL_SCENES.map(s => <option key={s} value={s}>{s.replace("hospital_", "").replace(/_/g, " ")}</option>)}
              </select>
            </div>
            <div className="flex flex-col gap-1 col-span-2">
              <label className="font-mono text-[8px] text-muted-foreground/50">Goal description</label>
              <input
                value={form.goal}
                onChange={e => setForm(f => ({ ...f, goal: e.target.value }))}
                placeholder="Navigate to reception desk…"
                className="bg-background border border-border font-mono text-[9px] text-foreground px-2 py-1.5 placeholder:text-muted-foreground/20"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="font-mono text-[8px] text-muted-foreground/50">Priority (0=high)</label>
              <input
                type="number" min={0} max={9}
                value={form.priority}
                onChange={e => setForm(f => ({ ...f, priority: parseInt(e.target.value) || 5 }))}
                className="bg-background border border-border font-mono text-[9px] text-foreground px-2 py-1.5 w-20"
              />
            </div>
          </div>
          <div className="flex gap-2 pt-1">
            <button
              onClick={handleCreate}
              disabled={submitting || !form.robot_id}
              className="font-mono text-[9px] px-4 py-1.5 border border-green-500/40 text-green-400 hover:border-green-500 transition-colors disabled:opacity-30"
            >
              {submitting ? "Queuing…" : "Queue Mission"}
            </button>
            <button
              onClick={() => setShowForm(false)}
              className="font-mono text-[9px] px-3 py-1.5 border border-border text-muted-foreground hover:border-foreground/30 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Mission table */}
      {loading ? (
        <div className="font-mono text-[10px] text-muted-foreground/30">Loading…</div>
      ) : missions.length === 0 ? (
        <div className="font-mono text-[10px] text-muted-foreground/30">No missions yet. Create one above.</div>
      ) : (
        <div className="flex flex-col gap-0.5">
          <div className="grid grid-cols-[80px_1fr_100px_70px_70px_70px_32px] gap-2 font-mono text-[8px] text-muted-foreground/40 uppercase tracking-wider px-2 py-1">
            <span>ID</span>
            <span>Robot · Scene</span>
            <span>Status</span>
            <span>Created</span>
            <span>Started</span>
            <span>Finished</span>
            <span />
          </div>
          {missions.map(m => (
            <div key={m.mission_id}
              className="grid grid-cols-[80px_1fr_100px_70px_70px_70px_32px] gap-2 items-center px-2 py-1.5 border border-border hover:bg-foreground/3 font-mono text-[9px]">
              <span className="text-muted-foreground/50 font-mono">{m.mission_id}</span>
              <div className="flex flex-col min-w-0">
                <span className="text-foreground truncate">{robots.find(r => r.robot_id === m.robot_id)?.name ?? m.robot_id}</span>
                <span className="text-muted-foreground/50 text-[8px] truncate">{m.scene.replace("hospital_", "").replace(/_/g, " ")}</span>
              </div>
              <span className={`text-[8px] px-1 border self-start ${STATUS_STYLE[m.status] ?? ""}`}>
                {m.status}
              </span>
              <span className="text-muted-foreground/40">{fmt(m.created_at)}</span>
              <span className="text-muted-foreground/40">{fmt(m.started_at)}</span>
              <span className="text-muted-foreground/40">{fmt(m.finished_at)}</span>
              {["queued", "dispatching", "running"].includes(m.status) ? (
                <button onClick={() => handleCancel(m.mission_id)}
                  className="text-muted-foreground/30 hover:text-red-400 transition-colors">
                  <X size={10} />
                </button>
              ) : <span />}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
