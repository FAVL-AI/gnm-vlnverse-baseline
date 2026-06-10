#!/usr/bin/env python3
"""scripts/gnm/inspect_trajectory_labels.py
Print the label contents of General Navigation Model trajectory folders.

For each trajectory in the requested split, this script reports:
  - folder path
  - number of Red-Green-Blue (JPG) image frames
  - whether traj_data.pkl exists
  - position array shape (N, 2)
  - yaw array shape (N,)
  - start position [x, y]
  - goal position [x, y]  (last recorded position, or from episode_info.json if present)
  - scene identifier (from folder name or episode_info.json)
  - episode identifier (from folder name or episode_info.json)
  - split name
  - whether instruction.txt exists (language annotation)
  - goal_pos / goal_radius from episode_info.json if present

Usage
─────
  python3 scripts/gnm/inspect_trajectory_labels.py \\
      --data-root datasets/vlntube \\
      --split train \\
      --limit 5

  python3 scripts/gnm/inspect_trajectory_labels.py \\
      --data-root datasets/vlntube \\
      --split val
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]


def inspect_trajectory(folder: Path, split: str) -> None:
    sep = "─" * 60
    print(sep)
    print(f"  Trajectory : {folder.name}")
    print(f"  Path       : {folder}")
    print(f"  Split      : {split}")

    # ── Image frames ─────────────────────────────────────────────────────────
    jpg_files = sorted(folder.glob("*.jpg"), key=lambda p: int(p.stem))
    print(f"  RGB frames : {len(jpg_files)}")

    # ── traj_data.pkl ─────────────────────────────────────────────────────────
    pkl_path = folder / "traj_data.pkl"
    if not pkl_path.exists():
        print("  traj_data  : NOT FOUND")
        return

    print("  traj_data  : EXISTS")
    try:
        data = pickle.load(open(pkl_path, "rb"))
    except Exception as exc:
        print(f"  traj_data  : LOAD ERROR — {exc}")
        return

    if not isinstance(data, dict):
        print(f"  traj_data  : unexpected type {type(data)}")
        return

    pos = data.get("position")
    yaw = data.get("yaw")

    if pos is not None and hasattr(pos, "shape"):
        print(f"  position   : shape {pos.shape}  dtype {pos.dtype}")
        print(f"  start_pos  : {pos[0].tolist()}")
        print(f"  end_pos    : {pos[-1].tolist()}")
        path_len_m = float(np.sum(np.linalg.norm(np.diff(pos, axis=0), axis=1)))
        print(f"  path_len   : {path_len_m:.3f} m")
    else:
        print("  position   : not found")

    if yaw is not None and hasattr(yaw, "shape"):
        print(f"  yaw        : shape {yaw.shape}  range [{yaw.min():.3f}, {yaw.max():.3f}] rad")
    else:
        print("  yaw        : not found")

    # ── episode_info.json ──────────────────────────────────────────────────────
    info_path = folder / "episode_info.json"
    if info_path.exists():
        try:
            info = json.loads(info_path.read_text())
            scan = info.get("scan", "not found")
            ep_id = info.get("episode_id", "not found")
            goal_pos = info.get("goal_pos", "not found")
            goal_radius = info.get("goal_radius", "not found")
            n_steps = info.get("n_steps", "not found")
            print(f"  scene      : {scan}")
            print(f"  episode_id : {ep_id}")
            print(f"  goal_pos   : {goal_pos}")
            print(f"  goal_radius: {goal_radius} m")
            print(f"  n_steps    : {n_steps}")
        except Exception as exc:
            print(f"  episode_info: PARSE ERROR — {exc}")
    else:
        # Fall back to folder-name parsing: scene_XXXX_scene_XXXX_<ep>_<variant>
        parts = folder.name.split("_")
        scene = "_".join(parts[:2]) if len(parts) >= 2 else "not found"
        print(f"  scene      : {scene}  (parsed from folder name)")
        print(f"  episode_id : {folder.name}  (folder name)")
        print(f"  goal_pos   : not found (no episode_info.json)")

    # ── instruction.txt (language annotation) ─────────────────────────────────
    instr_path = folder / "instruction.txt"
    if instr_path.exists():
        instr = instr_path.read_text().strip().replace("\n", " ")
        preview = instr[:100] + ("…" if len(instr) > 100 else "")
        print(f"  instruction: {preview}")
    else:
        print("  instruction: not found")

    # ── action / waypoint targets ──────────────────────────────────────────────
    action_keys = [k for k in data if "action" in k.lower() or "waypoint" in k.lower()]
    if action_keys:
        for k in action_keys:
            v = data[k]
            shp = getattr(v, "shape", None)
            print(f"  {k:<12}: shape {shp}" if shp else f"  {k:<12}: {repr(v)[:60]}")
    else:
        print("  actions    : not found (derived by GNMDataset at training time)")

    # ── distance-to-goal ──────────────────────────────────────────────────────
    dist_keys = [k for k in data if "dist" in k.lower()]
    if dist_keys:
        for k in dist_keys:
            v = data[k]
            shp = getattr(v, "shape", None)
            print(f"  {k:<12}: shape {shp}" if shp else f"  {k:<12}: {repr(v)[:60]}")
    else:
        print("  dist_target: derived at sampling time (goal_idx − obs_idx)")

    # ── collision metadata ─────────────────────────────────────────────────────
    coll_keys = [k for k in data if "coll" in k.lower() or "collision" in k.lower()]
    meta_path  = folder / "metadata.json"
    if coll_keys:
        print(f"  collision  : keys {coll_keys}")
    elif meta_path.exists():
        print(f"  collision  : see {meta_path.name}")
    else:
        print("  collision  : not recorded (offline trajectory data)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--data-root", default="datasets/vlntube",
                        help="Root of the vlntube dataset")
    parser.add_argument("--split", default="train",
                        choices=["train", "val", "test"],
                        help="Which split to inspect")
    parser.add_argument("--limit", default=None, type=int,
                        help="Maximum number of trajectories to print (default: all)")
    parser.add_argument("--scene", default=None,
                        help="Filter by scene identifier, e.g. kujiale_0092")
    args = parser.parse_args()

    data_root = Path(args.data_root)
    if not data_root.is_absolute():
        data_root = REPO_ROOT / data_root

    split_dir = data_root / args.split
    if not split_dir.exists():
        print(f"ERROR: split directory not found: {split_dir}")
        sys.exit(1)

    folders = sorted(p for p in split_dir.iterdir() if p.is_dir())
    if args.scene:
        folders = [f for f in folders if args.scene in f.name]

    total = len(folders)
    if args.limit:
        folders = folders[: args.limit]

    print(f"\nGeneralNavModel trajectory label inspection")
    print(f"Data root : {data_root}")
    print(f"Split     : {args.split}  ({total} trajectories total)")
    if args.scene:
        print(f"Scene filter: {args.scene}")
    print(f"Showing   : {len(folders)}\n")

    for folder in folders:
        inspect_trajectory(folder, args.split)

    print("─" * 60)
    print(f"\nShowed {len(folders)} / {total} trajectories in '{args.split}' split.")


if __name__ == "__main__":
    main()
