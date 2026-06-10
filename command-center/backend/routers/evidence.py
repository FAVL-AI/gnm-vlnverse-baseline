"""
Evidence Ledger & Dataset Provenance router — v0.8.

  GET  /api/evidence/ledger           — paginated ledger entries
  POST /api/evidence/record           — manually record an entry
  GET  /api/evidence/stats            — entry counts by scope/source
  GET  /api/evidence/manifest         — dataset manifest (cached)
  POST /api/evidence/manifest/rebuild — force rebuild manifest
  GET  /api/evidence/training         — PPO + W&B + HF status
  GET  /api/evidence/ros2             — DDS / ROS2 graph status
  GET  /api/evidence/timeline         — chronological event list
  GET  /api/evidence/heatmap          — collision / intervention heatmap data
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from ..services.evidence_ledger import evidence_ledger, sha256_file
from ..services.dataset_manifest import build_manifest, load_manifest
from ..services.hf_connector import get_hf_status
from ..services.wandb_connector import get_wandb_status
from ..services.ppo_status import get_ppo_status
from ..services.ros2_status import get_ros2_status
from ..config import settings

router = APIRouter(prefix="/api/evidence", tags=["evidence"])

RESULTS_DIR    = settings.repo_root / "benchmarks" / "visualnav" / "results"
RECORDINGS_DIR = settings.repo_root / "command-center" / "recordings"
AUDIT_PATH     = RECORDINGS_DIR / "audit.jsonl"


# ── Ledger ────────────────────────────────────────────────────────────────────

@router.get("/ledger")
async def get_ledger(
    source: str | None = None,
    claim_scope: str | None = None,
    n: int = 200,
) -> list[dict]:
    return evidence_ledger.query(source=source, claim_scope=claim_scope, n=n)


class RecordBody(BaseModel):
    claim_scope: str
    source: str
    ground_truth_type: str
    description: str
    artifact_path: str | None = None
    robot_id: str | None = None
    operator: str = "operator"
    metadata: dict = {}


@router.post("/record")
async def record_entry(body: RecordBody) -> dict:
    path = Path(body.artifact_path) if body.artifact_path else None
    return evidence_ledger.record(
        claim_scope=body.claim_scope,        # type: ignore[arg-type]
        source=body.source,                  # type: ignore[arg-type]
        ground_truth_type=body.ground_truth_type,  # type: ignore[arg-type]
        description=body.description,
        artifact_path=path,
        robot_id=body.robot_id,
        operator=body.operator,
        metadata=body.metadata,
    )


@router.get("/stats")
async def get_stats() -> dict:
    return evidence_ledger.get_stats()


# ── Manifest ──────────────────────────────────────────────────────────────────

@router.get("/manifest")
async def get_manifest() -> dict:
    m = load_manifest()
    if m is None:
        m = build_manifest()
    return m


@router.post("/manifest/rebuild")
async def rebuild_manifest() -> dict:
    return build_manifest()


# ── Training status ───────────────────────────────────────────────────────────

@router.get("/training")
async def get_training_status() -> dict:
    return {
        "ppo": get_ppo_status(),
        "wandb": get_wandb_status(),
        "huggingface": get_hf_status(),
    }


# ── ROS2 status ───────────────────────────────────────────────────────────────

@router.get("/ros2")
async def get_ros2() -> dict:
    return get_ros2_status()


# ── Timeline ──────────────────────────────────────────────────────────────────

@router.get("/timeline")
async def get_timeline(n: int = 200) -> list[dict]:
    """Chronological events from ledger + audit + benchmark runs."""
    events: list[dict] = []

    # Evidence ledger entries
    for e in evidence_ledger.query(n=n):
        events.append({
            "ts": e["timestamp"],
            "type": "evidence",
            "scope": e.get("claim_scope"),
            "source": e.get("source"),
            "description": e.get("description", ""),
            "sha256": e.get("sha256"),
        })

    # Audit log entries
    if AUDIT_PATH.exists():
        for line in AUDIT_PATH.read_text().splitlines()[-100:]:
            try:
                e = json.loads(line)
                events.append({
                    "ts": e.get("ts", 0),
                    "type": "audit",
                    "scope": "dashboard_audit",
                    "source": "dashboard",
                    "description": f"{e.get('op', '?')}: {e.get('result', '')[:60]}",
                    "dry_run": e.get("dry_run"),
                })
            except Exception:
                pass

    # Benchmark run directories (use mtime as timestamp)
    if RESULTS_DIR.exists():
        for d in RESULTS_DIR.iterdir():
            if not d.is_dir():
                continue
            m = d / "aggregate_metrics.json"
            if not m.exists():
                continue
            try:
                data = json.loads(m.read_text())
                events.append({
                    "ts": m.stat().st_mtime,
                    "type": "benchmark_run",
                    "scope": "sim_benchmark_result",
                    "source": data.get("backend", "mujoco"),
                    "description": f"{data.get('model','?')} {data.get('backend','?')} "
                                   f"fs={data.get('fleetsafe',False)} "
                                   f"sr={data.get('success_rate',0):.2f}",
                    "run_id": d.name,
                })
            except Exception:
                pass

    events.sort(key=lambda x: x.get("ts", 0), reverse=True)
    return events[:n]


# ── Heatmap ───────────────────────────────────────────────────────────────────

@router.get("/heatmap")
async def get_heatmap() -> dict:
    """
    Aggregate collision/intervention positions from all simulation runs.
    Returns grid cells with counts for rendering as SVG overlay.
    """
    cells: dict[str, dict] = {}  # "x,y" -> {collisions, interventions, path_density}

    if not RESULTS_DIR.exists():
        return {"cells": [], "bounds": None, "warning": "No results directory found"}

    for d in RESULTS_DIR.iterdir():
        if not d.is_dir():
            continue
        events_file = d / "safety_events.jsonl"
        traj_file   = d / "trajectory.csv"

        if events_file.exists():
            for line in events_file.read_text().splitlines():
                try:
                    ev = json.loads(line)
                    x = round(ev.get("x", 0), 0)
                    y = round(ev.get("y", 0), 0)
                    key = f"{int(x)},{int(y)}"
                    cell = cells.setdefault(key, {"x": int(x), "y": int(y), "collisions": 0, "interventions": 0, "path_count": 0})
                    if ev.get("event_type") in ("collision", "near_miss"):
                        cell["collisions"] += 1
                    elif ev.get("event_type") == "intervention":
                        cell["interventions"] += 1
                except Exception:
                    pass

        if traj_file.exists():
            for line in traj_file.read_text().splitlines()[1:]:  # skip header
                try:
                    parts = line.split(",")
                    if len(parts) >= 3:
                        x = round(float(parts[1]), 0)
                        y = round(float(parts[2]), 0)
                        key = f"{int(x)},{int(y)}"
                        cell = cells.setdefault(key, {"x": int(x), "y": int(y), "collisions": 0, "interventions": 0, "path_count": 0})
                        cell["path_count"] += 1
                except Exception:
                    pass

    cell_list = list(cells.values())
    if not cell_list:
        return {"cells": [], "bounds": None, "warning": "No trajectory or event data found in results"}

    xs = [c["x"] for c in cell_list]
    ys = [c["y"] for c in cell_list]
    return {
        "cells": cell_list,
        "bounds": {"x_min": min(xs), "x_max": max(xs), "y_min": min(ys), "y_max": max(ys)},
        "total_collisions": sum(c["collisions"] for c in cell_list),
        "total_interventions": sum(c["interventions"] for c in cell_list),
        "total_path_samples": sum(c["path_count"] for c in cell_list),
    }
