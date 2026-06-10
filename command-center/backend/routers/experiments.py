"""
Experiments & Publication router — v1.1.

  GET  /api/experiments/runs                   — full registry
  GET  /api/experiments/runs/{run_id}          — single run detail
  GET  /api/experiments/summary                — registry summary
  GET  /api/experiments/compare/{backbone}     — baseline vs FleetSafe delta
  GET  /api/experiments/table                  — paper comparison table
  GET  /api/experiments/deltas                 — all backbone deltas
  GET  /api/experiments/claims                 — paper claim validation report
  POST /api/experiments/export                 — generate publication bundle
  GET  /api/experiments/manifest               — reproducibility manifest
  GET  /api/experiments/figure-data            — data for paper figures
  GET  /api/experiments/sim-evidence-status    — Isaac/PPO/W&B/matrix status (v1.0)
  GET  /api/experiments/publication-runs       — all simulations/ runs, newest first
  GET  /api/experiments/live-run               — in-progress Isaac run + recent complete
  GET  /api/experiments/cross-backend          — unified MuJoCo vs Isaac comparison table
"""
from __future__ import annotations

from fastapi import APIRouter

from ..services.experiment_registry import experiment_registry
from ..services.metrics_pipeline import metrics_pipeline
from ..services.paper_artifact_exporter import paper_exporter
from ..services.sim_evidence_tracker import get_sim_evidence_status as _sim_evidence_status
from ..services.publication_run_scanner import (
    scan_publication_runs,
    live_run_status,
    cross_backend_comparison,
)

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


@router.get("/runs")
async def get_runs(backbone: str | None = None, backend: str | None = None,
                   safety_mode: str | None = None) -> list[dict]:
    runs = experiment_registry.scan()
    if backbone:
        runs = [r for r in runs if r["backbone"].lower() == backbone.lower()]
    if backend:
        runs = [r for r in runs if r["backend_raw"] == backend]
    if safety_mode:
        runs = [r for r in runs if r["safety_mode"] == safety_mode]
    return runs


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    run = experiment_registry.get_run(run_id)
    if run is None:
        from fastapi import HTTPException
        raise HTTPException(404, detail=f"Run '{run_id}' not found")
    return run


@router.get("/summary")
async def get_summary() -> dict:
    return experiment_registry.summary()


@router.get("/compare/{backbone}")
async def compare(backbone: str, backend: str | None = None) -> dict:
    return experiment_registry.compare(backbone, backend)


@router.get("/table")
async def get_table(backend: str | None = None) -> dict:
    return metrics_pipeline.full_table(backend=backend)


@router.get("/deltas")
async def get_deltas() -> list[dict]:
    return metrics_pipeline.delta_analysis()


@router.get("/claims")
async def get_claims() -> dict:
    return metrics_pipeline.claim_validation_report()


@router.post("/export")
async def export_bundle() -> dict:
    out = paper_exporter.bundle()
    return {
        "ok": True,
        "output_dir": str(out),
        "files": [str(p.relative_to(out)) for p in out.rglob("*") if p.is_file()],
    }


@router.get("/manifest")
async def get_manifest() -> dict:
    return paper_exporter.export_manifest()


@router.get("/figure-data")
async def get_figure_data() -> dict:
    return paper_exporter.export_figure_data()


@router.get("/sim-evidence-status")
async def sim_evidence_status() -> dict:
    """
    Aggregate status of all simulation evidence items (v1.0).
    Reads from local recording directories — no external connections.
    Returns honest labels: PROVEN / RECORDED / PRELIMINARY / MISSING / NOT_RUN.
    """
    return _sim_evidence_status()


# ── Publication run scanner endpoints (v1.1) ──────────────────────────────────

@router.get("/publication-runs")
async def get_publication_runs() -> list[dict]:
    """
    All publication runs from simulations/ directory, newest first.
    Covers both MuJoCo (publication_*) and Isaac (isaac_publication_*) runs.
    """
    return scan_publication_runs()


@router.get("/live-run")
async def get_live_run() -> dict:
    """
    In-progress Isaac run status + most recent complete Isaac run.
    Polls the simulations/ directory for aggregate_metrics.json files.
    Safe to call at 5-second intervals from the frontend.
    """
    return live_run_status()


@router.get("/cross-backend")
async def get_cross_backend() -> dict:
    """
    Unified MuJoCo vs Isaac comparison table for paper figures.
    Returns per-row collision_rate, intervention_rate, n_episodes for
    (model × scene × fleetsafe × backend) and gate status for both backends.
    """
    return cross_backend_comparison()


@router.get("/isaac-progress")
async def get_isaac_progress() -> dict:
    """
    Real-time episode-level progress for all Isaac combos in the latest run.
    Returns {run_id, combos: [{model, scene, mode, n_done, n_target, done, collision_rate?}]}.
    Safe to poll every 10-15 seconds.
    """
    from pathlib import Path
    import json

    sim_dir = Path(__file__).resolve().parents[3] / "simulations"
    candidates = sorted(sim_dir.glob("isaac_publication_*"), reverse=True)
    if not candidates:
        return {"run_id": None, "combos": []}

    run_dir = candidates[0]
    backbone_dir = run_dir / "backbone"
    if not backbone_dir.exists():
        return {"run_id": run_dir.name, "combos": []}

    MODELS = ["gnm", "vint", "nomad"]
    SCENES = ["hospital_corridor", "hospital_icu_approach", "hospital_elevator_lobby"]
    MODES  = ["raw", "fs"]
    N_TARGET = 50

    combos = []
    for model in MODELS:
        for scene in SCENES:
            for mode in MODES:
                combo_dir = backbone_dir / f"isaac_{model}_{mode}_{scene}_{run_dir.name.replace('isaac_publication_','')}"
                agg_file = combo_dir / "aggregate_metrics.json"
                if agg_file.exists():
                    try:
                        d = json.loads(agg_file.read_text())
                        combos.append({
                            "model": model, "scene": scene, "mode": mode,
                            "n_done": d.get("n_episodes", N_TARGET),
                            "n_target": N_TARGET,
                            "done": True,
                            "collision_rate": d.get("collision_rate"),
                            "intervention_rate": d.get("intervention_rate_mean"),
                        })
                    except Exception:
                        combos.append({
                            "model": model, "scene": scene, "mode": mode,
                            "n_done": N_TARGET, "n_target": N_TARGET, "done": True,
                        })
                elif combo_dir.exists():
                    eps_dir = combo_dir / "episodes"
                    n_done = len(list(eps_dir.glob("episode_*"))) if eps_dir.exists() else 0
                    combos.append({
                        "model": model, "scene": scene, "mode": mode,
                        "n_done": n_done, "n_target": N_TARGET, "done": False,
                    })
                else:
                    combos.append({
                        "model": model, "scene": scene, "mode": mode,
                        "n_done": 0, "n_target": N_TARGET, "done": False,
                    })

    total_done   = sum(1 for c in combos if c["done"])
    total_eps    = sum(c["n_done"] for c in combos)
    total_target = len(combos) * N_TARGET

    return {
        "run_id": run_dir.name,
        "combos": combos,
        "total_combos_done": total_done,
        "total_combos":      len(combos),
        "total_eps_done":    total_eps,
        "total_eps_target":  total_target,
        "progress_pct":      round(total_eps / total_target * 100, 1),
    }
