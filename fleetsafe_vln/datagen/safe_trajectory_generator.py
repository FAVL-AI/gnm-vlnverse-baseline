"""Safe trajectory generator — samples collision-free paths with CBF check.

Generates trajectories for FleetSafe-DataForge dataset export.
Can use VLNTube A* planner if available, otherwise uses a simple
kinematic forward simulation.
"""
from __future__ import annotations

import json
import math
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class TrajectoryStep:
    t: float
    x: float
    y: float
    yaw: float
    vx: float
    wz: float
    cbf_active: bool = False
    min_obstacle_m: float = math.inf
    action_label: str = "forward"


@dataclass
class SafeTrajectory:
    trajectory_id: str
    scene: str
    start_xy: Tuple[float, float]
    goal_xy: Tuple[float, float]
    steps: List[TrajectoryStep] = field(default_factory=list)
    success: bool = False
    path_length_m: float = 0.0
    optimal_path_m: float = 0.0
    safety_certificates: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "trajectory_id": self.trajectory_id,
            "scene": self.scene,
            "start_xy": list(self.start_xy),
            "goal_xy": list(self.goal_xy),
            "success": self.success,
            "path_length_m": self.path_length_m,
            "optimal_path_m": self.optimal_path_m,
            "steps": [
                {
                    "t": s.t,
                    "x": s.x, "y": s.y, "yaw": s.yaw,
                    "vx": s.vx, "wz": s.wz,
                    "cbf_active": s.cbf_active,
                    "min_obstacle_m": s.min_obstacle_m,
                    "action_label": s.action_label,
                }
                for s in self.steps
            ],
        }


class SafeTrajectoryGenerator:
    """Generate safe trajectories for a scene."""

    def __init__(
        self,
        d_safe: float = 0.5,
        estop_dist: float = 0.3,
        control_hz: float = 4.0,
        max_vx: float = 0.3,
        max_wz: float = 0.7,
        seed: int = 0,
    ):
        self._d_safe = d_safe
        self._estop = estop_dist
        self._dt = 1.0 / control_hz
        self._max_vx = max_vx
        self._max_wz = max_wz
        self._rng = random.Random(seed)

    def generate(
        self,
        scene: str,
        start_xy: Tuple[float, float],
        goal_xy: Tuple[float, float],
        obstacles: Optional[List[Tuple[float, float, float]]] = None,
        max_steps: int = 500,
    ) -> SafeTrajectory:
        traj_id = f"{scene}_{int(time.time()*1000)}"
        traj = SafeTrajectory(
            trajectory_id=traj_id,
            scene=scene,
            start_xy=start_xy,
            goal_xy=goal_xy,
        )

        obstacles = obstacles or []
        x, y, yaw = float(start_xy[0]), float(start_xy[1]), 0.0
        path_length = 0.0
        t = 0.0

        for step in range(max_steps):
            gx, gy = goal_xy
            dist_to_goal = math.sqrt((gx - x) ** 2 + (gy - y) ** 2)
            if dist_to_goal < 0.5:
                traj.success = True
                break

            goal_angle = math.atan2(gy - y, gx - x)
            angle_err = math.atan2(
                math.sin(goal_angle - yaw), math.cos(goal_angle - yaw)
            )
            vx_nom = self._max_vx * max(0.0, math.cos(angle_err))
            wz_nom = max(-self._max_wz, min(self._max_wz, 1.5 * angle_err))

            min_obs = self._min_obstacle_dist(x, y, obstacles)
            vx_safe, wz_safe, cbf_active = self._cbf_filter(vx_nom, wz_nom, min_obs)

            traj.steps.append(TrajectoryStep(
                t=t,
                x=x, y=y, yaw=yaw,
                vx=vx_safe, wz=wz_safe,
                cbf_active=cbf_active,
                min_obstacle_m=min_obs,
                action_label="stop" if vx_safe < 0.01 else "forward",
            ))

            path_length += abs(vx_safe) * self._dt
            yaw += wz_safe * self._dt
            x += vx_safe * math.cos(yaw) * self._dt
            y += vx_safe * math.sin(yaw) * self._dt
            t += self._dt

        traj.path_length_m = path_length
        traj.optimal_path_m = math.sqrt(
            (goal_xy[0] - start_xy[0]) ** 2 + (goal_xy[1] - start_xy[1]) ** 2
        )
        return traj

    def _min_obstacle_dist(self, x, y, obstacles) -> float:
        if not obstacles:
            return math.inf
        return min(
            math.sqrt((x - ox) ** 2 + (y - oy) ** 2) - r
            for ox, oy, r in obstacles
        )

    def _cbf_filter(self, vx, wz, min_dist) -> Tuple[float, float, bool]:
        if min_dist < self._estop:
            return 0.0, wz, True
        if min_dist < self._d_safe:
            scale = (min_dist - self._estop) / max(1e-6, self._d_safe - self._estop)
            return vx * max(0.0, scale), wz, True
        return vx, wz, False
