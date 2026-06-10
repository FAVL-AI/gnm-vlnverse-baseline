#!/usr/bin/env python3
"""scripts/gnm/package_dataset_sample.py
Create a small, shareable General Navigation Model dataset sample for reviewers.

Selects one trajectory per available scene from the requested split, then
packages image frames, traj_data.pkl, episode_info.json, instruction.txt,
and a generated README into a compressed tarball.

The tarball is NOT committed to git (add artifacts/*.tar.gz to .gitignore).
Only this script is committed.

Usage
─────
  python3 scripts/gnm/package_dataset_sample.py \\
      --data-root datasets/vlntube \\
      --output artifacts/gnm_vlnverse_sample_dataset.tar.gz \\
      --per-scene 1

  python3 scripts/gnm/package_dataset_sample.py \\
      --data-root datasets/vlntube \\
      --output artifacts/gnm_vlnverse_sample_dataset.tar.gz \\
      --per-scene 2 \\
      --split train
"""
from __future__ import annotations

import argparse
import io
import json
import pickle
import sys
import tarfile
import textwrap
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]


def select_trajectories(split_dir: Path, per_scene: int) -> list[Path]:
    by_scene: dict[str, list[Path]] = defaultdict(list)
    for folder in sorted(split_dir.iterdir()):
        if not folder.is_dir():
            continue
        parts = folder.name.split("_")
        scene = "_".join(parts[:2]) if len(parts) >= 2 else folder.name
        by_scene[scene].append(folder)
    selected: list[Path] = []
    for scene in sorted(by_scene):
        selected.extend(by_scene[scene][:per_scene])
    return selected


def build_readme(trajectories: list[Path], split: str) -> str:
    scene_list = sorted({("_".join(t.name.split("_")[:2])) for t in trajectories})
    lines = [
        "# General Navigation Model — VLNVerse Sample Dataset",
        "",
        "This package contains a small sample of the training data used to train",
        "the General Navigation Model (GNM) baseline for the FleetSafe-VisualNav-Benchmark.",
        "",
        "## Contents",
        "",
        f"Split     : {split}",
        f"Scenes    : {', '.join(scene_list)}",
        f"Trajectories: {len(trajectories)}  (one per scene for brevity)",
        "",
        "Each trajectory folder contains:",
        "",
        "  0.jpg, 1.jpg, …   — Red-Green-Blue (RGB) camera frames (96×96 or full resolution).",
        "                       Recorded from NVIDIA Isaac Sim inside the VLNVerse scene.",
        "",
        "  traj_data.pkl      — Python pickle (NumPy arrays).",
        "                       Keys:",
        "                         position  (N, 2) float32 — floor-plane x,y in metres",
        "                         yaw       (N,)   float32 — robot heading in radians",
        "",
        "  episode_info.json  — Episode metadata.",
        "                       Keys:",
        "                         scan         — scene identifier (e.g. kujiale_0092)",
        "                         episode_id   — unique episode string",
        "                         goal_pos     — [x, y] goal position in metres",
        "                         goal_radius  — success threshold in metres (3.0)",
        "                         n_steps      — number of recorded frames",
        "",
        "  instruction.txt    — Natural-language instruction for the episode (Track B future use).",
        "                       For Track A (visual-goal navigation) this is not used by the model.",
        "",
        "## How labels are created",
        "",
        "Labels are generated AUTOMATICALLY from the NVIDIA Isaac Sim simulator.",
        "No manual annotation is required.",
        "",
        "The robot follows a predefined expert trajectory from the VLNVerse episode.",
        "At each step, Isaac Sim records the RGB camera frame, robot position, and yaw.",
        "Action targets (local waypoints) are derived at training time from consecutive",
        "positions in the trajectory.  Distance-to-goal targets are derived from the",
        "index offset between the current observation and the sampled goal frame.",
        "",
        "## Reproduction",
        "",
        "To regenerate the full dataset (238 train + 15 val trajectories), run:",
        "",
        "  conda run -n isaac python scripts/gnm/04_generate_data.py",
        "",
        "## Full dataset",
        "",
        "The full dataset (~12,659 frames) is not included here because the image",
        "frames make it large.  Contact the author for a full download link.",
        "",
        "## Scene sources",
        "",
        "Scenes are from VLNVerse (https://sihaoevery.github.io/vlnverse/).",
        "Scene assets: https://huggingface.co/datasets/Eyz/VLNVerse_scene",
        "Only the four required scenes were downloaded: kujiale_0092, kujiale_0203,",
        "kujiale_0118, kujiale_0271.",
        "",
        "## Citation",
        "",
        "If you use this dataset, please cite the VLNVerse paper and the",
        "FleetSafe-VisualNav-Benchmark.",
        "",
    ]
    return "\n".join(lines)


def add_trajectory_to_tar(tf: tarfile.TarFile, folder: Path, archive_prefix: str) -> int:
    files_added = 0
    for f in sorted(folder.iterdir()):
        if f.is_file():
            tf.add(f, arcname=f"{archive_prefix}/{folder.name}/{f.name}")
            files_added += 1
    return files_added


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--data-root", default="datasets/vlntube")
    parser.add_argument("--output",    default="artifacts/gnm_vlnverse_sample_dataset.tar.gz")
    parser.add_argument("--per-scene", default=1, type=int,
                        help="Trajectories to include per scene")
    parser.add_argument("--split",     default="train",
                        choices=["train", "val"])
    args = parser.parse_args()

    data_root = Path(args.data_root)
    if not data_root.is_absolute():
        data_root = REPO_ROOT / data_root

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = REPO_ROOT / output_path

    split_dir = data_root / args.split
    if not split_dir.exists():
        print(f"ERROR: split directory not found: {split_dir}")
        sys.exit(1)

    trajectories = select_trajectories(split_dir, args.per_scene)
    if not trajectories:
        print("ERROR: no trajectories found")
        sys.exit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"\nPackaging {len(trajectories)} trajectories into {output_path.name}")

    with tarfile.open(output_path, "w:gz") as tf:
        prefix = "gnm_vlnverse_sample"

        # README
        readme_text = build_readme(trajectories, args.split)
        readme_bytes = readme_text.encode()
        info = tarfile.TarInfo(name=f"{prefix}/README.md")
        info.size = len(readme_bytes)
        tf.addfile(info, io.BytesIO(readme_bytes))

        total_files = 0
        for folder in trajectories:
            n = add_trajectory_to_tar(tf, folder, prefix)
            scene = "_".join(folder.name.split("_")[:2])
            print(f"  + {folder.name:<50}  ({n} files)  [{scene}]")
            total_files += n

    size_mb = output_path.stat().st_size / 1024 / 1024
    print(f"\nCreated : {output_path}")
    print(f"Size    : {size_mb:.1f} MB")
    print(f"Files   : {total_files} trajectory files + README")
    print()
    print("NOTE: The tarball is gitignored (artifacts/*.tar.gz).")
    print("      Commit only this script, not the generated archive.")


if __name__ == "__main__":
    main()
