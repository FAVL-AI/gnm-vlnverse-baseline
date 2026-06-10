"""Scan benchmark results directories and build a run index."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def _load_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _load_yaml(p: Path) -> dict:
    try:
        return yaml.safe_load(p.read_text()) or {}
    except Exception:
        return {}


def list_runs(results_dir: Path) -> list[dict[str, Any]]:
    """Return a list of run summaries, newest first."""
    runs: list[dict] = []
    for run_dir in sorted(results_dir.iterdir(), reverse=True):
        if not run_dir.is_dir():
            continue
        meta_path = run_dir / "metadata.yaml"
        agg_path  = run_dir / "aggregate_metrics.json"
        if not agg_path.exists():
            continue

        meta = _load_yaml(meta_path)
        agg  = _load_json(agg_path)

        runs.append({
            "run_id":                    run_dir.name,
            "model":                     agg.get("model",  meta.get("model", "?")),
            "fleetsafe":                 agg.get("fleetsafe", meta.get("fleetsafe", False)),
            "backend":                   agg.get("backend", meta.get("backend", "?")),
            "timestamp_utc":             meta.get("timestamp_utc", ""),
            "n_episodes":                agg.get("n_episodes", 0),
            "success_rate":              agg.get("success_rate", 0.0),
            "collision_rate":            agg.get("collision_rate", 0.0),
            "spl_mean":                  agg.get("spl_mean", 0.0),
            "intervention_rate_mean":    agg.get("intervention_rate_mean", 0.0),
            "inference_latency_ms_mean": agg.get("inference_latency_ms_mean", 0.0),
            "claim_scope":               agg.get("claim_scope", meta.get("claim_scope", "")),
        })
    return runs


def get_run_detail(results_dir: Path, run_id: str) -> dict[str, Any] | None:
    run_dir = results_dir / run_id
    if not run_dir.exists():
        return None

    metrics  = _load_json(run_dir / "aggregate_metrics.json")
    metadata = _load_yaml(run_dir / "metadata.yaml")
    by_scene = _load_json(run_dir / "aggregate_by_scene.json")

    episodes: list[dict] = []
    ep_dir = run_dir / "episodes"
    if ep_dir.exists():
        for ep_path in sorted(ep_dir.rglob("episode.json"))[:50]:
            ep = _load_json(ep_path)
            if ep:
                episodes.append(ep)

    summary = list_runs(results_dir)
    base = next((r for r in summary if r["run_id"] == run_id), {})

    return {
        **base,
        "metrics":  metrics,
        "metadata": metadata,
        "by_scene": by_scene,
        "episodes": episodes,
        "files":    _list_files(run_dir),
    }


def _list_files(run_dir: Path) -> list[dict]:
    files = []
    for p in run_dir.rglob("*"):
        if p.is_file():
            files.append({
                "name":  p.name,
                "rel":   str(p.relative_to(run_dir)),
                "size":  p.stat().st_size,
            })
    return sorted(files, key=lambda f: f["rel"])
