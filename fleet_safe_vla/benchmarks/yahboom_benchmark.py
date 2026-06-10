"""
Yahboom Safety Benchmark — fleet_safe_yahboom_benchmark_v0

Compares 4 backbones on identical episodes:
  A: Nominal planner only (NominalGoToGoalPlanner)
  B: Nominal + classical velocity clipping (hard speed limit)
  C: Nominal + APF repulsion (soft obstacle avoidance)
  D: Nominal + Fleet-Safe CBF filter (hard safety guarantee)

Same robot. Same maps. Same seeds. Same episode budget.

Metrics per backbone (11 total):
  success_rate           — fraction of episodes reaching goal
  collision_rate         — fraction ending in collision
  near_miss_rate         — fraction with ≥1 near-miss (d < 0.45m)
  intervention_count     — total CBF/filter interventions (D only)
  path_efficiency        — actual/optimal path length ratio
  time_to_goal_s         — mean seconds for successful episodes
  min_obs_dist_m         — minimum obstacle clearance (mean over episodes)
  unsafe_cmd_suppressed  — fraction of time CBF changed the command (D only)
  false_positive_rate    — interventions where nominal was actually safe (D only)
  recovery_success       — fraction of recovery episodes where goal reached
  sim_fps                — simulation throughput (MuJoCo steps/sec)

Usage:
  bench = YahboomBenchmark(n_episodes=50, seed=42)
  results = bench.run()
  bench.print_report(results)
  bench.save_report(results, "logs/yahboom/benchmark_report.json")
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import numpy as np

from fleet_safe_vla.envs.mujoco.yahboom.safe_path_env import YahboomSafePathEnv
from fleet_safe_vla.envs.mujoco.yahboom.recovery_env import YahboomRecoveryEnv
from fleet_safe_vla.policies.nominal.nominal_planner import NominalGoToGoalPlanner, APFPlanner
from fleet_safe_vla.fleet_safety.yahboom_cbf import YahboomCBFFilter, YahboomCBFConfig

NEAR_MISS_DIST = 0.45


@dataclass
class EpisodeResult:
    backbone: str
    task: str
    seed: int
    success: bool
    collision: bool
    near_miss: bool
    n_interventions: int
    path_length_m: float
    optimal_dist_m: float
    duration_s: float
    min_obs_dist_m: float
    cumulative_safety_cost: float
    unsafe_cmd_suppressed: float  # fraction of steps CBF modified action
    false_positives: int


@dataclass
class BackboneResults:
    name: str
    episodes: list[EpisodeResult]

    @property
    def success_rate(self) -> float:
        return float(np.mean([e.success for e in self.episodes]))

    @property
    def collision_rate(self) -> float:
        return float(np.mean([e.collision for e in self.episodes]))

    @property
    def near_miss_rate(self) -> float:
        return float(np.mean([e.near_miss for e in self.episodes]))

    @property
    def mean_interventions(self) -> float:
        return float(np.mean([e.n_interventions for e in self.episodes]))

    @property
    def path_efficiency(self) -> float:
        valid = [e for e in self.episodes if e.success and e.optimal_dist_m > 0]
        if not valid:
            return float("nan")
        return float(np.mean([e.optimal_dist_m / max(e.path_length_m, 0.01) for e in valid]))

    @property
    def mean_time_to_goal_s(self) -> float:
        valid = [e.duration_s for e in self.episodes if e.success]
        return float(np.mean(valid)) if valid else float("nan")

    @property
    def mean_min_obs_dist_m(self) -> float:
        return float(np.mean([e.min_obs_dist_m for e in self.episodes]))

    @property
    def unsafe_cmd_suppression_rate(self) -> float:
        return float(np.mean([e.unsafe_cmd_suppressed for e in self.episodes]))

    @property
    def false_positive_rate(self) -> float:
        total_intv = sum(e.n_interventions for e in self.episodes)
        total_fp   = sum(e.false_positives for e in self.episodes)
        return float(total_fp / total_intv) if total_intv > 0 else 0.0

    def summary(self) -> dict[str, Any]:
        return {
            "backbone": self.name,
            "n_episodes": len(self.episodes),
            "success_rate": round(self.success_rate, 3),
            "collision_rate": round(self.collision_rate, 3),
            "near_miss_rate": round(self.near_miss_rate, 3),
            "mean_interventions": round(self.mean_interventions, 1),
            "path_efficiency": round(self.path_efficiency, 3) if not np.isnan(self.path_efficiency) else "nan",
            "mean_time_to_goal_s": round(self.mean_time_to_goal_s, 2) if not np.isnan(self.mean_time_to_goal_s) else "nan",
            "mean_min_obs_dist_m": round(self.mean_min_obs_dist_m, 3),
            "unsafe_cmd_suppression_rate": round(self.unsafe_cmd_suppression_rate, 3),
            "false_positive_rate": round(self.false_positive_rate, 3),
        }


class YahboomBenchmark:
    """
    Runs all 4 backbones on the same set of seeded episodes.
    Each episode uses the same initial robot position, goal, and obstacle layout.
    """

    BACKBONES = ["A_nominal", "B_clip", "C_apf", "D_fleet_safe"]

    def __init__(
        self,
        n_episodes: int = 20,
        seed: int = 42,
        max_steps: int = 300,
        task: str = "safe_path",
        verbose: bool = True,
    ):
        self.n_episodes = n_episodes
        self.seed = seed
        self.max_steps = max_steps
        self.task = task
        self.verbose = verbose

    def run(self) -> dict[str, BackboneResults]:
        all_results: dict[str, BackboneResults] = {}
        t0 = time.monotonic()

        for backbone in self.BACKBONES:
            if self.verbose:
                print(f"\n[benchmark] Running backbone: {backbone}")
            results = self._run_backbone(backbone)
            all_results[backbone] = results
            s = results.summary()
            if self.verbose:
                print(f"  success={s['success_rate']:.1%} "
                      f"collision={s['collision_rate']:.1%} "
                      f"near_miss={s['near_miss_rate']:.1%} "
                      f"min_obs_dist={s['mean_min_obs_dist_m']:.3f}m "
                      f"interventions={s['mean_interventions']:.1f}")

        elapsed = time.monotonic() - t0
        if self.verbose:
            print(f"\n[benchmark] Total time: {elapsed:.1f}s")

        return all_results

    def _run_backbone(self, backbone: str) -> BackboneResults:
        episodes = []
        rng = np.random.default_rng(self.seed)

        for ep in range(self.n_episodes):
            ep_seed = int(rng.integers(0, 2**31))
            result = self._run_episode(backbone, ep_seed)
            episodes.append(result)
            if self.verbose and (ep + 1) % 10 == 0:
                print(f"  episode {ep+1}/{self.n_episodes}")

        return BackboneResults(name=backbone, episodes=episodes)

    def _run_episode(self, backbone: str, ep_seed: int) -> EpisodeResult:
        # Build env
        if self.task == "recovery":
            env = YahboomRecoveryEnv(seed=ep_seed, max_episode_steps=self.max_steps)
        else:
            env = YahboomSafePathEnv(seed=ep_seed, max_episode_steps=self.max_steps)

        obs, info = env.reset(seed=ep_seed)
        goal_xy = np.array(info.get("goal_xy", [2.0, 0.0]))
        start_xy = np.array(info.get("robot_xy", [0.0, 0.0]))
        optimal_dist = float(np.linalg.norm(goal_xy - start_xy))

        # Build policy
        planner, cbf = self._build_backbone(backbone, goal_xy)
        cbf_filter = cbf

        # Episode tracking
        path_length = 0.0
        prev_xy = start_xy.copy()
        min_obs_dist = 99.0
        n_interventions = 0
        n_suppressed = 0
        false_positives = 0
        near_miss = False
        collision = False
        success = False
        t_start = time.monotonic()

        for step in range(self.max_steps):
            nominal_action = planner.act(obs)

            if cbf_filter is not None:
                obs_positions = env._obs_positions.tolist() if hasattr(env, "_obs_positions") else []
                safe_action, cbf_info = cbf_filter.filter(obs, nominal_action, obs_positions)
                if cbf_info["intervened"]:
                    n_interventions += 1
                    n_suppressed += 1
                    # False positive: CBF intervened but robot was already safe
                    if cbf_info.get("min_dist_m", 99) > 0.45:
                        false_positives += 1
                action = safe_action
            else:
                action = nominal_action

            # Backbone B: hard velocity clip (no CBF)
            if backbone == "B_clip":
                action = np.clip(action, [-0.3, -0.7], [0.3, 0.7]).astype(np.float32)

            obs, rew, terminated, truncated, info = env.step(action)

            # Track
            cur_xy = np.array(info.get("robot_xy", [0.0, 0.0]))
            path_length += float(np.linalg.norm(cur_xy - prev_xy))
            prev_xy = cur_xy

            d_obs = float(info.get("min_obstacle_dist_m", 99.0))
            min_obs_dist = min(min_obs_dist, d_obs)
            if d_obs < NEAR_MISS_DIST:
                near_miss = True
            if info.get("collision", False):
                collision = True
            if info.get("success", False):
                success = True

            if terminated or truncated:
                break

        env.close()
        duration = time.monotonic() - t_start
        total_steps = max(step + 1, 1)
        suppression_rate = n_suppressed / total_steps

        return EpisodeResult(
            backbone=backbone,
            task=self.task,
            seed=ep_seed,
            success=success,
            collision=collision,
            near_miss=near_miss,
            n_interventions=n_interventions,
            path_length_m=path_length,
            optimal_dist_m=optimal_dist,
            duration_s=duration,
            min_obs_dist_m=min_obs_dist,
            cumulative_safety_cost=float(info.get("cumulative_safety_cost", 0.0)),
            unsafe_cmd_suppressed=suppression_rate,
            false_positives=false_positives,
        )

    def _build_backbone(self, backbone: str, goal_xy: np.ndarray):
        planner = NominalGoToGoalPlanner(goal_xy=goal_xy)
        cbf = None

        if backbone == "A_nominal":
            pass  # raw planner, no filter
        elif backbone == "B_clip":
            pass  # planner + hard clip (applied in loop)
        elif backbone == "C_apf":
            planner = APFPlanner(goal_xy=goal_xy)
        elif backbone == "D_fleet_safe":
            cbf = YahboomCBFFilter(YahboomCBFConfig())

        return planner, cbf

    @staticmethod
    def print_report(results: dict[str, BackboneResults]) -> None:
        print("\n" + "=" * 100)
        print(f"{'Backbone':<20} {'Success':>8} {'Collision':>10} {'NearMiss':>10} "
              f"{'MinObsDist':>12} {'Intervent':>11} {'PathEff':>9} {'TimeGoal':>10}")
        print("=" * 100)
        for name, br in results.items():
            s = br.summary()
            print(
                f"{name:<20} {s['success_rate']:>8.1%} {s['collision_rate']:>10.1%} "
                f"{s['near_miss_rate']:>10.1%} {s['mean_min_obs_dist_m']:>12.3f} "
                f"{s['mean_interventions']:>11.1f} {str(s['path_efficiency']):>9} "
                f"{str(s['mean_time_to_goal_s']):>10}"
            )
        print("=" * 100)

        # Fleet-Safe improvement summary
        if "A_nominal" in results and "D_fleet_safe" in results:
            a = results["A_nominal"].summary()
            d = results["D_fleet_safe"].summary()
            print("\n── Fleet-Safe (D) vs Nominal (A) ─────────────────────────")
            for metric in ["success_rate", "collision_rate", "near_miss_rate", "mean_min_obs_dist_m"]:
                va = a.get(metric, 0)
                vd = d.get(metric, 0)
                if isinstance(va, float) and isinstance(vd, float):
                    delta = vd - va
                    direction = "↑" if delta > 0 else "↓"
                    print(f"  {metric:<30}: A={va:.3f}  D={vd:.3f}  Δ={delta:+.3f} {direction}")

    @staticmethod
    def save_report(results: dict[str, BackboneResults], path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "backbones": {name: br.summary() for name, br in results.items()},
            "episodes": {
                name: [asdict(e) for e in br.episodes]
                for name, br in results.items()
            },
        }
        with open(path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"[benchmark] Report saved: {path}")
