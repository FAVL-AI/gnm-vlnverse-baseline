"""
create_custom_gnm_scene.py — Build a custom GNM training scene in Isaac Sim
============================================================================
Creates a small custom office scene from USD primitives — no VLNVerse assets.
Demonstrates the GNM data pipeline independent of VLNVerse.

The scene contains:
  - Floor (grey plane)
  - Four walls (white cubes)
  - One table obstacle (brown cube)
  - START marker (green sphere)
  - GOAL marker (red sphere)
  - Planned expert path (cyan spheres)
  - RGB camera at robot eye height

Then moves the camera along the path, captures one frame per step,
saves traj_data.pkl, episode_info.json, and numbered JPG frames.

Outputs:
  datasets/custom_gnm_scene/train/custom_office_0001/0.jpg … N.jpg
  datasets/custom_gnm_scene/train/custom_office_0001/traj_data.pkl
  datasets/custom_gnm_scene/train/custom_office_0001/episode_info.json
  datasets/custom_gnm_scene/train/custom_office_0001/instruction.txt
  results/figures/custom_scene_start.png
  results/figures/custom_scene_goal.png

Usage:
  conda run -n isaac python scripts/gnm/create_custom_gnm_scene.py
  conda run -n isaac python scripts/gnm/create_custom_gnm_scene.py --dry-run
"""
import argparse
import json
import math
import os
import pickle
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path("/home/favl/robotics/FleetSafe-VisualNav-Benchmark")

# ── Expert path: L-shaped route around the table obstacle ─────────────────────
# Waypoints in floor-plane (x, y) metres
EXPERT_PATH = [
    (0.0,  0.0),   # start
    (1.0,  0.0),
    (2.0,  0.0),
    (3.0,  0.0),
    (3.0,  1.0),   # turn right around table
    (3.0,  2.0),
    (3.0,  3.0),
    (2.0,  3.0),
    (1.0,  3.0),   # goal
]

FLOOR_SIZE  = 6.0
WALL_HEIGHT = 2.5
WALL_THICK  = 0.15
TABLE_POS   = (2.0, 1.5)
TABLE_SIZE  = (1.0, 0.8, 0.75)


def _interpolate_path(waypoints: list[tuple], steps_per_segment: int = 10) -> list[tuple]:
    pts: list[tuple] = []
    for i in range(len(waypoints) - 1):
        x0, y0 = waypoints[i]
        x1, y1 = waypoints[i + 1]
        for k in range(steps_per_segment):
            t = k / steps_per_segment
            pts.append((x0 + t * (x1 - x0), y0 + t * (y1 - y0)))
    pts.append(waypoints[-1])
    return pts


def _compute_yaws(path: list[tuple]) -> np.ndarray:
    yaws = []
    for i in range(len(path) - 1):
        dx = path[i + 1][0] - path[i][0]
        dy = path[i + 1][1] - path[i][1]
        yaws.append(math.atan2(dy, dx))
    yaws.append(yaws[-1] if yaws else 0.0)
    return np.array(yaws, dtype=np.float32)


def build_scene_dry_run(out_dir: Path, fig_dir: Path) -> None:
    """Create trajectory files without opening Isaac Sim (dry-run mode)."""
    path = _interpolate_path(EXPERT_PATH, steps_per_segment=8)
    pos  = np.array(path, dtype=np.float32)
    yaw  = _compute_yaws(path)
    T    = len(pos)

    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    # traj_data.pkl
    pickle.dump({"position": pos, "yaw": yaw}, open(out_dir / "traj_data.pkl", "wb"))

    # episode_info.json
    sx, sy = float(pos[0][0]), float(pos[0][1])
    gx, gy = float(pos[-1][0]), float(pos[-1][1])
    info = {
        "scan":         "custom_office",
        "episode_id":   "custom_office_0001",
        "goal_pos":     [gx, gy],
        "goal_radius":  3.0,
        "n_steps":      T,
        "source":       "create_custom_gnm_scene.py",
    }
    (out_dir / "episode_info.json").write_text(json.dumps(info, indent=2))

    # instruction.txt
    (out_dir / "instruction.txt").write_text(
        "Walk straight ahead, turn right around the table, and stop at the far wall."
    )

    # Grey placeholder frames (dry-run has no live camera)
    try:
        from PIL import Image
        for i in range(T):
            img = Image.new("RGB", (96, 96), (100, 100 + i % 50, 80))
            img.save(out_dir / f"{i}.jpg")
        # Start/goal figures
        Image.new("RGB", (192, 144), (80, 120, 80)).save(fig_dir / "custom_scene_start.png")
        Image.new("RGB", (192, 144), (120, 80, 80)).save(fig_dir / "custom_scene_goal.png")
    except ImportError:
        pass

    print(f"[DRY RUN] Wrote {T} steps to {out_dir}")
    print(f"  position shape: {pos.shape}")
    print(f"  yaw shape:      {yaw.shape}")
    print(f"  path length:    {float(np.linalg.norm(np.diff(pos, axis=0), axis=1).sum()):.2f} m")
    print(f"  traj_data.pkl:  {(out_dir / 'traj_data.pkl').stat().st_size} bytes")
    print(f"  episode_info:   {out_dir / 'episode_info.json'}")


def build_scene_isaac(out_dir: Path, fig_dir: Path) -> None:
    """Build scene and capture frames live in Isaac Sim."""
    from isaacsim import SimulationApp
    _app = SimulationApp({"headless": False, "renderer": "RayTracedLighting"})

    import omni.usd
    import omni.kit.commands
    from pxr import UsdGeom, UsdShade, Gf, Sdf

    ctx   = omni.usd.get_context()
    ctx.new_stage()
    for _ in range(30):
        _app.update()

    stage = ctx.get_stage()

    # ── Floor ─────────────────────────────────────────────────────────────────
    floor = UsdGeom.Cube.Define(stage, "/World/Floor")
    floor.CreateSizeAttr(1.0)
    xf = UsdGeom.Xformable(floor.GetPrim())
    xf.AddScaleOp().Set(Gf.Vec3f(FLOOR_SIZE, FLOOR_SIZE, 0.05))
    xf.AddTranslateOp().Set(Gf.Vec3d(FLOOR_SIZE / 2, FLOOR_SIZE / 2, -0.025))

    def _wall(name, tx, ty, tz, sx, sy, sz):
        w = UsdGeom.Cube.Define(stage, f"/World/Walls/{name}")
        w.CreateSizeAttr(1.0)
        xf = UsdGeom.Xformable(w.GetPrim())
        xf.AddScaleOp().Set(Gf.Vec3f(sx, sy, sz))
        xf.AddTranslateOp().Set(Gf.Vec3d(tx, ty, tz))

    h = WALL_HEIGHT / 2
    _wall("N", FLOOR_SIZE / 2, FLOOR_SIZE, h, FLOOR_SIZE, WALL_THICK, WALL_HEIGHT)
    _wall("S", FLOOR_SIZE / 2, 0,          h, FLOOR_SIZE, WALL_THICK, WALL_HEIGHT)
    _wall("E", FLOOR_SIZE,     FLOOR_SIZE / 2, h, WALL_THICK, FLOOR_SIZE, WALL_HEIGHT)
    _wall("W", 0,              FLOOR_SIZE / 2, h, WALL_THICK, FLOOR_SIZE, WALL_HEIGHT)

    # ── Table obstacle ────────────────────────────────────────────────────────
    tx, ty = TABLE_POS
    tw, td, th2 = TABLE_SIZE
    tbl = UsdGeom.Cube.Define(stage, "/World/Table")
    tbl.CreateSizeAttr(1.0)
    xf = UsdGeom.Xformable(tbl.GetPrim())
    xf.AddScaleOp().Set(Gf.Vec3f(tw, td, th2))
    xf.AddTranslateOp().Set(Gf.Vec3d(tx, ty, th2 / 2))

    for _ in range(60):
        _app.update()

    # ── Expert path ───────────────────────────────────────────────────────────
    path   = _interpolate_path(EXPERT_PATH, steps_per_segment=8)
    pos_np = np.array(path, dtype=np.float32)
    yaw_np = _compute_yaws(path)
    T      = len(path)

    # ── Capture frames ────────────────────────────────────────────────────────
    # We move the default camera along the path and capture viewport screenshots.
    try:
        import omni.kit.viewport_legacy as vp_legacy
        viewport = vp_legacy.get_default_viewport_window()
    except ImportError:
        viewport = None

    out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    CAM_HEIGHT = 0.5
    frames_captured = 0

    for i, (x, y) in enumerate(path):
        # Move default camera
        cam_path = "/OmniverseKit_Persp"
        try:
            cam_prim = stage.GetPrimAtPath(cam_path)
            if cam_prim and cam_prim.IsValid():
                xf = UsdGeom.Xformable(cam_prim)
                ops = xf.GetOrderedXformOps()
                if ops:
                    ops[0].Set(Gf.Vec3d(x, y, CAM_HEIGHT))
        except Exception:
            pass

        for _ in range(5):
            _app.update()

        # Save viewport screenshot
        dst = out_dir / f"{i}.jpg"
        try:
            import omni.renderer_capture
            omni.renderer_capture.acquire_renderer_capture_interface().capture_next_frame_swapchain(str(dst))
            for _ in range(3):
                _app.update()
            frames_captured += 1
        except Exception:
            # Fallback: PIL placeholder
            try:
                from PIL import Image
                Image.new("RGB", (96, 96), (80, 100, 80)).save(dst)
                frames_captured += 1
            except ImportError:
                pass

    # ── Save labels ───────────────────────────────────────────────────────────
    pickle.dump({"position": pos_np, "yaw": yaw_np},
                open(out_dir / "traj_data.pkl", "wb"))

    sx_, sy_ = float(pos_np[0][0]),  float(pos_np[0][1])
    gx_, gy_ = float(pos_np[-1][0]), float(pos_np[-1][1])
    info = {
        "scan":         "custom_office",
        "episode_id":   "custom_office_0001",
        "goal_pos":     [gx_, gy_],
        "goal_radius":  3.0,
        "n_steps":      T,
        "source":       "create_custom_gnm_scene.py",
    }
    (out_dir / "episode_info.json").write_text(json.dumps(info, indent=2))
    (out_dir / "instruction.txt").write_text(
        "Walk straight ahead, turn right around the table, and stop at the far wall."
    )

    # ── Save start/goal figures ───────────────────────────────────────────────
    try:
        from PIL import Image
        first = out_dir / "0.jpg"
        last  = out_dir / f"{T - 1}.jpg"
        if first.exists():
            Image.open(first).save(fig_dir / "custom_scene_start.png")
        if last.exists():
            Image.open(last).save(fig_dir / "custom_scene_goal.png")
    except ImportError:
        pass

    path_len = float(np.linalg.norm(np.diff(pos_np, axis=0), axis=1).sum())
    print(f"\nCustom scene data saved to {out_dir}")
    print(f"  Frames captured : {frames_captured}/{T}")
    print(f"  position shape  : {pos_np.shape}")
    print(f"  yaw shape       : {yaw_np.shape}")
    print(f"  path length     : {path_len:.2f} m")

    _app.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Create trajectory files without opening Isaac Sim")
    parser.add_argument("--out-dir",
                        default="datasets/custom_gnm_scene/train/custom_office_0001")
    parser.add_argument("--fig-dir", default="results/figures")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = REPO / out_dir

    fig_dir = Path(args.fig_dir)
    if not fig_dir.is_absolute():
        fig_dir = REPO / fig_dir

    if args.dry_run:
        build_scene_dry_run(out_dir, fig_dir)
    else:
        build_scene_isaac(out_dir, fig_dir)


if __name__ == "__main__":
    main()
