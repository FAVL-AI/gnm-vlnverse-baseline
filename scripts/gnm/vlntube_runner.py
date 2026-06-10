#!/usr/bin/env python3
"""scripts/gnm/vlntube_runner.py
Render GNM training episodes from VLNTube prebuilt splits using Isaac Sim.

This script runs INSIDE Isaac Sim's bundled Python (not the gnm_train conda env).
It replays reference paths from the prebuilt split JSON files, captures RGB frames
at each step, and writes GNM-format output (numbered JPEGs + traj_data.pkl).

Data flow
──────────
  prebuilt_data/raw_data/final_splits/<split>.json.gz
    ↓ filter to scenes with local USD files
  datasets/vlntube/envs/<scan>/<scan>.usd
    ↓ Isaac Sim loads scene, teleports camera to each path step
  RGB frames (224×224, 90° HFOV) captured by replicator
    ↓
  datasets/vlntube/<split>/<episode_id>/
    0.jpg  1.jpg  ...  traj_data.pkl  instruction.txt

Camera specification
─────────────────────
  Resolution: 224×224 pixels
  HFOV: 90 degrees
  Height: 1.5 m above ground (eye level)
  Frame rate: one frame per reference path step

Running this script
────────────────────
  Method A — from Isaac Python console:
    exec(open('scripts/gnm/vlntube_runner.py').read())

  Method B — from command line with Isaac Python:
    ~/.local/share/ov/pkg/isaac-sim-4.5.0/python.sh scripts/gnm/vlntube_runner.py \\
        --split fine_train --scenes kujiale_0003 --max-episodes 100

  Method C — from 02_generate_data.sh --generate:
    bash scripts/gnm/02_generate_data.sh --generate --scenes kujiale_0003

Prerequisite: USD scene files must exist in datasets/vlntube/envs/<scan>/
  Currently available:  kujiale_0003
  See datasets/vlntube/envs/ for full list.

To get more scenes:
  Download additional kujiale_XXXX.zip from the VLNVerse dataset release
  and unzip into datasets/vlntube/envs/
"""
from __future__ import annotations

import argparse
import gzip
import json
import logging
import math
import pathlib
import pickle
import sys
from typing import Optional

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("vlntube_runner")

# ── Isaac Sim initialisation ──────────────────────────────────────────────────
# pip-installed Isaac Sim (5.x) requires SimulationApp to be created BEFORE
# any omni.* or pxr import.  Omniverse Launcher installs (4.x python.sh) have
# the runtime already active, so the try-block is a no-op for them.
_simulation_app = None


def _ensure_sim_app() -> None:
    """Start SimulationApp if running with pip-installed Isaac Sim."""
    global _simulation_app
    if _simulation_app is not None:
        return
    try:
        try:
            from isaacsim import SimulationApp
        except ImportError:
            from isaacsim.simulation_app import SimulationApp
        _simulation_app = SimulationApp({
            "headless": True,
            "renderer": "RayTracedLighting",
            "anti_aliasing": 0,
        })
        logger.info("SimulationApp started (headless, pip-install mode)")
    except ImportError:
        # Omniverse Launcher mode — runtime already active, nothing to do
        pass

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SPLITS_ROOT = REPO_ROOT / "datasets/vlntube/prebuilt_data/raw_data/final_splits"
ENVS_ROOT   = REPO_ROOT / "datasets/vlntube/envs"
OUTPUT_ROOT = REPO_ROOT / "datasets/vlntube"

# Camera: 224×224, 90° HFOV, 1.5 m height
CAM_RES     = (224, 224)
CAM_HFOV    = 90.0
CAM_HEIGHT  = 1.5


USD_ROOT_NAME = "start_result_navigation.usd"


def list_available_scenes() -> list[str]:
    """Return names of USD scenes that exist locally."""
    return [
        d.name for d in ENVS_ROOT.iterdir()
        if d.is_dir() and not d.name.startswith(".")
        and (d / USD_ROOT_NAME).exists()
    ]


def load_split(split_name: str) -> list[dict]:
    """Load prebuilt split episodes from .json.gz."""
    gz_path = SPLITS_ROOT / f"{split_name}.json.gz"
    if not gz_path.exists():
        raise FileNotFoundError(f"Split not found: {gz_path}")
    with gzip.open(gz_path) as f:
        return json.load(f)["episodes"]


def quat_to_yaw(quat: list[float]) -> float:
    """Convert quaternion [w, x, y, z] to yaw (radians)."""
    w, x, y, z = quat
    return math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))


def render_episode(
    episode: dict,
    output_dir: pathlib.Path,
    camera_prim: str = "/World/GNMCamera",
) -> Optional[pathlib.Path]:
    """Render one episode: teleport camera along reference path, capture frames.

    Runs inside Isaac Sim's Python environment.

    Returns output_dir on success, None on failure.
    """
    _ensure_sim_app()  # no-op if already running (Launcher mode)
    try:
        import omni.usd
        import omni.kit.app
        from pxr import Gf, UsdGeom
        import omni.replicator.core as rep
    except ImportError as e:
        logger.error(f"Not running inside Isaac Sim: {e}")
        return None

    output_dir.mkdir(parents=True, exist_ok=True)

    ref_path    = episode["reference_path"]  # list of [x, y, z]
    goal_pos    = episode["goals"]["position"]
    instruction = episode["instruction"]["instruction_text"]
    T           = len(ref_path)

    # ── Create / get camera ───────────────────────────────────────────────────
    stage = omni.usd.get_context().get_stage()
    if not stage.GetPrimAtPath(camera_prim).IsValid():
        cam_prim = stage.DefinePrim(camera_prim, "Camera")
        _configure_camera(cam_prim)

    render_prod = rep.create.render_product(camera_prim, resolution=CAM_RES)
    rgb_annot   = rep.AnnotatorRegistry.get_annotator("rgb")
    rgb_annot.attach([render_prod])

    # Pre-create XformOps once; set values per step to avoid USD op stacking.
    xf = UsdGeom.Xformable(stage.GetPrimAtPath(camera_prim))
    xf.ClearXformOpOrder()
    translate_op = xf.AddTranslateOp()
    rotate_op    = xf.AddRotateZOp()

    # Warm up the ray tracer at the episode start position so frame 0 is
    # not dark.  RayTracedLighting converges over the first few renders.
    if ref_path:
        x0, y0, z0 = ref_path[0]
        translate_op.Set(Gf.Vec3d(x0, y0, z0 + CAM_HEIGHT))
        rotate_op.Set(0.0)
        for _ in range(3):
            rep.orchestrator.step(delta_time=0.0)

    positions = []
    yaws      = []
    n_saved   = 0

    for step, pos3d in enumerate(ref_path):
        x, y, z = pos3d
        # Compute heading toward next point (or carry last heading at end)
        if step < T - 1:
            nx, ny = ref_path[step + 1][0], ref_path[step + 1][1]
            heading = math.atan2(ny - y, nx - x)
        else:
            heading = yaws[-1] if yaws else 0.0

        # Teleport camera — set existing ops, no stacking
        translate_op.Set(Gf.Vec3d(x, y, z + CAM_HEIGHT))
        rotate_op.Set(math.degrees(heading))

        # rep.orchestrator.step() flushes the replicator render pipeline
        # synchronously; app.update() alone leaves the annotator buffer empty.
        rep.orchestrator.step(delta_time=0.0)

        # Capture frame — handle both dict (5.x API) and plain array (4.x)
        rgb_raw  = rgb_annot.get_data()
        rgb_data = rgb_raw.get("data") if isinstance(rgb_raw, dict) else rgb_raw
        if rgb_data is not None and rgb_data.size > 0:
            import cv2
            frame = rgb_data[..., :3].astype(np.uint8)
            cv2.imwrite(str(output_dir / f"{step}.jpg"), frame[..., ::-1],
                        [cv2.IMWRITE_JPEG_QUALITY, 95])
            n_saved += 1

        positions.append([x, y])
        yaws.append(heading)

    # ── Save traj_data.pkl ────────────────────────────────────────────────────
    traj_data = {
        "position": np.array(positions, dtype=np.float32),
        "yaw":      np.array(yaws,      dtype=np.float32),
    }
    with open(output_dir / "traj_data.pkl", "wb") as f:
        pickle.dump(traj_data, f)

    # ── Save instruction ──────────────────────────────────────────────────────
    (output_dir / "instruction.txt").write_text(instruction)

    # ── Save goal info ────────────────────────────────────────────────────────
    with open(output_dir / "episode_info.json", "w") as f:
        json.dump({
            "scan":        episode["scan"],
            "episode_id":  episode["episode_id"],
            "goal_pos":    goal_pos[:2],
            "goal_radius": episode["goals"]["radius"],
            "n_steps":     T,
        }, f, indent=2)

    logger.info(f"  Rendered {n_saved}/{T} frames → {output_dir.name}")
    return output_dir if n_saved > 0 else None


def _configure_camera(cam_prim) -> None:
    """Set camera intrinsics for 90° HFOV at 224×224."""
    from pxr import UsdGeom
    camera = UsdGeom.Camera(cam_prim)
    h_aperture   = 20.955
    focal_length = h_aperture / (2 * math.tan(math.radians(CAM_HFOV / 2)))
    camera.GetFocalLengthAttr().Set(focal_length)
    camera.GetHorizontalApertureAttr().Set(h_aperture)


def load_scene(scan: str) -> bool:
    """Open a kujiale USD scene in Isaac Sim."""
    _ensure_sim_app()
    usd_path = ENVS_ROOT / scan / USD_ROOT_NAME
    if not usd_path.exists():
        logger.warning(f"USD not found: {usd_path}")
        return False
    try:
        import omni.usd
        omni.usd.get_context().open_stage(str(usd_path))
        logger.info(f"Opened scene: {usd_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to open {usd_path}: {e}")
        return False


def run(
    split:        str   = "fine_train",
    scenes:       Optional[list[str]] = None,
    max_episodes: int   = 10000,
    output_root:  pathlib.Path = OUTPUT_ROOT,
    overwrite:    bool  = False,
) -> dict:
    """Main entry point: render episodes for all available scenes in a split.

    Parameters
    ----------
    split        : Name of prebuilt split (without .json.gz)
    scenes       : List of scene names to process (None = all available)
    max_episodes : Stop after this many episodes
    output_root  : Root of output dataset
    overwrite    : Re-render already-completed episodes

    Returns
    -------
    dict with rendered, skipped, failed counts
    """
    available = list_available_scenes()
    if not available:
        logger.error(
            f"No USD scenes found under {ENVS_ROOT}.\n"
            "Download kujiale_XXXX scenes and place them in datasets/vlntube/envs/."
        )
        return {"rendered": 0, "skipped": 0, "failed": 0}

    target_scenes = set(scenes) if scenes else set(available)
    to_render     = sorted(target_scenes & set(available))

    if not to_render:
        logger.warning(
            f"None of the requested scenes {sorted(target_scenes)} are available.\n"
            f"Available: {available}"
        )
        return {"rendered": 0, "skipped": 0, "failed": 0}

    logger.info(f"Rendering split={split}  scenes={to_render}")

    episodes = load_split(split)
    episodes = [e for e in episodes if e["scan"] in to_render]
    logger.info(f"Episodes to render: {len(episodes)} (capped at {max_episodes})")

    # Determine output split directory
    split_out = "train" if "train" in split else ("val" if "val" in split else "test")
    out_dir   = output_root / split_out

    rendered = skipped = failed = 0
    current_scene: Optional[str] = None

    for ep in episodes[:max_episodes]:
        scan = ep["scan"]
        ep_id = f"{scan}_{ep['episode_id']}"
        ep_dir = out_dir / ep_id

        if not overwrite and (ep_dir / "traj_data.pkl").exists():
            skipped += 1
            continue

        # Load scene if changed
        if scan != current_scene:
            if not load_scene(scan):
                failed += 1
                continue
            current_scene = scan

        result = render_episode(ep, ep_dir)
        if result:
            rendered += 1
        else:
            failed += 1

        if (rendered + failed) % 50 == 0:
            logger.info(f"Progress: {rendered} rendered, {skipped} skipped, {failed} failed")

    logger.info(f"Done: {rendered} rendered, {skipped} skipped, {failed} failed")
    return {"rendered": rendered, "skipped": skipped, "failed": failed}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", default="fine_train",
                        choices=["fine_train", "fine_val", "fine_val_unseen", "fine_test",
                                 "coarse_train", "coarse_val", "coarse_val_unseen", "coarse_test"])
    parser.add_argument("--scenes", default=None,
                        help="Comma-separated scene names, e.g. kujiale_0003,kujiale_0010")
    parser.add_argument("--max-episodes", type=int, default=10000)
    parser.add_argument("--output", default=str(OUTPUT_ROOT))
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--list-scenes", action="store_true",
                        help="Print available scenes and episode counts, then exit")
    args = parser.parse_args()

    if args.list_scenes:
        available = list_available_scenes()
        print(f"Available USD scenes ({len(available)}):")
        for sc in sorted(available):
            print(f"  {sc}")
        print()
        for split_name in ["fine_train", "fine_val_unseen", "fine_test"]:
            try:
                eps = load_split(split_name)
                for sc in sorted(available):
                    n = sum(1 for e in eps if e["scan"] == sc)
                    if n:
                        print(f"  {split_name}: {n} episodes for {sc}")
            except FileNotFoundError:
                pass
        sys.exit(0)

    scenes = [s.strip() for s in args.scenes.split(",")] if args.scenes else None
    stats  = run(
        split        = args.split,
        scenes       = scenes,
        max_episodes = args.max_episodes,
        output_root  = pathlib.Path(args.output),
        overwrite    = args.overwrite,
    )
    print(json.dumps(stats, indent=2))

    if _simulation_app is not None:
        _simulation_app.close()
