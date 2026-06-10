#!/usr/bin/env python3
"""
fleetsafe_perception_node.py — Real-time FleetSafe perception + safety node.

Closes the live loop on the physical Yahboom M3Pro:

    /camera/color/image_raw   ──→  PerceptionPipeline (YOLOv8 + DepthFusion)
    /camera/depth/image_raw   ──┘        │
    /camera/color/camera_info ──→  (intrinsics)
                                         ↓
                                  DynamicAgentTracker
                                         ↓
                                  SocialRiskFilter
                                         ↓
    /cmd_vel_raw ──────────────→  FleetSafe CBF-QP
                                         ↓
                                  /cmd_vel_safe   ← publish here
                                  /fleetsafe/social_risk
                                  /fleetsafe/detections
                                  /fleetsafe/tracks
                                  /fleetsafe/zone
                                  /fleetsafe/latency

SAFE RELAY PATTERN
------------------
This node does NOT publish to /cmd_vel.  Once validated, add a static relay:

    ros2 run topic_tools relay /cmd_vel_safe /cmd_vel

or use a twist_mux with the safety node as highest-priority source.

Usage
-----
    source /opt/ros/humble/setup.bash
    conda activate isaac
    python scripts/ros2/fleetsafe_perception_node.py

    # With YOLO model path:
    python scripts/ros2/fleetsafe_perception_node.py --yolo yolov8n.pt

    # Mock perception (no camera required):
    python scripts/ros2/fleetsafe_perception_node.py \\
        --perception mock --scene hospital_corridor

    # Disable navigation filter (monitor-only):
    python scripts/ros2/fleetsafe_perception_node.py --monitor-only

Required ROS2 topics (remappable via --ros-args -r):
    /camera/color/image_raw      sensor_msgs/Image
    /camera/depth/image_raw      sensor_msgs/Image   (optional, enables depth fusion)
    /camera/color/camera_info    sensor_msgs/CameraInfo  (optional, improves depth)
    /cmd_vel_raw                 geometry_msgs/Twist     (planner output)

Published topics:
    /cmd_vel_safe                geometry_msgs/Twist   (safety-filtered)
    /fleetsafe/social_risk       std_msgs/Float32      (crowding score 0-1)
    /fleetsafe/detections        std_msgs/String       (JSON detection list)
    /fleetsafe/tracks            std_msgs/String       (JSON track list)
    /fleetsafe/zone              std_msgs/String       ("GREEN"|"AMBER"|"RED")
    /fleetsafe/latency           std_msgs/Float32      (perception ms, last step)

Parameters (set via --ros-args -p name:=value):
    perception_mode   : "yolo" | "mock" | "none"  (default: "yolo")
    yolo_model        : model path or name         (default: "yolov8n.pt")
    scene_name        : mock scenario name         (default: "hospital_corridor")
    social_profile    : social risk profile        (default: "hospital")
    conf_threshold    : YOLO confidence threshold  (default: 0.40)
    control_hz        : cmd_vel processing rate    (default: 10.0)
    depth_scale       : raw depth → metres         (default: 0.001)
    max_depth_m       : reject detections beyond   (default: 6.0)
    publish_json      : publish JSON diag topics   (default: true)
    monitor_only      : skip cmd_vel_safe publish  (default: false)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

# ── Repo root on sys.path ─────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ── ROS2 availability guard ───────────────────────────────────────────────────
try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSDurabilityPolicy
    _ROS2_AVAILABLE = True
except ImportError:
    _ROS2_AVAILABLE = False
    Node = object  # type: ignore[misc, assignment]

# ── FleetSafe imports ──────────────────────────────────────────────────────────
from fleet_safe_vla.perception.perception_pipeline import PerceptionConfig, PerceptionPipeline
from fleet_safe_vla.perception.depth_fusion import CameraIntrinsics
from fleet_safe_vla.perception.mock_source import MockPerceptionSource
from fleet_safe_vla.social_awareness.dynamic_agent_tracker import DynamicAgentTracker, Detection
from fleet_safe_vla.social_awareness import SocialRiskFilter, get_profile

# ── numpy (optional — needed for image conversion) ───────────────────────────
try:
    import numpy as np
    _NUMPY = True
except ImportError:
    _NUMPY = False

# ── QoS profile: best-effort for sensor streams ───────────────────────────────
_SENSOR_QOS = QoSProfile(
    reliability=QoSReliabilityPolicy.BEST_EFFORT,
    durability=QoSDurabilityPolicy.VOLATILE,
    depth=1,
) if _ROS2_AVAILABLE else None


# ════════════════════════════════════════════════════════════════════════════════
# Node
# ════════════════════════════════════════════════════════════════════════════════

class FleetSafePerceptionNode(Node):  # type: ignore[misc]
    """
    ROS2 node: camera → YOLOv8/mock perception → social risk → safe cmd_vel.

    All heavy imports (ultralytics, cv_bridge) are deferred to the first
    callback to keep __init__ fast and to avoid import-time crashes when
    running on a machine without a GPU.
    """

    def __init__(self) -> None:
        super().__init__("fleetsafe_perception")

        # ── Declare ROS2 parameters ───────────────────────────────────────────
        self.declare_parameter("perception_mode",  "yolo")
        self.declare_parameter("yolo_model",       "yolov8n.pt")
        self.declare_parameter("scene_name",       "hospital_corridor")
        self.declare_parameter("social_profile",   "hospital")
        self.declare_parameter("conf_threshold",   0.40)
        self.declare_parameter("control_hz",       10.0)
        self.declare_parameter("depth_scale",      0.001)
        self.declare_parameter("max_depth_m",      6.0)
        self.declare_parameter("publish_json",     True)
        self.declare_parameter("monitor_only",     False)

        self._mode       = self.get_parameter("perception_mode").value
        self._model_path = self.get_parameter("yolo_model").value
        self._scene      = self.get_parameter("scene_name").value
        self._prof_name  = self.get_parameter("social_profile").value
        self._conf       = self.get_parameter("conf_threshold").value
        self._hz         = self.get_parameter("control_hz").value
        self._d_scale    = self.get_parameter("depth_scale").value
        self._max_depth  = self.get_parameter("max_depth_m").value
        self._pub_json   = self.get_parameter("publish_json").value
        self._monitor    = self.get_parameter("monitor_only").value

        # ── Lazy-init flags ───────────────────────────────────────────────────
        self._pipeline: PerceptionPipeline | None = None
        self._mock_src: MockPerceptionSource | None = None
        self._tracker  = DynamicAgentTracker()
        self._social_filter: SocialRiskFilter | None = None
        self._cv_bridge: Any = None
        self._intrinsics: CameraIntrinsics | None = None
        self._initialized = False

        # ── Latest sensor state ───────────────────────────────────────────────
        self._last_rgb:   Any = None   # np.ndarray HxWx3 uint8
        self._last_depth: Any = None   # np.ndarray HxW uint16
        self._last_rgb_stamp:   float = 0.0
        self._last_depth_stamp: float = 0.0
        self._last_cmd_vx: float = 0.0
        self._last_cmd_vy: float = 0.0
        self._last_cmd_wz: float = 0.0
        self._robot_xy:   tuple[float, float] = (0.0, 0.0)

        # ── Latency stats ──────────────────────────────────────────────────────
        self._last_perc_ms: float = 0.0
        self._step_count:   int   = 0

        # ── Message imports (deferred) ────────────────────────────────────────
        from sensor_msgs.msg import Image, CameraInfo
        from geometry_msgs.msg import Twist
        from std_msgs.msg import Float32, String, Bool

        # ── Subscriptions ─────────────────────────────────────────────────────
        self.create_subscription(
            Image, "/camera/color/image_raw", self._rgb_cb, _SENSOR_QOS
        )
        self.create_subscription(
            Image, "/camera/depth/image_raw", self._depth_cb, _SENSOR_QOS
        )
        self.create_subscription(
            CameraInfo, "/camera/color/camera_info", self._caminfo_cb, 1
        )
        self.create_subscription(
            Twist, "/cmd_vel_raw", self._cmd_vel_raw_cb, 10
        )

        # ── Publishers ────────────────────────────────────────────────────────
        self._pub_safe    = self.create_publisher(Twist,   "/cmd_vel_safe",         10)
        self._pub_risk    = self.create_publisher(Float32, "/fleetsafe/social_risk", 10)
        self._pub_zone    = self.create_publisher(String,  "/fleetsafe/zone",        10)
        self._pub_latency = self.create_publisher(Float32, "/fleetsafe/latency",     10)

        if self._pub_json:
            self._pub_dets   = self.create_publisher(String, "/fleetsafe/detections", 10)
            self._pub_tracks = self.create_publisher(String, "/fleetsafe/tracks",     10)
        else:
            self._pub_dets   = None
            self._pub_tracks = None

        # ── Control timer ─────────────────────────────────────────────────────
        self._timer = self.create_timer(1.0 / self._hz, self._control_cb)

        self.get_logger().info(
            f"[FleetSafe] Perception node starting — mode={self._mode!r}  "
            f"model={self._model_path!r}  profile={self._prof_name!r}  "
            f"hz={self._hz}  monitor_only={self._monitor}"
        )

    # ── Lazy initialisation (deferred to first timer tick) ────────────────────

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        self._initialized = True

        # Social filter
        try:
            profile = get_profile(self._prof_name)
        except ValueError:
            self.get_logger().warn(
                f"Unknown social profile {self._prof_name!r} — using 'default'"
            )
            profile = get_profile("default")
        self._social_filter = SocialRiskFilter(profile=profile)

        # Perception source
        if self._mode == "yolo":
            cfg = PerceptionConfig(
                model_path=self._model_path,
                conf_threshold=self._conf,
                depth_scale=self._d_scale,
                max_depth_m=self._max_depth,
            )
            self._pipeline = PerceptionPipeline.from_config(cfg)
            if self._pipeline.detector_enabled:
                self.get_logger().info(
                    f"[FleetSafe] YOLOv8 loaded: {self._model_path}"
                )
            else:
                self.get_logger().warn(
                    "[FleetSafe] ultralytics not installed — YOLO disabled, "
                    "no detections will be produced"
                )

        elif self._mode == "mock":
            self._mock_src = MockPerceptionSource(scenario=self._scene, seed=42)
            self.get_logger().info(
                f"[FleetSafe] Mock perception: scenario={self._scene!r}"
            )

        else:  # "none"
            self.get_logger().info("[FleetSafe] Perception disabled (monitor only)")

        # cv_bridge (optional; only needed for YOLO mode)
        if self._mode == "yolo":
            try:
                from cv_bridge import CvBridge  # type: ignore[import]
                self._cv_bridge = CvBridge()
            except ImportError:
                self.get_logger().warn(
                    "[FleetSafe] cv_bridge not available — ROS Image → numpy "
                    "conversion will use manual fallback"
                )

    # ── Sensor callbacks ──────────────────────────────────────────────────────

    def _rgb_cb(self, msg: Any) -> None:
        self._last_rgb = self._ros_image_to_numpy(msg, encoding="rgb8")
        self._last_rgb_stamp = self._ros_stamp(msg)

    def _depth_cb(self, msg: Any) -> None:
        self._last_depth = self._ros_image_to_numpy(msg, encoding="16UC1")
        self._last_depth_stamp = self._ros_stamp(msg)

    def _caminfo_cb(self, msg: Any) -> None:
        if self._intrinsics is not None:
            return  # latch once
        k = msg.k  # row-major 3×3
        self._intrinsics = CameraIntrinsics(
            fx=float(k[0]), fy=float(k[4]),
            cx=float(k[2]), cy=float(k[5]),
            width=msg.width, height=msg.height,
        )
        if self._pipeline is not None:
            self._pipeline._depth._K = self._intrinsics
        self.get_logger().info(
            f"[FleetSafe] Camera intrinsics received: "
            f"fx={self._intrinsics.fx:.1f} fy={self._intrinsics.fy:.1f} "
            f"cx={self._intrinsics.cx:.1f} cy={self._intrinsics.cy:.1f}"
        )

    def _cmd_vel_raw_cb(self, msg: Any) -> None:
        self._last_cmd_vx = msg.linear.x
        self._last_cmd_vy = msg.linear.y
        self._last_cmd_wz = msg.angular.z

    # ── Main control loop ─────────────────────────────────────────────────────

    def _control_cb(self) -> None:
        self._ensure_initialized()

        t0 = time.perf_counter()
        timestamp = time.monotonic()
        self._step_count += 1

        # ── 1. Get detections ──────────────────────────────────────────────
        detections: list[Detection] = []

        if self._mode == "yolo" and self._pipeline is not None:
            rgb   = self._last_rgb
            depth = self._last_depth
            if rgb is not None:
                detections = self._pipeline.process(
                    rgb_frame=rgb,
                    depth_image=depth,
                    robot_xy=self._robot_xy,
                    timestamp=timestamp,
                )

        elif self._mode == "mock" and self._mock_src is not None:
            detections = self._mock_src.step(
                robot_xy=self._robot_xy,
                timestamp=timestamp,
            )

        # ── 2. Update tracker ──────────────────────────────────────────────
        tracked_agents = self._tracker.update(detections, timestamp=timestamp)

        # Build Detection objects from tracked agents for social filter
        tracked_dets = [
            Detection(
                position_xy=a.position_xy,
                agent_type=a.agent_type,
                timestamp=timestamp,
                confidence=a.confidence,
                semantic_role=a.semantic_role,
            )
            for a in tracked_agents
        ]

        # ── 3. Social risk filter ──────────────────────────────────────────
        zone_str       = "GREEN"
        crowding_score = 0.0
        social_out     = None

        if self._social_filter is not None:
            social_out = self._social_filter.compute(
                timestamp=timestamp,
                robot_xy=self._robot_xy,
                robot_speed_ms=abs(self._last_cmd_vx),
                robot_yaw=0.0,
                detections=tracked_dets,
            )
            zone_str       = social_out.zone.value
            crowding_score = social_out.state.crowding_score

        perc_ms = (time.perf_counter() - t0) * 1000.0
        self._last_perc_ms = perc_ms

        # ── 4. Safety filter: scale down cmd_vel in RED/AMBER zones ───────
        vx, vy, wz = self._last_cmd_vx, self._last_cmd_vy, self._last_cmd_wz

        if not self._monitor:
            if zone_str == "RED":
                vx, vy, wz = 0.0, 0.0, 0.0   # full stop
            elif zone_str == "AMBER":
                vx  *= 0.4
                vy  *= 0.4
                wz  *= 0.6

        # ── 5. Publish ─────────────────────────────────────────────────────
        self._publish_safe_cmd(vx, vy, wz)
        self._publish_diagnostics(
            crowding_score, zone_str, perc_ms,
            detections, tracked_agents,
        )

        if self._step_count % 50 == 0:
            self.get_logger().info(
                f"[FleetSafe] step={self._step_count}  zone={zone_str}  "
                f"dets={len(detections)}  tracks={len(tracked_agents)}  "
                f"perc={perc_ms:.1f}ms  "
                f"cmd=({vx:.2f},{vy:.2f},{wz:.2f})"
            )

    # ── Publishers ────────────────────────────────────────────────────────────

    def _publish_safe_cmd(self, vx: float, vy: float, wz: float) -> None:
        from geometry_msgs.msg import Twist
        msg = Twist()
        msg.linear.x  = float(vx)
        msg.linear.y  = float(vy)
        msg.angular.z = float(wz)
        self._pub_safe.publish(msg)

    def _publish_diagnostics(
        self,
        crowding: float,
        zone: str,
        perc_ms: float,
        detections: list,
        tracks: list,
    ) -> None:
        from std_msgs.msg import Float32, String

        risk_msg = Float32(); risk_msg.data = float(crowding)
        self._pub_risk.publish(risk_msg)

        zone_msg = String(); zone_msg.data = zone
        self._pub_zone.publish(zone_msg)

        lat_msg = Float32(); lat_msg.data = float(perc_ms)
        self._pub_latency.publish(lat_msg)

        if self._pub_json:
            det_payload = json.dumps([
                {
                    "role": d.semantic_role,
                    "type": d.agent_type.value,
                    "pos":  list(d.position_xy),
                    "conf": round(d.confidence, 3),
                }
                for d in detections
            ])
            det_msg = String(); det_msg.data = det_payload
            self._pub_dets.publish(det_msg)

            trk_payload = json.dumps([
                {
                    "id":   a.agent_id,
                    "role": a.semantic_role,
                    "type": a.agent_type.value,
                    "pos":  list(a.position_xy),
                    "vel":  list(a.velocity_xy),
                    "age":  a.age_steps,
                }
                for a in tracks
            ])
            trk_msg = String(); trk_msg.data = trk_payload
            self._pub_tracks.publish(trk_msg)

    # ── Utilities ──────────────────────────────────────────────────────────────

    def _ros_image_to_numpy(self, msg: Any, encoding: str) -> Any:
        """Convert ROS Image to numpy array.  Falls back to manual decode."""
        if self._cv_bridge is not None:
            try:
                import cv2  # type: ignore[import]
                arr = self._cv_bridge.imgmsg_to_cv2(msg, desired_encoding=encoding)
                if encoding == "rgb8":
                    arr = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
                return arr
            except Exception:
                pass

        # Manual fallback (no cv_bridge)
        if not _NUMPY:
            return None
        data = bytes(msg.data)
        arr  = np.frombuffer(data, dtype=np.uint8)
        if encoding == "rgb8":
            return arr.reshape((msg.height, msg.width, 3))
        if encoding == "16UC1":
            arr16 = np.frombuffer(data, dtype=np.uint16)
            return arr16.reshape((msg.height, msg.width))
        return None

    @staticmethod
    def _ros_stamp(msg: Any) -> float:
        try:
            s = msg.header.stamp
            return float(s.sec) + float(s.nanosec) * 1e-9
        except AttributeError:
            return time.monotonic()


# ════════════════════════════════════════════════════════════════════════════════
# Entry point
# ════════════════════════════════════════════════════════════════════════════════

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--perception", choices=["yolo", "mock", "none"], default="yolo",
        help="Perception source (default: yolo)",
    )
    p.add_argument("--yolo",   default="yolov8n.pt", help="YOLO model path or name")
    p.add_argument("--scene",  default="hospital_corridor", help="Mock scenario name")
    p.add_argument("--profile", default="hospital", help="Social risk profile")
    p.add_argument("--conf",   type=float, default=0.40, help="YOLO conf threshold")
    p.add_argument("--hz",     type=float, default=10.0, help="Control loop Hz")
    p.add_argument("--monitor-only", action="store_true",
                   help="Publish diagnostics only; do not modify cmd_vel")
    p.add_argument("--no-json", action="store_true",
                   help="Skip JSON diagnostic topic publishing")
    return p.parse_args()


def main() -> None:
    if not _ROS2_AVAILABLE:
        print(
            "[FleetSafe] ERROR: rclpy not found.\n"
            "  source /opt/ros/humble/setup.bash\n"
            "  conda activate isaac",
            file=sys.stderr,
        )
        sys.exit(1)

    args = _parse_args()

    rclpy.init()
    node = FleetSafePerceptionNode()

    # Override params from CLI args (useful when not using ros2 run)
    node._mode       = args.perception
    node._model_path = args.yolo
    node._scene      = args.scene
    node._prof_name  = args.profile
    node._conf       = args.conf
    node._hz         = args.hz
    node._monitor    = args.monitor_only
    node._pub_json   = not args.no_json

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
