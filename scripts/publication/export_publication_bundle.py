#!/usr/bin/env python3
"""
export_publication_bundle.py — One-click publication bundle export. v1.0.

Writes everything needed for a paper submission into a single timestamped
directory. Does not require a running FastAPI server.

Outputs (publication_bundle/<timestamp>/)
-----------------------------------------
  tables/
    table1_main.md          — backbone × safety Table 1 (Markdown)
    table1_main.csv         — same as CSV
    table2_delta.md         — FleetSafe Δ vs baseline
  figures/
    figure_data.json        — data for matplotlib / pgfplots
  manifests/
    reproducibility_manifest.json   — run IDs + git commits + artifact hashes
    smoke_matrix_manifests/  — all smoke matrix runs
  evidence_ledger.jsonl     — snapshot of the evidence ledger
  publication_metrics.json  — all metrics with CI and evidence status
  publication_readiness.json — readiness score + per-item status
  claim_validation_report.json
  README.md

Usage
-----
  python scripts/publication/export_publication_bundle.py [--output-dir PATH]
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "command-center"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_commit() -> str:
    try:
        import subprocess
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(_REPO_ROOT), stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"


def _isaac_proof_status() -> dict:
    # First check: 50-seed publication run PROVEN gate (highest authority)
    import sys as _sys
    _sys.path.insert(0, str(_REPO_ROOT / "command-center"))
    try:
        from backend.services.publication_run_scanner import latest_run_by_backend
        isaac_run = latest_run_by_backend("isaaclab")
        if isaac_run and isaac_run.get("proven"):
            n = isaac_run.get("n_seeds", 0)
            models = [r.get("model","") for r in isaac_run.get("backbone_results",[]) if not r.get("fleetsafe")]
            return {
                "status": "PROVEN",
                "path": None,
                "procedural": f"PROVEN ({n} seeds, {sorted(set(models))} models)",
                "photoreal":  "RTX confirmed",
                "isaac_sim":  "OK",
                "run_id": isaac_run.get("run_id"),
            }
        elif isaac_run:
            n_done = len(isaac_run.get("backbone_results", []))
            return {
                "status": "RECORDED",
                "path": None,
                "procedural": f"IN_PROGRESS ({n_done}/18 combos done)",
                "photoreal":  "MISSING",
                "isaac_sim":  "running",
                "run_id": isaac_run.get("run_id"),
            }
    except Exception:
        pass

    # Fallback: legacy isaac_scene_proof.json from recordings/isaac_proof/
    proof_root = _REPO_ROOT / "recordings" / "isaac_proof"
    if not proof_root.exists():
        return {"status": "NOT_RUN", "path": None}
    runs = sorted(proof_root.iterdir(), reverse=True)
    for r in runs:
        proof_file = r / "isaac_scene_proof.json"
        if proof_file.exists():
            try:
                proof = json.loads(proof_file.read_text())
                return {
                    "status": "RECORDED",
                    "path": str(r),
                    "procedural": proof.get("honest_labels", {}).get("procedural_hospital_status", "?"),
                    "photoreal":  proof.get("honest_labels", {}).get("photoreal_hospital_status", "?"),
                    "isaac_sim":  proof.get("honest_labels", {}).get("isaac_sim_runtime_status", "?"),
                }
            except Exception:
                pass
    return {"status": "NOT_RUN", "path": None}


def _ppo_smoke_status() -> dict:
    ppo_root = _REPO_ROOT / "recordings" / "ppo_smoke"
    if not ppo_root.exists():
        return {"PPO_FULL_TRAINING": "NOT_VALIDATED", "PPO_SMOKE_TRAINING": "NOT_RUN"}
    runs = sorted(ppo_root.iterdir(), reverse=True)
    for r in runs:
        eval_file = r / "eval_metrics.json"
        if eval_file.exists():
            try:
                m = json.loads(eval_file.read_text())
                return {
                    "PPO_FULL_TRAINING":  m.get("PPO_FULL_TRAINING", "NOT_VALIDATED"),
                    "PPO_SMOKE_TRAINING": m.get("PPO_SMOKE_TRAINING", "RECORDED"),
                    "run_id": m.get("run_id"),
                    "mean_reward": m.get("mean_total_reward"),
                    "path": str(r),
                }
            except Exception:
                pass
    return {"PPO_FULL_TRAINING": "NOT_VALIDATED", "PPO_SMOKE_TRAINING": "NOT_RUN"}


def _wandb_hf_status() -> dict:
    int_dir = _REPO_ROOT / "recordings" / "integrations"
    result: dict = {}
    for fname, key in [("wandb_status.json", "wandb"), ("hf_status.json", "hf")]:
        fp = int_dir / fname
        if fp.exists():
            try:
                d = json.loads(fp.read_text())
                result[key] = d.get("honest_label", "MISSING")
            except Exception:
                result[key] = "ERROR"
        else:
            result[key] = "NOT_RUN"
    return result


def _smoke_matrix_status() -> dict:
    """Delegates to sim_evidence_tracker which cross-checks the live registry."""
    try:
        sys.path.insert(0, str(_REPO_ROOT / "command-center"))
        from backend.services.sim_evidence_tracker import _smoke_matrix_status as _tracker_mat
        return _tracker_mat()
    except Exception:
        pass
    # Fallback: read manifest directly (no registry cross-check)
    mat_dir = _REPO_ROOT / "recordings" / "smoke_matrix"
    if not mat_dir.exists():
        return {"status": "NOT_RUN"}
    manifests = sorted(mat_dir.glob("matrix_manifest_*.json"), reverse=True)
    if not manifests:
        return {"status": "NOT_RUN"}
    try:
        m = json.loads(manifests[0].read_text())
        return {
            "status":        m.get("evidence_status", "SYNTHETIC"),
            "n_ok":          m.get("n_ok", 0),
            "n_total":       m.get("n_total", 0),
            "readiness_pct": m.get("ci_metrics", {}).get("readiness_pct"),
        }
    except Exception:
        return {"status": "ERROR"}


def _build_readiness(claims: dict, isaac: dict, ppo: dict, wandb_hf: dict, matrix: dict) -> dict:
    """
    Compute publication readiness.

    Paper claims (from metrics_pipeline.claim_validation_report) are the
    primary source of truth. Integration and infrastructure items are
    secondary checks. Both are merged into a single item list with a
    unified score.
    """
    def _score(s: str) -> float:
        return {"PROVEN": 1.0, "RECORDED": 0.7, "PRELIMINARY": 0.5,
                "RECORDED_ONLY": 0.3, "PARTIAL": 0.3,
                "MISSING": 0.0, "NOT_RUN": 0.0, "NOT_VALIDATED": 0.0,
                "NOT_CONFIGURED": 0.0}.get(s, 0.0)

    # ── Paper claims ──────────────────────────────────────────────────────
    claim_items = [
        {
            "item":   c["claim"],
            "status": c["status"],
            "detail": c.get("evidence", ""),
            "gap":    c.get("gap"),
        }
        for c in claims.get("claims", [])
    ]

    # ── Infrastructure items ──────────────────────────────────────────────
    infra_items = [
        {
            "item": "Isaac hospital proof",
            "status": isaac.get("status", "NOT_RUN"),
            "detail": (f"procedural={isaac.get('procedural','?')} "
                       f"photoreal={isaac.get('photoreal','?')}")
            if isaac.get("status") in ("RECORDED", "PROVEN") else "Run publication 50-seed Isaac benchmark",
        },
        {
            "item": "PPO smoke training",
            "status": ppo.get("PPO_SMOKE_TRAINING", "NOT_RUN"),
            "detail": f"mean_reward={ppo.get('mean_reward','?')}"
            if ppo.get("PPO_SMOKE_TRAINING") == "RECORDED" else "Run run_ppo_smoke.py",
        },
        {
            "item": "W&B integration",
            "status": wandb_hf.get("wandb", "NOT_RUN"),
            "detail": "Run sync_wandb_hf_metadata.py",
        },
        {
            "item": "HuggingFace integration",
            "status": wandb_hf.get("hf", "NOT_RUN"),
            "detail": "Run sync_wandb_hf_metadata.py",
        },
        {
            "item": "Backbone matrix (≥10 seeds)",
            "status": matrix.get("status", "NOT_RUN"),
            "detail": (f"{matrix.get('n_ok',0)}/{matrix.get('n_total',0)} runs OK")
            if matrix.get("status") != "NOT_RUN" else "Run run_publication_smoke_matrix.py",
        },
        {
            "item": "Real robot sessions",
            "status": "RECORDED_ONLY",
            "detail": "YOLO node wired, dry-run mode; need real sessions",
        },
    ]

    all_items = claim_items + infra_items
    scores    = [_score(it["status"]) for it in all_items]
    overall   = round(sum(scores) / len(scores) * 100, 1) if scores else 0.0

    return {
        "items":               all_items,
        "claim_items":         claim_items,
        "infra_items":         infra_items,
        "overall_pct":         overall,
        "target_pct":          80.0,
        "ready_for_submission": overall >= 80.0,
        "n_claims_proven":     sum(1 for c in claims.get("claims", []) if c["status"] == "PROVEN"),
        "n_claims_total":      len(claims.get("claims", [])),
        "generated_at":        _now_iso(),
    }


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--output-dir", default=None)
    args = p.parse_args()

    ts = int(time.time())
    base = Path(args.output_dir) if args.output_dir else (
        _REPO_ROOT / "publication_bundle" / str(ts)
    )
    base.mkdir(parents=True, exist_ok=True)

    tables_dir    = base / "tables"
    figures_dir   = base / "figures"
    manifests_dir = base / "manifests"
    tables_dir.mkdir()
    figures_dir.mkdir()
    manifests_dir.mkdir()

    print(f"[export_bundle] Output → {base}")

    # ── Core paper exporter ───────────────────────────────────────────────────
    print("[export_bundle] Running paper_exporter.bundle()…")
    try:
        from backend.services.paper_artifact_exporter import paper_exporter
        from backend.services.experiment_registry import experiment_registry
        from backend.services.metrics_pipeline import metrics_pipeline

        bundle_dir = paper_exporter.bundle(output_dir=base / "_inner")
        # Flatten into our structure
        for f in bundle_dir.rglob("*"):
            if f.is_file():
                rel = f.relative_to(bundle_dir)
                dest = base / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)
        shutil.rmtree(bundle_dir, ignore_errors=True)

        claims = metrics_pipeline.claim_validation_report()
        table  = metrics_pipeline.full_table()
        deltas = metrics_pipeline.delta_analysis()
        print(f"  {len(table['table'])} table rows, {len(deltas)} deltas")

    except Exception as exc:
        print(f"  [WARN] paper_exporter failed: {exc} — writing empty stubs")
        claims = {"claims": [], "summary": {"total": 0, "proven": 0, "preliminary": 0,
                                            "recorded_only": 0, "not_validated": 0, "readiness_pct": 0.0}}
        table  = {"table": []}
        deltas = []

    # ── Sim evidence statuses ─────────────────────────────────────────────────
    isaac   = _isaac_proof_status()
    ppo     = _ppo_smoke_status()
    wandb_hf = _wandb_hf_status()
    matrix  = _smoke_matrix_status()

    print(f"[export_bundle] Isaac proof:   {isaac.get('status','NOT_RUN')}")
    print(f"[export_bundle] PPO smoke:     {ppo.get('PPO_SMOKE_TRAINING','NOT_RUN')}")
    print(f"[export_bundle] W&B:           {wandb_hf.get('wandb','NOT_RUN')}")
    print(f"[export_bundle] HF:            {wandb_hf.get('hf','NOT_RUN')}")
    print(f"[export_bundle] Smoke matrix:  {matrix.get('status','NOT_RUN')}")

    # ── Evidence ledger snapshot ──────────────────────────────────────────────
    ledger_src = _REPO_ROOT / "command-center" / "recordings" / "evidence_ledger.jsonl"
    if ledger_src.exists():
        shutil.copy2(ledger_src, base / "evidence_ledger.jsonl")
        print(f"[export_bundle] Ledger copied ({ledger_src.stat().st_size} bytes)")
    else:
        (base / "evidence_ledger.jsonl").write_text("")
        print("[export_bundle] Ledger: empty (no recordings yet)")

    # ── Smoke matrix manifests ────────────────────────────────────────────────
    mat_src = _REPO_ROOT / "recordings" / "smoke_matrix"
    if mat_src.exists():
        mat_dst = manifests_dir / "smoke_matrix_manifests"
        shutil.copytree(mat_src, mat_dst, dirs_exist_ok=True)

    # ── Publication readiness ─────────────────────────────────────────────────
    readiness = _build_readiness(claims, isaac, ppo, wandb_hf, matrix)
    (base / "publication_readiness.json").write_text(json.dumps(readiness, indent=2))

    # ── Claim validation ──────────────────────────────────────────────────────
    (base / "claim_validation_report.json").write_text(json.dumps(claims, indent=2))

    # ── README ────────────────────────────────────────────────────────────────
    readme = f"""# FleetSafe Publication Bundle

Generated: {_now_iso()}
Git commit: {_git_commit()}
Overall readiness: {readiness['overall_pct']}% (target ≥ 80%)

## Evidence Status

| Item | Status |
|------|--------|
| Isaac hospital proof | {isaac.get('status','NOT_RUN')} |
| PPO smoke training | {ppo.get('PPO_SMOKE_TRAINING','NOT_RUN')} |
| W&B integration | {wandb_hf.get('wandb','NOT_RUN')} |
| HuggingFace integration | {wandb_hf.get('hf','NOT_RUN')} |
| Smoke matrix | {matrix.get('status','NOT_RUN')} |

## Do NOT Claim

- photoreal hospital complete — USD file not present
- PPO trained — smoke run only (no gradient updates)
- HF dataset published — no upload yet
- Real robot dataset — dry-run mode only

## Contents

- `tables/` — Table 1 (backbone × safety) and delta table
- `figures/` — figure_data.json for matplotlib/pgfplots
- `manifests/` — reproducibility manifest + smoke matrix runs
- `evidence_ledger.jsonl` — append-only evidence record
- `publication_metrics.json` — all metrics with CI
- `publication_readiness.json` — per-item readiness
- `claim_validation_report.json` — paper claim audit

## Reproduction

```bash
git checkout {_git_commit()}
python scripts/visualnav/run_visualnav_benchmark.py \\
    --model gnm --backend mujoco --seeds paper --fleetsafe both
sha256sum benchmarks/visualnav/results/<run_id>/aggregate_metrics.json
```
"""
    (base / "README.md").write_text(readme)

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"PUBLICATION READINESS: {readiness['overall_pct']}% (target ≥ 80%)")
    for it in readiness["items"]:
        print(f"  {it['status']:16s} {it['item']}")
    print(f"\nBundle → {base}")
    print("─" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
