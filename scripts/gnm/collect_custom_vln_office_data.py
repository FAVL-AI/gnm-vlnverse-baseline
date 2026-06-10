"""
collect_custom_vln_office_data.py — Collect RGB data for CustomVLN-Office
=========================================================================
Executes scripted navigation episodes defined in tasks.yaml, captures RGB
frames, and records x/y/yaw + local waypoint/action labels.

Dry-run: generates complete dataset structure with synthetic RGB frames
         (no Isaac Sim required — proves the full pipeline).
Isaac:   captures real rendered frames from the scene.

NO VLNVerse assets or datasets are used.

Output structure per episode:
  datasets/custom_vln_office/{split}/{episode_id}/
    rgb/000000.jpg  … rgb/000NNN.jpg
    traj_data.pkl
    actions.jsonl
    metadata.json

Usage:
  python3 scripts/gnm/collect_custom_vln_office_data.py --dry-run
  conda run -n isaac python scripts/gnm/collect_custom_vln_office_data.py
"""
import argparse
import json
import math
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import yaml

REPO       = Path(__file__).resolve().parents[2]
TASKS_YAML = REPO / "configs/custom_vln_office/tasks.yaml"
SCENE_USD  = REPO / "assets/custom_vln_office/custom_vln_office.usd"
DATA_ROOT  = REPO / "datasets/custom_vln_office"
STEPS_PER_SEG = 10     # frames per waypoint segment
WAYPOINT_HORIZON = 5   # local waypoint offset


def _load_tasks() -> dict:
    with open(TASKS_YAML) as f:
        return yaml.safe_load(f)


def _interpolate(wps: list[tuple], steps: int = STEPS_PER_SEG) -> list[tuple]:
    pts = []
    for i in range(len(wps) - 1):
        x0, y0 = wps[i]
        x1, y1 = wps[i + 1]
        for k in range(steps):
            t = k / steps
            pts.append((x0 + t * (x1 - x0), y0 + t * (y1 - y0)))
    pts.append(wps[-1])
    return pts


def _compute_yaws(path: list[tuple]) -> np.ndarray:
    yaws = []
    for i in range(len(path) - 1):
        dx = path[i + 1][0] - path[i][0]
        dy = path[i + 1][1] - path[i][1]
        yaws.append(math.atan2(dy, dx))
    yaws.append(yaws[-1] if yaws else 0.0)
    return np.array(yaws, dtype=np.float32)


def _local_waypoint(positions, yaws, frame_idx, horizon=WAYPOINT_HORIZON):
    T = len(positions)
    tgt = min(frame_idx + horizon, T - 1)
    wx  = positions[tgt][0] - positions[frame_idx][0]
    wy  = positions[tgt][1] - positions[frame_idx][1]
    yaw = float(yaws[frame_idx])
    cos_y, sin_y = math.cos(-yaw), math.sin(-yaw)
    lx = cos_y * wx - sin_y * wy
    ly = sin_y * wx + cos_y * wy
    return float(lx), float(ly)


def _placeholder_frame(i: int, split: str, ep_id: str) -> "PIL.Image":
    from PIL import Image, ImageDraw, ImageFont
    w, h = 480, 360
    # colour gradient encodes frame position
    hue_r = min(255, 40 + i * 2)
    hue_g = min(255, 60 + i)
    img = Image.new("RGB", (w, h), (hue_r, hue_g, 60))
    draw = ImageDraw.Draw(img)
    draw.rectangle([(0, 0), (w, 40)], fill=(20, 25, 40))
    try:
        from PIL import ImageFont as IFnt
        for path in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]:
            try:
                font = IFnt.truetype(path, 18)
                break
            except Exception:
                font = IFnt.load_default()
    except Exception:
        font = None
    label = f"{ep_id} | frame {i:04d} | CustomVLN-Office"
    draw.text((8, 8), label, fill=(230, 230, 80), font=font)
    draw.text((8, 330), "NO VLNVERSE ASSETS  |  Isaac Sim primitives", fill=(120, 180, 120), font=font)
    return img


def _save_episode(ep: dict, split: str, dry_run: bool,
                  get_frame_fn=None) -> Path:
    ep_id   = ep["episode_id"]
    instr   = ep["instruction"]
    wps     = [(w["x"], w["y"]) for w in ep["waypoints"]]
    start_p = ep["start_pose"]
    goal_p  = ep["goal_pose"]

    path    = _interpolate(wps, STEPS_PER_SEG)
    pos_np  = np.array(path, dtype=np.float32)
    yaw_np  = _compute_yaws(path)
    T       = len(path)

    gx, gy  = float(pos_np[-1][0]), float(pos_np[-1][1])
    sx, sy  = float(pos_np[0][0]),  float(pos_np[0][1])
    path_len = float(np.linalg.norm(np.diff(pos_np, axis=0), axis=1).sum())
    start_yaw = float(yaw_np[0])
    goal_yaw  = float(yaw_np[-1])

    out_dir = DATA_ROOT / split / ep_id
    rgb_dir = out_dir / "rgb"
    out_dir.mkdir(parents=True, exist_ok=True)
    rgb_dir.mkdir(parents=True, exist_ok=True)

    rgb_paths = []
    for i in range(T):
        frame_path = rgb_dir / f"{i:06d}.jpg"
        rgb_paths.append(str(frame_path.relative_to(REPO)))
        if dry_run:
            img = _placeholder_frame(i, split, ep_id)
            img.save(frame_path)
        elif get_frame_fn is not None:
            img = get_frame_fn(path[i][0], path[i][1], float(yaw_np[i]))
            img.save(frame_path)

    # Actions: consecutive-pose deltas
    actions = []
    for i in range(T - 1):
        dx = pos_np[i + 1][0] - pos_np[i][0]
        dy = pos_np[i + 1][1] - pos_np[i][1]
        dyaw = float(yaw_np[i + 1]) - float(yaw_np[i])
        actions.append((float(dx), float(dy), float(dyaw)))
    actions.append((0.0, 0.0, 0.0))

    local_wps = [_local_waypoint(pos_np, yaw_np, i) for i in range(T)]

    # traj_data.pkl
    pkl_data = {
        "position":        pos_np,
        "yaw":             yaw_np,
        "rgb_paths":       rgb_paths,
        "actions":         actions,
        "local_waypoints": local_wps,
        "instruction":     instr,
        "scene_id":        "custom_vln_office",
        "episode_id":      ep_id,
        "start_pos":       [sx, sy],
        "start_yaw":       start_yaw,
        "goal_pos":        [gx, gy],
        "goal_yaw":        goal_yaw,
        "n_steps":         T,
        "path_length_m":   path_len,
    }
    with open(out_dir / "traj_data.pkl", "wb") as f:
        pickle.dump(pkl_data, f)

    # actions.jsonl
    goal_pos_arr = np.array([gx, gy])
    with open(out_dir / "actions.jsonl", "w") as f:
        for i in range(T):
            dist = float(np.linalg.norm(pos_np[i] - goal_pos_arr))
            lx, ly = local_wps[i]
            dx, dy, dyaw = actions[i]
            record = {
                "frame_index":       i,
                "timestamp":         round(i * 0.1, 3),
                "x":                 round(float(pos_np[i][0]), 4),
                "y":                 round(float(pos_np[i][1]), 4),
                "yaw":               round(float(yaw_np[i]), 4),
                "action_dx":         round(dx, 4),
                "action_dy":         round(dy, 4),
                "action_dyaw":       round(dyaw, 4),
                "local_waypoint_x":  round(lx, 4),
                "local_waypoint_y":  round(ly, 4),
                "rgb_image_path":    rgb_paths[i],
                "distance_to_goal":  round(dist, 4),
            }
            f.write(json.dumps(record) + "\n")

    # metadata.json
    meta = {
        "episode_id":          ep_id,
        "scene_id":            "custom_vln_office",
        "split":               split,
        "instruction":         instr,
        "start_pos":           [round(sx, 4), round(sy, 4)],
        "start_yaw":           round(start_yaw, 4),
        "goal_pos":            [round(gx, 4), round(gy, 4)],
        "goal_yaw":            round(goal_yaw, 4),
        "n_steps":             T,
        "path_length_m":       round(path_len, 4),
        "goal_radius_m":       2.0,
        "source":              "collect_custom_vln_office_data.py" + (" --dry-run" if dry_run else ""),
        "isaac_assets_used":   False,
        "vlnverse_assets_used": False,
        "gnm_input":           "current RGB frame + goal RGB frame",
        "gnm_output":          "local waypoint (delta_x, delta_y) in robot frame",
        "label_source":        "derived from consecutive trajectory poses (traj_data.pkl)",
    }
    with open(out_dir / "metadata.json", "w") as f:
        json.dump(meta, f, indent=2)

    print(f"  {split}/{ep_id}  T={T}  len={path_len:.1f} m  "
          f"start=({sx:.1f},{sy:.1f})  goal=({gx:.1f},{gy:.1f})")
    return out_dir


def run_dry_run(tasks: dict) -> None:
    print("Collecting CustomVLN-Office data (dry-run — no Isaac Sim)")
    print("=" * 60)
    for ep in tasks["episodes"]:
        _save_episode(ep, ep["split"], dry_run=True)

    # Counts
    t_count = len([e for e in tasks["episodes"] if e["split"] == "train"])
    v_count = len([e for e in tasks["episodes"] if e["split"] == "val"])
    print()
    print(f"  Train episodes : {t_count}")
    print(f"  Val   episodes : {v_count}")
    print(f"  Dataset root   : {DATA_ROOT}")
    print(f"  No VLNVerse assets used.")
    print(f"  RGB frames are synthetic placeholders (dry-run mode).")
    print()
    print("To capture real rendered frames, run inside Isaac Sim:")
    print("  conda run -n isaac python scripts/gnm/collect_custom_vln_office_data.py")


def run_isaac(tasks: dict) -> None:
    from isaacsim import SimulationApp
    _app = SimulationApp({"headless": False, "renderer": "RayTracedLighting"})

    import omni.usd
    from pxr import UsdGeom, Gf

    ctx = omni.usd.get_context()
    if SCENE_USD.exists():
        ctx.open_stage(str(SCENE_USD))
    else:
        print(f"WARNING: {SCENE_USD} not found. Run create_custom_vln_office_scene.py first.")
        ctx.new_stage()
    for _ in range(120):
        _app.update()
        time.sleep(0.01)
    stage = ctx.get_stage()

    CAM_PATH = "/World/Cameras/RobotCam"
    cam_prim = stage.GetPrimAtPath(CAM_PATH) if stage else None

    def get_frame(x: float, y: float, yaw: float):
        from PIL import Image
        if cam_prim and cam_prim.IsValid():
            xf = UsdGeom.Xformable(cam_prim)
            ops = xf.GetOrderedXformOps()
            yaw_deg = math.degrees(yaw)
            if ops:
                for op in ops:
                    if "translate" in str(op.GetOpType()).lower():
                        op.Set(Gf.Vec3d(x, y, 1.2))
                    elif "rotate" in str(op.GetOpType()).lower():
                        op.Set(Gf.Vec3f(90.0, 0.0, yaw_deg - 90.0))
        for _ in range(10):
            _app.update()
            time.sleep(0.02)
        # Try capture; fallback to placeholder
        import tempfile
        tmp = Path(tempfile.mktemp(suffix=".jpg"))
        try:
            import omni.renderer_capture
            omni.renderer_capture.acquire_renderer_capture_interface()\
                .capture_next_frame_swapchain(str(tmp))
            for _ in range(5):
                _app.update()
            if tmp.exists():
                img = Image.open(tmp).convert("RGB").resize((480, 360))
                tmp.unlink(missing_ok=True)
                return img
        except Exception:
            pass
        return Image.new("RGB", (480, 360), (80, 100, 80))

    for ep in tasks["episodes"]:
        _save_episode(ep, ep["split"], dry_run=False, get_frame_fn=get_frame)

    _app.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    tasks = _load_tasks()
    if args.dry_run:
        run_dry_run(tasks)
    else:
        run_isaac(tasks)


if __name__ == "__main__":
    main()
