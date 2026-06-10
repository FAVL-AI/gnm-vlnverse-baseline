"""VLNVerse dataset indexer for FleetSafe.

Inspects datasets/vlnverse for downloaded/generated assets and writes
datasets/vlnverse/vlnverse_index.json.

Usage (CLI):
    python -m fleetsafe_vln.benchmark.vlnverse_indexer
    python -m fleetsafe_vln.benchmark.vlnverse_indexer --root datasets/vlnverse
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _rglob_limited(base: Path, pattern: str, limit: int = 500) -> List[Path]:
    if not base.exists():
        return []
    results = []
    for p in base.rglob(pattern):
        results.append(p)
        if len(results) >= limit:
            break
    return results


def inspect_vlnverse_datasets(data_root: Path) -> Dict[str, Any]:
    """Inspect datasets/vlnverse directory structure."""
    scenes_dir    = data_root / "scenes"
    previews_dir  = data_root / "previews"
    metadata_dir  = data_root / "metadata"
    data_dir      = data_root / "data"

    scene_files   = _rglob_limited(scenes_dir, "*")
    preview_imgs  = _rglob_limited(previews_dir, "*.jpg") + _rglob_limited(previews_dir, "*.png")
    meta_files    = _rglob_limited(metadata_dir, "*.json")
    traj_files    = _rglob_limited(data_dir, "*traj*") + _rglob_limited(data_dir, "trajectory*.json")
    instr_files   = (
        _rglob_limited(data_dir, "*instruction*")
        + _rglob_limited(data_dir, "*instruct*")
        + _rglob_limited(metadata_dir, "*instruction*")
    )
    dataset_files = _rglob_limited(data_dir, "*.json") + _rglob_limited(data_dir, "*.jsonl")
    all_images    = _rglob_limited(data_root, "*.jpg") + _rglob_limited(data_root, "*.png")

    # Sample instructions from any JSON files that contain instruction fields
    sample_instructions: List[str] = []
    for jf in (instr_files + meta_files)[:10]:
        try:
            d = json.loads(jf.read_text())
            for field in ("instruction", "instructions", "nl_command", "text"):
                val = d.get(field)
                if isinstance(val, str):
                    sample_instructions.append(val[:200])
                    break
                if isinstance(val, list) and val:
                    sample_instructions.append(str(val[0])[:200])
                    break
        except Exception:
            pass

    # Sample trajectory metadata
    sample_trajs: List[Dict[str, Any]] = []
    for tf in traj_files[:5]:
        try:
            d = json.loads(tf.read_text())
            if isinstance(d, dict):
                sample_trajs.append({
                    "file": str(tf.relative_to(data_root)),
                    "keys": list(d.keys())[:8],
                })
            elif isinstance(d, list):
                sample_trajs.append({
                    "file": str(tf.relative_to(data_root)),
                    "items": len(d),
                })
        except Exception:
            pass

    return {
        "data_root": str(data_root),
        "exists": data_root.exists(),
        "scene_files": len(scene_files),
        "preview_images": len(preview_imgs),
        "preview_paths": [str(p.relative_to(data_root)) for p in preview_imgs[:8]],
        "metadata_files": len(meta_files),
        "trajectory_files": len(traj_files),
        "instruction_files": len(instr_files),
        "dataset_files": len(dataset_files),
        "total_images": len(all_images),
        "sample_instructions": sample_instructions[:5],
        "sample_trajectories": sample_trajs,
    }


def build_index(data_root: Path | None = None) -> Dict[str, Any]:
    data_root = data_root or (_REPO_ROOT / "datasets" / "vlnverse")
    data_info = inspect_vlnverse_datasets(data_root)

    any_data = (
        data_info["scene_files"] > 0
        or data_info["dataset_files"] > 0
        or data_info["preview_images"] > 0
    )

    next_actions: List[str] = []
    if not any_data:
        next_actions += [
            "Run: bash scripts/setup_vlnverse.sh --sample",
            "Or download VLNVerse data manually from https://huggingface.co/datasets/VLN-datasets",
            "Place scene files in datasets/vlnverse/scenes/",
            "Place preview images in datasets/vlnverse/previews/",
            "Place metadata in datasets/vlnverse/metadata/",
        ]
    else:
        next_actions.append("Data present. Refresh: python -m fleetsafe_vln.benchmark.vlnverse_indexer")

    return {
        "indexed_at": datetime.now(timezone.utc).isoformat(),
        "source": "VLNVerse",
        "datasets": data_info,
        "summary": {
            "data_available": any_data,
            "scene_count": data_info["scene_files"],
            "preview_count": data_info["preview_images"],
            "instruction_count": data_info["instruction_files"],
            "trajectory_count": data_info["trajectory_files"],
            "total_images": data_info["total_images"],
        },
        "reference": {
            "project": "VLNVerse",
            "hf_datasets": "https://huggingface.co/datasets",
            "note": (
                "VLNVerse is used as a benchmark/data reference. "
                "FleetSafe extends it with Yahboom M3 Pro, GNM/ViNT/NoMaD, "
                "CBF-QP safety shield, and ROS 2 / Isaac Sim bridge."
            ),
        },
        "next_actions": next_actions,
    }


def write_index(
    data_root: Path | None = None,
    output: Path | None = None,
) -> Path:
    data_root = data_root or (_REPO_ROOT / "datasets" / "vlnverse")
    output = output or (data_root / "vlnverse_index.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    index = build_index(data_root=data_root)
    output.write_text(json.dumps(index, indent=2))
    return output


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Index VLNVerse dataset for FleetSafe")
    p.add_argument("--root", default=None, help="Path to vlnverse datasets dir (default: datasets/vlnverse)")
    p.add_argument("--output", default=None, help="Output JSON path")
    args = p.parse_args()

    out = write_index(
        data_root=Path(args.root) if args.root else None,
        output=Path(args.output) if args.output else None,
    )
    index = json.loads(out.read_text())
    print(f"VLNVerse index written: {out}")
    s = index["summary"]
    print(f"  data_available={s['data_available']}  scenes={s['scene_count']}  "
          f"previews={s['preview_count']}  instructions={s['instruction_count']}  "
          f"trajectories={s['trajectory_count']}")
    if index["next_actions"]:
        print("Next actions:")
        for a in index["next_actions"]:
            print(f"  {a}")
