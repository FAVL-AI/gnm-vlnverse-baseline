"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import {
  Play, Square, RefreshCw, Wifi, WifiOff, Shield, Camera,
  Activity, Zap, AlertTriangle, CheckCircle, ChevronRight,
  Eye, Cpu, Layers, ArrowUp, ArrowDown, ArrowLeft, ArrowRight,
  CircleDot, OctagonX,
} from "lucide-react";
import { useDemoTelemetry, type DemoFrame, type DemoZone } from "@/hooks/useDemoTelemetry";
import { robotApi } from "@/lib/api";

// ── Constants ─────────────────────────────────────────────────────────────────

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const MODEL_META: Record<string, { label: string; color: string; arch: string; description: string }> = {
  gnm:   { label: "GNM",   color: "#60a5fa", arch: "CNN",         description: "Goal-directed navigation model. Predicts waypoints from camera + goal image." },
  vint:  { label: "ViNT",  color: "#f472b6", arch: "Transformer", description: "Vision Transformer backbone. Richer features, goal-conditioned waypoint prediction." },
  nomad: { label: "NoMaD", color: "#34d399", arch: "Diffusion",   description: "Exploration diffusion model. Does not commit to narrow paths — avoids naturally." },
};

const ZONE_COLOR: Record<DemoZone, string> = {
  GREEN: "#22c55e",
  AMBER: "#f59e0b",
  RED:   "#ef4444",
};

const ZONE_BG: Record<DemoZone, string> = {
  GREEN: "bg-green-500/10 border-green-500/30 text-green-400",
  AMBER: "bg-amber-500/10 border-amber-500/30 text-amber-400",
  RED:   "bg-red-500/10   border-red-500/30   text-red-400",
};

// ── Small utility components ──────────────────────────────────────────────────

function Pill({ label, value, unit, color, mono = true }:
  { label: string; value: string | number | null; unit?: string; color?: string; mono?: boolean }) {
  const val = value !== null && value !== undefined ? `${value}${unit ?? ""}` : "—";
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[9px] font-mono text-muted-foreground/60 uppercase tracking-wide">{label}</span>
      <span className={`${mono ? "font-mono" : ""} text-[13px] font-semibold`} style={color ? { color } : undefined}>{val}</span>
    </div>
  );
}

function ZoneBadge({ zone }: { zone: DemoZone }) {
  return (
    <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded border ${ZONE_BG[zone]}`}>
      {zone}
    </span>
  );
}

function CmdArrow({ label, vx, wz, color }: { label: string; vx: number; wz: number; color: string }) {
  const MAX_VX = 0.35;
  const MAX_WZ = 0.75;
  const barW = Math.min(1, Math.abs(vx) / MAX_VX) * 100;
  const barWz = Math.min(1, Math.abs(wz) / MAX_WZ) * 100;
  return (
    <div className="space-y-1.5">
      <span className="text-[10px] font-semibold text-muted-foreground/60 uppercase tracking-wide">{label}</span>
      <div className="flex items-center gap-2">
        <span className="text-[9px] font-mono w-4 text-muted-foreground/50">vx</span>
        <div className="flex-1 h-2 rounded-full bg-muted/30 overflow-hidden">
          <div className="h-2 rounded-full transition-all duration-200"
               style={{ width: `${barW}%`, background: color }} />
        </div>
        <span className="text-[10px] font-mono w-12 text-right" style={{ color }}>
          {vx >= 0 ? "+" : ""}{vx.toFixed(3)}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-[9px] font-mono w-4 text-muted-foreground/50">ωz</span>
        <div className="flex-1 h-2 rounded-full bg-muted/30 overflow-hidden">
          <div className="h-2 rounded-full transition-all duration-200"
               style={{ width: `${barWz}%`, background: color }} />
        </div>
        <span className="text-[10px] font-mono w-12 text-right" style={{ color }}>
          {wz >= 0 ? "+" : ""}{wz.toFixed(3)}
        </span>
      </div>
    </div>
  );
}

// ── Isaac Sim WebRTC viewport ─────────────────────────────────────────────────
// AppLauncher livestream=1 serves WebRTC at port 49100.
// When streaming is active (Isaac mode + stream flag), embed it directly.

const ISAAC_STREAM_URL = "http://localhost:49100";

function IsaacViewport({ streaming, cameraB64 }: { streaming: boolean; cameraB64?: string }) {
  const [streamReachable, setStreamReachable] = useState<boolean>(false);

  // Poll stream availability when streaming=true
  useEffect(() => {
    if (!streaming) { setStreamReachable(false); return; }
    let alive = true;
    const check = () => fetch(ISAAC_STREAM_URL, { mode: "no-cors" })
      .then(() => { if (alive) setStreamReachable(true); })
      .catch(() => { if (alive) setStreamReachable(false); });
    check();
    const t = setInterval(check, 3000);
    return () => { alive = false; clearInterval(t); };
  }, [streaming]);

  // Live camera feed from telemetry takes priority in viewport when no 3D stream
  if (cameraB64) {
    return (
      <div className="relative w-full h-full bg-black rounded-lg overflow-hidden">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={cameraB64} alt="Isaac Sim camera" className="w-full h-full object-contain" />
        <span className="absolute top-2 left-2 text-[8px] font-mono text-white/50 bg-black/40 px-1 rounded">
          LIVE · Isaac camera
        </span>
        {streaming && streamReachable && (
          <a href={ISAAC_STREAM_URL} target="_blank" rel="noreferrer"
            className="absolute top-2 right-2 text-[8px] font-mono text-orange-400/80 bg-black/40 px-1.5 py-0.5 rounded hover:text-orange-400 transition-colors">
            3D ↗
          </a>
        )}
      </div>
    );
  }

  if (streaming && streamReachable) {
    return (
      <iframe
        src={ISAAC_STREAM_URL}
        className="w-full h-full rounded-lg border-0"
        allow="camera; microphone"
        title="Isaac Sim 3D Viewport (WebRTC)"
        sandbox="allow-scripts allow-same-origin allow-forms"
      />
    );
  }

  if (streaming && !streamReachable) {
    return (
      <div className="w-full h-full flex flex-col items-center justify-center bg-black/40 rounded-lg gap-2 text-center px-4">
        <RefreshCw className="w-5 h-5 text-orange-400 animate-spin" />
        <p className="text-xs font-semibold text-orange-400">Isaac Sim loading…</p>
        <p className="text-[10px] text-muted-foreground/70">
          WebRTC stream will appear here once Isaac has booted (~60s).
        </p>
        <p className="text-[10px] text-muted-foreground/50">Camera feed will show below when rendering starts.</p>
      </div>
    );
  }

  return (
    <div className="w-full h-full flex flex-col items-center justify-center bg-black/40 rounded-lg gap-2 text-center px-4">
      <Zap className="w-6 h-6 text-muted-foreground/40" />
      <p className="text-xs font-semibold text-muted-foreground/60">Isaac Sim not streaming</p>
      <p className="text-[10px] text-muted-foreground/50 leading-relaxed">
        Switch to <span className="text-orange-400 font-mono">Isaac Sim</span> backend and click Start,<br />
        or launch directly:<br />
        <code className="font-mono text-[9px] text-muted-foreground/70">
          python scripts/demo/run_supervisor_demo_isaac.py --stream
        </code>
      </p>
      <p className="text-[10px] text-muted-foreground/40">
        Mock mode: camera feed shows top-down view below.
      </p>
    </div>
  );
}

// ── Waypoint canvas ───────────────────────────────────────────────────────────

function WaypointCanvas({ waypoints, intervened }: { waypoints: [number, number][]; intervened: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const W = canvas.width;
    const H = canvas.height;
    ctx.clearRect(0, 0, W, H);

    // Background
    ctx.fillStyle = "#0a0f1a";
    ctx.fillRect(0, 0, W, H);

    // Robot position (center bottom)
    const rx = W / 2;
    const ry = H - 20;

    // Robot body
    ctx.beginPath();
    ctx.arc(rx, ry, 8, 0, Math.PI * 2);
    ctx.fillStyle = "#3b82f6";
    ctx.fill();
    ctx.strokeStyle = "#93c5fd";
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // Robot heading arrow
    ctx.beginPath();
    ctx.moveTo(rx, ry);
    ctx.lineTo(rx, ry - 20);
    ctx.strokeStyle = "#93c5fd";
    ctx.lineWidth = 2;
    ctx.stroke();

    // Safe zone ring
    const dSafePx = 25;
    ctx.beginPath();
    ctx.arc(rx, ry, dSafePx, 0, Math.PI * 2);
    ctx.strokeStyle = intervened ? "#ef4444" : "#22c55e";
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 3]);
    ctx.stroke();
    ctx.setLineDash([]);

    // Waypoints
    waypoints.forEach(([wdx, wdy], i) => {
      // wdx = forward (up on canvas), wdy = lateral
      const scale = 40;
      const wx = rx + wdy * scale;
      const wy = ry - wdx * scale;
      const r = Math.max(3, 7 - i);
      const alpha = 1 - i * 0.15;
      ctx.beginPath();
      ctx.arc(wx, wy, r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(100, 200, 255, ${alpha})`;
      ctx.fill();
      if (i > 0) {
        const [px_dx, px_dy] = waypoints[i - 1];
        ctx.beginPath();
        ctx.moveTo(rx + px_dy * scale, ry - px_dx * scale);
        ctx.lineTo(wx, wy);
        ctx.strokeStyle = `rgba(100, 200, 255, ${alpha * 0.6})`;
        ctx.lineWidth = 1;
        ctx.stroke();
      }
    });

    // Labels
    ctx.fillStyle = "#64748b";
    ctx.font = "9px monospace";
    ctx.fillText("robot frame (forward ↑)", 4, 10);
    ctx.fillStyle = intervened ? "#ef4444" : "#22c55e";
    ctx.fillText(intervened ? "CBF ACTIVE" : "CBF IDLE", W - 68, 10);
  }, [waypoints, intervened]);

  return (
    <canvas
      ref={canvasRef}
      width={180}
      height={160}
      className="rounded border border-border/30 w-full"
    />
  );
}

// ── Architecture flow diagram ─────────────────────────────────────────────────

function ArchDiagram({ model, intervened, zone }: { model: string; intervened: boolean; zone: DemoZone }) {
  const meta = MODEL_META[model] ?? MODEL_META.vint;
  const arrowCls = "text-[9px] font-mono text-muted-foreground/50";

  const Block = ({ label, sub, active, color }: { label: string; sub?: string; active?: boolean; color?: string }) => (
    <div className={`rounded border px-2 py-1 text-center transition-all duration-300 ${
      active ? "border-current bg-current/10" : "border-border/30 bg-card/30"
    }`} style={active && color ? { borderColor: color, color } : undefined}>
      <div className="text-[10px] font-semibold">{label}</div>
      {sub && <div className="text-[8px] text-muted-foreground/60 mt-0.5">{sub}</div>}
    </div>
  );

  return (
    <div className="flex items-center gap-1 flex-wrap">
      <Block label="Camera" sub="forward-facing" active />
      <ChevronRight className="w-3 h-3 text-muted-foreground/40 shrink-0" />
      <Block label={meta.label} sub={meta.arch} active color={meta.color} />
      <ChevronRight className="w-3 h-3 text-muted-foreground/40 shrink-0" />
      <Block label="u_nom" sub="waypoints→cmd" active />
      <ChevronRight className="w-3 h-3 text-muted-foreground/40 shrink-0" />
      <Block
        label="CBF-QP"
        sub="FleetSafe"
        active={intervened}
        color={intervened ? ZONE_COLOR[zone] : "#22c55e"}
      />
      <ChevronRight className="w-3 h-3 text-muted-foreground/40 shrink-0" />
      <Block label="u_safe" sub="cmd_vel" active />
      <ChevronRight className="w-3 h-3 text-muted-foreground/40 shrink-0" />
      <Block label="Isaac Sim" sub="robot" active />
    </div>
  );
}

// ── Robot Controls panel ──────────────────────────────────────────────────────

function RobotControls() {
  const [estopLatched, setEstopLatched] = useState<boolean>(false);
  const [busy, setBusy] = useState<boolean>(false);

  // Poll estop status on mount and after each action
  const refreshEstop = useCallback(async () => {
    try {
      const s = await robotApi.estopStatus();
      setEstopLatched(s.latched);
    } catch { /* robot offline — ignore */ }
  }, []);

  useEffect(() => { refreshEstop(); }, [refreshEstop]);

  const act = useCallback(async (fn: () => Promise<unknown>) => {
    if (busy) return;
    setBusy(true);
    try { await fn(); } catch { /* ignore — robot may be offline */ }
    finally { setBusy(false); }
  }, [busy]);

  const latchEstop = useCallback(() => act(async () => {
    await robotApi.estopLatch("demo-page");
    setEstopLatched(true);
  }), [act]);

  const clearEstop = useCallback(() => act(async () => {
    await robotApi.estopClear("operator");
    setEstopLatched(false);
  }), [act]);

  const DpadBtn = ({ onClick, title, children }: {
    onClick: () => Promise<unknown>; title: string; children: React.ReactNode;
  }) => (
    <button
      onClick={() => !estopLatched && act(onClick)}
      disabled={estopLatched || busy}
      title={title}
      className="flex items-center justify-center w-10 h-10 rounded border border-border/40 bg-card/60
                 text-muted-foreground hover:bg-primary/10 hover:text-primary hover:border-primary/40
                 transition-colors disabled:opacity-30 disabled:cursor-not-allowed active:scale-95">
      {children}
    </button>
  );

  return (
    <div className="rounded-lg border border-border/50 bg-card/30 p-3 space-y-3">
      <div className="flex items-center gap-1.5">
        <CircleDot className="w-3.5 h-3.5 text-sky-400" />
        <span className="text-[11px] font-semibold">Robot Controls</span>
        <span className="text-[9px] text-muted-foreground/50 ml-1">direct Yahboom M3Pro</span>
      </div>

      {/* E-stop banner */}
      {estopLatched && (
        <div className="rounded border border-red-500/40 bg-red-500/10 px-2 py-1 text-[10px] font-mono text-red-400 text-center">
          E-STOP LATCHED — robot locked
        </div>
      )}

      {/* D-pad */}
      <div className="flex flex-col items-center gap-1">
        {/* Forward */}
        <DpadBtn onClick={robotApi.pulseForward} title="Forward">
          <ArrowUp className="w-4 h-4" />
        </DpadBtn>
        {/* Middle row: Left | Stop | Right */}
        <div className="flex items-center gap-1">
          <DpadBtn onClick={robotApi.pulseLeft} title="Turn left">
            <ArrowLeft className="w-4 h-4" />
          </DpadBtn>
          <button
            onClick={() => act(robotApi.zero)}
            disabled={busy}
            title="Stop (zero velocity)"
            className="flex items-center justify-center w-10 h-10 rounded border border-amber-500/40
                       bg-amber-500/10 text-amber-400 hover:bg-amber-500/20 transition-colors
                       disabled:opacity-30 active:scale-95">
            <Square className="w-4 h-4" />
          </button>
          <DpadBtn onClick={robotApi.pulseRight} title="Turn right">
            <ArrowRight className="w-4 h-4" />
          </DpadBtn>
        </div>
        {/* Back */}
        <DpadBtn onClick={robotApi.pulseBack} title="Backward">
          <ArrowDown className="w-4 h-4" />
        </DpadBtn>
      </div>

      {/* E-stop controls */}
      <div className="flex gap-2">
        <button
          onClick={latchEstop}
          disabled={estopLatched || busy}
          className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded border border-red-500/50
                     bg-red-500/15 text-red-400 text-[10px] font-mono font-semibold
                     hover:bg-red-500/25 transition-colors disabled:opacity-30 disabled:cursor-not-allowed">
          <OctagonX className="w-3.5 h-3.5" /> E-STOP
        </button>
        <button
          onClick={clearEstop}
          disabled={!estopLatched || busy}
          className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded border border-green-500/50
                     bg-green-500/15 text-green-400 text-[10px] font-mono font-semibold
                     hover:bg-green-500/25 transition-colors disabled:opacity-30 disabled:cursor-not-allowed">
          <CheckCircle className="w-3.5 h-3.5" /> CLEAR
        </button>
      </div>

      <p className="text-[8px] text-muted-foreground/40 text-center leading-tight">
        Each D-pad tap sends a 300 ms velocity pulse to the physical robot via ROS2 relay.
        Stop sends zero velocity. E-STOP latches the safety relay.
      </p>
    </div>
  );
}

// ── Main demo page ─────────────────────────────────────────────────────────────

export default function DemoPage() {
  const { frame, serverStatus, connected } = useDemoTelemetry();

  const [model,     setModel]     = useState<string>("vint");
  const [scene,     setScene]     = useState<string>("hospital_corridor");
  const [fleetsafe, setFleetsafe] = useState<boolean>(true);
  const [mockMode,  setMockMode]  = useState<boolean>(true);
  const [launching, setLaunching] = useState<boolean>(false);
  // mounted: defers client-only state (WebSocket connected) from SSR render
  // so the first paint matches the server HTML and avoids hydration mismatch.
  const [mounted,   setMounted]   = useState<boolean>(false);
  useEffect(() => { setMounted(true); }, []);

  const runningStatus = serverStatus?.status;
  const isRunning = runningStatus === "running" || runningStatus === "starting";
  const meta = MODEL_META[model] ?? MODEL_META.vint;

  const start = useCallback(async () => {
    setLaunching(true);
    try {
      await fetch(`${BASE}/api/demo/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model,
          scene,
          fleetsafe,
          mock: mockMode,
          stream: !mockMode,   // WebRTC streaming in Isaac mode
          max_steps: mockMode ? 500 : 2000,  // longer run for supervisor demo
        }),
      });
    } finally {
      setLaunching(false);
    }
  }, [model, scene, fleetsafe, mockMode]);

  const stop = useCallback(async () => {
    await fetch(`${BASE}/api/demo/stop`, { method: "POST" });
  }, []);

  const reset = useCallback(async () => {
    await fetch(`${BASE}/api/demo/stop`, { method: "POST" });
    // Clear local frame/status so the panel shows a clean slate for the new model
    window.location.reload();
  }, []);

  // Current frame data
  const f = frame;
  const zone: DemoZone = f?.cbf_zone ?? "GREEN";
  const intervened = f?.intervened ?? false;

  return (
    <div className="p-4 space-y-4 max-w-[1400px] mx-auto">

      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-lg font-bold flex items-center gap-2">
            <Shield className="w-5 h-5 text-primary" />
            FleetSafe Supervisor Demo
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            GNM / ViNT visual navigation + CBF-QP safety filter · Isaac Sim + Isaac Lab
          </p>
        </div>
        <div className="flex items-center gap-2">
          {mounted && (connected
            ? <span className="flex items-center gap-1 text-[10px] text-green-400"><Wifi className="w-3 h-3" />live</span>
            : <span className="flex items-center gap-1 text-[10px] text-muted-foreground"><WifiOff className="w-3 h-3" />offline</span>)}
          {/* Stop — always clickable so user can abort regardless of WS state */}
          <button onClick={stop}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded bg-red-500/15 text-red-400 border border-red-500/30 text-xs hover:bg-red-500/25 transition-colors ${!isRunning ? "opacity-40" : ""}`}>
            <Square className="w-3 h-3" /> Stop
          </button>
          {/* Reset — stops demo and clears all telemetry so a new model can be selected */}
          <button onClick={reset}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-muted/20 text-muted-foreground border border-border/40 text-xs hover:bg-muted/40 transition-colors">
            <RefreshCw className="w-3 h-3" /> Reset
          </button>
          <button onClick={start} disabled={isRunning || launching || (mounted && !connected)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-primary/15 text-primary border border-primary/30 text-xs hover:bg-primary/25 transition-colors disabled:opacity-30 disabled:cursor-not-allowed">
            {launching ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
            Start Demo
          </button>
        </div>
      </div>

      {/* ── Config strip ────────────────────────────────────────────────────── */}
      <div className="rounded-lg border border-border/50 bg-card/30 p-3">
        <div className="flex flex-wrap items-center gap-4">
          {/* Model selector */}
          <div className="space-y-0.5">
            <label className="text-[9px] font-mono text-muted-foreground/60 uppercase tracking-wide block">Model</label>
            <div className="flex gap-1">
              {(["gnm", "vint", "nomad"] as const).map(m => (
                <button key={m} onClick={() => setModel(m)} disabled={isRunning}
                  className={`px-2.5 py-1 rounded text-[10px] font-mono font-semibold border transition-colors disabled:opacity-40 ${
                    model === m ? "border-current bg-current/10" : "border-border/30 text-muted-foreground hover:bg-muted/20"
                  }`}
                  style={model === m ? { color: MODEL_META[m].color, borderColor: MODEL_META[m].color } : undefined}>
                  {MODEL_META[m].label}
                </button>
              ))}
            </div>
          </div>

          {/* Scene selector */}
          <div className="space-y-0.5">
            <label className="text-[9px] font-mono text-muted-foreground/60 uppercase tracking-wide block">Scene</label>
            <select value={scene} onChange={e => setScene(e.target.value)} disabled={isRunning}
              className="bg-card border border-border/50 rounded px-2 py-1 text-[10px] font-mono disabled:opacity-40">
              <option value="hospital_corridor">Hospital Corridor</option>
              <option value="hospital_icu_approach">ICU Approach</option>
              <option value="hospital_elevator_lobby">Elevator Lobby</option>
            </select>
          </div>

          {/* FleetSafe toggle */}
          <div className="space-y-0.5">
            <label className="text-[9px] font-mono text-muted-foreground/60 uppercase tracking-wide block">FleetSafe</label>
            <button onClick={() => setFleetsafe(v => !v)} disabled={isRunning}
              className={`px-2.5 py-1 rounded text-[10px] font-mono border transition-colors disabled:opacity-40 ${
                fleetsafe ? "bg-green-500/10 border-green-500/30 text-green-400" : "bg-muted/10 border-border/30 text-muted-foreground"
              }`}>
              {fleetsafe ? "ON" : "OFF"}
            </button>
          </div>

          {/* Mock / Isaac toggle */}
          <div className="space-y-0.5">
            <label className="text-[9px] font-mono text-muted-foreground/60 uppercase tracking-wide block">Backend</label>
            <button onClick={() => setMockMode(v => !v)} disabled={isRunning}
              className={`px-2.5 py-1 rounded text-[10px] font-mono border transition-colors disabled:opacity-40 ${
                !mockMode ? "bg-orange-500/10 border-orange-500/30 text-orange-400" : "bg-muted/10 border-border/30 text-muted-foreground"
              }`}>
              {mockMode ? "Mock" : "Isaac Sim"}
            </button>
          </div>

          {/* Status badge */}
          <div className="ml-auto">
            <span className={`text-[10px] font-mono font-bold px-2.5 py-1 rounded border ${
              runningStatus === "running"  ? "bg-green-500/10 border-green-500/30 text-green-400" :
              runningStatus === "starting" ? "bg-amber-500/10 border-amber-500/30 text-amber-400" :
              runningStatus === "error"    ? "bg-red-500/10   border-red-500/30   text-red-400"   :
              runningStatus === "done"     ? "bg-sky-500/10   border-sky-500/30   text-sky-400"   :
              "bg-muted/10 border-border/30 text-muted-foreground"
            }`}>
              {(runningStatus ?? "idle").toUpperCase()}
              {f && ` · step ${f.step}`}
              {serverStatus?.frame_count ? ` · ${serverStatus.frame_count} frames` : ""}
            </span>
          </div>
        </div>

        {/* Model description */}
        <p className="text-[10px] text-muted-foreground/60 mt-2" style={{ color: meta.color + "99" }}>
          {meta.label} ({meta.arch}): {meta.description}
        </p>
      </div>

      {/* ── Architecture flow ────────────────────────────────────────────────── */}
      <div className="rounded-lg border border-border/50 bg-card/30 p-3">
        <div className="flex items-center gap-2 mb-2">
          <Layers className="w-3.5 h-3.5 text-primary" />
          <span className="text-[11px] font-semibold">Command Flow</span>
          <span className="text-[9px] text-muted-foreground/50 ml-1">
            sensor → {meta.label} → u_nom → CBF-QP → u_safe → robot
          </span>
        </div>
        <ArchDiagram model={model} intervened={intervened} zone={zone} />
      </div>

      {/* ── Main split layout ────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* ── Left: Isaac Sim viewport ───────────────────────────────────────── */}
        <div className="lg:col-span-2 space-y-3">

          <div className="rounded-lg border border-border/50 bg-card/30 overflow-hidden">
            <div className="flex items-center gap-2 px-3 py-2 border-b border-border/30">
              <Zap className="w-3.5 h-3.5 text-orange-400" />
              <span className="text-[11px] font-semibold">Isaac Sim Viewport</span>
              <span className="text-[9px] text-muted-foreground/50">WebRTC · 3D physics · full Isaac Lab engine</span>
            </div>
            <div className="h-64">
              <IsaacViewport
                streaming={!mockMode && isRunning}
                cameraB64={f?.camera_b64 || undefined}
              />
            </div>
          </div>

          {/* ── Robot camera feed ────────────────────────────────────────────── */}
          <div className="rounded-lg border border-border/50 bg-card/30 overflow-hidden">
            <div className="flex items-center gap-2 px-3 py-2 border-b border-border/30">
              <Camera className="w-3.5 h-3.5 text-sky-400" />
              <span className="text-[11px] font-semibold">Robot Camera View</span>
              <span className="text-[9px] text-muted-foreground/50 ml-1">
                egocentric forward-facing · {meta.label} visual input
              </span>
              {f?.camera_b64 && (
                <span className={`ml-auto text-[9px] font-mono ${(f as DemoFrame & { camera_source?: string }).camera_source === "real_robot" ? "text-orange-400" : "text-green-400"}`}>
                  {(f as DemoFrame & { camera_source?: string }).camera_source === "real_robot"
                    ? "● real robot"
                    : "● sim"}
                </span>
              )}
            </div>
            <div className="relative bg-black/60 h-48 flex items-center justify-center">
              {f?.camera_b64 ? (
                <img src={f.camera_b64} alt="robot camera" className="w-full h-full object-contain" />
              ) : (
                <div className="flex flex-col items-center gap-2 text-muted-foreground/40">
                  <Camera className="w-8 h-8" />
                  <span className="text-[10px]">{isRunning ? "Waiting for camera frame…" : "Start demo to see camera feed"}</span>
                </div>
              )}
              {f && (
                <div className="absolute bottom-2 left-2 right-2 flex justify-between text-[9px] font-mono text-white/60">
                  <span>step {f.step}</span>
                  <span>{f.inference_ms.toFixed(0)}ms inference</span>
                  <span>d_obs={f.min_dist_m.toFixed(2)}m</span>
                </div>
              )}
            </div>
          </div>

        </div>

        {/* ── Right: Decision panel ─────────────────────────────────────────── */}
        <div className="space-y-3">

          {/* CBF Zone */}
          <div className={`rounded-lg border p-3 transition-all duration-500 ${
            f ? ZONE_BG[zone] : "border-border/30 bg-card/30"
          }`}>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-1.5">
                <Shield className="w-3.5 h-3.5" />
                <span className="text-[11px] font-semibold">FleetSafe Status</span>
              </div>
              {f && <ZoneBadge zone={zone} />}
            </div>
            {f ? (
              <div className="grid grid-cols-2 gap-2">
                <Pill label="min dist" value={f.min_dist_m.toFixed(3)} unit=" m" color={ZONE_COLOR[zone]} />
                <Pill label="h(x) barrier" value={f.h_min.toFixed(4)} color={f.h_min < 0 ? "#ef4444" : "#22c55e"} />
                <Pill label="interventions" value={f.intervention_count} />
                <Pill label="cbf latency" value={f.cbf_ms.toFixed(1)} unit=" ms" />
              </div>
            ) : (
              <p className="text-[10px] text-muted-foreground/50">Awaiting telemetry…</p>
            )}
          </div>

          {/* CBF intervention indicator */}
          {f && (
            <div className={`rounded-lg border p-3 flex items-center gap-3 transition-all duration-300 ${
              intervened
                ? "border-red-500/40 bg-red-500/10"
                : "border-green-500/40 bg-green-500/10"
            }`}>
              {intervened
                ? <AlertTriangle className="w-5 h-5 text-red-400 shrink-0" />
                : <CheckCircle   className="w-5 h-5 text-green-400 shrink-0" />}
              <div>
                <p className={`text-[11px] font-bold ${intervened ? "text-red-400" : "text-green-400"}`}>
                  {intervened ? "CBF-QP ACTIVE — command modified" : "CBF-QP IDLE — nominal command passed"}
                </p>
                <p className="text-[9px] text-muted-foreground/60 mt-0.5">
                  {intervened
                    ? `Unsafe zone detected (h=${f.h_min.toFixed(3)} < 0). FleetSafe overrides u_nom.`
                    : `h(x)=${f.h_min.toFixed(3)} > 0. Safety constraint satisfied. No modification.`}
                </p>
              </div>
            </div>
          )}

          {/* u_nom — GNM/ViNT decision */}
          <div className="rounded-lg border border-border/50 bg-card/30 p-3 space-y-2">
            <div className="flex items-center gap-1.5">
              <Eye className="w-3.5 h-3.5" style={{ color: meta.color }} />
              <span className="text-[11px] font-semibold">{meta.label} Nominal Command (u_nom)</span>
            </div>
            {f ? (
              <CmdArrow label="Proposed by model" vx={f.raw_vx} wz={f.raw_wz} color={meta.color} />
            ) : (
              <p className="text-[10px] text-muted-foreground/50">No data</p>
            )}
          </div>

          {/* u_safe — FleetSafe command */}
          <div className="rounded-lg border border-border/50 bg-card/30 p-3 space-y-2">
            <div className="flex items-center gap-1.5">
              <Shield className="w-3.5 h-3.5 text-primary" />
              <span className="text-[11px] font-semibold">Safe Command (u_safe)</span>
            </div>
            {f ? (
              <CmdArrow label="After CBF-QP filter" vx={f.safe_vx} wz={f.safe_wz} color="#22c55e" />
            ) : (
              <p className="text-[10px] text-muted-foreground/50">No data</p>
            )}
            {f && intervened && (
              <div className="rounded border border-red-500/20 bg-red-500/5 px-2 py-1">
                <p className="text-[9px] font-mono text-red-400">
                  Δvx={((f.safe_vx - f.raw_vx)).toFixed(3)}  Δωz={((f.safe_wz - f.raw_wz)).toFixed(3)}
                </p>
              </div>
            )}
          </div>

          {/* Waypoints canvas */}
          <div className="rounded-lg border border-border/50 bg-card/30 p-3 space-y-2">
            <div className="flex items-center gap-1.5">
              <Activity className="w-3.5 h-3.5 text-sky-400" />
              <span className="text-[11px] font-semibold">Predicted Waypoints</span>
              <span className="text-[9px] text-muted-foreground/50">robot frame</span>
            </div>
            <WaypointCanvas waypoints={f?.waypoints ?? []} intervened={intervened} />
          </div>

          {/* Robot Controls */}
          <RobotControls />

          {/* Timing */}
          {f && (
            <div className="rounded-lg border border-border/50 bg-card/30 p-3">
              <div className="flex items-center gap-1.5 mb-2">
                <Cpu className="w-3.5 h-3.5 text-muted-foreground" />
                <span className="text-[11px] font-semibold">Latency</span>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <Pill label={`${meta.label} inference`} value={f.inference_ms.toFixed(1)} unit=" ms" color={meta.color} />
                <Pill label="CBF-QP solve" value={f.cbf_ms.toFixed(1)} unit=" ms" color="#22c55e" />
                <Pill label="total" value={(f.inference_ms + f.cbf_ms).toFixed(1)} unit=" ms" />
              </div>
              <div className="mt-2 h-1.5 w-full rounded-full bg-muted/30 overflow-hidden">
                <div className="h-1.5 rounded-full flex">
                  <div className="h-full" style={{ width: `${Math.min(100, f.inference_ms / 1.0)}%`, background: meta.color }} />
                  <div className="h-full bg-green-500" style={{ width: `${Math.min(20, f.cbf_ms / 0.2)}%` }} />
                </div>
              </div>
              <p className="text-[8px] text-muted-foreground/40 mt-1">
                Real-time threshold: &lt;100ms total · {meta.label}: {f.inference_ms.toFixed(0)}ms CBF: {f.cbf_ms.toFixed(0)}ms
              </p>
            </div>
          )}

        </div>
      </div>

      {/* ── Code reference ────────────────────────────────────────────────────── */}
      <details className="rounded-lg border border-border/50 bg-card/30">
        <summary className="px-4 py-3 text-[11px] font-semibold cursor-pointer text-muted-foreground hover:text-foreground select-none">
          View integration code — {meta.label} + FleetSafe command loop
        </summary>
        <div className="px-4 pb-4 space-y-3 border-t border-border/30 pt-3">
          <p className="text-[10px] text-muted-foreground/70">
            The demo script at <code className="font-mono text-[9px] text-sky-400">scripts/demo/run_supervisor_demo_isaac.py</code> runs this pipeline.
          </p>
          <pre className="bg-black/40 rounded p-3 text-[10px] font-mono text-green-300 overflow-x-auto leading-relaxed">{`# Load ${meta.label} model adapter
from fleet_safe_vla.integrations.visualnav_transformer import get_adapter
from fleet_safe_vla.integrations.visualnav_transformer.fleetsafe_wrapper import FleetSafeWrapper
from fleet_safe_vla.fleet_safety.yahboom_cbf import YahboomCBFConfig

adapter = get_adapter("${model}")           # GNMAdapter / ViNTAdapter / NoMaDAdapter
adapter.load_checkpoint(Path("checkpoints/${model}.pth"))

wrapper = FleetSafeWrapper(
    adapter=adapter,
    cbf_config=YahboomCBFConfig(d_safe_m=0.30),  # 30 cm safety margin
    v_max=0.30,   # m/s
    w_max=0.70,   # rad/s
)

# ── Control loop (runs inside Isaac AppLauncher) ──────────────────────────────
while not done:
    # 1. Read camera observation from Isaac Sim robot
    obs_imgs = env.get_camera_frames()   # list of last 5 RGB frames
    goal_img  = env.get_goal_image()     # visual navigation goal
    obs_vec   = env.get_obs_vector()     # 47-dim kinematic state

    # 2. Preprocess for ${meta.label}
    preprocessed = adapter.preprocess_observation(obs_imgs, goal_img)

    # 3. Run FleetSafe (model + CBF-QP in one call)
    result = wrapper.step(
        preprocessed,
        obs_vec,
        obstacle_positions=env.obstacle_positions,  # from Isaac Sim
        robot_xy=obs_vec[22:24],
    )

    # 4. result contains full telemetry
    # result.raw_cmd_vel  — what ${meta.label} proposed
    # result.safe_cmd_vel — what CBF-QP allows
    # result.intervened   — True if CBF modified the command
    # result.min_dist_m   — closest obstacle distance

    # 5. Send safe command to robot in Isaac Sim
    env.apply_cmd_vel(result.safe_cmd_vel.vx,
                      result.safe_cmd_vel.vy,
                      result.safe_cmd_vel.wz)`}</pre>
          <div className="grid grid-cols-2 gap-2 text-[9px] font-mono text-muted-foreground/60">
            <div>
              <p className="text-[8px] uppercase tracking-wide mb-1 text-muted-foreground/40">Adapters</p>
              <p>fleet_safe_vla/integrations/visualnav_transformer/</p>
              <p className="pl-2 text-sky-400">gnm_adapter.py</p>
              <p className="pl-2 text-pink-400">vint_adapter.py</p>
              <p className="pl-2 text-emerald-400">nomad_adapter.py</p>
            </div>
            <div>
              <p className="text-[8px] uppercase tracking-wide mb-1 text-muted-foreground/40">Safety layer</p>
              <p>fleet_safe_vla/fleet_safety/</p>
              <p className="pl-2 text-green-400">yahboom_cbf.py  — CBF-QP solver</p>
              <p>fleet_safe_vla/integrations/visualnav_transformer/</p>
              <p className="pl-2 text-green-400">fleetsafe_wrapper.py</p>
            </div>
          </div>
        </div>
      </details>

      {/* ── Session summary ───────────────────────────────────────────────────── */}
      {serverStatus && serverStatus.status === "done" && (
        <div className="rounded-lg border border-sky-500/30 bg-sky-500/10 p-4 space-y-2">
          <p className="text-sm font-semibold text-sky-400 flex items-center gap-2">
            <CheckCircle className="w-4 h-4" />
            Episode complete
          </p>
          <div className="grid grid-cols-3 gap-4 text-[11px]">
            <Pill label="Total steps" value={serverStatus.frame_count} />
            <Pill label="CBF interventions" value={serverStatus.intervention_count} />
            <Pill label="IR" value={serverStatus.frame_count > 0
              ? `${((serverStatus.intervention_count / serverStatus.frame_count) * 100).toFixed(1)}%`
              : "—"} />
          </div>
        </div>
      )}

    </div>
  );
}
