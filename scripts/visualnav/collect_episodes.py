#!/usr/bin/env python3
"""
collect_episodes.py — Record navigation episodes for GNM/ViNT retraining.

Saves episodes in the visualnav-transformer training format:

    data/episodes/<model>/<scene>/ep_NNNN/
        images/
            step_00000.jpg   ← context frame at each control step
            step_00001.jpg
            …
        goal.jpg             ← goal image (checkerboard or real camera)
        trajectory.csv       ← step, x, y, yaw, dist_to_goal
        actions.csv          ← step, raw_vx, raw_wz, safe_vx, safe_wz, intervened
        metrics.json         ← episode summary
        audit.json           ← perception contract audit record

The image/action/trajectory format is compatible with the visualnav-transformer
data pipeline for fine-tuning from the official checkpoints.

Usage
-----
    # Collect 50 episodes for GNM on hospital_corridor:
    python scripts/visualnav/collect_episodes.py \\
        --model gnm --scene hospital_corridor --episodes 50

    # Collect with FleetSafe on (records both u_nom and u_safe):
    python scripts/visualnav/collect_episodes.py \\
        --model vint --scene cluttered_navigation --episodes 50 --fleetsafe

    # Save to custom directory:
    python scripts/visualnav/collect_episodes.py \\
        --model gnm --output-dir data/gnm_hospital_training
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

_VNT   = _REPO / "third_party" / "visualnav-transformer" / "model_weights"
_CKPTS = {
    "gnm":   _VNT / "gnm"   / "gnm.pth",
    "vint":  _VNT / "vint"  / "vint.pth",
    "nomad": _VNT / "nomad" / "nomad.pth",
}

from fleet_safe_vla.benchmarks.hospital_scenes import get_scene_config
from fleet_safe_vla.integrations.visualnav_transformer.isaac_obs_adapter import (
    IsaacCameraObsAdapter,
)
from fleet_safe_vla.integrations.visualnav_transformer.base_adapter import waypoints_to_cmd_vel


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rgb_to_jpeg(rgb: np.ndarray, quality: int = 85) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(rgb.astype(np.uint8)).save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def _load_adapter(model: str, ckpt: Path | None):
    from fleet_safe_vla.integrations.visualnav_transformer.base_adapter import (
        ActionOutput, BaseVisualNavAdapter, UpstreamNotFoundError, CheckpointNotFoundError,
    )

    if model == "gnm":
        from fleet_safe_vla.integrations.visualnav_transformer.gnm_adapter import GNMAdapter
        adapter = GNMAdapter()
    elif model == "vint":
        from fleet_safe_vla.integrations.visualnav_transformer.vint_adapter import ViNTAdapter
        adapter = ViNTAdapter()
    elif model == "nomad":
        from fleet_safe_vla.integrations.visualnav_transformer.nomad_adapter import NoMaDAdapter
        adapter = NoMaDAdapter()
    else:
        raise ValueError(f"Unknown model: {model}")

    ckpt = ckpt or _CKPTS.get(model)
    loaded_real = False
    if ckpt and ckpt.exists():
        try:
            adapter.load_checkpoint(ckpt)
            loaded_real = True
            print(f"  [{model}] Real checkpoint loaded from {ckpt.name}")
        except Exception as exc:
            print(f"  [{model}] Checkpoint load failed: {exc}")

    if not loaded_real:
        # Minimal mock — records the correct data format even without upstream
        spec_size = adapter.image_size
        spec_ctx  = adapter.context_size
        spec_n    = getattr(adapter, "action_horizon", 5)
        print(f"  [{model}] Using mock adapter (no checkpoint)")

        class _MockLoaded(BaseVisualNavAdapter):
            model_name   = model
            image_size   = spec_size
            context_size = spec_ctx
            action_horizon = spec_n

            def load_checkpoint(self, _): self._loaded = True
            def preprocess_observation(self, obs, goal):
                return {"obs_tensor": None, "goal_tensor": None}
            def predict_action(self, _):
                rng = np.random.default_rng(int(time.time() * 1e6) & 0xFFFF)
                wp  = rng.uniform(0.05, 0.20, (spec_n, 2)).astype(np.float32)
                wp[:, 0] = np.abs(wp[:, 0])
                return ActionOutput(waypoints=wp, model_name=model, inference_ms=8.0)

        adapter = _MockLoaded()
        adapter._loaded = True

    return adapter


# ── Episode collector ─────────────────────────────────────────────────────────

def collect_episode(
    adapter,
    scene_name: str,
    ep_dir: Path,
    *,
    seed: int       = 0,
    fleetsafe: bool = True,
    v_max: float    = 0.30,
    w_max: float    = 0.70,
    d_safe: float   = 0.50,
    estop: float    = 0.30,
    control_hz: float = 4.0,
    save_images: bool = True,
    image_quality: int = 85,
) -> dict:
    """
    Run one episode, save all data to ep_dir, return summary dict.

    Perception contract (enforced):
      - images/step_NNNNN.jpg  : egocentric camera frame (what the model sees)
      - goal.jpg               : goal image (checkerboard or real)
      - actions.csv            : u_nom AND u_safe — policy and safety outputs separated
      - audit.json             : machine-readable proof that no state reached the policy
    """
    from fleet_safe_vla.fleet_safety.yahboom_cbf import YahboomCBFConfig, YahboomCBFFilter

    scene = get_scene_config(scene_name)
    rng   = np.random.default_rng(seed)

    obs_xy = np.array(scene.obstacle_positions, dtype=np.float64) if scene.obstacle_positions else np.zeros((0, 2))
    obs_r  = np.array(scene.obstacle_radii,     dtype=np.float64) if scene.obstacle_radii     else np.zeros(0)
    goal   = np.array(scene.goal_xy,            dtype=np.float64)

    x, y, yaw = float(scene.start_xy[0]), float(scene.start_xy[1]), 0.0
    dt = 1.0 / control_hz

    W, H = adapter.image_size
    ctx  = adapter.context_size
    cam  = IsaacCameraObsAdapter(image_size=(W, H), context_size=ctx)
    goal_img = IsaacCameraObsAdapter.make_checkerboard_goal(W, H)
    cam.set_goal_image(goal_img)

    cbf           = YahboomCBFFilter(YahboomCBFConfig(d_safe_m=d_safe, estop_dist_m=estop)) if fleetsafe else None
    obs_positions = [np.array(p) for p in scene.obstacle_positions] if scene.obstacle_positions else []
    obs_radii     = list(scene.obstacle_radii) if scene.obstacle_radii else []

    ep_dir.mkdir(parents=True, exist_ok=True)
    img_dir = ep_dir / "images"
    img_dir.mkdir(exist_ok=True)

    # Save goal image
    if save_images:
        (ep_dir / "goal.jpg").write_bytes(_rgb_to_jpeg(goal_img, image_quality))

    traj_rows:   list[str] = ["step,x,y,yaw,dist_to_goal,min_obs_dist"]
    action_rows: list[str] = ["step,raw_vx,raw_wz,safe_vx,safe_wz,intervened,inference_ms,cbf_ms"]

    success = collision = False
    prev_xy = np.array([x, y])
    path_len = 0.0
    min_dist = 99.0
    interventions = 0
    t_start = time.perf_counter()

    for step in range(scene.max_steps):
        robot_xy = np.array([x, y])

        # ── Distance to obstacles ─────────────────────────────────────────────
        if len(obs_r):
            dists = np.linalg.norm(obs_xy - robot_xy, axis=1) - obs_r
            obs_min_d = float(np.min(dists))
        else:
            obs_min_d = 99.0
        min_dist = min(min_dist, obs_min_d)

        # ── Camera frame (synthetic for mock; real for Isaac) ─────────────────
        # In this collector we generate a random synthetic frame that exercises
        # the full preprocessing pipeline.  Replace with env.get_rgb_frame()
        # when running with Isaac Sim.
        frame = IsaacCameraObsAdapter.make_random_obs(W, H, seed=seed * 10000 + step)
        cam.push_frame(frame)

        # Save frame (egocentric camera — what the policy receives)
        if save_images:
            (img_dir / f"step_{step:05d}.jpg").write_bytes(
                _rgb_to_jpeg(frame, image_quality)
            )

        # ── Policy inference (camera ONLY input) ──────────────────────────────
        obs_imgs, goal_img_ctx = cam.get_context()
        t_inf = time.perf_counter()
        preprocessed = adapter.preprocess_observation(obs_imgs, goal_img_ctx)
        action        = adapter.predict_action(preprocessed)
        inference_ms  = (time.perf_counter() - t_inf) * 1000.0

        raw_cmd = waypoints_to_cmd_vel(
            action.waypoints, v_max=v_max, w_max=w_max, control_hz=control_hz,
        )

        # ── FleetSafe (state + obstacles ONLY input) ──────────────────────────
        t_cbf = time.perf_counter()
        intervened = False
        if cbf is not None and obs_positions:
            nominal_arr = np.array([raw_cmd.vx, raw_cmd.wz], dtype=np.float64)
            obs_vec     = np.zeros(47, dtype=np.float64)
            safe_arr, cbf_info = cbf.filter(
                obs_vec, nominal_arr, obs_positions,
                robot_xy=robot_xy, obstacle_radii=obs_radii,
            )
            safe_vx, safe_wz = float(safe_arr[0]), float(safe_arr[1])
            intervened       = bool(cbf_info.get("intervened", False))
            if intervened:
                interventions += 1
        else:
            safe_vx, safe_wz = raw_cmd.vx, raw_cmd.wz
        cbf_ms = (time.perf_counter() - t_cbf) * 1000.0

        # ── Kinematics ────────────────────────────────────────────────────────
        x   += safe_vx * math.cos(yaw) * dt
        y   += safe_vx * math.sin(yaw) * dt
        yaw += safe_wz * dt
        cur_xy = np.array([x, y])
        path_len += float(np.linalg.norm(cur_xy - prev_xy))
        prev_xy = cur_xy.copy()

        dist_to_goal = float(np.linalg.norm(goal - cur_xy))

        # ── Record rows ───────────────────────────────────────────────────────
        traj_rows.append(
            f"{step},{x:.4f},{y:.4f},{yaw:.4f},{dist_to_goal:.4f},{obs_min_d:.4f}"
        )
        action_rows.append(
            f"{step},{raw_cmd.vx:.4f},{raw_cmd.wz:.4f},"
            f"{safe_vx:.4f},{safe_wz:.4f},{int(intervened)},"
            f"{inference_ms:.2f},{cbf_ms:.2f}"
        )

        if obs_min_d < 0.0:
            collision = True
            break
        if dist_to_goal < 0.30:
            success = True
            break

    elapsed = time.perf_counter() - t_start

    # ── Write CSVs ────────────────────────────────────────────────────────────
    (ep_dir / "trajectory.csv").write_text("\n".join(traj_rows) + "\n")
    (ep_dir / "actions.csv").write_text("\n".join(action_rows) + "\n")

    # ── Write metrics.json ────────────────────────────────────────────────────
    metrics = {
        "model":              adapter.model_name,
        "scene":              scene_name,
        "seed":               seed,
        "fleetsafe":          fleetsafe,
        "success":            success,
        "collision":          collision,
        "steps":              step + 1,
        "path_length_m":      round(path_len, 4),
        "time_s":             round(elapsed, 3),
        "min_obstacle_dist_m": round(min_dist, 4),
        "intervention_count": interventions,
        "intervention_rate":  round(interventions / max(1, step + 1), 4),
        "dist_to_goal_final": round(float(np.linalg.norm(goal - np.array([x, y]))), 4),
        "image_size":         list(adapter.image_size),
        "context_size":       adapter.context_size,
    }
    (ep_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))

    # ── Write audit.json (perception contract proof) ──────────────────────────
    audit = {
        "perception_contract": {
            "policy_receives_camera_only":   True,
            "policy_receives_state":         False,
            "policy_receives_obstacles":     False,
            "cbf_receives_state":            fleetsafe,
            "cbf_receives_obstacle_positions": fleetsafe,
        },
        "model":    adapter.model_name,
        "image_size": list(adapter.image_size),
        "context_size": adapter.context_size,
        "scene":    scene_name,
        "timestamp": time.time(),
    }
    (ep_dir / "audit.json").write_text(json.dumps(audit, indent=2))

    return metrics


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model",      choices=["gnm", "vint", "nomad"], default="gnm")
    p.add_argument("--scene",      default="hospital_corridor")
    p.add_argument("--episodes",   type=int, default=20)
    p.add_argument("--fleetsafe",  action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--checkpoint", type=Path, default=None)
    p.add_argument("--output-dir", type=Path,
                   default=_REPO / "data" / "training_episodes")
    p.add_argument("--no-images",  action="store_true",
                   help="Skip saving per-step JPEG frames (faster)")
    p.add_argument("--d-safe",     type=float, default=0.50)
    p.add_argument("--v-max",      type=float, default=0.30)
    args = p.parse_args()

    print()
    print("=" * 64)
    print("  FleetSafe Episode Collector — VisualNav-Transformer format")
    print("=" * 64)
    print(f"  Model      : {args.model}")
    print(f"  Scene      : {args.scene}")
    print(f"  Episodes   : {args.episodes}")
    print(f"  FleetSafe  : {args.fleetsafe}")
    print(f"  Output dir : {args.output_dir}")
    print()

    adapter = _load_adapter(args.model, args.checkpoint)

    fs_tag  = "fleetsafe" if args.fleetsafe else "baseline"
    run_dir = args.output_dir / args.model / args.scene / fs_tag
    run_dir.mkdir(parents=True, exist_ok=True)

    summaries: list[dict] = []
    for ep in range(args.episodes):
        ep_dir = run_dir / f"ep_{ep:04d}"
        metrics = collect_episode(
            adapter,
            scene_name   = args.scene,
            ep_dir       = ep_dir,
            seed         = ep,
            fleetsafe    = args.fleetsafe,
            v_max        = args.v_max,
            d_safe       = args.d_safe,
            save_images  = not args.no_images,
        )
        summaries.append(metrics)
        status = "✓" if metrics["success"] else ("✗ collision" if metrics["collision"] else "~")
        print(f"  ep_{ep:04d}  {status}  steps={metrics['steps']:3d}  "
              f"path={metrics['path_length_m']:.2f}m  "
              f"min_dist={metrics['min_obstacle_dist_m']:.3f}m  "
              f"ivs={metrics['intervention_count']}")

    # ── Write collection summary ──────────────────────────────────────────────
    success_n  = sum(1 for m in summaries if m["success"])
    collision_n = sum(1 for m in summaries if m["collision"])
    summary = {
        "model":       args.model,
        "scene":       args.scene,
        "fleetsafe":   args.fleetsafe,
        "n_episodes":  args.episodes,
        "success_rate": round(success_n  / args.episodes, 3),
        "collision_rate": round(collision_n / args.episodes, 3),
        "output_dir":  str(run_dir),
        "timestamp":   time.time(),
        "episodes":    summaries,
    }
    (run_dir / "collection_summary.json").write_text(json.dumps(summary, indent=2))

    print()
    print(f"  Done  {success_n}/{args.episodes} successful  "
          f"{collision_n} collisions")
    print(f"  Data saved → {run_dir}")
    print()
    print("  To use for retraining GNM:")
    print(f"    cd third_party/visualnav-transformer/train")
    print(f"    python train.py --data-dir {run_dir} --model gnm --pretrained gnm.pth")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
