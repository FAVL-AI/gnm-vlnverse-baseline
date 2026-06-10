"""
Fleet-Safe Joint Controller ROS2 Node.

Implements a PD joint controller that reads target positions from
/fleet_safe/policy_action and publishes effort commands.

Integrates with the safety filter stack for hardware protection.
"""
from __future__ import annotations

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float64MultiArray
from sensor_msgs.msg import JointState
import numpy as np

JOINT_NAMES = [
    "left_hip_yaw", "left_hip_roll", "left_hip_pitch", "left_knee", "left_ankle",
    "right_hip_yaw", "right_hip_roll", "right_hip_pitch", "right_knee", "right_ankle",
    "left_shoulder_pitch", "left_shoulder_roll", "left_elbow", "left_wrist",
    "right_shoulder_pitch", "right_shoulder_roll", "right_elbow", "right_wrist",
]

_KP = np.array([200, 200, 200, 300, 40, 200, 200, 200, 300, 40,
                40, 40, 40, 10, 40, 40, 40, 10], dtype=np.float32)
_KD = np.array([5, 5, 5, 8, 1, 5, 5, 5, 8, 1,
                1, 1, 1, 0.5, 1, 1, 1, 0.5], dtype=np.float32)
_TORQUE_LIMITS = np.array([200, 200, 200, 300, 40, 200, 200, 200, 300, 40,
                            40, 40, 40, 10, 40, 40, 40, 10], dtype=np.float32)


class JointController(Node):
    """PD joint controller node."""

    def __init__(self):
        super().__init__("fleet_safe_joint_controller")

        self._joint_pos = np.zeros(18, dtype=np.float32)
        self._joint_vel = np.zeros(18, dtype=np.float32)
        self._target_pos = np.array([
            0, 0, -0.4, 0.8, -0.4,
            0, 0, -0.4, 0.8, -0.4,
            0, 0, 0, 0, 0, 0, 0, 0,
        ], dtype=np.float32)

        self._name_to_idx = {n: i for i, n in enumerate(JOINT_NAMES)}

        # Subscribe to joint states
        self.create_subscription(
            JointState, "/joint_states", self._js_callback, 10
        )

        # Subscribe to target positions
        self.create_subscription(
            Float64MultiArray, "/fleet_safe/target_positions", self._target_callback, 10
        )

        # Publish effort commands
        self._effort_pub = self.create_publisher(
            Float64MultiArray, "/joint_group_effort_controller/commands", 10
        )

        # Control loop at 50 Hz
        self.create_timer(0.02, self._control_loop)
        self.get_logger().info("JointController started")

    def _js_callback(self, msg: JointState) -> None:
        for i, name in enumerate(msg.name):
            if name in self._name_to_idx:
                j = self._name_to_idx[name]
                if i < len(msg.position):
                    self._joint_pos[j] = msg.position[i]
                if i < len(msg.velocity):
                    self._joint_vel[j] = msg.velocity[i]

    def _target_callback(self, msg: Float64MultiArray) -> None:
        arr = np.array(msg.data, dtype=np.float32)
        if len(arr) == 18:
            self._target_pos = arr

    def _control_loop(self) -> None:
        torques = _KP * (self._target_pos - self._joint_pos) - _KD * self._joint_vel
        torques = np.clip(torques, -_TORQUE_LIMITS, _TORQUE_LIMITS)
        out = Float64MultiArray()
        out.data = torques.tolist()
        self._effort_pub.publish(out)


def main():
    rclpy.init()
    node = JointController()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
