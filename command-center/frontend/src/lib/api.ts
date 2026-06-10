const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Static mode: Vercel deployment has no backend — use bundled public assets.
const IS_STATIC = process.env.NEXT_PUBLIC_API_MODE === "static";

// Public evidence root bundled into the Next.js static build.
const STATIC_EVIDENCE = "/evidence/isaac/latest";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

/** Fetch from a public/ static asset path (works on Vercel without a backend). */
async function getStatic<T>(staticPath: string): Promise<T> {
  const res = await fetch(staticPath, { cache: "no-store" });
  if (!res.ok) throw new Error(`GET ${staticPath} → ${res.status}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

async function del(path: string): Promise<void> {
  await fetch(`${BASE}${path}`, { method: "DELETE" });
}

export type ScriptInfo = {
  key: string;
  label: string;
  description: string;
  preset: string;
  backend: string;
  estimated_s: number | null;
};

export type JobStatus = {
  job_id: string;
  script_key: string;
  label: string;
  status: "queued" | "running" | "done" | "error" | "killed";
  pid: number | null;
  exit_code: number | null;
  started_at: number | null;
  finished_at: number | null;
};

export type RunSummary = {
  run_id: string;
  model: string;
  fleetsafe: boolean;
  backend: string;
  timestamp_utc: string;
  n_episodes: number;
  success_rate: number;
  collision_rate: number;
  spl_mean: number;
  intervention_rate_mean: number;
  inference_latency_ms_mean: number;
  claim_scope: string;
};

export type RunDetail = RunSummary & {
  metrics: Record<string, unknown>;
  metadata: Record<string, unknown>;
  by_scene: Record<string, unknown>;
  episodes: Record<string, unknown>[];
  files: { name: string; rel: string; size: number }[];
};

export const api = {
  get: <T>(path: string)             => get<T>(path),
  health: ()                         => get<{ status: string; version: string }>("/api/health"),
  git:    ()                         => get<{ commit: string; branch: string }>("/api/git"),
  scripts: ()                        => get<ScriptInfo[]>("/api/scripts"),
  launch: (script_key: string, extra_args: string[] = []) =>
    post<JobStatus>("/api/launch", { script_key, extra_args }),
  jobs:     ()                       => get<JobStatus[]>("/api/jobs"),
  job:      (id: string)             => get<JobStatus>(`/api/jobs/${id}`),
  jobTail:  (id: string, n = 200)    => get<{ lines: string[] }>(`/api/jobs/${id}/tail?n=${n}`),
  killJob:  (id: string)             => del(`/api/jobs/${id}`),
  runs:     ()                       => get<RunSummary[]>("/api/runs"),
  run:      (id: string)             => get<RunDetail>(`/api/runs/${id}`),
  fileUrl:  (run_id: string, rel: string) =>
    `${BASE}/api/runs/${run_id}/file?rel=${encodeURIComponent(rel)}`,
};

export function logsWsUrl(job_id: string): string {
  const ws = BASE.replace(/^http/, "ws");
  return `${ws}/api/ws/logs/${job_id}`;
}

// ── Replay types ───────────────────────────────────────────────────────────────

export type ReplayRun = {
  run_id: string;
  model: string;
  fleetsafe: boolean;
  backend: string;
  n_episodes: number;
};

export type ReplayEpisode = {
  ep_id: string;
  scene: string;
  seed: number;
  success: boolean;
  spl: number;
  collision_count: number;
  intervention_count: number;
  n_steps: number;
  n_events: number;
};

export type TrajPoint = {
  step: number;
  x: number;
  y: number;
  heading: number;
  latency_ms: number;
};

export type ActionRow = {
  step: number;
  raw_vx: number; raw_vy: number; raw_wz: number;
  safe_vx: number; safe_vy: number; safe_wz: number;
  delta_l2: number;
  intervened: number;
  min_dist_m: number;
};

export type SafetyEvent = {
  step: number;
  type: "intervention" | "near_miss" | "collision";
  min_dist_m: number;
  raw_vx: number; raw_wz: number;
  safe_vx: number; safe_wz: number;
};

export type CompareResult = {
  a: { run_id: string; meta: Record<string,unknown>|null; trajectory: TrajPoint[]; actions: ActionRow[]; events: SafetyEvent[] };
  b: { run_id: string; meta: Record<string,unknown>|null; trajectory: TrajPoint[]; actions: ActionRow[]; events: SafetyEvent[] };
};

// ── Isaac types ────────────────────────────────────────────────────────────────

export type IsaacStatus = {
  isaac_live: boolean;
  webrtc_live: boolean;
  http_url: string;
  stream_status: string;
};

export const replayApi = {
  runs:       ()                                   => get<ReplayRun[]>("/api/replay/runs"),
  episodes:   (run_id: string)                     => get<ReplayEpisode[]>(`/api/replay/${run_id}/episodes`),
  meta:       (run_id: string, ep_id: string)      => get<Record<string,unknown>>(`/api/replay/${run_id}/${ep_id}/meta`),
  trajectory: (run_id: string, ep_id: string)      => get<TrajPoint[]>(`/api/replay/${run_id}/${ep_id}/trajectory`),
  actions:    (run_id: string, ep_id: string)      => get<ActionRow[]>(`/api/replay/${run_id}/${ep_id}/actions`),
  events:     (run_id: string, ep_id: string)      => get<SafetyEvent[]>(`/api/replay/${run_id}/${ep_id}/events`),
  compare:    (run_a: string, run_b: string, ep_id: string) =>
    get<CompareResult>(`/api/replay/compare/${run_a}/${run_b}/${ep_id}`),
};

export type PhotorealStatus = {
  status: "PROVEN" | "PROCEDURAL" | "MISSING" | "NOT_RUN";
  usd_loaded: boolean;
  usd_path: string | null;
  usd_size_kb?: number;
  screenshot: string | null;
  capture_method: string | null;
  scene: string | null;
  scenario: string | null;
  timestamp: string | null;
  isaac_version: string | null;
  photoreal_claimed?: boolean;
  honest_label?: string | null;
};

export type AssetStatus = {
  usd_found: boolean;
  usd_path: string;
  size_kb: number;
  generate_cmd: string;
  capture_cmd: string;
};

export const isaacApi = {
  status:           ()                                           => get<IsaacStatus>("/api/isaac/status"),
  scenes:           ()                                           => get<string[]>("/api/isaac/scenes"),
  start:            (scene: string, extra_args: string[] = [])  => post<{job_id:string;status:string}>("/api/isaac/start", { scene, extra_args }),
  stop:             ()                                           => post<{killed:string[]}>("/api/isaac/stop", {}),
  benchmark:        (scene: string, extra_args: string[] = [])  => post<{job_id:string;status:string}>("/api/isaac/benchmark", { scene, extra_args }),
  loadScene:        (scene: string)                              => post<{scene:string;response:unknown}>(`/api/isaac/load-scene/${scene}`, {}),
  snapshot:         ()                                           => post<{snapshot:unknown}>("/api/isaac/snapshot", {}),
  photorealStatus:  ()                                           => IS_STATIC
    ? getStatic<PhotorealStatus>(`${STATIC_EVIDENCE}/photoreal_status.json`)
    : get<PhotorealStatus>("/api/isaac/photoreal-status"),
  assetStatus:      ()                                           => IS_STATIC
    ? Promise.resolve<AssetStatus>({ usd_found: true, usd_path: "hospital_world.usd", size_kb: 8.2, generate_cmd: "", capture_cmd: "" })
    : get<AssetStatus>("/api/isaac/asset-status"),
  screenshotUrl:    ()                                           => IS_STATIC
    ? `${STATIC_EVIDENCE}/procedural_preview.png`
    : `${BASE}/api/isaac/screenshot`,
  /** URL for the run-specific procedural preview */
  previewUrl:       (timestamp: string)                          => IS_STATIC
    ? `${STATIC_EVIDENCE}/procedural_preview.png`
    : `${BASE}/api/isaac/run/${timestamp}/preview`,
};

// ── Fleet types ────────────────────────────────────────────────────────────────

export type RobotSnapshot = {
  robot_id: string;
  name: string;
  robot_type: "real" | "simulated" | "unknown";
  status: "online" | "offline" | "mission" | "error" | "estop";
  zone: "GREEN" | "AMBER" | "RED";
  risk: number;
  crowding_risk: number;
  battery_pct: number | null;
  battery_charging: boolean;
  odom: { x: number; y: number; heading: number };
  cmd_vel: { vx: number; vy: number; wz: number };
  active_mission_id: string | null;
  intervention_active: boolean;
  detection_count: number;
  tracked_count: number;
  latency_ms: number;
  source: string;
};

export type FleetSnapshot = {
  robots: RobotSnapshot[];
  estopped: string[];
  timestamp: number;
};

export type FleetSafetyEvent = {
  event_id: string;
  robot_id: string;
  event_type: "intervention" | "near_miss" | "collision" | "estop" | "zone_change";
  severity: "info" | "warning" | "critical";
  timestamp: number;
  zone: string;
  risk: number;
  min_dist_m: number | null;
  details: Record<string, unknown>;
};

export type Mission = {
  mission_id: string;
  robot_id: string;
  scene: string;
  goal_description: string;
  priority: number;
  status: "queued" | "dispatching" | "running" | "done" | "failed" | "cancelled";
  created_at: number;
  started_at: number | null;
  finished_at: number | null;
  result: Record<string, unknown> | null;
};

export type RecordingSession = {
  session_id: string;
  robot_id: string;
  started_at: number;
  stopped_at: number | null;
  n_frames: number;
  n_events: number;
  is_active: boolean;
};

export const fleetApi = {
  robots:   ()                    => get<RobotSnapshot[]>("/api/fleet/robots"),
  robot:    (id: string)          => get<RobotSnapshot>(`/api/fleet/robots/${id}`),
  estop:    (id: string)          => post<{robot_id:string;event:unknown}>(`/api/safety/estop/${id}`, {}),
  estopAll: ()                    => post<{estopped:string[]}>("/api/safety/estop/all", {}),
  clearEstop:(id: string)         => post<{cleared:boolean}>(`/api/safety/clear/${id}`, {}),
};

export const missionApi = {
  list:   (robot_id?: string)     => get<Mission[]>(`/api/missions${robot_id ? `?robot_id=${robot_id}` : ""}`),
  create: (body: { robot_id: string; scene: string; goal_description?: string; priority?: number }) =>
    post<Mission>("/api/missions", body),
  cancel: (id: string)            => del(`/api/missions/${id}`),
  get:    (id: string)            => get<Mission>(`/api/missions/${id}`),
};

export const sessionApi = {
  list:       ()                  => get<RecordingSession[]>("/api/sessions"),
  start:      (robot_id: string)  => post<RecordingSession>("/api/sessions/start", { robot_id }),
  stop:       (id: string)        => post<RecordingSession>(`/api/sessions/${id}/stop`, {}),
  trajectory: (id: string)        => get<TrajPoint[]>(`/api/sessions/${id}/trajectory`),
  events:     (id: string)        => get<FleetSafetyEvent[]>(`/api/sessions/${id}/events`),
};

export function fleetWsUrl(): string {
  const ws = BASE.replace(/^http/, "ws");
  return `${ws}/api/fleet/ws`;
}

export function safetyWsUrl(): string {
  const ws = BASE.replace(/^http/, "ws");
  return `${ws}/api/safety/ws`;
}

// ── Commissioning types ────────────────────────────────────────────────────────

export type CommissioningState =
  | "DISARMED"
  | "MONITOR"
  | "ESTOP_VALIDATED"
  | "ARMED"
  | "RELAY_ENABLED";

export type CommissioningStatus = {
  state: CommissioningState;
  robot_id: string | null;
  checklist: Record<string, boolean>;
  checklist_labels: Record<string, string>;
  estop_test_result: { passed: boolean; latency_ms: number; note: string } | null;
  session_id: string | null;
  armed_at: number | null;
  relay_enabled_at: number | null;
  last_event: string;
  last_event_ts: number;
  can_arm: boolean;
  can_relay: boolean;
};

export const commissioningApi = {
  status:        ()                    => get<CommissioningStatus>("/api/commissioning/status"),
  connect:       (robot_id: string)    => post<CommissioningStatus>("/api/commissioning/connect", { robot_id }),
  disconnect:    ()                    => post<CommissioningStatus>("/api/commissioning/disconnect", {}),
  check:         ()                    => post<CommissioningStatus>("/api/commissioning/check", {}),
  estopTest:     ()                    => post<CommissioningStatus>("/api/commissioning/estop-test", {}),
  arm:           ()                    => post<CommissioningStatus>("/api/commissioning/arm", {}),
  disarm:        ()                    => post<CommissioningStatus>("/api/commissioning/disarm", {}),
  enableRelay:   ()                    => post<CommissioningStatus>("/api/commissioning/relay/enable", {}),
  disableRelay:  ()                    => post<CommissioningStatus>("/api/commissioning/relay/disable", {}),
  emergencyStop: ()                    => post<CommissioningStatus>("/api/commissioning/emergency-stop", {}),
  linkSession:   (session_id: string)  => post<{ok:boolean}>("/api/commissioning/session", { session_id }),
  reportUrl:     (session_id: string)  => `${BASE}/api/commissioning/report/${session_id}`,
};

// ── Robot operator controls ────────────────────────────────────────────────────

export type OpResult = {
  ok: boolean;
  dry_run: boolean;
  op: string;
  output?: string;
  error?: string;
  cmd?: string;
};

export type RelayGuardResult = {
  pass: boolean;
  dry_run: boolean;
  checks: { id: string; label: string; pass: boolean; detail: string }[];
};

export type GraphResult = {
  ok: boolean;
  dry_run: boolean;
  nodes: string[];
  topics: string[];
};

export type AuditEntry = {
  ts: number;
  op: string;
  args: Record<string, unknown>;
  result: string;
  dry_run: boolean;
};

export const robotApi = {
  status:          ()                                              => get<{ host: string; dry_run: boolean }>("/api/robot/status"),
  setDryRun:       (enabled: boolean)                             => post<{ dry_run: boolean }>("/api/robot/dry-run", { enabled }),
  relayGuard:      ()                                             => get<RelayGuardResult>("/api/robot/relay-guard"),
  graph:           ()                                             => get<GraphResult>("/api/robot/graph"),
  auditLog:        (n?: number)                                   => get<AuditEntry[]>(`/api/robot/audit${n ? `?n=${n}` : ""}`),
  startAgent:      ()                                             => post<OpResult>("/api/robot/start-agent", {}),
  startFleetsafe:  ()                                             => post<OpResult>("/api/robot/start-fleetsafe", {}),
  stopFleetsafe:   ()                                             => post<OpResult>("/api/robot/stop-fleetsafe", {}),
  stopConflicting: ()                                             => post<OpResult>("/api/robot/stop-conflicting", {}),
  startRelay:      ()                                             => post<OpResult>("/api/robot/relay/start", {}),
  stopRelay:       ()                                             => post<OpResult>("/api/robot/relay/stop", {}),
  zero:            ()                                             => post<OpResult>("/api/robot/zero", {}),
  pulse:           (vx: number, vy: number, wz: number, ms = 300) => post<OpResult>("/api/robot/pulse", { vx, vy, wz, duration_ms: ms }),
  pulseForward:    ()                                             => post<OpResult>("/api/robot/pulse/forward", {}),
  pulseBack:       ()                                             => post<OpResult>("/api/robot/pulse/back", {}),
  pulseLeft:       ()                                             => post<OpResult>("/api/robot/pulse/left", {}),
  pulseRight:      ()                                             => post<OpResult>("/api/robot/pulse/right", {}),
  voiceMap:        ()                                             => get<{ map: Record<string, string> }>("/api/robot/voice-map"),

  // v0.7 safety supervisor
  estopStatus:     ()                    => get<LatchStatus>("/api/robot/estop/status"),
  estopLatch:      (reason?: string)     => post<LatchStatus>(`/api/robot/estop${reason ? `?reason=${encodeURIComponent(reason)}` : ""}`, {}),
  estopClear:      (operator?: string)   => post<LatchStatus>("/api/robot/estop/clear", { operator: operator ?? "operator" }),

  relayStatus:     ()                    => get<RelayStatus>("/api/robot/relay/status"),
  relayManagedStart: ()                  => post<OpResult>("/api/robot/relay/managed-start", {}),
  relayManagedStop:  (reason?: string)   => post<OpResult>(`/api/robot/relay/managed-stop${reason ? `?reason=${encodeURIComponent(reason)}` : ""}`, {}),

  watchdogStatus:  ()                    => get<WatchdogStatus>("/api/robot/watchdog/status"),
  watchdogStart:   ()                    => post<{ running: boolean }>("/api/robot/watchdog/start", {}),
  watchdogStop:    ()                    => post<{ running: boolean }>("/api/robot/watchdog/stop", {}),

  demoStart:       ()                    => post<{ ok: boolean; state: string }>("/api/robot/demo/start", {}),
  demoAbort:       ()                    => post<{ ok: boolean; state: string }>("/api/robot/demo/abort", {}),
  demoStatus:      ()                    => get<DemoStatus>("/api/robot/demo/status"),

  sessionStart:    (robot_id: string)    => post<RealSession>("/api/robot/session/start", { robot_id }),
  sessionStop:     (id: string)          => post<RealSession>(`/api/robot/session/stop/${id}`, {}),
  sessionList:     ()                    => get<RealSession[]>("/api/robot/session/list"),

  yoloStatus:      ()                    => get<YoloStatus>("/api/robot/yolo/status"),
  yoloStart:       ()                    => post<{ ok: boolean; dry_run: boolean; op: string }>("/api/robot/yolo/start", {}),
  yoloStop:        ()                    => post<{ ok: boolean; dry_run: boolean; op: string }>("/api/robot/yolo/stop", {}),

  preflight:       ()                    => get<PreflightResult>("/api/robot/preflight"),
  killLaunchSource:(node_name: string)   => post<OpResult>("/api/robot/preflight/kill", { node_name }),
};

// ── v0.7 types ─────────────────────────────────────────────────────────────────

export type LatchStatus = {
  latched: boolean;
  reason: string;
  latch_ts: number | null;
  clear_count: number;
  last_clear: { cleared_at: number; operator: string; was_reason: string } | null;
};

export type RelayStatus = {
  active: boolean;
  start_time: number | null;
  uptime_s: number | null;
  stop_reason: string;
};

export type WatchdogStatus = {
  running: boolean;
  last_check: number | null;
  last_ok: number | null;
  consecutive_failures: number;
  total_triggers: number;
  log: { ts: number; event: string; detail: string }[];
};

export type DemoStatus = {
  state: string;
  log: string[];
  start_ts: number | null;
  end_ts: number | null;
};

export type RealSession = {
  session_id: string;
  robot_id: string;
  bag_path: string;
  started_at: number;
  stopped_at: number | null;
  duration_s: number | null;
  topics: string[];
  n_topics: number;
  sha256: string | null;
  evidence_id: string | null;
  ok: boolean;
};

export type YoloStatus = {
  active: boolean;
  mode: "yolo" | "mock";
  started_at: number | null;
  uptime_s: number | null;
  model_path: string;
  package: string;
  dry_run: boolean;
};

export type PreflightPublisher = {
  node: string;
  verdict: "ALLOWED" | "BLOCKED";
  kill_cmd: string | null;
};

export type PreflightResult = {
  pass: boolean;
  dry_run: boolean;
  publishers: PreflightPublisher[];
  blocked: string[];
  safe_graph: RelayGuardResult;
};

// ── Evidence v0.8 types ────────────────────────────────────────────────────────

export type LedgerEntry = {
  id: string;
  timestamp: number;
  claim_scope: string;
  source: string;
  ground_truth_type: string;
  description: string;
  sha256: string | null;
  artifact_path: string | null;
  robot_id: string | null;
  operator: string;
  git_commit: string | null;
  host: string;
  metadata: Record<string, unknown>;
};

export type EvidenceStats = {
  total: number;
  hashed: number;
  by_source: Record<string, number>;
  by_scope: Record<string, number>;
};

export type EvidenceManifest = {
  generated_at: number;
  categories: Record<string, {
    present: boolean;
    count: number;
    description: string;
    ground_truth_type: string;
    missing_warning?: string;
  }>;
  summary: {
    total_items: number;
    categories_present: number;
    categories_total: number;
    defensibility_score: string;
  };
};

export type TrainingStatus = {
  ppo: {
    status: string;
    shim_exists: boolean;
    checkpoint_count: number;
    training_active: boolean;
    has_rl_scripts: boolean;
    notes: string[];
    warning?: string;
  };
  wandb: {
    status: string;
    runs?: Record<string, unknown>[];
    warning?: string;
  };
  huggingface: {
    status: string;
    runs?: Record<string, unknown>[];
    warning?: string;
  };
};

export type Ros2Status = {
  online: boolean;
  mode: string;
  host: string;
  nodes: string[];
  topics: string[];
  rates_hz: Record<string, number | string>;
  missing_nodes?: string[];
  missing_topics?: string[];
  domain_id?: number;
  warning?: string;
};

export type TimelineEvent = {
  ts: number;
  type: "benchmark_run" | "evidence" | "audit" | string;
  scope?: string;
  source?: string;
  description: string;
  sha256?: string;
  run_id?: string;
  dry_run?: boolean;
};

export type HeatmapCell = {
  x: number;
  y: number;
  collisions: number;
  interventions: number;
  path_count: number;
};

export type HeatmapData = {
  cells: HeatmapCell[];
  bounds: { x_min: number; x_max: number; y_min: number; y_max: number } | null;
  total_collisions?: number;
  total_interventions?: number;
  total_path_samples?: number;
  warning?: string;
};

// ── Experiment registry v0.9 types ────────────────────────────────────────────

export type EvidenceStatus = "PROVEN" | "PRELIMINARY" | "SYNTHETIC" | "RECORDED_ONLY" | "NOT_VALIDATED";

export type ExperimentRun = {
  run_id: string;
  git_commit: string;
  timestamp: number | null;
  backbone: string;
  backbone_raw: string;
  safety_mode: string;
  backend: string;
  backend_raw: string;
  scene: string;
  seed: number;
  n_episodes: number;
  robot: string;
  sim_type: string;
  evidence_status: EvidenceStatus;
  artifacts: {
    metrics_path: string | null;
    by_scene_path: string | null;
    episodes_dir: string | null;
    video_path: string | null;
    bag_path: string | null;
  };
  hashes: Record<string, string | null>;
  paper_metrics: Record<string, number | null>;
  claim_scope: string;
};

export type RegistrySummary = {
  total_runs: number;
  backbones: string[];
  safety_modes: string[];
  by_status: Record<string, number>;
  n_proven: number;
  n_preliminary: number;
  n_synthetic: number;
};

export type CompareResult2 = {
  backbone: string;
  backend: string;
  n_baseline: number;
  n_fleetsafe: number;
  baseline_avg: Record<string, number | null>;
  fleetsafe_avg: Record<string, number | null>;
  delta_pct: Record<string, number | null>;
  evidence_status: EvidenceStatus;
};

export type PaperMetricRow = {
  backbone: string;
  safety_mode: string;
  n_runs: number;
  backend: string;
  evidence_status: EvidenceStatus;
  metrics: Record<string, {
    value: number | null;
    n: number;
    ci_95: [number, number] | null;
    status: EvidenceStatus;
    note: string;
  }>;
};

export type ClaimValidation = {
  claims: {
    claim: string;
    status: EvidenceStatus | "PARTIAL";
    evidence: string;
    gap: string | null;
  }[];
  summary: {
    total: number;
    proven: number;
    preliminary: number;
    partial?: number;
    recorded_only: number;
    not_validated: number;
    readiness_pct: number;
  };
};

export type SimEvidenceItem = {
  name: string;
  status: string;
};

export type SimEvidenceStatus = {
  items: SimEvidenceItem[];
  overall_pct: number;
  isaac: {
    status: string;
    honest_label?: string;
    procedural?: string;
    photoreal?: string;
    isaac_sim?: string;
    do_not_claim?: string[];
    guidance?: string;
  };
  ppo: {
    PPO_FULL_TRAINING: string;
    PPO_SMOKE_TRAINING: string;
    run_id?: string;
    mean_reward?: number;
    n_steps?: number;
    guidance?: string;
  };
  wandb_hf: {
    wandb: string;
    hf: string;
    wandb_detail?: string;
    hf_detail?: string;
    guidance?: string;
  };
  smoke_matrix: {
    status: string;
    n_ok?: number;
    n_total?: number;
    readiness_pct?: number;
    guidance?: string;
  };
  bundle: {
    status: string;
    bundle_dir?: string;
    overall_pct?: number;
    ready?: boolean;
    guidance?: string;
  };
};

// ── Publication run scanner types ──────────────────────────────────────────────

export type PublicationRunResult = {
  model: string;
  scene: string;
  fleetsafe: boolean;
  collision_rate: number;
  intervention_rate_mean: number;
  n_episodes: number;
  spl_mean: number;
  inference_latency_ms_mean?: number | null;
  min_obstacle_distance_m_mean?: number | null;
};

export type ProvenDetail = {
  seeds_ok: boolean;
  collision_ok: boolean;
  coverage_ok: boolean;
  cbf_ok: boolean;
  photoreal_ok?: boolean;
  cbf_per_model?: Record<string, boolean>;
  cbf_detail?: Record<string, number>;
  collision_detail?: Record<string, boolean>;
};

export type PublicationRun = {
  run_id: string;
  timestamp: string;
  backend: "mujoco" | "isaaclab";
  n_seeds: number;
  models: string[];
  n_results: number;
  expected_combos: number;
  progress_pct: number;
  complete: boolean;
  proven: boolean;
  proven_detail: ProvenDetail;
  backbone_results: PublicationRunResult[];
  evidence_tier: string;
  photoreal: boolean;
  mtime: number;
};

export type LiveRunEta = {
  active_combo: string;
  n_episodes_done: number;
  episode_rate_per_min: number;
  eta_min: number | null;
  last_ep_age_s: number;
};

export type LiveRunStatus = {
  status: "running" | "idle" | "none";
  in_progress: PublicationRun[];
  latest_complete: PublicationRun[];
  all_isaac: PublicationRun[];
  eta?: LiveRunEta;
};

export type CrossBackendRow = {
  backend: string;
  model: string;
  scene: string;
  fleetsafe: boolean;
  collision_rate: number;
  intervention_rate_mean: number;
  n_episodes: number;
  spl_mean: number;
  inference_latency_ms_mean?: number | null;
  min_obstacle_distance_m_mean?: number | null;
  path_length_m_mean?: number | null;
  raw_vs_safe_delta_l2_mean?: number | null;
  smoothness_mean?: number | null;
  steps_green_mean?: number | null;
  steps_amber_mean?: number | null;
  steps_red_mean?: number | null;
  near_violation_count_mean?: number | null;
};

export type CrossBackendComparison = {
  mujoco: {
    run_id: string | null;
    proven: boolean;
    n_seeds: number;
    rows: CrossBackendRow[];
    proven_detail: ProvenDetail;
  };
  isaaclab: {
    run_id: string | null;
    proven: boolean;
    n_seeds: number;
    complete: boolean;
    progress_pct: number;
    rows: CrossBackendRow[];
    proven_detail: ProvenDetail;
  };
  generated_at: number;
};

export type IsaacProgressCombo = {
  model: string;
  scene: string;
  mode: string;
  n_done: number;
  n_target: number;
  done: boolean;
  collision_rate?: number | null;
  intervention_rate?: number | null;
};

export type IsaacProgress = {
  run_id: string | null;
  combos: IsaacProgressCombo[];
  total_combos_done: number;
  total_combos: number;
  total_eps_done: number;
  total_eps_target: number;
  progress_pct: number;
};

export const experimentsApi = {
  runs:       (params?: { backbone?: string; backend?: string; safety_mode?: string }) => {
    const q = new URLSearchParams(
      Object.entries(params ?? {}).filter(([, v]) => v) as [string, string][]
    ).toString();
    return get<ExperimentRun[]>(`/api/experiments/runs${q ? `?${q}` : ""}`);
  },
  run:        (id: string)              => get<ExperimentRun>(`/api/experiments/runs/${id}`),
  summary:    ()                        => get<RegistrySummary>("/api/experiments/summary"),
  compare:    (backbone: string, backend?: string) =>
    get<CompareResult2>(`/api/experiments/compare/${backbone}${backend ? `?backend=${backend}` : ""}`),
  table:      (backend?: string)        => get<{ table: PaperMetricRow[]; n_total_runs: number }>(`/api/experiments/table${backend ? `?backend=${backend}` : ""}`),
  deltas:     ()                        => get<CompareResult2[]>("/api/experiments/deltas"),
  claims:     ()                        => IS_STATIC
    ? getStatic<ClaimValidation>("/evidence/claims.json")
    : get<ClaimValidation>("/api/experiments/claims"),
  export:     ()                        => post<{ ok: boolean; output_dir: string; files: string[] }>("/api/experiments/export", {}),
  manifest:   ()                        => get<{ total_runs: number; entries: unknown[] }>("/api/experiments/manifest"),
  figureData: ()                        => get<Record<string, unknown>>("/api/experiments/figure-data"),
  simEvidence: ()                       => get<SimEvidenceStatus>("/api/experiments/sim-evidence-status"),
  publicationRuns: ()                   => get<PublicationRun[]>("/api/experiments/publication-runs"),
  liveRun:    ()                        => IS_STATIC
    ? getStatic<LiveRunStatus>("/evidence/live-run.json")
    : get<LiveRunStatus>("/api/experiments/live-run"),
  crossBackend: ()                      => IS_STATIC
    ? getStatic<CrossBackendComparison>("/evidence/cross-backend.json")
    : get<CrossBackendComparison>("/api/experiments/cross-backend"),
  isaacProgress: ()                     => IS_STATIC
    ? Promise.reject(new Error("static"))
    : get<IsaacProgress>("/api/experiments/isaac-progress"),
};

// ── Console API ────────────────────────────────────────────────────────────────

export interface ConsoleExecResult {
  command: string;
  output: string;
  ok: boolean;
  dry_run: boolean;
  timestamp: string;
}

export const consoleApi = {
  exec:     (command: string): Promise<ConsoleExecResult> => post<ConsoleExecResult>("/api/robot/console/exec", { command }),
  commands: (): Promise<string[]>                          => get<string[]>("/api/robot/console/commands"),
};

// ── ROS Graph API ──────────────────────────────────────────────────────────────

export interface RosNodeState {
  id: string;
  label: string;
  state: "ok" | "warn" | "err" | "unknown";
}

export interface RosEdgeState {
  id: string;
  from_node: string;
  to_node: string;
  topic: string;
  state: "flowing" | "blocked" | "unknown";
  hz?: number | null;
}

export interface RosGraphState {
  overall: "GREEN" | "YELLOW" | "RED" | "ESTOP";
  nodes: RosNodeState[];
  edges: RosEdgeState[];
  intervention_active: boolean;
  estop_latched: boolean;
  relay_open: boolean;
  watchdog_armed: boolean;
  unsafe_publisher?: string | null;
}

export const rosGraphApi = {
  state: (): Promise<RosGraphState> => get<RosGraphState>("/api/robot/ros-graph"),
};

// ── Isaac extras ───────────────────────────────────────────────────────────────

export const isaacExtrasApi = {
  sensorDegradation: (config: Record<string, unknown>): Promise<{ applied: boolean; dry_run: boolean }> =>
    post<{ applied: boolean; dry_run: boolean }>("/api/isaac/sensor-degradation", config),
  pedestrianScenario: (scene: string, scenario: string): Promise<{ applied: boolean; dry_run: boolean }> =>
    post<{ applied: boolean; dry_run: boolean }>("/api/isaac/pedestrian-scenario", { scene, scenario }),
  recoveryTest: (test_type: string): Promise<{ applied: boolean; dry_run: boolean }> =>
    post<{ applied: boolean; dry_run: boolean }>("/api/isaac/recovery-test", { test_type }),
};

// ── Hospital Run History types ─────────────────────────────────────────────────

export interface HospitalRun {
  timestamp: string;
  scene: string;
  scenario: string;
  has_preview: boolean;
  has_screenshot: boolean;
  has_trajectory: boolean;
  has_events: boolean;
  isaac_runtime: string;
  usd_asset: string;
}

export interface HospitalTrajectory {
  steps: number;
  points: [number, number, number][]; // [step, x, y]
}

export interface HospitalEvents {
  events: Record<string, unknown>[];
}

export interface HospitalSocial {
  n_steps: number;
  min_interpersonal_dist_mean?: number;
  ttc_mean?: number;
  stop_count_total?: number;
  hesitation_latency_mean?: number;
}

export const hospitalApi = {
  runs:          ()             => get<HospitalRun[]>("/api/isaac/runs"),
  session:       (ts: string)  => get<Record<string, unknown>>(`/api/isaac/run/${ts}/session`),
  trajectory:    (ts: string)  => get<HospitalTrajectory>(`/api/isaac/run/${ts}/trajectory`),
  events:        (ts: string)  => get<HospitalEvents>(`/api/isaac/run/${ts}/events`),
  social:        (ts: string)  => get<HospitalSocial>(`/api/isaac/run/${ts}/social`),
  preview:       (ts: string)  => `${BASE}/api/isaac/run/${ts}/preview`,
  captureStatus: (ts: string)  => get<Record<string, unknown>>(`/api/isaac/run/${ts}/capture-status`),
};

export const evidenceApi = {
  ledger:          (source?: string, n = 200)  => get<LedgerEntry[]>(`/api/evidence/ledger?n=${n}${source ? `&source=${source}` : ""}`),
  record:          (body: {
    claim_scope: string; source: string; ground_truth_type: string;
    description: string; artifact_path?: string; robot_id?: string;
    operator?: string; metadata?: Record<string, unknown>;
  })                                            => post<LedgerEntry>("/api/evidence/record", body),
  stats:           ()                           => get<EvidenceStats>("/api/evidence/stats"),
  manifest:        ()                           => get<EvidenceManifest>("/api/evidence/manifest"),
  rebuildManifest: ()                           => post<EvidenceManifest>("/api/evidence/manifest/rebuild", {}),
  trainingStatus:  ()                           => get<TrainingStatus>("/api/evidence/training"),
  ros2Status:      ()                           => get<Ros2Status>("/api/evidence/ros2"),
  timeline:        (n = 200)                    => get<TimelineEvent[]>(`/api/evidence/timeline?n=${n}`),
  heatmap:         ()                           => get<HeatmapData>("/api/evidence/heatmap"),
};
