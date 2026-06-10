"""
Canonical episode data recorder.

Writes one directory per episode:
  {output_dir}/{episode_id}/
    metadata.json
    observations/
      odom.jsonl
      imu.jsonl
      lidar.npy         (if available)
    actions/
      nominal_actions.jsonl
      safety_filtered_actions.jsonl
      executed_cmd_vel.jsonl
    labels/
      collision.jsonl
      near_miss.jsonl
      intervention.jsonl
      success.json
    metrics.json        (end-of-episode summary)

Works identically for sim (MuJoCo, Gazebo) and real robot.
The caller decides what data to feed — the recorder just writes it.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

import numpy as np


class EpisodeRecorder:
    """
    Stateful recorder for a single episode.

    Usage:
        rec = EpisodeRecorder(output_dir="data/episodes")
        rec.start(metadata={"task": "safe_path", "backbone": "D"})
        for step in episode:
            rec.record_step(obs, nominal_action, safe_action, info)
        rec.finish(success=True)
    """

    def __init__(self, output_dir: str | Path, episode_id: str | None = None):
        self.output_dir = Path(output_dir)
        self.episode_id = episode_id or str(uuid.uuid4())[:8]
        self._ep_dir: Path | None = None
        self._step = 0
        self._t_start: float = 0.0
        self._files: dict[str, Any] = {}
        self._lidar_frames: list[np.ndarray] = []
        self._collision_events: list[dict] = []
        self._near_miss_events: list[dict] = []
        self._intervention_events: list[dict] = []

    def start(self, metadata: dict | None = None) -> None:
        self._ep_dir = self.output_dir / self.episode_id
        (self._ep_dir / "observations").mkdir(parents=True, exist_ok=True)
        (self._ep_dir / "actions").mkdir(parents=True, exist_ok=True)
        (self._ep_dir / "labels").mkdir(parents=True, exist_ok=True)

        self._t_start = time.monotonic()
        self._step = 0

        meta = {
            "episode_id": self.episode_id,
            "start_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            **(metadata or {}),
        }
        (self._ep_dir / "metadata.json").write_text(json.dumps(meta, indent=2))

        # Open streaming files
        self._files = {
            "odom":     open(self._ep_dir / "observations/odom.jsonl",   "w"),
            "imu":      open(self._ep_dir / "observations/imu.jsonl",    "w"),
            "nominal":  open(self._ep_dir / "actions/nominal_actions.jsonl",         "w"),
            "safe":     open(self._ep_dir / "actions/safety_filtered_actions.jsonl", "w"),
            "cmd_vel":  open(self._ep_dir / "actions/executed_cmd_vel.jsonl",        "w"),
        }

    def record_step(
        self,
        obs: np.ndarray,
        nominal_action: np.ndarray,
        safe_action: np.ndarray,
        info: dict,
        lidar: np.ndarray | None = None,
    ) -> None:
        t = time.monotonic() - self._t_start
        s = self._step

        # Odom from obs vector
        odom_rec = {
            "t": t, "step": s,
            "x": float(obs[16]), "y": float(obs[17]), "z": float(obs[18]),
            "vx": float(obs[23]), "vy": float(obs[24]), "vyaw": float(obs[25]),
        }
        self._files["odom"].write(json.dumps(odom_rec) + "\n")

        # IMU
        imu_rec = {
            "t": t, "step": s,
            "ax": float(obs[0]), "ay": float(obs[1]), "az": float(obs[2]),
            "wx": float(obs[3]), "wy": float(obs[4]), "wz": float(obs[5]),
        }
        self._files["imu"].write(json.dumps(imu_rec) + "\n")

        # Actions
        self._files["nominal"].write(json.dumps({"t": t, "step": s, "vx": float(nominal_action[0]), "wz": float(nominal_action[1])}) + "\n")
        self._files["safe"].write(json.dumps({"t": t, "step": s, "vx": float(safe_action[0]), "wz": float(safe_action[1])}) + "\n")
        self._files["cmd_vel"].write(json.dumps({"t": t, "step": s, "vx": float(safe_action[0]), "wz": float(safe_action[1])}) + "\n")

        # Lidar
        if lidar is not None:
            self._lidar_frames.append(lidar.astype(np.float32))

        # Labels
        if info.get("collision", False):
            self._collision_events.append({"t": t, "step": s})
        if info.get("min_obstacle_dist_m", 99) < 0.45:
            self._near_miss_events.append({"t": t, "step": s, "dist_m": info.get("min_obstacle_dist_m")})
        if info.get("intervened", False):
            self._intervention_events.append({"t": t, "step": s, "estop": info.get("estop", False)})

        self._step += 1

    def finish(self, success: bool, extra_metrics: dict | None = None) -> Path:
        # Flush and close streams
        for f in self._files.values():
            f.close()
        self._files = {}

        # Save lidar
        if self._lidar_frames:
            np.save(str(self._ep_dir / "observations/lidar.npy"),
                    np.stack(self._lidar_frames))

        # Labels
        _write_jsonl(self._ep_dir / "labels/collision.jsonl",    self._collision_events)
        _write_jsonl(self._ep_dir / "labels/near_miss.jsonl",    self._near_miss_events)
        _write_jsonl(self._ep_dir / "labels/intervention.jsonl", self._intervention_events)
        (self._ep_dir / "labels/success.json").write_text(
            json.dumps({"success": success, "episode_id": self.episode_id})
        )

        # Metrics
        metrics = {
            "episode_id": self.episode_id,
            "duration_s": time.monotonic() - self._t_start,
            "n_steps": self._step,
            "success": success,
            "n_collisions": len(self._collision_events),
            "n_near_misses": len(self._near_miss_events),
            "n_interventions": len(self._intervention_events),
            **(extra_metrics or {}),
        }
        (self._ep_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))

        return self._ep_dir

    def __enter__(self):
        return self

    def __exit__(self, *args):
        for f in self._files.values():
            try: f.close()
            except Exception: pass


def _write_jsonl(path: Path, records: list) -> None:
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


class DatasetGenerator:
    """
    Runs N episodes across any Yahboom env and records them all.
    Produces the canonical dataset directory used for training and analysis.
    """

    def __init__(
        self,
        env_factory,
        policy_fn,
        cbf_filter=None,
        output_dir: str | Path = "data/episodes",
        n_episodes: int = 100,
        seed: int = 42,
        verbose: bool = True,
    ):
        self.env_factory = env_factory
        self.policy_fn = policy_fn
        self.cbf_filter = cbf_filter
        self.output_dir = Path(output_dir)
        self.n_episodes = n_episodes
        self.rng = np.random.default_rng(seed)
        self.verbose = verbose

    def run(self) -> list[Path]:
        saved_dirs = []

        for ep_i in range(self.n_episodes):
            ep_seed = int(self.rng.integers(0, 2**31))
            ep_id   = f"ep_{ep_i:05d}"

            env = self.env_factory(seed=ep_seed)
            obs, info = env.reset(seed=ep_seed)
            goal_xy = np.array(info.get("goal_xy", [2.0, 0.0]))

            if hasattr(self.policy_fn, "set_goal"):
                self.policy_fn.set_goal(goal_xy)
            if self.cbf_filter is not None:
                self.cbf_filter.reset()

            rec = EpisodeRecorder(self.output_dir, episode_id=ep_id)
            rec.start(metadata={
                "task": info.get("task", "unknown"),
                "seed": ep_seed,
                "goal_xy": goal_xy.tolist(),
            })

            success = False
            for step in range(env.max_episode_steps):
                nominal = self.policy_fn.act(obs)

                if self.cbf_filter is not None:
                    obs_pos = list(env._obs_positions) if hasattr(env, "_obs_positions") else []
                    safe_action, cbf_info = self.cbf_filter.filter(obs, nominal, obs_pos)
                else:
                    safe_action = nominal
                    cbf_info = {"intervened": False}

                obs, rew, terminated, truncated, info = env.step(safe_action)
                info["intervened"] = cbf_info.get("intervened", False)
                info["estop"]      = cbf_info.get("estop", False)

                rec.record_step(obs, nominal, safe_action, info)

                if info.get("success", False):
                    success = True
                if terminated or truncated:
                    break

            ep_dir = rec.finish(success=success, extra_metrics={
                "cumulative_safety_cost": info.get("cumulative_safety_cost", 0),
            })
            saved_dirs.append(ep_dir)
            env.close()

            if self.verbose and (ep_i + 1) % 10 == 0:
                print(f"  [{ep_i+1}/{self.n_episodes}] success={success} dir={ep_dir}")

        return saved_dirs
