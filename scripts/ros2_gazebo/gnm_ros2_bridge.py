#!/usr/bin/env python3
"""
gnm_ros2_bridge.py — Run GNM/ViNT navigation on the real M3Pro via ROS2.

This is the **real-robot deployment script** for the M3Pro + Jetson.
It:
  1. Subscribes to /usb_cam/image_raw for camera input
  2. Subscribes to /odom for position tracking
  3. Runs GNM or ViNT inference on the camera stream
  4. Applies FleetSafe CBF-QP safety filter
  5. Publishes safe /cmd_vel to the robot

This is the ROS2 equivalent of the official navigate.py (which uses ROS1).

Hardware: Yahboom ROSMASTER M3Pro + Jetson Orin NX 16GB
Software: ROS2 Humble, Python 3.10+

Usage
-----
  # On Jetson (or workbench with ROS2 bridge running):
  source /opt/ros/humble/setup.bash
  python scripts/ros2_gazebo/gnm_ros2_bridge.py \\
      --model gnm \\
      --topomap topomaps/hospital_route_1 \\
      --fleetsafe \\
      --v-max 0.3

  # Navigate without topomap (direct goal image):
  python scripts/ros2_gazebo/gnm_ros2_bridge.py \\
      --model vint \\
      --goal-image path/to/goal.jpg \\
      --fleetsafe
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

_VNT = _REPO / "third_party" / "visualnav-transformer" / "model_weights"
_CKPTS = {
    "gnm":   _VNT / "gnm"  / "gnm.pth",
    "vint":  _VNT / "vint" / "vint.pth",
    "nomad": _VNT / "nomad"/ "nomad.pth",
}

# Control parameters (match robot config)
_MAX_V    = 0.30  # m/s — conservative for indoor hospital
_MAX_W    = 0.70  # rad/s
_CTRL_HZ  = 4.0   # Hz — matches GNM paper
_D_SAFE   = 0.50  # m  — FleetSafe safety margin
_ESTOP    = 0.25  # m  — emergency stop distance

# M3Pro mecanum kinematics
_WHEEL_RADIUS = 0.048   # m
_LX           = 0.0775  # half wheelbase
_LY           = 0.0850  # half track width


def mecanum_cmd_to_wheel_speeds(vx: float, vy: float, wz: float) -> np.ndarray:
    """Convert body velocity [vx, vy, wz] to mecanum wheel angular speeds (rad/s)."""
    r  = _WHEEL_RADIUS
    lx = _LX
    ly = _LY
    return np.array([
        (vx - vy - (lx + ly) * wz) / r,
        (vx + vy + (lx + ly) * wz) / r,
        (vx + vy - (lx + ly) * wz) / r,
        (vx - vy + (lx + ly) * wz) / r,
    ])


class GNMNavigatorROS2:
    """
    ROS2 node that runs GNM/ViNT navigation on the real M3Pro.

    Subscribes:
        /usb_cam/image_raw    — forward camera (BGR8 or RGB8)
        /odom                 — robot odometry (nav_msgs/Odometry)
        /scan                 — LiDAR for FleetSafe (sensor_msgs/LaserScan)

    Publishes:
        /cmd_vel              — safe velocity command (geometry_msgs/Twist)
        /fleetsafe/status     — FleetSafe intervention status (std_msgs/String)
        /gnm/waypoints        — predicted waypoints (visualization_msgs/MarkerArray)
    """

    def __init__(
        self,
        model_name:   str,
        topomap_dir:  Optional[Path],
        goal_image:   Optional[Path],
        fleetsafe:    bool,
        v_max:        float,
        w_max:        float,
        d_safe:       float,
        estop:        float,
        ctrl_hz:      float,
        camera_topic: str,
        cmd_topic:    str,
    ):
        import rclpy
        from rclpy.node import Node
        from sensor_msgs.msg import Image, LaserScan
        from nav_msgs.msg import Odometry
        from geometry_msgs.msg import Twist
        from std_msgs.msg import String
        from cv_bridge import CvBridge
        from PIL import Image as PILImage

        self._rclpy = rclpy
        rclpy.init()

        self._bridge = CvBridge()
        self._v_max  = v_max
        self._w_max  = w_max
        self._dt     = 1.0 / ctrl_hz

        # State
        self._latest_img:   Optional[PILImage.Image] = None
        self._robot_x       = 0.0
        self._robot_y       = 0.0
        self._robot_yaw     = 0.0
        self._scan_ranges:  Optional[np.ndarray] = None
        self._scan_angles:  Optional[np.ndarray] = None

        # Load model
        from scripts.visualnav.run_evaluation_matrix import _load_adapter  # type: ignore
        self._adapter, mode = _load_adapter(model_name, _CKPTS.get(model_name), verbose=True)
        print(f"  Model: {model_name.upper()} ({mode})")

        # Camera observation adapter
        from fleet_safe_vla.integrations.visualnav_transformer.isaac_obs_adapter import (
            IsaacCameraObsAdapter,
        )
        W, H = self._adapter.image_size
        self._cam_adapter = IsaacCameraObsAdapter(
            image_size=(W, H),
            context_size=self._adapter.context_size,
        )

        # Load goal
        if goal_image and goal_image.exists():
            goal = PILImage.open(goal_image).convert("RGB").resize((W, H), PILImage.BILINEAR)
            self._cam_adapter.set_goal_image(goal)
            print(f"  Goal: {goal_image.name}")
        elif topomap_dir:
            # Will be set per-step during topological navigation
            self._topomap_dir = topomap_dir
            print(f"  Topomap: {topomap_dir}")
        else:
            # Use checkerboard as placeholder goal
            self._cam_adapter.set_goal_image(
                IsaacCameraObsAdapter.make_checkerboard_goal(W, H)
            )
            print("  Goal: checkerboard placeholder (set a real goal for deployment)")

        # FleetSafe
        self._cbf = None
        if fleetsafe:
            from fleet_safe_vla.fleet_safety.yahboom_cbf import YahboomCBFConfig, YahboomCBFFilter
            self._cbf = YahboomCBFFilter(YahboomCBFConfig(d_safe_m=d_safe, estop_dist_m=estop))
            print(f"  FleetSafe: ON  (d_safe={d_safe}m, estop={estop}m)")
        else:
            print("  FleetSafe: OFF")

        # ROS2 node
        class _NavNode(Node):
            def __init__(inner):
                super().__init__("gnm_fleetsafe_navigator")

                inner.sub_img  = inner.create_subscription(
                    Image, camera_topic,
                    self._cb_image, 1,
                )
                inner.sub_odom = inner.create_subscription(
                    Odometry, "/odom",
                    self._cb_odom, 10,
                )
                inner.sub_scan = inner.create_subscription(
                    LaserScan, "/scan",
                    self._cb_scan, 1,
                )
                inner.pub_cmd  = inner.create_publisher(Twist, cmd_topic, 1)
                inner.pub_status = inner.create_publisher(String, "/fleetsafe/status", 10)

                self._pub_cmd    = inner.pub_cmd
                self._pub_status = inner.pub_status

                inner.timer = inner.create_timer(1.0 / ctrl_hz, self._control_loop)
                inner.get_logger().info("GNM FleetSafe Navigator ready.")

        self._node = _NavNode()
        print(f"\n  ROS2 node ready.  Waiting for camera at {camera_topic}…")

    def _cb_image(self, msg) -> None:
        from PIL import Image as PILImage
        try:
            cv_img = self._bridge.imgmsg_to_cv2(msg, "rgb8")
            self._latest_img = PILImage.fromarray(cv_img)
        except Exception:
            pass

    def _cb_odom(self, msg) -> None:
        self._robot_x = msg.pose.pose.position.x
        self._robot_y = msg.pose.pose.position.y
        q = msg.pose.pose.orientation
        siny = 2.0 * (q.w * q.z + q.x * q.y)
        cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
        self._robot_yaw = math.atan2(siny, cosy)

    def _cb_scan(self, msg) -> None:
        angles = np.linspace(msg.angle_min, msg.angle_max,
                             len(msg.ranges), endpoint=True)
        ranges = np.array(msg.ranges, dtype=np.float32)
        valid  = np.isfinite(ranges) & (ranges > msg.range_min) & (ranges < msg.range_max)
        self._scan_ranges = ranges[valid]
        self._scan_angles = angles[valid]

    def _scan_to_obstacles(self) -> tuple[list, list]:
        """Convert LiDAR scan to obstacle positions for CBF."""
        if self._scan_ranges is None or len(self._scan_ranges) == 0:
            return [], []

        robot_x, robot_y, yaw = self._robot_x, self._robot_y, self._robot_yaw
        # Select prominent obstacles (min in each 30° sector)
        obs_positions, obs_radii = [], []
        n_sectors = 12
        sector_size = 2 * np.pi / n_sectors

        for i in range(n_sectors):
            lo  = -np.pi + i * sector_size
            hi  = lo + sector_size
            mask = (self._scan_angles >= lo) & (self._scan_angles < hi)
            if not np.any(mask):
                continue
            r_min = float(self._scan_ranges[mask].min())
            a_min = float(self._scan_angles[mask][self._scan_ranges[mask].argmin()])
            gx = robot_x + r_min * math.cos(yaw + a_min)
            gy = robot_y + r_min * math.sin(yaw + a_min)
            obs_positions.append(np.array([gx, gy]))
            obs_radii.append(0.2)  # nominal obstacle radius

        return obs_positions, obs_radii

    def _control_loop(self) -> None:
        """Called at control_hz Hz by the ROS2 timer."""
        from geometry_msgs.msg import Twist
        from std_msgs.msg import String

        if self._latest_img is None:
            return

        W, H = self._adapter.image_size

        # Push current frame to context queue
        frame_resized = self._latest_img.resize((W, H), __import__("PIL").Image.BILINEAR)
        self._cam_adapter.push_frame(frame_resized)
        obs_imgs, goal_img = self._cam_adapter.get_context()

        # Inference
        preprocessed = self._adapter.preprocess_observation(obs_imgs, goal_img)
        action       = self._adapter.predict_action(preprocessed)

        from fleet_safe_vla.integrations.visualnav_transformer.base_adapter import waypoints_to_cmd_vel
        raw_cmd = waypoints_to_cmd_vel(
            action.waypoints,
            v_max=self._v_max,
            w_max=self._w_max,
            control_hz=1.0 / self._dt,
        )

        # FleetSafe
        safe_vx, safe_wz = raw_cmd.vx, raw_cmd.wz
        intervened = False
        status_str = "OK"

        if self._cbf is not None:
            obs_positions, obs_radii = self._scan_to_obstacles()
            if obs_positions:
                robot_xy = np.array([self._robot_x, self._robot_y])
                obs_vec  = np.zeros(47)
                nominal  = np.array([raw_cmd.vx, raw_cmd.wz])
                safe_arr, info = self._cbf.filter(
                    obs_vec, nominal, obs_positions,
                    robot_xy=robot_xy, obstacle_radii=obs_radii,
                )
                safe_vx    = float(safe_arr[0])
                safe_wz    = float(safe_arr[1])
                intervened = info.get("intervened", False)
                if info.get("estop", False):
                    status_str = "ESTOP"
                elif intervened:
                    status_str = "IV"

        # Publish velocity
        twist = Twist()
        twist.linear.x  = float(safe_vx)
        twist.linear.y  = 0.0
        twist.angular.z = float(safe_wz)
        self._pub_cmd.publish(twist)

        # Publish FleetSafe status
        msg = String()
        msg.data = status_str
        self._pub_status.publish(msg)

    def spin(self) -> None:
        try:
            self._rclpy.spin(self._node)
        except KeyboardInterrupt:
            print("\n  Keyboard interrupt — stopping robot.")
        finally:
            # Send E-STOP
            from geometry_msgs.msg import Twist
            twist = Twist()
            self._pub_cmd.publish(twist)
            self._rclpy.shutdown()


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--model", type=str, default="gnm",
                   choices=["gnm", "vint", "nomad"])
    p.add_argument("--topomap", type=Path, default=None,
                   help="Topological map directory (from build_topomap.py)")
    p.add_argument("--goal-image", type=Path, default=None,
                   help="Single goal image (alternative to topomap)")
    p.add_argument("--fleetsafe", action="store_true",
                   help="Enable FleetSafe CBF-QP safety filter")
    p.add_argument("--v-max",  type=float, default=_MAX_V)
    p.add_argument("--w-max",  type=float, default=_MAX_W)
    p.add_argument("--d-safe", type=float, default=_D_SAFE)
    p.add_argument("--estop",  type=float, default=_ESTOP)
    p.add_argument("--hz",     type=float, default=_CTRL_HZ,
                   help="Control frequency Hz (default: 4)")
    p.add_argument("--camera-topic", type=str, default="/usb_cam/image_raw")
    p.add_argument("--cmd-topic",    type=str, default="/cmd_vel")
    args = p.parse_args()

    print()
    print("=" * 65)
    print("  GNM FleetSafe Navigator — ROS2 / Yahboom M3Pro")
    print("=" * 65)
    print(f"  Model   : {args.model.upper()}")
    print(f"  Safety  : {'FleetSafe ON' if args.fleetsafe else 'NO SAFETY FILTER'}")
    print(f"  Camera  : {args.camera_topic}")
    print(f"  Cmd vel : {args.cmd_topic}")
    print(f"  Hz      : {args.hz}")
    print()

    try:
        import rclpy  # noqa: F401
    except ImportError:
        print("ERROR: ROS2 (rclpy) not available.")
        print("       Source ROS2 first: source /opt/ros/humble/setup.bash")
        return 1

    nav = GNMNavigatorROS2(
        model_name   = args.model,
        topomap_dir  = args.topomap,
        goal_image   = args.goal_image,
        fleetsafe    = args.fleetsafe,
        v_max        = args.v_max,
        w_max        = args.w_max,
        d_safe       = args.d_safe,
        estop        = args.estop,
        ctrl_hz      = args.hz,
        camera_topic = args.camera_topic,
        cmd_topic    = args.cmd_topic,
    )
    nav.spin()
    return 0


if __name__ == "__main__":
    sys.exit(main())
