"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import {
  evidenceApi,
  rosGraphApi,
  isaacApi,
  hospitalApi,
  type Ros2Status,
  type RosGraphState,
  type PhotorealStatus,
  type HospitalRun,
  type HospitalTrajectory,
  type HospitalEvents,
  type HospitalSocial,
} from "@/lib/api";
import { RefreshCw, Wifi, WifiOff, Circle, Radio } from "lucide-react";
import { RosGraphVisualizer } from "@/components/RosGraphVisualizer";

// ── Scenario waypoints ────────────────────────────────────────────────────────

const WAYPOINTS: Record<string, [number, number][]> = {
  none: [],
  crossing: [[-4, 0], [4, 0]],
  occlusion: [[-3, 1.5], [3, 1.5], [-3, -1.5], [3, -1.5]],
  congestion: [[-5, 0], [-3, 1], [-1, -1], [1, 0], [3, 1], [5, -1]],
  yield: [[-4, 0], [0, 0], [4, 0]],
  corridor_rush: [
    [-6, -1.5], [-6, -1], [-6, -0.5], [-6, 0],
    [-6, 0.5], [-6, 1], [-6, 1.5], [-6, 2],
  ],
};

// ── Shared sub-components ─────────────────────────────────────────────────────

function NodeRow({ name }: { name: string }) {
  const isFs = name.includes("fleetsafe");
  const isYb = name.includes("YB");
  return (
    <div className="flex items-center gap-2 font-mono text-[8px] py-0.5">
      <Circle
        size={6}
        className={isFs ? "text-green-400" : isYb ? "text-blue-400" : "text-muted-foreground/30"}
        fill="currentColor"
      />
      <span className={isFs || isYb ? "text-foreground/60" : "text-muted-foreground/40"}>{name}</span>
    </div>
  );
}

function TopicRow({ name, rate }: { name: string; rate?: number | string }) {
  const isCmdVelSafe = name.includes("cmd_vel_safe");
  const isCmdVelRaw  = name.includes("cmd_vel_raw");
  const isCmdVel     = name === "/cmd_vel";
  const color = isCmdVelSafe
    ? "text-green-400/70"
    : isCmdVelRaw
    ? "text-amber-400/70"
    : isCmdVel
    ? "text-amber-400/50"
    : "text-foreground/40";
  return (
    <div className="flex items-center gap-2 font-mono text-[8px] py-0.5">
      <span className={`flex-1 ${color}`}>{name}</span>
      {rate !== undefined && (
        <span
          className={`shrink-0 ${
            typeof rate === "number" ? "text-muted-foreground/50" : "text-muted-foreground/25"
          }`}
        >
          {typeof rate === "number" ? `${rate.toFixed(1)} Hz` : rate}
        </span>
      )}
    </div>
  );
}

// ── Digital twin types ────────────────────────────────────────────────────────

interface TwinPayload {
  type:              string;
  t:                 number;
  live:              boolean;
  source:            string;
  odom:              { x: number; y: number; heading: number };
  cmd_vel:           { vx: number; vy: number; wz: number };
  zone:              string;
  risk:              number;
  crowding_risk:     number;
  battery_pct:       number | null;
  battery_charging:  boolean;
  detection_count:   number;
  tracked_count:     number;
  latency_ms:        number;
  perception_latency_ms: number;
  detections:        unknown[];
  tracks:            unknown[];
  camera_b64?:       string;
}

// ── Live robot sync panel (ws://…/api/twin/ws) ─────────────────────────────

function LiveSyncPanel() {
  const [connected, setConnected] = useState(false);
  const [data, setData]           = useState<TwinPayload | null>(null);
  const wsRef                     = useRef<WebSocket | null>(null);

  const connect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws    = new WebSocket(`${proto}//localhost:8000/api/twin/ws`);
    wsRef.current = ws;

    ws.onopen  = () => setConnected(true);
    ws.onclose = () => { setConnected(false); wsRef.current = null; };
    ws.onmessage = (e) => {
      try { setData(JSON.parse(e.data) as TwinPayload); } catch { /* */ }
    };
  }, []);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    setConnected(false);
    setData(null);
  }, []);

  const zoneColor = (z: string) =>
    z === "RED"   ? "text-red-400"   :
    z === "AMBER" ? "text-amber-400" : "text-green-400";

  return (
    <div className="border-t border-border shrink-0">
      <div className="px-6 py-2.5 border-b border-border flex items-center gap-4">
        <Radio size={11} className={connected ? "text-green-400 animate-pulse" : "text-muted-foreground/30"} />
        <span className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">
          Real Robot Live Sync
        </span>
        <span className={`font-mono text-[9px] ${connected ? "text-green-400" : "text-muted-foreground/30"}`}>
          {connected ? (data?.live ? "ROBOT ONLINE" : "MOCK DATA") : "DISCONNECTED"}
        </span>
        <span className="ml-auto flex gap-2">
          <button
            onClick={connected ? disconnect : connect}
            className={[
              "px-3 py-1 border font-mono text-[9px] transition-colors",
              connected
                ? "border-red-500/40 text-red-400 hover:border-red-500"
                : "border-green-500/40 text-green-400 hover:border-green-500",
            ].join(" ")}
          >
            {connected ? "Disconnect" : "Connect"}
          </button>
        </span>
      </div>

      {connected && (
        <div className="px-6 py-4 flex gap-6 items-start">
          {/* Left: numeric telemetry */}
          <div className="min-w-[220px] space-y-3">
            {/* Pose */}
            <div>
              <div className="font-mono text-[8px] text-muted-foreground/40 mb-1 uppercase tracking-wider">Pose (odometry)</div>
              <div className="grid grid-cols-3 gap-x-4 font-mono text-[10px]">
                <div><span className="text-muted-foreground/40">x </span><span className="text-foreground/70">{data?.odom.x.toFixed(3) ?? "—"}</span><span className="text-muted-foreground/30"> m</span></div>
                <div><span className="text-muted-foreground/40">y </span><span className="text-foreground/70">{data?.odom.y.toFixed(3) ?? "—"}</span><span className="text-muted-foreground/30"> m</span></div>
                <div><span className="text-muted-foreground/40">ψ </span><span className="text-foreground/70">{data ? (data.odom.heading * 180 / Math.PI).toFixed(1) : "—"}</span><span className="text-muted-foreground/30"> °</span></div>
              </div>
            </div>

            {/* Velocity */}
            <div>
              <div className="font-mono text-[8px] text-muted-foreground/40 mb-1 uppercase tracking-wider">Velocity</div>
              <div className="grid grid-cols-3 gap-x-4 font-mono text-[10px]">
                <div><span className="text-muted-foreground/40">vx </span><span className="text-foreground/70">{data?.cmd_vel.vx.toFixed(3) ?? "—"}</span></div>
                <div><span className="text-muted-foreground/40">vy </span><span className="text-foreground/70">{data?.cmd_vel.vy.toFixed(3) ?? "—"}</span></div>
                <div><span className="text-muted-foreground/40">ωz </span><span className="text-foreground/70">{data?.cmd_vel.wz.toFixed(3) ?? "—"}</span></div>
              </div>
            </div>

            {/* Safety */}
            <div>
              <div className="font-mono text-[8px] text-muted-foreground/40 mb-1 uppercase tracking-wider">Safety</div>
              <div className="flex flex-wrap gap-3 font-mono text-[10px]">
                <div>
                  <span className="text-muted-foreground/40">zone </span>
                  <span className={zoneColor(data?.zone ?? "GREEN")}>{data?.zone ?? "—"}</span>
                </div>
                <div>
                  <span className="text-muted-foreground/40">risk </span>
                  <span className="text-foreground/70">{data?.risk.toFixed(2) ?? "—"}</span>
                </div>
                <div>
                  <span className="text-muted-foreground/40">crowd </span>
                  <span className="text-foreground/70">{data?.crowding_risk.toFixed(2) ?? "—"}</span>
                </div>
              </div>
            </div>

            {/* Agents + latency */}
            <div className="flex gap-4 font-mono text-[10px]">
              <div><span className="text-muted-foreground/40">det </span><span className="text-foreground/70">{data?.detection_count ?? 0}</span></div>
              <div><span className="text-muted-foreground/40">trk </span><span className="text-foreground/70">{data?.tracked_count ?? 0}</span></div>
              <div><span className="text-muted-foreground/40">lat </span><span className="text-foreground/70">{data?.latency_ms.toFixed(1) ?? "—"}</span><span className="text-muted-foreground/30"> ms</span></div>
            </div>

            {/* Battery */}
            {data?.battery_pct != null && (
              <div className="font-mono text-[10px]">
                <span className="text-muted-foreground/40">battery </span>
                <span className={data.battery_pct < 20 ? "text-red-400" : "text-foreground/70"}>
                  {data.battery_pct.toFixed(0)}%
                </span>
                {data.battery_charging && <span className="text-green-400 ml-1">⚡</span>}
              </div>
            )}
          </div>

          {/* Right: camera feed */}
          <div className="flex-1">
            <div className="font-mono text-[8px] text-muted-foreground/40 mb-1 uppercase tracking-wider">
              Forward Camera (egocentric VLN input)
            </div>
            {data?.camera_b64 ? (
              /* eslint-disable-next-line @next/next/no-img-element */
              <img
                src={data.camera_b64}
                alt="Real robot forward camera"
                className="max-h-44 border border-border object-contain bg-background"
              />
            ) : (
              <div className="h-32 border border-border bg-background/50 flex items-center justify-center">
                <span className="font-mono text-[9px] text-muted-foreground/25">
                  {data?.live ? "No camera frame — check /usb_cam/image_raw" : "Robot offline or ROS2 not bridged"}
                </span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Live Twin tab ─────────────────────────────────────────────────────────────

function LiveTwinTab() {
  const [ros2, setRos2]       = useState<Ros2Status | null>(null);
  const [loading, setLoading] = useState(false);
  const [rosGraph, setRosGraph]         = useState<RosGraphState | null>(null);
  const [rosGraphLoading, setRosGraphLoading] = useState(false);
  const [webrtcUrl, setWebrtcUrl]             = useState("ws://localhost:8765");
  const [webrtcConnected, setWebrtcConnected] = useState(false);
  const [photoreal, setPhotoreal]             = useState<PhotorealStatus | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try { setRos2(await evidenceApi.ros2Status()); } catch { /* */ }
    finally { setLoading(false); }
  }, []);

  const loadRosGraph = useCallback(async () => {
    setRosGraphLoading(true);
    try { setRosGraph(await rosGraphApi.state()); } catch { /* */ }
    finally { setRosGraphLoading(false); }
  }, []);

  useEffect(() => {
    load();
    loadRosGraph();
    isaacApi.photorealStatus().then(setPhotoreal).catch(() => {});
    const t = setInterval(loadRosGraph, 5000);
    return () => clearInterval(t);
  }, [load, loadRosGraph]);

  const online = ros2?.online ?? false;

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      {/* ROS Graph */}
      <RosGraphVisualizer state={rosGraph} loading={rosGraphLoading} onRefresh={loadRosGraph} />

      {/* Header */}
      <div className="px-6 py-3 border-b border-border shrink-0 flex items-center gap-4">
        <span className="font-mono text-sm font-bold tracking-widest text-foreground/80">DIGITAL TWIN</span>
        <div className={`flex items-center gap-1.5 font-mono text-[9px] ${online ? "text-green-400" : "text-red-400/60"}`}>
          {online ? <Wifi size={11} /> : <WifiOff size={11} />}
          {online ? `ONLINE — ${ros2?.host}` : ros2?.mode === "dry_run" ? "DRY RUN (no probe)" : "OFFLINE"}
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="ml-auto flex items-center gap-1 font-mono text-[8px] text-muted-foreground/40 hover:text-muted-foreground border border-border px-2 py-1 transition-colors disabled:opacity-30"
        >
          <RefreshCw size={9} className={loading ? "animate-spin" : ""} /> Probe
        </button>
      </div>

      {ros2?.warning && (
        <div className="px-6 py-2 border-b border-border font-mono text-[8px] text-amber-400/70 bg-amber-500/5">
          {ros2.warning}
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        {/* Left: nodes */}
        <div className="w-72 shrink-0 border-r border-border p-4 overflow-y-auto">
          <div className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider mb-3">
            ROS2 Nodes {ros2 ? `(${ros2.nodes.length})` : ""}
          </div>
          {ros2?.nodes.map(n => <NodeRow key={n} name={n} />)}
          {ros2?.missing_nodes?.map(n => (
            <div key={n} className="flex items-center gap-2 font-mono text-[8px] py-0.5 text-red-400/50">
              <Circle size={6} className="text-red-400/30" /> {n} <span className="text-red-400/30">(missing)</span>
            </div>
          ))}
          {!loading && !ros2?.nodes.length && (
            <div className="font-mono text-[8px] text-muted-foreground/20">No nodes — robot offline or dry-run mode</div>
          )}
          {ros2?.domain_id != null && (
            <div className="mt-4 pt-3 border-t border-border">
              <div className="font-mono text-[9px] text-muted-foreground/40 mb-1">ROS_DOMAIN_ID</div>
              <div className="font-mono text-[10px] text-foreground/60">{ros2.domain_id}</div>
            </div>
          )}
        </div>

        {/* Right: topics */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="px-4 py-3 border-b border-border shrink-0">
            <div className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">
              Topics {ros2 ? `(${ros2.topics.length})` : ""}
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            {Object.keys(ros2?.rates_hz ?? {}).length > 0 && (
              <div className="mb-4">
                <div className="font-mono text-[8px] text-muted-foreground/40 mb-2">Measured Rates</div>
                {Object.entries(ros2!.rates_hz).map(([t, r]) => (
                  <TopicRow key={t} name={t} rate={r as number | string} />
                ))}
              </div>
            )}
            <div className="font-mono text-[8px] text-muted-foreground/40 mb-2">All Topics</div>
            {ros2?.topics.map(t => <TopicRow key={t} name={t} />)}
            {ros2?.missing_topics?.map(t => (
              <div key={t} className="font-mono text-[8px] py-0.5 text-red-400/40">{t} (missing)</div>
            ))}
            {!loading && !ros2?.topics.length && (
              <div className="font-mono text-[8px] text-muted-foreground/20">No topics — probe when robot is online</div>
            )}
          </div>
          <div className="border-t border-border p-4 shrink-0">
            <div className="font-mono text-[8px] text-muted-foreground/40 mb-2">Hardware Profiling (static)</div>
            <div className="grid grid-cols-2 gap-x-6 gap-y-0.5 font-mono text-[8px]">
              {[
                ["/scan0", "~7 Hz"],
                ["/odom_raw", "~11 Hz"],
                ["/camera/color/image_raw", "~30 Hz"],
                ["/camera/depth/image_raw", "~10 Hz"],
                ["/imu/data_raw", "unstable"],
              ].map(([t, r]) => (
                <div key={t} className="flex justify-between gap-2">
                  <span className="text-muted-foreground/40 truncate">{t}</span>
                  <span className="text-muted-foreground/50 shrink-0">{r}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Photoreal / Viewport Capture */}
      <div className="border-t border-border shrink-0">
        <div className="px-6 py-2.5 border-b border-border flex items-center gap-4">
          <span className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">
            Viewport Capture
          </span>
          {photoreal && (
            <span
              className={`font-mono text-[9px] font-semibold ${
                photoreal.status === "PROVEN"     ? "text-green-400"       :
                photoreal.status === "PROCEDURAL" ? "text-amber-400"       :
                photoreal.status === "NOT_RUN"    ? "text-muted-foreground/30" :
                                                    "text-red-400/60"
              }`}
            >
              {photoreal.status}
            </span>
          )}
          <span className="ml-auto font-mono text-[8px] text-muted-foreground/30">
            Capture: <code className="text-muted-foreground/50">run_hospital.sh --capture</code>
          </span>
        </div>
        <div className="px-6 py-4">
          <div className="flex gap-6 items-start">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={isaacApi.screenshotUrl()}
              alt="Hospital scene capture"
              className="max-h-56 border border-border object-contain bg-background shrink-0"
              onError={e => { (e.target as HTMLImageElement).style.display = "none"; }}
            />
            {photoreal ? (
              <div className="flex flex-col gap-2 justify-center font-mono text-[8px] min-w-0">
                <div className="flex flex-col gap-1">
                  <div className={`flex items-center gap-2 font-semibold ${photoreal.usd_loaded ? "text-green-400/80" : "text-amber-500/70"}`}>
                    <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${photoreal.usd_loaded ? "bg-green-400" : "bg-amber-500"}`} />
                    USD asset: {photoreal.usd_loaded
                      ? `FOUND${photoreal.usd_size_kb ? ` (${photoreal.usd_size_kb} KB)` : ""}`
                      : "MISSING"}
                  </div>
                  <div className={`flex items-center gap-2 font-semibold ${
                    photoreal.status === "PROVEN" ? "text-green-400/80" : "text-amber-400/70"
                  }`}>
                    <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${photoreal.status === "PROVEN" ? "bg-green-400" : "bg-amber-400"}`} />
                    Render: {photoreal.status}
                  </div>
                  <div className="flex items-center gap-2 font-semibold text-red-400/60">
                    <span className="w-1.5 h-1.5 rounded-full shrink-0 bg-red-400/50" />
                    Photoreal: {photoreal.photoreal_claimed === false ? "NOT CLAIMED" : "CLAIMED"}
                  </div>
                </div>
                <div className="border-t border-border/30 pt-1.5 text-muted-foreground/40 space-y-0.5">
                  <div>scene : {photoreal.scene ?? "—"} · scenario : {photoreal.scenario ?? "—"}</div>
                  <div>method: {photoreal.capture_method ?? "—"} · isaac: {photoreal.isaac_version ?? "—"}</div>
                  <div>ts    : {photoreal.timestamp ?? "—"}</div>
                </div>
              </div>
            ) : (
              <div className="flex flex-col justify-center font-mono text-[9px] text-muted-foreground/25 space-y-1">
                <div>No capture data.</div>
                <div className="text-[8px]">Run: python scripts/isaaclab/gen_proof_run.py</div>
                <div className="text-[8px]">Then: python scripts/isaaclab/export_latest_capture_for_web.py</div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Live Feed */}
      <div className="border-t border-border shrink-0">
        <div className="px-6 py-2.5 border-b border-border flex items-center gap-4">
          <span className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider">
            Isaac Sim Live Feed (WebRTC)
          </span>
          <div className={`flex items-center gap-1.5 font-mono text-[9px] ${webrtcConnected ? "text-green-400" : "text-muted-foreground/30"}`}>
            <span className={`w-2 h-2 rounded-full ${webrtcConnected ? "bg-green-500 animate-pulse" : "bg-red-500/40"}`} />
            {webrtcConnected ? "connected" : "disconnected"}
          </div>
          <span className="ml-auto font-mono text-[8px] text-muted-foreground/30">
            Connect via: <code className="text-muted-foreground/50">scripts/isaaclab/start_webrtc.sh</code>
          </span>
        </div>
        <div className="flex items-center gap-3 px-6 py-3">
          <span className="font-mono text-[9px] text-muted-foreground/50 shrink-0">Endpoint</span>
          <input
            type="text"
            value={webrtcUrl}
            onChange={e => setWebrtcUrl(e.target.value)}
            className="flex-1 max-w-xs font-mono text-[9px] bg-background border border-border px-2 py-1 text-foreground/70 focus:outline-none focus:border-foreground/40"
            spellCheck={false}
          />
          <button
            onClick={() => setWebrtcConnected(v => !v)}
            className={[
              "px-3 py-1.5 border font-mono text-[9px] transition-colors",
              webrtcConnected
                ? "border-red-500/40 text-red-400 hover:border-red-500"
                : "border-green-500/40 text-green-400 hover:border-green-500",
            ].join(" ")}
          >
            {webrtcConnected ? "Disconnect" : "Connect"}
          </button>
          {webrtcConnected && (
            <div className="flex-1 h-32 border border-border bg-background/50 flex items-center justify-center">
              <span className="font-mono text-[9px] text-muted-foreground/30">
                WebRTC stream — {webrtcUrl}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Real robot live sync */}
      <LiveSyncPanel />
    </div>
  );
}

// ── Floor plan SVG ────────────────────────────────────────────────────────────

function FloorPlanSVG({
  trajectory,
  scenario,
}: {
  trajectory: HospitalTrajectory | null;
  scenario: string;
}) {
  const waypoints = WAYPOINTS[scenario] ?? [];
  const pts = trajectory?.points ?? [];

  const polylinePoints = pts
    .map(([, x, y]) => `${x},${-y}`)
    .join(" ");

  const start = pts[0];
  const end   = pts[pts.length - 1];

  // Grid lines
  const gridX = [-8, -6, -4, -2, 0, 2, 4, 6, 8];
  const gridY = [-6, -4, -2, 0, 2, 4, 6];

  return (
    <svg
      viewBox="-12 -10 24 20"
      className="w-full h-96 border border-border bg-background"
      style={{ display: "block" }}
    >
      {/* Grid */}
      {gridX.map(gx => (
        <line
          key={`gx${gx}`}
          x1={gx} y1={-8} x2={gx} y2={8}
          stroke="white" strokeOpacity="0.05" strokeWidth="0.03"
        />
      ))}
      {gridY.map(gy => (
        <line
          key={`gy${gy}`}
          x1={-10} y1={-gy} x2={10} y2={-gy}
          stroke="white" strokeOpacity="0.05" strokeWidth="0.03"
        />
      ))}

      {/* Hospital zones (y-axis flipped: SVG y+ is down, world y+ is up) */}
      {/* ICU: x∈[-10,-2], y∈[2,8] → SVG y∈[-8,-2] */}
      <rect x={-10} y={-8} width={8} height={6} fill="rgba(51,102,204,0.35)" />
      {/* NurseStation: x∈[-2,2], y∈[2,8] → SVG y∈[-8,-2] */}
      <rect x={-2} y={-8} width={4} height={6} fill="rgba(140,140,153,0.35)" />
      {/* Pharmacy: x∈[2,10], y∈[2,8] → SVG y∈[-8,-2] */}
      <rect x={2} y={-8} width={8} height={6} fill="rgba(51,166,166,0.35)" />
      {/* Corridor: x∈[-10,10], y∈[-1.5,2] → SVG y∈[-2,1.5] */}
      <rect x={-10} y={-2} width={20} height={3.5} fill="rgba(242,235,209,0.45)" />
      {/* WaitingRoom: x∈[-10,10], y∈[-8,-1.5] → SVG y∈[1.5,8] */}
      <rect x={-10} y={1.5} width={20} height={6.5} fill="rgba(102,166,115,0.35)" />

      {/* Zone labels */}
      <text x={-6} y={-5} fontSize="0.7" fill="rgba(255,255,255,0.6)" textAnchor="middle">ICU</text>
      <text x={0} y={-5} fontSize="0.7" fill="rgba(255,255,255,0.6)" textAnchor="middle">NURSE</text>
      <text x={6} y={-5} fontSize="0.7" fill="rgba(255,255,255,0.6)" textAnchor="middle">PHARMACY</text>
      <text x={0} y={-0.5} fontSize="0.7" fill="rgba(255,255,255,0.6)" textAnchor="middle">CORRIDOR</text>
      <text x={0} y={5} fontSize="0.7" fill="rgba(255,255,255,0.6)" textAnchor="middle">WAITING ROOM</text>

      {/* Wall lines (stroke-width 0.08, opacity 0.5) */}
      {/* Boundary */}
      <rect x={-10} y={-8} width={20} height={16} fill="none" stroke="white" strokeOpacity="0.5" strokeWidth="0.08" />
      {/* Dividers */}
      <line x1={-10} y1={-2} x2={10} y2={-2} stroke="white" strokeOpacity="0.5" strokeWidth="0.08" />
      <line x1={-10} y1={1.5} x2={10} y2={1.5} stroke="white" strokeOpacity="0.5" strokeWidth="0.08" />
      <line x1={-2} y1={-8} x2={-2} y2={-2} stroke="white" strokeOpacity="0.5" strokeWidth="0.08" />
      <line x1={2} y1={-8} x2={2} y2={-2} stroke="white" strokeOpacity="0.5" strokeWidth="0.08" />

      {/* Trajectory polyline */}
      {pts.length > 1 && (
        <polyline
          points={polylinePoints}
          fill="none"
          stroke="#34d399"
          strokeWidth="0.15"
          opacity="0.8"
        />
      )}

      {/* Robot start marker (triangle) */}
      {start && (
        <polygon
          points={`${start[1]},${-start[2] - 0.4} ${start[1] - 0.3},${-start[2] + 0.2} ${start[1] + 0.3},${-start[2] + 0.2}`}
          fill="#34d399"
          opacity="0.9"
        />
      )}

      {/* Robot end marker (circle) */}
      {end && pts.length > 0 && (
        <circle cx={end[1]} cy={-end[2]} r="0.2" fill="#34d399" opacity="0.9" />
      )}

      {/* No trajectory overlay */}
      {pts.length === 0 && (
        <text
          x={0}
          y={0}
          fontSize="0.8"
          fill="rgba(255,255,255,0.2)"
          textAnchor="middle"
          dominantBaseline="middle"
        >
          No trajectory recorded
        </text>
      )}

      {/* Pedestrian waypoints */}
      {waypoints.map(([wx, wy], i) => (
        <g key={i}>
          <circle cx={wx} cy={-wy} r="0.3" fill="#f87171" opacity="0.7" />
          <text
            x={wx + 0.35}
            y={-wy - 0.35}
            fontSize="0.5"
            fill="rgba(248,113,113,0.9)"
          >
            P{i + 1}
          </text>
        </g>
      ))}
    </svg>
  );
}

// ── Safety event timeline ─────────────────────────────────────────────────────

function EventTimeline({ events }: { events: Record<string, unknown>[] }) {
  if (events.length === 0) {
    return (
      <div className="font-mono text-[9px] text-muted-foreground/25">
        No safety events recorded in this run.
      </div>
    );
  }

  const maxStep = Math.max(...events.map(e => Number(e.step ?? 0)), 1);
  const shown   = events.slice(0, 10);

  return (
    <div className="space-y-3">
      {/* Timeline bar */}
      <div className="relative w-full h-8 border border-border bg-background">
        {events.map((e, i) => {
          const step = Number(e.step ?? 0);
          const pct  = (step / maxStep) * 100;
          const isCbf = String(e.event_type ?? e.type ?? "").includes("cbf");
          return (
            <div
              key={i}
              className="absolute top-0 bottom-0 w-px"
              style={{
                left: `${pct}%`,
                backgroundColor: isCbf ? "#fbbf24" : "#f87171",
                opacity: 0.8,
              }}
            />
          );
        })}
      </div>
      {/* Event list */}
      <div className="space-y-0.5">
        {shown.map((e, i) => {
          const step     = Number(e.step ?? 0);
          const evType   = String(e.event_type ?? e.type ?? "unknown");
          const deltaL2  = e.delta_l2 != null ? Number(e.delta_l2).toFixed(3) : "—";
          const minDist  = e.min_dist != null ? Number(e.min_dist).toFixed(2) : e.min_dist_m != null ? Number(e.min_dist_m).toFixed(2) : "—";
          const isCbf    = evType.includes("cbf");
          return (
            <div key={i} className="flex items-center gap-3 font-mono text-[8px]">
              <span className="text-muted-foreground/40 w-10 shrink-0 text-right">{step}</span>
              <span className={isCbf ? "text-amber-400/80" : "text-red-400/70"}>{evType}</span>
              <span className="text-muted-foreground/40">dl2={deltaL2}</span>
              <span className="text-muted-foreground/40">dist={minDist}m</span>
            </div>
          );
        })}
        {events.length > 10 && (
          <div className="font-mono text-[8px] text-muted-foreground/25">
            +{events.length - 10} more events not shown
          </div>
        )}
      </div>
    </div>
  );
}

// ── Social metrics chips ──────────────────────────────────────────────────────

function SocialMetrics({ social }: { social: HospitalSocial | null }) {
  if (!social || social.n_steps === 0) {
    return (
      <div className="font-mono text-[9px] text-muted-foreground/25">
        No social metrics — run with more steps.
      </div>
    );
  }

  const chips: [string, string][] = [
    ["Min interpersonal dist", `${social.min_interpersonal_dist_mean?.toFixed(2) ?? "—"} m`],
    ["Mean TTC",               `${social.ttc_mean?.toFixed(2) ?? "—"} s`],
    ["Stop count",             `${social.stop_count_total ?? "—"}`],
    ["Hesitation latency",     `${social.hesitation_latency_mean?.toFixed(3) ?? "—"} s`],
  ];

  return (
    <div className="flex flex-wrap gap-3">
      {chips.map(([label, value]) => (
        <div key={label} className="border border-border p-3 min-w-[120px]">
          <div className="font-mono text-[8px] text-muted-foreground/50 mb-1">{label}</div>
          <div className="font-mono text-sm text-foreground/80">{value}</div>
        </div>
      ))}
    </div>
  );
}

// ── Run metadata card ─────────────────────────────────────────────────────────

function RunMetaCard({
  run,
  session,
}: {
  run: HospitalRun;
  session: Record<string, unknown> | null;
}) {
  const rows: [string, string][] = [
    ["scene",           run.scene],
    ["scenario",        run.scenario],
    ["agent_count",     session ? String(session.agent_count ?? "—") : "—"],
    ["isaac_version",   session ? String(session.isaac_version ?? "—") : "—"],
    ["usd_available",   session ? String(session.usd_available ?? false) : "—"],
    ["capture",         session ? String(session.capture ?? false) : "—"],
    ["isaac_runtime",   run.isaac_runtime],
    ["usd_asset",       run.usd_asset],
  ];

  return (
    <div className="border border-border bg-card p-3 space-y-1">
      {rows.map(([k, v]) => (
        <div key={k} className="flex items-start gap-2 font-mono text-[8px]">
          <span className="text-muted-foreground/50 shrink-0 w-24">{k}</span>
          <span className="text-foreground/70 break-all">{v}</span>
        </div>
      ))}
    </div>
  );
}

// ── Run Viewer tab ────────────────────────────────────────────────────────────

function RunViewerTab() {
  const [runs, setRuns]           = useState<HospitalRun[]>([]);
  const [selectedTs, setSelectedTs] = useState<string>("");
  const [session, setSession]     = useState<Record<string, unknown> | null>(null);
  const [trajectory, setTrajectory] = useState<HospitalTrajectory | null>(null);
  const [events, setEvents]       = useState<HospitalEvents | null>(null);
  const [social, setSocial]       = useState<HospitalSocial | null>(null);
  const [loading, setLoading]     = useState(false);

  // Load run list once
  useEffect(() => {
    hospitalApi.runs().then(r => {
      setRuns(r);
      if (r.length > 0) setSelectedTs(r[0].timestamp);
    }).catch(() => {});
  }, []);

  // Load run data when selection changes
  useEffect(() => {
    if (!selectedTs) return;
    setLoading(true);
    setSession(null);
    setTrajectory(null);
    setEvents(null);
    setSocial(null);

    Promise.all([
      hospitalApi.session(selectedTs).catch(() => null),
      hospitalApi.trajectory(selectedTs).catch(() => null),
      hospitalApi.events(selectedTs).catch(() => null),
      hospitalApi.social(selectedTs).catch(() => null),
    ]).then(([sess, traj, evts, soc]) => {
      setSession(sess);
      setTrajectory(traj);
      setEvents(evts);
      setSocial(soc);
    }).finally(() => setLoading(false));
  }, [selectedTs]);

  const selectedRun = runs.find(r => r.timestamp === selectedTs) ?? null;
  const scenario    = selectedRun?.scenario ?? "none";

  return (
    <div className="flex flex-1 overflow-hidden">
      {/* Left panel — run list */}
      <div className="w-64 shrink-0 border-r border-border flex flex-col overflow-hidden">
        <div className="p-4 border-b border-border">
          <div className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider mb-2">
            Run
          </div>
          <select
            value={selectedTs}
            onChange={e => setSelectedTs(e.target.value)}
            className="w-full font-mono text-[8px] bg-background border border-border px-2 py-1 text-foreground/70 focus:outline-none focus:border-foreground/40"
          >
            {runs.map(r => (
              <option key={r.timestamp} value={r.timestamp}>
                {r.timestamp} · {r.scene} · {r.scenario}
              </option>
            ))}
            {runs.length === 0 && <option value="">No runs found</option>}
          </select>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {selectedRun && (
            <RunMetaCard run={selectedRun} session={session} />
          )}
          {selectedRun?.has_preview && (
            <div className="mt-4">
              <div className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider mb-2">
                Preview
              </div>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={hospitalApi.preview(selectedTs)}
                alt="Run procedural preview"
                className="w-full border border-border bg-background"
                onError={e => { (e.target as HTMLImageElement).style.display = "none"; }}
              />
            </div>
          )}
        </div>
      </div>

      {/* Main area */}
      <div className="flex-1 overflow-y-auto">
        {loading && (
          <div className="p-6 font-mono text-[9px] text-muted-foreground/30">Loading run data...</div>
        )}

        {!loading && selectedTs && (
          <div className="p-4 space-y-6">
            {/* Section 1: Floor plan + trajectory */}
            <div>
              <div className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider mb-2">
                Floor Plan + Trajectory Overlay
              </div>
              <FloorPlanSVG trajectory={trajectory} scenario={scenario} />
              <div className="mt-1 flex gap-4 font-mono text-[8px] text-muted-foreground/40">
                <span className="flex items-center gap-1">
                  <span className="inline-block w-4 h-px bg-green-400 opacity-70" /> robot path
                </span>
                <span className="flex items-center gap-1">
                  <span className="inline-block w-2 h-2 rounded-full bg-red-400 opacity-70" /> pedestrian waypoints
                </span>
                {trajectory && <span>{trajectory.steps} pts</span>}
              </div>
            </div>

            {/* Section 2: Safety event timeline */}
            <div>
              <div className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider mb-2">
                Safety Event Timeline
              </div>
              <div className="border border-border bg-card p-4">
                <EventTimeline events={events?.events ?? []} />
              </div>
            </div>

            {/* Section 3: Social metrics */}
            <div>
              <div className="font-mono text-[9px] text-muted-foreground/50 uppercase tracking-wider mb-2">
                Social Metrics Summary
              </div>
              <div className="border border-border bg-card p-4">
                <SocialMetrics social={social} />
              </div>
            </div>
          </div>
        )}

        {!loading && !selectedTs && (
          <div className="p-6 font-mono text-[9px] text-muted-foreground/25">
            No runs available. Run: ./scripts/isaaclab/run_hospital.sh
          </div>
        )}
      </div>
    </div>
  );
}

// ── Page root ─────────────────────────────────────────────────────────────────

type Tab = "live" | "runs";

export default function DigitalTwinPage() {
  const [tab, setTab] = useState<Tab>("live");

  const tabCls = (t: Tab) =>
    [
      "px-4 py-2 font-mono text-[9px] uppercase tracking-wider border-b-2 transition-colors",
      tab === t
        ? "border-foreground text-foreground/80"
        : "border-transparent text-muted-foreground/50 hover:text-muted-foreground/70",
    ].join(" ");

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Tab bar */}
      <div className="flex shrink-0 border-b border-border px-4 gap-2">
        <button className={tabCls("live")} onClick={() => setTab("live")}>
          Live Twin
        </button>
        <button className={tabCls("runs")} onClick={() => setTab("runs")}>
          Run Viewer
        </button>
      </div>

      {/* Tab content */}
      {tab === "live" && <LiveTwinTab />}
      {tab === "runs" && <RunViewerTab />}
    </div>
  );
}
