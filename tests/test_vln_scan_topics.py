"""
test_vln_scan_topics.py — Verify scan/odom topic detection and the per-slot
scan callback introduced by --scan-topics / --odom-topic support.

Covers:
  - Default --scan-topics is /scan0,/scan1
  - Default --odom-topic is /odom_raw
  - _make_scan_cb(slot=0) writes to scan0_sample / scan0_raw_min
  - _make_scan_cb(slot=1) writes to scan1_sample / scan1_raw_min
  - scan_clearance = min(slot0, slot1) when both are populated
  - scan_clearance = slot0 effective when only slot0 has data
  - scan_clearance = slot1 effective when only slot1 has data
  - scan_timestamp is updated on every callback
  - _publish_zero does not raise when _HAS_ROS2 is False
  - _publish_zero does not raise when no _pub_cmd attribute
  - _publish_zero catches exceptions from publish() (invalid context)
  - detect_scan_topics.sh selects /scan0,/scan1 when both present
  - detect_scan_topics.sh falls back to /scan,/scan_multi
"""
from __future__ import annotations

import time
import types
import unittest.mock as mock
from pathlib import Path

import pytest

import scripts.real_robot.run_vln_m3pro as mod
from fleet_safe_vla.safety.lidar_sanitizer import sanitize as _lidar_sanitize


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_scan_state():
    """Reset scan-related _robot entries to pristine state."""
    with mod._state_lock:
        mod._robot["scan0_sample"]  = None
        mod._robot["scan1_sample"]  = None
        mod._robot["scan0_raw_min"] = float("inf")
        mod._robot["scan1_raw_min"] = float("inf")
        mod._robot["scan_clearance"] = float("inf")
        mod._robot["scan_timestamp"] = 0.0


def _fake_scan_msg(ranges: list[float], range_min: float = 0.05, range_max: float = 10.0):
    """Return a minimal LaserScan-like object."""
    return types.SimpleNamespace(ranges=ranges, range_min=range_min, range_max=range_max)


def _get_cb(slot: int):
    """Return the closure from _make_scan_cb(slot) bound to a dummy node."""
    dummy = types.SimpleNamespace()
    return mod.VLNControllerNode._make_scan_cb(dummy, slot)


# ---------------------------------------------------------------------------
# Argument default tests
# ---------------------------------------------------------------------------

class TestArgDefaults:
    def test_scan_topics_default(self):
        """--scan-topics default must be /scan0,/scan1."""
        assert mod.args_cli.scan_topics == "/scan0,/scan1"

    def test_odom_topic_default(self):
        """--odom-topic default must be /odom_raw."""
        assert mod.args_cli.odom_topic == "/odom_raw"


# ---------------------------------------------------------------------------
# Per-slot scan callback tests
# ---------------------------------------------------------------------------

class TestScanCbSlots:
    def setup_method(self):
        _reset_scan_state()

    def test_slot0_writes_to_scan0(self):
        """Slot-0 callback must update scan0_sample and scan0_raw_min."""
        cb = _get_cb(slot=0)
        msg = _fake_scan_msg([1.0, 1.2, 0.9])
        cb(msg)
        with mod._state_lock:
            assert mod._robot["scan0_sample"] is not None
            assert mod._robot["scan1_sample"] is None   # untouched
            assert mod._robot["scan0_raw_min"] < float("inf")

    def test_slot1_writes_to_scan1(self):
        """Slot-1 callback must update scan1_sample and scan1_raw_min."""
        cb = _get_cb(slot=1)
        msg = _fake_scan_msg([0.8, 0.9, 1.0])
        cb(msg)
        with mod._state_lock:
            assert mod._robot["scan1_sample"] is not None
            assert mod._robot["scan0_sample"] is None   # untouched
            assert mod._robot["scan1_raw_min"] < float("inf")

    def test_clearance_is_min_of_both_slots(self):
        """scan_clearance = min(slot0.effective, slot1.effective)."""
        cb0 = _get_cb(slot=0)
        cb1 = _get_cb(slot=1)
        # Wide-open scan for slot0, tighter scan for slot1
        cb0(_fake_scan_msg([2.0, 2.1, 2.2]))
        cb1(_fake_scan_msg([0.5, 0.6, 0.7]))
        with mod._state_lock:
            s0 = mod._robot["scan0_sample"]
            s1 = mod._robot["scan1_sample"]
            assert s0 is not None and s1 is not None
            expected = min(s0.effective_clearance_m, s1.effective_clearance_m)
            assert abs(mod._robot["scan_clearance"] - expected) < 1e-9

    def test_clearance_from_slot0_only(self):
        """With only slot0 data, scan_clearance must equal slot0 effective."""
        cb0 = _get_cb(slot=0)
        cb0(_fake_scan_msg([1.5, 1.6, 1.4]))
        with mod._state_lock:
            s0 = mod._robot["scan0_sample"]
            assert s0 is not None
            assert abs(mod._robot["scan_clearance"] - s0.effective_clearance_m) < 1e-9

    def test_clearance_from_slot1_only(self):
        """With only slot1 data, scan_clearance must equal slot1 effective."""
        cb1 = _get_cb(slot=1)
        cb1(_fake_scan_msg([0.7, 0.8, 0.9]))
        with mod._state_lock:
            s1 = mod._robot["scan1_sample"]
            assert s1 is not None
            assert abs(mod._robot["scan_clearance"] - s1.effective_clearance_m) < 1e-9

    def test_scan_timestamp_updated(self):
        """scan_timestamp must be updated to approximately now on every callback."""
        t_before = time.time()
        cb0 = _get_cb(slot=0)
        cb0(_fake_scan_msg([1.0]))
        t_after = time.time()
        with mod._state_lock:
            ts = mod._robot["scan_timestamp"]
        assert t_before <= ts <= t_after + 0.1

    def test_slot0_overwrites_on_repeated_calls(self):
        """Repeated slot-0 calls must overwrite the slot-0 sample (not accumulate)."""
        cb0 = _get_cb(slot=0)
        cb0(_fake_scan_msg([2.0, 2.1]))
        cb0(_fake_scan_msg([0.6, 0.7]))
        with mod._state_lock:
            s0 = mod._robot["scan0_sample"]
            assert s0 is not None
            # The second (closer) scan must now be active
            assert s0.effective_clearance_m < 1.0


# ---------------------------------------------------------------------------
# _publish_zero safety tests
# ---------------------------------------------------------------------------

class TestPublishZeroSafety:
    def test_no_crash_when_has_ros2_false(self):
        """_publish_zero must silently return when _HAS_ROS2 is False."""
        with mock.patch.object(mod, "_HAS_ROS2", False):
            node = types.SimpleNamespace()
            mod.VLNControllerNode._publish_zero(node)  # must not raise

    def test_no_crash_without_pub_cmd_attribute(self):
        """_publish_zero must silently return when node has no _pub_cmd."""
        node = types.SimpleNamespace()  # no _pub_cmd
        mod.VLNControllerNode._publish_zero(node)  # must not raise

    def test_catches_publish_exception(self):
        """_publish_zero must catch exceptions from publish() (e.g. invalid context)."""
        exploding_pub = types.SimpleNamespace(
            publish=mock.MagicMock(side_effect=RuntimeError("context invalid"))
        )
        node = types.SimpleNamespace(_pub_cmd=exploding_pub)
        with mock.patch.object(mod, "_HAS_ROS2", True):
            mock_rclpy = mock.MagicMock()
            mock_rclpy.ok.return_value = True
            original_rclpy = getattr(mod, "rclpy", None)
            try:
                mod.rclpy = mock_rclpy  # type: ignore[attr-defined]
                mod.VLNControllerNode._publish_zero(node)  # must not raise
            finally:
                if original_rclpy is not None:
                    mod.rclpy = original_rclpy  # type: ignore[attr-defined]

    def test_skips_publish_when_rclpy_not_ok(self):
        """_publish_zero must not call publish() when rclpy.ok() returns False."""
        mock_pub = mock.MagicMock()
        node = types.SimpleNamespace(_pub_cmd=mock_pub)
        with mock.patch.object(mod, "_HAS_ROS2", True):
            mock_rclpy = mock.MagicMock()
            mock_rclpy.ok.return_value = False
            original_rclpy = getattr(mod, "rclpy", None)
            try:
                mod.rclpy = mock_rclpy  # type: ignore[attr-defined]
                mod.VLNControllerNode._publish_zero(node)
            finally:
                if original_rclpy is not None:
                    mod.rclpy = original_rclpy  # type: ignore[attr-defined]
        mock_pub.publish.assert_not_called()


# ---------------------------------------------------------------------------
# detect_scan_topics.sh content tests (no ROS required)
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
DETECT_SCRIPT = REPO_ROOT / "scripts/live/detect_scan_topics.sh"


class TestDetectScanTopicsScript:
    def test_script_exists(self):
        assert DETECT_SCRIPT.exists(), "detect_scan_topics.sh not found"

    def test_script_detects_scan0_scan1(self):
        content = DETECT_SCRIPT.read_text()
        assert "/scan0" in content and "/scan1" in content
        assert "FLEETSAFE_SCAN_TOPICS" in content

    def test_script_detects_scan_scan_multi_fallback(self):
        content = DETECT_SCRIPT.read_text()
        assert "/scan_multi" in content, \
            "detect_scan_topics.sh must handle /scan,/scan_multi layout"

    def test_script_exports_odom_topic(self):
        content = DETECT_SCRIPT.read_text()
        assert "FLEETSAFE_ODOM_TOPIC" in content
        assert "/odom_raw" in content
        assert "/odom" in content

    def test_script_outputs_shell_assignments(self):
        """Script must output 'VAR=value' lines that can be sourced."""
        content = DETECT_SCRIPT.read_text()
        assert 'echo "FLEETSAFE_SCAN_TOPICS=' in content
        assert 'echo "FLEETSAFE_ODOM_TOPIC=' in content

    def test_run_vln_desktop_sources_detect_script(self):
        """run_vln_desktop.sh must source detect_scan_topics.sh."""
        desktop = (REPO_ROOT / "scripts/live/run_vln_desktop.sh").read_text()
        assert "detect_scan_topics.sh" in desktop

    def test_run_vln_desktop_passes_scan_topics_to_controller(self):
        """run_vln_desktop.sh must pass --scan-topics to run_vln_m3pro.py."""
        desktop = (REPO_ROOT / "scripts/live/run_vln_desktop.sh").read_text()
        assert "--scan-topics" in desktop

    def test_run_vln_desktop_passes_odom_topic_to_controller(self):
        """run_vln_desktop.sh must pass --odom-topic to run_vln_m3pro.py."""
        desktop = (REPO_ROOT / "scripts/live/run_vln_desktop.sh").read_text()
        assert "--odom-topic" in desktop

    def test_preflight_sources_detect_script(self):
        """preflight_live_motion.sh must source detect_scan_topics.sh."""
        content = (REPO_ROOT / "scripts/live/preflight_live_motion.sh").read_text()
        assert "detect_scan_topics.sh" in content

    def test_preflight_checks_ssh_reachability(self):
        """preflight_live_motion.sh must check Jetson SSH reachability."""
        content = (REPO_ROOT / "scripts/live/preflight_live_motion.sh").read_text()
        assert "fleetsafe-jetson" in content
        assert "SSH" in content or "ssh" in content

    def test_check_vln_stack_uses_detected_topics(self):
        """check_vln_stack.sh must use FLEETSAFE_SCAN_TOPICS from detection."""
        content = (REPO_ROOT / "scripts/live/check_vln_stack.sh").read_text()
        assert "FLEETSAFE_SCAN_TOPICS" in content or "detect_scan_topics" in content

    def test_controller_has_scan_topics_arg(self):
        """run_vln_m3pro.py must define --scan-topics argument."""
        content = (REPO_ROOT / "scripts/real_robot/run_vln_m3pro.py").read_text()
        assert "--scan-topics" in content

    def test_controller_has_odom_topic_arg(self):
        """run_vln_m3pro.py must define --odom-topic argument."""
        content = (REPO_ROOT / "scripts/real_robot/run_vln_m3pro.py").read_text()
        assert "--odom-topic" in content

    def test_controller_publish_zero_guards_rclpy_ok(self):
        """_publish_zero must check rclpy.ok() before publishing."""
        content = (REPO_ROOT / "scripts/real_robot/run_vln_m3pro.py").read_text()
        assert "rclpy.ok()" in content, \
            "_publish_zero must guard publish with rclpy.ok() check"
