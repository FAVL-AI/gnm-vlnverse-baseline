"use client";

import type { CommissioningState } from "@/lib/api";
import type { TelemetryData } from "@/hooks/useTelemetry";

interface Props {
  telemetry: TelemetryData | null;
  state: CommissioningState;
}

function VelBar({ label, value, max = 0.5 }: { label: string; value: number; max?: number }) {
  const pct = Math.min(Math.abs(value) / max, 1) * 100;
  const pos = value >= 0;
  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex justify-between font-mono text-[8px] text-muted-foreground">
        <span>{label}</span>
        <span className={value !== 0 ? (pos ? "text-green-400" : "text-amber-400") : "text-muted-foreground/30"}>
          {value >= 0 ? "+" : ""}{value.toFixed(3)} m/s
        </span>
      </div>
      <div className="h-1 bg-border rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-150 ${pos ? "bg-green-500" : "bg-amber-400"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export function CmdVelPreview({ telemetry: t, state }: Props) {
  const isLive = state === "RELAY_ENABLED";
  const hasData = !!t;

  const vx = t?.cmd_vel?.vx ?? 0;
  const vy = t?.cmd_vel?.vy ?? 0;
  const wz = t?.cmd_vel?.wz ?? 0;
  const speed = Math.sqrt(vx * vx + vy * vy);

  return (
    <div className="flex flex-col gap-3">
      {/* Live/preview badge */}
      <div className="flex items-center justify-between">
        <div className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">
          cmd_vel_safe
        </div>
        <span className={`font-mono text-[8px] px-2 py-0.5 border font-semibold tracking-wider
          ${isLive
            ? "border-red-500/60 text-red-400 animate-pulse"
            : "border-border text-muted-foreground/30"}`}>
          {isLive ? "LIVE · FORWARDING" : "PREVIEW ONLY"}
        </span>
      </div>

      {!hasData ? (
        <div className="font-mono text-[9px] text-muted-foreground/20">Waiting for telemetry…</div>
      ) : (
        <>
          <div className="flex flex-col gap-2">
            <VelBar label="vx (forward)" value={vx} max={0.5} />
            <VelBar label="vy (lateral)" value={vy} max={0.5} />
            <VelBar label="ωz (rotation)" value={wz} max={1.0} />
          </div>

          <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 font-mono text-[8px] border-t border-border pt-2">
            <span className="text-muted-foreground/50">speed</span>
            <span className={speed > 0.01 ? "text-green-400" : "text-muted-foreground/30"}>
              {speed.toFixed(3)} m/s
            </span>
            <span className="text-muted-foreground/50">zone</span>
            <span className={
              t.zone === "RED" ? "text-red-400" :
              t.zone === "AMBER" ? "text-amber-400" : "text-green-400"
            }>{t.zone}</span>
            <span className="text-muted-foreground/50">risk</span>
            <span className="text-foreground/70">{(t.risk * 100).toFixed(0)}%</span>
            <span className="text-muted-foreground/50">CBF</span>
            <span className={t.intervention_active ? "text-red-400 font-semibold" : "text-muted-foreground/30"}>
              {t.intervention_active ? "ACTIVE" : "inactive"}
            </span>
          </div>

          {isLive && (
            <div className="font-mono text-[8px] text-red-400/70 border border-red-500/30 px-2 py-1.5 leading-relaxed">
              ⚠ Commands are being forwarded to the robot.<br />
              E-STOP immediately if behaviour is unexpected.
            </div>
          )}

          {!isLive && state !== "DISARMED" && (
            <div className="font-mono text-[8px] text-muted-foreground/40 border border-border px-2 py-1">
              Showing what FleetSafe would send. Not forwarding.
            </div>
          )}
        </>
      )}
    </div>
  );
}
