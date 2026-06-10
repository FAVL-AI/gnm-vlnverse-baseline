#!/usr/bin/env python3
"""scripts/gnm/check_scene_holdout_split.py
Verify the scene-level holdout split: no train/test scene overlap,
and report trajectory counts per scene.

Usage
─────
  python3 scripts/gnm/check_scene_holdout_split.py \\
      --data-root datasets/vlntube \\
      --split-config configs/gnm/splits/scene_holdout_kujiale_0271.yaml
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from collections import defaultdict

try:
    import yaml
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyyaml", "-q"])
    import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def count_trajectories_by_scene(split_dir: Path) -> dict[str, list[str]]:
    by_scene: dict[str, list[str]] = defaultdict(list)
    if not split_dir.exists():
        return by_scene
    for folder in sorted(split_dir.iterdir()):
        if not folder.is_dir():
            continue
        # folder name pattern: scene_scan_scene_scan_epID_variant
        # scene prefix is the first two underscore-separated tokens
        parts = folder.name.split("_")
        if len(parts) >= 2:
            scene = "_".join(parts[:2])
        else:
            scene = folder.name
        by_scene[scene].append(folder.name)
    return dict(by_scene)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--data-root", default="datasets/vlntube",
                        help="Root of the vlntube dataset")
    parser.add_argument("--split-config",
                        default="configs/gnm/splits/scene_holdout_kujiale_0271.yaml",
                        help="YAML split config with train_scenes and test_scenes")
    args = parser.parse_args()

    data_root = Path(args.data_root)
    if not data_root.is_absolute():
        data_root = REPO_ROOT / data_root

    cfg_path = Path(args.split_config)
    if not cfg_path.is_absolute():
        cfg_path = REPO_ROOT / cfg_path

    if not cfg_path.exists():
        print(f"ERROR: split config not found: {cfg_path}")
        sys.exit(1)

    cfg = yaml.safe_load(cfg_path.read_text())
    split_cfg = cfg.get("split", cfg)

    train_scenes = set(split_cfg["train_scenes"])
    test_scenes  = set(split_cfg["test_scenes"])

    # ── Overlap check ─────────────────────────────────────────────────────────
    overlap = train_scenes & test_scenes
    assert not overlap, f"FAIL: scenes appear in both train and test: {overlap}"

    print("\nScene-level holdout split verification")
    print(f"Config     : {cfg_path}")
    print(f"Data root  : {data_root}")

    # ── Count trajectories ────────────────────────────────────────────────────
    rows = {}
    for split_name in ("train", "val"):
        split_dir = data_root / split_name
        rows[split_name] = count_trajectories_by_scene(split_dir)

    print()
    sep = "─" * 55

    # Train split — filter to train scenes
    train_by_scene  = rows["train"]
    train_total     = sum(len(v) for k, v in train_by_scene.items() if k in train_scenes)
    test_from_train = sum(len(v) for k, v in train_by_scene.items() if k in test_scenes)
    all_train       = sum(len(v) for v in train_by_scene.values())

    print(sep)
    print(f"  {'TRAIN scenes (train/ folder)':<40}")
    print(sep)
    for scene in sorted(train_scenes):
        n = len(train_by_scene.get(scene, []))
        print(f"  {scene:<30}  {n:4d} trajectories")
    print(f"  {'TOTAL (train scenes)':<30}  {train_total:4d} trajectories")

    print()
    print(sep)
    print(f"  {'TEST scenes (currently in train/ folder)':<40}")
    print(sep)
    for scene in sorted(test_scenes):
        n = len(train_by_scene.get(scene, []))
        print(f"  {scene:<30}  {n:4d} trajectories  [held-out for test]")
    print(f"  {'TOTAL (test scenes)':<30}  {test_from_train:4d} trajectories")

    # Val split — informational
    val_by_scene = rows["val"]
    val_total    = sum(len(v) for v in val_by_scene.values())
    print()
    print(sep)
    print(f"  {'val/ split (all scenes)':<40}")
    print(sep)
    for scene in sorted(val_by_scene.keys()):
        n = len(val_by_scene[scene])
        tag = "[test]" if scene in test_scenes else "[train]"
        print(f"  {scene:<30}  {n:4d}  {tag}")
    print(f"  {'TOTAL val':<30}  {val_total:4d}")

    # ── Percentages ───────────────────────────────────────────────────────────
    all_trajs = all_train + val_total
    pct_train = 100.0 * train_total / all_trajs if all_trajs else 0
    pct_test  = 100.0 * test_from_train / all_trajs if all_trajs else 0

    print()
    print(sep)
    print(f"  All trajectories       : {all_trajs}")
    print(f"  Train (3 scenes)       : {train_total}  ({pct_train:.1f}%)")
    print(f"  Scene holdout test     : {test_from_train}  ({pct_test:.1f}%)")
    print(f"  Standard val (15)      : {val_total}")
    print()
    print("  Train / test scenes: NO OVERLAP  ✓")
    print(sep)
    print()
    print("PASS — scene-level holdout split is valid.")


if __name__ == "__main__":
    main()
