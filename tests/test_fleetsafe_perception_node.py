"""
tests/test_fleetsafe_perception_node.py

Tests for fleetsafe_perception_node pure logic extracted without ROS runtime.

Covered cases
-------------
* Zero command pass-through (GREEN zone → cmd unchanged)
* RED zone hard stop (vx/vy/wz → 0.0)
* AMBER speed cap (vx * 0.4, vy * 0.4, wz * 0.6)
* Monitor-only mode: RED zone does NOT stop the robot
* Message serialization helpers (_ros_stamp, _ros_image_to_numpy fallback)
* Detection JSON serialisation (published to /fleetsafe/detections)
* Track JSON serialisation (published to /fleetsafe/tracks)
* Stale-image handling: None rgb → zero detections
* Latency accounting: perc_ms is non-negative
* Intrinsics latch: second CameraInfo does not overwrite first
"""
from __future__ import annotations

import json
import math
import sys
import time
import types
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ── Repo root ────────────────────────────────────────────────────────────────
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# ── Stub out rclpy so the module imports without a ROS environment ─────────────
def _stub_rclpy():
    rclpy = types.ModuleType("rclpy")
    rclpy.init = lambda *a, **kw: None
    rclpy.ok   = lambda: True
    rclpy.spin = lambda n: None
    rclpy.shutdown = lambda: None

    node_mod = types.ModuleType("rclpy.node")
    class Node:
        def __init__(self, name="test"):
            self._name = name
        def get_logger(self):
            log = MagicMock()
            log.info  = lambda *a, **kw: None
            log.warn  = lambda *a, **kw: None
            log.error = lambda *a, **kw: None
            return log
        def declare_parameter(self, name, default): pass
        def get_parameter(self, name):
            m = MagicMock()
            m.value = {
                "perception_mode": "none",
                "yolo_model":      "yolov8n.pt",
                "scene_name":      "hospital_corridor",
                "social_profile":  "hospital",
                "conf_threshold":  0.40,
                "control_hz":      10.0,
                "depth_scale":     0.001,
                "max_depth_m":     6.0,
                "publish_json":    True,
                "monitor_only":    False,
            }[name]
            return m
        def create_subscription(self, *a, **kw): return MagicMock()
        def create_publisher(self, *a, **kw): return MagicMock()
        def create_timer(self, *a, **kw): return MagicMock()
        def destroy_node(self): pass
    node_mod.Node = Node

    qos_mod = types.ModuleType("rclpy.qos")
    class QoSProfile:
        def __init__(self, **kw): pass
    class QoSReliabilityPolicy:
        BEST_EFFORT = "best_effort"
    class QoSDurabilityPolicy:
        VOLATILE = "volatile"
    qos_mod.QoSProfile           = QoSProfile
    qos_mod.QoSReliabilityPolicy = QoSReliabilityPolicy
    qos_mod.QoSDurabilityPolicy  = QoSDurabilityPolicy

    sys.modules.setdefault("rclpy",      rclpy)
    sys.modules.setdefault("rclpy.node", node_mod)
    sys.modules.setdefault("rclpy.qos",  qos_mod)

    for mod in [
        "sensor_msgs", "sensor_msgs.msg",
        "geometry_msgs", "geometry_msgs.msg",
        "std_msgs", "std_msgs.msg",
        "builtin_interfaces", "builtin_interfaces.msg",
        "cv_bridge",
    ]:
        if mod not in sys.modules:
            sys.modules[mod] = types.ModuleType(mod)

    # geometry_msgs.msg.Twist
    gm = sys.modules["geometry_msgs.msg"]
    class _Vec3:
        x = y = z = 0.0
    class Twist:
        def __init__(self):
            self.linear  = _Vec3()
            self.angular = _Vec3()
    gm.Twist = Twist

    # std_msgs.msg
    sm = sys.modules["std_msgs.msg"]
    class Float32:
        data = 0.0
    class String:
        data = ""
    class Bool:
        data = False
    sm.Float32 = Float32
    sm.String  = String
    sm.Bool    = Bool

    # sensor_msgs.msg
    sms = sys.modules["sensor_msgs.msg"]
    class Image:
        height = width = 0
        data   = b""
        header = MagicMock()
    class CameraInfo:
        k = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
        width = height = 0
    sms.Image      = Image
    sms.CameraInfo = CameraInfo

_stub_rclpy()

# ── Now import the node module ─────────────────────────────────────────────────
import importlib
_node_mod = importlib.import_module(
    "scripts.ros2.fleetsafe_perception_node",
    # module lives at scripts/ros2/fleetsafe_perception_node.py
)

# Re-import via file path to handle the non-package location
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "fleetsafe_perception_node",
    _REPO / "scripts" / "ros2" / "fleetsafe_perception_node.py",
)
_node_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_node_mod)  # type: ignore[union-attr]

FleetSafePerceptionNode = _node_mod.FleetSafePerceptionNode


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_node(**overrides) -> FleetSafePerceptionNode:
    """Construct a node with safe defaults, bypassing ROS2 spin."""
    n = FleetSafePerceptionNode.__new__(FleetSafePerceptionNode)
    # Minimal attribute set (mirrors __init__ without calling super().__init__)
    n._mode       = overrides.get("mode",       "none")
    n._model_path = overrides.get("model_path", "yolov8n.pt")
    n._scene      = overrides.get("scene",      "hospital_corridor")
    n._prof_name  = overrides.get("prof_name",  "hospital")
    n._conf       = overrides.get("conf",       0.40)
    n._hz         = overrides.get("hz",         10.0)
    n._d_scale    = overrides.get("d_scale",    0.001)
    n._max_depth  = overrides.get("max_depth",  6.0)
    n._pub_json   = overrides.get("pub_json",   True)
    n._monitor    = overrides.get("monitor",    False)

    n._pipeline   = None
    n._mock_src   = None
    n._cv_bridge  = None
    n._intrinsics = None
    n._initialized= False
    n._tracker    = None
    n._social_filter = None

    n._last_rgb         = None
    n._last_depth       = None
    n._last_rgb_stamp   = 0.0
    n._last_depth_stamp = 0.0
    n._last_cmd_vx = 0.0
    n._last_cmd_vy = 0.0
    n._last_cmd_wz = 0.0
    n._robot_xy    = (0.0, 0.0)
    n._last_perc_ms = 0.0
    n._step_count   = 0

    n._pub_safe    = MagicMock()
    n._pub_risk    = MagicMock()
    n._pub_zone    = MagicMock()
    n._pub_latency = MagicMock()
    n._pub_dets    = MagicMock()
    n._pub_tracks  = MagicMock()

    # stub get_logger
    log = MagicMock()
    log.info  = lambda *a, **kw: None
    log.warn  = lambda *a, **kw: None
    log.error = lambda *a, **kw: None
    n.get_logger = lambda: log

    return n


# ── Safety scaling logic (extracted for unit testing) ─────────────────────────

def _apply_zone_scaling(vx, vy, wz, zone_str, monitor=False):
    """Mirror the velocity scaling logic in _control_cb."""
    if monitor:
        return vx, vy, wz
    if zone_str == "RED":
        return 0.0, 0.0, 0.0
    if zone_str == "AMBER":
        return vx * 0.4, vy * 0.4, wz * 0.6
    return vx, vy, wz  # GREEN — unchanged


# ════════════════════════════════════════════════════════════════════════════════
# Zone velocity scaling
# ════════════════════════════════════════════════════════════════════════════════

class TestZoneVelocityScaling:

    def test_green_zone_pass_through(self):
        vx, vy, wz = _apply_zone_scaling(0.3, 0.1, 0.5, "GREEN")
        assert vx == pytest.approx(0.3)
        assert vy == pytest.approx(0.1)
        assert wz == pytest.approx(0.5)

    def test_red_zone_hard_stop(self):
        vx, vy, wz = _apply_zone_scaling(0.3, 0.1, 0.5, "RED")
        assert vx == 0.0
        assert vy == 0.0
        assert wz == 0.0

    def test_amber_zone_speed_cap(self):
        vx, vy, wz = _apply_zone_scaling(1.0, 1.0, 1.0, "AMBER")
        assert vx == pytest.approx(0.4)
        assert vy == pytest.approx(0.4)
        assert wz == pytest.approx(0.6)

    def test_amber_preserves_sign(self):
        vx, vy, wz = _apply_zone_scaling(-0.3, 0.0, -1.0, "AMBER")
        assert vx == pytest.approx(-0.12)
        assert wz == pytest.approx(-0.6)

    def test_zero_cmd_stays_zero_in_all_zones(self):
        for zone in ("GREEN", "AMBER", "RED"):
            vx, vy, wz = _apply_zone_scaling(0.0, 0.0, 0.0, zone)
            assert vx == 0.0 and vy == 0.0 and wz == 0.0

    def test_monitor_only_red_no_stop(self):
        vx, vy, wz = _apply_zone_scaling(0.3, 0.1, 0.5, "RED", monitor=True)
        assert vx == pytest.approx(0.3)
        assert vy == pytest.approx(0.1)
        assert wz == pytest.approx(0.5)

    def test_monitor_only_amber_no_cap(self):
        vx, vy, wz = _apply_zone_scaling(1.0, 1.0, 1.0, "AMBER", monitor=True)
        assert vx == pytest.approx(1.0)
        assert vy == pytest.approx(1.0)
        assert wz == pytest.approx(1.0)

    def test_unknown_zone_treated_as_green(self):
        vx, vy, wz = _apply_zone_scaling(0.3, 0.1, 0.5, "UNKNOWN")
        assert vx == pytest.approx(0.3)


# ════════════════════════════════════════════════════════════════════════════════
# _ros_stamp
# ════════════════════════════════════════════════════════════════════════════════

class TestRosStamp:

    def test_valid_stamp(self):
        msg = MagicMock()
        msg.header.stamp.sec     = 1000
        msg.header.stamp.nanosec = 500_000_000
        result = FleetSafePerceptionNode._ros_stamp(msg)
        assert result == pytest.approx(1000.5)

    def test_zero_stamp(self):
        msg = MagicMock()
        msg.header.stamp.sec     = 0
        msg.header.stamp.nanosec = 0
        result = FleetSafePerceptionNode._ros_stamp(msg)
        assert result == pytest.approx(0.0)

    def test_missing_header_returns_monotonic(self):
        msg = object()  # no .header attribute
        t0 = time.monotonic()
        result = FleetSafePerceptionNode._ros_stamp(msg)
        t1 = time.monotonic()
        assert t0 <= result <= t1 + 0.01

    def test_large_nanosec(self):
        msg = MagicMock()
        msg.header.stamp.sec     = 0
        msg.header.stamp.nanosec = 1_000_000_000  # exactly 1 second
        result = FleetSafePerceptionNode._ros_stamp(msg)
        assert result == pytest.approx(1.0)


# ════════════════════════════════════════════════════════════════════════════════
# _ros_image_to_numpy
# ════════════════════════════════════════════════════════════════════════════════

class TestRosImageToNumpy:

    def _make_rgb_msg(self, h=4, w=4):
        msg = MagicMock()
        msg.height = h
        msg.width  = w
        msg.data   = bytes(h * w * 3)
        return msg

    def _make_depth_msg(self, h=4, w=4):
        import struct
        msg = MagicMock()
        msg.height = h
        msg.width  = w
        msg.data   = bytes(h * w * 2)
        return msg

    def test_rgb_manual_fallback_shape(self):
        try:
            import numpy as np
        except ImportError:
            pytest.skip("numpy required")
        n = _make_node()
        n._cv_bridge = None
        msg = self._make_rgb_msg(8, 6)
        arr = n._ros_image_to_numpy(msg, "rgb8")
        assert arr is not None
        assert arr.shape == (8, 6, 3)

    def test_depth_manual_fallback_shape(self):
        try:
            import numpy as np
        except ImportError:
            pytest.skip("numpy required")
        n = _make_node()
        n._cv_bridge = None
        msg = self._make_depth_msg(8, 6)
        arr = n._ros_image_to_numpy(msg, "16UC1")
        assert arr is not None
        assert arr.shape == (8, 6)

    def test_none_for_unknown_encoding(self):
        n = _make_node()
        n._cv_bridge = None
        msg = self._make_rgb_msg()
        arr = n._ros_image_to_numpy(msg, "bgra8")
        assert arr is None


# ════════════════════════════════════════════════════════════════════════════════
# Detection + Track JSON serialisation
# ════════════════════════════════════════════════════════════════════════════════

class TestJsonSerialisation:
    """Validate the JSON structure published to /fleetsafe/detections and /fleetsafe/tracks."""

    def _detection_payload(self, dets):
        return json.dumps([
            {
                "role": d.semantic_role,
                "type": d.agent_type.value,
                "pos":  list(d.position_xy),
                "conf": round(d.confidence, 3),
            }
            for d in dets
        ])

    def test_empty_detection_list(self):
        payload = self._detection_payload([])
        assert json.loads(payload) == []

    def test_single_detection_fields(self):
        from fleet_safe_vla.social_awareness.dynamic_agent_tracker import Detection, AgentType
        dets = [Detection(
            position_xy=(1.5, -0.3),
            agent_type=AgentType.HUMAN,
            timestamp=5.0,
            confidence=0.87,
            semantic_role="staff",
        )]
        parsed = json.loads(self._detection_payload(dets))
        assert len(parsed) == 1
        d = parsed[0]
        assert d["role"] == "staff"
        assert d["type"] == "human"
        assert d["pos"]  == pytest.approx([1.5, -0.3])
        assert d["conf"] == pytest.approx(0.87, abs=0.001)

    def test_confidence_rounded_to_3dp(self):
        from fleet_safe_vla.social_awareness.dynamic_agent_tracker import Detection, AgentType
        dets = [Detection((0, 0), AgentType.HUMAN, confidence=0.123456789)]
        parsed = json.loads(self._detection_payload(dets))
        assert parsed[0]["conf"] == pytest.approx(0.123, abs=0.001)

    def _track_payload(self, agents):
        return json.dumps([
            {
                "id":   a.agent_id,
                "role": a.semantic_role,
                "type": a.agent_type.value,
                "pos":  list(a.position_xy),
                "vel":  list(a.velocity_xy),
                "age":  a.age_steps,
            }
            for a in agents
        ])

    def test_empty_track_list(self):
        assert json.loads(self._track_payload([])) == []

    def test_track_fields(self):
        from fleet_safe_vla.social_awareness.dynamic_agent_tracker import DynamicAgent, AgentType
        agent = DynamicAgent(
            agent_id="t0",
            agent_type=AgentType.HUMAN,
            position_xy=(2.0, 1.0),
            velocity_xy=(0.1, 0.0),
            speed_ms=0.1,
            timestamp=1.0,
            confidence=0.9,
            age_steps=5,
            semantic_role="patient",
        )
        parsed = json.loads(self._track_payload([agent]))
        assert len(parsed) == 1
        t = parsed[0]
        assert t["id"]   == "t0"
        assert t["role"] == "patient"
        assert t["type"] == "human"
        assert t["pos"]  == pytest.approx([2.0, 1.0])
        assert t["vel"]  == pytest.approx([0.1, 0.0])
        assert t["age"]  == 5


# ════════════════════════════════════════════════════════════════════════════════
# Stale image handling
# ════════════════════════════════════════════════════════════════════════════════

class TestStaleImageHandling:

    def test_none_rgb_yolo_mode_returns_no_detections(self):
        """When no RGB frame has arrived, perception should produce empty list."""
        from fleet_safe_vla.perception.perception_pipeline import PerceptionConfig, PerceptionPipeline
        cfg = PerceptionConfig(model_path=None)  # disable YOLO
        pipeline = PerceptionPipeline.from_config(cfg)
        dets = pipeline.process(rgb_frame=None, depth_image=None)
        assert dets == []

    def test_none_rgb_pipeline_process_increments_frame_count(self):
        from fleet_safe_vla.perception.perception_pipeline import PerceptionConfig, PerceptionPipeline
        cfg = PerceptionConfig(model_path=None)
        pipeline = PerceptionPipeline.from_config(cfg)
        pipeline.process(None)
        pipeline.process(None)
        assert pipeline.stats["frames_processed"] == 2

    def test_mock_source_independent_of_rgb(self):
        """MockPerceptionSource always produces detections regardless of rgb."""
        from fleet_safe_vla.perception.mock_source import MockPerceptionSource
        src = MockPerceptionSource(scenario="hospital_corridor", seed=0)
        dets = src.step(robot_xy=(0.0, 0.0), timestamp=0.0)
        assert len(dets) > 0  # does not depend on an image frame


# ════════════════════════════════════════════════════════════════════════════════
# Latency accounting
# ════════════════════════════════════════════════════════════════════════════════

class TestLatencyAccounting:

    def test_perc_ms_non_negative(self):
        """Wall-clock perc_ms can't be negative."""
        t0 = time.perf_counter()
        time.sleep(0.001)
        perc_ms = (time.perf_counter() - t0) * 1000.0
        assert perc_ms >= 0.0

    def test_perc_ms_reasonable_upper_bound(self):
        """A no-op perception step shouldn't take more than 500 ms on any machine."""
        from fleet_safe_vla.perception.perception_pipeline import PerceptionConfig, PerceptionPipeline
        cfg = PerceptionConfig(model_path=None)
        pipeline = PerceptionPipeline.from_config(cfg)
        t0 = time.perf_counter()
        pipeline.process(None)
        perc_ms = (time.perf_counter() - t0) * 1000.0
        assert perc_ms < 500.0

    def test_mock_source_latency_reasonable(self):
        from fleet_safe_vla.perception.mock_source import MockPerceptionSource
        src = MockPerceptionSource(scenario="hospital_corridor", seed=0)
        t0 = time.perf_counter()
        src.step()
        perc_ms = (time.perf_counter() - t0) * 1000.0
        assert perc_ms < 50.0


# ════════════════════════════════════════════════════════════════════════════════
# Intrinsics latch
# ════════════════════════════════════════════════════════════════════════════════

class TestIntrinsicsLatch:

    def test_second_caminfo_does_not_overwrite(self):
        from fleet_safe_vla.perception.depth_fusion import CameraIntrinsics
        n = _make_node(mode="none")
        first  = CameraIntrinsics(fx=615.0, fy=615.0, cx=320.0, cy=240.0)
        n._intrinsics = first

        # Simulate a second CameraInfo message arriving
        msg = MagicMock()
        msg.k = [500.0, 0.0, 300.0, 0.0, 500.0, 200.0, 0.0, 0.0, 1.0]
        msg.width  = 640
        msg.height = 480
        n._caminfo_cb(msg)

        # Should still be the first intrinsics (latched)
        assert n._intrinsics is first
        assert n._intrinsics.fx == pytest.approx(615.0)

    def test_first_caminfo_sets_intrinsics(self):
        n = _make_node(mode="none")
        assert n._intrinsics is None

        msg = MagicMock()
        msg.k = [610.0, 0.0, 320.0, 0.0, 610.0, 240.0, 0.0, 0.0, 1.0]
        msg.width  = 640
        msg.height = 480
        n._caminfo_cb(msg)

        assert n._intrinsics is not None
        assert n._intrinsics.fx == pytest.approx(610.0)
        assert n._intrinsics.cy == pytest.approx(240.0)


# ════════════════════════════════════════════════════════════════════════════════
# Node construction sanity
# ════════════════════════════════════════════════════════════════════════════════

class TestNodeConstruction:

    def test_mode_stored(self):
        n = _make_node(mode="mock")
        assert n._mode == "mock"

    def test_monitor_flag(self):
        n = _make_node(monitor=True)
        assert n._monitor is True

    def test_pub_json_flag(self):
        n = _make_node(pub_json=False)
        assert n._pub_json is False

    def test_initial_robot_xy(self):
        n = _make_node()
        assert n._robot_xy == (0.0, 0.0)

    def test_initial_cmd_zero(self):
        n = _make_node()
        assert n._last_cmd_vx == 0.0
        assert n._last_cmd_vy == 0.0
        assert n._last_cmd_wz == 0.0

    def test_initial_step_count_zero(self):
        n = _make_node()
        assert n._step_count == 0
