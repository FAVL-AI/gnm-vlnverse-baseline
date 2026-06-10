"""
Replay browser API — serve episode trajectories, events, and comparisons.

Endpoints:
  GET /api/replay/runs                     — runs that have episode data
  GET /api/replay/{run_id}/episodes        — episode list with meta
  GET /api/replay/{run_id}/{ep_id}/meta    — episode.json summary
  GET /api/replay/{run_id}/{ep_id}/trajectory  — trajectory.csv as JSON
  GET /api/replay/{run_id}/{ep_id}/actions     — actions.csv as JSON
  GET /api/replay/{run_id}/{ep_id}/events      — safety_events.jsonl as JSON
  GET /api/replay/compare/{run_a}/{run_b}/{ep_id}  — paired comparison
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from ..config import settings

router = APIRouter(prefix="/api/replay", tags=["replay"])


def _results_dir() -> Path:
    return settings._results_dir


def _ep_dir(run_id: str, ep_id: str) -> Path:
    return _results_dir() / run_id / "episodes" / ep_id


def _read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def _read_csv(p: Path) -> list[dict[str, Any]]:
    if not p.exists():
        return []
    rows = []
    with open(p, newline="") as f:
        for row in csv.DictReader(f):
            # Cast numeric values
            parsed: dict[str, Any] = {}
            for k, v in row.items():
                try:
                    parsed[k] = float(v) if "." in v else int(v)
                except (ValueError, TypeError):
                    parsed[k] = v
            rows.append(parsed)
    return rows


def _episode_meta(run_id: str, ep_id: str) -> dict | None:
    p = _ep_dir(run_id, ep_id) / "episode.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text())
        # Trim the heavy 'steps' list for the meta endpoint
        d.pop("steps", None)
        return d
    except Exception:
        return None


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/runs")
async def replay_runs() -> list[dict]:
    """Runs that have at least one episode directory."""
    results = _results_dir()
    runs = []
    for run_dir in sorted(results.iterdir(), reverse=True):
        if not run_dir.is_dir():
            continue
        ep_dir = run_dir / "episodes"
        if not ep_dir.exists():
            continue
        episodes = sorted(ep_dir.iterdir())
        if not episodes:
            continue
        # Load metadata
        meta_path = run_dir / "metadata.yaml"
        agg_path  = run_dir / "aggregate_metrics.json"
        model, fleetsafe, backend = "?", False, "?"
        if agg_path.exists():
            try:
                agg = json.loads(agg_path.read_text())
                model     = agg.get("model",     "?")
                fleetsafe = agg.get("fleetsafe",  False)
                backend   = agg.get("backend",   "?")
            except Exception:
                pass
        runs.append({
            "run_id":     run_dir.name,
            "model":      model,
            "fleetsafe":  fleetsafe,
            "backend":    backend,
            "n_episodes": len(episodes),
        })
    return runs


@router.get("/{run_id}/episodes")
async def list_episodes(run_id: str) -> list[dict]:
    ep_root = _results_dir() / run_id / "episodes"
    if not ep_root.exists():
        raise HTTPException(404, f"No episodes for run {run_id!r}")
    eps = []
    for ep_dir in sorted(ep_root.iterdir()):
        if not ep_dir.is_dir():
            continue
        meta = _episode_meta(run_id, ep_dir.name)
        n_events = len(_read_jsonl(ep_dir / "safety_events.jsonl"))
        traj_rows = sum(1 for _ in (ep_dir / "trajectory.csv").open()) - 1 if (ep_dir / "trajectory.csv").exists() else 0
        eps.append({
            "ep_id":        ep_dir.name,
            "scene":        meta.get("scene",   "?") if meta else "?",
            "seed":         meta.get("seed",    0)   if meta else 0,
            "success":      meta.get("success", False) if meta else False,
            "spl":          meta.get("spl",     0.0) if meta else 0.0,
            "collision_count":    meta.get("collision_count",    0) if meta else 0,
            "intervention_count": meta.get("intervention_count", 0) if meta else 0,
            "n_steps":      traj_rows,
            "n_events":     n_events,
        })
    return eps


@router.get("/{run_id}/{ep_id}/meta")
async def episode_meta(run_id: str, ep_id: str) -> dict:
    meta = _episode_meta(run_id, ep_id)
    if meta is None:
        raise HTTPException(404)
    return meta


@router.get("/{run_id}/{ep_id}/trajectory")
async def episode_trajectory(run_id: str, ep_id: str) -> list[dict]:
    return _read_csv(_ep_dir(run_id, ep_id) / "trajectory.csv")


@router.get("/{run_id}/{ep_id}/actions")
async def episode_actions(run_id: str, ep_id: str) -> list[dict]:
    return _read_csv(_ep_dir(run_id, ep_id) / "actions.csv")


@router.get("/{run_id}/{ep_id}/events")
async def episode_events(run_id: str, ep_id: str) -> list[dict]:
    return _read_jsonl(_ep_dir(run_id, ep_id) / "safety_events.jsonl")


@router.get("/compare/{run_a}/{run_b}/{ep_id}")
async def compare_episodes(run_a: str, run_b: str, ep_id: str) -> dict:
    """Return trajectory + actions + events for two runs side-by-side."""
    def _load(run_id: str) -> dict:
        d = _ep_dir(run_id, ep_id)
        return {
            "run_id":     run_id,
            "meta":       _episode_meta(run_id, ep_id),
            "trajectory": _read_csv(d / "trajectory.csv"),
            "actions":    _read_csv(d / "actions.csv"),
            "events":     _read_jsonl(d / "safety_events.jsonl"),
        }
    return {"a": _load(run_a), "b": _load(run_b)}
