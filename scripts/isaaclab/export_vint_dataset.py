#!/usr/bin/env python3
"""
export_vint_dataset.py — Export Isaac Sim synthetic images to GNM/ViNT/NoMaD canonical format.

Drives the M3Pro along N random routes in a loaded USD scene, captures RGB frames
from the onboard camera, and saves each route as a traj_NNNN/ folder:

    <output_dir>/
        train/
            traj_0000/  0.jpg  1.jpg  …  traj_data.pkl
            traj_0001/  …
        test/
            traj_NNNN/  …
        data_config.yaml    ← ready for gnm.yaml --data-folder

traj_data.pkl schema (identical across GNM / ViNT / NoMaD):
    {"position": np.ndarray([T, 2], float32),   # (x, y) in metres
     "yaw":      np.ndarray([T],   float32)}     # heading in radians

Image resolution: 85×64 px (GNM default) — override with --width / --height.

Usage:
    conda activate isaac
    python scripts/isaaclab/export_vint_dataset.py \\
        --usd IsaacLabAssets/hospital_photorealistic.usd \\
        --episodes 100 --steps 200 --out data/isaac_hospital_vint

    # Warehouse, higher res for ViNT/NoMaD:
    python scripts/isaaclab/export_vint_dataset.py \\
        --usd IsaacLabAssets/warehouse_photorealistic.usd \\
        --episodes 50 --width 160 --height 120 --out data/isaac_warehouse_vint

    # Then fine-tune GNM:
    cd third_party/visualnav-transformer/train
    python train.py --config vint_train/config/gnm.yaml \\
                    --data-folder ../../../data/isaac_hospital_vint
"""
from __future__ import annotations

import argparse
import math
import pickle
import random
import sys
from pathlib import Path

import numpy as np

# ── Arg parse BEFORE AppLauncher ──────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

parser = argparse.ArgumentParser(description="Export Isaac Sim → ViNT training dataset.")
parser.add_argument("--usd", type=Path, required=True,
                    help="Pre-built USD scene file (from load_nvidia_assets.py or generate_hospital_usd.py)")
parser.add_argument("--episodes", type=int, default=100,
                    help="Number of trajectories to record (default: 100)")
parser.add_argument("--steps", type=int, default=200,
                    help="Max steps per trajectory (default: 200)")
parser.add_argument("--width",  type=int, default=85,  help="Image width  (GNM default: 85)")
parser.add_argument("--height", type=int, default=64,  help="Image height (GNM default: 64)")
parser.add_argument("--dt", type=float, default=0.1,   help="Sim dt per step in seconds (default: 0.1)")
parser.add_argument("--eval-frac", type=float, default=0.1,
                    help="Fraction of episodes for test split (default: 0.1)")
parser.add_argument("--out", type=Path,
                    default=_REPO_ROOT / "data" / "isaac_vint_dataset",
                    help="Output dataset root directory")
parser.add_argument("--dataset-name", default="isaac_hospital",
                    help="Name written to data_config.yaml (default: isaac_hospital)")
parser.add_argument("--seed", type=int, default=42)
parser.add_argument("--headless", action="store_true", default=True)
parser.add_argument("--no-replicator", action="store_true", default=False,
                    help="Skip RTX camera capture; use fast noise images instead. "
                         "Proves dataset format without GPU rendering overhead.")
args, remaining = parser.parse_known_args()

# ── AppLauncher ───────────────────────────────────────────────────────────────

from isaaclab.app import AppLauncher  # noqa: E402

# Only load the full RTX camera pipeline when actually needed — it causes a
# 200k-file disk accumulation in the replicator writer that makes each sim
# step take 9+ seconds in headless mode.
launcher_args = argparse.Namespace(headless=args.headless,
                                   enable_cameras=not args.no_replicator)
app_launcher  = AppLauncher(launcher_args)
simulation_app = app_launcher.app

# ── Isaac / omni imports (post-launcher) ──────────────────────────────────────

import omni.usd                                    # noqa: E402
from isaaclab.sim import SimulationContext         # noqa: E402
from pxr import Gf, UsdGeom                       # noqa: E402

try:
    from omni.replicator.core import orchestrator   # noqa: E402
    import omni.replicator.core as rep
    _HAS_REP = True
except ImportError:
    _HAS_REP = False
    print("[export_vint_dataset] WARNING: omni.replicator not found — using PIL fallback for image capture.")

try:
    from PIL import Image as PILImage
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


# ── Scene loading ─────────────────────────────────────────────────────────────

def _load_stage(usd_path: Path) -> None:
    context = omni.usd.get_context()
    if usd_path.exists():
        # Isaac Sim 4.x returns (bool, error_str); 5.x returns a single bool.
        ret = context.open_stage(str(usd_path))
        result = ret[0] if isinstance(ret, (tuple, list)) else bool(ret)
        if not result:
            raise RuntimeError(f"Failed to open USD: {usd_path}")
        print(f"[export_vint_dataset] Stage loaded: {usd_path}")
    else:
        print(f"[export_vint_dataset] USD not found ({usd_path}), building procedural hospital …")
        from fleet_safe_vla.envs.isaaclab.hospital.hospital_world_loader import HospitalWorldLoader
        HospitalWorldLoader(verbose=True, nucleus_ok=False).build_procedural_scene()


# ── Mock navigation policy (random-walk with goal bias) ──────────────────────

class _RandomWalkPolicy:
    """Minimal random-walk driver for synthetic data collection.

    In production, replace with a real GNM/ViNT adapter to collect on-policy data.
    """
    def __init__(self, rng: random.Random):
        self._rng    = rng
        self._vx     = 0.3
        self._wz_max = 0.8

    def act(self, goal_vec: np.ndarray) -> tuple[float, float]:
        angle  = math.atan2(float(goal_vec[1]), float(goal_vec[0]))
        wz     = max(-self._wz_max, min(self._wz_max, 1.5 * angle))
        noise  = self._rng.gauss(0, 0.05)
        return self._vx, wz + noise


# ── Camera capture helpers ────────────────────────────────────────────────────

def _setup_replicator_camera(camera_prim_path: str, w: int, h: int):
    if not _HAS_REP:
        return None
    cam = rep.create.camera(position=(0, 0, 0.13), look_at=(1, 0, 0.13))
    rp  = rep.create.render_product(cam, (w, h))
    writer = rep.WriterRegistry.get("BasicWriter")
    writer.initialize(output_dir="/tmp/_rep_tmp", rgb=True)
    writer.attach([rp])
    return rp


def _capture_rgb(render_product, w: int, h: int) -> np.ndarray | None:
    """Return (H, W, 3) uint8 array or None if capture fails."""
    if not _HAS_REP or render_product is None:
        # Fallback: white noise image (marks frames where replicator is absent)
        arr = np.random.randint(100, 200, (h, w, 3), dtype=np.uint8)
        return arr
    try:
        rep.orchestrator.step(rt_subframes=4)
        # Replicator writes to disk; read back
        from omni.replicator.core import utils as rep_utils
        data = rep_utils.collect_placement_group_output(render_product)
        if data and "rgb" in data:
            return data["rgb"][:h, :w, :3].astype(np.uint8)
    except Exception as e:
        print(f"[export_vint_dataset] Replicator capture error: {e}")
    arr = np.random.randint(100, 200, (h, w, 3), dtype=np.uint8)
    return arr


def _save_image(arr: np.ndarray, path: Path) -> None:
    if _HAS_PIL:
        PILImage.fromarray(arr).save(str(path))
    else:
        # Minimal PPM writer (no dependencies)
        h, w, _ = arr.shape
        with open(path.with_suffix(".ppm"), "wb") as f:
            f.write(f"P6\n{w} {h}\n255\n".encode())
            f.write(arr.tobytes())


# ── Robot pose helpers (read from USD stage) ──────────────────────────────────

def _get_robot_pose(stage) -> tuple[float, float, float]:
    """Return (x, y, yaw) from /World/Robot/M3Pro xform, or zeros if absent."""
    prim = stage.GetPrimAtPath("/World/Robot/M3Pro")
    if not prim.IsValid():
        return 0.0, 0.0, 0.0
    xf = UsdGeom.Xformable(prim)
    t  = xf.GetLocalTransformation()
    x  = t.GetRow3(3)[0]
    y  = t.GetRow3(3)[1]
    # Approximate yaw from rotation matrix row 0
    rx = t.GetRow3(0)
    yaw = math.atan2(float(rx[1]), float(rx[0]))
    return float(x), float(y), float(yaw)


def _set_robot_pose(stage, x: float, y: float, yaw: float) -> None:
    prim = stage.GetPrimAtPath("/World/Robot/M3Pro")
    if not prim.IsValid():
        return
    xf      = UsdGeom.Xformable(prim)
    ops     = {op.GetName(): op for op in xf.GetOrderedXformOps()}
    t_op    = ops.get("xformOp:translate") or xf.AddTranslateOp()
    r_op    = ops.get("xformOp:rotateZ")   or xf.AddRotateZOp()
    t_op.Set(Gf.Vec3d(x, y, 0.048))
    r_op.Set(math.degrees(yaw))


# ── Episode runner ────────────────────────────────────────────────────────────

def run_episode(
    sim:      SimulationContext,
    policy:   _RandomWalkPolicy,
    rng:      random.Random,
    goal_xy:  np.ndarray,
    n_steps:  int,
    render_product,
    img_w:    int,
    img_h:    int,
) -> dict:
    """Simulate one navigation episode and return recorded data."""
    stage = omni.usd.get_context().get_stage()

    positions  = []
    yaws       = []
    images     = []
    success    = False

    x, y, yaw = 0.0, 0.0, 0.0
    dt = args.dt

    for step in range(n_steps):
        # Capture image BEFORE stepping (matches robot's current observation)
        img = _capture_rgb(render_product, img_w, img_h)
        images.append(img)

        # Record pose
        positions.append([x, y])
        yaws.append(yaw)

        # Goal vector in robot frame
        dx, dy = goal_xy[0] - x, goal_xy[1] - y
        dist   = math.hypot(dx, dy)
        if dist < 0.30:
            success = True
            break

        # Rotate to robot frame
        gx_rob =  dx * math.cos(-yaw) - dy * math.sin(-yaw)
        gy_rob =  dx * math.sin(-yaw) + dy * math.cos(-yaw)

        vx, wz = policy.act(np.array([gx_rob, gy_rob]))

        # Integrate kinematics (forward Euler, approximation)
        x   += vx * math.cos(yaw) * dt
        y   += vx * math.sin(yaw) * dt
        yaw += wz * dt
        yaw  = (yaw + math.pi) % (2 * math.pi) - math.pi

        _set_robot_pose(stage, x, y, yaw)
        sim.step(render=not args.headless)

    return {
        "positions": np.array(positions, dtype=np.float32),
        "yaws":      np.array(yaws,      dtype=np.float32),
        "images":    images,
        "success":   success,
        "n_steps":   len(positions),
    }


# ── Dataset writer ────────────────────────────────────────────────────────────

def write_trajectory(ep_data: dict, traj_dir: Path, img_w: int, img_h: int) -> None:
    traj_dir.mkdir(parents=True, exist_ok=True)

    for i, img in enumerate(ep_data["images"]):
        _save_image(img, traj_dir / f"{i}.jpg")

    pkl_data = {
        "position": ep_data["positions"],
        "yaw":      ep_data["yaws"],
    }
    with open(traj_dir / "traj_data.pkl", "wb") as f:
        pickle.dump(pkl_data, f)


def write_data_config(out_dir: Path, dataset_name: str) -> None:
    import yaml
    cfg = {
        "dataset_name":              dataset_name,
        "data_folder":               str(out_dir),
        "train":                     "train",
        "test":                      "test",
        "end_slack":                 3,
        "goals_per_obs":             1,
        "negative_mining":           True,
        "metric_waypoint_spacing":   0.25,
    }
    out_path = out_dir / "data_config.yaml"
    with open(out_path, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False)
    print(f"[export_vint_dataset] data_config.yaml → {out_path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    rng = random.Random(args.seed)

    # Train / test split
    n_test  = max(1, int(args.episodes * args.eval_frac))
    n_train = args.episodes - n_test

    train_dir = args.out / "train"
    test_dir  = args.out / "test"
    train_dir.mkdir(parents=True, exist_ok=True)
    test_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n[export_vint_dataset] Plan: {n_train} train + {n_test} test trajectories")
    print(f"[export_vint_dataset] Image: {args.width}×{args.height}  Steps/ep: {args.steps}")

    # Load scene
    _load_stage(args.usd)
    # Isaac Lab 5.x: SimulationContext takes only a SimulationCfg; older versions
    # accepted (stage_units_in_meters, physics_dt, rendering_dt) directly.
    try:
        from isaaclab.sim import SimulationCfg
        sim = SimulationContext(SimulationCfg(dt=args.dt))
    except (TypeError, ImportError):
        try:
            sim = SimulationContext(stage_units_in_meters=1.0, physics_dt=args.dt, rendering_dt=args.dt)
        except TypeError:
            sim = SimulationContext()
    sim.reset()

    render_product = (None if args.no_replicator else
                      _setup_replicator_camera("/World/Robot/M3Pro/camera_link", args.width, args.height))
    policy = _RandomWalkPolicy(rng)

    success_count = 0

    for ep_idx in range(args.episodes):
        split   = "train" if ep_idx < n_train else "test"
        traj_n  = ep_idx if split == "train" else ep_idx - n_train
        traj_id = f"traj_{traj_n:04d}"
        out_dir = train_dir if split == "train" else test_dir

        # Random start pose and goal
        sx   = rng.uniform(-5.0, 5.0)
        sy   = rng.uniform(-2.0, 2.0)
        syaw = rng.uniform(-math.pi, math.pi)
        gx   = sx + rng.uniform(3.0, 10.0)
        gy   = sy + rng.uniform(-1.0, 1.0)

        stage = omni.usd.get_context().get_stage()
        _set_robot_pose(stage, sx, sy, syaw)
        sim.reset()

        ep_data = run_episode(
            sim, policy, rng,
            goal_xy=np.array([gx, gy]),
            n_steps=args.steps,
            render_product=render_product,
            img_w=args.width,
            img_h=args.height,
        )

        write_trajectory(ep_data, out_dir / traj_id, args.width, args.height)
        if ep_data["success"]:
            success_count += 1

        if (ep_idx + 1) % 10 == 0 or ep_idx == args.episodes - 1:
            pct = 100 * (ep_idx + 1) / args.episodes
            print(f"  [{ep_idx+1:4d}/{args.episodes}] {pct:.0f}%  success={success_count}")

    write_data_config(args.out, args.dataset_name)

    print(f"\n[export_vint_dataset] Done!")
    print(f"  Dataset : {args.out}")
    print(f"  Episodes: {args.episodes}  (success: {success_count}/{args.episodes})")
    print(f"  Train   : {n_train} trajectories in {train_dir}")
    print(f"  Test    : {n_test}  trajectories in {test_dir}")
    print()
    print("Fine-tune GNM:")
    print(f"  cd third_party/visualnav-transformer/train")
    print(f"  python train.py --config vint_train/config/gnm.yaml \\")
    print(f"                  --data-folder {args.out}")
    print()

    simulation_app.close()


if __name__ == "__main__":
    main()
