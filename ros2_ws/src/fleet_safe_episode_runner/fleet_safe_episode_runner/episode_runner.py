"""
ROS2 episode runner node for Yahboom robot.

Manages the high-level episode lifecycle:
  1. Wait for sensors to be ready
  2. Send goal to planner
  3. Monitor progress
  4. Detect success/failure/timeout
  5. Trigger recording start/stop
  6. Publish episode results

Subscribes:
  /odom
  /fleet_safe/estop

Publishes:
  /fleet_safe/goal        (geometry_msgs/PoseStamped)
  /cmd_vel_nominal        (geometry_msgs/Twist)  — planner output
  /fleet_safe/episode_status (std_msgs/String)

Usage:
  ros2 run fleet_safe_episode_runner episode_runner \
      --ros-args -p policy:="" -p record:=true -p task:=safe_path
"""
from __future__ import annotations

try:
    import rclpy
    from rclpy.node import Node
    from rclpy.duration import Duration
    from geometry_msgs.msg import Twist, PoseStamped
    from nav_msgs.msg import Odometry
    from std_msgs.msg import Bool, String
    _HAS_ROS = True
except ImportError:
    _HAS_ROS = False

import numpy as np
import sys
import json
import time

if not _HAS_ROS:
    print("[episode_runner] rclpy not available.")
    sys.exit(1)

from fleet_safe_vla.policies.nominal.nominal_planner import NominalGoToGoalPlanner
from fleet_safe_vla.robots.yahboom.controllers.obs_adapter import YahboomObsAdapter


GOAL_TOLERANCE_M = 0.25
MAX_EPISODE_STEPS = 500


class EpisodeRunnerNode(Node):

    def __init__(self):
        super().__init__("fleet_safe_episode_runner")

        self.declare_parameter("task",       "nav")
        self.declare_parameter("record",     False)
        self.declare_parameter("output_dir", "/tmp/fleet_safe_data")
        self.declare_parameter("max_steps",  MAX_EPISODE_STEPS)

        self._task        = self.get_parameter("task").value
        self._record      = self.get_parameter("record").value
        self._output_dir  = self.get_parameter("output_dir").value
        self._max_steps   = self.get_parameter("max_steps").value

        self._obs_adapter = YahboomObsAdapter()
        self._planner = NominalGoToGoalPlanner(goal_xy=np.array([2.0, 0.0]))

        # State
        self._current_odom: dict = {}
        self._estop = False
        self._step = 0
        self._episode_active = False
        self._goal_xy = np.array([2.0, 0.0])

        # Subs / pubs
        self.create_subscription(Odometry, "/odom",            self._cb_odom,  10)
        self.create_subscription(Bool,     "/fleet_safe/estop", self._cb_estop, 10)

        self._pub_cmd    = self.create_publisher(Twist,        "/cmd_vel_nominal",           10)
        self._pub_status = self.create_publisher(String,       "/fleet_safe/episode_status", 10)

        # 10 Hz control loop
        self.create_timer(0.1, self._control_loop)

        self.get_logger().info(f"Episode runner ready. Task={self._task} Record={self._record}")
        self._start_episode()

    def _start_episode(self) -> None:
        self._goal_xy = np.array([2.0, 0.0])  # default; real system would use nav2 goal
        self._planner.set_goal(self._goal_xy)
        self._obs_adapter.reset()
        self._step = 0
        self._episode_active = True
        self.get_logger().info(f"Episode started. Goal: {self._goal_xy}")

    def _control_loop(self) -> None:
        if not self._episode_active or self._estop:
            return

        if not self._current_odom:
            return   # wait for first odom

        obs = self._obs_adapter.update(
            imu={}, joints={}, odom=self._current_odom,
        )

        action = self._planner.act(obs)

        cmd = Twist()
        cmd.linear.x  = float(np.clip(action[0], -0.5, 0.5))
        cmd.angular.z = float(np.clip(action[1], -1.0, 1.0))
        self._pub_cmd.publish(cmd)

        # Check goal
        x, y = float(self._current_odom.get("x", 0)), float(self._current_odom.get("y", 0))
        dist = float(np.linalg.norm(self._goal_xy - np.array([x, y])))

        self._step += 1
        if dist < GOAL_TOLERANCE_M:
            self._finish_episode(success=True, reason="goal_reached")
        elif self._step >= self._max_steps:
            self._finish_episode(success=False, reason="timeout")

    def _finish_episode(self, success: bool, reason: str) -> None:
        self._episode_active = False
        # Stop robot
        self._pub_cmd.publish(Twist())
        status = json.dumps({"success": success, "reason": reason, "step": self._step})
        self._pub_status.publish(String(data=status))
        self.get_logger().info(f"Episode finished: {status}")

    def _cb_odom(self, msg: Odometry) -> None:
        self._current_odom = {
            "x": msg.pose.pose.position.x,
            "y": msg.pose.pose.position.y,
            "vx": msg.twist.twist.linear.x,
            "vyaw": msg.twist.twist.angular.z,
            "qz": msg.pose.pose.orientation.z,
            "qw": msg.pose.pose.orientation.w,
        }

    def _cb_estop(self, msg: Bool) -> None:
        if msg.data and not self._estop:
            self.get_logger().error("EMERGENCY STOP received!")
            self._pub_cmd.publish(Twist())  # zero velocity
        self._estop = msg.data


def main(args=None):
    rclpy.init(args=args)
    node = EpisodeRunnerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
