#!/usr/bin/env python3
"""scripts/gnm/03_convert_data.py
Step 3a of 7: Convert raw VLNTube/IAmGoodNavigator episodes to GNM format.

This script is the bridge between raw Isaac Sim recordings and the GNM
training dataset.  It calls VLNTubeConverter from gnm_vlnverse/data/.

Pipeline
─────────
  Raw Isaac Sim episode               GNM training format
  ─────────────────────               ───────────────────
  episode_meta.json          →        traj_data.pkl
  *.jpg frames               →        0.jpg, 1.jpg, 2.jpg, ...
  IAmGoodNavigator *.csv     →        traj_data.pkl
                                      sensor_config.json
                                      collision_log.json
                                      source_episode.json

Validation checks run on every episode:
  - Minimum 10 frames
  - Max 10% missing frames
  - Yaw values in radians (not degrees)
  - No pose jumps > 3 m (split into sub-trajectories if found)

Output structure
─────────────────
  datasets/gnm_vlnverse/
    train/
      scene_001_ep_00042/
        0.jpg  1.jpg  ...  traj_data.pkl  sensor_config.json ...
    val/
      ...
    test/
      ...
    conversion_stats.json    ← summary of how many were converted

Usage
─────
    python scripts/gnm/03_convert_data.py
    python scripts/gnm/03_convert_data.py --input datasets/vlntube --output datasets/gnm_vlnverse
    python scripts/gnm/03_convert_data.py --overwrite     # reconvert existing
    python scripts/gnm/03_convert_data.py --smoke-test    # first 20 only
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--input",
        default="datasets/vlntube",
        help="Root of raw VLNTube episodes",
    )
    parser.add_argument(
        "--output",
        default="datasets/gnm_vlnverse",
        help="Root of converted GNM dataset",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Reconvert episodes that already exist",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Convert at most 20 episodes (for quick validation)",
    )
    parser.add_argument(
        "--splits",
        default="train:0.8,val:0.1,test:0.1",
        help="Split ratios — must sum to 1.0",
    )
    args = parser.parse_args()

    repo_root  = Path(__file__).resolve().parents[2]
    input_root = repo_root / args.input
    output_root = repo_root / args.output

    if not input_root.exists():
        print(f"ERROR: input directory not found: {input_root}")
        print("Run scripts/gnm/02_generate_data.sh first.")
        sys.exit(1)

    # Parse splits
    split_map: dict[str, float] = {}
    for item in args.splits.split(","):
        name, ratio = item.strip().split(":")
        split_map[name] = float(ratio)
    total = sum(split_map.values())
    if abs(total - 1.0) > 0.01:
        print(f"ERROR: split ratios must sum to 1.0, got {total}")
        sys.exit(1)

    print()
    print("════════════════════════════════════════════════")
    print(" FleetSafe GNM-VLNVerse — Data Conversion")
    print("════════════════════════════════════════════════")
    print(f" Input:  {input_root}")
    print(f" Output: {output_root}")
    print(f" Splits: {split_map}")
    print(f" Smoke:  {args.smoke_test}")
    print()

    sys.path.insert(0, str(repo_root))
    from gnm_vlnverse.data.vlntube_converter import VLNTubeConverter

    converter = VLNTubeConverter(
        input_root=input_root,
        output_root=output_root,
        split_ratios=split_map,
        image_size=(96, 96),
        min_length=10,
        max_jump_m=3.0,
        max_missing_frac=0.1,
    )

    t0    = time.perf_counter()
    stats = converter.convert_all(
        overwrite=args.overwrite,
        max_episodes=20 if args.smoke_test else None,
    )
    elapsed = time.perf_counter() - t0

    print()
    print("── Conversion Results ───────────────────────────────────────────────")
    print(f"  Total episodes found:    {stats.total_episodes}")
    print(f"  Successfully converted:  {stats.converted}")
    print(f"  Rejected (failed check): {stats.rejected}")
    print(f"  Split into sub-segs:     {stats.split_episodes}")
    print(f"  Total frames written:    {stats.total_frames}")
    print(f"  Missing frames skipped:  {stats.missing_frames}")
    print(f"  Time elapsed:            {elapsed:.1f}s")
    print()

    stats_path = output_root / "conversion_stats.json"
    with open(stats_path, "w") as f:
        json.dump(
            {
                "total_episodes":  stats.total_episodes,
                "converted":       stats.converted,
                "rejected":        stats.rejected,
                "split_episodes":  stats.split_episodes,
                "total_frames":    stats.total_frames,
                "missing_frames":  stats.missing_frames,
                "elapsed_s":       round(elapsed, 2),
            },
            f,
            indent=2,
        )
    print(f"  Stats saved to {stats_path}")

    if stats.converted == 0:
        print()
        print("  WARNING: No episodes were converted.")
        print("  Check that input_root contains valid VLNTube episodes.")
        sys.exit(1)

    print()
    print(" Next step:")
    print("   python scripts/gnm/03_compute_action_std.py --update-config")
    print()


if __name__ == "__main__":
    main()
