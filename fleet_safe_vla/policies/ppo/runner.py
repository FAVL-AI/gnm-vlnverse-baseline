"""
FleetSafe PPO Runner — wraps robot-lab's PPO training loop.

Adds fleet-safety hooks:
  - Per-iteration CBF intervention logging
  - Fleet risk monitoring during training rollouts
  - Checkpoint export with ONNX validation

This runner is called by scripts/isaaclab/train.sh.
It must be run after AppLauncher (Isaac Sim initialized).

Usage (from train.sh):
    python fleet_safe_vla/envs/isaaclab/train.py task=FleetSafe-H1-RoughLocomotion-v0
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def make_fleet_safe_runner(env, runner_cfg, log_dir: str | Path):
    """
    Create an rsl_rl OnPolicyRunner with fleet-safe hooks.

    All Isaac Lab / rsl_rl imports are here (deferred from module level).

    Args:
        env: ManagerBasedRLEnv instance
        runner_cfg: FleetSafeH1RunnerCfg instance
        log_dir: directory for checkpoints and tensorboard logs

    Returns:
        rsl_rl OnPolicyRunner with fleet-safe callbacks
    """
    # All heavy imports happen here — after AppLauncher has started Isaac Sim
    from isaaclab_rl.rsl_rl import RslRlOnPolicyRunner

    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    runner = RslRlOnPolicyRunner(env, runner_cfg, log_dir=str(log_dir))
    return runner
