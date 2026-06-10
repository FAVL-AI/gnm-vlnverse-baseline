"use client";

import { useRef, useEffect } from "react";
import type { FleetSafetyEvent } from "@/lib/api";

const TYPE_STYLE: Record<string, { bg: string; text: string; label: string }> = {
  intervention: { bg: "border-amber-400/30",  text: "text-amber-400",  label: "CBF"      },
  near_miss:    { bg: "border-orange-400/30", text: "text-orange-400", label: "NEAR MISS" },
  collision:    { bg: "border-red-500/40",    text: "text-red-400",    label: "COLLISION" },
  estop:        { bg: "border-red-600/50",    text: "text-red-300",    label: "E-STOP"   },
  zone_change:  { bg: "border-border",        text: "text-muted-foreground/60", label: "ZONE" },
};

function ts(unix: number): string {
  const d = new Date(unix * 1000);
  return d.toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

interface Props {
  events: FleetSafetyEvent[];
  maxVisible?: number;
  autoScroll?: boolean;
}

export function InterventionFeed({ events, maxVisible = 100, autoScroll = true }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (autoScroll) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [events.length, autoScroll]);

  const visible = events.slice(0, maxVisible);

  return (
    <div className="flex flex-col gap-0.5 overflow-y-auto font-mono">
      {visible.length === 0 && (
        <div className="text-[9px] text-muted-foreground/30 p-3">No events yet.</div>
      )}
      {[...visible].reverse().map((ev, i) => {
        const style = TYPE_STYLE[ev.event_type] ?? TYPE_STYLE.zone_change;
        return (
          <div key={ev.event_id ?? i}
            className={`flex items-start gap-2 px-3 py-1.5 border-l-2 ${style.bg} text-[9px]`}>
            <span className="text-muted-foreground/40 shrink-0 w-16">{ts(ev.timestamp)}</span>
            <span className={`${style.text} font-semibold shrink-0 w-16`}>{style.label}</span>
            <span className="text-muted-foreground/70 shrink-0 w-24 truncate">{ev.robot_id}</span>
            <span className="text-muted-foreground/50 flex-1">
              {ev.zone &&
                <span className={`mr-2 ${ev.zone === "RED" ? "text-red-400" : ev.zone === "AMBER" ? "text-amber-400" : "text-green-400"}`}>
                  {ev.zone}
                </span>}
              {ev.risk != null && `risk ${(ev.risk * 100).toFixed(0)}%`}
              {ev.min_dist_m != null && ` · dist ${ev.min_dist_m.toFixed(2)}m`}
              {ev.details?.from != null && ` ${ev.details.from}→${ev.details.to}`}
            </span>
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
