"""
ROS2 bridge — single rclpy node subscribing to all FleetSafe topics.

Graceful: entire module is a no-op if rclpy is not importable.
Provides a thread-safe cache dict and is_live() for telemetry.

Topics (all published by fleetsafe_perception_node.py):
  /fleetsafe/zone         std_msgs/String  JSON {"zone","step",...}
  /fleetsafe/social_risk  std_msgs/String  JSON {"risk","crowding_risk",...}
  /fleetsafe/latency      std_msgs/String  JSON {"inference_ms","perception_ms",...}
  /fleetsafe/detections   std_msgs/String  JSON [{"id","role","x","y",...},...]
  /fleetsafe/tracks       std_msgs/String  JSON [{"id","x","y","vx","vy",...},...]
  /cmd_vel_safe           geometry_msgs/Twist
  /odom_raw               nav_msgs/Odometry  (or std_msgs/String JSON)
  /battery                sensor_msgs/BatteryState  (or std_msgs/Float32)

Camera topics (forward-facing, egocentric — model input for VLN):
  /usb_cam/image_raw      sensor_msgs/Image  — M3Pro USB camera (primary)
  /camera/image_raw       sensor_msgs/Image  — fallback topic name
  /usb_cam/image_raw/compressed  sensor_msgs/CompressedImage  — compressed path
"""
from __future__ import annotations

import base64
import io
import json
import math
import threading
import time
from typing import Any

_rclpy_available = False
_bridge_started   = False
_lock = threading.Lock()

# ── Camera frame cache (forward-facing robot camera for VLN) ──────────────────
# Stores the latest JPEG data-URI from the real M3Pro USB camera.
# Written by the ROS2 camera callback; read by the demo telemetry generator.

_camera_lock  = threading.Lock()
_camera_b64: str = ""         # latest "data:image/jpeg;base64,..." or ""
_camera_ts:  float = 0.0      # monotonic timestamp of last camera frame


def get_camera_b64(max_age_s: float = 0.5) -> str:
    """Return the latest robot camera frame as a data-URI, or '' if stale/absent."""
    with _camera_lock:
        if _camera_b64 and (time.monotonic() - _camera_ts) < max_age_s:
            return _camera_b64
    return ""


def _set_camera_b64(b64: str) -> None:
    with _camera_lock:
        global _camera_b64, _camera_ts
        _camera_b64 = b64
        _camera_ts  = time.monotonic()

# Canonical cache — written by ROS2 callbacks, read by telemetry generator
_cache: dict[str, Any] = {
    "zone":               "GREEN",
    "risk":               0.0,
    "crowding_risk":      0.0,
    "occlusion_risk":     0.0,
    "intervention_active": False,
    "detection_count":    0,
    "tracked_count":      0,
    "cmd_vel":            {"vx": 0.0, "vy": 0.0, "wz": 0.0},
    "odom":               {"x": 0.0, "y": 0.0, "heading": 0.0},
    "battery_pct":        None,   # None = not available
    "battery_charging":   False,
    "latency_ms":         0.0,
    "perception_latency_ms": 0.0,
    "sim_fps":            0.0,
    "detections":         [],
    "tracks":             [],
    "last_update":        0.0,    # monotonic timestamp of most recent msg
    "source":             "mock",
}


def is_live(max_age_s: float = 2.0) -> bool:
    """True if a ROS2 message was received within max_age_s."""
    return _cache["source"] == "ros2" and (time.monotonic() - _cache["last_update"]) < max_age_s


def get_snapshot() -> dict[str, Any]:
    with _lock:
        return dict(_cache)


def _update(**kwargs: Any) -> None:
    with _lock:
        _cache.update(kwargs)
        _cache["last_update"] = time.monotonic()
        _cache["source"] = "ros2"


def _parse_json(data: str) -> dict | list | None:
    try:
        return json.loads(data)
    except Exception:
        return None


# ── ROS2 node ─────────────────────────────────────────────────────────────────

def _spin_node() -> None:
    global _rclpy_available
    try:
        import rclpy
        from rclpy.node import Node
        from std_msgs.msg import String as RosStr, Float32
        from geometry_msgs.msg import Twist
    except ImportError:
        return

    _rclpy_available = True

    try:
        rclpy.init(args=[])
    except Exception:
        return

    node = rclpy.create_node("cc_ros2_bridge")

    # /fleetsafe/zone
    def _zone_cb(msg: "RosStr") -> None:
        d = _parse_json(msg.data)
        if not isinstance(d, dict):
            return
        zone = d.get("zone", "GREEN")
        _update(
            zone=zone,
            intervention_active=(zone == "RED"),
        )

    # /fleetsafe/social_risk
    def _risk_cb(msg: "RosStr") -> None:
        d = _parse_json(msg.data)
        if not isinstance(d, dict):
            return
        _update(
            risk=float(d.get("risk", 0.0)),
            crowding_risk=float(d.get("crowding_risk", 0.0)),
            occlusion_risk=float(d.get("occlusion_risk", 0.0)),
            detection_count=int(d.get("detection_count", 0)),
            tracked_count=int(d.get("tracked_count", 0)),
        )

    # /fleetsafe/latency
    def _latency_cb(msg: "RosStr") -> None:
        d = _parse_json(msg.data)
        if not isinstance(d, dict):
            return
        _update(
            latency_ms=float(d.get("inference_ms", d.get("latency_ms", 0.0))),
            perception_latency_ms=float(d.get("perception_ms", 0.0)),
            sim_fps=float(d.get("sim_fps", 0.0)),
        )

    # /fleetsafe/detections
    def _det_cb(msg: "RosStr") -> None:
        d = _parse_json(msg.data)
        if isinstance(d, list):
            _update(detections=d, detection_count=len(d))

    # /fleetsafe/tracks
    def _tracks_cb(msg: "RosStr") -> None:
        d = _parse_json(msg.data)
        if isinstance(d, list):
            _update(tracks=d, tracked_count=len(d))

    # /cmd_vel_safe
    def _cmd_vel_cb(msg: "Twist") -> None:
        _update(cmd_vel={
            "vx": round(float(msg.linear.x),  4),
            "vy": round(float(msg.linear.y),  4),
            "wz": round(float(msg.angular.z), 4),
        })

    # /odom_raw — try nav_msgs/Odometry first, fall back to std_msgs/String JSON
    def _odom_str_cb(msg: "RosStr") -> None:
        d = _parse_json(msg.data)
        if isinstance(d, dict):
            _update(odom={
                "x":       float(d.get("x", 0.0)),
                "y":       float(d.get("y", 0.0)),
                "heading": float(d.get("heading", 0.0)),
            })

    # /battery — try BatteryState, fall back to Float32 percentage
    def _battery_f32_cb(msg: "Float32") -> None:
        pct = float(msg.data)
        _update(battery_pct=round(pct, 1), battery_charging=(pct > 100.0))

    def _battery_str_cb(msg: "RosStr") -> None:
        d = _parse_json(msg.data)
        if isinstance(d, dict):
            _update(
                battery_pct=float(d.get("percentage", d.get("pct", 0.0))),
                battery_charging=bool(d.get("charging", False)),
            )

    # ── Forward-facing camera (VLN model input) ───────────────────────────────
    # Subscribes to the M3Pro's USB camera.  Both raw and compressed topics are
    # tried; whichever the robot publishes will supply frames.
    try:
        from sensor_msgs.msg import Image as RosImage, CompressedImage

        def _camera_raw_cb(msg: "RosImage") -> None:
            try:
                from PIL import Image as PIL_Image
                # sensor_msgs/Image: encoding is typically "rgb8" or "bgr8"
                encoding = msg.encoding.lower()
                data = bytes(msg.data)
                if encoding in ("rgb8", "bgr8", "bgr8; jpeg-compressed"):
                    pil_img = PIL_Image.frombytes(
                        "RGB", (msg.width, msg.height), data, "raw",
                        "RGB" if encoding == "rgb8" else "BGR",
                    )
                elif encoding == "mono8":
                    pil_img = PIL_Image.frombytes(
                        "L", (msg.width, msg.height), data
                    ).convert("RGB")
                else:
                    # Try raw bytes regardless of encoding declaration
                    pil_img = PIL_Image.frombytes("RGB", (msg.width, msg.height), data)
                buf = io.BytesIO()
                pil_img.save(buf, format="JPEG", quality=72)
                _set_camera_b64(
                    "data:image/jpeg;base64,"
                    + base64.b64encode(buf.getvalue()).decode()
                )
            except Exception:
                pass

        def _camera_compressed_cb(msg: "CompressedImage") -> None:
            try:
                # CompressedImage.data is already JPEG bytes for "jpeg" format
                raw = bytes(msg.data)
                _set_camera_b64(
                    "data:image/jpeg;base64," + base64.b64encode(raw).decode()
                )
            except Exception:
                pass

        node.create_subscription(RosImage,        "/usb_cam/image_raw",              _camera_raw_cb,        10)
        node.create_subscription(RosImage,        "/camera/image_raw",               _camera_raw_cb,        10)
        node.create_subscription(CompressedImage, "/usb_cam/image_raw/compressed",   _camera_compressed_cb, 10)
        node.create_subscription(CompressedImage, "/camera/image_raw/compressed",    _camera_compressed_cb, 10)
    except Exception:
        pass  # sensor_msgs not available — camera feed will be absent

    qos = 10
    node.create_subscription(RosStr,  "/fleetsafe/zone",        _zone_cb,    qos)
    node.create_subscription(RosStr,  "/fleetsafe/social_risk",  _risk_cb,    qos)
    node.create_subscription(RosStr,  "/fleetsafe/latency",      _latency_cb, qos)
    node.create_subscription(RosStr,  "/fleetsafe/detections",   _det_cb,     qos)
    node.create_subscription(RosStr,  "/fleetsafe/tracks",       _tracks_cb,  qos)
    node.create_subscription(Twist,   "/cmd_vel_safe",           _cmd_vel_cb, qos)
    node.create_subscription(RosStr,  "/odom_raw",               _odom_str_cb, qos)
    node.create_subscription(Float32, "/battery",                _battery_f32_cb, qos)
    node.create_subscription(RosStr,  "/battery",                _battery_str_cb, qos)

    try:
        rclpy.spin(node)
    except Exception:
        pass
    finally:
        node.destroy_node()
        try:
            rclpy.shutdown()
        except Exception:
            pass


def start() -> None:
    """Start the ROS2 bridge thread (idempotent)."""
    global _bridge_started
    if _bridge_started:
        return
    _bridge_started = True
    t = threading.Thread(target=_spin_node, daemon=True, name="ros2_bridge")
    t.start()
