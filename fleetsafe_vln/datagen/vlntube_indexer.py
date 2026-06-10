"""VLNTube dataset indexer for FleetSafe.

Inspects external/VLNTube and datasets/vlntube, detects available assets,
and writes datasets/vlntube/vlntube_index.json.

Usage (CLI):
    python -m fleetsafe_vln.datagen.vlntube_indexer
    python -m fleetsafe_vln.datagen.vlntube_indexer --repo external/VLNTube
    python -m fleetsafe_vln.datagen.vlntube_indexer --root datasets/vlntube
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _rglob_limited(base: Path, pattern: str, limit: int = 500) -> List[Path]:
    results = []
    for p in base.rglob(pattern):
        results.append(p)
        if len(results) >= limit:
            break
    return results


def inspect_vlntube_repo(repo_root: Path) -> Dict[str, Any]:
    """Inspect the cloned VLNTube repository."""
    if not repo_root.exists():
        return {
            "available": False,
            "path": str(repo_root),
            "note": "Not cloned. Run: bash scripts/setup_vlntube.sh",
        }

    folders = {
        "scene_graph": (repo_root / "scene_graph").exists(),
        "vistube": (repo_root / "vistube").exists(),
        "instube": (repo_root / "instube").exists(),
        "datatube": (repo_root / "datatube").exists(),
        "splits": (repo_root / "splits").exists(),
    }

    usd_files = _rglob_limited(repo_root, "*.usd") + _rglob_limited(repo_root, "*.usda")
    py_files  = _rglob_limited(repo_root, "*.py", 200)

    return {
        "available": True,
        "path": str(repo_root),
        "folders": folders,
        "usd_scene_count": len(usd_files),
        "usd_scenes": [str(p.relative_to(repo_root)) for p in usd_files[:20]],
        "python_file_count": len(py_files),
        "has_readme": (repo_root / "README.md").exists(),
    }


def inspect_vlntube_datasets(data_root: Path) -> Dict[str, Any]:
    """Inspect datasets/vlntube for generated/downloaded assets.

    Detects: USD scenes, scene graph JSON, room metadata, trajectories (.json/.npy),
    RGB/depth images, instruction JSON, parquet/npy training exports.
    """
    def rglob_multi(base: Path, *patterns: str, limit: int = 200) -> List[Path]:
        if not base.exists():
            return []
        results: List[Path] = []
        for pat in patterns:
            for p in base.rglob(pat):
                if p not in results:
                    results.append(p)
                if len(results) >= limit:
                    return results
        return results

    # USD scene files (real Isaac Sim assets)
    usd_files = rglob_multi(data_root, "*.usd", "*.usda", "*.usdc")

    # Scene graph JSON
    graphs = rglob_multi(data_root / "scene_graph", "*.json") if (data_root / "scene_graph").exists() else []
    # Also search whole tree for scene graph patterns
    if not graphs:
        graphs = rglob_multi(data_root, "*scene_graph*.json", "*scenegraph*.json")

    # Room metadata (from Eyz/SceneMeta / Eyz/SceneSummary)
    meta = rglob_multi(data_root / "room_meta", "*.json", "*.parquet")
    if not meta:
        meta = rglob_multi(data_root, "*scene_meta*.json", "*room_meta*.json", "*summary*.json")

    # RGB image sequences
    rgb_imgs = rglob_multi(data_root, "*.jpg", "*.png", limit=500)

    # Depth images
    depth_imgs = rglob_multi(data_root, "*.npy")  # depth often stored as npy

    # Instruction files
    instr = rglob_multi(data_root,
                        "instruction*.json", "*instructions*.json",
                        "*_instruct*.json", "instruct*.json",
                        "*episode*.json", "*demo*.json")

    # Trajectory files
    trajs = rglob_multi(data_root,
                        "trajectory*.json", "*traj*.json",
                        "path*.json", "*waypoint*.json")
    traj_npy = _rglob_limited(data_root, "*.npy")  # trajectories as npy

    # Training exports (parquet, jsonl, gz)
    exports = rglob_multi(data_root / "outputs", "*.json", "*.jsonl", "*.parquet")
    if not exports:
        exports = rglob_multi(data_root, "*.parquet", "*.jsonl", "*.json.gz", "*.zip")

    # Count RGB sequences (dirs containing images)
    rgb_seq_dirs: List[Path] = []
    for p in rgb_imgs[:200]:
        d = p.parent
        if d not in rgb_seq_dirs:
            rgb_seq_dirs.append(d)

    # Sample instructions text
    sample_instructions: List[str] = []
    for jf in instr[:10]:
        try:
            d = json.loads(jf.read_text())
            for field in ("instruction", "instructions", "nl_command", "text", "description"):
                val = d.get(field)
                if isinstance(val, str):
                    sample_instructions.append(val[:200])
                    break
                if isinstance(val, list) and val:
                    sample_instructions.append(str(val[0])[:200])
                    break
        except Exception:
            pass

    has_real_data = (
        len(usd_files) > 0
        or len(rgb_imgs) > 0
        or len(graphs) > 0
        or len(meta) > 0
        or len(instr) > 0
        or len(exports) > 0  # parquet/jsonl/zip counts as real data
    )

    return {
        "data_root": str(data_root),
        "exists": data_root.exists(),
        "usd_scene_files": len(usd_files),
        "usd_scene_paths": [str(p.relative_to(data_root)) for p in usd_files[:5]],
        "rgb_sequences": len(rgb_seq_dirs),
        "rgb_images": len(rgb_imgs),
        "depth_npy_files": len(depth_imgs),
        "scene_graphs": len(graphs),
        "scene_graph_files": [str(p.relative_to(data_root)) for p in graphs[:5]],
        "room_metadata_files": len(meta),
        "room_meta_paths": [str(p.relative_to(data_root)) for p in meta[:3]],
        "instruction_files": len(instr),
        "sample_instructions": sample_instructions[:5],
        "trajectory_files": len(trajs),
        "trajectory_npy": len(traj_npy),
        "datatube_exports": len(exports),
        "image_samples": len(rgb_imgs),
        "image_sample_paths": [str(p.relative_to(data_root)) for p in rgb_imgs[:6]],
        "has_real_data": has_real_data,
    }


def build_index(
    repo_root: Path | None = None,
    data_root: Path | None = None,
) -> Dict[str, Any]:
    repo_root = repo_root or (_REPO_ROOT / "external" / "VLNTube")
    data_root = data_root or (_REPO_ROOT / "datasets" / "vlntube")

    # Also check legacy third_party location
    legacy = _REPO_ROOT / "third_party" / "VLNTube"
    repo_info = inspect_vlntube_repo(repo_root)
    if not repo_info["available"] and legacy.exists():
        repo_info = inspect_vlntube_repo(legacy)
        repo_info["note"] = f"Found at legacy path {legacy}. Consider: cp -r {legacy} {repo_root}"

    data_info = inspect_vlntube_datasets(data_root)

    next_actions: List[str] = []
    if not repo_info.get("available"):
        next_actions.append("bash scripts/setup_vlntube.sh")
    if data_info["rgb_sequences"] == 0 and data_info["scene_graphs"] == 0:
        next_actions.append("Run VLNTube pipeline to generate scene data (requires Isaac Sim)")
        next_actions.append("Or copy pre-built data into datasets/vlntube/prebuilt_data/")
    if not next_actions:
        next_actions.append("Data looks good. Run: python -m fleetsafe_vln.datagen.vlntube_indexer to refresh.")

    return {
        "indexed_at": datetime.now(timezone.utc).isoformat(),
        "source": "VLNTube",
        "repo": repo_info,
        "datasets": data_info,
        "summary": {
            "repo_available": repo_info.get("available", False),
            "usd_scenes": repo_info.get("usd_scene_count", 0) + data_info.get("usd_scene_files", 0),
            "rgb_sequences": data_info["rgb_sequences"],
            "rgb_images": data_info.get("rgb_images", 0),
            "scene_graphs": data_info["scene_graphs"],
            "room_metadata_files": data_info.get("room_metadata_files", 0),
            "instruction_files": data_info["instruction_files"],
            "trajectory_files": data_info.get("trajectory_files", 0),
            "datatube_exports": data_info["datatube_exports"],
            "image_samples": data_info["image_samples"],
            "has_real_data": data_info.get("has_real_data", False),
        },
        "next_actions": next_actions,
    }


def write_index(
    repo_root: Path | None = None,
    data_root: Path | None = None,
    output: Path | None = None,
) -> Path:
    data_root = data_root or (_REPO_ROOT / "datasets" / "vlntube")
    output = output or (data_root / "vlntube_index.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    index = build_index(repo_root=repo_root, data_root=data_root)
    output.write_text(json.dumps(index, indent=2))
    return output


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Index VLNTube dataset for FleetSafe")
    p.add_argument("--repo", default=None, help="Path to VLNTube repo (default: external/VLNTube)")
    p.add_argument("--root", default=None, help="Path to vlntube datasets dir (default: datasets/vlntube)")
    p.add_argument("--output", default=None, help="Output JSON path")
    args = p.parse_args()

    out = write_index(
        repo_root=Path(args.repo) if args.repo else None,
        data_root=Path(args.root) if args.root else None,
        output=Path(args.output) if args.output else None,
    )
    index = json.loads(out.read_text())
    print(f"VLNTube index written: {out}")
    s = index["summary"]
    print(f"  repo_available={s['repo_available']}  usd={s['usd_scenes']}  "
          f"rgb_seq={s['rgb_sequences']}  graphs={s['scene_graphs']}  "
          f"instr={s['instruction_files']}  exports={s['datatube_exports']}")
    if index["next_actions"]:
        print("Next actions:")
        for a in index["next_actions"]:
            print(f"  {a}")
