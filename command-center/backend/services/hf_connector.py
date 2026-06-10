"""
HuggingFace connector — metadata only, honest about absence. v1.1.

Priority resolution for the dataset repo:
  1. HF_REPO_ID env var (explicit, e.g. "FAVL/fleetsafe-hospitalnav")
  2. f"{HF_USERNAME}/fleetsafe-hospitalnav"  (from HF_USERNAME env var)
  3. Falls back to search for any fleetsafe model repos under authenticated user

Returns explicit status:
  ok             — repo exists and has files
  missing        — authenticated but repo not found
  not_configured — no token / huggingface_hub not installed
  error          — unexpected error
"""
from __future__ import annotations

import os


def _default_repo_id() -> str:
    username = os.environ.get("HF_USERNAME", "")
    explicit  = os.environ.get("HF_REPO_ID", "")
    if explicit:
        return explicit
    if username:
        return f"{username}/fleetsafe-hospitalnav"
    return ""


def get_hf_status() -> dict:
    repo_id = _default_repo_id()

    try:
        from huggingface_hub import HfApi
        api = HfApi()

        # Confirm authentication
        try:
            user    = api.whoami()
            uname   = user.get("name", "") or user.get("username", "")
        except Exception:
            return {
                "status":  "not_configured",
                "warning": "HuggingFace token not set — set HF_TOKEN env var or run `huggingface-cli login`",
                "repo_id": repo_id or None,
                "runs":    [],
            }

        # If we have an explicit repo_id, query it directly
        if repo_id:
            try:
                from huggingface_hub.utils import RepositoryNotFoundError, HfHubHTTPError
            except ImportError:
                RepositoryNotFoundError = Exception
                HfHubHTTPError = Exception
            try:
                info = api.repo_info(repo_id, repo_type="dataset")
                siblings = getattr(info, "siblings", []) or []
                files    = [s.rfilename for s in siblings]
                return {
                    "status":        "ok",
                    "username":      uname,
                    "repo_id":       repo_id,
                    "url":           f"https://huggingface.co/datasets/{repo_id}",
                    "last_modified": str(getattr(info, "lastModified", None)
                                        or getattr(info, "last_modified", None)),
                    "n_files":       len(files),
                    "files":         files[:20],
                    "runs": [{
                        "repo_id":  repo_id,
                        "n_files":  len(files),
                        "url":      f"https://huggingface.co/datasets/{repo_id}",
                    }],
                }
            except RepositoryNotFoundError:
                return {
                    "status":  "missing",
                    "username": uname,
                    "repo_id": repo_id,
                    "warning": (
                        f"Dataset repo '{repo_id}' not found on HuggingFace. "
                        "Create it at https://huggingface.co/new-dataset"
                    ),
                    "runs": [],
                }
            except HfHubHTTPError as e:
                return {
                    "status":  "missing",
                    "username": uname,
                    "repo_id": repo_id,
                    "warning": f"HTTP error querying '{repo_id}': {e}",
                    "runs": [],
                }

        # Fallback: search for any fleetsafe repos under this user
        try:
            from huggingface_hub import list_models, list_datasets
            datasets = list(list_datasets(author=uname, search="fleetsafe", limit=5))
            models   = list(list_models(author=uname, search="fleetsafe",  limit=5))
            all_repos = datasets + models
        except Exception:
            all_repos = []

        if all_repos:
            return {
                "status":   "ok",
                "username": uname,
                "repo_id":  None,
                "warning":  "No HF_REPO_ID set — found repos via search",
                "runs": [{"repo_id": getattr(r, "id", str(r))} for r in all_repos[:5]],
            }

        return {
            "status":   "no_runs",
            "username": uname,
            "repo_id":  None,
            "warning":  (
                "No FleetSafe repos found on HuggingFace. "
                "Set HF_REPO_ID=OWNER/repo-name or create a dataset repo."
            ),
            "runs": [],
        }

    except ImportError:
        return {
            "status":  "not_configured",
            "warning": "huggingface_hub not installed — pip install huggingface-hub",
            "repo_id": repo_id or None,
            "runs":    [],
        }
    except Exception as e:
        return {
            "status": "error",
            "error":  str(e),
            "repo_id": repo_id or None,
            "runs":   [],
        }
