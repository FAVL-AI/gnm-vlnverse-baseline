"""Dataset exporters — write FleetSafe-DataForge episodes to standard formats.

Supported formats:
  - fleetsafe_jsonl  — FleetSafe native (trajectory + certificates + instructions)
  - vln_r2r          — R2R-compatible JSON
  - hf_dataset       — Hugging Face datasets-compatible Parquet (if datasets installed)
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class DatasetExporter:
    """Export generated episodes to one or more dataset formats."""

    def __init__(self, output_dir: str | Path):
        self._out = Path(output_dir)
        self._out.mkdir(parents=True, exist_ok=True)

    def export_fleetsafe_jsonl(
        self,
        episodes: List[Dict[str, Any]],
        filename: str = "fleetsafe_episodes.jsonl",
    ) -> Path:
        path = self._out / filename
        with path.open("w", encoding="utf-8") as f:
            for ep in episodes:
                f.write(json.dumps(ep) + "\n")
        print(f"[exporter] fleetsafe_jsonl → {path} ({len(episodes)} episodes)")
        return path

    def export_vln_r2r(
        self,
        episodes: List[Dict[str, Any]],
        split: str = "val_unseen",
        filename: Optional[str] = None,
    ) -> Path:
        r2r_records = []
        for ep in episodes:
            traj = ep.get("trajectory", {})
            r2r_records.append({
                "path_id": ep.get("trajectory_id", ""),
                "scan": ep.get("scene", ""),
                "heading": 0.0,
                "distance": traj.get("path_length_m", 0.0),
                "instructions": ep.get("instructions", []),
                "path": [
                    [s["x"], s["y"], s["yaw"]]
                    for s in traj.get("steps", [])
                ],
            })

        fname = filename or f"fleetsafe_{split}.json"
        path = self._out / fname
        path.write_text(json.dumps(r2r_records, indent=2), encoding="utf-8")
        print(f"[exporter] vln_r2r ({split}) → {path} ({len(r2r_records)} records)")
        return path

    def export_hf_dataset(
        self,
        episodes: List[Dict[str, Any]],
        dataset_name: str = "fleetsafe_vln",
    ) -> Path:
        try:
            import datasets  # type: ignore
        except ImportError:
            raise ImportError("pip install datasets to use HF export")

        rows = []
        for ep in episodes:
            traj = ep.get("trajectory", {})
            rows.append({
                "trajectory_id": ep.get("trajectory_id", ""),
                "scene": ep.get("scene", ""),
                "instruction": (ep.get("instructions") or [""])[0],
                "success": ep.get("success", False),
                "path_length_m": traj.get("path_length_m", 0.0),
                "optimal_path_m": traj.get("optimal_path_m", 0.0),
                "n_steps": len(traj.get("steps", [])),
            })

        ds = datasets.Dataset.from_list(rows)
        path = self._out / dataset_name
        ds.save_to_disk(str(path))
        print(f"[exporter] hf_dataset → {path} ({len(rows)} rows)")
        return path
