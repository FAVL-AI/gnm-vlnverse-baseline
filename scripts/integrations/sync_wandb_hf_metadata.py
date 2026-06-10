#!/usr/bin/env python3
"""
sync_wandb_hf_metadata.py — W&B / HuggingFace metadata check. v1.0.

Reads configuration from environment variables (never from committed tokens).
Writes status files regardless of whether integrations are configured.

If a run does not exist: status = MISSING (not failure).
If a token is not set: status = NOT_CONFIGURED (not failure).

Environment variables
---------------------
  WANDB_API_KEY    — W&B API key (optional)
  WANDB_ENTITY     — W&B entity/username (optional)
  WANDB_PROJECT    — W&B project name (default: fleetsafe-visualnav)
  HF_TOKEN         — HuggingFace token (optional)
  HF_USERNAME      — HF username (optional)
  ORCID_ID         — Researcher ORCID (optional, e.g. 0000-0002-1234-5678)

Outputs (recordings/integrations/)
-----------------------------------
  wandb_status.json
  hf_status.json
  researcher_identity.json

Usage
-----
  python scripts/integrations/sync_wandb_hf_metadata.py
"""
from __future__ import annotations

import json
import os
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


# ── W&B status ────────────────────────────────────────────────────────────────

def _get_wandb_status() -> dict:
    """
    Wraps backend wandb_connector. Falls back gracefully if env not set.
    Augments with WANDB_ENTITY and WANDB_PROJECT from environment.
    """
    entity  = os.environ.get("WANDB_ENTITY", "f-a-v-l")
    project = os.environ.get("WANDB_PROJECT", "fleet-safe-vla")

    try:
        from backend.services.wandb_connector import get_wandb_status
        status = get_wandb_status()
    except ImportError:
        # Fallback: try wandb directly
        try:
            import wandb
            try:
                api = wandb.Api(timeout=5)
                target = f"{entity}/{project}" if entity else project
                runs = list(api.runs(target, per_page=5))
                username = api.viewer.username if hasattr(api.viewer, "username") else ""
                status = {
                    "status": "ok" if runs else "no_runs",
                    "project": target,
                    "username": username,
                    "runs": [{"id": r.id, "name": r.name, "state": r.state} for r in runs[:5]],
                }
            except Exception as e:
                status = {"status": "no_runs", "project": project, "warning": str(e), "runs": []}
        except ImportError:
            status = {
                "status": "not_configured",
                "warning": "wandb not installed",
                "runs": [],
            }

    # Merge env config
    status["entity"]  = entity or status.get("entity", "")
    status["project"] = project
    status["checked_at"] = _now_iso()

    # Honest status normalisation
    if status.get("status") in ("no_runs", None) and not status.get("runs"):
        status["honest_label"] = "MISSING"
        status.setdefault("warning", f"No W&B runs in project '{project}' — start a training run")
    elif status.get("status") == "not_configured":
        status["honest_label"] = "NOT_CONFIGURED"
    elif status.get("status") == "ok":
        status["honest_label"] = "RECORDED"
    else:
        status["honest_label"] = "MISSING"

    return status


# ── HuggingFace status ────────────────────────────────────────────────────────

def _get_hf_status() -> dict:
    username = os.environ.get("HF_USERNAME", "")

    try:
        from backend.services.hf_connector import get_hf_status
        status = get_hf_status()
    except ImportError:
        try:
            from huggingface_hub import HfApi
            api = HfApi()
            try:
                user = api.whoami()
                uname = user.get("name", username or "unknown")
                models = []
                try:
                    from huggingface_hub import list_models
                    models = list(list_models(author=uname, search="fleetsafe", limit=5))
                except Exception:
                    pass
                if models:
                    status = {
                        "status": "ok",
                        "username": uname,
                        "runs": [{"model_id": m.modelId} for m in models],
                    }
                else:
                    status = {
                        "status": "no_runs",
                        "username": uname,
                        "warning": "No FleetSafe model repos found",
                        "runs": [],
                    }
            except Exception as e:
                status = {"status": "not_configured", "warning": str(e), "runs": []}
        except ImportError:
            status = {
                "status": "not_configured",
                "warning": "huggingface_hub not installed",
                "runs": [],
            }

    status["username"]   = username or status.get("username", "")
    status["checked_at"] = _now_iso()

    if status.get("status") == "ok":
        status["honest_label"] = "RECORDED"
    elif status.get("status") == "no_runs":
        status["honest_label"] = "MISSING"
    else:
        status["honest_label"] = "NOT_CONFIGURED"

    return status


# ── Researcher identity ───────────────────────────────────────────────────────

def _get_researcher_identity() -> dict:
    orcid     = os.environ.get("ORCID_ID", "")
    hf_user   = os.environ.get("HF_USERNAME", "")
    wandb_ent = os.environ.get("WANDB_ENTITY", "")

    return {
        "orcid_id":      orcid or None,
        "hf_username":   hf_user or None,
        "wandb_entity":  wandb_ent or None,
        "orcid_status":  "SET" if orcid else "NOT_SET",
        "hf_status":     "SET" if hf_user else "NOT_SET",
        "wandb_status":  "SET" if wandb_ent else "NOT_SET",
        "git_commit":    _git_commit(),
        "generated_at":  _now_iso(),
        "note": (
            "Identity fields are read from environment variables — "
            "no credentials are committed to this repository."
        ),
    }


# ── Evidence ledger ───────────────────────────────────────────────────────────

def _record_evidence(out_dir: Path, wandb_s: dict, hf_s: dict) -> None:
    try:
        from backend.services.evidence_ledger import evidence_ledger
        combined = out_dir / "wandb_status.json"
        evidence_ledger.record(
            claim_scope="ros2_verification",  # closest scope: integration status
            source="wandb",
            ground_truth_type="none",
            description=(
                f"W&B status={wandb_s['honest_label']}, "
                f"HF status={hf_s['honest_label']}"
            ),
            artifact_path=combined,
            operator="sync_wandb_hf_metadata",
            metadata={
                "wandb_label": wandb_s["honest_label"],
                "hf_label":    hf_s["honest_label"],
            },
        )
    except Exception:
        pass


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    out_dir = _REPO_ROOT / "recordings" / "integrations"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("[sync_wandb_hf] Checking W&B status…")
    wandb_status = _get_wandb_status()
    print(f"  W&B:  {wandb_status['honest_label']}")

    print("[sync_wandb_hf] Checking HuggingFace status…")
    hf_status = _get_hf_status()
    print(f"  HF:   {hf_status['honest_label']}")

    identity = _get_researcher_identity()
    print(f"[sync_wandb_hf] ORCID: {identity['orcid_status']}")

    (out_dir / "wandb_status.json").write_text(json.dumps(wandb_status, indent=2, default=str))
    (out_dir / "hf_status.json").write_text(json.dumps(hf_status, indent=2, default=str))
    (out_dir / "researcher_identity.json").write_text(json.dumps(identity, indent=2, default=str))

    _record_evidence(out_dir, wandb_status, hf_status)

    print("\n" + "─" * 50)
    print(f"  W&B  {wandb_status['honest_label']}")
    print(f"  HF   {hf_status['honest_label']}")
    print(f"  ORCID {identity['orcid_status']}")
    print(f"\nArtifacts → {out_dir}")
    print("─" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())
