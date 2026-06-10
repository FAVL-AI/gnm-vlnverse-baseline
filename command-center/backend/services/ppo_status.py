"""
PPO training status — reports honestly based on file system evidence.

Status values:
  shim_only   — adapter code exists, no checkpoint or training run found
  checkpoint  — at least one checkpoint file found
  training    — active W&B run detected
  not_started — nothing found at all
"""
from __future__ import annotations

from pathlib import Path

from ..config import settings

CHECKPOINT_PATTERNS = [
    "**/*.pt", "**/*.ckpt", "**/*.pkl",
    "**/ppo_checkpoint*", "**/policy*",
]

SHIM_PATH = settings.repo_root / "fleet_safe_vla" / "adapters" / "ppo_adapter.py"
SCRIPTS_RL = settings.repo_root / "scripts" / "rl"


def get_ppo_status() -> dict:
    checkpoints = []
    for pattern in CHECKPOINT_PATTERNS:
        for p in settings.repo_root.glob(pattern):
            # Exclude virtual envs and node_modules
            parts = p.parts
            if any(x in parts for x in (".venv", "node_modules", "__pycache__", "site-packages")):
                continue
            checkpoints.append(str(p))

    shim_exists = SHIM_PATH.exists()
    has_rl_scripts = SCRIPTS_RL.exists() and any(SCRIPTS_RL.glob("*.py"))

    if not shim_exists and not checkpoints:
        status = "not_started"
        warning = "No PPO adapter or checkpoints found"
    elif shim_exists and not checkpoints:
        status = "shim_only"
        warning = (
            "PPO adapter code exists but no training checkpoint found. "
            "Run a training session to produce a checkpoint."
        )
    else:
        status = "checkpoint"
        warning = None

    return {
        "status": status,
        "warning": warning,
        "shim_exists": shim_exists,
        "shim_path": str(SHIM_PATH) if shim_exists else None,
        "has_rl_scripts": has_rl_scripts,
        "checkpoints": checkpoints[:10],
        "checkpoint_count": len(checkpoints),
        "training_active": False,  # requires W&B active run
        "notes": [
            "PPO adapter is a shim — wraps existing policy for RL fine-tuning",
            "Full training run not yet completed",
            "Evaluation episodes: not available until checkpoint exists",
        ] if status == "shim_only" else [],
    }
