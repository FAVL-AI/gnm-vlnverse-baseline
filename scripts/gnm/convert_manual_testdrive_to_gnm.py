"""
Convert saved manual test-drive episodes into GNM-compatible dataset format.

Does NOT overwrite or modify datasets/vlntube or the official 238/15 split.

Usage:
  python3 scripts/gnm/convert_manual_testdrive_to_gnm.py \\
      --input  datasets/manual_testdrive_custom_office \\
      --output datasets/manual_gnm_format

Dry-run:
  python3 scripts/gnm/convert_manual_testdrive_to_gnm.py --dry-run
"""

import argparse
import json
import os
import pickle
import sys
from pathlib import Path


PROTECTED_DIRS = ("vlntube", "vlnverse", "visualnav_transformer", "gnm_release")


def dry_run():
    print("=" * 60)
    print("convert_manual_testdrive_to_gnm.py — dry-run")
    print("=" * 60)
    print()
    print("Usage:")
    print("  python3 scripts/gnm/convert_manual_testdrive_to_gnm.py \\")
    print("    --input  datasets/manual_testdrive_custom_office \\")
    print("    --output datasets/manual_gnm_format")
    print()
    print("Output structure (GNM-compatible):")
    print("  datasets/manual_gnm_format/")
    print("    <episode_id>/")
    print("      0.jpg  1.jpg  ...   (renamed from 000000.jpg, 000001.jpg)")
    print("      traj_data.pkl       (position, yaw, actions)")
    print("      metadata.json")
    print()
    print("Protected directories (never written to):")
    for d in PROTECTED_DIRS:
        print(f"  {d}")
    print()
    print("NOTE: manual episodes are NOT mixed into the official 238 train / 15 val split.")
    print("      Official Track A result: SR=20.0%, OSR=46.7%, NE=6.51 m")


def _check_output_safe(output: Path):
    name = output.name.lower()
    for protected in PROTECTED_DIRS:
        if protected in name or protected in str(output).lower():
            print(
                f"[ERROR] Output path {output} looks like a protected dataset directory. "
                f"Refusing to write.",
                file=sys.stderr,
            )
            sys.exit(1)


def convert_episode(episode_dir: Path, output_root: Path) -> Path:
    traj_path = episode_dir / "traj_data.pkl"
    if not traj_path.exists():
        raise FileNotFoundError(f"traj_data.pkl not found in {episode_dir}")

    with open(traj_path, "rb") as f:
        traj = pickle.load(f)

    episode_id = traj.get("episode_id", episode_dir.name)
    out_dir = output_root / episode_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # Rename RGB frames to GNM convention (0.jpg, 1.jpg, ...)
    rgb_src = episode_dir / "rgb"
    if rgb_src.exists():
        frames = sorted(rgb_src.glob("*.jpg"))
        for i, src in enumerate(frames):
            dst = out_dir / f"{i}.jpg"
            if not dst.exists():
                import shutil
                shutil.copy2(src, dst)

    # Write traj_data.pkl with updated rgb_paths
    import numpy as np
    n = len(traj.get("position", []))
    updated_rgb_paths = [str(out_dir / f"{i}.jpg") for i in range(n)]
    out_traj = {
        "position": traj.get("position", np.zeros((n, 2))),
        "yaw": traj.get("yaw", np.zeros(n)),
        "rgb_paths": updated_rgb_paths,
        "actions": traj.get("actions", []),
        "timestamps": traj.get("timestamps", []),
        "scene_id": traj.get("scene_id", "unknown"),
        "episode_id": episode_id,
        "mode": traj.get("mode", "manual_testdrive"),
        "start_pos": traj.get("start_pos"),
        "start_yaw": traj.get("start_yaw", 0.0),
        "n_steps": n,
        "path_length_m": traj.get("path_length_m", 0.0),
    }
    if "goal_pos" in traj:
        out_traj["goal_pos"] = traj["goal_pos"]
        out_traj["goal_yaw"] = traj.get("goal_yaw", 0.0)

    with open(out_dir / "traj_data.pkl", "wb") as f:
        pickle.dump(out_traj, f)

    # Copy / update metadata
    meta_src = episode_dir / "metadata.json"
    meta = {}
    if meta_src.exists():
        with open(meta_src) as f:
            meta = json.load(f)
    meta["converted_from"] = str(episode_dir)
    meta["gnm_format"] = True
    meta["official_benchmark_data"] = False
    with open(out_dir / "metadata.json", "w") as f:
        json.dump(meta, f, indent=2)

    return out_dir


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Source folder of manual episodes")
    parser.add_argument("--output", type=Path, help="Destination GNM-format folder")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        dry_run()
        return

    if not args.input or not args.output:
        parser.print_help()
        sys.exit(1)

    _check_output_safe(args.output)

    if not args.input.exists():
        print(f"[ERROR] Input directory does not exist: {args.input}", file=sys.stderr)
        sys.exit(1)

    # Discover episode sub-directories
    episodes = [p for p in sorted(args.input.iterdir()) if p.is_dir() and (p / "traj_data.pkl").exists()]

    if not episodes:
        print(f"[WARN] No episodes with traj_data.pkl found in {args.input}")
        return

    print(f"Converting {len(episodes)} episode(s) from {args.input} → {args.output}")
    for ep in episodes:
        out = convert_episode(ep, args.output)
        print(f"  {ep.name} → {out}")

    print(f"\nDone. {len(episodes)} episode(s) written to {args.output}")
    print("NOTE: These are manual data-collection episodes, not official benchmark data.")


if __name__ == "__main__":
    main()
