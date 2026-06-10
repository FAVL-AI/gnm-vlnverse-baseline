"""Mock simulator — always available, no external dependencies.

Used for CI smoke tests and offline development. Generates synthetic
observations driven by a simple kinematic model.
"""
from __future__ import annotations

import math
import time
from typing import Any, List

import numpy as np

from fleetsafe_vln.simulators.base import SimulatorAdapter, SimulatorObs


class MockSimAdapter(SimulatorAdapter):
    """Deterministic 2-D kinematic simulator with synthetic obstacles."""

    platform_name = "mock"

    def __init__(self, dt: float = 0.25, img_w: int = 320, img_h: int = 240):
        self._dt = dt
        self._img_w = img_w
        self._img_h = img_h
        self._x = self._y = self._yaw = 0.0
        self._goal = np.array([3.0, 0.0])
        self._obstacles = np.array([[2.0, 0.8], [1.5, -0.6], [3.5, 0.3]])
        self._obs_r = np.array([0.3, 0.3, 0.3])
        self._humans: List = []
        self._step = 0
        self._max_steps = 500

    def reset(self, task: Any) -> SimulatorObs:
        from fleetsafe_vln.benchmark.task_schema import TaskConfig
        if isinstance(task, TaskConfig):
            pose = task.start_pose
            self._x, self._y = float(pose[0]), float(pose[1])
            self._yaw = float(pose[2]) if len(pose) > 2 else 0.0
            self._goal = np.array(task.goal_xy, dtype=float)
            self._max_steps = task.max_steps
        else:
            self._x = self._y = self._yaw = 0.0
        self._step = 0
        return self._make_obs()

    def step(self, u_safe: List[float]) -> SimulatorObs:
        vx = float(u_safe[0]) if len(u_safe) > 0 else 0.0
        wz = float(u_safe[1]) if len(u_safe) > 1 else 0.0
        self._yaw += wz * self._dt
        self._x += vx * math.cos(self._yaw) * self._dt
        self._y += vx * math.sin(self._yaw) * self._dt
        self._step += 1
        return self._make_obs()

    def close(self) -> None:
        pass

    def _make_obs(self) -> SimulatorObs:
        rx, ry = self._x, self._y
        dist_to_goal = float(np.linalg.norm(self._goal - np.array([rx, ry])))
        goal_reached = dist_to_goal < 0.5

        dists = np.linalg.norm(self._obstacles - np.array([rx, ry]), axis=1) - self._obs_r
        collision = bool(np.any(dists < 0.05))

        rgb = np.zeros((self._img_h, self._img_w, 3), dtype=np.uint8)
        rgb[:, :, 1] = 40
        rgb[:, :, 2] = 80

        return SimulatorObs(
            rgb=rgb,
            robot_pose=(rx, ry, self._yaw),
            obstacle_positions=[(float(p[0]), float(p[1])) for p in self._obstacles],
            human_positions=[],
            goal_reached=goal_reached,
            collision=collision,
            step=self._step,
            metadata={"dist_to_goal": dist_to_goal},
        )
