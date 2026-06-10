#!/usr/bin/env python3
"""scripts/gnm/download_vlntube_scenes.py
Download VLNVerse Kujiale USD scene assets from Hugging Face.

Scene assets come from Eyz/VLNVerse_scene (312 GB total).
This script downloads only the scenes you request.

Usage
-----
    # Download specific scenes (recommended — each ~50–200 MB):
    python scripts/gnm/download_vlntube_scenes.py kujiale_0092 kujiale_0203

    # Download the top-N scenes by prebuilt episode count (train split only):
    python scripts/gnm/download_vlntube_scenes.py --top 4

    # List what is currently usable (already downloaded + has split episodes):
    python scripts/gnm/download_vlntube_scenes.py --status

After downloading, verify with:
    python scripts/gnm/check_scene_overlap.py
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT  = Path(__file__).resolve().parents[2]
ENV_DIR    = REPO_ROOT / "datasets/vlntube/envs"
SPLITS_DIR = REPO_ROOT / "datasets/vlntube/prebuilt_data/raw_data/final_splits"
HF_REPO    = "Eyz/VLNVerse_scene"
USD_ROOT   = "start_result_navigation.usd"

TRAIN_SPLITS = ["fine_train", "coarse_train"]


def _train_episode_counts() -> dict[str, int]:
    counts: Counter = Counter()
    for split_name in TRAIN_SPLITS:
        gz = SPLITS_DIR / f"{split_name}.json.gz"
        if not gz.exists():
            continue
        with gzip.open(gz, "rt") as f:
            data = json.load(f)
        for ep in data.get("episodes", []):
            scan = ep.get("scan") or ep.get("scene_id")
            if scan:
                counts[scan] += 1
    return dict(counts)


def _is_downloaded(scene: str) -> bool:
    return (ENV_DIR / scene / USD_ROOT).exists()


def download(scenes: list[str]) -> None:
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("ERROR: huggingface_hub not installed.  Run: pip install huggingface_hub")
        sys.exit(1)

    for scene in scenes:
        if _is_downloaded(scene):
            print(f"  {scene}: already present, skipping")
            continue
        print(f"  {scene}: downloading from {HF_REPO} ...", flush=True)
        snapshot_download(
            repo_id=HF_REPO,
            repo_type="dataset",
            allow_patterns=[f"{scene}/*"],
            local_dir=str(ENV_DIR),
        )
        if _is_downloaded(scene):
            n = sum(1 for _ in (ENV_DIR / scene).rglob("*") if _.is_file())
            print(f"  {scene}: done ({n} files)")
        else:
            print(f"  {scene}: WARNING — download completed but {USD_ROOT} not found")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("scenes", nargs="*",
                        help="Scene names to download (e.g. kujiale_0092)")
    parser.add_argument("--top", type=int, default=0,
                        help="Download top-N scenes by training episode count")
    parser.add_argument("--status", action="store_true",
                        help="Show download status and exit")
    args = parser.parse_args()

    counts = _train_episode_counts()

    if args.status or (not args.scenes and args.top == 0):
        downloaded = [s for s in sorted(counts) if _is_downloaded(s)]
        missing    = [s for s, n in sorted(counts.items(), key=lambda x: -x[1])
                      if not _is_downloaded(s)]
        print(f"Downloaded scenes ({len(downloaded)}):")
        for s in downloaded:
            print(f"  {s:30s}  train_eps={counts[s]}")
        print(f"\nTop missing scenes ({min(10, len(missing))}):")
        for s in missing[:10]:
            print(f"  {s:30s}  train_eps={counts[s]}")
        return

    scenes_to_get: list[str] = list(args.scenes)
    if args.top:
        ranked = sorted(counts.items(), key=lambda x: -x[1])
        scenes_to_get = [s for s, _ in ranked[: args.top]]
        print(f"Top {args.top} scenes by training episodes: {scenes_to_get}")

    if not scenes_to_get:
        parser.print_help()
        sys.exit(1)

    ENV_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {len(scenes_to_get)} scene(s) to {ENV_DIR}")
    download(scenes_to_get)
    print("\nDone.  Verify with: python scripts/gnm/check_scene_overlap.py")


if __name__ == "__main__":
    main()
