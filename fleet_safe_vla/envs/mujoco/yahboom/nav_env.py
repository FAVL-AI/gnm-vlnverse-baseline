"""
FleetSafe-Yahboom-Nav-v0

Navigation to a goal point in an open arena.
Reward: progress toward goal – velocity penalty – proximity safety penalty.
"""
from __future__ import annotations

import mujoco
import numpy as np

from fleet_safe_vla.envs.mujoco.yahboom.base_env import YahboomMuJoCoBase

GOAL_TOLERANCE_M = 0.20     # success radius
MAX_DIST_M = 8.0            # episode timeout distance


class YahboomNavEnv(YahboomMuJoCoBase):
    """
    Reset: robot at origin, goal randomly placed 1–4 m away.
    Success: reach goal within GOAL_TOLERANCE_M.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._goal_xy = np.array([2.0, 0.0], dtype=np.float32)
        self._prev_dist = None

    def _reset_task(self):
        angle = self._rng.uniform(-np.pi, np.pi)
        dist  = self._rng.uniform(1.5, 3.5)
        self._goal_xy = np.array([
            dist * np.cos(angle),
            dist * np.sin(angle),
        ], dtype=np.float32)
        self._prev_dist = dist

    def _compute_reward(self, obs, action, info) -> float:
        x, y, _ = self.get_robot_pose()
        dist = float(np.linalg.norm(self._goal_xy - np.array([x, y])))
        progress = (self._prev_dist - dist) if self._prev_dist is not None else 0.0
        self._prev_dist = dist

        r_progress  = 2.0 * progress
        r_goal      = 10.0 if dist < GOAL_TOLERANCE_M else 0.0
        r_smooth    = -0.01 * float(np.abs(action[1]))   # discourage spinning
        r_speed     = -0.005 * float(action[0] ** 2)

        return r_progress + r_goal + r_smooth + r_speed

    def _is_terminated(self, obs, info) -> bool:
        x, y, _ = self.get_robot_pose()
        dist = float(np.linalg.norm(self._goal_xy - np.array([x, y])))
        return dist < GOAL_TOLERANCE_M

    def _task_info(self) -> dict:
        x, y, yaw = self.get_robot_pose()
        dist = float(np.linalg.norm(self._goal_xy - np.array([x, y])))
        return {
            "step": self._step_count,
            "goal_xy": self._goal_xy.tolist(),
            "robot_xy": [x, y],
            "dist_to_goal_m": dist,
            "success": dist < GOAL_TOLERANCE_M,
            "task": "nav",
        }
