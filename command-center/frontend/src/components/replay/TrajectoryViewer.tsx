"use client";

import { useMemo } from "react";
import type { TrajPoint, SafetyEvent, ActionRow } from "@/lib/api";

const W = 340;
const H = 280;
const PAD = 24;

function worldToSvg(
  xs: number[], ys: number[],
  px: number, py: number,
): [number, number] {
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const rangeX = maxX - minX || 1;
  const rangeY = maxY - minY || 1;
  const scale = Math.min((W - PAD * 2) / rangeX, (H - PAD * 2) / rangeY);
  const offX = PAD + ((W - PAD * 2) - rangeX * scale) / 2;
  const offY = PAD + ((H - PAD * 2) - rangeY * scale) / 2;
  return [
    offX + (px - minX) * scale,
    H - (offY + (py - minY) * scale),
  ];
}

const EVENT_COLOR: Record<string, string> = {
  intervention: "#f59e0b",
  near_miss:    "#fb923c",
  collision:    "#ef4444",
};

interface Props {
  trajectory: TrajPoint[];
  events: SafetyEvent[];
  actions?: ActionRow[];
  currentStep?: number;
  color?: string;
  label?: string;
}

export function TrajectoryViewer({
  trajectory,
  events,
  currentStep,
  color = "#22c55e",
  label,
}: Props) {
  const { pts, eventPts, robotPt, startPt, goalPt } = useMemo(() => {
    if (!trajectory.length) return { pts: [], eventPts: [], robotPt: null, startPt: null, goalPt: null };

    const xs = trajectory.map(t => t.x);
    const ys = trajectory.map(t => t.y);
    const toSvg = (x: number, y: number) => worldToSvg(xs, ys, x, y);

    const pts = trajectory.map(t => toSvg(t.x, t.y));

    const eventPts = events.map(ev => {
      const tp = trajectory[Math.min(ev.step, trajectory.length - 1)];
      return { ...toSvg(tp?.x ?? 0, tp?.y ?? 0), type: ev.type };
    });

    const idx = currentStep !== undefined
      ? Math.min(currentStep, trajectory.length - 1)
      : trajectory.length - 1;
    const robotPt = toSvg(trajectory[idx].x, trajectory[idx].y);
    const startPt = toSvg(trajectory[0].x, trajectory[0].y);
    const last = trajectory[trajectory.length - 1];
    const goalPt = toSvg(last.x, last.y);

    return { pts, eventPts, robotPt, startPt, goalPt };
  }, [trajectory, events, currentStep]);

  if (!trajectory.length) {
    return (
      <div className="flex items-center justify-center bg-card border border-border font-mono text-[9px] text-muted-foreground/30"
        style={{ width: W, height: H }}>
        no trajectory data
      </div>
    );
  }

  const pathD = pts.map((p, i) => `${i === 0 ? "M" : "L"} ${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(" ");

  return (
    <div className="relative">
      {label && (
        <div className="absolute top-1 left-2 font-mono text-[9px] text-muted-foreground/50 z-10">{label}</div>
      )}
      <svg width={W} height={H} className="bg-card border border-border block">
        {/* Grid */}
        {[0.25, 0.5, 0.75].map(f => (
          <g key={f} className="text-border">
            <line x1={PAD} y1={H * f} x2={W - PAD} y2={H * f} stroke="currentColor" strokeWidth={0.4} opacity={0.4} />
            <line x1={W * f} y1={PAD} x2={W * f} y2={H - PAD} stroke="currentColor" strokeWidth={0.4} opacity={0.4} />
          </g>
        ))}

        {/* Full trajectory (faint) */}
        <path d={pathD} fill="none" stroke={color} strokeWidth={1} opacity={0.25} />

        {/* Replayed portion */}
        {currentStep !== undefined && pts.length > 0 && (
          <path
            d={pts.slice(0, currentStep + 1).map((p, i) =>
              `${i === 0 ? "M" : "L"} ${p[0].toFixed(1)} ${p[1].toFixed(1)}`
            ).join(" ")}
            fill="none" stroke={color} strokeWidth={1.5} opacity={0.9}
          />
        )}

        {/* Event markers */}
        {eventPts.map((ep, i) => (
          <circle key={i} cx={ep[0]} cy={ep[1]} r={3.5}
            fill={EVENT_COLOR[ep.type] ?? "#94a3b8"}
            stroke="black" strokeWidth={0.5} opacity={0.85} />
        ))}

        {/* Start */}
        {startPt && (
          <circle cx={startPt[0]} cy={startPt[1]} r={4}
            fill="none" stroke="#6366f1" strokeWidth={1.5} />
        )}

        {/* Robot position */}
        {robotPt && (
          <circle cx={robotPt[0]} cy={robotPt[1]} r={5}
            fill={color} stroke="black" strokeWidth={0.5} opacity={0.9} />
        )}
      </svg>

      {/* Legend */}
      <div className="flex items-center gap-3 mt-1 font-mono text-[8px] text-muted-foreground/50">
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full border border-indigo-500 inline-block" /> start
        </span>
        {Object.entries(EVENT_COLOR).map(([k, c]) => (
          <span key={k} className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full inline-block" style={{ background: c }} /> {k.replace("_", " ")}
          </span>
        ))}
      </div>
    </div>
  );
}
