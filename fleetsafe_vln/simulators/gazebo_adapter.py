"""Gazebo adapter — bridges ROS 2 topics to the unified SimulatorAdapter API.

Fails gracefully if ROS 2 is not sourced.
"""
from __future__ import annotations

from typing import Any, List

from fleetsafe_vln.simulators.base import SimulatorAdapter, SimulatorObs


class GazeboAdapter(SimulatorAdapter):
    """Reads ROS 2 sensor topics, publishes cmd_vel. Requires ros2 sourced."""

    platform_name = "gazebo"

    def __init__(self, ros2_namespace: str = "/m3pro", timeout_s: float = 5.0, **kwargs):
        self._ns = ros2_namespace
        self._timeout = timeout_s
        self._node = None
        self._step_count = 0
        self._check_available()

    def _check_available(self) -> None:
        try:
            import rclpy  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "rclpy (ROS 2) is not installed or not sourced. "
                "Source your ROS 2 workspace and retry. "
                f"Original error: {e}"
            ) from e

    def reset(self, task: Any) -> SimulatorObs:
        import rclpy
        from fleet_safe_vla.sim2real.deployment.ros2_node import FleetSafeROS2Node  # type: ignore
        if not rclpy.ok():
            rclpy.init()
        self._node = FleetSafeROS2Node(namespace=self._ns)
        self._step_count = 0
        return SimulatorObs(step=0)

    def step(self, u_safe: List[float]) -> SimulatorObs:
        assert self._node is not None, "Call reset() first"
        self._node.publish_cmd_vel(vx=u_safe[0], wz=u_safe[1] if len(u_safe) > 1 else 0.0)
        obs_dict = self._node.get_latest_obs(timeout_s=self._timeout)
        self._step_count += 1
        return SimulatorObs(
            rgb=obs_dict.get("rgb"),
            depth=obs_dict.get("depth"),
            lidar=obs_dict.get("lidar"),
            robot_pose=tuple(obs_dict.get("pose", (0.0, 0.0, 0.0))),
            step=self._step_count,
        )

    def close(self) -> None:
        if self._node is not None:
            self._node.destroy_node()
            self._node = None

    def is_available(self) -> bool:
        try:
            import rclpy  # noqa: F401
            return True
        except ImportError:
            return False
