"""HuggingFace dataset registry for FleetSafe-VLN.

Provides a curated list of VLN and embodied-AI datasets available on HuggingFace
Hub, with download instructions and local cache detection.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

# HF cache typically lives under ~/.cache/huggingface/hub/
_HF_CACHE = Path.home() / ".cache" / "huggingface" / "hub"

DATASET_REGISTRY: List[Dict[str, Any]] = [
    {
        "id": "R2R",
        "name": "Room-to-Room (R2R)",
        "hf_repo": "waymo/r2r",
        "description": "Room-to-Room VLN — 21,567 navigation instructions across 90 Matterport environments",
        "modalities": ["rgb", "depth", "instruction"],
        "license": "CC-BY-4.0",
        "size_gb": 15.0,
        "fleetsafe_compatible": True,
        "tags": ["vln", "indoor", "matterport"],
    },
    {
        "id": "RxR",
        "name": "Room-Across-Room (RxR)",
        "hf_repo": "google-research-datasets/rxr",
        "description": "Room-Across-Room — multilingual VLN with richer annotations",
        "modalities": ["rgb", "depth", "instruction", "pose"],
        "license": "CC-BY-4.0",
        "size_gb": 40.0,
        "fleetsafe_compatible": True,
        "tags": ["vln", "indoor", "multilingual"],
    },
    {
        "id": "REVERIE",
        "name": "REVERIE",
        "hf_repo": "VLN-BERT/REVERIE",
        "description": "Remote Embodied Visual Referring Expression in Real Indoor Environments",
        "modalities": ["rgb", "instruction", "object_bbox"],
        "license": "MIT",
        "size_gb": 8.0,
        "fleetsafe_compatible": True,
        "tags": ["vln", "indoor", "object_grounding"],
    },
    {
        "id": "CVDN",
        "name": "CVDN",
        "hf_repo": "VLN-datasets/CVDN",
        "description": "Cooperative Vision-and-Dialog Navigation",
        "modalities": ["rgb", "dialog", "instruction"],
        "license": "MIT",
        "size_gb": 5.0,
        "fleetsafe_compatible": False,
        "tags": ["vln", "dialog", "indoor"],
    },
    {
        "id": "GNM-dataset",
        "name": "GNM Dataset",
        "hf_repo": "robodhruv/go-navigate-move",
        "description": "GNM training dataset — 60+ hours of robot navigation across diverse environments",
        "modalities": ["rgb", "odom", "goal_image"],
        "license": "MIT",
        "size_gb": 120.0,
        "fleetsafe_compatible": True,
        "tags": ["gnm", "robot", "outdoor", "indoor"],
    },
    {
        "id": "HM3D-VLN",
        "name": "HM3D-VLN",
        "hf_repo": "aihabitat/hm3d-vln",
        "description": "HM3D Habitat-style VLN with semantic annotations",
        "modalities": ["rgb", "depth", "semantic", "instruction"],
        "license": "Habitat License",
        "size_gb": 200.0,
        "fleetsafe_compatible": True,
        "tags": ["vln", "indoor", "semantic", "habitat"],
    },
]


def list_known_datasets(
    tag: Optional[str] = None,
    fleetsafe_compatible_only: bool = False,
) -> List[Dict[str, Any]]:
    """Return registry entries, optionally filtered."""
    results = DATASET_REGISTRY
    if fleetsafe_compatible_only:
        results = [d for d in results if d.get("fleetsafe_compatible")]
    if tag:
        results = [d for d in results if tag in d.get("tags", [])]
    return results


def print_download_instructions(dataset_id: Optional[str] = None) -> None:
    """Print HuggingFace download instructions for one or all datasets."""
    entries = DATASET_REGISTRY
    if dataset_id:
        entries = [d for d in entries if d["id"] == dataset_id]
        if not entries:
            print(f"Unknown dataset: {dataset_id}")
            return

    for d in entries:
        print(f"\n{'='*60}")
        print(f"Dataset:  {d['id']}")
        print(f"Repo:     {d['hf_repo']}")
        print(f"Size:     ~{d['size_gb']:.0f} GB")
        print(f"License:  {d['license']}")
        print(f"  pip install huggingface-hub")
        print(f"  huggingface-cli download {d['hf_repo']} --repo-type dataset")
        print(f"  # OR in Python:")
        print(f"  from datasets import load_dataset")
        print(f"  ds = load_dataset(\"{d['hf_repo']}\")")


def check_local_cache(
    hf_cache: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """Check which registry datasets appear to be cached locally."""
    cache_root = Path(hf_cache) if hf_cache else _HF_CACHE
    results: Dict[str, Any] = {}
    for d in DATASET_REGISTRY:
        # HF Hub stores datasets as datasets--<org>--<name>
        slug = "datasets--" + d["hf_repo"].replace("/", "--")
        cached = (cache_root / slug).exists()
        results[d["id"]] = {
            "cached": cached,
            "cache_path": str(cache_root / slug) if cached else None,
        }
    return results


def write_registry_report(
    output_path: str | Path,
    hf_cache: Optional[str | Path] = None,
) -> str:
    """Write a JSON registry report to output_path and return the path."""
    cache_status = check_local_cache(hf_cache)
    report = {
        "registry_count": len(DATASET_REGISTRY),
        "datasets": DATASET_REGISTRY,
        "local_cache": cache_status,
        "hf_cache_root": str(Path(hf_cache) if hf_cache else _HF_CACHE),
    }
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    return str(out)
