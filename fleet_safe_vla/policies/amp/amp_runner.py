"""
AMP (Adversarial Motion Priors) Runner for Fleet-Safe H1.

Extends robot-lab's AMP discriminator with fleet-safe modifications:
  - Filters demonstration data through CBF constraints
  - Monitors style reward vs. safety cost tradeoff

All heavy imports are deferred to function bodies.
"""
from __future__ import annotations

from pathlib import Path


def make_amp_runner(env, runner_cfg, motion_file: str, log_dir: str | Path):
    """
    Create an AMP training runner for H1 locomotion style transfer.

    Args:
        env:         ManagerBasedRLEnv
        runner_cfg:  PPO runner config (reuses for AMP base)
        motion_file: path to reference motion data (numpy or mjcf motion)
        log_dir:     output directory

    Returns:
        AMP runner object (rsl_rl compatible)
    """
    # Deferred imports — only after AppLauncher
    from isaaclab_rl.rsl_rl import RslRlOnPolicyRunner
    from robot_lab.imitation.amp_discriminator import AMPDiscriminator
    from robot_lab.imitation.motion_loader import MotionLoader

    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Load reference motion
    motion_loader = MotionLoader(motion_file)

    # AMP discriminator
    state_dim = 45  # proprioceptive observation
    discriminator = AMPDiscriminator(
        state_dim=state_dim,
        hidden_dims=[256, 128],
    )

    # Base PPO runner
    runner = RslRlOnPolicyRunner(env, runner_cfg, log_dir=str(log_dir))

    return runner, discriminator, motion_loader
