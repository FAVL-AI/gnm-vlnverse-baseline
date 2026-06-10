"""
IMU Processor ROS2 Node — Fleet-Safe-VLA-OS.

Subscribes to raw IMU data and publishes:
  - Filtered orientation (complementary filter via robot-lab StateEstimator)
  - Projected gravity vector for policy observation
  - Base tilt angle for safety monitor
"""
from __future__ import annotations

import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Imu
from std_msgs.msg import Float32MultiArray, Float32

from robot_lab.sim2real.state_estimator import StateEstimator, StateEstimatorConfig


class IMUProcessor(Node):
    """
    Processes raw IMU messages and publishes filtered state estimates.

    Subscriptions:
      /imu/data  (sensor_msgs/Imu)

    Publications:
      /fleet_safe/projected_gravity  (std_msgs/Float32MultiArray, 3 dims)
      /fleet_safe/base_tilt_rad      (std_msgs/Float32)
      /fleet_safe/base_ang_vel       (std_msgs/Float32MultiArray, 3 dims)
    """

    def __init__(self) -> None:
        super().__init__("fleet_safe_imu_processor")

        self.declare_parameter("imu_alpha", 0.98)
        alpha = self.get_parameter("imu_alpha").value

        self._estimator = StateEstimator(StateEstimatorConfig(alpha=alpha, dt=0.01))

        self.create_subscription(Imu, "/imu/data", self._imu_callback, 10)

        self._grav_pub = self.create_publisher(
            Float32MultiArray, "/fleet_safe/projected_gravity", 10
        )
        self._tilt_pub = self.create_publisher(
            Float32, "/fleet_safe/base_tilt_rad", 10
        )
        self._angvel_pub = self.create_publisher(
            Float32MultiArray, "/fleet_safe/base_ang_vel", 10
        )

        self.get_logger().info("IMU Processor started")

    def _imu_callback(self, msg: Imu) -> None:
        o = msg.orientation
        av = msg.angular_velocity

        quat = np.array([o.x, o.y, o.z, o.w], dtype=np.float32)
        gyro = np.array([av.x, av.y, av.z], dtype=np.float32)

        est = self._estimator.update(imu_quat=quat, imu_gyro=gyro)

        # Projected gravity
        grav_msg = Float32MultiArray()
        grav_msg.data = est["proj_gravity"].tolist()
        self._grav_pub.publish(grav_msg)

        # Tilt angle
        cos_tilt = float(np.clip(-est["proj_gravity"][2], -1.0, 1.0))
        tilt = float(np.arccos(cos_tilt))
        tilt_msg = Float32()
        tilt_msg.data = tilt
        self._tilt_pub.publish(tilt_msg)

        # Angular velocity
        angvel_msg = Float32MultiArray()
        angvel_msg.data = est["base_ang_vel"].tolist()
        self._angvel_pub.publish(angvel_msg)


def main():
    rclpy.init()
    node = IMUProcessor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
