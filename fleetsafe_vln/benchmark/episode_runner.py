"""Episode runner — run one FleetSafe-VLN episode from a task YAML.

CLI usage:
    python -m fleetsafe_vln.benchmark.episode_runner \\
        --platform mock \\
        --task tasks/hospital_corridor.yaml \\
        --model vint \\
        --safety cbf_qp \\
        --log-dir runs/test_episode

All platforms fail gracefully — if Isaac/Gazebo/ROS2 are unavailable the
runner prints a clear error and exits 1 without a traceback storm.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fleetsafe_vln.benchmark.metrics import EpisodeResult, compute_certificate_validity_rate
from fleetsafe_vln.benchmark.task_schema import TaskConfig, load_task
from fleetsafe_vln.safety.cbf_qp_shield import CBFQPShield
from fleetsafe_vln.safety.certificate_logger import ExtendedCertificateLogger
from fleetsafe_vln.safety.human_distance_monitor import HumanDistanceMonitor
from fleetsafe_vln.safety.risk_map import RiskMap
from fleetsafe_vln.simulators.base import SimulatorObs, make_simulator
from fleetsafe_vln.multimodal.intent_router import IntentRouter


class EpisodeRunner:
    """Run one episode and save all artifacts to log_dir."""

    def __init__(
        self,
        task: TaskConfig,
        platform: str = "mock",
        model: str = "mock",
        safety: str = "cbf_qp",
        log_dir: Optional[str] = None,
        dashboard: bool = False,
        seed: int = 0,
    ):
        self._task = task
        self._platform = platform
        self._model = model
        self._safety = safety
        self._dashboard = dashboard
        self._seed = seed
        self._run_id = str(uuid.uuid4())[:8]

        if log_dir is None:
            ts = time.strftime("%Y%m%d_%H%M%S")
            log_dir = f"runs/{task.task_id}_{platform}_{model}_{ts}"
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)

    def run(self) -> EpisodeResult:
        print(f"[episode_runner] task={self._task.task_id} platform={self._platform} "
              f"model={self._model} safety={self._safety}")
        print(f"[episode_runner] log_dir={self._log_dir}")

        self._save_run_config()

        try:
            sim = make_simulator(self._platform)
        except ImportError as e:
            print(f"[episode_runner] ❌ Platform '{self._platform}' not available: {e}")
            sys.exit(1)

        log_only = self._safety == "log_only"
        no_safety = self._safety == "none"

        shield = CBFQPShield(
            d_safe=self._task.safety.d_safe_m,
            estop_dist=self._task.safety.estop_dist_m,
            alpha=self._task.safety.cbf_alpha,
            model_name=self._model,
        )

        try:
            backbone_router = self._make_backbone()
        except ImportError as e:
            print(f"[episode_runner] ⚠️  Backbone '{self._model}' unavailable ({e}), using mock.")
            backbone_router = None

        human_monitor = HumanDistanceMonitor(
            min_safe_m=self._task.safety.min_human_distance_m,
        )
        risk_map = RiskMap()
        intent_router = IntentRouter()
        normalized_goal = intent_router.from_task(self._task.instruction)

        cert_path = self._log_dir / "safety_certificates.jsonl"
        traj_path = self._log_dir / "trajectory.csv"

        # ── Episode loop ──────────────────────────────────────────────────────
        obs = sim.reset(self._task)
        t_start = time.time()

        path_length = 0.0
        prev_xy = (obs.robot_pose[0], obs.robot_pose[1])

        cbf_intervention_count = 0
        cbf_magnitudes: List[float] = []
        invalid_cert_count = 0
        total_certs = 0
        collision_count = 0
        inference_latencies: List[float] = []

        traj_rows: List[Dict] = []

        with ExtendedCertificateLogger(cert_path) as cert_logger:
            for step in range(self._task.max_steps):
                # Nominal action
                t_inf = time.perf_counter()
                u_nom = self._get_nominal_action(backbone_router, normalized_goal, obs)
                inference_ms = (time.perf_counter() - t_inf) * 1000
                inference_latencies.append(inference_ms)

                # CBF filter
                obs_dists = [obs.min_obstacle_dist()] if obs.obstacle_positions else [math.inf]
                human_dists = [
                    math.sqrt((obs.robot_pose[0] - hx) ** 2 + (obs.robot_pose[1] - hy) ** 2)
                    for hx, hy in obs.human_positions
                ] if obs.human_positions else []

                cert = shield.filter(
                    u_nom=u_nom,
                    obstacle_dists=obs_dists,
                    robot_pose=obs.robot_pose,
                    human_dists=human_dists if human_dists else None,
                )
                # log_only: record certificate but do not modify the action
                # none: pass nominal action through without any safety check
                if no_safety:
                    u_safe = list(u_nom)
                    cert.cbf_active = False
                elif log_only:
                    u_safe = list(u_nom)   # nominal action sent to sim
                else:
                    u_safe = cert.u_safe   # filtered action sent to sim

                cert_logger.append(cert)
                total_certs += 1
                if not cert.certificate_valid:
                    invalid_cert_count += 1
                if cert.cbf_active:
                    cbf_intervention_count += 1
                    cbf_magnitudes.append(cert.intervention_magnitude)

                # Human monitor
                human_monitor.update(obs.human_positions, obs.robot_pose[:2])

                # Risk map
                risk_map.update(
                    robot_xy=obs.robot_pose[:2],
                    cbf_active=cert.cbf_active,
                    near_human=bool(human_dists and min(human_dists) < 1.2),
                )

                # Path length
                cur_xy = (obs.robot_pose[0], obs.robot_pose[1])
                path_length += math.sqrt(
                    (cur_xy[0] - prev_xy[0]) ** 2 + (cur_xy[1] - prev_xy[1]) ** 2
                )
                prev_xy = cur_xy

                # Trajectory row
                traj_rows.append({
                    "step": step,
                    "t": cert.t,
                    "x": obs.robot_pose[0],
                    "y": obs.robot_pose[1],
                    "yaw": obs.robot_pose[2],
                    "vx_nom": u_nom[0],
                    "wz_nom": u_nom[1] if len(u_nom) > 1 else 0.0,
                    "vx_safe": u_safe[0],
                    "wz_safe": u_safe[1] if len(u_safe) > 1 else 0.0,
                    "cbf_active": cert.cbf_active,
                    "h": cert.barrier_value_h,
                    "min_obs_m": cert.min_obstacle_distance_m,
                })

                # Collision detection
                if obs.collision:
                    collision_count += 1

                # Step simulation
                obs = sim.step(u_safe)

                if obs.goal_reached:
                    print(f"[episode_runner] ✓ Goal reached at step {step+1}")
                    break

        sim.close()
        t_total = time.time() - t_start

        # ── Compute final metrics ─────────────────────────────────────────────
        final_obs = obs
        goal = self._task.goal_xy
        nav_err = math.sqrt(
            (final_obs.robot_pose[0] - goal[0]) ** 2
            + (final_obs.robot_pose[1] - goal[1]) ** 2
        )
        success = bool(final_obs.goal_reached)

        spl = 0.0
        if success and self._task.optimal_path_m > 0:
            spl = self._task.optimal_path_m / max(path_length, self._task.optimal_path_m)

        cert_validity_rate, _, _ = compute_certificate_validity_rate(cert_path)

        result = EpisodeResult(
            task_id=self._task.task_id,
            scene=self._task.scene,
            platform=self._platform,
            model=self._model,
            safety=self._safety,
            seed=self._seed,
            run_id=self._run_id,
            log_dir=str(self._log_dir),
            success=success,
            navigation_error_m=nav_err,
            path_length_m=path_length,
            optimal_path_m=self._task.optimal_path_m,
            spl=spl,
            episode_steps=len(traj_rows),
            time_s=t_total,
            collision_count=collision_count,
            collision_rate=collision_count / max(1, len(traj_rows)),
            min_obstacle_distance_m=min(
                (r["min_obs_m"] for r in traj_rows), default=math.inf
            ),
            min_human_distance_m=human_monitor.state.min_distance_m,
            near_miss_count=human_monitor.state.near_miss_count,
            cbf_intervention_count=cbf_intervention_count,
            cbf_intervention_rate=cbf_intervention_count / max(1, len(traj_rows)),
            cbf_intervention_magnitude_mean=(
                sum(cbf_magnitudes) / len(cbf_magnitudes) if cbf_magnitudes else 0.0
            ),
            unsafe_nominal_action_count=cbf_intervention_count,
            unsafe_nominal_action_rate=cbf_intervention_count / max(1, len(traj_rows)),
            certificate_validity_rate=cert_validity_rate,
            invalid_certificate_count=invalid_cert_count,
            social_margin_violation_count=human_monitor.state.violation_count,
            inference_latency_ms_mean=(
                sum(inference_latencies) / len(inference_latencies)
                if inference_latencies else 0.0
            ),
        )

        self._save_trajectory(traj_path, traj_rows)
        result.save(self._log_dir / "metrics.json")
        self._save_replay(result, traj_rows)

        print(f"[episode_runner] success={success}  spl={spl:.3f}  "
              f"cbf_interventions={cbf_intervention_count}  "
              f"cert_validity={cert_validity_rate:.3f}")
        print(f"[episode_runner] Artifacts saved to {self._log_dir}")

        return result

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _make_backbone(self):
        from fleetsafe_vln.backbones.base import make_backbone
        return make_backbone(
            self._model,
            max_vx=self._task.robot.max_vx,
            max_wz=self._task.robot.max_wz,
        )

    def _get_nominal_action(self, backbone, goal, obs: SimulatorObs) -> List[float]:
        if backbone is None:
            return [self._task.robot.max_vx * 0.5, 0.0]
        try:
            from fleet_safe_vla.vln.instruction_schema import GroundedGoal, ActionType, GoalType
            grounded = GroundedGoal(
                label=goal.goal_label,
                confidence=goal.confidence,
                goal_type=GoalType.SEMANTIC_REGION.value,
                action_type=ActionType.NAVIGATE.value,
                nominal_vx=min(goal.nominal_vx, self._task.robot.max_vx),
                nominal_wz=goal.nominal_wz,
            )
            action = backbone.run_nominal_policy(grounded, camera_context=obs.rgb)
            return action.as_list()
        except Exception:
            return [self._task.robot.max_vx * 0.5, 0.0]

    def _save_run_config(self) -> None:
        config = {
            "run_id": self._run_id,
            "task_id": self._task.task_id,
            "platform": self._platform,
            "model": self._model,
            "safety": self._safety,
            "seed": self._seed,
            "task": self._task.to_dict(),
        }
        (self._log_dir / "run_config.json").write_text(
            json.dumps(config, indent=2), encoding="utf-8"
        )

    def _save_trajectory(self, path: Path, rows: List[Dict]) -> None:
        if not rows:
            return
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    def _save_replay(self, result: EpisodeResult, traj_rows: List[Dict]) -> None:
        replay = {
            "run_id": self._run_id,
            "task_id": self._task.task_id,
            "platform": self._platform,
            "model": self._model,
            "success": result.success,
            "trajectory": traj_rows,
            "summary": result.to_dict(),
        }
        (self._log_dir / "dashboard_replay.json").write_text(
            json.dumps(replay, indent=2), encoding="utf-8"
        )


# ── CLI entry point ────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run one FleetSafe-VLN episode",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--task", required=True, help="Path to task YAML file")
    p.add_argument("--platform", default="mock",
                   choices=["mock", "isaac", "gazebo", "real_robot"],
                   help="Simulator platform")
    p.add_argument("--model", default="mock",
                   choices=["gnm", "vint", "nomad", "mock", "auto"],
                   help="Navigation backbone model")
    p.add_argument("--safety", default="cbf_qp",
                   choices=["cbf_qp", "log_only", "none"],
                   help="Safety layer: cbf_qp=full filter, log_only=log without modifying action, none=passthrough")
    p.add_argument("--log-dir", default=None, help="Output directory for artifacts")
    p.add_argument("--dashboard", action="store_true", help="Enable dashboard websocket events")
    p.add_argument("--seed", type=int, default=0)
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        task = load_task(args.task)
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return 1
    except Exception as e:
        print(f"❌ Failed to load task: {e}")
        return 1

    runner = EpisodeRunner(
        task=task,
        platform=args.platform,
        model=args.model,
        safety=args.safety,
        log_dir=args.log_dir,
        dashboard=args.dashboard,
        seed=args.seed,
    )
    result = runner.run()
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
