"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { isaacApi, isaacExtrasApi, type IsaacStatus } from "@/lib/api";
import { Zap, Square, Camera, RefreshCw, Play, LayoutGrid } from "lucide-react";

const SCENE_LABELS: Record<string, string> = {
  hospital_corridor:        "Corridor",
  hospital_waiting_room:    "Waiting Room",
  hospital_narrow_passage:  "Narrow Passage",
  hospital_crowded_junction:"Crowded Junction",
  hospital_elevator_lobby:  "Elevator Lobby",
  hospital_reception:       "Reception",
};

function StatusDot({ live }: { live: boolean }) {
  return (
    <span className={`w-2 h-2 rounded-full shrink-0 ${
      live ? "bg-green-500" : "bg-red-500/60"
    } ${live ? "animate-pulse" : ""}`} />
  );
}

function ActionButton({
  icon: Icon,
  label,
  onClick,
  variant = "default",
  disabled = false,
}: {
  icon: React.ElementType;
  label: string;
  onClick: () => void;
  variant?: "default" | "danger" | "primary";
  disabled?: boolean;
}) {
  const colours = {
    default: "border-border text-muted-foreground hover:text-foreground hover:border-foreground/40",
    danger:  "border-red-500/40 text-red-400 hover:border-red-500 hover:text-red-300",
    primary: "border-green-500/40 text-green-400 hover:border-green-500 hover:text-green-300",
  };
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`flex items-center gap-2 px-3 py-2 border font-mono text-[10px] transition-colors
        ${colours[variant]} ${disabled ? "opacity-30 pointer-events-none" : ""}`}
    >
      <Icon size={12} strokeWidth={1.5} />
      {label}
    </button>
  );
}

function LogLine({ line }: { line: string }) {
  const isErr = /error|fail|traceback/i.test(line);
  const isWarn = /warn/i.test(line);
  return (
    <div className={`font-mono text-[9px] leading-4 ${
      isErr ? "text-red-400" : isWarn ? "text-amber-400" : "text-muted-foreground/70"
    }`}>
      {line}
    </div>
  );
}

// ── Sensor degradation defaults ───────────────────────────────────────────────

interface SensorDegConfig {
  motion_blur: number;
  low_light: number;
  lidar_dropout_rate: number;
  camera_packet_loss: number;
  latency_jitter_ms: number;
  depth_corruption: boolean;
}

const SENSOR_DEG_DEFAULTS: SensorDegConfig = {
  motion_blur: 0,
  low_light: 0,
  lidar_dropout_rate: 0,
  camera_packet_loss: 0,
  latency_jitter_ms: 0,
  depth_corruption: false,
};

const PEDESTRIAN_SCENARIOS: { id: string; label: string; description: string }[] = [
  { id: "crossing",      label: "Crossing",          description: "Human crossing trajectory" },
  { id: "occlusion",     label: "Occlusion",          description: "Occlusion emergence" },
  { id: "congestion",    label: "Congestion",         description: "Multi-person congestion" },
  { id: "yield",         label: "Yield",              description: "Yield behaviour test" },
  { id: "corridor_rush", label: "Corridor Rush Hour", description: "Corridor rush hour" },
];

export default function IsaacPage() {
  const [status, setStatus]         = useState<IsaacStatus | null>(null);
  const [scenes, setScenes]         = useState<string[]>([]);
  const [selectedScene, setSelectedScene] = useState("hospital_corridor");
  const [logs, setLogs]             = useState<string[]>([]);
  const [busy, setBusy]             = useState(false);
  const [lastAction, setLastAction] = useState<string | null>(null);
  const logsEndRef                  = useRef<HTMLDivElement>(null);

  // Sensor degradation
  const [sensorDeg, setSensorDeg]   = useState<SensorDegConfig>(SENSOR_DEG_DEFAULTS);

  // Pedestrian scenario
  const [selectedScenario, setSelectedScenario] = useState<string | null>(null);

  // Recovery test metrics (stub)
  const RECOVERY_TESTS = [
    { id: "blocked_path_recovery", label: "Test: Blocked Path Recovery" },
    { id: "reroute_around_human",  label: "Test: Reroute Around Human" },
    { id: "resume_after_estop",    label: "Test: Resume After E-Stop" },
  ];

  const pushLog = useCallback((msg: string) => {
    setLogs(l => [...l.slice(-200), msg]);
    setTimeout(() => logsEndRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
  }, []);

  const refreshStatus = useCallback(() => {
    isaacApi.status().then(setStatus).catch(() => {});
  }, []);

  useEffect(() => {
    refreshStatus();
    isaacApi.scenes().then(setScenes).catch(() => {});
    const t = setInterval(refreshStatus, 3000);
    return () => clearInterval(t);
  }, [refreshStatus]);

  async function runAction(label: string, fn: () => Promise<unknown>) {
    setBusy(true);
    setLastAction(label);
    pushLog(`[${new Date().toISOString()}] → ${label}`);
    try {
      const result = await fn();
      pushLog(`  ✓ ${JSON.stringify(result)}`);
    } catch (e) {
      pushLog(`  ✗ ${String(e)}`);
    } finally {
      setBusy(false);
      refreshStatus();
    }
  }

  return (
    <div className="flex flex-col gap-6 p-6 max-w-3xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-mono text-sm font-semibold tracking-wider uppercase">Isaac Sim Control</h1>
          <p className="font-mono text-[9px] text-muted-foreground/50 mt-0.5">
            NVIDIA Omniverse · Hospital environment
          </p>
        </div>
        <button
          onClick={refreshStatus}
          className="text-muted-foreground hover:text-foreground transition-colors"
          title="Refresh status"
        >
          <RefreshCw size={14} />
        </button>
      </div>

      {/* Status panel */}
      <div className="border border-border p-4 flex flex-col gap-3">
        <div className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">Status</div>
        <div className="flex items-center gap-6 font-mono text-[10px]">
          <span className="flex items-center gap-2">
            <StatusDot live={status?.isaac_live ?? false} />
            <span className="text-muted-foreground">Isaac Sim</span>
            <span className={status?.isaac_live ? "text-green-400" : "text-red-400/60"}>
              {status?.isaac_live ? "LIVE" : "offline"}
            </span>
          </span>
          <span className="flex items-center gap-2">
            <StatusDot live={status?.webrtc_live ?? false} />
            <span className="text-muted-foreground">WebRTC</span>
            <span className={status?.webrtc_live ? "text-green-400" : "text-muted-foreground/30"}>
              {status?.webrtc_live ? "LIVE" : "—"}
            </span>
          </span>
          <span className="flex items-center gap-2 ml-auto text-muted-foreground/40">
            stream: {status?.stream_status ?? "—"}
          </span>
        </div>
      </div>

      {/* Scene selector */}
      <div className="border border-border p-4 flex flex-col gap-3">
        <div className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">Scene</div>
        <div className="grid grid-cols-3 gap-2">
          {(scenes.length ? scenes : Object.keys(SCENE_LABELS)).map(s => (
            <button
              key={s}
              onClick={() => setSelectedScene(s)}
              className={`px-3 py-2 border font-mono text-[9px] text-left transition-colors
                ${selectedScene === s
                  ? "border-foreground/60 text-foreground bg-foreground/5"
                  : "border-border text-muted-foreground hover:border-foreground/30 hover:text-foreground"}`}
            >
              <LayoutGrid size={9} className="mb-1 opacity-50" />
              {SCENE_LABELS[s] ?? s}
            </button>
          ))}
        </div>
      </div>

      {/* Actions */}
      <div className="border border-border p-4 flex flex-col gap-3">
        <div className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">Actions</div>
        <div className="flex flex-wrap gap-2">
          <ActionButton
            icon={Zap}
            label={`Start (${SCENE_LABELS[selectedScene] ?? selectedScene})`}
            variant="primary"
            disabled={busy}
            onClick={() => runAction(`start Isaac — ${selectedScene}`, () => isaacApi.start(selectedScene))}
          />
          <ActionButton
            icon={Square}
            label="Stop Isaac"
            variant="danger"
            disabled={busy}
            onClick={() => runAction("stop Isaac", () => isaacApi.stop())}
          />
          <ActionButton
            icon={LayoutGrid}
            label="Load Scene"
            disabled={busy || !status?.isaac_live}
            onClick={() => runAction(`load scene ${selectedScene}`, () => isaacApi.loadScene(selectedScene))}
          />
          <ActionButton
            icon={Camera}
            label="Snapshot"
            disabled={busy || !status?.isaac_live}
            onClick={() => runAction("snapshot", () => isaacApi.snapshot())}
          />
          <ActionButton
            icon={Play}
            label="Run Benchmark"
            variant="primary"
            disabled={busy}
            onClick={() => runAction("run benchmark", () => isaacApi.benchmark(selectedScene))}
          />
        </div>

        {busy && lastAction && (
          <div className="font-mono text-[9px] text-amber-400 animate-pulse">
            Running: {lastAction}…
          </div>
        )}
      </div>

      {/* Action log */}
      <div className="border border-border p-4 flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <div className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">Action Log</div>
          <button
            onClick={() => setLogs([])}
            className="font-mono text-[8px] text-muted-foreground/30 hover:text-muted-foreground transition-colors"
          >
            clear
          </button>
        </div>
        <div className="max-h-48 overflow-y-auto flex flex-col gap-0.5 bg-background p-2">
          {logs.length === 0 && (
            <div className="font-mono text-[9px] text-muted-foreground/20">No actions yet.</div>
          )}
          {logs.map((line, i) => <LogLine key={i} line={line} />)}
          <div ref={logsEndRef} />
        </div>
      </div>

      {/* Notes */}
      <div className="font-mono text-[9px] text-muted-foreground/30 border-t border-border pt-3">
        Isaac Sim must be running at {status?.http_url ?? "http://localhost:8211"} for scene load and snapshot.
        Start will launch via <code className="text-muted-foreground/50">scripts/isaaclab/run_hospital.sh</code>.
      </div>

      {/* ── Sensor Degradation Panel ──────────────────────────────────────── */}
      <div className="border border-border p-4 flex flex-col gap-3">
        <div className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">
          Sensor Degradation
        </div>

        <div className="grid grid-cols-2 gap-x-6 gap-y-3">
          {([
            { key: "motion_blur",         label: "Motion Blur",          min: 0, max: 100, unit: "%" },
            { key: "low_light",           label: "Low-Light Level",      min: 0, max: 100, unit: "%" },
            { key: "lidar_dropout_rate",  label: "LiDAR Dropout",        min: 0, max: 50,  unit: "%" },
            { key: "camera_packet_loss",  label: "Camera Packet Loss",   min: 0, max: 30,  unit: "%" },
            { key: "latency_jitter_ms",   label: "Latency Jitter",       min: 0, max: 200, unit: "ms" },
          ] as { key: keyof SensorDegConfig; label: string; min: number; max: number; unit: string }[]).map(({ key, label, min, max, unit }) => (
            <div key={key} className="flex flex-col gap-1">
              <div className="flex items-center justify-between font-mono text-[8px] text-muted-foreground/50">
                <span>{label}</span>
                <span className="text-foreground/60">{sensorDeg[key] as number}{unit}</span>
              </div>
              <input
                type="range"
                min={min}
                max={max}
                value={sensorDeg[key] as number}
                onChange={e => setSensorDeg(prev => ({ ...prev, [key]: Number(e.target.value) }))}
                className="w-full accent-foreground/60"
              />
            </div>
          ))}

          <div className="flex items-center gap-3">
            <span className="font-mono text-[8px] text-muted-foreground/50">Depth Corruption</span>
            <button
              onClick={() => setSensorDeg(prev => ({ ...prev, depth_corruption: !prev.depth_corruption }))}
              className={[
                "px-2 py-1 border font-mono text-[8px] transition-colors",
                sensorDeg.depth_corruption
                  ? "border-amber-500/40 text-amber-400"
                  : "border-border text-muted-foreground/50",
              ].join(" ")}
            >
              {sensorDeg.depth_corruption ? "ON" : "OFF"}
            </button>
          </div>
        </div>

        <div className="flex gap-2 pt-1">
          <button
            onClick={() => runAction("apply sensor degradation", () =>
              isaacExtrasApi.sensorDegradation(sensorDeg as unknown as Record<string, unknown>)
            )}
            disabled={busy}
            className="px-3 py-1.5 border border-amber-500/40 text-amber-400 font-mono text-[9px] hover:border-amber-500 transition-colors disabled:opacity-30"
          >
            Apply Degradation
          </button>
          <button
            onClick={() => {
              setSensorDeg(SENSOR_DEG_DEFAULTS);
              runAction("reset sensor degradation", () =>
                isaacExtrasApi.sensorDegradation(SENSOR_DEG_DEFAULTS as unknown as Record<string, unknown>)
              );
            }}
            disabled={busy}
            className="px-3 py-1.5 border border-border text-muted-foreground/60 font-mono text-[9px] hover:border-foreground/40 hover:text-foreground transition-colors disabled:opacity-30"
          >
            Reset to Clean
          </button>
        </div>
      </div>

      {/* ── Pedestrian Scenarios Panel ────────────────────────────────────── */}
      <div className="border border-border p-4 flex flex-col gap-3">
        <div className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">
          Pedestrian Scenarios
        </div>

        <div className="grid grid-cols-3 gap-2">
          {PEDESTRIAN_SCENARIOS.map(sc => (
            <button
              key={sc.id}
              onClick={() => setSelectedScenario(sc.id)}
              className={[
                "p-3 border font-mono text-left transition-colors flex flex-col gap-1",
                selectedScenario === sc.id
                  ? "border-foreground/60 text-foreground bg-foreground/5"
                  : "border-border text-muted-foreground hover:border-foreground/30 hover:text-foreground",
              ].join(" ")}
            >
              <span className="text-[9px] font-semibold">{sc.label}</span>
              <span className="text-[8px] text-muted-foreground/50">{sc.description}</span>
            </button>
          ))}
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              if (!selectedScenario) return;
              runAction(`load scenario: ${selectedScenario}`, () =>
                isaacExtrasApi.pedestrianScenario(selectedScene, selectedScenario)
              );
            }}
            disabled={busy || !selectedScenario}
            className="px-3 py-1.5 border border-green-500/40 text-green-400 font-mono text-[9px] hover:border-green-500 transition-colors disabled:opacity-30"
          >
            Load Scenario
          </button>
          {!selectedScenario && (
            <span className="font-mono text-[8px] text-muted-foreground/30">Select a scenario first</span>
          )}
        </div>

        {/* Metrics display */}
        <div className="border-t border-border pt-3 grid grid-cols-5 gap-3">
          {[
            { key: "min_interpersonal_distance", label: "Min IPS Dist" },
            { key: "ttc",                        label: "TTC" },
            { key: "stop_frequency",             label: "Stop Freq" },
            { key: "hesitation_latency",         label: "Hesitation Lat" },
            { key: "social_compliance_score",    label: "Social Score" },
          ].map(m => (
            <div key={m.key} className="flex flex-col gap-0.5">
              <div className="font-mono text-[7px] text-muted-foreground/40 uppercase">{m.label}</div>
              <div className="font-mono text-[10px] text-foreground/40">--</div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Recovery Behaviour Panel ──────────────────────────────────────── */}
      <div className="border border-border p-4 flex flex-col gap-3">
        <div className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">
          Recovery Behaviour Tests
        </div>
        <div className="flex flex-wrap gap-2">
          {RECOVERY_TESTS.map(test => (
            <button
              key={test.id}
              onClick={() => runAction(test.label, () => isaacExtrasApi.recoveryTest(test.id))}
              disabled={busy}
              className="px-3 py-2 border border-border font-mono text-[9px] text-muted-foreground hover:border-foreground/40 hover:text-foreground transition-colors disabled:opacity-30"
            >
              {test.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
