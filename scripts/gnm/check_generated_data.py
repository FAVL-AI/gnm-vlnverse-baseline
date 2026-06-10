#!/usr/bin/env python3
"""scripts/gnm/check_generated_data.py
Verify generated GNM-format trajectories after Isaac Sim rendering.

Checks:
  1. At least one traj_data.pkl per split
  2. position shape (T, 2), yaw shape (T,) — not scalar, not empty
  3. Matching image count (N images ≈ T frames)
  4. No val/test scan names appear in the train split (leakage guard)
  5. action_std in gnm_base.yaml has been updated from default [1.0, 1.0]

Usage
-----
    python scripts/gnm/check_generated_data.py
    python scripts/gnm/check_generated_data.py --data-root datasets/vlntube
"""
from __future__ import annotations

import argparse
import gzip
import json
import pickle
from pathlib import Path

import numpy as np
import yaml

REPO_ROOT  = Path(__file__).resolve().parents[2]
SPLITS_DIR = REPO_ROOT / "datasets/vlntube/prebuilt_data/raw_data/final_splits"

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
WARN = "\033[33mWARN\033[0m"


def check_split(split_dir: Path, split_name: str) -> tuple[int, int, int]:
    """Return (pass_count, warn_count, fail_count)."""
    passed = warned = failed = 0

    ep_dirs = [d for d in split_dir.iterdir() if d.is_dir()] if split_dir.exists() else []

    if not ep_dirs:
        print(f"  [{FAIL}] {split_name}: no episode directories found in {split_dir}")
        return 0, 0, 1

    print(f"  {split_name}: {len(ep_dirs)} episodes")
    total_frames = 0
    bad_shape = 0
    missing_pkl = 0
    frame_mismatch = 0

    for ep in ep_dirs:
        pkl = ep / "traj_data.pkl"
        if not pkl.exists():
            missing_pkl += 1
            continue
        try:
            data = pickle.load(open(pkl, "rb"))
            pos = np.array(data["position"])
            yaw = np.array(data["yaw"])
            T   = len(pos)

            if pos.ndim != 2 or pos.shape[1] != 2:
                bad_shape += 1
            elif yaw.shape != (T,):
                bad_shape += 1
            else:
                total_frames += T
                # Check image count matches T
                n_imgs = len(list(ep.glob("*.jpg")))
                if abs(n_imgs - T) > 1:
                    frame_mismatch += 1
        except Exception:
            bad_shape += 1

    if missing_pkl:
        print(f"    [{WARN}] {missing_pkl} episodes missing traj_data.pkl")
        warned += 1
    if bad_shape:
        print(f"    [{FAIL}] {bad_shape} episodes have wrong position/yaw shape")
        failed += 1
    else:
        print(f"    [{PASS}] position (T,2) and yaw (T,) shapes correct")
        passed += 1

    if frame_mismatch:
        print(f"    [{WARN}] {frame_mismatch} episodes: image count ≠ trajectory length")
        warned += 1
    else:
        print(f"    [{PASS}] image counts match trajectory lengths")
        passed += 1

    fps_equiv = total_frames / 3600 / 5
    print(f"    Total frames: {total_frames:,}  ({fps_equiv:.1f}h @ 5 Hz)")
    return passed, warned, failed


def check_leakage(train_dir: Path) -> tuple[int, int, int]:
    """Verify no val_unseen/test scan names appear in train output."""
    try:
        val_unseen_scans = set()
        test_scans = set()
        for split_file in ["fine_val_unseen.json.gz", "fine_test.json.gz"]:
            gz = SPLITS_DIR / split_file
            if gz.exists():
                with gzip.open(gz, "rt") as f:
                    eps = json.load(f).get("episodes", [])
                scans = {e.get("scan") for e in eps if e.get("scan")}
                if "unseen" in split_file:
                    val_unseen_scans = scans
                else:
                    test_scans = scans
    except Exception as e:
        print(f"  [{WARN}] Leakage check skipped: {e}")
        return 0, 1, 0

    if not train_dir.exists():
        return 0, 0, 0

    train_ep_ids = {d.name for d in train_dir.iterdir() if d.is_dir()}
    # ep_id format: {scan}_{episode_id}
    train_scans = {ep.split("_")[0] + "_" + ep.split("_")[1]
                   if len(ep.split("_")) > 1 else ep
                   for ep in train_ep_ids}
    # crude: check if any val_unseen scan name is a prefix of any train ep dir
    leaked_val = [ep for ep in train_ep_ids
                  if any(ep.startswith(sc) for sc in val_unseen_scans)]
    leaked_test = [ep for ep in train_ep_ids
                   if any(ep.startswith(sc) for sc in test_scans)]

    if leaked_val or leaked_test:
        print(f"  [{FAIL}] LEAKAGE: val_unseen={len(leaked_val)} test={len(leaked_test)} episodes in train")
        return 0, 0, 1
    print(f"  [{PASS}] No val_unseen or test scans in train split")
    return 1, 0, 0


def check_action_std(cfg_path: Path) -> tuple[int, int, int]:
    if not cfg_path.exists():
        print(f"  [{WARN}] Config not found: {cfg_path}")
        return 0, 1, 0
    cfg = yaml.safe_load(cfg_path.read_text())
    std = cfg.get("data", {}).get("action_std", [1.0, 1.0])
    if std == [1.0, 1.0]:
        print(f"  [{WARN}] action_std is still default [1.0, 1.0] — run 03_compute_action_std.py")
        return 0, 1, 0
    print(f"  [{PASS}] action_std = {std}")
    return 1, 0, 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-root", default="datasets/vlntube",
                        help="Root of generated dataset")
    parser.add_argument("--cfg", default="configs/gnm/gnm_base.yaml",
                        help="Config YAML to check action_std in")
    args = parser.parse_args()

    data_root = REPO_ROOT / args.data_root
    cfg_path  = REPO_ROOT / args.cfg

    total_pass = total_warn = total_fail = 0

    print("\nGenerated data integrity check")
    print("=" * 50)

    for split in ["train", "val", "test"]:
        split_dir = data_root / split
        p, w, f = check_split(split_dir, split)
        total_pass += p; total_warn += w; total_fail += f

    print("\nLeakage check")
    print("-" * 50)
    p, w, f = check_leakage(data_root / "train")
    total_pass += p; total_warn += w; total_fail += f

    print("\nConfig check")
    print("-" * 50)
    p, w, f = check_action_std(cfg_path)
    total_pass += p; total_warn += w; total_fail += f

    print("\n" + "=" * 50)
    print(f"Result: {total_pass} passed  {total_warn} warnings  {total_fail} failed")

    if total_fail:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
