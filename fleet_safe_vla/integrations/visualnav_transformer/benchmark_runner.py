"""
benchmark_runner.py — Episode runner for VisualNav + FleetSafe benchmark.

Executes the full benchmark matrix:
  - Any GNM / ViNT / NoMaD adapter (or wrapped with FleetSafe)
  - In a MuJoCo simulation backend (default: M3Pro MJCF, fallback: X3)
  - Over a configurable set of scenes, seeds, and start/goal pairs

Metric collection
-----------------
Per episode:
  success, collision, near_violation_count, min_obstacle_dist_m,
  intervention_count, time_to_goal_s, path_length_m, smoothness,
  stuck_count, recovery_success, step_latency_ms,
  raw_cmd_vel_log, safe_cmd_vel_log, delta_cmd_vel_log

Usage
-----
    runner = BenchmarkRunner(
        adapter         = gnm_adapter,          # loaded BaseVisualNavAdapter
        benchmark_cfg   = cfg,
        fleetsafe       = True,
    )
    results = runner.run_all()
    runner.save_results(Path("benchmarks/visualnav/results/run_001.json"))
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from fleet_safe_vla.integrations.visualnav_transformer.base_adapter import (
    BaseVisualNavAdapter,
    CmdVel,
)
from fleet_safe_vla.integrations.visualnav_transformer.fleetsafe_wrapper import (
    FleetSafeWrapper,
    FleetSafeStepResult,
)
from fleet_safe_vla.integrations.visualnav_transformer.isaac_obs_adapter import (
    IsaacCameraObsAdapter,
)

# ── Configuration dataclasses ─────────────────────────────────────────────────

@dataclass
class StartGoalPair:
    start_xy:  tuple[float, float]
    goal_xy:   tuple[float, float]
    label:     str = ""


@dataclass
class SceneConfig:
    name:             str
    obstacle_layout:  str = "none"     # "none" | "sparse" | "dense"
    n_obstacles:      int = 0
    arena_size_m:     float = 8.0


@dataclass
class BenchmarkConfig:
    scenes:          list[SceneConfig]
    start_goal_pairs: list[StartGoalPair]
    seeds:           list[int]
    max_steps:       int   = 500
    control_hz:      float = 4.0
    v_max:           float = 0.3
    vy_max:          float = 0.3     # holonomic (M3Pro); set 0 for X3
    w_max:           float = 0.7
    near_miss_dist_m: float = 0.45
    stuck_vel_thresh: float = 0.02
    stuck_min_steps:  int   = 10
    robot:           str   = "m3pro"   # "m3pro" | "x3"
    use_camera:      bool  = False      # False → synthetic checkerboard goal


# ── Episode result ─────────────────────────────────────────────────────────────

@dataclass
class EpisodeResult:
    # Identity
    model_name:       str   = ""
    fleetsafe:        bool  = False
    scene:            str   = ""
    seed:             int   = 0
    start_xy:         tuple = (0.0, 0.0)
    goal_xy:          tuple = (0.0, 0.0)

    # Primary metrics
    success:          bool  = False
    collision:        bool  = False
    near_violation_count: int   = 0
    min_obstacle_dist_m: float  = float("inf")
    intervention_count:  int   = 0
    time_to_goal_s:   float = 0.0
    path_length_m:    float = 0.0
    smoothness:       float = 0.0    # mean |Δcmd_vel| per step
    stuck_count:      int   = 0      # steps with near-zero velocity
    recovery_success: bool  = False

    # Latency
    step_latency_ms:  list[float] = field(default_factory=list)

    # Per-step command logs (serialisable)
    raw_cmd_log:      list[dict]  = field(default_factory=list)
    safe_cmd_log:     list[dict]  = field(default_factory=list)
    delta_cmd_log:    list[dict]  = field(default_factory=list)

    @property
    def mean_latency_ms(self) -> float:
        return float(np.mean(self.step_latency_ms)) if self.step_latency_ms else 0.0

    @property
    def fps(self) -> float:
        return 1000.0 / max(1e-6, self.mean_latency_ms)


# ── Runner ────────────────────────────────────────────────────────────────────

class BenchmarkRunner:
    """
    Runs the full benchmark matrix and collects metrics.

    Parameters
    ----------
    adapter       : Loaded BaseVisualNavAdapter (GNM / ViNT / NoMaD).
    benchmark_cfg : BenchmarkConfig specifying scenes, seeds, pairs.
    fleetsafe     : If True, wrap adapter with FleetSafeWrapper.
    results_dir   : Directory for JSON output files.
    """

    def __init__(
        self,
        adapter:       BaseVisualNavAdapter,
        benchmark_cfg: BenchmarkConfig,
        fleetsafe:     bool = False,
        results_dir:   Path = Path("benchmarks/visualnav/results"),
    ) -> None:
        if not adapter.is_loaded():
            raise RuntimeError(
                "Adapter checkpoint not loaded.  "
                "Call adapter.load_checkpoint() before BenchmarkRunner()."
            )
        self.adapter       = adapter
        self.cfg           = benchmark_cfg
        self.fleetsafe     = fleetsafe
        self.results_dir   = results_dir
        self._wrapper: FleetSafeWrapper | None = None

        if fleetsafe:
            self._wrapper = FleetSafeWrapper(
                adapter,
                v_max      = benchmark_cfg.v_max,
                vy_max     = benchmark_cfg.vy_max,
                w_max      = benchmark_cfg.w_max,
                control_hz = benchmark_cfg.control_hz,
            )

    # ── Public API ─────────────────────────────────────────────────────────────

    def run_all(self) -> list[EpisodeResult]:
        """Run every (scene × seed × start_goal) combination."""
        results = []
        total = (
            len(self.cfg.scenes)
            * len(self.cfg.seeds)
            * len(self.cfg.start_goal_pairs)
        )
        idx = 0
        for scene in self.cfg.scenes:
            for seed in self.cfg.seeds:
                for sg in self.cfg.start_goal_pairs:
                    idx += 1
                    print(
                        f"[{idx}/{total}] scene={scene.name}  seed={seed}  "
                        f"start={sg.start_xy} → goal={sg.goal_xy}  "
                        f"fleetsafe={self.fleetsafe}"
                    )
                    result = self._run_episode(scene, seed, sg)
                    results.append(result)
                    self._print_episode_summary(result)
        return results

    def save_results(self, path: Path, results: list[EpisodeResult]) -> None:
        """Save results list to a JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model":     self.adapter.model_name,
            "fleetsafe": self.fleetsafe,
            "timestamp": time.time(),
            "config":    {
                "v_max":    self.cfg.v_max,
                "w_max":    self.cfg.w_max,
                "robot":    self.cfg.robot,
                "seeds":    self.cfg.seeds,
            },
            "episodes":  [self._episode_to_dict(r) for r in results],
            "aggregate": self._aggregate(results),
        }
        path.write_text(json.dumps(payload, indent=2))
        print(f"Results saved → {path}")

    # ── Episode execution ──────────────────────────────────────────────────────

    def _run_episode(
        self,
        scene:  SceneConfig,
        seed:   int,
        sg:     StartGoalPair,
    ) -> EpisodeResult:
        """Run one episode and return metrics."""
        env, obs_adapter = self._make_env_and_camera(scene, seed, sg)
        if self._wrapper:
            self._wrapper.reset_stats()

        result = EpisodeResult(
            model_name = self.adapter.model_name,
            fleetsafe  = self.fleetsafe,
            scene      = scene.name,
            seed       = seed,
            start_xy   = sg.start_xy,
            goal_xy    = sg.goal_xy,
        )

        prev_xy         = np.array(sg.start_xy, dtype=np.float64)
        prev_cmd        = CmdVel(0.0, 0.0, 0.0)
        stuck_streak    = 0
        collision_dist  = 0.10   # robot chassis half-diagonal ≈ 0.15 m

        for step in range(self.cfg.max_steps):
            t_step = time.perf_counter()

            # ── Camera observation ────────────────────────────────────────────
            if self.cfg.use_camera:
                raw_rgb = self._render_camera(env)
                obs_adapter.push_frame(raw_rgb)
            else:
                # Synthetic frame for pipeline testing
                obs_adapter.push_frame(
                    IsaacCameraObsAdapter.make_random_obs(
                        *self.adapter.image_size if hasattr(self.adapter, "image_size")
                        else (85, 64),
                        seed=seed + step,
                    )
                )

            obs_imgs, goal_img = obs_adapter.get_context()
            preprocessed = self.adapter.preprocess_observation(obs_imgs, goal_img)

            # ── Obstacle positions (robot frame) ──────────────────────────────
            obs_positions = self._get_obstacle_positions(env, scene)

            # ── Inference ─────────────────────────────────────────────────────
            if self._wrapper:
                obs_vec  = self._get_obs_vec(env)
                step_res = self._wrapper.step(preprocessed, obs_vec, obs_positions)
                cmd      = step_res.safe_cmd_vel
                raw_cmd  = step_res.raw_cmd_vel
                result.intervention_count += int(step_res.intervened)
                if step_res.min_dist_m < result.min_obstacle_dist_m:
                    result.min_obstacle_dist_m = step_res.min_dist_m
                if step_res.min_dist_m < self.cfg.near_miss_dist_m:
                    result.near_violation_count += 1
                result.raw_cmd_log.append({"vx": raw_cmd.vx, "vy": raw_cmd.vy, "wz": raw_cmd.wz})
                result.safe_cmd_log.append({"vx": cmd.vx, "vy": cmd.vy, "wz": cmd.wz})
                result.delta_cmd_log.append({
                    "dvx": abs(cmd.vx - raw_cmd.vx),
                    "dvy": abs(cmd.vy - raw_cmd.vy),
                    "dwz": abs(cmd.wz - raw_cmd.wz),
                })
            else:
                action = self.adapter.predict_action(preprocessed)
                cmd    = self.adapter.action_to_cmd_vel(
                    action,
                    v_max=self.cfg.v_max,
                    vy_max=self.cfg.vy_max,
                    w_max=self.cfg.w_max,
                    control_hz=self.cfg.control_hz,
                )
                raw_cmd = cmd
                result.raw_cmd_log.append({"vx": cmd.vx, "vy": cmd.vy, "wz": cmd.wz})

                # Obstacle proximity without FleetSafe
                if obs_positions:
                    min_d = min(float(np.linalg.norm(p)) for p in obs_positions)
                    if min_d < result.min_obstacle_dist_m:
                        result.min_obstacle_dist_m = min_d
                    if min_d < self.cfg.near_miss_dist_m:
                        result.near_violation_count += 1

            # ── Apply action to env ───────────────────────────────────────────
            env_obs, _, terminated, truncated, info = env.step(
                np.array([cmd.vx, cmd.wz], dtype=np.float32)
                if self.cfg.robot == "x3"
                else np.array([cmd.vx, cmd.vy, cmd.wz], dtype=np.float32)
            )
            robot_xy = np.array(info.get("robot_xy", [0.0, 0.0]))

            # ── Metrics accumulation ──────────────────────────────────────────
            step_dist = float(np.linalg.norm(robot_xy - prev_xy))
            result.path_length_m += step_dist

            # Smoothness: |Δcmd_vel|
            cmd_arr      = cmd.as_array()
            prev_cmd_arr = prev_cmd.as_array()
            result.smoothness += float(np.linalg.norm(cmd_arr - prev_cmd_arr))

            speed = float(np.hypot(cmd.vx, cmd.vy))
            stuck_streak = stuck_streak + 1 if speed < self.cfg.stuck_vel_thresh else 0
            if stuck_streak >= self.cfg.stuck_min_steps:
                result.stuck_count += 1

            ms = (time.perf_counter() - t_step) * 1000.0
            result.step_latency_ms.append(ms)

            prev_xy  = robot_xy
            prev_cmd = cmd

            # ── Termination ───────────────────────────────────────────────────
            goal_dist = float(np.linalg.norm(robot_xy - np.array(sg.goal_xy)))
            if terminated or info.get("success", False) or goal_dist < 0.20:
                result.success      = True
                result.time_to_goal_s = step / self.cfg.control_hz
                break

            if info.get("collision", False) or (
                result.min_obstacle_dist_m < collision_dist
            ):
                result.collision = True
                break

        # Normalise smoothness
        n = max(1, len(result.step_latency_ms))
        result.smoothness /= n

        env.close()
        return result

    # ── Environment factory ────────────────────────────────────────────────────

    def _make_env_and_camera(
        self,
        scene: SceneConfig,
        seed:  int,
        sg:    StartGoalPair,
    ) -> tuple[Any, IsaacCameraObsAdapter]:
        """Instantiate the MuJoCo environment appropriate for the benchmark."""
        from fleet_safe_vla.envs.mujoco.yahboom.nav_env import YahboomNavEnv
        from fleet_safe_vla.envs.mujoco.yahboom.obstacle_env import YahboomObstacleEnv

        img_size = getattr(self.adapter, "image_size", (85, 64))
        ctx_size = getattr(self.adapter, "context_size", 5)

        if scene.obstacle_layout == "none":
            env = YahboomNavEnv(
                max_episode_steps=self.cfg.max_steps,
                control_hz=self.cfg.control_hz,
                seed=seed,
            )
        else:
            env = YahboomObstacleEnv(
                n_obstacles=scene.n_obstacles,
                max_episode_steps=self.cfg.max_steps,
                control_hz=self.cfg.control_hz,
                seed=seed,
            )

        env.reset(seed=seed)

        obs_adapter = IsaacCameraObsAdapter(
            image_size=img_size,
            context_size=ctx_size,
        )
        # Synthetic goal for pipeline testing
        obs_adapter.set_goal_image(
            IsaacCameraObsAdapter.make_checkerboard_goal(*img_size)
        )
        return env, obs_adapter

    def _render_camera(self, env: Any) -> np.ndarray:
        """
        Render the robot's egocentric forward-facing camera view.

        MUST use cam_name="camera" — the <camera name="camera"> element defined
        inside base_link in yahboom_x3.xml.  If that camera is missing,
        render_mujoco() falls back to the free spectator camera (external view),
        which violates the VLN embodied-perception contract.  Raise rather than
        silently return a privileged external view.
        """
        import mujoco as _mj
        cam_id = _mj.mj_name2id(env.model, _mj.mjtObj.mjOBJ_CAMERA, "camera")
        if cam_id < 0:
            raise RuntimeError(
                "MuJoCo model has no camera named 'camera'.  "
                "The VLN perception contract requires a robot-mounted forward-facing "
                "camera.  Add <camera name=\"camera\" xyaxes=\"0 -1 0 0 0 1\" fovy=\"62\"/> "
                "inside the base_link body in the MJCF."
            )
        return IsaacCameraObsAdapter.render_mujoco(
            env.model, env.data, cam_name="camera",
            width=640, height=480,
        )

    def _get_obstacle_positions(
        self, env: Any, scene: SceneConfig
    ) -> list[np.ndarray]:
        """Extract obstacle positions from env info (robot-frame)."""
        if not hasattr(env, "_obs_positions"):
            return []
        robot_xy = np.array(env.get_robot_pose()[:2])
        return [p - robot_xy for p in env._obs_positions]

    def _get_obs_vec(self, env: Any) -> np.ndarray:
        """Return a minimal obs vector for CBF state extraction."""
        # Uses the cached _last_obs if available, else zeros
        return getattr(env, "_last_obs", np.zeros(47, dtype=np.float32))

    # ── Reporting helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _print_episode_summary(r: EpisodeResult) -> None:
        status  = "SUCCESS" if r.success else ("COLLISION" if r.collision else "TIMEOUT")
        latency = f"{r.mean_latency_ms:.1f} ms/step"
        print(
            f"  {status:<10}  path={r.path_length_m:.2f}m  "
            f"interv={r.intervention_count}  latency={latency}"
        )

    @staticmethod
    def _episode_to_dict(r: EpisodeResult) -> dict:
        d = asdict(r)
        d["mean_latency_ms"] = r.mean_latency_ms
        d["fps"]             = r.fps
        # Truncate long per-step logs to save space
        d["step_latency_ms"] = d["step_latency_ms"][:20]
        d["raw_cmd_log"]     = d["raw_cmd_log"][:20]
        d["safe_cmd_log"]    = d["safe_cmd_log"][:20]
        d["delta_cmd_log"]   = d["delta_cmd_log"][:20]
        return d

    @staticmethod
    def _aggregate(results: list[EpisodeResult]) -> dict:
        if not results:
            return {}
        n = len(results)
        return {
            "n_episodes":           n,
            "success_rate":         sum(r.success for r in results) / n,
            "collision_rate":       sum(r.collision for r in results) / n,
            "mean_path_length_m":   float(np.mean([r.path_length_m for r in results])),
            "mean_smoothness":      float(np.mean([r.smoothness for r in results])),
            "mean_stuck_count":     float(np.mean([r.stuck_count for r in results])),
            "mean_intervention_count": float(np.mean([r.intervention_count for r in results])),
            "mean_near_violation_count": float(np.mean([r.near_violation_count for r in results])),
            "mean_min_obstacle_dist_m": float(np.mean([r.min_obstacle_dist_m for r in results])),
            "mean_latency_ms":      float(np.mean([r.mean_latency_ms for r in results])),
            "mean_fps":             float(np.mean([r.fps for r in results])),
        }
