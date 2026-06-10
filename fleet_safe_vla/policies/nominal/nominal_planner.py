"""
Nominal planner for Yahboom navigation — Backbone A.

Pure geometric planning: go-to-goal with obstacle potential field.
No safety layer. Used as the unsafe baseline in the benchmark.

Obs contract: 36-dim vector from YahboomObsAdapter.
  [0:10]  imu
  [10:16] joints
  [16:26] odom: x,y,z,qx,qy,qz,qw,vx,vy,vyaw
  [26:36] cmd_vel_history
"""
from __future__ import annotations

import numpy as np


class NominalGoToGoalPlanner:
    """
    Proportional go-to-goal controller.

    Does NOT respect safety limits. Use Fleet-Safe layer for safe version.
    """

    def __init__(
        self,
        goal_xy: np.ndarray | None = None,
        k_linear: float = 0.4,
        k_angular: float = 1.5,
        max_linear: float = 0.5,
        max_angular: float = 1.0,
    ):
        self.goal_xy = goal_xy if goal_xy is not None else np.zeros(2)
        self.k_linear = k_linear
        self.k_angular = k_angular
        self.max_linear = max_linear
        self.max_angular = max_angular

    def set_goal(self, goal_xy: np.ndarray) -> None:
        self.goal_xy = np.asarray(goal_xy, dtype=np.float32)

    def act(self, obs: np.ndarray) -> np.ndarray:
        """
        Args:
            obs: 36-dim obs vector
        Returns:
            action: [vx, wz]
        """
        # Extract pose from odom slice
        x, y = float(obs[16]), float(obs[17])
        qx, qy, qz, qw = obs[19], obs[20], obs[21], obs[22]
        yaw = float(2 * np.arctan2(qz, qw))

        dx = self.goal_xy[0] - x
        dy = self.goal_xy[1] - y
        dist = float(np.sqrt(dx**2 + dy**2))
        angle_to_goal = float(np.arctan2(dy, dx))
        heading_error = float(_wrap_angle(angle_to_goal - yaw))

        vx = float(np.clip(self.k_linear * dist * np.cos(heading_error), -self.max_linear, self.max_linear))
        wz = float(np.clip(self.k_angular * heading_error, -self.max_angular, self.max_angular))

        return np.array([vx, wz], dtype=np.float32)

    def reset(self) -> None:
        pass


class APFPlanner:
    """
    Artificial Potential Field planner.
    Adds repulsive field from lidar readings (approximated from obs).
    Still no hard safety guarantees — that's Backbone A2.
    """

    def __init__(
        self,
        goal_xy: np.ndarray | None = None,
        k_att: float = 0.4,
        k_rep: float = 0.8,
        rep_radius: float = 0.6,
        max_linear: float = 0.5,
        max_angular: float = 1.0,
    ):
        self.goal_xy = goal_xy if goal_xy is not None else np.zeros(2)
        self.k_att = k_att
        self.k_rep = k_rep
        self.rep_radius = rep_radius
        self.max_linear = max_linear
        self.max_angular = max_angular
        self._obstacle_estimates: list[np.ndarray] = []

    def set_goal(self, goal_xy: np.ndarray) -> None:
        self.goal_xy = np.asarray(goal_xy, dtype=np.float32)

    def update_obstacles(self, obstacle_positions: list[np.ndarray]) -> None:
        self._obstacle_estimates = obstacle_positions

    def act(self, obs: np.ndarray) -> np.ndarray:
        x, y = float(obs[16]), float(obs[17])
        qz, qw = float(obs[21]), float(obs[22])
        yaw = float(2 * np.arctan2(qz, qw))

        # Attractive force
        dx = self.goal_xy[0] - x
        dy = self.goal_xy[1] - y
        dist = float(np.sqrt(dx**2 + dy**2)) + 1e-6
        fx_att = self.k_att * dx / dist
        fy_att = self.k_att * dy / dist

        # Repulsive forces
        fx_rep, fy_rep = 0.0, 0.0
        for obs_pos in self._obstacle_estimates:
            odx = x - obs_pos[0]
            ody = y - obs_pos[1]
            d = float(np.sqrt(odx**2 + ody**2)) + 1e-6
            if d < self.rep_radius:
                mag = self.k_rep * (1.0 / d - 1.0 / self.rep_radius) / (d**2)
                fx_rep += mag * odx / d
                fy_rep += mag * ody / d

        # Combine
        fx = fx_att + fx_rep
        fy = fy_att + fy_rep

        angle_to_force = float(np.arctan2(fy, fx))
        heading_error  = float(_wrap_angle(angle_to_force - yaw))
        speed = float(np.sqrt(fx**2 + fy**2))

        vx = float(np.clip(speed * np.cos(heading_error), -self.max_linear, self.max_linear))
        wz = float(np.clip(2.0 * heading_error, -self.max_angular, self.max_angular))

        return np.array([vx, wz], dtype=np.float32)

    def reset(self) -> None:
        self._obstacle_estimates = []


def _wrap_angle(angle: float) -> float:
    while angle > np.pi:
        angle -= 2 * np.pi
    while angle < -np.pi:
        angle += 2 * np.pi
    return angle
