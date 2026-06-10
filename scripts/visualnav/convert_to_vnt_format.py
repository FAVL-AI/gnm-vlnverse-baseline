#!/usr/bin/env python3
"""
convert_to_vnt_format.py — Convert FleetSafe episodes to visualnav-transformer format.

GNM training expects:
    dataset_root/
        train/
            traj_0000/
                0.jpg  1.jpg  ...  N.jpg   (85×64 RGB)
                traj_data.pkl              {"position": (T,2), "yaw": (T,)}
        test/
            ...
        data_config.yaml

Each trajectory is a continuous navigation episode.  This script converts
FleetSafe episode folders into that structure so the official GNM/ViNT
`train.py` can be used for fine-tuning from the official checkpoint.

GNM data_config.yaml fields (from official gnm.yaml):
    dataset_name:       yahboom_hospital
    data_folder:        <path>
    train:              train
    test:               test
    end_slack:          3
    goals_per_obs:      1
    negative_mining:    true
    metric_waypoint_spacing: 0.25  (metres between waypoints, from odometry)

Usage
-----
    # Convert all FleetSafe episodes (hospital_corridor, gnm model):
    python scripts/visualnav/convert_to_vnt_format.py \\
        --input  data/training_episodes/gnm/hospital_corridor \\
        --output data/gnm_hospital_dataset \\
        --eval-fraction 0.1

    # Also include cluttered_navigation episodes:
    python scripts/visualnav/convert_to_vnt_format.py \\
        --input  data/training_episodes/gnm \\
        --output data/gnm_hospital_dataset \\
        --recursive \\
        --eval-fraction 0.1

    # Then fine-tune from official checkpoint:
    cd third_party/visualnav-transformer/train
    python train.py \\
        --config vint_train/config/gnm.yaml \\
        --data-folder ../../data/gnm_hospital_dataset \\
        --eval-fraction 0.1
"""
from __future__ import annotations

import argparse
import csv
import json
import pickle
import random
import shutil
import sys
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

_GNM_IMG_SIZE = (85, 64)   # width, height — from gnm.yaml image_size: [85, 64]


# ── Single episode converter ──────────────────────────────────────────────────

def convert_episode(
    episode_dir: Path,
    traj_out_dir: Path,
    img_size: tuple[int, int] = _GNM_IMG_SIZE,
) -> Optional[dict]:
    """
    Convert one FleetSafe episode to a GNM-format trajectory folder.

    Returns a summary dict or None if conversion failed.
    """
    img_dir = episode_dir / "images"
    traj_csv = episode_dir / "trajectory.csv"

    if not img_dir.exists() or not traj_csv.exists():
        return None

    frames = sorted(img_dir.glob("step_*.jpg"))
    if not frames:
        return None

    # Read trajectory CSV: step,x,y,yaw,dist_to_goal,min_obs_dist
    positions = []
    yaws      = []
    with open(traj_csv) as f:
        reader = csv.DictReader(f)
        for row in reader:
            positions.append([float(row["x"]), float(row["y"])])
            yaws.append(float(row["yaw"]))

    T = min(len(frames), len(positions))
    if T < 5:
        return None

    traj_out_dir.mkdir(parents=True, exist_ok=True)
    W, H = img_size

    # Copy and resize images: 0.jpg, 1.jpg, ...
    for i, frame in enumerate(frames[:T]):
        img = Image.open(frame).convert("RGB")
        img = img.resize((W, H), Image.BILINEAR)
        img.save(traj_out_dir / f"{i}.jpg")

    # Save traj_data.pkl
    traj_data = {
        "position": np.array(positions[:T], dtype=np.float32),
        "yaw":      np.array(yaws[:T],      dtype=np.float32),
    }
    with open(traj_out_dir / "traj_data.pkl", "wb") as f:
        pickle.dump(traj_data, f)

    # Compute path length
    pos_arr = traj_data["position"]
    diffs   = np.linalg.norm(np.diff(pos_arr, axis=0), axis=1)
    path_m  = float(diffs.sum())

    return {
        "episode":    episode_dir.name,
        "T":          T,
        "path_m":     round(path_m, 3),
        "traj_dir":   str(traj_out_dir),
    }


# ── Batch converter ───────────────────────────────────────────────────────────

def find_episodes(input_dir: Path, recursive: bool = False) -> list[Path]:
    """Find all FleetSafe episode directories under input_dir."""
    if recursive:
        # Look for any directory containing images/ + trajectory.csv
        episodes = []
        for d in sorted(input_dir.rglob("trajectory.csv")):
            ep_dir = d.parent
            if (ep_dir / "images").exists():
                episodes.append(ep_dir)
        return episodes
    else:
        # Direct children that look like ep_NNNN
        return sorted(
            d for d in input_dir.iterdir()
            if d.is_dir() and (d / "trajectory.csv").exists() and (d / "images").exists()
        )


def convert_dataset(
    input_dir:     Path,
    output_dir:    Path,
    eval_fraction: float = 0.1,
    recursive:     bool  = False,
    seed:          int   = 42,
) -> dict:
    """
    Convert all episodes in input_dir to GNM format.

    Splits into train/test based on eval_fraction.
    Writes data_config.yaml for use with the official train.py.
    """
    episodes = find_episodes(input_dir, recursive=recursive)
    if not episodes:
        raise ValueError(f"No FleetSafe episodes found in {input_dir}")

    print(f"  Found {len(episodes)} episodes in {input_dir}")

    # Train/test split
    rng = random.Random(seed)
    shuffled = episodes[:]
    rng.shuffle(shuffled)
    n_test  = max(1, int(len(shuffled) * eval_fraction))
    n_train = len(shuffled) - n_test
    train_eps = shuffled[:n_train]
    test_eps  = shuffled[n_train:]
    print(f"  Split: {n_train} train, {n_test} test")

    output_dir.mkdir(parents=True, exist_ok=True)
    summaries = {"train": [], "test": []}
    failed    = []

    for split_name, split_eps in [("train", train_eps), ("test", test_eps)]:
        split_dir = output_dir / split_name
        split_dir.mkdir(exist_ok=True)
        print(f"\n  Converting {split_name} ({len(split_eps)} episodes)…")
        for ep_dir in split_eps:
            traj_name = ep_dir.name
            traj_out  = split_dir / traj_name
            result    = convert_episode(ep_dir, traj_out)
            if result is None:
                failed.append(str(ep_dir))
                print(f"    SKIP {ep_dir.name} (incomplete)")
            else:
                summaries[split_name].append(result)
                print(f"    {ep_dir.name}  T={result['T']}  path={result['path_m']:.2f}m")

    # Write traj_names.txt split files (required by official train.py)
    # Path: data_splits/<dataset_name>/train/traj_names.txt
    dataset_name = input_dir.name
    for split_name, split_summary in summaries.items():
        split_txt_dir = output_dir / "data_splits" / dataset_name / split_name
        split_txt_dir.mkdir(parents=True, exist_ok=True)
        traj_names = [s["episode"] for s in split_summary]
        with open(split_txt_dir / "traj_names.txt", "w") as f:
            f.write("\n".join(traj_names) + "\n")

    # Write data_config.yaml for official train.py
    data_config  = {
        "dataset_name":             dataset_name,
        "data_folder":              str(output_dir.resolve()),
        "train":                    f"data_splits/{dataset_name}/train",
        "test":                     f"data_splits/{dataset_name}/test",
        "end_slack":                3,
        "goals_per_obs":            1,
        "negative_mining":          True,
        "metric_waypoint_spacing":  0.25,
    }
    config_path = output_dir / "data_config.yaml"
    import yaml  # type: ignore
    with open(config_path, "w") as f:
        yaml.safe_dump(data_config, f, default_flow_style=False)

    # Write conversion summary
    summary = {
        "input_dir":     str(input_dir),
        "output_dir":    str(output_dir),
        "dataset_name":  dataset_name,
        "n_train":       len(summaries["train"]),
        "n_test":        len(summaries["test"]),
        "n_failed":      len(failed),
        "eval_fraction": eval_fraction,
        "image_size":    list(_GNM_IMG_SIZE),
        "data_config":   data_config,
        "train":         summaries["train"],
        "test":          summaries["test"],
        "failed":        failed,
    }
    with open(output_dir / "conversion_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    return summary


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--input",  type=Path, required=True,
                   help="FleetSafe episode root directory")
    p.add_argument("--output", type=Path, required=True,
                   help="Output GNM dataset directory")
    p.add_argument("--eval-fraction", type=float, default=0.1,
                   help="Fraction of episodes for evaluation (default: 0.1)")
    p.add_argument("--recursive", action="store_true",
                   help="Recursively search for episodes under --input")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    print()
    print("=" * 65)
    print("  FleetSafe → visualnav-transformer Dataset Converter")
    print("=" * 65)
    print(f"  Input  : {args.input}")
    print(f"  Output : {args.output}")
    print(f"  Split  : {(1-args.eval_fraction)*100:.0f}% train / {args.eval_fraction*100:.0f}% test")
    print()

    try:
        summary = convert_dataset(
            input_dir     = args.input.resolve(),
            output_dir    = args.output.resolve(),
            eval_fraction = args.eval_fraction,
            recursive     = args.recursive,
            seed          = args.seed,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1

    print()
    print("=" * 65)
    print(f"  Conversion complete!")
    print(f"  Train trajectories : {summary['n_train']}")
    print(f"  Test  trajectories : {summary['n_test']}")
    print(f"  Failed             : {summary['n_failed']}")
    print()
    print("  To fine-tune GNM from official checkpoint:")
    print(f"    cd third_party/visualnav-transformer/train")
    print(f"    python train.py \\")
    print(f"        --config vint_train/config/gnm.yaml \\")
    print(f"        --data-folder {args.output.resolve()} \\")
    print(f"        --eval-fraction {args.eval_fraction}")
    print()
    return 0


if __name__ == "__main__":
    # Inline YAML fallback if PyYAML not installed
    try:
        import yaml  # noqa: F401
    except ImportError:
        class _YamlShim:
            @staticmethod
            def safe_dump(data: dict, stream, **_):
                for k, v in data.items():
                    stream.write(f"{k}: {v!r}\n")
        sys.modules["yaml"] = _YamlShim()  # type: ignore

    sys.exit(main())
