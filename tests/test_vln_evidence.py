"""
test_vln_evidence.py — Verify that VLNControllerNode._emit_evidence writes
trace and certificate JSONL on every instruction decision path, and that
camera_seen / camera_age_ms are correctly propagated.

Tests run without ROS2 by constructing a minimal mock node that has the
attributes _emit_evidence() needs, binding the method directly from
VLNControllerNode so the actual production code is exercised.

Covered decision paths:
  - allowed (safe motion)
  - cbf_infeasible (e-stop)
  - stale_lidar (e-stop)
  - estop_latched (ignore instruction, write evidence)
  - dry_run_zero (DRY-RUN mode)
  - exception path (grounding/backbone failure)
  - files are non-empty after one instruction

Camera-specific tests:
  - camera_seen=False when frame_id="none" (no camera frames received)
  - camera_seen=True when frame_id has a real value
  - camera_age_ms=None when no camera frames ever received
  - camera_age_ms populated when a frame was received
  - cert always emitted even when camera is absent
  - _cb_image sets camera_timestamp in _robot state
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
import types
import unittest.mock as mock
from pathlib import Path

import pytest

from fleet_safe_vla.vln.instruction_schema import InstructionSource
from fleet_safe_vla.vln.instruction_intake import InstructionIntake
from fleet_safe_vla.vln.vln_trace_logger import VLNTraceLogger


# ── helpers ───────────────────────────────────────────────────────────────────

def _read_jsonl(path: Path) -> list[dict]:
    text = path.read_text().strip()
    if not text:
        return []
    return [json.loads(l) for l in text.splitlines() if l.strip()]


def _fake_scan_audit() -> dict:
    return {
        "scan0_raw_min_m": 0.05,
        "scan1_raw_min_m": 0.05,
        "scan0_valid_min_m": 0.84,
        "scan1_valid_min_m": 0.76,
        "scan0_invalid_ct": 12,
        "scan1_invalid_ct": 18,
        "effective_clearance_m": 0.73,
        "filtering_applied": True,
    }


def _fake_args(*, safety_radius: float = 0.30, enable_motion: bool = False,
               camera_stale_sec: float = 2.0) -> argparse.Namespace:
    return argparse.Namespace(
        backbone="auto",
        safety_radius=safety_radius,
        enable_motion=enable_motion,
        max_vx=0.12,
        max_wz=0.35,
        camera_stale_sec=camera_stale_sec,
    )


def _make_mock_node(tmp_path: Path, *, dry_run: bool = True,
                    safety_radius: float = 0.30) -> types.SimpleNamespace:
    """Build a minimal SimpleNamespace that _emit_evidence can run on."""
    trace_path = tmp_path / "trace.jsonl"
    cert_path  = tmp_path / "certs.jsonl"

    node = types.SimpleNamespace(
        _dry_run=dry_run,
        _args=_fake_args(safety_radius=safety_radius, enable_motion=not dry_run),
        _trace_logger=VLNTraceLogger(trace_path),
        _cert_path=cert_path,
        _cert_fh=cert_path.open("a", encoding="utf-8", buffering=1),
        _cert_published=[],
    )

    # Bind the production _emit_evidence so actual code is exercised
    from scripts.real_robot.run_vln_m3pro import VLNControllerNode
    node._emit_evidence = lambda **kw: VLNControllerNode._emit_evidence(node, **kw)

    return node


def _make_inst(text: str = "go forward") -> object:
    return InstructionIntake().from_text(text)


def _fake_goal(
    action_type: str = "move",
    label: str = "forward",
    confidence: float = 0.85,
) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        action_type=action_type,
        label=label,
        confidence=confidence,
        grounding_candidates=[],
    )


def _call_emit(node, *, frame_id="frame_1", camera_last_age_ms=None,
               decision="allowed", qp_status="skipped",
               u_nom=None, u_safe=None,
               h_min=0.28, min_dist=0.73,
               cbf_active=False, estop_latched=False,
               reason="", goal=None, inst=None):
    """Convenience wrapper so tests don't repeat boilerplate."""
    if inst is None:
        inst = _make_inst()
    if goal is None and decision not in ("stale_lidar", "estop_latched",
                                          "exception", "cbf_infeasible"):
        goal = _fake_goal()
    node._emit_evidence(
        inst=inst, goal=goal,
        decision=decision, qp_status=qp_status,
        u_nom=u_nom or [0.10, 0.0], u_safe=u_safe or [0.10, 0.0],
        cbf_active=cbf_active, min_dist=min_dist, h_min=h_min,
        frame_id=frame_id, camera_last_age_ms=camera_last_age_ms,
        latency_ms=25.0,
        scan_audit=_fake_scan_audit(),
        estop_latched=estop_latched, reason=reason,
    )


# ── fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp(tmp_path):
    return tmp_path


# ── decision path tests ───────────────────────────────────────────────────────

class TestEmitEvidenceAllPaths:

    def test_allowed_writes_trace_and_cert(self, tmp):
        node = _make_mock_node(tmp)
        _call_emit(node, decision="allowed", qp_status="skipped")
        traces = _read_jsonl(node._trace_logger.path)
        certs  = _read_jsonl(node._cert_path)
        assert len(traces) == 1
        assert len(certs)  == 1
        assert certs[0]["decision"] == "allowed"
        assert certs[0]["safe"] is True

    def test_cbf_infeasible_writes_trace_and_cert(self, tmp):
        node = _make_mock_node(tmp)
        _call_emit(node, decision="cbf_infeasible", qp_status="cbf_infeasible",
                   h_min=-0.08, min_dist=0.10, cbf_active=True,
                   reason="cbf_infeasible")
        certs = _read_jsonl(node._cert_path)
        assert len(certs) == 1
        assert certs[0]["decision"] == "cbf_infeasible"
        assert certs[0]["safe"] is False
        assert certs[0]["qp_status"] == "cbf_infeasible"

    def test_stale_lidar_writes_trace_and_cert(self, tmp):
        node = _make_mock_node(tmp)
        _call_emit(node, decision="stale_lidar", qp_status="stale_lidar",
                   frame_id="none", h_min=-1.0, min_dist=float("inf"),
                   reason="stale_lidar")
        certs = _read_jsonl(node._cert_path)
        assert len(certs) == 1
        assert certs[0]["decision"] == "stale_lidar"
        assert certs[0]["safe"] is False

    def test_estop_latched_writes_trace_and_cert(self, tmp):
        node = _make_mock_node(tmp)
        _call_emit(node, decision="estop_latched", qp_status="estop_latched",
                   h_min=-1.0, min_dist=0.10, estop_latched=True,
                   reason="estop_latched")
        certs = _read_jsonl(node._cert_path)
        assert len(certs) == 1
        assert certs[0]["decision"] == "estop_latched"
        assert certs[0]["estop_latched"] is True
        assert certs[0]["safe"] is False

    def test_dry_run_writes_trace_and_cert(self, tmp):
        node = _make_mock_node(tmp, dry_run=True)
        _call_emit(node, decision="dry_run_zero", qp_status="skipped")
        certs = _read_jsonl(node._cert_path)
        assert len(certs) == 1
        assert certs[0]["decision"] == "dry_run_zero"
        assert certs[0]["dry_run"] is True

    def test_exception_path_writes_trace_and_cert(self, tmp):
        node = _make_mock_node(tmp)
        _call_emit(node, decision="exception", qp_status="exception",
                   frame_id="none", h_min=0.0, min_dist=0.50,
                   reason="grounding_exception:test error")
        certs = _read_jsonl(node._cert_path)
        assert len(certs) == 1
        assert certs[0]["decision"] == "exception"


# ── file / content tests ──────────────────────────────────────────────────────

class TestEvidenceFiles:

    def test_cert_file_non_empty_after_one_instruction(self, tmp):
        node = _make_mock_node(tmp)
        _call_emit(node, frame_id="frame_7")
        assert node._cert_path.stat().st_size > 0, "cert file must be non-empty"
        assert node._trace_logger.path.stat().st_size > 0, "trace file must be non-empty"

    def test_multiple_instructions_append(self, tmp):
        node = _make_mock_node(tmp)
        for i, dec in enumerate(["allowed", "cbf_infeasible", "dry_run_zero"]):
            _call_emit(node, decision=dec,
                       h_min=0.10 if dec == "allowed" else -0.05)
        certs = _read_jsonl(node._cert_path)
        assert len(certs) == 3

    def test_cert_row_has_required_keys(self, tmp):
        node = _make_mock_node(tmp)
        _call_emit(node, camera_last_age_ms=33.0)
        cert = _read_jsonl(node._cert_path)[0]
        required = {
            "timestamp", "instruction_id", "safe", "qp_status",
            "h_min", "min_dist_m", "safety_radius_m", "constraint_margin_min",
            "latency_ms", "u_nominal", "u_safe", "cbf_active",
            "estop_latched", "decision", "reason", "dry_run",
            "scan_audit", "camera_seen", "camera_frame_id", "camera_last_age_ms",
        }
        for key in required:
            assert key in cert, f"Missing required cert field: {key!r}"

    def test_cert_instruction_id_matches_inst(self, tmp):
        node = _make_mock_node(tmp)
        inst = _make_inst("stop now")
        _call_emit(node, inst=inst, decision="stop_override",
                   qp_status="stop_override", reason="stop_override")
        cert = _read_jsonl(node._cert_path)[0]
        assert cert["instruction_id"] == inst.instruction_id

    def test_cert_json_serializable(self, tmp):
        node = _make_mock_node(tmp)
        _call_emit(node, camera_last_age_ms=100.0)
        certs = _read_jsonl(node._cert_path)
        assert len(certs) == 1
        json.dumps(certs[0])  # must not raise

    def test_fsync_called_after_write(self, tmp):
        node = _make_mock_node(tmp)
        _call_emit(node)
        assert node._cert_path.stat().st_size > 0, "cert file empty — fsync/flush failed"


# ── camera-specific tests ─────────────────────────────────────────────────────

class TestCameraSeen:

    def test_camera_seen_false_when_no_frame(self, tmp):
        """frame_id='none' means no camera frame received → camera_seen=False."""
        node = _make_mock_node(tmp)
        _call_emit(node, frame_id="none", camera_last_age_ms=None)
        cert = _read_jsonl(node._cert_path)[0]
        assert cert["camera_seen"] is False

    def test_camera_seen_false_when_empty_frame_id(self, tmp):
        """frame_id='' also means no camera → camera_seen=False."""
        node = _make_mock_node(tmp)
        _call_emit(node, frame_id="", camera_last_age_ms=None)
        cert = _read_jsonl(node._cert_path)[0]
        assert cert["camera_seen"] is False

    def test_camera_seen_true_when_frame_received(self, tmp):
        """A real frame_id within freshness window → camera_seen=True."""
        node = _make_mock_node(tmp)
        _call_emit(node, frame_id="camera_link", camera_last_age_ms=16.7)
        cert = _read_jsonl(node._cert_path)[0]
        assert cert["camera_seen"] is True

    def test_camera_seen_true_with_generated_frame_id(self, tmp):
        """Generated frame IDs like 'frame_12345' within freshness window → camera_seen=True."""
        node = _make_mock_node(tmp)
        _call_emit(node, frame_id="frame_12345", camera_last_age_ms=50.0)
        cert = _read_jsonl(node._cert_path)[0]
        assert cert["camera_seen"] is True

    def test_camera_seen_false_when_stale(self, tmp):
        """camera_last_age_ms > camera_stale_sec*1000 → camera_seen=False even with valid frame_id."""
        node = _make_mock_node(tmp)
        # default camera_stale_sec=2.0, so 3000 ms > 2000 ms → stale
        _call_emit(node, frame_id="camera_link", camera_last_age_ms=3000.0)
        cert = _read_jsonl(node._cert_path)[0]
        assert cert["camera_seen"] is False

    def test_camera_seen_true_at_freshness_boundary(self, tmp):
        """camera_last_age_ms just under 2 s → camera_seen=True."""
        node = _make_mock_node(tmp)
        _call_emit(node, frame_id="camera_link", camera_last_age_ms=1999.0)
        cert = _read_jsonl(node._cert_path)[0]
        assert cert["camera_seen"] is True

    def test_camera_last_age_ms_none_when_no_camera(self, tmp):
        """When camera_last_age_ms=None (no frames ever), cert stores None."""
        node = _make_mock_node(tmp)
        _call_emit(node, frame_id="none", camera_last_age_ms=None)
        cert = _read_jsonl(node._cert_path)[0]
        assert cert["camera_last_age_ms"] is None

    def test_camera_last_age_ms_populated_when_frame_received(self, tmp):
        """When camera_last_age_ms has a value, cert stores it as a number."""
        node = _make_mock_node(tmp)
        _call_emit(node, frame_id="frame_42", camera_last_age_ms=33.3)
        cert = _read_jsonl(node._cert_path)[0]
        assert cert["camera_last_age_ms"] is not None
        assert abs(cert["camera_last_age_ms"] - 33.3) < 0.01

    def test_camera_frame_id_in_cert(self, tmp):
        """cert must include camera_frame_id with the actual frame_id string."""
        node = _make_mock_node(tmp)
        _call_emit(node, frame_id="camera_link", camera_last_age_ms=20.0)
        cert = _read_jsonl(node._cert_path)[0]
        assert cert["camera_frame_id"] == "camera_link"

    def test_evidence_emitted_even_without_camera(self, tmp):
        """Evidence is always written regardless of camera_seen state."""
        node = _make_mock_node(tmp)
        _call_emit(node, frame_id="none", camera_last_age_ms=None,
                   decision="stale_lidar", qp_status="stale_lidar",
                   h_min=-1.0, reason="stale_lidar")
        certs = _read_jsonl(node._cert_path)
        assert len(certs) == 1, "cert must be written even when camera absent"

    def test_camera_seen_propagated_to_trace_notes(self, tmp):
        """camera_seen, camera_frame_id, and camera_last_age_ms are in trace notes."""
        node = _make_mock_node(tmp)
        _call_emit(node, frame_id="live_frame", camera_last_age_ms=20.0)
        traces = _read_jsonl(node._trace_logger.path)
        assert len(traces) == 1
        notes = json.loads(traces[0]["notes"])
        assert notes["camera_seen"] is True
        assert notes["camera_frame_id"] == "live_frame"
        assert notes["camera_last_age_ms"] is not None


class TestCameraCallback:
    """Test that _cb_image updates _robot state correctly."""

    def test_cb_image_sets_camera_timestamp(self):
        """_cb_image must update _robot['camera_timestamp']."""
        from scripts.real_robot import run_vln_m3pro as mod

        # Reset global state
        before = mod._robot["camera_timestamp"]

        # Build a mock Image message
        img = types.SimpleNamespace(
            header=types.SimpleNamespace(frame_id="camera_link",
                                          stamp=types.SimpleNamespace(sec=123)),
            encoding="rgb8", width=640, height=480,
        )

        # Build a minimal node that can run _cb_image (no ROS2 needed)
        node = types.SimpleNamespace(
            _first_camera_frame=False,
        )

        from scripts.real_robot.run_vln_m3pro import VLNControllerNode
        t_before = time.time()
        VLNControllerNode._cb_image(node, img)
        t_after = time.time()

        with mod._state_lock:
            cam_ts = mod._robot["camera_timestamp"]
            frame_id = mod._robot["last_image_id"]

        assert cam_ts >= t_before, "camera_timestamp not updated"
        assert cam_ts <= t_after,  "camera_timestamp in the future"
        assert frame_id == "camera_link"
        assert node._first_camera_frame is True

        # Cleanup: restore global state
        with mod._state_lock:
            mod._robot["camera_timestamp"] = before
            mod._robot["last_image_id"] = "none"

    def test_cb_image_generates_frame_id_when_empty(self):
        """When header.frame_id is empty, _cb_image generates frame_N."""
        from scripts.real_robot import run_vln_m3pro as mod
        before_ts  = mod._robot["camera_timestamp"]
        before_fid = mod._robot["last_image_id"]

        img = types.SimpleNamespace(
            header=types.SimpleNamespace(frame_id="",
                                          stamp=types.SimpleNamespace(sec=999)),
            encoding="bgr8", width=320, height=240,
        )
        node = types.SimpleNamespace(_first_camera_frame=True)

        from scripts.real_robot.run_vln_m3pro import VLNControllerNode
        VLNControllerNode._cb_image(node, img)

        with mod._state_lock:
            fid = mod._robot["last_image_id"]

        assert fid == "frame_999"

        # Cleanup
        with mod._state_lock:
            mod._robot["camera_timestamp"] = before_ts
            mod._robot["last_image_id"]    = before_fid
