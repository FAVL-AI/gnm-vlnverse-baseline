"""
sim_evidence_tracker.py — Aggregates status of all simulation evidence items. v1.0.

Reads from local recording directories — no Isaac/W&B connection required.
Returns honest labels: PROVEN / RECORDED / PRELIMINARY / MISSING / NOT_RUN.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from ..config import settings

_REPO_ROOT = settings.repo_root


def _isaac_proof_status() -> dict:
    proof_root = _REPO_ROOT / "recordings" / "isaac_proof"
    if not proof_root.exists() or not list(proof_root.iterdir()):
        return {
            "status":     "NOT_RUN",
            "honest_label": "NOT_RUN",
            "guidance":   "Run: python scripts/isaaclab/capture_hospital_proof.py",
        }
    runs = sorted(proof_root.iterdir(), reverse=True)
    for r in runs:
        proof_file = r / "isaac_scene_proof.json"
        if proof_file.exists():
            try:
                proof = json.loads(proof_file.read_text())
                labels = proof.get("honest_labels", {})
                return {
                    "status":          "RECORDED",
                    "honest_label":    "RECORDED",
                    "run_dir":         str(r),
                    "procedural":      labels.get("procedural_hospital_status", "UNKNOWN"),
                    "photoreal":       labels.get("photoreal_hospital_status", "MISSING"),
                    "isaac_sim":       labels.get("isaac_sim_runtime_status", "NOT_AVAILABLE"),
                    "do_not_claim": [s for s in proof.get("do_not_claim", [])],
                }
            except Exception:
                pass
    return {"status": "NOT_RUN", "honest_label": "NOT_RUN"}


def _ppo_smoke_status() -> dict:
    ppo_root = _REPO_ROOT / "recordings" / "ppo_smoke"
    if not ppo_root.exists() or not list(ppo_root.iterdir()):
        return {
            "PPO_FULL_TRAINING":  "NOT_VALIDATED",
            "PPO_SMOKE_TRAINING": "NOT_RUN",
            "guidance":           "Run: python scripts/training/run_ppo_smoke.py",
        }
    runs = sorted(ppo_root.iterdir(), reverse=True)
    for r in runs:
        eval_file = r / "eval_metrics.json"
        if eval_file.exists():
            try:
                m = json.loads(eval_file.read_text())
                return {
                    "PPO_FULL_TRAINING":  m.get("PPO_FULL_TRAINING",  "NOT_VALIDATED"),
                    "PPO_SMOKE_TRAINING": m.get("PPO_SMOKE_TRAINING", "RECORDED"),
                    "run_id":             m.get("run_id"),
                    "mean_reward":        m.get("mean_total_reward"),
                    "n_steps":            m.get("n_steps"),
                    "run_dir":            str(r),
                }
            except Exception:
                pass
    return {"PPO_FULL_TRAINING": "NOT_VALIDATED", "PPO_SMOKE_TRAINING": "NOT_RUN"}


def _wandb_hf_status() -> dict:
    int_dir = _REPO_ROOT / "recordings" / "integrations"
    result: dict = {"wandb": "NOT_RUN", "hf": "NOT_RUN"}
    for fname, key in [("wandb_status.json", "wandb"), ("hf_status.json", "hf")]:
        fp = int_dir / fname
        if fp.exists():
            try:
                d = json.loads(fp.read_text())
                result[key] = d.get("honest_label", "MISSING")
                result[f"{key}_detail"] = d.get("warning") or d.get("project") or ""
            except Exception:
                result[key] = "ERROR"
    if not int_dir.exists():
        result["guidance"] = "Run: python scripts/integrations/sync_wandb_hf_metadata.py"
    return result


def _smoke_matrix_status() -> dict:
    mat_dir = _REPO_ROOT / "recordings" / "smoke_matrix"
    if not mat_dir.exists():
        return {
            "status": "NOT_RUN",
            "guidance": "Run: python scripts/visualnav/run_publication_smoke_matrix.py",
        }
    manifests = sorted(mat_dir.glob("matrix_manifest_*.json"), reverse=True)
    if not manifests:
        return {"status": "NOT_RUN"}
    try:
        m = json.loads(manifests[0].read_text())

        # Cross-check against actual registry: manifests cache evidence_status at
        # run time, but the registry accumulates across all sessions. If the
        # registry shows ≥10 seeds per arm for ≥1 non-MOCK backbone, promote to PROVEN.
        registry_status = "SYNTHETIC"
        try:
            sys.path.insert(0, str(_REPO_ROOT / "command-center"))
            from backend.services.experiment_registry import experiment_registry
            pub_runs = [
                r for r in experiment_registry.scan()
                if r["backbone"] not in ("MOCK",)
                and r["backend_raw"] in ("mujoco", "isaaclab")
            ]
            counts = Counter((r["backbone"], r["safety_mode"]) for r in pub_runs)
            proven_backbones = {
                bb for (bb, _), n in counts.items()
                if n >= 10
                and counts.get((bb, "FleetSafe_full"), 0) >= 10
                and counts.get((bb, "nominal_only"), 0) >= 10
            }
            if len(proven_backbones) >= 1:
                registry_status = "PROVEN"
            elif pub_runs:
                registry_status = "PRELIMINARY"
        except Exception:
            pass

        return {
            "status":        registry_status,
            "n_ok":          m.get("n_ok", 0),
            "n_total":       m.get("n_total", 0),
            "readiness_pct": m.get("ci_metrics", {}).get("readiness_pct"),
            "config":        m.get("config", {}),
            "proven_backbones": list(proven_backbones) if "proven_backbones" in dir() else [],
        }
    except Exception:
        return {"status": "ERROR"}


def _bundle_status() -> dict:
    bundle_root = _REPO_ROOT / "publication_bundle"
    if not bundle_root.exists():
        return {
            "status": "NOT_RUN",
            "guidance": "Run: python scripts/publication/export_publication_bundle.py",
        }
    bundles = sorted(bundle_root.iterdir(), reverse=True)
    for b in bundles:
        readme = b / "README.md"
        readiness = b / "publication_readiness.json"
        if readiness.exists():
            try:
                r = json.loads(readiness.read_text())
                return {
                    "status":      "RECORDED",
                    "bundle_dir":  str(b),
                    "overall_pct": r.get("overall_pct"),
                    "ready":       r.get("ready_for_submission", False),
                }
            except Exception:
                pass
        if readme.exists():
            return {"status": "RECORDED", "bundle_dir": str(b)}
    return {"status": "NOT_RUN"}


def get_sim_evidence_status() -> dict:
    """Aggregate status of all simulation evidence components."""
    isaac   = _isaac_proof_status()
    ppo     = _ppo_smoke_status()
    wh      = _wandb_hf_status()
    matrix  = _smoke_matrix_status()
    bundle  = _bundle_status()

    items = [
        {"name": "isaac_hospital_proof",  "status": isaac.get("honest_label", "NOT_RUN")},
        {"name": "ppo_smoke_training",    "status": ppo.get("PPO_SMOKE_TRAINING", "NOT_RUN")},
        {"name": "ppo_full_training",     "status": ppo.get("PPO_FULL_TRAINING",  "NOT_VALIDATED")},
        {"name": "wandb_sync",            "status": wh.get("wandb",  "NOT_RUN")},
        {"name": "hf_sync",               "status": wh.get("hf",     "NOT_RUN")},
        {"name": "smoke_matrix",          "status": matrix.get("status", "NOT_RUN")},
        {"name": "publication_bundle",    "status": bundle.get("status", "NOT_RUN")},
    ]

    def _weight(s: str) -> float:
        return {"PROVEN": 1.0, "RECORDED": 0.7, "PRELIMINARY": 0.5,
                "RECORDED_ONLY": 0.3, "PARTIAL": 0.3,
                "MISSING": 0.0, "NOT_RUN": 0.0, "NOT_VALIDATED": 0.0,
                "NOT_CONFIGURED": 0.0, "ERROR": 0.0}.get(s, 0.0)

    pct = round(sum(_weight(it["status"]) for it in items) / len(items) * 100, 1)

    return {
        "items":          items,
        "overall_pct":    pct,
        "isaac":          isaac,
        "ppo":            ppo,
        "wandb_hf":       wh,
        "smoke_matrix":   matrix,
        "bundle":         bundle,
    }
