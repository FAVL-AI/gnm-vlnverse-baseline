"""
W&B connector — metadata only, honest about absence.

Returns explicit status: configured | not_configured | no_runs | error

Project and entity are read from environment variables so they can be
set per-session without committing credentials:
  WANDB_PROJECT  (default: fleet-safe-vla)
  WANDB_ENTITY   (default: f-a-v-l, or derived from api.viewer.username)
"""
from __future__ import annotations

import os

_DEFAULT_PROJECT = "fleet-safe-vla"
_DEFAULT_ENTITY  = "f-a-v-l"


def get_wandb_status() -> dict:
    project = os.environ.get("WANDB_PROJECT", _DEFAULT_PROJECT)
    entity  = os.environ.get("WANDB_ENTITY", _DEFAULT_ENTITY)

    try:
        import wandb
        api = wandb.Api(timeout=8)

        # Resolve username from viewer (property in modern wandb SDK, not a method)
        try:
            viewer   = api.viewer  # NOT api.viewer() — property, not callable
            username = viewer.username
        except Exception:
            return {
                "status":  "not_configured",
                "warning": "W&B not logged in — run `wandb login` or set WANDB_API_KEY",
                "runs":    [],
            }

        # Build the full project path: entity/project
        resolved_entity  = entity or username
        project_path     = f"{resolved_entity}/{project}"

        try:
            runs = list(api.runs(project_path, per_page=20))
        except Exception as e:
            # Project doesn't exist yet or access denied
            return {
                "status":   "no_runs",
                "username": username,
                "entity":   resolved_entity,
                "project":  project,
                "warning":  (
                    f"No runs found at '{project_path}' — "
                    "create the project on wandb.ai or start a training run"
                ),
                "runs": [],
            }

        if not runs:
            return {
                "status":   "no_runs",
                "username": username,
                "entity":   resolved_entity,
                "project":  project,
                "warning":  f"Project '{project_path}' exists but has no runs",
                "runs":     [],
            }

        import json

        def _safe_summary(s) -> dict:
            """Convert wandb SummarySubDict to a plain JSON-serializable dict."""
            try:
                raw = dict(s) if s else {}
                return json.loads(json.dumps(raw, default=str))
            except Exception:
                return {}

        return {
            "status":   "ok",
            "username": username,
            "entity":   resolved_entity,
            "project":  project,
            "runs": [
                {
                    "id":         r.id,
                    "name":       r.name,
                    "state":      r.state,
                    "created_at": str(r.created_at),
                    "summary":    _safe_summary(r.summary),
                }
                for r in runs[:10]
            ],
        }

    except ImportError:
        return {
            "status":  "not_configured",
            "warning": "wandb not installed — pip install wandb",
            "runs":    [],
        }
    except Exception as e:
        return {
            "status": "error",
            "error":  str(e),
            "runs":   [],
        }
