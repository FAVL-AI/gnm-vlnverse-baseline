#!/usr/bin/env python3
"""scripts/gnm/check_scene_overlap.py
Report which VLNTube scenes have BOTH a local USD file AND prebuilt split episodes.

A scene is "usable" only when:
  datasets/vlntube/envs/<scan>/<scan>.usd   EXISTS
  AND
  at least one prebuilt split episode references that <scan>

Usage
-----
    python scripts/gnm/check_scene_overlap.py
    python scripts/gnm/check_scene_overlap.py --top 10
    python scripts/gnm/check_scene_overlap.py --splits fine_train fine_val
"""
from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT  = Path(__file__).resolve().parents[2]
ENV_DIR    = REPO_ROOT / "datasets/vlntube/envs"
SPLITS_DIR = REPO_ROOT / "datasets/vlntube/prebuilt_data/raw_data/final_splits"

ALL_SPLITS = [
    "fine_train", "fine_val", "fine_val_unseen",
    "coarse_train", "coarse_val", "coarse_val_unseen",
    "fine_test", "coarse_test",
]

TRAIN_SPLITS = {"fine_train", "coarse_train"}
VAL_SPLITS   = {"fine_val", "coarse_val"}


USD_ROOT_NAME = "start_result_navigation.usd"


def collect_usd_scenes() -> set[str]:
    if not ENV_DIR.exists():
        return set()
    return {
        d.name for d in ENV_DIR.iterdir()
        if d.is_dir() and not d.name.startswith(".")
        and (d / USD_ROOT_NAME).exists()
    }


def load_split_counts(split_names: list[str]) -> dict[str, Counter]:
    counts = {}
    for name in split_names:
        gz = SPLITS_DIR / f"{name}.json.gz"
        if not gz.exists():
            continue
        with gzip.open(gz, "rt") as f:
            data = json.load(f)
        episodes = data.get("episodes", data if isinstance(data, list) else [])
        scans = [
            e.get("scan") or e.get("scene_id") or e.get("scene")
            for e in episodes
        ]
        counts[name] = Counter(s for s in scans if s)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--top", type=int, default=20,
                        help="Number of no-USD scenes to list as download candidates")
    parser.add_argument("--splits", nargs="+", default=ALL_SPLITS,
                        help="Which splits to inspect")
    args = parser.parse_args()

    usd_scenes = collect_usd_scenes()
    split_counts = load_split_counts(args.splits)

    scan_to_splits: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for split_name, counter in split_counts.items():
        for scan, n in counter.items():
            scan_to_splits[scan].append((split_name, n))

    print(f"USD scenes found locally: {len(usd_scenes)}")
    if usd_scenes:
        for s in sorted(usd_scenes):
            print(f"  {s}")
    print()

    print("Episodes per split:")
    for split_name, counter in split_counts.items():
        print(f"  {split_name}: {sum(counter.values())} episodes, {len(counter)} scenes")
    print()

    all_scans = set(scan_to_splits)
    usable = sorted(
        usd_scenes & all_scans,
        key=lambda s: -sum(n for _, n in scan_to_splits[s])
    )

    if usable:
        print(f"USABLE scenes (USD + episodes): {len(usable)}")
        for scan in usable:
            parts = {sp: n for sp, n in scan_to_splits[scan]}
            tr = sum(parts.get(s, 0) for s in TRAIN_SPLITS)
            vl = sum(parts.get(s, 0) for s in VAL_SPLITS)
            total = sum(n for _, n in scan_to_splits[scan])
            print(f"  {scan:30s}  train={tr:4d}  val={vl:3d}  total={total:4d}")
        best = usable[0]
        print(f"\nBEST_SCENE: {best}")
        print(f"Command:    bash scripts/gnm/02_generate_data.sh --generate --scenes {best}")
    else:
        print("NO_OVERLAP_FOUND — no local USD matches any prebuilt split scene.")
        print()
        no_usd = {
            s: sum(n for _, n in v)
            for s, v in scan_to_splits.items()
            if s not in usd_scenes
        }
        top = sorted(no_usd.items(), key=lambda x: -x[1])[: args.top]
        print(f"Top {len(top)} scenes to download (by total prebuilt episodes):")
        print(f"  {'scene':30s}  {'train':>6}  {'val':>5}  {'total':>6}")
        print(f"  {'-'*30}  {'-'*6}  {'-'*5}  {'-'*6}")
        for scan, total in top:
            parts = {sp: n for sp, n in scan_to_splits[scan]}
            tr = sum(parts.get(s, 0) for s in TRAIN_SPLITS)
            vl = sum(parts.get(s, 0) for s in VAL_SPLITS)
            print(f"  {scan:30s}  {tr:6d}  {vl:5d}  {total:6d}")
        print()
        print("After downloading a scene ZIP:")
        print("  unzip kujiale_XXXX.zip -d datasets/vlntube/envs/")
        print("  python scripts/gnm/check_scene_overlap.py   # recheck")


if __name__ == "__main__":
    main()
