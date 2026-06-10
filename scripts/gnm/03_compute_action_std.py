#!/usr/bin/env python3
"""scripts/gnm/03_compute_action_std.py
Step 3 of 7: Compute action normalization statistics from the TRAINING set.

Why do we normalize actions?
─────────────────────────────
GNM outputs (Δx, Δy) in metres in the robot frame.  If one robot walks very
fast (Δx ≈ 1.0 m/step) and another very slow (Δx ≈ 0.05 m/step), the loss
function would weight the fast robot 20× more just because its numbers are
bigger.

Normalization fixes this:
  action_normalized = action_raw / action_std

Now all actions are roughly in [-1, 1], and the MSE loss treats all robots
equally.  At inference, we undo it:
  action_real = action_normalized * action_std

IMPORTANT: Compute action_std from the TRAINING set ONLY.
           Never use val/test data — that would leak information.
           The computed values get written into configs/gnm/gnm_base.yaml.

Usage
─────
    python scripts/gnm/03_compute_action_std.py
    python scripts/gnm/03_compute_action_std.py --data-root datasets/gnm_vlnverse
    python scripts/gnm/03_compute_action_std.py --update-config  # write to yaml
"""
from __future__ import annotations

import argparse
import math
import pickle
import sys
from pathlib import Path

import numpy as np
import yaml


def compute_action_std(train_root: Path) -> tuple[float, float]:
    """Compute per-axis action standard deviation over the training split.

    For each trajectory, for each consecutive frame pair (t, t+1):
        1. Compute world-frame displacement: (dx_w, dy_w) = pos[t+1] - pos[t]
        2. Rotate to robot frame:
             dx_robot =  cos(yaw[t]) * dx_w + sin(yaw[t]) * dy_w
             dy_robot = -sin(yaw[t]) * dx_w + cos(yaw[t]) * dy_w
           (Note: robot forward = +x, left = +y, matching GNM convention)

    Returns (std_x, std_y) — one value per action dimension.
    """
    all_dx: list[float] = []
    all_dy: list[float] = []

    traj_dirs = sorted(d for d in train_root.iterdir() if d.is_dir())
    skipped   = 0

    for tdir in traj_dirs:
        pkl_path = tdir / "traj_data.pkl"
        if not pkl_path.exists():
            skipped += 1
            continue

        try:
            data = pickle.load(open(pkl_path, "rb"))
        except Exception:
            skipped += 1
            continue

        positions = data["position"]  # (T, 2)
        yaws      = data["yaw"]       # (T,)
        T         = len(positions)

        if T < 2:
            continue

        for t in range(T - 1):
            dx_w = float(positions[t + 1][0] - positions[t][0])
            dy_w = float(positions[t + 1][1] - positions[t][1])

            cos_y = math.cos(float(yaws[t]))
            sin_y = math.sin(float(yaws[t]))

            # Robot-frame rotation (world → robot)
            dx_r =  cos_y * dx_w + sin_y * dy_w
            dy_r = -sin_y * dx_w + cos_y * dy_w

            all_dx.append(dx_r)
            all_dy.append(dy_r)

    if not all_dx:
        print(f"  ERROR: No valid trajectories found in {train_root}", file=sys.stderr)
        print("  Make sure you ran 03_convert_data.py first.", file=sys.stderr)
        sys.exit(1)

    std_x = float(np.std(all_dx))
    std_y = float(np.std(all_dy))

    # Guard against zero std (e.g. paths with no lateral movement).
    # If std_y is very small compared to std_x (< 10%), use std_x for y
    # so that lateral normalization doesn't amplify tiny floating-point
    # residuals from curved paths into massive loss values.
    if std_x > 0 and std_y < 0.1 * std_x:
        std_y = std_x
    std_x = max(std_x, 1e-6)
    std_y = max(std_y, 1e-6)

    return std_x, std_y


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--data-root",
        default="datasets/gnm_vlnverse",
        help="Root of converted GNM dataset (must contain a train/ subdir)",
    )
    parser.add_argument(
        "--update-config",
        action="store_true",
        help="Write the computed std values into configs/gnm/gnm_base.yaml",
    )
    parser.add_argument(
        "--config",
        default="configs/gnm/gnm_base.yaml",
        help="Config file to update (only used with --update-config)",
    )
    args = parser.parse_args()

    repo_root  = Path(__file__).resolve().parents[2]
    train_root = repo_root / args.data_root / "train"

    if not train_root.exists():
        print(f"ERROR: training split not found at {train_root}")
        print("Run 02_generate_data.sh or 03_convert_data.py first.")
        sys.exit(1)

    print(f"Scanning {train_root} ...")
    traj_dirs = [d for d in train_root.iterdir() if d.is_dir()]
    print(f"  Found {len(traj_dirs)} trajectory directories")

    std_x, std_y = compute_action_std(train_root)

    print()
    print("─────────────────────────────────────────────────")
    print(" Action Standard Deviation (training split)")
    print("─────────────────────────────────────────────────")
    print(f"  std(Δx_robot) = {std_x:.6f}  m/step")
    print(f"  std(Δy_robot) = {std_y:.6f}  m/step")
    print(f"  action_std    = [{std_x:.4f}, {std_y:.4f}]")
    print()
    print("  Interpretation:")
    print(f"    The typical forward step is ±{std_x:.3f} m")
    print(f"    The typical lateral step is ±{std_y:.3f} m")
    print()

    if args.update_config:
        cfg_path = repo_root / args.config
        if not cfg_path.exists():
            print(f"  ERROR: config not found at {cfg_path}")
            sys.exit(1)

        with open(cfg_path) as f:
            cfg = yaml.safe_load(f)

        old_std = cfg.get("data", {}).get("action_std", [1.0, 1.0])
        cfg["data"]["action_std"] = [round(std_x, 6), round(std_y, 6)]

        with open(cfg_path, "w") as f:
            yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)

        print(f"  Updated {cfg_path}")
        print(f"    action_std: {old_std}  →  [{std_x:.6f}, {std_y:.6f}]")
    else:
        print("  Add to configs/gnm/gnm_base.yaml:")
        print(f"    data:")
        print(f"      action_std: [{std_x:.6f}, {std_y:.6f}]")
        print()
        print("  Or run with --update-config to do this automatically.")


if __name__ == "__main__":
    main()
