"""Abstract simulator interface for FleetSafe-VLN.

All platform adapters (Isaac, Gazebo, real robot, mock) implement this API
so the episode runner is platform-agnostic.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


@dataclass
class SimulatorObs:
    """One timestep of simulator output."""
    rgb: Optional[np.ndarray] = None          # (H, W, 3) uint8
    depth: Optional[np.ndarray] = None        # (H, W) float32, metres
    lidar: Optional[np.ndarray] = None        # (N,) float32, metres
    robot_pose: Tuple[float, float, float] = (0.0, 0.0, 0.0)  # x, y, yaw
    obstacle_positions: List[Tuple[float, float]] = field(default_factory=list)
    human_positions: List[Tuple[float, float]] = field(default_factory=list)
    goal_reached: bool = False
    collision: bool = False
    step: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def min_obstacle_dist(self) -> float:
        if not self.obstacle_positions:
            return float("inf")
        rx, ry, _ = self.robot_pose
        return float(min(
            ((rx - ox) ** 2 + (ry - oy) ** 2) ** 0.5
            for ox, oy in self.obstacle_positions
        ))

    def min_human_dist(self) -> float:
        if not self.human_positions:
            return float("inf")
        rx, ry, _ = self.robot_pose
        return float(min(
            ((rx - hx) ** 2 + (ry - hy) ** 2) ** 0.5
            for hx, hy in self.human_positions
        ))


class SimulatorAdapter(abc.ABC):
    """Base class for all simulator adapters."""

    @abc.abstractmethod
    def reset(self, task: Any) -> SimulatorObs:
        """Reset the simulator to the task start state. Returns initial obs."""

    @abc.abstractmethod
    def step(self, u_safe: List[float]) -> SimulatorObs:
        """Apply u_safe = [vx, wz] and return next obs."""

    @abc.abstractmethod
    def close(self) -> None:
        """Tear down the simulator."""

    @property
    @abc.abstractmethod
    def platform_name(self) -> str:
        """Human-readable platform identifier."""

    def is_available(self) -> bool:
        """Return True if this platform can actually run on this machine."""
        return True


def make_simulator(platform: str, **kwargs) -> SimulatorAdapter:
    """Factory — returns the adapter for the requested platform.

    Fails gracefully: if the platform is unavailable (missing Isaac, ROS2, etc.)
    it raises ImportError with a clear message rather than a cryptic traceback.
    """
    platform = platform.lower()

    if platform in ("mock", "mock_sim"):
        from fleetsafe_vln.simulators.mock_adapter import MockSimAdapter
        return MockSimAdapter(**kwargs)

    if platform in ("isaac", "isaaclab", "isaac_lab"):
        from fleetsafe_vln.simulators.isaac_adapter import IsaacSimAdapter
        return IsaacSimAdapter(**kwargs)

    if platform in ("gazebo", "ros2_gazebo"):
        from fleetsafe_vln.simulators.gazebo_adapter import GazeboAdapter
        return GazeboAdapter(**kwargs)

    if platform in ("real_robot", "real", "yahboom", "yahboom_m3_pro"):
        from fleetsafe_vln.simulators.real_robot_adapter import RealRobotAdapter
        return RealRobotAdapter(**kwargs)

    raise ValueError(
        f"Unknown platform: {platform!r}. "
        "Choose from: mock, isaac, gazebo, real_robot"
    )
