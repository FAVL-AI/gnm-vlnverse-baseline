"""Isaac Sim robot controller for GNM.

Converts GNM's (Δx, Δy) waypoint output into velocity commands
and sends them to the robot in Isaac Sim.

Control loop (5 Hz)
────────────────────
  1. GNM predicts waypoint (dx_robot, dy_robot) in robot frame
  2. compute_velocity() converts to (linear_vel, angular_vel)
  3. apply_velocity() drives the robot for one physics step
  4. Repeat until dist_pred < stop_threshold

Coordinate frame
─────────────────
  Robot frame: +x = forward, +y = left
  World frame: Isaac uses +X = forward, +Y = left, +Z = up

  GNM outputs actions in the robot frame, so we must rotate them to world
  frame before moving the robot:
    dx_world = cos(yaw) * dx_robot - sin(yaw) * dy_robot
    dy_world = sin(yaw) * dx_robot + cos(yaw) * dy_robot
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

try:
    import omni.isaac.core.utils.prims as prim_utils
    from omni.isaac.core.robots import Robot
    _ISAAC_AVAILABLE = True
except ImportError:
    _ISAAC_AVAILABLE = False


class GNMRobotController:
    """Drive a robot in Isaac Sim using GNM waypoint predictions.

    Parameters
    ----------
    robot_prim_path : str
        USD prim path of the robot, e.g. "/World/YahboomM3Pro"
    max_linear_vel : float
        Maximum forward speed (m/s).  Default: 0.5
    max_angular_vel : float
        Maximum turn rate (rad/s).  Default: 1.0
    control_hz : float
        Control loop frequency.  Default: 5 Hz (matching GNM training)
    """

    def __init__(
        self,
        robot_prim_path: str = "/World/YahboomM3Pro",
        max_linear_vel:  float = 0.5,
        max_angular_vel: float = 1.0,
        control_hz:      float = 5.0,
    ) -> None:
        self.prim_path       = robot_prim_path
        self.max_linear_vel  = max_linear_vel
        self.max_angular_vel = max_angular_vel
        self.dt              = 1.0 / control_hz
        self._robot: Optional[object] = None

    def initialize(self) -> None:
        """Get handle to Isaac robot object."""
        if not _ISAAC_AVAILABLE:
            raise ImportError("Isaac Sim required for robot control.")
        from omni.isaac.core.world import World
        world  = World.instance()
        self._robot = world.scene.get_object(self.prim_path.split("/")[-1])

    def compute_velocity(
        self,
        action: np.ndarray,
        current_yaw: float,
    ) -> tuple[float, float]:
        """Convert GNM (Δx, Δy) to (linear_vel, angular_vel).

        Strategy: Pure-pursuit controller.
          1. The predicted waypoint is (dx_r, dy_r) in robot frame.
          2. Heading error = atan2(dy_r, dx_r)  (angle to waypoint)
          3. linear_vel  proportional to forward displacement
          4. angular_vel proportional to heading error

        Parameters
        ----------
        action : (2,) array — (dx_robot, dy_robot)
        current_yaw : float — robot's current heading (radians)

        Returns
        -------
        (linear_vel, angular_vel) — both clipped to max values
        """
        dx_r, dy_r = float(action[0]), float(action[1])

        # Heading error to reach waypoint
        heading_error = math.atan2(dy_r, dx_r)

        # Forward distance
        dist = math.hypot(dx_r, dy_r)

        # Proportional controller
        k_v = 1.0   # linear gain
        k_w = 2.0   # angular gain

        linear_vel  = k_v * dist
        angular_vel = k_w * heading_error

        # Clip to max values
        linear_vel  = float(np.clip(linear_vel,  0.0, self.max_linear_vel))
        angular_vel = float(np.clip(angular_vel, -self.max_angular_vel, self.max_angular_vel))

        return linear_vel, angular_vel

    def apply_velocity(self, linear_vel: float, angular_vel: float) -> None:
        """Send velocity command to the robot.

        For differential-drive robots (Yahboom M3Pro):
          left_wheel_vel  = linear_vel - angular_vel * wheel_base / 2
          right_wheel_vel = linear_vel + angular_vel * wheel_base / 2

        We use Isaac's ArticulationController for joint velocity control.
        """
        if self._robot is None:
            return

        try:
            # Differential drive kinematics
            wheel_base   = 0.17  # metres (Yahboom M3Pro)
            wheel_radius = 0.04  # metres

            v_left  = (linear_vel - angular_vel * wheel_base / 2) / wheel_radius
            v_right = (linear_vel + angular_vel * wheel_base / 2) / wheel_radius

            self._robot.get_articulation_controller().apply_action(
                {"joint_velocities": np.array([v_left, v_right], dtype=np.float32)}
            )
        except Exception:
            pass

    def stop(self) -> None:
        """Send zero velocity to stop the robot."""
        self.apply_velocity(0.0, 0.0)
