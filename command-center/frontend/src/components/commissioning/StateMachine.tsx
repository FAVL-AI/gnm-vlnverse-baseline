"use client";

import type { CommissioningState } from "@/lib/api";

const STATES: { id: CommissioningState; label: string; desc: string }[] = [
  { id: "DISARMED",        label: "DISARMED",        desc: "Platform idle. No robot connected." },
  { id: "MONITOR",         label: "MONITOR ONLY",    desc: "Receiving telemetry. Zero output." },
  { id: "ESTOP_VALIDATED", label: "E-STOP VALIDATED", desc: "Emergency stop confirmed functional." },
  { id: "ARMED",           label: "ARMED",           desc: "FleetSafe active. Commands in preview." },
  { id: "RELAY_ENABLED",   label: "RELAY ENABLED",   desc: "cmd_vel_safe forwarding to robot." },
];

const STATE_COLOR: Record<CommissioningState, { dot: string; text: string; ring: string }> = {
  DISARMED:        { dot: "bg-muted-foreground/30", text: "text-muted-foreground/50",  ring: "border-border" },
  MONITOR:         { dot: "bg-blue-400",             text: "text-blue-400",             ring: "border-blue-500/30" },
  ESTOP_VALIDATED: { dot: "bg-amber-400",            text: "text-amber-400",            ring: "border-amber-400/40" },
  ARMED:           { dot: "bg-green-400",            text: "text-green-400",            ring: "border-green-500/40" },
  RELAY_ENABLED:   { dot: "bg-red-400 animate-pulse", text: "text-red-400",             ring: "border-red-500/60" },
};

interface Props {
  current: CommissioningState;
}

export function StateMachine({ current }: Props) {
  const currentIdx = STATES.findIndex(s => s.id === current);

  return (
    <div className="flex flex-col gap-0">
      {STATES.map((s, i) => {
        const active  = s.id === current;
        const passed  = i < currentIdx;
        const pending = i > currentIdx;
        const col     = STATE_COLOR[s.id];

        return (
          <div key={s.id} className="flex items-start gap-3">
            {/* Connector line column */}
            <div className="flex flex-col items-center w-5 shrink-0">
              <div className={`w-2 h-2 rounded-full mt-1 shrink-0 ${
                active  ? col.dot :
                passed  ? "bg-foreground/30" :
                          "bg-border"
              }`} />
              {i < STATES.length - 1 && (
                <div className={`w-px flex-1 my-0.5 ${passed ? "bg-foreground/20" : "bg-border/50"}`}
                  style={{ minHeight: 20 }} />
              )}
            </div>

            {/* Content */}
            <div className={`pb-4 flex-1 ${pending ? "opacity-30" : ""}`}>
              <div className={`font-mono text-[10px] font-semibold tracking-wider ${
                active ? col.text : passed ? "text-foreground/40" : "text-muted-foreground/30"
              }`}>
                {s.label}
                {active && (
                  <span className={`ml-2 text-[8px] px-1 border ${col.ring}`}>CURRENT</span>
                )}
              </div>
              {active && (
                <div className="font-mono text-[9px] text-muted-foreground/50 mt-0.5">{s.desc}</div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
