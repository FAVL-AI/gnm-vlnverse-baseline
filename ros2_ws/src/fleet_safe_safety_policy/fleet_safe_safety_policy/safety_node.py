"""
ROS2 Fleet-Safe safety policy node for the Yahboom robot.

Subscribes:
  /cmd_vel_nominal   (geometry_msgs/Twist)  — from planner/policy
  /scan              (sensor_msgs/LaserScan) — from LiDAR
  /imu/data          (sensor_msgs/Imu)
  /odom              (nav_msgs/Odometry)
  /joint_states      (sensor_msgs/JointState)

Publishes:
  /cmd_vel           (geometry_msgs/Twist)  — filtered command
  /fleet_safe/estop  (std_msgs/Bool)        — emergency stop
  /fleet_safe/status (fleet_safe_msgs/SafetyStatus) — safety state

Runtime graph:
  /cmd_vel_nominal → YahboomCBFFilter → /cmd_vel → robot

Usage:
  ros2 run fleet_safe_safety_policy safety_node
"""
from __future__ import annotations

try:
    import rclpy
    from rclpy.node import Node
    from geometry_msgs.msg import Twist
    from sensor_msgs.msg import LaserScan, Imu, JointState
    from nav_msgs.msg import Odometry
    from std_msgs.msg import Bool
    _HAS_ROS = True
except ImportError:
    _HAS_ROS = False

import numpy as np
import sys


if not _HAS_ROS:
    print("[safety_node] rclpy not available. This node requires ROS2 Humble.")
    sys.exit(1)


from fleet_safe_vla.fleet_safety.yahboom_cbf import YahboomCBFFilter, YahboomCBFConfig
from fleet_safe_vla.robots.yahboom.controllers.obs_adapter import YahboomObsAdapter

MIN_OBS_DIST = 0.30    # from safety_limits.yaml


class FleetSafeSafetyNode(Node):

    def __init__(self):
        super().__init__("fleet_safe_safety")

        # Parameters
        self.declare_parameter("max_linear_ms",  0.5)
        self.declare_parameter("max_angular_rs", 1.0)
        self.declare_parameter("d_safe_m",       0.30)
        self.declare_parameter("estop_dist_m",   0.15)

        cfg = YahboomCBFConfig(
            max_linear_ms=self.get_parameter("max_linear_ms").value,
            max_angular_rs=self.get_parameter("max_angular_rs").value,
            d_safe_m=self.get_parameter("d_safe_m").value,
            estop_dist_m=self.get_parameter("estop_dist_m").value,
        )
        self._cbf = YahboomCBFFilter(cfg)
        self._obs_adapter = YahboomObsAdapter()

        # State
        self._latest_scan: np.ndarray | None = None
        self._latest_imu: dict = {}
        self._latest_odom: dict = {}
        self._latest_joints: dict = {}
        self._obstacle_positions: list[np.ndarray] = []

        # Subscribers
        self.create_subscription(Twist,      "/cmd_vel_nominal", self._cb_nominal,  10)
        self.create_subscription(LaserScan,  "/scan",            self._cb_scan,     10)
        self.create_subscription(Imu,        "/imu/data",        self._cb_imu,      10)
        self.create_subscription(Odometry,   "/odom",            self._cb_odom,     10)
        self.create_subscription(JointState, "/joint_states",    self._cb_joints,   10)

        # Publishers
        self._pub_cmd   = self.create_publisher(Twist, "/cmd_vel",          10)
        self._pub_estop = self.create_publisher(Bool,  "/fleet_safe/estop", 10)

        self.get_logger().info("Fleet-Safe safety node ready.")

    def _cb_nominal(self, msg: Twist) -> None:
        """Filter incoming command and publish safe version."""
        nominal = np.array([msg.linear.x, msg.angular.z], dtype=np.float32)

        # Build obs from latest sensor readings
        obs = self._obs_adapter.update(
            imu=self._latest_imu,
            joints=self._latest_joints,
            odom=self._latest_odom,
            cmd_vel=nominal,
        )

        safe_action, info = self._cbf.filter(obs, nominal, self._obstacle_positions)

        # Publish filtered command
        out = Twist()
        out.linear.x  = float(safe_action[0])
        out.angular.z = float(safe_action[1])
        self._pub_cmd.publish(out)

        # E-stop
        estop_msg = Bool()
        estop_msg.data = info.get("estop", False)
        self._pub_estop.publish(estop_msg)

        if info.get("intervened", False):
            self.get_logger().warn(
                f"Safety intervention! min_dist={info.get('min_dist_m', -1):.3f}m "
                f"estop={info.get('estop', False)}"
            )

    def _cb_scan(self, msg: LaserScan) -> None:
        """Convert 2D LiDAR scan to obstacle positions in robot frame."""
        ranges = np.array(msg.ranges, dtype=np.float32)
        angles = np.linspace(msg.angle_min, msg.angle_max, len(ranges))
        valid = np.isfinite(ranges) & (ranges > msg.range_min) & (ranges < msg.range_max)
        r = ranges[valid]
        a = angles[valid]
        xs = r * np.cos(a)
        ys = r * np.sin(a)

        # Cluster into obstacle estimates (simple grid binning)
        if len(xs) == 0:
            self._obstacle_positions = []
            return

        points = np.stack([xs, ys], axis=1)
        # Keep only close obstacles
        dists = np.linalg.norm(points, axis=1)
        close = points[dists < 2.0]
        if len(close) == 0:
            self._obstacle_positions = []
        else:
            # Simple: just track the nearest point cluster centres
            self._obstacle_positions = [close[np.argmin(np.linalg.norm(close, axis=1))]]

    def _cb_imu(self, msg: Imu) -> None:
        self._latest_imu = {
            "ax": msg.linear_acceleration.x,
            "ay": msg.linear_acceleration.y,
            "az": msg.linear_acceleration.z,
            "wx": msg.angular_velocity.x,
            "wy": msg.angular_velocity.y,
            "wz": msg.angular_velocity.z,
            "qx": msg.orientation.x,
            "qy": msg.orientation.y,
            "qz": msg.orientation.z,
            "qw": msg.orientation.w,
        }

    def _cb_odom(self, msg: Odometry) -> None:
        self._latest_odom = {
            "x": msg.pose.pose.position.x,
            "y": msg.pose.pose.position.y,
            "z": msg.pose.pose.position.z,
            "qx": msg.pose.pose.orientation.x,
            "qy": msg.pose.pose.orientation.y,
            "qz": msg.pose.pose.orientation.z,
            "qw": msg.pose.pose.orientation.w,
            "vx": msg.twist.twist.linear.x,
            "vy": msg.twist.twist.linear.y,
            "vyaw": msg.twist.twist.angular.z,
        }

    def _cb_joints(self, msg: JointState) -> None:
        name_to_idx = {n: i for i, n in enumerate(msg.name)}
        li = name_to_idx.get("left_wheel_joint", None)
        ri = name_to_idx.get("right_wheel_joint", None)
        self._latest_joints = {
            "left_pos":  msg.position[li] if li is not None and li < len(msg.position)  else 0.0,
            "right_pos": msg.position[ri] if ri is not None and ri < len(msg.position)  else 0.0,
            "left_vel":  msg.velocity[li] if li is not None and li < len(msg.velocity)  else 0.0,
            "right_vel": msg.velocity[ri] if ri is not None and ri < len(msg.velocity)  else 0.0,
            "left_eff":  msg.effort[li]   if li is not None and li < len(msg.effort)    else 0.0,
            "right_eff": msg.effort[ri]   if ri is not None and ri < len(msg.effort)    else 0.0,
        }


def main(args=None):
    rclpy.init(args=args)
    node = FleetSafeSafetyNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
