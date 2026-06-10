"use client";

import { useTelemetry } from "@/hooks/useTelemetry";

const ZONE_STYLE = {
  GREEN: { dot: "bg-green-500",  text: "text-green-400",  fill: "#22c55e" },
  AMBER: { dot: "bg-amber-400",  text: "text-amber-400",  fill: "#f59e0b" },
  RED:   { dot: "bg-red-500",    text: "text-red-400",    fill: "#ef4444" },
};

function RiskBar({ label, value, color = "bg-foreground/40" }: { label: string; value: number; color?: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex justify-between font-mono text-[9px] text-muted-foreground">
        <span>{label}</span>
        <span>{(value * 100).toFixed(0)}%</span>
      </div>
      <div className="h-0.5 bg-border rounded-full overflow-hidden">
        <div className={`h-full ${color} transition-all duration-200`}
          style={{ width: `${Math.min(value * 100, 100)}%` }} />
      </div>
    </div>
  );
}

function CmdVelCompass({ vx, vy, wz }: { vx: number; vy: number; wz: number }) {
  const S = 44, cx = 22, cy = 22, r = 17;
  const angle = Math.atan2(-vy, vx);
  const speed = Math.sqrt(vx * vx + vy * vy);
  const len   = r * Math.min(speed / 0.35, 1);
  const ax = cx + len * Math.cos(angle);
  const ay = cy + len * Math.sin(angle);
  const hasVel = speed > 0.005;
  const hasRot = Math.abs(wz) > 0.005;

  return (
    <svg width={S} height={S} className="shrink-0">
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="currentColor" strokeWidth={0.5} className="text-border" />
      <line x1={cx} y1={cy-r} x2={cx} y2={cy+r} stroke="currentColor" strokeWidth={0.4} className="text-border" opacity={0.4} />
      <line x1={cx-r} y1={cy} x2={cx+r} y2={cy} stroke="currentColor" strokeWidth={0.4} className="text-border" opacity={0.4} />
      {hasVel && <>
        <line x1={cx} y1={cy} x2={ax} y2={ay} stroke="#22c55e" strokeWidth={1.5} />
        <circle cx={ax} cy={ay} r={1.5} fill="#22c55e" />
      </>}
      {hasRot && (
        <path
          d={wz > 0
            ? `M ${cx+r-4} ${cy} A ${r-4} ${r-4} 0 0 1 ${cx} ${cy-r+4}`
            : `M ${cx} ${cy-r+4} A ${r-4} ${r-4} 0 0 1 ${cx+r-4} ${cy}`}
          fill="none" stroke="#f59e0b" strokeWidth={1} opacity={0.7}
        />
      )}
      {!hasVel && !hasRot && (
        <circle cx={cx} cy={cy} r={2} fill="currentColor" className="text-border" />
      )}
    </svg>
  );
}

function BatteryIcon({ pct, charging }: { pct: number | null; charging: boolean }) {
  if (pct == null) return <span className="text-muted-foreground/30 font-mono text-[9px]">n/a</span>;
  const colour = pct > 60 ? "text-green-500" : pct > 25 ? "text-amber-400" : "text-red-400";
  return (
    <span className={`font-mono text-[10px] ${colour} flex items-center gap-1`}>
      {charging && <span className="text-amber-300">⚡</span>}
      {pct.toFixed(0)}%
    </span>
  );
}

export function TelemetryPanel({ compact = false }: { compact?: boolean }) {
  const t = useTelemetry();

  if (!t) {
    return (
      <div className="border border-border bg-card px-4 py-2 font-mono text-[10px] text-muted-foreground/30 flex items-center gap-2">
        <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/20 animate-pulse" />
        Connecting to telemetry…
      </div>
    );
  }

  const zs = ZONE_STYLE[t.zone];

  /* ── Compact bar (inside viewport toolbar) ────────────────────── */
  if (compact) {
    return (
      <div className="flex items-center gap-3 font-mono text-[10px] flex-wrap">
        <span className={`flex items-center gap-1 ${zs.text} font-semibold`}>
          <span className={`w-1.5 h-1.5 rounded-full ${zs.dot} ${t.zone==="RED"?"animate-pulse":""}`} />
          {t.zone}
        </span>
        <span className="text-muted-foreground">risk {(t.risk*100).toFixed(0)}%</span>
        <span className="text-muted-foreground">{t.detection_count} det</span>
        <span className="text-muted-foreground">{t.latency_ms.toFixed(0)} ms</span>
        {t.sim_fps > 0 && <span className="text-muted-foreground">{t.sim_fps.toFixed(0)} fps</span>}
        {t.intervention_active && <span className="text-red-400 font-semibold animate-pulse">CBF ACTIVE</span>}
        <span className={`ml-auto text-[9px] px-1 border ${t.source==="ros2" ? "border-green-500/40 text-green-500" : "border-border text-muted-foreground/30"}`}>
          {t.source}
        </span>
      </div>
    );
  }

  /* ── Full panel ────────────────────────────────────────────────── */
  const riskColour = t.risk > 0.6 ? "bg-red-500" : t.risk > 0.3 ? "bg-amber-400" : "bg-green-500";

  return (
    <div className="bg-card font-mono text-xs flex flex-col gap-3 p-4">

      {/* Row 1: zone + source badge + intervention */}
      <div className="flex items-center justify-between gap-2">
        <span className={`flex items-center gap-2 ${zs.text} font-semibold tracking-wider uppercase`}>
          <span className={`w-2.5 h-2.5 rounded-full ${zs.dot} ${t.zone==="RED"?"animate-pulse":""}`} />
          {t.zone}
        </span>
        <div className="flex items-center gap-2 text-[9px]">
          {t.intervention_active && (
            <span className="text-red-400 font-semibold animate-pulse tracking-wider">CBF ACTIVE</span>
          )}
          <span className={`px-1.5 py-0.5 border ${t.source==="ros2" ? "border-green-500/40 text-green-500" : "border-border text-muted-foreground/30"}`}>
            {t.source}
          </span>
        </div>
      </div>

      {/* Row 2: risk bars */}
      <div className="flex flex-col gap-1.5">
        <RiskBar label="risk"      value={t.risk}          color={riskColour} />
        <RiskBar label="crowding"  value={t.crowding_risk}  color="bg-foreground/40" />
        <RiskBar label="occlusion" value={t.occlusion_risk} color="bg-foreground/30" />
      </div>

      {/* Row 3: cmd_vel + odom + battery */}
      <div className="flex items-start gap-3">
        <CmdVelCompass vx={t.cmd_vel?.vx ?? 0} vy={t.cmd_vel?.vy ?? 0} wz={t.cmd_vel?.wz ?? 0} />
        <div className="flex-1 flex flex-col gap-1 text-[9px] text-muted-foreground">
          <div className="flex gap-2">
            <span>vx <span className="text-foreground">{(t.cmd_vel?.vx ?? 0).toFixed(2)}</span></span>
            <span>vy <span className="text-foreground">{(t.cmd_vel?.vy ?? 0).toFixed(2)}</span></span>
            <span>ωz <span className="text-foreground">{(t.cmd_vel?.wz ?? 0).toFixed(2)}</span></span>
          </div>
          <div className="flex gap-2">
            <span>x <span className="text-foreground">{(t.odom?.x ?? 0).toFixed(2)}</span></span>
            <span>y <span className="text-foreground">{(t.odom?.y ?? 0).toFixed(2)}</span></span>
            <span>θ <span className="text-foreground">{((t.odom?.heading ?? 0) * 180 / Math.PI).toFixed(0)}°</span></span>
          </div>
        </div>
        <div className="flex flex-col items-end gap-1 text-[9px] text-muted-foreground shrink-0">
          <div className="flex items-center gap-1">
            <span>bat</span>
            <BatteryIcon pct={t.battery_pct} charging={t.battery_charging} />
          </div>
          {t.sim_fps > 0 && <span><span className="text-foreground">{t.sim_fps.toFixed(0)}</span> fps</span>}
        </div>
      </div>

      {/* Row 4: counts + latency */}
      <div className="flex items-center gap-4 text-[9px] text-muted-foreground border-t border-border pt-2">
        <span>det <span className="text-foreground">{t.detection_count}</span></span>
        <span>tracked <span className="text-foreground">{t.tracked_count}</span></span>
        <span className="ml-auto">
          infer <span className="text-foreground">{t.latency_ms.toFixed(1)}</span> ms
          {t.perception_latency_ms > 0 && (
            <> · perc <span className="text-foreground">{t.perception_latency_ms.toFixed(1)}</span> ms</>
          )}
        </span>
      </div>

      {/* Row 5: tracked agents mini-list (live ROS2 only) */}
      {t.source === "ros2" && t.tracks.length > 0 && (
        <div className="border-t border-border pt-2 flex flex-col gap-0.5">
          <div className="text-[9px] text-muted-foreground/50 uppercase tracking-wider mb-1">Tracks</div>
          {t.tracks.slice(0, 5).map(tr => (
            <div key={tr.id} className="flex items-center gap-2 text-[9px] text-muted-foreground">
              <span className="w-3 text-right text-foreground/60">{tr.id}</span>
              <span>({tr.x.toFixed(1)}, {tr.y.toFixed(1)})</span>
              <span className="text-muted-foreground/40">
                v={Math.sqrt(tr.vx**2 + tr.vy**2).toFixed(2)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
