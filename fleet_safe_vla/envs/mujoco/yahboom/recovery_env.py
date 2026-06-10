"""
FleetSafe-Yahboom-Recovery-v0

Tests the robot's ability to recover from near-collision states.
Episode starts with the robot already close to an obstacle, requiring
a recovery manoeuvre before navigating to the goal.

Success: reach goal after recovering from the initial unsafe state.
Failure: collide with obstacle or timeout.
"""
from __future__ import annotations

import mujoco
import numpy as np

from fleet_safe_vla.envs.mujoco.yahboom.safe_path_env import YahboomSafePathEnv, OBS_RADIUS_M

RECOVERY_START_DIST = 0.32    # start this close to obstacle (just inside soft limit)
GOAL_TOLERANCE_M = 0.20
MIN_SAFE_DIST = 0.30


class YahboomRecoveryEnv(YahboomSafePathEnv):
    """
    Begins each episode with the robot dangerously close to an obstacle,
    testing the safety layer's recovery policy.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("n_obstacles", 4)
        super().__init__(**kwargs)
        self._recovery_triggered = False
        self._recovery_steps = 0

    def _reset_task(self):
        super()._reset_task()
        self._recovery_triggered = False
        self._recovery_steps = 0

        if len(self._obs_positions) == 0:
            return

        # Place robot right next to the first obstacle
        obs_xy = self._obs_positions[0]
        direction = self._rng.uniform(-np.pi, np.pi)
        start_xy = obs_xy + (OBS_RADIUS_M + RECOVERY_START_DIST) * np.array([
            np.cos(direction), np.sin(direction)
        ])

        self._data.qpos[0] = start_xy[0]
        self._data.qpos[1] = start_xy[1]
        self._data.qpos[2] = 0.066
        # Face toward goal
        dx = float(self._goal_xy[0] - start_xy[0])
        dy = float(self._goal_xy[1] - start_xy[1])
        yaw = np.arctan2(dy, dx)
        self._data.qpos[3:7] = [np.cos(yaw/2), 0, 0, np.sin(yaw/2)]
        mujoco.mj_forward(self._model, self._data)

    def _compute_reward(self, obs, action, info) -> float:
        base_reward = super()._compute_reward(obs, action, info)

        # Extra reward for successfully increasing distance from initial obstacle
        min_d = info.get("min_obstacle_dist_m", 99.0)
        if min_d > MIN_SAFE_DIST and not self._recovery_triggered:
            self._recovery_triggered = True
            base_reward += 5.0    # bonus for clearing safe zone
        if self._recovery_triggered:
            self._recovery_steps += 1

        return base_reward

    def _task_info(self) -> dict:
        info = super()._task_info()
        info["recovery_triggered"] = self._recovery_triggered
        info["recovery_steps"] = self._recovery_steps
        info["task"] = "recovery"
        return info
