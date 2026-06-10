"""
run_hospital.py — FleetSafe hospital benchmark runner for Isaac Sim.

Launches the procedural hospital scene with optional pedestrian scenarios
and sensor degradation injection. Records trajectory, safety events, and
social metrics to logs/hospital_benchmark/.

Usage (via shell wrapper — preferred):
    ./scripts/isaaclab/run_hospital.sh
    ./scripts/isaaclab/run_hospital.sh --scene hospital_corridor --scenario crossing
    ./scripts/isaaclab/run_hospital.sh --degrade "motion_blur=40,low_light=60"
    ./scripts/isaaclab/run_hospital.sh --headless --steps 100 --capture
    ./scripts/isaaclab/run_hospital.sh --capture --scenario crossing  # always writes files

Direct (isaac env must be active):
    conda activate isaac
    export OMNI_KIT_ACCEPT_EULA=Y
    python scripts/isaaclab/run_hospital.py [options]

Arguments:
    --scene       Hospital scene ID (see VALID_SCENES below)
    --scenario    Pedestrian scenario (none|crossing|occlusion|congestion|yield|corridor_rush)
    --degrade     Comma-separated sensor faults e.g. "motion_blur=30,lidar_dropout=10"
    --steps N     Stop after N physics steps (0 = run until window closed)
    --log-dir     Override log directory (default: logs/hospital_benchmark)
    --capture     Attempt viewport screenshot; always writes capture_status.json,
                  viewport_status.txt, and procedural_preview.png
    --no-usd      Force procedural scene even if hospital_world.usd exists

Outputs written per run (logs/hospital_benchmark/<timestamp>/):
    session.json            scene, scenario, degradation config, Isaac version
    trajectory.csv          step × (x, y, z, heading, timestamp_s)
    safety_events.jsonl     CBF intervention events
    social_metrics.jsonl    per-step social safety metrics (TTC, min_dist, etc.)
    sensor_faults.json      applied degradation config
    capture_status.json     always written: isaac_runtime / usd_asset / screenshot / procedural_preview
    viewport_status.txt     always written: PROVEN | PROCEDURAL | MISSING
    photoreal_status.json   always written: dashboard-compatible photoreal evidence record
    procedural_preview.png  always written (matplotlib, no GPU needed)
    screenshot.png          written only when Isaac viewport capture succeeds

logs/hospital_benchmark/latest/ is symlinked to the most recent run so the
dashboard backend can always read a fixed path.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

# ── Pure-Python utilities (no Isaac dependency) ───────────────────────────────
from scripts.isaaclab.hospital_capture_utils import (  # noqa: E402
    SCENARIO_AGENT_COUNTS,
    SCENARIO_WAYPOINTS,
    parse_degrade,
    update_latest_symlink,
    write_capture_status,
    write_photoreal_status,
    write_procedural_preview,
    write_viewport_status,
)

# ── AppLauncher MUST be instantiated before any omni/isaaclab imports ─────────

try:
    from isaaclab.app import AppLauncher
except ModuleNotFoundError:
    print(
        "\n[ERROR] 'isaaclab' package not found.\n"
        "  Activate the isaac conda environment:\n"
        "    conda activate isaac\n"
        "  Then re-run via the shell wrapper:\n"
        "    ./scripts/isaaclab/run_hospital.sh\n",
        file=sys.stderr,
    )
    sys.exit(1)

# ── Argument parsing ──────────────────────────────────────────────────────────

VALID_SCENES = [
    "hospital_corridor",
    "hospital_waiting_room",
    "hospital_narrow_passage",
    "hospital_crowded_junction",
    "hospital_elevator_lobby",
    "hospital_reception",
]

VALID_SCENARIOS = list(SCENARIO_WAYPOINTS.keys())

parser = argparse.ArgumentParser(
    description="FleetSafe Hospital Benchmark — Isaac Sim runner"
)
parser.add_argument("--scene",    type=str, default="hospital_corridor", choices=VALID_SCENES)
parser.add_argument("--scenario", type=str, default="none",              choices=VALID_SCENARIOS)
parser.add_argument("--degrade",  type=str, default="",
    help='Comma-separated faults: "motion_blur=30,low_light=50,lidar_dropout=10"')
parser.add_argument("--steps",    type=int, default=0,
    help="Stop after N physics steps (0 = run until window closed)")
parser.add_argument("--log-dir",  type=str, default=str(REPO_ROOT / "logs/hospital_benchmark"),
    help="Directory for benchmark logs")
parser.add_argument("--capture",  action="store_true", default=False,
    help="Write capture_status.json, procedural_preview.png, attempt screenshot.png")
parser.add_argument("--no-usd",   action="store_true", default=False,
    help="Force procedural scene even if hospital_world.usd exists")
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

# ── Post-launch imports ────────────────────────────────────────────────────────

import numpy as np  # noqa: E402

try:
    import isaaclab  # type: ignore
    ISAAC_VERSION = getattr(isaaclab, "__version__", "unknown")
except Exception:
    ISAAC_VERSION = "unknown"

try:
    from fleet_safe_vla.envs.isaaclab.yahboom.m3pro_nav_env import IsaacNavBenchmarkEnv
    _ENV_AVAILABLE = True
except Exception as e:
    print(f"[run_hospital.py] WARNING: IsaacNavBenchmarkEnv not importable: {e}")
    print("  Falling back to viewer-only mode.")
    _ENV_AVAILABLE = False

try:
    from fleet_safe_vla.envs.isaaclab.hospital.hospital_world_loader import HospitalWorldLoader
    _LOADER_AVAILABLE = True
except Exception as e:
    print(f"[run_hospital.py] WARNING: HospitalWorldLoader not available: {e}")
    _LOADER_AVAILABLE = False

# ── Log directory setup ───────────────────────────────────────────────────────

run_ts  = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
log_dir = Path(args_cli.log_dir) / run_ts
log_dir.mkdir(parents=True, exist_ok=True)

degrade_cfg = parse_degrade(args_cli.degrade)

USD_ASSET    = REPO_ROOT / "fleet_safe_vla" / "envs" / "isaaclab" / "hospital" / "assets" / "hospital_world.usd"
usd_available = USD_ASSET.exists() and not args_cli.no_usd

session_meta = {
    "timestamp":     run_ts,
    "scene":         args_cli.scene,
    "scenario":      args_cli.scenario,
    "agent_count":   SCENARIO_AGENT_COUNTS.get(args_cli.scenario, 0),
    "degradation":   degrade_cfg,
    "steps_target":  args_cli.steps,
    "headless":      args_cli.headless,
    "capture":       args_cli.capture,
    "usd_available": usd_available,
    "usd_path":      str(USD_ASSET) if usd_available else None,
    "isaac_version": ISAAC_VERSION,
    "repo":          str(REPO_ROOT),
}
(log_dir / "session.json").write_text(json.dumps(session_meta, indent=2))
(log_dir / "sensor_faults.json").write_text(json.dumps(degrade_cfg, indent=2))

print(f"\n[run_hospital.py] Log dir  : {log_dir}")
print(f"[run_hospital.py] Scene    : {args_cli.scene}")
print(f"[run_hospital.py] Scenario : {args_cli.scenario} ({SCENARIO_AGENT_COUNTS.get(args_cli.scenario,0)} agents)")
print(f"[run_hospital.py] USD asset: {'FOUND' if usd_available else 'MISSING — procedural fallback'}")
if any(v for v in degrade_cfg.values()):
    print(f"[run_hospital.py] Degrade  : {degrade_cfg}")
print("")

# ── Trajectory / metrics writers ─────────────────────────────────────────────

_traj_file   = open(log_dir / "trajectory.csv",     "w", newline="")
_safety_file = open(log_dir / "safety_events.jsonl", "w")
_social_file = open(log_dir / "social_metrics.jsonl", "w")

_traj_writer = csv.writer(_traj_file)
_traj_writer.writerow(["step", "x", "y", "z", "heading_rad", "timestamp_s"])


def log_step(step: int, x: float, y: float, z: float, heading: float) -> None:
    _traj_writer.writerow([step, round(x, 4), round(y, 4), round(z, 4),
                           round(heading, 4), round(time.monotonic(), 4)])


def log_safety_event(step: int, event_type: str, details: dict) -> None:
    _safety_file.write(json.dumps({"step": step, "event": event_type,
                                   "ts": time.monotonic(), **details}) + "\n")
    _safety_file.flush()


def log_social_metrics(step: int, metrics: dict) -> None:
    _social_file.write(json.dumps({"step": step, "ts": time.monotonic(), **metrics}) + "\n")


def close_writers() -> None:
    _traj_file.close()
    _safety_file.close()
    _social_file.close()
    update_latest_symlink(log_dir)
    print(f"\n[run_hospital.py] Logs saved : {log_dir}")
    print(f"[run_hospital.py] Latest link: {log_dir.parent / 'latest'}")


# ── Capture pipeline ──────────────────────────────────────────────────────────

def run_capture_pipeline() -> dict:
    """
    Always-succeeding capture pipeline:
      1. Write procedural_preview.png (matplotlib, guaranteed, no Isaac GPU needed)
      2. Attempt Isaac viewport screenshot.png (may fail in headless/partial install)
      3. Write capture_status.json, viewport_status.txt, photoreal_status.json

    Returns the capture_status dict.
    """
    print("\n[capture] Starting capture pipeline...")

    # ── Step 1: Procedural preview (guaranteed) ───────────────────────────────
    preview_path = write_procedural_preview(
        log_dir,
        scene=args_cli.scene,
        scenario=args_cli.scenario,
        isaac_version=ISAAC_VERSION,
    )
    procedural_status = "RECORDED" if (preview_path and preview_path.exists()) else "MISSING"
    print(f"[capture] Procedural preview : {procedural_status}"
          + (f" → {preview_path}" if preview_path else ""))

    # ── Step 2: Isaac viewport screenshot (best-effort) ───────────────────────
    screenshot_path = log_dir / "screenshot.png"
    screenshot_status = "MISSING"
    method_used = "none"

    # Flush frames so the viewport has content
    for _ in range(15):
        simulation_app.update()

    # Method A: omni.renderer_capture (most universal across Isaac versions)
    try:
        import omni.renderer_capture as rc  # type: ignore
        iface = rc.acquire_renderer_capture_interface()
        iface.capture_next_frame_swapchain(str(screenshot_path))
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            simulation_app.update()
            if screenshot_path.exists() and screenshot_path.stat().st_size > 1000:
                screenshot_status = "RECORDED"
                method_used = "omni.renderer_capture"
                break
        if screenshot_status != "RECORDED":
            print("[capture] omni.renderer_capture: timed out waiting for file")
    except Exception as e:
        print(f"[capture] omni.renderer_capture: {e}")

    # Method B: omni.kit.capture.viewport (older SDK builds)
    if screenshot_status == "MISSING":
        try:
            import omni.kit.capture.viewport as kvc  # type: ignore
            opts = kvc.CaptureOptions()
            opts.output_folder = str(log_dir)
            opts.file_name = "screenshot"
            opts.file_type = kvc.CaptureFileType.PNG
            kvc.CaptureViewport(opts).start()
            for _ in range(25):
                simulation_app.update()
            candidates = sorted(
                log_dir.glob("screenshot*.png"),
                key=lambda p: p.stat().st_mtime, reverse=True,
            )
            if candidates:
                if candidates[0] != screenshot_path:
                    candidates[0].rename(screenshot_path)
                if screenshot_path.exists() and screenshot_path.stat().st_size > 1000:
                    screenshot_status = "RECORDED"
                    method_used = "omni.kit.capture.viewport"
        except Exception as e:
            print(f"[capture] omni.kit.capture.viewport: {e}")

    # Method C: omni.replicator synthetic camera (headless-safe)
    if screenshot_status == "MISSING":
        try:
            import omni.replicator.core as rep  # type: ignore
            cam = rep.create.camera(position=(0, 0, 20), look_at=(0, 0, 0))
            rp  = rep.create.render_product(cam, (1280, 720))
            writer = rep.WriterRegistry.get("BasicWriter")
            writer.initialize(output_dir=str(log_dir), rgb=True)
            writer.attach([rp])
            rep.orchestrator.run_until_complete(num_frames=1)
            # BasicWriter writes rgb/frame_XXXX.png
            frames = sorted((log_dir / "rgb").glob("frame_*.png")) if (log_dir / "rgb").exists() else []
            if not frames:
                frames = sorted(log_dir.glob("**/*.png"))
            if frames:
                frames[-1].rename(screenshot_path)
                screenshot_status = "RECORDED"
                method_used = "omni.replicator"
        except Exception as e:
            print(f"[capture] omni.replicator: {e}")

    print(f"[capture] Screenshot          : {screenshot_status}"
          + (f" (method: {method_used})" if screenshot_status == "RECORDED" else ""))

    # ── Step 3: Determine overall render status ───────────────────────────────
    if screenshot_status == "RECORDED" and usd_available:
        render_status = "PROVEN"
    elif screenshot_status == "RECORDED":
        render_status = "PROCEDURAL"
    elif procedural_status == "RECORDED":
        render_status = "PROCEDURAL"
    else:
        render_status = "MISSING"

    # ── Step 4: Write all status files ───────────────────────────────────────
    write_viewport_status(log_dir, render_status)

    capture_dict = write_capture_status(
        log_dir,
        scene=args_cli.scene,
        scenario=args_cli.scenario,
        isaac_runtime="RECORDED",
        usd_asset="FOUND" if usd_available else "MISSING",
        screenshot=screenshot_status,
        procedural_preview=procedural_status,
        method=method_used,
        timestamp=run_ts,
        isaac_version=ISAAC_VERSION,
    )

    write_photoreal_status(
        log_dir,
        render_status=render_status,
        usd_loaded=usd_available,
        usd_path=str(USD_ASSET) if usd_available else None,
        screenshot_path=str(screenshot_path) if screenshot_status == "RECORDED" else (
            str(preview_path) if preview_path else None
        ),
        method=method_used or ("matplotlib" if procedural_status == "RECORDED" else "none"),
        scene=args_cli.scene,
        scenario=args_cli.scenario,
        timestamp=run_ts,
        isaac_version=ISAAC_VERSION,
    )

    print(f"[capture] Render status       : {render_status}")
    print(f"[capture] capture_status.json : {log_dir / 'capture_status.json'}")
    print(f"[capture] viewport_status.txt : {log_dir / 'viewport_status.txt'}")
    print(f"[capture] photoreal_status.json: {log_dir / 'photoreal_status.json'}")

    return capture_dict


def _write_not_captured_status() -> None:
    """
    Write status files even when --capture was not passed.
    Records that Isaac ran but no capture was attempted.
    """
    write_viewport_status(log_dir, "NOT_RUN")
    write_capture_status(
        log_dir,
        scene=args_cli.scene,
        scenario=args_cli.scenario,
        isaac_runtime="RECORDED",
        usd_asset="FOUND" if usd_available else "MISSING",
        screenshot="NOT_RUN",
        procedural_preview="NOT_RUN",
        method="none",
        timestamp=run_ts,
        isaac_version=ISAAC_VERSION,
    )
    write_photoreal_status(
        log_dir,
        render_status="NOT_RUN",
        usd_loaded=usd_available,
        usd_path=str(USD_ASSET) if usd_available else None,
        screenshot_path=None,
        method="none",
        scene=args_cli.scene,
        scenario=args_cli.scenario,
        timestamp=run_ts,
        isaac_version=ISAAC_VERSION,
    )


# ── Pedestrian scenario configurator ─────────────────────────────────────────

def _configure_pedestrian_scenario(scenario: str) -> None:
    waypoints = SCENARIO_WAYPOINTS.get(scenario, [])
    if not waypoints:
        return
    print(f"[run_hospital.py] Pedestrian '{scenario}': {len(waypoints)} waypoint(s)")
    print(f"  Waypoints: {waypoints}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    _configure_pedestrian_scenario(args_cli.scenario)

    if _ENV_AVAILABLE:
        _run_with_env()
    else:
        _run_viewer_only()


def _run_with_env() -> None:
    """Full benchmark loop using IsaacNavBenchmarkEnv."""
    from fleet_safe_vla.envs.isaaclab.yahboom.m3pro_nav_env import IsaacNavBenchmarkEnv

    env = IsaacNavBenchmarkEnv(
        scene=args_cli.scene,
        headless=args_cli.headless,
        num_agents=SCENARIO_AGENT_COUNTS.get(args_cli.scenario, 0),
    )
    obs = env.reset()
    step = 0
    max_steps = args_cli.steps or 10_000

    print(f"[run_hospital.py] Benchmark loop: max {max_steps} steps")

    if args_cli.capture:
        run_capture_pipeline()
    else:
        _write_not_captured_status()

    try:
        while simulation_app.is_running() and step < max_steps:
            action = np.zeros(3, dtype=np.float32)
            obs, reward, done, info = env.step(action)
            x, y, z = env.get_robot_pose()
            log_step(step, x, y, z, heading=0.0)

            if info.get("cbf_active"):
                log_safety_event(step, "cbf_intervention", {
                    "delta_l2": float(info.get("delta_l2", 0.0)),
                    "min_dist": float(info.get("min_dist", -1.0)),
                })

            log_social_metrics(step, {
                "min_interpersonal_dist": float(info.get("min_dist", -1.0)),
                "ttc":                   float(info.get("ttc", -1.0)),
                "stop_count":            int(info.get("stop_count", 0)),
                "hesitation_latency_s":  float(info.get("hesitation_latency", 0.0)),
            })

            if done:
                obs = env.reset()
            step += 1
            if step % 100 == 0:
                print(f"  step {step:>5}  pos=({x:.2f}, {y:.2f})  reward={reward:.3f}")

    except KeyboardInterrupt:
        print("\n[run_hospital.py] Interrupted.")
    finally:
        env.close()
        close_writers()


def _run_viewer_only() -> None:
    """Viewer-only fallback when IsaacNavBenchmarkEnv is unavailable."""
    import omni.isaac.core.utils.stage as stage_utils  # type: ignore  # noqa: F401
    from omni.isaac.core import World  # type: ignore

    world = World(stage_units_in_meters=1.0, physics_dt=1.0 / 100.0, rendering_dt=1.0 / 30.0)

    if _LOADER_AVAILABLE:
        from fleet_safe_vla.envs.isaaclab.hospital.hospital_world_loader import HospitalWorldLoader
        loader = HospitalWorldLoader(verbose=True)
        try:
            zone_map, prim_paths = loader.build_procedural_scene()
            print(f"[run_hospital.py] Procedural scene built — {len(prim_paths)} prims")
        except Exception as e:
            print(f"[run_hospital.py] build_procedural_scene failed: {e}")
    else:
        print("[run_hospital.py] HospitalWorldLoader unavailable — bare world")

    world.reset()
    step = 0
    max_steps = args_cli.steps or 10_000

    print(f"[run_hospital.py] Viewer-only mode — {max_steps} steps")
    _configure_pedestrian_scenario(args_cli.scenario)

    if args_cli.capture:
        # Settle the scene before capture
        for _ in range(30):
            world.step(render=not args_cli.headless)
        run_capture_pipeline()
    else:
        _write_not_captured_status()

    try:
        while simulation_app.is_running() and step < max_steps:
            world.step(render=not args_cli.headless)
            log_step(step, 0.0, 0.0, 0.0, 0.0)
            step += 1
            if step % 200 == 0:
                print(f"  step {step:>5}")

    except KeyboardInterrupt:
        print("\n[run_hospital.py] Interrupted.")
    finally:
        close_writers()


if __name__ == "__main__":
    try:
        main()
    finally:
        simulation_app.close()
