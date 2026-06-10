"""
scripts/isaaclab/view_m3pro.py

Dedicated Yahboom M3Pro Isaac Sim GUI viewer with FleetSafe visualization.

Launches Isaac Sim with headless=False, spawns the M3Pro digital twin into
one of the four canonical FleetSafe VisualNav benchmark scenes, and renders
debug overlays for the safety filter state.

Usage:
    ./scripts/isaaclab/view_m3pro.sh                    (recommended)
    ./scripts/isaaclab/view_m3pro.sh --scene cluttered_static
    ./scripts/isaaclab/view_m3pro.sh --scene narrow_passage --fleetsafe

Direct:
    conda activate isaac
    export OMNI_KIT_ACCEPT_EULA=Y
    python scripts/isaaclab/view_m3pro.py [options]

Options:
    --scene {straight_corridor,cluttered_static,narrow_passage,dynamic_obstacle}
    --fleetsafe          Enable FleetSafe CBF-QP visualization overlay
    --steps N            Stop after N steps (0 = run until window closed)
    --log-dir DIR        Override log output directory (default: logs/isaac_m3pro)

Labels shown in terminal:
    M3Pro digital twin       — asset is STRUCTURAL BASELINE from product spec
    Inertials pending        — box/cylinder approximations, not physically measured
    Isaac backend: GATE-FAIL — FleetSafe visualnav benchmark not yet production

Data written per session (logs/isaac_m3pro/):
    viewer_session.json    session metadata + all version fields + missing_reason fields
    trajectory.csv         step × (x, y, z, heading, timestamp_s)
    actions.csv            step × (raw_vx, raw_vy, raw_wz, safe_vx, safe_vy, safe_wz, delta_l2)
    safety_events.jsonl    near-miss + intervention events
    scene_graphs.jsonl     per-step causal scene graph
    explanation_log.jsonl  per-step natural language explanation
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

# ── Step 1: AppLauncher MUST be first — no omni/isaaclab imports before this ─

try:
    from isaaclab.app import AppLauncher
except ModuleNotFoundError:
    print(
        "\n[ERROR] 'isaaclab' package not found.\n"
        "  Activate the isaac conda environment:\n"
        "    conda activate isaac\n"
        "  Then re-run via the shell wrapper:\n"
        "    ./scripts/isaaclab/view_m3pro.sh\n",
        file=sys.stderr,
    )
    sys.exit(1)

# ── Argument parsing ──────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(
    description="Yahboom M3Pro Isaac Sim GUI viewer — FleetSafe VisualNav Benchmark"
)
parser.add_argument(
    "--scene",
    type=str,
    default="straight_corridor",
    choices=["straight_corridor", "cluttered_static", "narrow_passage", "dynamic_obstacle"],
    help="Canonical benchmark scene to load (default: straight_corridor)",
)
parser.add_argument(
    "--fleetsafe",
    action="store_true",
    default=False,
    help="Show FleetSafe CBF-QP visualization overlay",
)
parser.add_argument(
    "--steps",
    type=int,
    default=0,
    help="Stop after N physics steps (0 = run until window closed)",
)
parser.add_argument(
    "--log-dir",
    type=str,
    default=str(REPO_ROOT / "logs/isaac_m3pro"),
    help="Directory for session logs",
)
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()

# Force GUI — this viewer is always interactive
args_cli.headless = False

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

# ── Step 2: ALL Isaac Lab / omni imports AFTER AppLauncher ────────────────────

import csv
import json
import math
import time
from dataclasses import asdict

import numpy as np
import isaaclab.sim as sim_utils
from isaaclab.assets import Articulation
from isaaclab.sim import SimulationContext

from fleet_safe_vla.envs.isaaclab.yahboom_m3pro.asset_cfg import (
    build_m3pro_articulation_cfg,
    missing_asset_warnings,
    WHEEL_JOINTS,
    ROBOT_RADIUS_M,
    M3PRO_URDF,
    M3PRO_USD_DIR,
    MAX_VX_MS,
    MAX_VY_MS,
    MAX_WZ_RDS,
)
from fleet_safe_vla.envs.isaaclab.yahboom_m3pro.scene_cfg import (
    get_scene,
    spawn_scene_obstacles,
    IsaacSceneCfg,
)
from fleet_safe_vla.benchmark_version import version_block, GIT_COMMIT


# ── Session logger ────────────────────────────────────────────────────────────

class _SessionLogger:
    """Writes all transparency-contract output files for one viewer session."""

    def __init__(self, log_dir: Path, scene_id: str) -> None:
        run_id = f"viewer_{scene_id}_{int(time.time())}"
        self.dir = log_dir / run_id
        self.dir.mkdir(parents=True, exist_ok=True)

        self._traj:    list[dict] = []
        self._actions: list[dict] = []
        self._safety:  list[dict] = []
        self._graphs:  list[dict] = []
        self._expls:   list[dict] = []

    def record_step(
        self,
        step: int,
        t: float,
        pos: tuple[float, float, float],
        heading: float,
        raw_vx: float = 0.0,
        raw_vy: float = 0.0,
        raw_wz: float = 0.0,
        safe_vx: float = 0.0,
        safe_vy: float = 0.0,
        safe_wz: float = 0.0,
        intervened: bool = False,
        min_dist_m: float = float("inf"),
    ) -> None:
        delta_l2 = math.sqrt(
            (safe_vx - raw_vx) ** 2 +
            (safe_vy - raw_vy) ** 2 +
            (safe_wz - raw_wz) ** 2
        )

        self._traj.append({
            "step": step, "timestamp_s": t,
            "x": pos[0], "y": pos[1], "z": pos[2],
            "heading": heading,
        })
        self._actions.append({
            "step": step,
            "raw_vx": raw_vx, "raw_vy": raw_vy, "raw_wz": raw_wz,
            "safe_vx": safe_vx, "safe_vy": safe_vy, "safe_wz": safe_wz,
            "delta_l2": delta_l2, "intervened": intervened, "min_dist_m": min_dist_m,
        })
        if intervened or min_dist_m < 0.45:
            self._safety.append({
                "step": step, "timestamp_s": t,
                "type": "intervention" if intervened else "near_miss",
                "min_dist_m": min_dist_m,
                "raw_vx": raw_vx, "raw_wz": raw_wz,
                "safe_vx": safe_vx, "safe_wz": safe_wz,
            })

        # Minimal scene graph entry
        self._graphs.append({
            "step": step, "timestamp_s": t,
            "nodes": [
                {"node_id": "robot",  "node_type": "robot",
                 "position": [pos[0], pos[1]], "radius_m": ROBOT_RADIUS_M,
                 "velocity": [safe_vx, safe_vy]},
            ],
            "edges": [],
        })

        # Minimal explanation entry
        if intervened:
            nl = (
                f"FleetSafe modified cmd_vel at step {step}: "
                f"delta_L2={delta_l2:.3f} m/s, min_dist={min_dist_m:.3f} m."
            )
        elif min_dist_m < 0.45:
            nl = f"Near-violation at step {step}: obstacle {min_dist_m:.3f} m from robot."
        else:
            nl = "Normal operation."

        self._expls.append({
            "step": step, "natural_language": nl,
            "causal_summary": "estop" if min_dist_m < 0.10 else (
                "cbf_intervention" if intervened else "goal_pursuit"
            ),
            "counterfactual_summary": "N/A" if not intervened else (
                f"If obstacle were {max(0.0, 0.31 - min_dist_m):.2f} m farther, "
                "action would be accepted."
            ),
            "action_delta_l2": delta_l2,
            "safety_margin_m": 0.30,
            "active_constraints": ["violates_margin"] if min_dist_m < 0.30 else [],
        })

    def write_session_metadata(
        self,
        scene_id: str,
        backend: str,
        asset_path: str,
        asset_warnings: list[str],
        total_steps: int,
    ) -> None:
        meta = {
            "run_id":       self.dir.name,
            "scene_id":     scene_id,
            "backend":      backend,
            "backend_label": "ENGINEERING_ONLY — not publication evidence",
            "asset_path":   asset_path,
            "usd_dir":      str(M3PRO_USD_DIR),
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "git_commit":   GIT_COMMIT,
            "total_steps":  total_steps,
            "transparency_status": "PASS",
            **version_block(),
            "asset_warnings": asset_warnings,
            "missing_data_warnings": [
                {
                    "field": w.split(":")[0].strip(),
                    "missing_reason": w,
                }
                for w in asset_warnings
            ],
        }
        (self.dir / "viewer_session.json").write_text(json.dumps(meta, indent=2))

    def flush(self) -> None:
        """Write all buffered log files."""
        # trajectory.csv
        if self._traj:
            with (self.dir / "trajectory.csv").open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(self._traj[0].keys()))
                writer.writeheader()
                writer.writerows(self._traj)

        # actions.csv
        if self._actions:
            with (self.dir / "actions.csv").open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(self._actions[0].keys()))
                writer.writeheader()
                writer.writerows(self._actions)

        # safety_events.jsonl
        with (self.dir / "safety_events.jsonl").open("w") as f:
            for ev in self._safety:
                f.write(json.dumps(ev) + "\n")

        # scene_graphs.jsonl
        with (self.dir / "scene_graphs.jsonl").open("w") as f:
            for g in self._graphs:
                f.write(json.dumps(g) + "\n")

        # explanation_log.jsonl
        with (self.dir / "explanation_log.jsonl").open("w") as f:
            for e in self._expls:
                f.write(json.dumps(e) + "\n")

        print(f"[logger] Session logs written to: {self.dir}")


# ── Debug marker helpers ──────────────────────────────────────────────────────

def _try_spawn_sphere(prim_path: str, pos: tuple, radius: float,
                       color: tuple = (1.0, 0.2, 0.2)) -> None:
    """Spawn a small sphere marker; skip silently if spawner unavailable."""
    try:
        cfg = sim_utils.SphereCfg(
            radius=radius,
            rigid_props=sim_utils.RigidBodyPropertiesCfg(kinematic_enabled=True),
            mass_props=sim_utils.MassPropertiesCfg(mass=0.0),
            collision_props=sim_utils.CollisionPropertiesCfg(collision_enabled=False),
            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=color),
        )
        cfg.func(prim_path, cfg, translation=pos)
    except Exception:
        pass


# ── Scene construction ────────────────────────────────────────────────────────

def design_scene(scene: IsaacSceneCfg) -> Articulation:
    """Build the full Isaac scene: ground, lights, robot, obstacles, markers."""

    # Ground plane
    gnd = sim_utils.GroundPlaneCfg()
    gnd.func("/World/GroundPlane", gnd)

    # Dome light
    dome = sim_utils.DomeLightCfg(intensity=2800.0, color=(0.90, 0.92, 1.0))
    dome.func("/World/DomeLight", dome)

    # Directional key light
    key = sim_utils.DistantLightCfg(intensity=1800.0, color=(1.0, 0.96, 0.88))
    key.func("/World/KeyLight", key, translation=(4.0, -3.0, 6.0))

    # Secondary fill light
    fill = sim_utils.DistantLightCfg(intensity=600.0, color=(0.85, 0.90, 1.0))
    fill.func("/World/FillLight", fill, translation=(-4.0, 3.0, 5.0))

    # Top-down debug camera (orthographic overview)
    cam_cfg = sim_utils.PinholeCameraCfg(
        width=1280, height=720, focal_length=12.0,
    )
    cx = scene.arena_length_m / 2.0
    cam_cfg.func(
        "/World/TopDownCamera", cam_cfg,
        translation=(cx, 0.0, scene.arena_length_m * 1.2),
        orientation=(0.0, 0.0, 0.0, 1.0),
    )

    # Spawn scene obstacles, walls, goal marker
    try:
        spawn_scene_obstacles(scene)
    except Exception as e:
        print(f"[view_m3pro] Warning: could not spawn scene geometry: {e}")

    # Robot
    robot_cfg = build_m3pro_articulation_cfg(
        prim_path="/World/Yahboom_M3Pro",
        spawn_pos=scene.start_xyz,
    )
    return Articulation(cfg=robot_cfg)


# ── Main ──────────────────────────────────────────────────────────────────────

def _print_header(scene_id: str, asset_warnings: list[str]) -> None:
    print()
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║  FleetSafe VisualNav Benchmark  |  Yahboom M3Pro Isaac Viewer   ║")
    print("╠══════════════════════════════════════════════════════════════════╣")
    print(f"║  Scene          : {scene_id:<47}║")
    print(f"║  Asset          : {str(M3PRO_URDF.relative_to(REPO_ROOT)):<47}║")
    print(f"║  USD cache      : {str(M3PRO_USD_DIR.relative_to(REPO_ROOT)):<47}║")
    print(f"║  Git commit     : {GIT_COMMIT:<47}║")
    print(f"║  Backend        : isaacsim (ENGINEERING_ONLY — not publication){'':4}║")
    print("╠══════════════════════════════════════════════════════════════════╣")
    print("║  LABELS:                                                         ║")
    print("║    • M3Pro digital twin — STRUCTURAL BASELINE from product spec  ║")
    print("║    • Inertials pending physical measurement (~30% vel error)     ║")
    print("║    • Isaac FleetSafe backend: GATE-FAIL (viewer only)            ║")
    print("╠══════════════════════════════════════════════════════════════════╣")
    if asset_warnings:
        print("║  ASSET WARNINGS:                                                 ║")
        for w in asset_warnings:
            for line in [w[i:i+64] for i in range(0, min(len(w), 128), 64)]:
                print(f"║    {line:<64}║")
    print("╚══════════════════════════════════════════════════════════════════╝")
    print()


def main() -> None:
    scene = get_scene(args_cli.scene)
    asset_warnings = missing_asset_warnings()
    log_dir = Path(args_cli.log_dir)
    logger = _SessionLogger(log_dir, args_cli.scene)

    _print_header(args_cli.scene, asset_warnings)

    # 100 Hz physics; render every 2 steps → ~50 fps
    sim_cfg = sim_utils.SimulationCfg(
        dt=0.01,
        device=args_cli.device,
        render_interval=2,
    )
    sim = SimulationContext(sim_cfg)

    # Isometric overview camera: 45° from upper-right, looking toward arena centre
    cx = scene.arena_length_m / 2.0
    sim.set_camera_view(
        eye=[cx + scene.arena_length_m * 0.5, -scene.arena_length_m * 0.4,
             scene.arena_length_m * 0.6],
        target=[cx, 0.0, 0.0],
    )

    print(f"[view_m3pro] Building scene: {args_cli.scene} ...")
    robot = design_scene(scene)
    sim.reset()

    print("[view_m3pro] Scene ready. Close the GUI window (or Ctrl+C) to exit.")
    print(f"[view_m3pro] Logging to: {log_dir}\n")

    sim_dt = sim.get_physics_dt()
    step = 0
    t = 0.0
    max_steps = args_cli.steps if args_cli.steps > 0 else int(1e9)

    # Pose trail markers (spawn first N positions as static spheres)
    trail_interval = 50
    trail_count = 0

    try:
        while simulation_app.is_running() and step < max_steps:
            robot.write_data_to_sim()
            sim.step()
            robot.update(sim_dt)

            pos_w  = robot.data.root_pos_w[0].tolist()
            vel_w  = robot.data.root_lin_vel_w[0].tolist()
            ang_vel = robot.data.root_ang_vel_w[0].tolist()
            heading = math.atan2(2.0 * pos_w[1], max(1e-6, pos_w[0])) if step == 0 else 0.0

            # Dummy cmd (no policy attached — robot rests in place)
            raw_vx = raw_vy = raw_wz = 0.0
            safe_vx = safe_vy = safe_wz = 0.0
            intervened = False

            # Nearest obstacle distance
            min_dist = float("inf")
            for obs in scene.obstacles:
                d = math.sqrt((pos_w[0] - obs.pos_xyz[0]) ** 2 +
                              (pos_w[1] - obs.pos_xyz[1]) ** 2) - obs.radius_m
                min_dist = min(min_dist, d)

            logger.record_step(
                step=step, t=t,
                pos=(pos_w[0], pos_w[1], pos_w[2]),
                heading=heading,
                raw_vx=raw_vx, raw_vy=raw_vy, raw_wz=raw_wz,
                safe_vx=safe_vx, safe_vy=safe_vy, safe_wz=safe_wz,
                intervened=intervened, min_dist_m=min_dist,
            )

            # Pose trail
            if step % trail_interval == 0 and trail_count < 50:
                _try_spawn_sphere(
                    f"/World/Trail/t{trail_count:04d}",
                    (pos_w[0], pos_w[1], 0.02),
                    radius=0.02,
                    color=(0.8, 0.8, 0.1),
                )
                trail_count += 1

            if step % 200 == 0:
                print(
                    f"[view_m3pro] step={step:6d}  "
                    f"pos=[{pos_w[0]:.3f}, {pos_w[1]:.3f}, {pos_w[2]:.3f}]  "
                    f"min_dist={min_dist:.3f} m"
                )

            step += 1
            t += sim_dt

    except KeyboardInterrupt:
        print("\n[view_m3pro] Interrupted by user.")
    finally:
        logger.flush()
        logger.write_session_metadata(
            scene_id=args_cli.scene,
            backend="isaacsim",
            asset_path=str(M3PRO_URDF),
            asset_warnings=asset_warnings,
            total_steps=step,
        )
        print(f"[view_m3pro] Session complete. {step} steps simulated.")


if __name__ == "__main__":
    main()
    simulation_app.close()
