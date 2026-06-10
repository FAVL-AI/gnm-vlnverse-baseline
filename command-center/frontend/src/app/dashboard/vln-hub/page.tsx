"use client";

import { useCallback, useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Types ──────────────────────────────────────────────────────────────────
interface LiveStatus {
  ok: boolean;
  isaac: {
    camera_status: string;
    camera_path: string | null;
    camera_is_first_person: boolean;
    camera_ok: boolean;
    camera_outside_isaac: boolean;
    camera_report_exists: boolean;
    scene_valid_for_evidence: boolean;
    scene_invalid_reasons: string[];
    has_yahboom_staged: boolean;
    yahboom_stage_status: string;
    camera_instructions: string;
  };
  iamgoodnavigator: {
    available: boolean;
    demo_py: boolean;
    fine_episodes: number;
    coarse_episodes: number;
    data_downloaded: boolean;
    imported_episodes: number;
    ready: boolean;
    missing: string[];
    scene_exists: boolean;
    expected_scene_path: string | null;
    episode_status: string;
    episode_evidence_valid: boolean;
    scenes_missing_from_disk: string[];
    next_step: string;
  };
  vlntube: {
    repo_available: boolean;
    has_real_data: boolean;
    hf_data_downloaded: boolean;
    usd_scenes: number;
    rgb_images: number;
    instruction_files: number;
  };
  yahboom: {
    urdf_found: boolean;
    usd_exists: boolean;
    usd_path: string | null;
    canonical_urdf: string | null;
    status: string;
    staged: boolean;
    stage_status: string;
    stage_prim_path: string | null;
    stage_instructions: string | null;
    blocked: boolean;
    usd_blocked: boolean;
    block_message: string | null;
    usd_block_message: string | null;
  };
  live_capture: {
    running: boolean;
    last_frame_time: string | null;
    frame_exists: boolean;
    frame_url: string;
    message: string | null;
    tool: string | null;
    start_cmd: string;
  };
  e2e_motion: {
    demo_run: boolean;
    autonomous_robot_control: boolean;
    mode: string;
    e2e_evidence: boolean;
    timesteps: number;
    note: string | null;
  };
  evidence: {
    ready: boolean;
    summary_exists: boolean;
    all_images_present: boolean;
    camera_is_first_person: boolean;
    episode_evidence_valid: boolean;
    yahboom_urdf_exists: boolean;
    yahboom_usd_exists: boolean;
    missing_steps: string[];
  };
  exact_missing_steps: string[];
  blocking_issues: string[];
}

interface EpisodesData {
  count: number;
  episodes: Array<{
    task?: string;
    index?: number;
    status?: string;
    instruction?: string | Record<string, unknown> | null;
    file_counts?: Record<string, number>;
    exit_code?: number;
    name?: string;
  }>;
  has_data: boolean;
  missing_data_message: string | null;
}

function instrText(v: string | Record<string, unknown> | null | undefined): string | null {
  if (!v) return null;
  if (typeof v === "string") return v;
  if (typeof v === "object") {
    const t = (v as Record<string, unknown>).instruction_text;
    if (typeof t === "string") return t;
    return JSON.stringify(v).slice(0, 160);
  }
  return String(v);
}

interface CameraData {
  ok: boolean;
  camera_mode: string;
  selected_camera: string | null;
  is_first_person: boolean;
  all_cameras?: string[];
  message?: string;
  camera_instructions?: string;
}

interface AssetData {
  ok: boolean;
  has_urdf?: boolean;
  has_usd?: boolean;
  best_urdf?: string | null;
  generated_usd?: string | null;
  status?: string;
  assets?: Record<string, number>;
  message?: string;
}

interface VLNHubStatus {
  ok: boolean;
  vlntube: {
    indexed: boolean;
    repo_available: boolean;
    usd_scenes: number;
    rgb_sequences: number;
    scene_graphs: number;
    instruction_files: number;
    indexed_at: string | null;
  };
  vlnverse: {
    indexed: boolean;
    data_available: boolean;
    scene_count: number;
    preview_count: number;
    instruction_count: number;
    trajectory_count: number;
    indexed_at: string | null;
  };
  next_actions: {
    vlntube: string[];
    vlnverse: string[];
  };
}

// ── Small components ────────────────────────────────────────────────────────
function StatusDot({ ok, warn }: { ok: boolean; warn?: boolean }) {
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full shrink-0 ${
        ok ? "bg-emerald-400" : warn ? "bg-amber-400" : "bg-red-500"
      }`}
    />
  );
}

function Cmd({ children }: { children: string }) {
  return (
    <code className="block mt-1 text-[10px] font-mono text-amber-300 bg-zinc-950 rounded px-2 py-1 border border-zinc-800">
      $ {children}
    </code>
  );
}

function BlockBanner({ message }: { message: string }) {
  return (
    <div className="mt-2 bg-red-950 border border-red-800 rounded p-2 text-red-300 text-[10px] font-mono">
      [BLOCKED] {message}
    </div>
  );
}

function ts(iso: string | null) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

// ── Main page ──────────────────────────────────────────────────────────────
export default function VLNHubPage() {
  const [live, setLive]           = useState<LiveStatus | null>(null);
  const [status, setStatus]       = useState<VLNHubStatus | null>(null);
  const [episodes, setEpisodes]   = useState<EpisodesData | null>(null);
  const [camera, setCamera]       = useState<CameraData | null>(null);
  const [assets, setAssets]       = useState<AssetData | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [backendDown, setBackendDown] = useState(false);
  const [liveTs, setLiveTs]       = useState(Date.now());
  const [imgError, setImgError]   = useState(false);

  const fetchAll = useCallback(async () => {
    try {
      const [lRes, sRes, eRes, cRes, aRes] = await Promise.all([
        fetch(`${API}/api/vln-hub/live`),
        fetch(`${API}/api/vln-hub/status`),
        fetch(`${API}/api/vln-hub/imported-episodes`),
        fetch(`${API}/api/vln-hub/camera/latest`),
        fetch(`${API}/api/vln-hub/asset-report`),
      ]);
      if (!lRes.ok && !sRes.ok) { setBackendDown(true); return; }
      setBackendDown(false);
      if (lRes.ok) setLive(await lRes.json());
      if (sRes.ok) setStatus(await sRes.json());
      if (eRes.ok) setEpisodes(await eRes.json());
      if (cRes.ok) setCamera(await cRes.json());
      if (aRes.ok) setAssets(await aRes.json());
    } catch {
      setBackendDown(true);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  // Refresh live frame every 1 second
  useEffect(() => {
    const id = setInterval(() => { setLiveTs(Date.now()); setImgError(false); }, 1000);
    return () => clearInterval(id);
  }, []);

  const doRefresh = async () => {
    setRefreshing(true);
    try {
      await fetch(`${API}/api/vln-hub/refresh`, { method: "POST" });
      await fetchAll();
    } catch {}
    setRefreshing(false);
  };

  const blockers = live?.blocking_issues ?? [];

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 p-6 font-mono">
      {/* Header */}
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">VLN Hub</h1>
          <p className="text-zinc-400 text-sm mt-0.5">
            VLNVerse · IAmGoodNavigator · VLNTube · Yahboom M3 Pro — real imported data
          </p>
        </div>
        <button
          onClick={doRefresh}
          disabled={refreshing}
          className="shrink-0 text-xs bg-zinc-800 border border-zinc-700 hover:bg-zinc-700 disabled:opacity-50 text-zinc-300 rounded px-3 py-1.5 transition"
        >
          {refreshing ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {backendDown && (
        <div className="mb-4 bg-amber-950 border border-amber-800 rounded p-3 text-amber-300 text-xs">
          Backend offline —{" "}
          <code className="text-amber-200">
            cd command-center && python -m uvicorn backend.main:app --port 8000
          </code>
        </div>
      )}

      {/* Evidence readiness banner */}
      {live && (
        <div className={`mb-4 rounded border p-3 text-xs ${
          live.evidence?.ready
            ? "bg-emerald-950 border-emerald-800 text-emerald-300"
            : "bg-zinc-900 border-zinc-700 text-zinc-400"
        }`}>
          <span className="font-semibold">
            {live.evidence?.ready ? "Evidence ready" : "Evidence not yet ready"}
          </span>
          {live.exact_missing_steps?.length > 0 && (
            <ul className="mt-1 space-y-0.5">
              {live.exact_missing_steps.map((b, i) => (
                <li key={i} className="text-red-400">• {b}</li>
              ))}
            </ul>
          )}
          {blockers.length > 0 && live.exact_missing_steps?.length === 0 && (
            <ul className="mt-1 space-y-0.5">
              {blockers.map((b, i) => (
                <li key={i} className="text-amber-400">• {b}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        {/* ── Panel 1: Imported Episodes ─────────────────────────────────── */}
        <div className="bg-zinc-900 rounded-lg border border-zinc-700 p-4">
          <div className="flex items-center gap-2 mb-3">
            <StatusDot ok={!!(episodes?.has_data)} warn={false} />
            <h2 className="text-sm font-semibold text-zinc-300">Imported Episodes</h2>
            {live?.iamgoodnavigator.imported_episodes !== undefined && (
              <span className="ml-auto text-[10px] text-zinc-500">
                {live.iamgoodnavigator.imported_episodes} imported
              </span>
            )}
          </div>

          {/* IAmGoodNavigator clone status */}
          <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-[11px] mb-3">
            <span className="text-zinc-500">Clone present</span>
            <span className={live?.iamgoodnavigator.available ? "text-emerald-400" : "text-red-400"}>
              {live ? (live.iamgoodnavigator.available ? "yes" : "no") : "—"}
            </span>
            <span className="text-zinc-500">demo.py</span>
            <span className={live?.iamgoodnavigator.demo_py ? "text-emerald-400" : "text-red-400"}>
              {live ? (live.iamgoodnavigator.demo_py ? "found" : "missing") : "—"}
            </span>
            <span className="text-zinc-500">Fine episodes</span>
            <span className="text-zinc-200">{live?.iamgoodnavigator.fine_episodes ?? "—"}</span>
            <span className="text-zinc-500">Coarse episodes</span>
            <span className="text-zinc-200">{live?.iamgoodnavigator.coarse_episodes ?? "—"}</span>
          </div>

          {/* Scene existence warning */}
          {live && !live.iamgoodnavigator.scene_exists && live.iamgoodnavigator.imported_episodes > 0 && (
            <div className="mb-2 bg-red-950 border border-red-800 rounded p-2 text-red-300 text-[10px]">
              <p className="font-semibold">[BLOCKED] VLN scene USD missing from disk.</p>
              <p className="text-red-400 mt-0.5 break-all">
                {live.iamgoodnavigator.expected_scene_path ?? "unknown path"}
              </p>
              <Cmd>bash scripts/fix_iamgoodnavigator_asset_paths.sh</Cmd>
            </div>
          )}

          {/* Imported episodes list */}
          {episodes?.has_data ? (
            <ul className="space-y-1.5">
              {episodes.episodes.slice(0, 4).map((ep, i) => {
                const epStatus = ep.status ?? "unknown";
                const statusColor =
                  epStatus === "completed" ? "text-emerald-400" :
                  epStatus === "completed_missing_scene" ? "text-red-400" :
                  epStatus === "completed_no_output" ? "text-amber-400" :
                  epStatus === "failed" ? "text-red-500" : "text-zinc-500";
                const dotOk = epStatus === "completed";
                const dotWarn = epStatus === "completed_no_output";
                return (
                  <li key={i} className="text-[10px] border border-zinc-800 rounded p-2">
                    <div className="flex items-center gap-2">
                      <StatusDot ok={dotOk} warn={dotWarn} />
                      <span className="text-zinc-300 font-semibold">
                        {ep.task ?? ep.name} #{ep.index ?? ""}
                      </span>
                      <span className={`ml-auto font-mono ${statusColor}`}>
                        {epStatus}
                      </span>
                    </div>
                    {instrText(ep.instruction) && (
                      <p className="text-zinc-500 mt-1 truncate">{instrText(ep.instruction)}</p>
                    )}
                    {ep.file_counts && (
                      <p className={`mt-0.5 ${
                        (ep.file_counts.trajectories ?? 0) === 0 && (ep.file_counts.images ?? 0) === 0
                          ? "text-amber-600" : "text-zinc-600"
                      }`}>
                        traj:{ep.file_counts.trajectories ?? 0}{" "}
                        img:{ep.file_counts.images ?? 0}
                        {(ep.file_counts.trajectories ?? 0) === 0 && (ep.file_counts.images ?? 0) === 0
                          ? " ← no output (run interactively inside Isaac Sim)" : ""}
                      </p>
                    )}
                    {epStatus === "completed_missing_scene" && (
                      <p className="text-red-400 mt-0.5">
                        Scene USD not on disk — episode metadata only, not final evidence.
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
          ) : (
            <div className="text-[11px] text-zinc-500 bg-zinc-800 rounded p-3">
              {episodes?.missing_data_message}
              <Cmd>bash scripts/setup_iamgoodnavigator.sh</Cmd>
              <Cmd>bash scripts/run_iamgoodnavigator_episode.sh fine 0</Cmd>
            </div>
          )}

          {live?.iamgoodnavigator.missing && live.iamgoodnavigator.missing.length > 0 && (
            <BlockBanner message={`Missing: ${live.iamgoodnavigator.missing.join(", ")}`} />
          )}
        </div>

        {/* ── Panel 2: Isaac Live Scene ──────────────────────────────────── */}
        <div className="bg-zinc-900 rounded-lg border border-zinc-700 p-4">
          <div className="flex items-center gap-2 mb-3">
            <StatusDot ok={live?.isaac.camera_ok ?? false} warn={live?.isaac.camera_outside_isaac} />
            <h2 className="text-sm font-semibold text-zinc-300">Isaac Live Scene</h2>
          </div>

          <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-[11px] mb-3">
            <span className="text-zinc-500">Camera status</span>
            <span className={`font-semibold ${
              live?.isaac.camera_ok ? "text-emerald-400" :
              live?.isaac.camera_outside_isaac ? "text-amber-400" : "text-red-400"
            }`}>
              {live?.isaac.camera_status ?? "—"}
            </span>
            <span className="text-zinc-500">First-person</span>
            <span className={live?.isaac.camera_is_first_person ? "text-emerald-400" : "text-red-400"}>
              {live ? (live.isaac.camera_is_first_person ? "yes" : "no") : "—"}
            </span>
            <span className="text-zinc-500">Camera path</span>
            <span className="text-zinc-300 truncate text-[9px]">
              {live?.isaac.camera_path ?? "—"}
            </span>
            <span className="text-zinc-500">Scene valid for evidence</span>
            <span className={live?.isaac.scene_valid_for_evidence ? "text-emerald-400" : "text-zinc-500"}>
              {live ? (live.isaac.scene_valid_for_evidence ? "yes" : "no") : "—"}
            </span>
            <span className="text-zinc-500">Yahboom staged</span>
            <span className={live?.isaac.has_yahboom_staged ? "text-emerald-400" : "text-zinc-500"}>
              {live ? (live.isaac.has_yahboom_staged ? "yes" : "no") : "—"}
            </span>
            <span className="text-zinc-500">VLNTube real data</span>
            <span className={live?.vlntube.has_real_data ? "text-emerald-400" : "text-amber-400"}>
              {live ? (live.vlntube.has_real_data ? "yes" : "no") : "—"}
            </span>
          </div>

          {live?.isaac.camera_outside_isaac && (
            <div className="bg-amber-950 border border-amber-700 rounded p-2 text-amber-300 text-[10px] mb-2">
              Camera report was captured outside Isaac Sim. Run{" "}
              <code className="text-amber-200">scripts/isaac/set_navigation_camera.py</code>{" "}
              <em>inside Isaac Sim</em> to get a valid first-person report.
            </div>
          )}
          {!live?.isaac.camera_ok && !live?.isaac.camera_outside_isaac && (
            <div className="text-[11px] text-zinc-500 bg-zinc-800 rounded p-2">
              <p className="text-zinc-400">{live?.isaac.camera_instructions}</p>
              <Cmd>python.sh scripts/isaac/set_navigation_camera.py</Cmd>
              <p className="mt-1 text-zinc-600">Or in Isaac UI: Perspective → Cameras → FloatingCamera</p>
            </div>
          )}
          {live?.isaac.scene_invalid_reasons && live.isaac.scene_invalid_reasons.length > 0 && (
            <ul className="mt-2 text-[10px] text-red-400 space-y-0.5">
              {live.isaac.scene_invalid_reasons.map((r, i) => (
                <li key={i}>• {r}</li>
              ))}
            </ul>
          )}
          {!live?.vlntube.has_real_data && (
            <div className="mt-2 text-[11px] text-zinc-500">
              <Cmd>bash scripts/download_vlntube_minimal_assets.sh</Cmd>
            </div>
          )}
        </div>

        {/* ── Panel 3: First-Person Camera Preview ──────────────────────── */}
        <div className="bg-zinc-900 rounded-lg border border-zinc-700 p-4">
          <div className="flex items-center gap-2 mb-3">
            <StatusDot ok={camera?.is_first_person ?? false} />
            <h2 className="text-sm font-semibold text-zinc-300">First-Person Camera</h2>
            {camera?.camera_mode && (
              <span className={`ml-auto text-[10px] font-mono px-1.5 py-0.5 rounded ${
                camera.is_first_person
                  ? "bg-emerald-900 text-emerald-300"
                  : "bg-zinc-800 text-zinc-400"
              }`}>
                {camera.camera_mode}
              </span>
            )}
          </div>

          {camera?.is_first_person ? (
            <div className="space-y-2 text-[11px]">
              <p className="text-emerald-400">
                First-person / FloatingCamera selected.
              </p>
              <p className="text-zinc-400">
                Path: <code className="text-zinc-300">{camera.selected_camera}</code>
              </p>

              {/* Live Isaac viewport image — refreshes every 1 second */}
              <div className="relative aspect-video bg-zinc-800 rounded overflow-hidden flex items-center justify-center">
                {!imgError && (live?.live_capture?.frame_exists || true) ? (
                  <img
                    key={liveTs}
                    src={`/live/isaac_live.png?t=${liveTs}`}
                    alt="Isaac live view"
                    className="max-h-full max-w-full rounded object-contain"
                    onError={() => setImgError(true)}
                  />
                ) : null}
                {imgError && (
                  <div className="text-center px-3 text-zinc-500 text-[10px]">
                    <p className="text-amber-400 font-semibold mb-1">Live capture not running</p>
                    <p>Run in a second terminal:</p>
                    <code className="block mt-1 text-amber-300 bg-zinc-900 rounded px-2 py-1">
                      bash scripts/capture_isaac_live.sh
                    </code>
                    {live?.live_capture?.tool && (
                      <p className="mt-1 text-zinc-600">Tool: {live.live_capture.tool}</p>
                    )}
                  </div>
                )}
              </div>

              {/* Live capture status row */}
              <div className="flex items-center gap-2 text-[10px]">
                <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                  live?.live_capture?.running ? "bg-emerald-400" :
                  live?.live_capture?.frame_exists ? "bg-amber-400" : "bg-zinc-600"
                }`} />
                <span className="text-zinc-500">
                  {live?.live_capture?.running
                    ? `Live — ${live.live_capture.tool ?? "capturing"}`
                    : live?.live_capture?.frame_exists
                      ? `Last frame: ${live.live_capture.last_frame_time?.slice(11, 19) ?? "unknown"}`
                      : "Not capturing"}
                </span>
                {!live?.live_capture?.running && (
                  <span className="ml-auto">
                    <code className="text-amber-300 bg-zinc-900 rounded px-1.5 py-0.5">
                      bash scripts/capture_isaac_live.sh
                    </code>
                  </span>
                )}
              </div>

              <p className="text-zinc-600">
                Evidence capture:{" "}
                <code className="text-zinc-500">bash scripts/capture_fleetsafe_evidence.sh</code>
              </p>
            </div>
          ) : (
            <div className="space-y-2 text-[11px]">
              <div className="bg-red-950 border border-red-800 rounded p-2 text-red-300">
                Bird's-eye / top-down camera is NOT accepted as main navigation evidence.
                Set camera to first-person or FloatingCamera.
              </div>
              <p className="text-zinc-400">
                {camera?.camera_instructions ?? camera?.message ??
                 "Run Isaac Sim, open a VLN scene, then set FloatingCamera."}
              </p>
              <Cmd>python.sh scripts/isaac/set_first_person_camera.py</Cmd>
              <p className="text-zinc-600 text-[10px]">
                Or manually: Perspective → Cameras → FloatingCamera
              </p>
              {camera?.all_cameras && camera.all_cameras.length > 0 && (
                <div className="mt-2">
                  <p className="text-zinc-500 mb-0.5">Cameras in current scene:</p>
                  {camera.all_cameras.map((c, i) => (
                    <p key={i} className="text-zinc-600 text-[9px]">{c}</p>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── Panel 4: Yahboom M3 Pro — Asset / Stage / E2E Evidence ───── */}
        <div className="bg-zinc-900 rounded-lg border border-zinc-700 p-4">
          <div className="flex items-center gap-2 mb-3">
            <StatusDot
              ok={!!(live?.yahboom.urdf_found && live?.yahboom.usd_exists && live?.yahboom.staged)}
              warn={!!(live?.yahboom.urdf_found && live?.yahboom.usd_exists && !live?.yahboom.staged)}
            />
            <h2 className="text-sm font-semibold text-zinc-300">Yahboom M3 Pro</h2>
          </div>

          {/* Row: Asset evidence */}
          <p className="text-[9px] text-zinc-600 uppercase tracking-wide mb-1">Asset evidence</p>
          <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-[11px] mb-3">
            <span className="text-zinc-500">URDF found</span>
            <span className={live?.yahboom.urdf_found ? "text-emerald-400" : "text-red-400"}>
              {live ? (live.yahboom.urdf_found ? "yes" : "no") : "—"}
            </span>
            <span className="text-zinc-500">Isaac USD</span>
            <span className={live?.yahboom.usd_exists ? "text-emerald-400" : "text-red-400"}>
              {live ? (live.yahboom.usd_exists ? "present" : "missing") : "—"}
            </span>
          </div>

          {/* Row: Live-stage evidence */}
          <p className="text-[9px] text-zinc-600 uppercase tracking-wide mb-1">Live-stage evidence</p>
          <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-[11px] mb-3">
            <span className="text-zinc-500">Yahboom staged</span>
            <span className={
              live?.yahboom.staged ? "text-emerald-400" :
              live?.yahboom.usd_exists ? "text-amber-400" : "text-zinc-500"
            }>
              {live
                ? live.yahboom.staged
                  ? `yes — ${live.yahboom.stage_prim_path ?? "/World/YahboomM3Pro"}`
                  : `no (${live.yahboom.stage_status})`
                : "—"}
            </span>
          </div>

          {/* Row: Autonomous E2E evidence */}
          <p className="text-[9px] text-zinc-600 uppercase tracking-wide mb-1">Autonomous E2E evidence</p>
          <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-[11px] mb-3">
            <span className="text-zinc-500">Autonomous /cmd_vel</span>
            <span className={live?.e2e_motion?.autonomous_robot_control ? "text-emerald-400" : "text-zinc-500"}>
              {live ? (live.e2e_motion?.autonomous_robot_control ? "yes" : "no — not wired") : "—"}
            </span>
            <span className="text-zinc-500">E2E motion demo</span>
            <span className={live?.e2e_motion?.e2e_evidence ? "text-emerald-400" : "text-zinc-500"}>
              {live
                ? live.e2e_motion?.demo_run
                  ? `${live.e2e_motion.mode} (${live.e2e_motion.timesteps}t)`
                  : "not run"
                : "—"}
            </span>
          </div>

          {live?.yahboom.usd_path && (
            <p className="text-[10px] text-emerald-600 truncate mb-2">
              USD: {live.yahboom.usd_path}
            </p>
          )}

          {live?.yahboom.blocked && (
            <BlockBanner message={live.yahboom.block_message ?? "Yahboom URDF missing"} />
          )}
          {live?.yahboom.usd_blocked && !live?.yahboom.blocked && (
            <div className="mt-1 bg-red-950 border border-red-800 rounded p-2 text-red-300 text-[10px]">
              <p className="font-semibold">[BLOCKED] Yahboom USD not generated.</p>
              <Cmd>bash scripts/import_yahboom_m3_urdf_to_isaac.sh</Cmd>
            </div>
          )}

          {/* Stage instruction — shown when USD present but not staged */}
          {live?.yahboom.usd_exists && !live?.yahboom.staged && (
            <div className="mt-1 bg-amber-950 border border-amber-700 rounded p-2 text-amber-200 text-[10px]">
              <p className="font-semibold mb-1">Robot not staged in current Isaac scene</p>
              <Cmd>bash scripts/add_yahboom_to_isaac_stage.sh</Cmd>
              <p className="mt-1 text-zinc-500">
                Or in Isaac Console:{" "}
                <code className="text-zinc-400 text-[9px]">
                  exec(open(&apos;scripts/isaac/add_yahboom_to_current_stage.py&apos;).read())
                </code>
              </p>
              <p className="mt-0.5 text-zinc-500">
                Or: File &rarr; Add Reference &rarr; yahboom_m3pro.usd
              </p>
            </div>
          )}

          {!live?.yahboom.urdf_found && (
            <div className="mt-1 text-[11px] text-zinc-500">
              <Cmd>bash scripts/setup_yahboom_m3_assets.sh</Cmd>
            </div>
          )}
        </div>

        {/* ── Panel 5: VLNTube Imported Data ────────────────────────────── */}
        <div className="bg-zinc-900 rounded-lg border border-zinc-700 p-4 lg:col-span-2">
          <div className="flex items-center gap-2 mb-3">
            <StatusDot ok={live?.vlntube.has_real_data ?? false} warn={live?.vlntube.repo_available && !live.vlntube.has_real_data} />
            <h2 className="text-sm font-semibold text-zinc-300">VLNTube Imported Data</h2>
            {status?.vlntube.indexed_at && (
              <span className="ml-auto text-[9px] text-zinc-600">
                indexed {ts(status.vlntube.indexed_at)}
              </span>
            )}
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-[11px] mb-3">
            <div className="bg-zinc-800 rounded p-2">
              <p className="text-zinc-500 mb-1">USD Scenes</p>
              <p className={`text-base font-mono ${live?.vlntube.usd_scenes ? "text-white" : "text-zinc-600"}`}>
                {live?.vlntube.usd_scenes ?? status?.vlntube.usd_scenes ?? "—"}
              </p>
            </div>
            <div className="bg-zinc-800 rounded p-2">
              <p className="text-zinc-500 mb-1">RGB Images</p>
              <p className={`text-base font-mono ${live?.vlntube.rgb_images ? "text-white" : "text-zinc-600"}`}>
                {live?.vlntube.rgb_images ?? "—"}
              </p>
            </div>
            <div className="bg-zinc-800 rounded p-2">
              <p className="text-zinc-500 mb-1">Scene Graphs</p>
              <p className={`text-base font-mono ${status?.vlntube.scene_graphs ? "text-white" : "text-zinc-600"}`}>
                {status?.vlntube.scene_graphs ?? "—"}
              </p>
            </div>
            <div className="bg-zinc-800 rounded p-2">
              <p className="text-zinc-500 mb-1">Instructions</p>
              <p className={`text-base font-mono ${live?.vlntube.instruction_files ? "text-white" : "text-zinc-600"}`}>
                {live?.vlntube.instruction_files ?? status?.vlntube.instruction_files ?? "—"}
              </p>
            </div>
          </div>

          {!live?.vlntube.has_real_data && (
            <div className="text-[11px] text-zinc-500 bg-zinc-800 rounded p-3">
              <p className="text-zinc-400 mb-1">No real VLNTube data downloaded yet.</p>
              <Cmd>bash scripts/setup_vlntube.sh</Cmd>
              <Cmd>bash scripts/download_vlntube_minimal_assets.sh</Cmd>
              <p className="mt-1 text-zinc-600">
                Downloads: Eyz/SceneMeta · Eyz/SceneSummary · Eyz/VLNVerse_data (minimal)
              </p>
            </div>
          )}
          {live?.vlntube.has_real_data && (
            <p className="text-[10px] text-emerald-400">
              Real VLNTube data present. Run{" "}
              <code className="text-emerald-300">python -m fleetsafe_vln.datagen.vlntube_indexer</code>
              {" "}to refresh counts.
            </p>
          )}
        </div>

      </div>

      {/* Screenshot evidence note */}
      <div className="mt-4 bg-zinc-900 border border-zinc-800 rounded p-3 text-[10px] text-zinc-600">
        <span className="text-zinc-400 font-semibold">Evidence capture: </span>
        <code className="text-zinc-500">bash scripts/capture_live_evidence.sh</code>
        {" · "}
        <code className="text-zinc-500">bash scripts/run_real_imported_vln_demo.sh</code>
        {" · "}
        <code className="text-zinc-500">bash scripts/run_real_imported_vln_demo_check.sh</code>
      </div>
    </div>
  );
}
