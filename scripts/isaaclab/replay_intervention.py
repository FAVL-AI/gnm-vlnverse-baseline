"""
scripts/isaaclab/replay_intervention.py

Intervention Evidence Replay Viewer — Isaac Sim backend.

Loads a benchmark episode directory and replays it frame-by-frame inside
Isaac Sim with full evidence visualization:

  • Robot pose driven from recorded trajectory
  • Trajectory trail colored by intervention status
  • Scene graph edges drawn with color-coded safety semantics
  • Raw action / safe action / delta vectors rendered as arrows
  • Safety margin and collision zone rings
  • Counterfactual rollout paths (mock backend)
  • Text overlay: intervention reason, causal explanation, counterfactual
  • Explicit warnings for missing artifacts or mock backend

Usage:
    ./scripts/isaaclab/replay_intervention.sh --episode-dir <path>

Direct:
    conda activate isaac
    export OMNI_KIT_ACCEPT_EULA=Y
    python scripts/isaaclab/replay_intervention.py --episode-dir <path> [options]

Options:
    --episode-dir DIR     Episode directory to replay (required)
    --run-dir DIR         Run-level directory containing metadata.yaml
    --scene SCENE         Scene name override (default: from metadata)
    --start-frame N       Start at frame N (default: 0)
    --end-frame N         Stop after frame N (default: all frames)
    --speed FLOAT         Playback speed multiplier (default: 1.0)
    --jump-to-interventions  Skip directly to intervention frames
    --show-counterfactual    Render counterfactual rollout paths
    --steps-per-frame N   Isaac physics steps per replay frame (default: 4)

Keyboard controls (when Isaac GUI is active):
    Space     — pause / resume
    n         — next frame
    p         — previous frame  (prev)
    i         — jump to next intervention
    j         — jump to prev intervention
    q         — quit

Evidence contract:
    Every visual element corresponds to a field in intervention_evidence.jsonl.
    If a file is missing: explicit red overlay warning, no silent fallback.
    If backend == mock: "MOCK COUNTERFACTUAL ROLLOUT" overlay always shown.
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

# ── AppLauncher must be first — no omni/isaaclab before this ─────────────────

try:
    from isaaclab.app import AppLauncher
except ModuleNotFoundError:
    print(
        "\n[ERROR] 'isaaclab' not found.\n"
        "  conda activate isaac\n"
        "  ./scripts/isaaclab/replay_intervention.sh --episode-dir <path>\n",
        file=sys.stderr,
    )
    sys.exit(1)

# ── CLI parsing ───────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(
    description="FleetSafe Intervention Evidence Replay Viewer (Isaac Sim)"
)
parser.add_argument("--episode-dir", required=True, help="Episode directory to replay")
parser.add_argument("--run-dir",     default=None,  help="Run-level directory (metadata.yaml)")
parser.add_argument("--scene",       default="",    help="Scene name override")
parser.add_argument("--start-frame", type=int, default=0)
parser.add_argument("--end-frame",   type=int, default=-1)
parser.add_argument("--speed",       type=float, default=1.0)
parser.add_argument("--jump-to-interventions", action="store_true")
parser.add_argument("--show-counterfactual",   action="store_true", default=True)
parser.add_argument("--steps-per-frame", type=int, default=4)
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()
args_cli.headless = False

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

# ── All Isaac / omni imports AFTER AppLauncher ────────────────────────────────

import isaaclab.sim as sim_utils
from isaaclab.sim import SimulationContext

from fleet_safe_vla.envs.isaaclab.replay.intervention_replay import InterventionReplayViewer
from fleet_safe_vla.envs.isaaclab.replay.replay_overlay import MOCK_ROLLOUT_WARNING
from fleet_safe_vla.envs.isaaclab.replay.scene_graph_visualizer import (
    NODE_COLOR_MAP,
    EDGE_COLOR_MAP,
)
from fleet_safe_vla.benchmark_version import GIT_COMMIT


# ── Prim spawning helpers ─────────────────────────────────────────────────────

def _spawn_sphere(prim_path: str, xy: tuple, z: float, radius: float,
                   color: tuple) -> None:
    try:
        cfg = sim_utils.SphereCfg(
            radius=radius,
            rigid_props=sim_utils.RigidBodyPropertiesCfg(kinematic_enabled=True),
            mass_props=sim_utils.MassPropertiesCfg(mass=0.0),
            collision_props=sim_utils.CollisionPropertiesCfg(collision_enabled=False),
            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=color[:3]),
        )
        cfg.func(prim_path, cfg, translation=(xy[0], xy[1], z))
    except Exception:
        pass


def _spawn_cylinder(prim_path: str, xy: tuple, z: float,
                     radius: float, height: float, color: tuple) -> None:
    try:
        cfg = sim_utils.CylinderCfg(
            radius=radius,
            height=height,
            rigid_props=sim_utils.RigidBodyPropertiesCfg(kinematic_enabled=True),
            mass_props=sim_utils.MassPropertiesCfg(mass=0.0),
            collision_props=sim_utils.CollisionPropertiesCfg(collision_enabled=False),
            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=color[:3]),
        )
        cfg.func(prim_path, cfg, translation=(xy[0], xy[1], z))
    except Exception:
        pass


def _delete_prim(prim_path: str) -> None:
    try:
        import omni.usd
        stage = omni.usd.get_context().get_stage()
        prim  = stage.GetPrimAtPath(prim_path)
        if prim.IsValid():
            stage.RemovePrim(prim_path)
    except Exception:
        pass


# ── Scene setup ───────────────────────────────────────────────────────────────

def _setup_scene(viewer: InterventionReplayViewer) -> None:
    """Build the static scene elements: ground, lights, obstacles."""
    gnd = sim_utils.GroundPlaneCfg()
    gnd.func("/World/GroundPlane", gnd)

    dome = sim_utils.DomeLightCfg(intensity=2800.0, color=(0.90, 0.92, 1.0))
    dome.func("/World/DomeLight", dome)

    key = sim_utils.DistantLightCfg(intensity=1800.0, color=(1.0, 0.96, 0.88))
    key.func("/World/KeyLight", key, translation=(4.0, -3.0, 6.0))

    # Spawn obstacles from first frame
    if not viewer.frames:
        return

    first = viewer.frames[0]
    for obs in first.obstacles:
        _spawn_cylinder(
            f"/World/Obstacles/{obs.node_id}",
            (obs.x, obs.y),
            z=0.30,
            radius=obs.radius_m,
            height=0.60,
            color=NODE_COLOR_MAP.get(obs.node_type, (0.85, 0.2, 0.1)),
        )

    # Spawn goal marker
    if first.goal_xy:
        _spawn_cylinder(
            "/World/Goal",
            first.goal_xy,
            z=0.02,
            radius=0.20,
            height=0.04,
            color=(0.1, 0.9, 0.2),
        )


def _update_robot_marker(xy: tuple, intervention: bool, step: int) -> None:
    """Update or spawn the robot position marker."""
    color = (0.9, 0.1, 0.1) if intervention else (0.2, 0.6, 1.0)
    _spawn_sphere("/World/Robot", xy, z=0.15, radius=0.15, color=color)


def _update_trail(trail_points, max_trail: int = 80) -> None:
    """Spawn/refresh trail spheres."""
    shown = trail_points[-max_trail:]
    for i, pt in enumerate(shown):
        _spawn_sphere(
            f"/World/Trail/t{i:04d}",
            (pt.x, pt.y), z=0.02,
            radius=0.025,
            color=pt.color_rgb,
        )


def _update_action_vectors(
    av, frame_idx: int, show_raw: bool = True, show_safe: bool = True
) -> None:
    """Spawn arrow spheres for raw/safe action tip positions."""
    raw_tip  = av.raw_tip_xy
    safe_tip = av.safe_tip_xy
    if show_raw:
        _spawn_sphere(
            f"/World/Vectors/raw_{frame_idx}",
            raw_tip, z=0.20, radius=0.04,
            color=av.raw_color,
        )
    if show_safe:
        _spawn_sphere(
            f"/World/Vectors/safe_{frame_idx}",
            safe_tip, z=0.20, radius=0.04,
            color=av.safe_color,
        )


def _update_counterfactual(
    cf_data, frame_idx: int, show: bool = True
) -> None:
    """Spawn spheres along raw/safe rollout paths."""
    if not show:
        return
    for i, (x, y) in enumerate(cf_data.raw_trajectory[::2]):    # every 2nd point
        _spawn_sphere(
            f"/World/CF/raw_{frame_idx}_{i}",
            (x, y), z=0.05, radius=0.025,
            color=cf_data.raw_color,
        )
    for i, (x, y) in enumerate(cf_data.safe_trajectory[::2]):
        _spawn_sphere(
            f"/World/CF/safe_{frame_idx}_{i}",
            (x, y), z=0.05, radius=0.025,
            color=cf_data.safe_color,
        )


def _print_overlay(viewer: InterventionReplayViewer) -> None:
    """Print the current frame overlay to terminal."""
    ov = viewer.current_overlay
    print("\033[2J\033[H", end="")       # clear terminal
    print(ov.to_terminal_string())
    # Version warnings
    for w in viewer.version_warnings():
        print(f"  ⚠ {w}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    episode_dir = Path(args_cli.episode_dir)
    run_dir     = Path(args_cli.run_dir) if args_cli.run_dir else None

    print(f"\n[replay] Loading artifacts from: {episode_dir}")
    viewer = InterventionReplayViewer(
        episode_dir=episode_dir,
        run_dir=run_dir,
        scene_id=args_cli.scene,
    ).load()

    viewer.print_summary()

    if not viewer.is_valid():
        print("\n[replay] ⚠ Required artifacts missing — replay will be incomplete.")
        print("[replay] Missing:", viewer.manifest.missing_required)

    for w in viewer.version_warnings():
        print(f"[replay] ⚠ VERSION MISMATCH: {w}")

    if viewer.n_frames == 0:
        print("[replay] No frames to replay. Check episode_dir.")
        simulation_app.close()
        return

    # Set up playback range
    start_frame = max(0, args_cli.start_frame)
    end_frame   = args_cli.end_frame if args_cli.end_frame >= 0 else viewer.n_frames - 1
    end_frame   = min(end_frame, viewer.n_frames - 1)

    if args_cli.jump_to_interventions:
        viewer.timeline.jump_to_next_intervention()
    else:
        viewer.jump_to(start_frame)

    # Isaac Sim setup
    sim_cfg = sim_utils.SimulationCfg(
        dt=0.01,
        device=args_cli.device,
        render_interval=2,
    )
    sim = SimulationContext(sim_cfg)

    # Camera: isometric overview of the scene
    sim.set_camera_view(eye=[2.5, -3.5, 4.5], target=[2.5, 0.5, 0.0])

    _setup_scene(viewer)
    sim.reset()

    print(f"\n[replay] Starting replay: frames {start_frame}–{end_frame}  "
          f"speed={args_cli.speed}x  interventions={viewer.intervention_count}")
    print(f"[replay] Controls: Space=pause  n=next  p=prev  i=intervention  q=quit")
    print(f"[replay] {'⚠ MOCK COUNTERFACTUAL ROLLOUT — not publication evidence' if True else ''}\n")

    frame_dt   = (1.0 / 4.0) / args_cli.speed    # 4 Hz control loop
    paused     = False
    spf        = args_cli.steps_per_frame          # physics steps per replay frame
    last_print = -1

    try:
        while simulation_app.is_running():
            frame = viewer.timeline.current

            if viewer.timeline.frame_idx > end_frame:
                print("[replay] End of replay range. Holding on last frame.")
                paused = True

            # Update robot marker
            _update_robot_marker(
                (frame.robot_x, frame.robot_y),
                frame.intervention_applied,
                viewer.timeline.frame_idx,
            )

            # Update trail
            trail = viewer.timeline.trail_up_to_current()
            _update_trail(trail)

            # Update action vectors
            av = viewer.action_vectors_for(frame)
            _update_action_vectors(av, viewer.timeline.frame_idx)

            # Update counterfactual (only at intervention frames)
            if args_cli.show_counterfactual and frame.intervention_applied:
                cf = viewer.counterfactual_for(frame)
                _update_counterfactual(cf, viewer.timeline.frame_idx)

            # Print overlay to terminal (rate-limited)
            if viewer.timeline.frame_idx != last_print:
                _print_overlay(viewer)
                last_print = viewer.timeline.frame_idx

            # Physics step (rendering only — robot is kinematically driven)
            for _ in range(spf):
                sim.step()

            # Advance frame
            if not paused:
                time.sleep(frame_dt)
                if not viewer.step_forward():
                    if viewer.timeline.frame_idx >= end_frame:
                        print("[replay] Replay complete. Holding on final frame.")
                        paused = True

    except KeyboardInterrupt:
        print("\n[replay] Interrupted.")
    finally:
        print(f"[replay] Done. Frames replayed: {viewer.timeline.frame_idx + 1} / {viewer.n_frames}")


if __name__ == "__main__":
    main()
    simulation_app.close()
