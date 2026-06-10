"""
publication_run_scanner.py — Scans the simulations/ directory for publication
benchmark runs (both MuJoCo and Isaac) and serves structured data for the
frontend visualisation dashboard.

Returns per-run summary, gate status, live-progress for in-progress runs,
and a cross-backend comparison table for paper figures.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ..config import settings

_SIMS_DIR = settings.repo_root / "simulations"

# ── Internal helpers ──────────────────────────────────────────────────────────

def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _count_results(run_dir: Path) -> int:
    return len(list(run_dir.rglob("aggregate_metrics.json")))


def _extract_scene_from_dir(dir_name: str) -> str:
    """
    Extract scene name from sub-directory names like:
      isaac_{model}_{raw|fs}_{scene}_{ts}   →  {scene}
      {model}_{raw|safe}_{scene}_{ts}        →  {scene}
    Scene names contain underscores, timestamp is always last (looks like T191959 or digits).
    Strategy: strip known prefix tokens (isaac/model/mode) and the timestamp suffix.
    """
    import re
    parts = dir_name.split("_")
    # Drop leading "isaac" prefix if present
    if parts and parts[0] == "isaac":
        parts = parts[1:]
    # Drop model token (first remaining token)
    if len(parts) > 1:
        parts = parts[1:]
    # Drop mode token (raw / fs / safe)
    if parts and parts[0] in ("raw", "fs", "safe"):
        parts = parts[1:]
    # The timestamp suffix matches a pattern like 20260520T191959 (date+T+time)
    if parts and re.match(r"^\d{8}T\d{6}$", parts[-1]):
        parts = parts[:-1]
    return "_".join(parts) if parts else ""


def _all_aggregate_metrics(run_dir: Path) -> list[dict]:
    results = []
    for f in sorted(run_dir.rglob("aggregate_metrics.json")):
        d = _load_json(f)
        if d:
            # Inject scene from directory name if missing.
            # MuJoCo layout: backbone/{combo}/{run_id}/aggregate_metrics.json
            #   → f.parent.name = run_id (looks like "pub_..."), use grandparent
            # Isaac layout:  backbone/{isaac_combo}/aggregate_metrics.json
            #   → f.parent.name = combo dir, use directly
            if not d.get("scene") and not d.get("scene_name"):
                scene = _extract_scene_from_dir(f.parent.name)
                if not scene and f.parent.parent != run_dir:
                    scene = _extract_scene_from_dir(f.parent.parent.name)
                if scene:
                    d = dict(d)
                    d["scene"] = scene
            results.append(d)
    return results


def _expected_combos(n_models: int, n_scenes: int) -> int:
    """RAW + FS for each model × scene."""
    return n_models * n_scenes * 2


# ── Per-run parser ────────────────────────────────────────────────────────────

def _parse_run(run_dir: Path) -> dict | None:
    name = run_dir.name
    if not run_dir.is_dir():
        return None

    # Determine backend from directory name prefix
    if name.startswith("isaac_publication_"):
        backend = "isaaclab"
        ts = name.replace("isaac_publication_", "")
    elif name.startswith("publication_"):
        backend = "mujoco"
        ts = name.replace("publication_", "")
    else:
        return None

    n_results = _count_results(run_dir)
    if n_results == 0:
        return None

    # Load canonical summary file
    summary: dict = {}
    for summary_name in ("all_scenarios_summary.json", "isaac_summary.json"):
        s = _load_json(run_dir / summary_name)
        if s:
            summary = s
            break

    n_seeds = summary.get("n_seeds", 0)
    models: list[str] = summary.get("models", [])
    proven = bool(summary.get("proven", False))
    proven_detail: dict = summary.get("proven_detail", {})

    # Guard: a summary written after only a subset of models completed must not
    # claim proven=True — it represents an intermediate checkpoint, not a full run.
    EXPECTED_MODELS = {"gnm", "vint", "nomad"}
    if proven and models and not EXPECTED_MODELS.issubset({m.lower() for m in models}):
        proven = False
        proven_detail = dict(proven_detail, _partial_run_warning=True)

    # Collect backbone results — "backbone_results" (MuJoCo runner) or
    # "backbone" (Isaac runner) are both valid summary keys.
    # Always prefer on-disk aggregate_metrics over the (potentially stale/partial)
    # summary cache so resume runs are reflected correctly in the frontend.
    backbone_results = _all_aggregate_metrics(run_dir)
    if not backbone_results:
        backbone_results = (
            summary.get("backbone_results")
            or summary.get("backbone")
            or []
        )

    # Expected total combos.
    # Use the max of (summary model count, actual backbone dir model count) to avoid
    # under-counting when a resume run added more models than the partial summary knows.
    n_scenes = len({
        r.get("scene", r.get("scene_name", ""))
        for r in backbone_results
    }) or 3

    # Count unique models seen in backbone subdir names (handles resume case)
    backbone_subdir = run_dir / "backbone"
    dir_models: set[str] = set()
    if backbone_subdir.exists():
        import re as _re
        for sub in backbone_subdir.iterdir():
            if sub.is_dir():
                # "isaac_{model}_{mode}_{scene}_{ts}" → model is second token
                parts = sub.name.split("_")
                if parts and parts[0] == "isaac" and len(parts) > 1:
                    dir_models.add(parts[1])
    n_models_eff = max(len(models) or 3, len(dir_models) or 1, 3)
    expected = _expected_combos(n_models_eff, n_scenes)
    progress_pct = round(min(n_results / expected * 100, 100.0), 1) if expected else 0

    # Build model-level summary
    model_summary: dict[str, dict] = {}
    for r in backbone_results:
        model = r.get("model", "")
        if not model:
            continue
        fs = bool(r.get("fleetsafe", False))
        key = "fs" if fs else "raw"
        scene = r.get("scene", r.get("scene_name", "unknown"))
        if model not in model_summary:
            model_summary[model] = {}
        model_summary[model][f"{key}_{scene}_coll"] = r.get("collision_rate", 0)
        model_summary[model][f"{key}_{scene}_ir"] = r.get("intervention_rate_mean", 0)
        model_summary[model][f"{key}_{scene}_n"] = r.get("n_episodes", 0)

    return {
        "run_id":        name,
        "timestamp":     ts,
        "backend":       backend,
        "n_seeds":       n_seeds,
        "models":        models,
        "n_results":     n_results,
        "expected_combos": expected,
        "progress_pct":  progress_pct,
        "complete":      n_results >= expected,
        "proven":        proven,
        "proven_detail": proven_detail,
        "backbone_results": backbone_results,
        "model_summary": model_summary,
        "evidence_tier": summary.get("evidence_tier", f"SIM-{backend.upper()}"),
        "photoreal":     summary.get("photoreal", backend == "mujoco"),
        "mtime":         run_dir.stat().st_mtime,
    }


# ── Public API ────────────────────────────────────────────────────────────────

def scan_publication_runs() -> list[dict]:
    """Return all publication runs, newest first."""
    if not _SIMS_DIR.exists():
        return []
    runs = []
    for d in _SIMS_DIR.iterdir():
        r = _parse_run(d)
        if r:
            runs.append(r)
    runs.sort(key=lambda r: r["mtime"], reverse=True)
    return runs


def latest_run_by_backend(backend: str) -> dict | None:
    """
    Return the best available run for a backend, preferring (in order):
    1. complete + 50-seed + scenes + valid RAW collisions
    2. in-progress + 50-seed + scenes + valid RAW collisions  (beats old completed 1-seed runs)
    3. complete + scenes + valid RAW collisions
    4. complete + scenes (any)
    5. most recent (partial) with scenes
    6. most recent overall
    """
    runs = [r for r in scan_publication_runs() if r["backend"] == backend]
    if not runs:
        return None

    def _has_scenes(r: dict) -> bool:
        return any(row.get("scene") for row in r.get("backbone_results", []))

    def _has_valid_collisions(r: dict) -> bool:
        """RAW collision rate > 0 in any scene means obstacles are correctly set up."""
        return any(
            row.get("collision_rate", 0) > 0
            for row in r.get("backbone_results", [])
            if not row.get("fleetsafe", False)
        )

    for pred in [
        lambda r: r["complete"] and r["n_seeds"] >= 50 and _has_scenes(r) and _has_valid_collisions(r),
        lambda r: r["n_seeds"] >= 50 and _has_scenes(r) and _has_valid_collisions(r),   # in-progress 50-seed > old complete
        lambda r: r["complete"] and _has_scenes(r) and _has_valid_collisions(r),
        lambda r: r["complete"] and _has_scenes(r),
        lambda r: _has_scenes(r),
        lambda r: True,
    ]:
        candidates = [r for r in runs if pred(r)]
        if candidates:
            return candidates[0]
    return None


def _in_progress_eta(run_dir: Path) -> dict:
    """
    Scan the in-progress run directory to find the active combo and estimate ETA.
    Returns episode_rate (ep/min) and eta_min.
    """
    import time as _time
    active_combo = None
    latest_ep_mtime: float = 0.0
    earliest_ep_mtime: float = float("inf")
    n_eps = 0

    for combo_dir in run_dir.iterdir():
        if not combo_dir.is_dir():
            continue
        if (combo_dir / "aggregate_metrics.json").exists():
            continue  # already complete
        ep_dir = combo_dir / "episodes"
        if not ep_dir.exists():
            continue
        eps = list(ep_dir.iterdir())
        if not eps:
            continue
        mtimes = [e.stat().st_mtime for e in eps]
        active_combo = combo_dir.name
        n_eps = len(eps)
        earliest_ep_mtime = min(mtimes)
        latest_ep_mtime = max(mtimes)

    if not active_combo or n_eps < 2:
        return {}

    elapsed = latest_ep_mtime - earliest_ep_mtime
    rate = (n_eps / elapsed * 60.0) if elapsed > 1 else 0.0  # ep/min
    remaining_ep = max(0, 50 - n_eps)
    eta_min = (remaining_ep / rate) if rate > 0 else None
    age_s = _time.time() - latest_ep_mtime

    return {
        "active_combo": active_combo,
        "n_episodes_done": n_eps,
        "episode_rate_per_min": round(rate, 2),
        "eta_min": round(eta_min, 1) if eta_min is not None else None,
        "last_ep_age_s": round(age_s, 0),
        # Seeds per combo assumed 50; used for total-run ETA computation in frontend
        "seeds_per_combo": 50,
    }


def live_run_status() -> dict:
    """
    Returns the in-progress Isaac run (or most recent), including per-combo results
    and a completion timeline for live frontend polling.
    """
    all_runs = scan_publication_runs()
    isaac_runs = [r for r in all_runs if r["backend"] == "isaaclab"]
    if not isaac_runs:
        return {"status": "none", "runs": []}

    in_progress = [r for r in isaac_runs if not r["complete"]]
    latest_complete = [r for r in isaac_runs if r["complete"]]

    eta_data: dict = {}
    if in_progress:
        run_dir = _SIMS_DIR / in_progress[0]["run_id"]
        if run_dir.exists():
            sub = run_dir / "backbone"
            search_dir = sub if sub.exists() else run_dir
            eta_data = _in_progress_eta(search_dir)

    return {
        "status":          "running" if in_progress else "idle",
        "in_progress":     in_progress[:1],
        "latest_complete": latest_complete[:1],
        "all_isaac":       isaac_runs[:5],
        "eta":             eta_data,
    }


def cross_backend_comparison() -> dict:
    """
    Build a unified comparison table: MuJoCo PROVEN vs Isaac (best available).
    Used for the paper figure and frontend visualisation.
    """
    mujoco = latest_run_by_backend("mujoco")
    isaac  = latest_run_by_backend("isaaclab")

    def _extract_rows(run: dict | None, backend: str) -> list[dict]:
        if not run:
            return []
        rows = []
        for r in run["backbone_results"]:
            rows.append({
                "backend":    backend,
                "model":      r.get("model", ""),
                "scene":      r.get("scene", r.get("scene_name", "")),
                "fleetsafe":  bool(r.get("fleetsafe", False)),
                "collision_rate":              r.get("collision_rate", 0),
                "intervention_rate_mean":      r.get("intervention_rate_mean", 0),
                "min_obstacle_distance_m_mean": r.get("min_obstacle_distance_m_mean"),
                "n_episodes":                  r.get("n_episodes", 0),
                "spl_mean":                    r.get("spl_mean", 0),
                "inference_latency_ms_mean":   r.get("inference_latency_ms_mean"),
                "path_length_m_mean":          r.get("path_length_m_mean"),
                "raw_vs_safe_delta_l2_mean":   r.get("raw_vs_safe_delta_l2_mean"),
                "smoothness_mean":             r.get("smoothness_mean"),
                "steps_green_mean":            r.get("steps_green_mean"),
                "steps_amber_mean":            r.get("steps_amber_mean"),
                "steps_red_mean":              r.get("steps_red_mean"),
                "near_violation_count_mean":   r.get("near_violation_count_mean"),
            })
        return rows

    mujoco_rows = _extract_rows(mujoco, "mujoco")
    isaac_rows  = _extract_rows(isaac,  "isaaclab")

    return {
        "mujoco": {
            "run_id":  mujoco["run_id"] if mujoco else None,
            "proven":  mujoco["proven"] if mujoco else False,
            "n_seeds": mujoco["n_seeds"] if mujoco else 0,
            "rows":    mujoco_rows,
            "proven_detail": mujoco["proven_detail"] if mujoco else {},
        },
        "isaaclab": {
            "run_id":  isaac["run_id"] if isaac else None,
            "proven":  isaac["proven"] if isaac else False,
            "n_seeds": isaac["n_seeds"] if isaac else 0,
            "complete": isaac["complete"] if isaac else False,
            "progress_pct": isaac["progress_pct"] if isaac else 0,
            "rows":    isaac_rows,
            "proven_detail": isaac["proven_detail"] if isaac else {},
        },
        "generated_at": time.time(),
    }
