"use client";

import { Hash, Video, VideoOff } from "lucide-react";
import type { RealSession } from "@/lib/api";

const BAG_TOPICS = [
  "/camera/color/image_raw",
  "/camera/depth/image_raw",
  "/camera/color/camera_info",
  "/odom_raw",
  "/scan0",
  "/battery",
  "/cmd_vel_raw",
  "/cmd_vel_safe",
  "/cmd_vel",
  "/fleetsafe/zone",
  "/fleetsafe/social_risk",
  "/fleetsafe/detections",
  "/fleetsafe/tracks",
  "/fleetsafe/latency",
];

interface Props {
  session: RealSession | null;
  robotId: string;
  onStart: (robotId: string) => void;
  onStop:  (sessionId: string) => void;
  busy: boolean;
}

export function SessionCapture({ session, robotId, onStart, onStop, busy }: Props) {
  const recording = session != null && session.stopped_at == null;
  const stopped   = session != null && session.stopped_at != null;

  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <span className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">
          ROS2 Bag Session
        </span>
        {recording && (
          <span className="font-mono text-[8px] text-red-400 border border-red-500/40 px-1.5 py-0.5 animate-pulse">
            ● REC
          </span>
        )}
        {stopped && session.evidence_id && (
          <span className="font-mono text-[8px] text-green-400/70 border border-green-500/30 px-1.5 py-0.5">
            ✓ EVIDENCE
          </span>
        )}
      </div>

      {/* Session metadata */}
      {session && (
        <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 font-mono text-[8px] mb-3">
          <span className="text-muted-foreground/40">Session</span>
          <span className="text-foreground/50 truncate">{session.session_id}</span>
          <span className="text-muted-foreground/40">Topics</span>
          <span className="text-foreground/50">{session.n_topics} captured</span>
          {session.duration_s != null && (
            <>
              <span className="text-muted-foreground/40">Duration</span>
              <span className="text-foreground/50">{session.duration_s.toFixed(0)}s</span>
            </>
          )}
          {session.sha256 && (
            <>
              <span className="text-muted-foreground/40">SHA256</span>
              <span className="text-green-400/50 flex items-center gap-1">
                <Hash size={7} /> {session.sha256.slice(0, 12)}…
              </span>
            </>
          )}
          {session.evidence_id && (
            <>
              <span className="text-muted-foreground/40">Evidence ID</span>
              <span className="text-green-400/40">{session.evidence_id}</span>
            </>
          )}
        </div>
      )}

      {/* Topic list (collapsed) */}
      {!recording && !stopped && (
        <div className="mb-3 grid grid-cols-2 gap-x-2 gap-y-0.5">
          {BAG_TOPICS.map(t => (
            <div key={t} className="font-mono text-[7px] text-muted-foreground/30 truncate">{t}</div>
          ))}
        </div>
      )}

      <div className="flex gap-2">
        {!recording ? (
          <button
            onClick={() => onStart(robotId)}
            disabled={busy}
            className="flex items-center gap-1 font-mono text-[8px] px-2 py-1 border border-border text-muted-foreground/50 hover:text-foreground hover:border-foreground/40 transition-colors disabled:opacity-30"
          >
            <Video size={9} /> Start Recording
          </button>
        ) : (
          <button
            onClick={() => onStop(session!.session_id)}
            disabled={busy}
            className="flex items-center gap-1 font-mono text-[8px] px-2 py-1 border border-red-500/40 text-red-400 hover:bg-red-500/10 transition-colors disabled:opacity-30"
          >
            <VideoOff size={9} /> Stop + Hash
          </button>
        )}
      </div>

      {stopped && !session.sha256 && (
        <div className="mt-1.5 font-mono text-[7px] text-amber-400/50">
          Session stopped — evidence hash pending
        </div>
      )}
    </div>
  );
}
