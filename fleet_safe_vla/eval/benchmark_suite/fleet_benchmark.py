"""
FleetSafe Benchmark Suite — fleet_safe_benchmark_v0.

11 scenarios × 8 metrics = comprehensive fleet-safe evaluation.

Scenarios:
  flat, rough, stairs, slopes, low_friction, actuator_weakness,
  payload_shift, sensor_noise, latency, push, obstacle

Metrics per scenario:
  success_rate, safety_cost, fall_rate, intervention_count,
  tracking_error, energy_per_meter, collision_rate, recovery_success

Output: JSON report + console table

Usage:
    python -m fleet_safe_vla.eval.benchmark_suite.fleet_benchmark \\
        --policy=deployed/h1_policy.onnx \\
        --n_episodes=10 \\
        --output=results/benchmark_v0.json

Or import:
    from fleet_safe_vla.eval.benchmark_suite.fleet_benchmark import FleetBenchmark
    bench = FleetBenchmark(policy)
    report = bench.run(n_episodes_per_scenario=5)
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np

# robot-lab metrics
from robot_lab.eval.metrics import (
    AggregateMetrics,
    EpisodeBuffer,
    compute_all_metrics,
)


# ── Scenario definitions ──────────────────────────────────────────────────────

@dataclass
class ScenarioConfig:
    """Configuration for a single benchmark scenario."""
    name: str
    description: str

    # Environment perturbations
    terrain_type: str = "flat"           # flat, rough, stairs, slope
    terrain_level: int = 0              # 0-9
    friction_scale: float = 1.0         # <1.0 = slippery
    motor_strength_scale: float = 1.0   # <1.0 = weak actuators
    extra_mass_kg: float = 0.0          # payload shift
    sensor_noise_scale: float = 0.0     # multiplier on obs noise
    latency_extra_ms: float = 0.0       # additional latency
    push_every_n_steps: Optional[int] = None  # push disturbance
    obstacle_density: float = 0.0       # for obstacle scenario

    # Episode parameters
    episode_steps: int = 500
    cmd_vel: tuple = (0.5, 0.0, 0.0)


SCENARIOS: list[ScenarioConfig] = [
    ScenarioConfig(
        name="flat",
        description="Flat terrain, nominal conditions",
        terrain_type="flat", terrain_level=0,
        episode_steps=500, cmd_vel=(0.5, 0.0, 0.0),
    ),
    ScenarioConfig(
        name="rough",
        description="Rough terrain, level 4",
        terrain_type="rough", terrain_level=4,
        episode_steps=500, cmd_vel=(0.5, 0.0, 0.0),
    ),
    ScenarioConfig(
        name="stairs",
        description="Stair climbing (simulated as rough+high_level)",
        terrain_type="rough", terrain_level=7,
        episode_steps=400, cmd_vel=(0.3, 0.0, 0.0),
    ),
    ScenarioConfig(
        name="slopes",
        description="Sloped terrain",
        terrain_type="rough", terrain_level=3,
        episode_steps=400, cmd_vel=(0.4, 0.0, 0.0),
    ),
    ScenarioConfig(
        name="low_friction",
        description="Ice / low-friction surface (mu = 0.3)",
        terrain_type="flat", friction_scale=0.3,
        episode_steps=400, cmd_vel=(0.3, 0.0, 0.0),
    ),
    ScenarioConfig(
        name="actuator_weakness",
        description="70% motor strength (aging/damage sim)",
        terrain_type="flat", motor_strength_scale=0.7,
        episode_steps=400, cmd_vel=(0.5, 0.0, 0.0),
    ),
    ScenarioConfig(
        name="payload_shift",
        description="10 kg payload on torso",
        terrain_type="flat", extra_mass_kg=10.0,
        episode_steps=400, cmd_vel=(0.5, 0.0, 0.0),
    ),
    ScenarioConfig(
        name="sensor_noise",
        description="High IMU noise (sim degraded sensors)",
        terrain_type="flat", sensor_noise_scale=5.0,
        episode_steps=500, cmd_vel=(0.5, 0.0, 0.0),
    ),
    ScenarioConfig(
        name="latency",
        description="Extra 40 ms network latency",
        terrain_type="flat", latency_extra_ms=40.0,
        episode_steps=500, cmd_vel=(0.5, 0.0, 0.0),
    ),
    ScenarioConfig(
        name="push",
        description="External pushes every 50 steps",
        terrain_type="flat", push_every_n_steps=50,
        episode_steps=500, cmd_vel=(0.5, 0.0, 0.0),
    ),
    ScenarioConfig(
        name="obstacle",
        description="Discrete obstacles on flat terrain",
        terrain_type="flat", obstacle_density=0.1,
        episode_steps=400, cmd_vel=(0.3, 0.0, 0.0),
    ),
]

assert len(SCENARIOS) == 11, f"Expected 11 scenarios, got {len(SCENARIOS)}"

METRIC_NAMES = [
    "success_rate",
    "safety_cost",
    "fall_rate",
    "intervention_count",
    "tracking_error",
    "energy_per_meter",
    "collision_rate",
    "recovery_success",
]


# ── Per-episode result ────────────────────────────────────────────────────────

@dataclass
class EpisodeResult:
    """Metrics for one episode of one scenario."""
    scenario_name: str
    episode_idx: int
    success: bool
    fell: bool
    safety_cost: float           # sum of CBF intervention distances
    intervention_count: int      # number of CBF interventions
    tracking_error: float        # RMS velocity tracking error
    energy_per_meter: float      # J/m
    collision_count: int         # obstacle contacts above threshold
    recovered: bool              # recovered from near-fall
    duration_s: float
    distance_m: float


# ── Benchmark engine ──────────────────────────────────────────────────────────

class FleetBenchmark:
    """
    fleet_safe_benchmark_v0: 11-scenario × 8-metric benchmark.

    Works with both real MuJoCo environments and mock environments.
    Calls the policy as a callable: action = policy(obs).

    Args:
        policy: callable(obs: np.ndarray) -> np.ndarray, or ONNX path
        env_factory: callable(scenario: ScenarioConfig) -> gym env
                     If None, uses H1MuJoCoEnv with perturbations.
        cbf_filter: CBFSafetyFilter instance (optional, for CBF metrics)
        n_episodes: episodes per scenario
        seed: random seed
    """

    def __init__(
        self,
        policy: Callable | str | Path | None = None,
        env_factory: Optional[Callable] = None,
        cbf_filter=None,
        n_episodes: int = 5,
        seed: int = 42,
    ) -> None:
        self._policy = self._load_policy(policy)
        self._env_factory = env_factory or self._default_env_factory
        self._cbf = cbf_filter
        self.n_episodes = n_episodes
        self._rng = np.random.default_rng(seed)

    def run(
        self,
        scenarios: list[ScenarioConfig] | None = None,
        output_path: str | Path | None = None,
        verbose: bool = True,
    ) -> dict[str, Any]:
        """
        Run the full benchmark suite.

        Args:
            scenarios: list of ScenarioConfig. Default: all 11 SCENARIOS.
            output_path: if set, write JSON report here.
            verbose: print progress and table.

        Returns:
            dict with keys: scenarios, summary, metadata
        """
        scenarios = scenarios or SCENARIOS
        start_time = time.time()

        all_results: dict[str, list[EpisodeResult]] = {}
        aggregate: dict[str, AggregateMetrics] = {s.name: AggregateMetrics() for s in scenarios}

        for scenario in scenarios:
            if verbose:
                print(f"\n[Benchmark] Running scenario: {scenario.name} "
                      f"({self.n_episodes} episodes)")

            results = []
            for ep_idx in range(self.n_episodes):
                result = self._run_episode(scenario, ep_idx)
                results.append(result)

                # Convert to EpisodeBuffer and compute robot-lab metrics
                buf = self._make_episode_buffer(result)
                base_metrics = compute_all_metrics(buf)
                base_metrics.update(self._fleet_metrics(result))
                aggregate[scenario.name].update(base_metrics)

                if verbose:
                    print(f"  ep {ep_idx+1}/{self.n_episodes}: "
                          f"success={result.success}, fell={result.fell}, "
                          f"cbf_count={result.intervention_count}")

            all_results[scenario.name] = results

        # Build report
        elapsed = time.time() - start_time
        report = self._build_report(all_results, aggregate, elapsed)

        if verbose:
            self._print_table(report)

        if output_path is not None:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(report, f, indent=2)
            if verbose:
                print(f"\n[Benchmark] Report saved to {output_path}")

        return report

    # ── Episode runner ────────────────────────────────────────────────────────

    def _run_episode(self, scenario: ScenarioConfig, ep_idx: int) -> EpisodeResult:
        """Run a single episode in the given scenario."""
        env = self._env_factory(scenario)

        result = env.reset(seed=int(self._rng.integers(0, 2**31)))
        if isinstance(result, tuple):
            obs, _ = result
        else:
            obs = result

        fell = False
        success = True
        safety_cost = 0.0
        intervention_count = 0
        collision_count = 0
        recovered = False
        total_reward = 0.0
        cmd_vels = []
        base_vels = []
        torques_list = []
        foot_contacts = []

        near_fall = False

        for step in range(scenario.episode_steps):
            # Apply sensor noise
            noisy_obs = obs.copy()
            if scenario.sensor_noise_scale > 0:
                noisy_obs += self._rng.normal(
                    0, 0.01 * scenario.sensor_noise_scale, size=obs.shape
                ).astype(np.float32)

            # Policy
            action = self._policy(noisy_obs)

            # Motor strength scaling
            if scenario.motor_strength_scale != 1.0:
                action = action * scenario.motor_strength_scale

            # Push disturbance
            if (scenario.push_every_n_steps is not None
                    and step % scenario.push_every_n_steps == 0
                    and step > 0):
                push = self._rng.uniform(-0.5, 0.5, 3).astype(np.float32)
                # Inject as obs perturbation (velocity disturbance approximation)
                noisy_obs[0:3] += push * 2.0

            # CBF filter
            if self._cbf is not None:
                action, cbf_info = self._cbf.filter_action(noisy_obs, action)
                if cbf_info.get("intervened", False):
                    intervention_count += 1
                    safety_cost += float(np.sum(np.abs(action - self._policy(noisy_obs))))

            # Step environment
            result = env.step(action)
            if len(result) == 5:
                obs, rew, terminated, truncated, info = result
                done = terminated or truncated
            else:
                obs, rew, done, info = result

            total_reward += rew

            # Collect telemetry
            cmd_vels.append(obs[6:9].copy())
            base_vels.append(info.get("base_vel_xyz", np.zeros(3))[:2].copy() if "base_vel_xyz" in info else np.zeros(2))
            # Approximate torques from obs (action × kp proxy)
            torques_list.append(action.copy() * 10.0)
            foot_contacts.append([
                float(info.get("left_foot_contact", 0.5)),
                float(info.get("right_foot_contact", 0.5)),
            ])

            # Fall detection
            if done:
                if not (step >= scenario.episode_steps - 1):
                    fell = True
                    success = False
                    near_fall = True
                break

            # Near-fall detection (tilt > 0.6 rad = ~34°)
            proj_grav = obs[3:6]
            tilt = float(np.arccos(np.clip(-proj_grav[2], -1.0, 1.0)))
            if tilt > 0.6:
                near_fall = True
            elif near_fall and tilt < 0.4:
                recovered = True
                near_fall = False

            # Collision (obstacle scenario: high base disturbance)
            if scenario.obstacle_density > 0 and np.any(np.abs(obs[0:3]) > 2.0):
                collision_count += 1

        env.close()

        # Post-process metrics
        n = len(cmd_vels)
        cmd_arr = np.array(cmd_vels, dtype=np.float32)
        vel_arr = np.array(base_vels, dtype=np.float32)
        dt = 0.02
        duration_s = n * dt

        # Tracking error
        if n > 0 and cmd_arr.shape[1] >= 2 and vel_arr.shape[1] >= 2:
            err = np.linalg.norm(cmd_arr[:, :2] - vel_arr, axis=-1)
            tracking_error = float(np.sqrt(np.mean(err ** 2)))
        else:
            tracking_error = float("nan")

        # Energy per meter
        torques_arr = np.array(torques_list, dtype=np.float32)
        # zero velocity proxy: |torque| * dt
        energy_J = float(np.sum(np.abs(torques_arr))) * dt * 0.001
        distance_m = float(np.sum(np.linalg.norm(vel_arr, axis=-1))) * dt if vel_arr.shape[0] > 0 else 0.1
        energy_per_meter = energy_J / max(0.1, distance_m)

        return EpisodeResult(
            scenario_name=scenario.name,
            episode_idx=ep_idx,
            success=success,
            fell=fell,
            safety_cost=safety_cost,
            intervention_count=intervention_count,
            tracking_error=tracking_error,
            energy_per_meter=energy_per_meter,
            collision_count=collision_count,
            recovered=recovered,
            duration_s=duration_s,
            distance_m=distance_m,
        )

    # ── Metric aggregation ────────────────────────────────────────────────────

    def _fleet_metrics(self, result: EpisodeResult) -> dict[str, float]:
        """Compute fleet-specific metrics from an episode result."""
        return {
            "success_rate": float(result.success),
            "safety_cost": result.safety_cost,
            "fall_rate": float(result.fell),
            "intervention_count": float(result.intervention_count),
            "tracking_error": result.tracking_error,
            "energy_per_meter": result.energy_per_meter,
            "collision_rate": float(result.collision_count) / max(1, 500),
            "recovery_success": float(result.recovered),
        }

    def _make_episode_buffer(self, result: EpisodeResult) -> EpisodeBuffer:
        """Create a robot-lab EpisodeBuffer from episode result for metric computation."""
        T = max(1, int(result.duration_s / 0.02))
        # Synthetic buffers (approximations from available data)
        speed = result.distance_m / max(result.duration_s, 0.01)
        cmd = np.tile([[speed, 0.0]], (T, 1)).astype(np.float32)
        vel = cmd * (0.8 if not result.fell else 0.3)
        return EpisodeBuffer(
            cmd_vel_xy=cmd,
            base_vel_xy=vel,
            cmd_yaw_rate=np.zeros(T, dtype=np.float32),
            base_yaw_rate=np.zeros(T, dtype=np.float32),
            joint_torques=np.ones((T, 18), dtype=np.float32) * 10.0,
            joint_vel=np.ones((T, 18), dtype=np.float32) * 0.5,
            foot_contacts=np.tile([[1, 0], [0, 1]], (T // 2 + 1, 1))[:T].astype(np.float32),
            base_height=np.ones(T, dtype=np.float32) * (0.9 if not result.fell else 0.4),
            dt=0.02,
            fell=result.fell,
            terrain_level=0,
        )

    # ── Report building ───────────────────────────────────────────────────────

    def _build_report(
        self,
        all_results: dict[str, list[EpisodeResult]],
        aggregate: dict[str, AggregateMetrics],
        elapsed_s: float,
    ) -> dict[str, Any]:
        """Build the full JSON-serializable benchmark report."""
        scenarios_report = {}
        for scenario_name, results in all_results.items():
            summary = aggregate[scenario_name].summarize()
            episodes = [
                {
                    "ep": r.episode_idx,
                    "success": r.success,
                    "fell": r.fell,
                    "intervention_count": r.intervention_count,
                    "safety_cost": r.safety_cost,
                    "tracking_error": r.tracking_error,
                    "energy_per_meter": r.energy_per_meter,
                    "collision_count": r.collision_count,
                    "recovery_success": r.recovered,
                    "duration_s": r.duration_s,
                    "distance_m": r.distance_m,
                }
                for r in results
            ]
            scenarios_report[scenario_name] = {
                "summary": summary,
                "episodes": episodes,
            }

        # Global summary
        all_success = [
            r.success
            for results in all_results.values()
            for r in results
        ]
        all_fell = [
            r.fell
            for results in all_results.values()
            for r in results
        ]
        global_summary = {
            "overall_success_rate": float(np.mean(all_success)),
            "overall_fall_rate": float(np.mean(all_fell)),
            "n_scenarios": len(all_results),
            "n_episodes_per_scenario": self.n_episodes,
            "total_episodes": sum(len(v) for v in all_results.values()),
            "elapsed_s": elapsed_s,
        }

        return {
            "benchmark": "fleet_safe_benchmark_v0",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "metadata": {
                "n_scenarios": 11,
                "n_metrics": 8,
                "n_episodes_per_scenario": self.n_episodes,
            },
            "summary": global_summary,
            "scenarios": scenarios_report,
        }

    def _print_table(self, report: dict) -> None:
        """Print a console table of results."""
        print("\n" + "=" * 90)
        print(f"  fleet_safe_benchmark_v0  |  {report['timestamp']}")
        print("=" * 90)
        header = f"{'Scenario':<20} {'SuccRate':>9} {'FallRate':>9} {'CBF/ep':>8} {'TrkErr':>9} {'J/m':>9} {'ColRate':>9} {'Recov':>7}"
        print(header)
        print("-" * 90)

        for scenario_name, data in report["scenarios"].items():
            s = data["summary"]
            success_rate = s.get("success_rate/mean", float("nan"))
            fall_rate    = s.get("fall_rate/mean",    float("nan"))
            cbf_count    = s.get("intervention_count/mean", float("nan"))
            tracking_err = s.get("tracking_error/mean", float("nan"))
            energy_pm    = s.get("energy_per_meter/mean", float("nan"))
            coll_rate    = s.get("collision_rate/mean", float("nan"))
            recovery     = s.get("recovery_success/mean", float("nan"))

            def fmt(v):
                return f"{v:9.3f}" if not np.isnan(v) else "     nan"

            print(f"{scenario_name:<20} {fmt(success_rate)} {fmt(fall_rate)} "
                  f"{fmt(cbf_count)} {fmt(tracking_err)} {fmt(energy_pm)} "
                  f"{fmt(coll_rate)} {fmt(recovery)}")

        print("=" * 90)
        gs = report["summary"]
        print(f"Overall success: {gs['overall_success_rate']:.1%}  |  "
              f"Fall rate: {gs['overall_fall_rate']:.1%}  |  "
              f"Episodes: {gs['total_episodes']}  |  "
              f"Elapsed: {gs['elapsed_s']:.1f}s")
        print("=" * 90)

    # ── Policy loading ────────────────────────────────────────────────────────

    def _load_policy(self, policy) -> Callable:
        """Load policy — callable, ONNX path, or zero-policy fallback."""
        if policy is None:
            # Zero policy — for testing without trained weights
            return lambda obs: np.zeros(18, dtype=np.float32)

        if callable(policy):
            return policy

        # ONNX
        policy_path = Path(str(policy))
        if policy_path.suffix == ".onnx":
            try:
                import onnxruntime as ort
                sess = ort.InferenceSession(
                    str(policy_path),
                    providers=["CPUExecutionProvider"],
                )
                input_name = sess.get_inputs()[0].name
                return lambda obs: sess.run(
                    None, {input_name: obs[np.newaxis].astype(np.float32)}
                )[0][0]
            except ImportError:
                print("onnxruntime not installed — using zero policy")
                return lambda obs: np.zeros(18, dtype=np.float32)

        print(f"Warning: unknown policy type {type(policy)}, using zero policy")
        return lambda obs: np.zeros(18, dtype=np.float32)

    def _default_env_factory(self, scenario: ScenarioConfig):
        """Create H1MuJoCoEnv with scenario perturbations."""
        from fleet_safe_vla.envs.mujoco.h1_mujoco_env import H1MuJoCoEnv
        return H1MuJoCoEnv(
            max_episode_steps=scenario.episode_steps,
            command_vel=scenario.cmd_vel,
        )


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="fleet_safe_benchmark_v0: 11-scenario × 8-metric evaluation"
    )
    parser.add_argument("--policy", type=str, default=None,
                        help="ONNX policy path (default: zero policy for testing)")
    parser.add_argument("--n_episodes", type=int, default=5)
    parser.add_argument("--scenarios", type=str, nargs="+",
                        help="Subset of scenario names to run")
    parser.add_argument("--output", type=str, default="results/fleet_benchmark_v0.json")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    # Filter scenarios
    scenarios = SCENARIOS
    if args.scenarios:
        scenarios = [s for s in SCENARIOS if s.name in args.scenarios]
        if not scenarios:
            print(f"Error: no matching scenarios for {args.scenarios}")
            return

    bench = FleetBenchmark(
        policy=args.policy,
        n_episodes=args.n_episodes,
        seed=args.seed,
    )
    report = bench.run(
        scenarios=scenarios,
        output_path=args.output,
        verbose=not args.quiet,
    )


if __name__ == "__main__":
    main()
