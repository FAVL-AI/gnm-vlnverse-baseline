"""
FleetSafe Isaac Lab Evaluation Entry Point.

Evaluates a trained policy using the fleet_safe_benchmark_v0 suite
inside Isaac Lab (with GPU physics).
"""
from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="FleetSafe H1 Evaluation")
    parser.add_argument("--task",       type=str, default="FleetSafe-H1-RoughLocomotion-v0")
    parser.add_argument("--checkpoint", type=str, required=True)
    parser.add_argument("--num_envs",   type=int, default=16)
    parser.add_argument("--n_episodes", type=int, default=10)
    parser.add_argument("--headless",   action="store_true", default=False)
    parser.add_argument("--output",     type=str, default="results/eval.json")
    args, extras = parser.parse_known_args()

    try:
        from isaaclab.app import AppLauncher
        app_launcher = AppLauncher({"headless": args.headless})
        simulation_app = app_launcher.app
    except ImportError as e:
        print(f"ERROR: isaaclab not available: {e}")
        sys.exit(1)

    import gymnasium as gym
    import fleet_safe_vla.envs.isaaclab.h1_locomotion_env  # noqa: F401

    env = gym.make(args.task, num_envs=args.num_envs)

    # Load policy
    from fleet_safe_vla.sim2real.export.onnx_export import validate_exported_policy
    policy_path = args.checkpoint
    if policy_path.endswith(".pt"):
        # Export to ONNX first
        from fleet_safe_vla.sim2real.export.onnx_export import export_fleet_policy
        onnx_path = policy_path.replace(".pt", ".onnx")
        export_fleet_policy(policy_path, onnx_path)
        policy_path = onnx_path

    # Run benchmark
    from fleet_safe_vla.eval.benchmark_suite.fleet_benchmark import FleetBenchmark
    bench = FleetBenchmark(policy=policy_path, n_episodes=args.n_episodes)

    def env_factory(scenario):
        return gym.make(args.task, num_envs=1)

    report = bench.run(output_path=args.output, verbose=True)

    env.close()
    simulation_app.close()


if __name__ == "__main__":
    main()
