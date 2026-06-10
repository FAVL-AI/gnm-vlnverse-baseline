"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Play, Pause, SkipBack, SkipForward, ChevronFirst, ChevronLast } from "lucide-react";
import type { SafetyEvent } from "@/lib/api";

const EVENT_COLOR: Record<string, string> = {
  intervention: "#f59e0b",
  near_miss:    "#fb923c",
  collision:    "#ef4444",
};

const SPEEDS = [0.25, 0.5, 1, 2, 4];

interface Props {
  totalSteps: number;
  currentStep: number;
  events: SafetyEvent[];
  onSeek: (step: number) => void;
  onPlay?: () => void;
  onPause?: () => void;
}

export function ReplayTimeline({
  totalSteps,
  currentStep,
  events,
  onSeek,
}: Props) {
  const [playing, setPlaying] = useState(false);
  const [speedIdx, setSpeedIdx] = useState(2);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const stepRef = useRef(currentStep);
  stepRef.current = currentStep;

  const speed = SPEEDS[speedIdx];

  const stop = useCallback(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    intervalRef.current = null;
  }, []);

  const play = useCallback(() => {
    stop();
    intervalRef.current = setInterval(() => {
      const next = stepRef.current + 1;
      if (next >= totalSteps) {
        setPlaying(false);
        stop();
        return;
      }
      onSeek(next);
    }, 100 / speed);
    setPlaying(true);
  }, [stop, totalSteps, onSeek, speed]);

  useEffect(() => {
    if (playing) play();
    return stop;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, speed]);

  useEffect(() => () => stop(), [stop]);

  function handleTrackClick(e: React.MouseEvent<HTMLDivElement>) {
    const rect = trackRef.current?.getBoundingClientRect();
    if (!rect) return;
    const frac = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const step = Math.round(frac * (totalSteps - 1));
    onSeek(step);
  }

  const pct = totalSteps > 1 ? (currentStep / (totalSteps - 1)) * 100 : 0;

  return (
    <div className="flex flex-col gap-2 bg-card border border-border p-3 font-mono">
      {/* Track bar */}
      <div
        ref={trackRef}
        className="relative h-6 bg-background border border-border cursor-pointer"
        onClick={handleTrackClick}
      >
        {/* Event markers */}
        {events.map((ev, i) => {
          const x = totalSteps > 1 ? (ev.step / (totalSteps - 1)) * 100 : 0;
          return (
            <div
              key={i}
              title={`${ev.type} @ step ${ev.step}`}
              className="absolute top-0 bottom-0 w-px cursor-pointer"
              style={{ left: `${x}%`, background: EVENT_COLOR[ev.type] ?? "#94a3b8", opacity: 0.8 }}
            />
          );
        })}
        {/* Progress fill */}
        <div
          className="absolute top-0 left-0 h-full bg-foreground/10 transition-none pointer-events-none"
          style={{ width: `${pct}%` }}
        />
        {/* Playhead */}
        <div
          className="absolute top-0 w-0.5 h-full bg-foreground pointer-events-none"
          style={{ left: `${pct}%` }}
        />
      </div>

      {/* Controls row */}
      <div className="flex items-center gap-2 text-muted-foreground">
        <button title="Start" onClick={() => onSeek(0)}
          className="hover:text-foreground transition-colors">
          <ChevronFirst size={14} />
        </button>
        <button title="Step back" onClick={() => onSeek(Math.max(0, currentStep - 1))}
          className="hover:text-foreground transition-colors">
          <SkipBack size={14} />
        </button>
        <button
          title={playing ? "Pause" : "Play"}
          onClick={() => setPlaying(p => !p)}
          className="hover:text-foreground transition-colors"
        >
          {playing ? <Pause size={14} /> : <Play size={14} />}
        </button>
        <button title="Step forward" onClick={() => onSeek(Math.min(totalSteps - 1, currentStep + 1))}
          className="hover:text-foreground transition-colors">
          <SkipForward size={14} />
        </button>
        <button title="End" onClick={() => onSeek(totalSteps - 1)}
          className="hover:text-foreground transition-colors">
          <ChevronLast size={14} />
        </button>

        <span className="ml-auto text-[9px] text-muted-foreground/50">
          step <span className="text-foreground">{currentStep}</span> / {totalSteps - 1}
        </span>

        {/* Speed control */}
        <button
          className="text-[9px] px-1.5 py-0.5 border border-border hover:border-foreground/40 transition-colors"
          onClick={() => setSpeedIdx(i => (i + 1) % SPEEDS.length)}
        >
          {speed}×
        </button>
      </div>

      {/* Event legend */}
      {events.length > 0 && (
        <div className="flex items-center gap-3 text-[8px] text-muted-foreground/50">
          {Object.entries(EVENT_COLOR).map(([k, c]) => {
            const count = events.filter(ev => ev.type === k).length;
            if (!count) return null;
            return (
              <span key={k} className="flex items-center gap-1">
                <span className="w-2 h-px inline-block" style={{ background: c, height: 2 }} />
                {count} {k.replace("_", " ")}
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}
