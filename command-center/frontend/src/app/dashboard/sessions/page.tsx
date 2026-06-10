"use client";

import { useCallback, useEffect, useState } from "react";
import { sessionApi, fleetApi, type RecordingSession, type RobotSnapshot } from "@/lib/api";
import { Video, VideoOff, RefreshCw, Play } from "lucide-react";
import Link from "next/link";

function fmt(ts: number | null): string {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString("en-US", {
    month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hour12: false,
  });
}

function duration(s: RecordingSession): string {
  if (!s.stopped_at) return "recording…";
  const secs = Math.round(s.stopped_at - s.started_at);
  if (secs < 60) return `${secs}s`;
  return `${Math.floor(secs / 60)}m ${secs % 60}s`;
}

export default function SessionsPage() {
  const [sessions, setSessions] = useState<RecordingSession[]>([]);
  const [robots, setRobots] = useState<RobotSnapshot[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedRobot, setSelectedRobot] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => {
    sessionApi.list().then(setSessions).catch(() => {});
  }, []);

  useEffect(() => {
    fleetApi.robots().then(r => {
      setRobots(r);
      if (r.length && !selectedRobot) setSelectedRobot(r[0].robot_id);
    }).catch(() => {});
    sessionApi.list()
      .then(setSessions)
      .catch(() => {})
      .finally(() => setLoading(false));
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, [refresh, selectedRobot]);

  const activeSession = sessions.find(s => s.is_active && s.robot_id === selectedRobot);

  async function toggleRecording() {
    setBusy(true);
    try {
      if (activeSession) {
        await sessionApi.stop(activeSession.session_id);
      } else if (selectedRobot) {
        await sessionApi.start(selectedRobot);
      }
      await refresh();
    } catch { /* ignore */ }
    finally { setBusy(false); }
  }

  return (
    <div className="flex flex-col gap-6 p-6 max-w-3xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-mono text-sm font-semibold tracking-wider uppercase">Session Recorder</h1>
          <p className="font-mono text-[9px] text-muted-foreground/50 mt-0.5">
            Record telemetry, trajectories, and safety events. Replay later.
          </p>
        </div>
        <button onClick={refresh} className="text-muted-foreground hover:text-foreground transition-colors">
          <RefreshCw size={13} />
        </button>
      </div>

      {/* Recording control */}
      <div className="border border-border p-4 flex flex-col gap-4">
        <div className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">Record</div>
        <div className="flex items-end gap-3 flex-wrap">
          <div className="flex flex-col gap-1">
            <label className="font-mono text-[8px] text-muted-foreground/50">Robot</label>
            <select
              value={selectedRobot}
              onChange={e => setSelectedRobot(e.target.value)}
              disabled={!!activeSession}
              className="bg-background border border-border font-mono text-[9px] text-foreground px-2 py-1.5 disabled:opacity-50"
            >
              {robots.map(r => <option key={r.robot_id} value={r.robot_id}>{r.name}</option>)}
              {!robots.length && <option value="">No robots online</option>}
            </select>
          </div>

          <button
            onClick={toggleRecording}
            disabled={busy || !selectedRobot}
            className={`flex items-center gap-2 px-4 py-2 border font-mono text-[9px] transition-colors disabled:opacity-30
              ${activeSession
                ? "border-red-500/50 text-red-400 hover:border-red-500 hover:text-red-300"
                : "border-green-500/40 text-green-400 hover:border-green-500"}`}
          >
            {activeSession ? <VideoOff size={12} /> : <Video size={12} />}
            {activeSession ? "Stop Recording" : "Start Recording"}
          </button>
        </div>

        {activeSession && (
          <div className="flex items-center gap-3 font-mono text-[9px] text-green-400 animate-pulse">
            <span className="w-2 h-2 rounded-full bg-red-500" />
            Recording {activeSession.session_id} ·{" "}
            {activeSession.n_frames} frames ·{" "}
            {activeSession.n_events} events
          </div>
        )}
      </div>

      {/* Session list */}
      <div className="border border-border p-4 flex flex-col gap-3">
        <div className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">Sessions</div>
        {loading ? (
          <div className="font-mono text-[9px] text-muted-foreground/30">Loading…</div>
        ) : sessions.length === 0 ? (
          <div className="font-mono text-[9px] text-muted-foreground/30">
            No recorded sessions yet. Start a recording above.
          </div>
        ) : (
          <div className="flex flex-col gap-0.5">
            <div className="grid grid-cols-[80px_1fr_70px_70px_60px_60px_44px] gap-2 font-mono text-[8px] text-muted-foreground/40 uppercase tracking-wider px-2 py-1">
              <span>ID</span>
              <span>Robot</span>
              <span>Started</span>
              <span>Duration</span>
              <span>Frames</span>
              <span>Events</span>
              <span />
            </div>
            {sessions.map(s => (
              <div key={s.session_id}
                className="grid grid-cols-[80px_1fr_70px_70px_60px_60px_44px] gap-2 items-center px-2 py-1.5 border border-border font-mono text-[9px]">
                <span className="text-muted-foreground/60">{s.session_id}</span>
                <span className="text-foreground/70 truncate">
                  {robots.find(r => r.robot_id === s.robot_id)?.name ?? s.robot_id}
                </span>
                <span className="text-muted-foreground/40">{fmt(s.started_at)}</span>
                <span className={`${s.is_active ? "text-red-400 animate-pulse" : "text-muted-foreground/40"}`}>
                  {duration(s)}
                </span>
                <span className="text-muted-foreground/40">{s.n_frames}</span>
                <span className="text-muted-foreground/40">{s.n_events}</span>
                {!s.is_active && s.n_frames > 0 ? (
                  <Link
                    href={`/dashboard/replay?session=${s.session_id}`}
                    className="flex items-center justify-center text-muted-foreground/40 hover:text-green-400 transition-colors"
                    title="Replay session"
                  >
                    <Play size={10} />
                  </Link>
                ) : <span />}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Info */}
      <div className="font-mono text-[9px] text-muted-foreground/30 border-t border-border pt-3">
        Sessions are stored in <code className="text-muted-foreground/50">command-center/recordings/</code>.
        Telemetry recorded at 10 Hz. Replaying a session opens the standard replay browser with trajectory extracted from odom data.
      </div>
    </div>
  );
}
