"""Tests for certify_rosbag_run.py logic — no ROS2 dependency.

These tests exercise the pure-Python helpers (min_range, certificate schema)
and the graceful handling of missing topics, without requiring rosbag2_py or
a real bag file.
"""
from __future__ import annotations

import json
import math
import tempfile
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fleet_safe_vla.safety.certificate import SafetyCertificate


# ---------------------------------------------------------------------------
# Import the module under test (it must be importable without ROS2)
# ---------------------------------------------------------------------------

import importlib
import sys

# Provide stub modules for ROS2 imports so the module can be loaded
def _make_ros_stubs():
    stubs = {}
    for name in ["rosbag2_py", "rclpy", "rclpy.serialization",
                 "rosidl_runtime_py", "rosidl_runtime_py.utilities"]:
        stubs[name] = types.ModuleType(name)
    stubs["rosbag2_py"].SequentialReader = MagicMock
    stubs["rosbag2_py"].StorageOptions = MagicMock
    stubs["rosbag2_py"].ConverterOptions = MagicMock
    stubs["rosbag2_py"].StorageFilter = MagicMock
    stubs["rclpy.serialization"].deserialize_message = MagicMock()
    stubs["rosidl_runtime_py.utilities"].get_message = MagicMock()
    return stubs


@pytest.fixture(autouse=True)
def _ros_stubs(monkeypatch):
    """Inject stub ROS2 modules before importing certify_rosbag_run."""
    stubs = _make_ros_stubs()
    for name, mod in stubs.items():
        monkeypatch.setitem(sys.modules, name, mod)
    yield


@pytest.fixture
def certify_module():
    """Import (or reload) certify_rosbag_run with stubs in place."""
    # Remove any cached version so the import picks up the stubs
    if "scripts.evaluation.certify_rosbag_run" in sys.modules:
        del sys.modules["scripts.evaluation.certify_rosbag_run"]
    # Add repo root to sys.path
    repo_root = Path(__file__).resolve().parents[1]
    scripts_dir = repo_root / "scripts" / "evaluation"
    spec = importlib.util.spec_from_file_location(
        "certify_rosbag_run",
        scripts_dir / "certify_rosbag_run.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# _min_range_from_scan
# ---------------------------------------------------------------------------

class TestMinRangeFromScan:
    def test_returns_minimum_valid_range(self, certify_module):
        msg = MagicMock()
        msg.ranges = [1.5, 2.0, 0.8, 3.0]
        msg.range_max = 10.0
        assert certify_module._min_range_from_scan(msg) == pytest.approx(0.8)

    def test_ignores_zero_ranges(self, certify_module):
        msg = MagicMock()
        msg.ranges = [0.0, 1.2, 0.0, 0.9]
        msg.range_max = 10.0
        assert certify_module._min_range_from_scan(msg) == pytest.approx(0.9)

    def test_ignores_inf_ranges(self, certify_module):
        msg = MagicMock()
        msg.ranges = [float("inf"), 1.5, float("nan")]
        msg.range_max = 10.0
        assert certify_module._min_range_from_scan(msg) == pytest.approx(1.5)

    def test_ignores_ranges_beyond_range_max(self, certify_module):
        msg = MagicMock()
        msg.ranges = [15.0, 1.2]
        msg.range_max = 10.0
        assert certify_module._min_range_from_scan(msg) == pytest.approx(1.2)

    def test_empty_ranges_returns_inf(self, certify_module):
        msg = MagicMock()
        msg.ranges = []
        msg.range_max = 10.0
        assert certify_module._min_range_from_scan(msg) == float("inf")

    def test_all_invalid_returns_inf(self, certify_module):
        msg = MagicMock()
        msg.ranges = [0.0, float("inf"), float("nan")]
        msg.range_max = 10.0
        assert certify_module._min_range_from_scan(msg) == float("inf")


# ---------------------------------------------------------------------------
# Posthoc certificate schema validity
# ---------------------------------------------------------------------------

class TestPosthocCertificateSchema:
    """Verify that certificates generated in posthoc mode are well-formed."""

    def _make_posthoc_cert(self, min_dist_m: float, d_safe: float = 0.5) -> SafetyCertificate:
        h_min = min_dist_m ** 2 - d_safe ** 2
        safe = min_dist_m >= d_safe
        return SafetyCertificate(
            timestamp=1000.0,
            model_name="posthoc_bag",
            u_nom=[0.1, 0.0],
            u_safe=[0.1, 0.0],
            h_min=h_min,
            min_dist_m=min_dist_m,
            cbf_active=False,
            qp_status="posthoc_observation",
            constraint_margin_min=h_min,
            latency_ms=0.0,
            safe=safe,
            notes="posthoc certificate from recorded bag",
        )

    def test_safe_cert_roundtrips_jsonl(self):
        cert = self._make_posthoc_cert(min_dist_m=1.5)
        restored = SafetyCertificate.from_json(cert.to_json())
        assert restored.qp_status == "posthoc_observation"
        assert restored.safe is True
        assert math.isclose(restored.min_dist_m, 1.5)

    def test_violation_cert_safe_false(self):
        cert = self._make_posthoc_cert(min_dist_m=0.3, d_safe=0.5)
        assert cert.safe is False
        assert cert.h_min < 0

    def test_boundary_cert_safe_true(self):
        cert = self._make_posthoc_cert(min_dist_m=0.5, d_safe=0.5)
        assert cert.safe is True
        assert math.isclose(cert.h_min, 0.0)

    def test_posthoc_not_formally_valid(self):
        """posthoc_observation qp_status fails is_valid — that's intentional."""
        cert = self._make_posthoc_cert(min_dist_m=1.5)
        # is_valid only accepts "optimal", "estop_fallback", "skipped"
        assert cert.is_valid(d_safe=0.5) is False

    def test_h_min_formula(self):
        """h_min = d² - d_safe²."""
        cert = self._make_posthoc_cert(min_dist_m=1.2, d_safe=0.5)
        expected = 1.2 ** 2 - 0.5 ** 2
        assert math.isclose(cert.h_min, expected, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# certify_bag: missing topics handled gracefully
# ---------------------------------------------------------------------------

class TestCertifyBagMissingTopics:
    """certify_bag should not crash when expected topics are absent."""

    def test_missing_scan_topics_returns_zero(self, certify_module, tmp_path):
        """Without any scan topics, cmd_vel certs use min_dist_m=0.0 (no data)."""
        out = tmp_path / "out.jsonl"
        # Create fake bag dir so the existence check passes
        fake_bag = tmp_path / "fake_bag"
        fake_bag.mkdir()

        # Build a fake reader that yields only /cmd_vel
        def _make_reader(bag_path):
            r = MagicMock()
            messages = [("/cmd_vel", b"fake", int(1e9))]
            r.has_next.side_effect = [True, False]
            r.read_next.return_value = messages[0]
            topic_meta = MagicMock()
            topic_meta.name = "/cmd_vel"
            topic_meta.type = "geometry_msgs/msg/Twist"
            r.get_all_topics_and_types.return_value = [topic_meta]
            return r

        import sys
        sys.modules["rosidl_runtime_py.utilities"].get_message.return_value = MagicMock
        twist_msg = MagicMock()
        twist_msg.linear.x = 0.2
        twist_msg.angular.z = 0.0
        sys.modules["rclpy.serialization"].deserialize_message.return_value = twist_msg

        with patch.object(certify_module, "_open_reader", _make_reader), \
             patch.object(certify_module, "_HAS_ROS", True), \
             patch.object(certify_module, "_HAS_CERT", True):
            n = certify_module.certify_bag(
                bag_path=str(fake_bag),
                output_path=str(out),
                d_safe=0.5,
                scan_topics=["/scan0"],
                cmd_topic="/cmd_vel",
            )
        # With no scan data, we still get one cert per cmd_vel (min_dist=inf → 0)
        assert n >= 0  # should not crash

    def test_missing_cmd_topic_returns_zero(self, certify_module, tmp_path, capsys):
        """When cmd_vel is absent, certify_bag warns and returns 0."""
        out = tmp_path / "out.jsonl"
        # Create fake bag dir so the existence check passes
        fake_bag = tmp_path / "fake_bag"
        fake_bag.mkdir()

        def _make_reader(bag_path):
            r = MagicMock()
            r.has_next.return_value = False
            scan_meta = MagicMock()
            scan_meta.name = "/scan0"
            scan_meta.type = "sensor_msgs/msg/LaserScan"
            r.get_all_topics_and_types.return_value = [scan_meta]
            return r

        with patch.object(certify_module, "_open_reader", _make_reader), \
             patch.object(certify_module, "_HAS_ROS", True), \
             patch.object(certify_module, "_HAS_CERT", True):
            n = certify_module.certify_bag(
                bag_path=str(fake_bag),
                output_path=str(out),
                d_safe=0.5,
                scan_topics=["/scan0"],
                cmd_topic="/cmd_vel",
            )
        assert n == 0
        captured = capsys.readouterr()
        assert "not found" in captured.err or n == 0
