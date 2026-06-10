"""
FleetSafe Isaac Lab Training Entry Point.

Follows Isaac Lab's AppLauncher pattern:
  1. Parse args + launch AppLauncher (starts Isaac Sim)
  2. Import all Isaac Lab modules (after AppLauncher)
  3. Create env + runner
  4. Train

Usage (via train.sh):
    python fleet_safe_vla/envs/isaaclab/train.py \\
        task=FleetSafe-H1-RoughLocomotion-v0 \\
        num_envs=4096 headless=true

Direct usage:
    conda activate isaac
    export OMNI_KIT_ACCEPT_EULA=Y
    python fleet_safe_vla/envs/isaaclab/train.py task=FleetSafe-H1-RoughLocomotion-v0
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> None:
    # ── Step 1: Parse args and start AppLauncher ─────────────────────────────
    # AppLauncher MUST be started before any omni/isaaclab imports

    parser = argparse.ArgumentParser(description="FleetSafe H1 Training")
    parser.add_argument("--task",      type=str, default="FleetSafe-H1-RoughLocomotion-v0")
    parser.add_argument("--num_envs",  type=int, default=4096)
    parser.add_argument("--headless",  action="store_true", default=True)
    parser.add_argument("--seed",      type=int, default=42)
    parser.add_argument("--log_dir",   type=str, default="logs/fleetsafe_h1")
    parser.add_argument("--max_iter",  type=int, default=10000)
    parser.add_argument("--device",    type=str, default="cuda:0")
    # Allow hydra-style args (task=X num_envs=Y)
    args, extras = parser.parse_known_args()

    # Parse hydra-style overrides from extras
    for extra in extras:
        if "=" in extra:
            key, val = extra.split("=", 1)
            key = key.lstrip("-")
            if key == "task":
                args.task = val
            elif key == "num_envs":
                args.num_envs = int(val)
            elif key == "headless":
                args.headless = val.lower() in ("true", "1", "yes")
            elif key == "seed":
                args.seed = int(val)
            elif key == "log_dir":
                args.log_dir = val

    try:
        from isaaclab.app import AppLauncher

        launcher_args = {
            "headless": args.headless,
            "seed": args.seed,
        }
        app_launcher = AppLauncher(launcher_args)
        simulation_app = app_launcher.app
    except ImportError as e:
        print(f"ERROR: isaaclab not available: {e}")
        print("Ensure you are in the 'isaac' conda environment:")
        print("  conda activate isaac && export OMNI_KIT_ACCEPT_EULA=Y")
        sys.exit(1)

    # ── Step 2: All Isaac Lab imports AFTER AppLauncher ───────────────────────
    import torch
    import gymnasium as gym

    # Register FleetSafe tasks
    import fleet_safe_vla.envs.isaaclab.h1_locomotion_env  # noqa: F401

    from isaaclab_rl.rsl_rl.runner import OnPolicyRunner

    # ── Step 3: Create environment ────────────────────────────────────────────
    env = gym.make(args.task, num_envs=args.num_envs, device=args.device)

    # ── Step 4: Get runner config ─────────────────────────────────────────────
    task_cfg = gym.spec(args.task).kwargs.get("rsl_rl_cfg_entry_point")
    runner_cfg_cls = gym.registry[args.task].kwargs.get("rsl_rl_cfg_entry_point")

    # Use FleetSafeH1RunnerCfg directly
    from fleet_safe_vla.envs.isaaclab.h1_locomotion_env import FleetSafeH1RunnerCfg
    runner_cfg = FleetSafeH1RunnerCfg()
    runner_cfg.max_iterations = args.max_iter

    # ── Step 5: Create and run runner ─────────────────────────────────────────
    log_dir = Path(args.log_dir) / args.task
    runner = OnPolicyRunner(env, runner_cfg, log_dir=str(log_dir), device=args.device)

    print(f"\n[Fleet-Safe] Training: {args.task}")
    print(f"  num_envs={args.num_envs}, max_iter={args.max_iter}")
    print(f"  log_dir={log_dir}\n")

    runner.learn(num_learning_iterations=args.max_iter, init_at_random_ep_len=True)

    # ── Cleanup ───────────────────────────────────────────────────────────────
    env.close()
    simulation_app.close()


if __name__ == "__main__":
    main()
