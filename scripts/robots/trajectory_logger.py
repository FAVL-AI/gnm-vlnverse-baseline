"""Mandatory per-step trajectory logging for live Isaac episodes.

One directory per episode under assets/experiments/trajectories/<episode_id>/:
    trajectory.jsonl        one JSON object per simulation/control step
    trajectory.csv          same rows, CSV convenience copy
    episode_metadata.json   provenance + aggregate statistics

Pure Python (no Isaac imports); the episode runner supplies all values.
Every live Isaac episode must produce one of these logs — rosbags prove
topics existed, the trajectory log proves episode-level behaviour.
"""

import csv
import json
import math
import subprocess
import time
from pathlib import Path

REQUIRED_FIELDS = [
    "episode_id", "step_idx", "sim_time", "wall_time",
    "robot_position_x", "robot_position_y", "robot_position_z",
    "robot_yaw", "linear_velocity_cmd", "angular_velocity_cmd",
    "odom_linear_velocity", "odom_angular_velocity",
    "camera_frame_id", "image_timestamp",
    "policy_mode", "stop_signal", "safety_state", "notes",
]


class TrajectoryLogger:
    def __init__(self, episode_id, repo_root, policy_mode="manual_cmd_vel",
                 extra_fields=None):
        self.episode_id = episode_id
        self.repo = Path(repo_root)
        self.policy_mode = policy_mode
        self.dir = self.repo / "assets/experiments/trajectories" / episode_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = self.dir / "trajectory.jsonl"
        self.csv_path = self.dir / "trajectory.csv"
        self.meta_path = self.dir / "episode_metadata.json"
        self.fieldnames = REQUIRED_FIELDS + list(extra_fields or [])
        self._jsonl = self.jsonl_path.open("w")
        self._csv_file = self.csv_path.open("w", newline="")
        self._csv = csv.DictWriter(self._csv_file, fieldnames=self.fieldnames)
        self._csv.writeheader()
        self.rows = 0
        self.start_wall = time.time()
        self._first = None
        self._prev = None
        self.total_distance = 0.0
        self.max_abs_z_drift = 0.0
        self.max_yaw_rate = 0.0
        self._z0 = None

    def log_step(self, step_idx, sim_time, x, y, z, yaw,
                 linear_cmd, angular_cmd, odom_lin, odom_ang,
                 image_timestamp, camera_frame_id="camera_link",
                 stop_signal=None, safety_state="nominal", notes="",
                 extra=None):
        row = {
            "episode_id": self.episode_id,
            "step_idx": step_idx,
            "sim_time": round(float(sim_time), 6),
            "wall_time": round(time.time(), 6),
            "robot_position_x": round(float(x), 6),
            "robot_position_y": round(float(y), 6),
            "robot_position_z": round(float(z), 6),
            "robot_yaw": round(float(yaw), 6),
            "linear_velocity_cmd": round(float(linear_cmd), 6),
            "angular_velocity_cmd": round(float(angular_cmd), 6),
            "odom_linear_velocity": round(float(odom_lin), 6),
            "odom_angular_velocity": round(float(odom_ang), 6),
            "camera_frame_id": camera_frame_id,
            "image_timestamp": round(float(image_timestamp), 6),
            "policy_mode": self.policy_mode,
            "stop_signal": stop_signal,
            "safety_state": safety_state,
            "notes": notes,
        }
        if extra:
            row.update(extra)
        self._jsonl.write(json.dumps(row) + "\n")
        self._csv.writerow(row)
        self.rows += 1

        if self._z0 is None:
            self._z0 = row["robot_position_z"]
        self.max_abs_z_drift = max(
            self.max_abs_z_drift, abs(row["robot_position_z"] - self._z0))
        if self._first is None:
            self._first = row
        if self._prev is not None:
            self.total_distance += math.hypot(
                row["robot_position_x"] - self._prev["robot_position_x"],
                row["robot_position_y"] - self._prev["robot_position_y"])
            dt = row["sim_time"] - self._prev["sim_time"]
            if dt > 1e-6:
                dyaw = abs(row["robot_yaw"] - self._prev["robot_yaw"])
                dyaw = min(dyaw, 2 * math.pi - dyaw)
                self.max_yaw_rate = max(self.max_yaw_rate, dyaw / dt)
        self._prev = row

    def finalize(self, scene_path, robot_asset, rosbag_path,
                 command_profile, topics_recorded, extra_meta=None):
        self._jsonl.close()
        self._csv_file.close()

        def git(*args):
            try:
                return subprocess.run(
                    ["git", "-C", str(self.repo), *args],
                    capture_output=True, text=True, timeout=10,
                ).stdout.strip()
            except Exception:
                return "unavailable"

        meta = {
            "episode_id": self.episode_id,
            "git_commit": git("rev-parse", "--short", "HEAD"),
            "git_branch": git("branch", "--show-current"),
            "scene_stage_path": str(scene_path),
            "robot_asset_path": str(robot_asset),
            "rosbag_path": str(rosbag_path) if rosbag_path else None,
            "trajectory_jsonl": str(self.jsonl_path.relative_to(self.repo)),
            "trajectory_csv": str(self.csv_path.relative_to(self.repo)),
            "command_profile": command_profile,
            "policy_mode": self.policy_mode,
            "start_wall_time": self.start_wall,
            "end_wall_time": time.time(),
            "wall_duration_s": round(time.time() - self.start_wall, 3),
            "sim_duration_s": round(
                (self._prev["sim_time"] - self._first["sim_time"])
                if self._prev and self._first else 0.0, 3),
            "steps_logged": self.rows,
            "total_distance_m": round(self.total_distance, 4),
            "max_abs_z_drift_m": round(self.max_abs_z_drift, 6),
            "max_yaw_rate_rad_s": round(self.max_yaw_rate, 4),
            "topics_recorded": topics_recorded,
        }
        if extra_meta:
            meta.update(extra_meta)
        with open(self.meta_path, "w") as f:
            json.dump(meta, f, indent=2)
        return meta
