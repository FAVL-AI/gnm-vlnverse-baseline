"""
test_vln_estop.py — Verify the e-stop latch and clear workflow.

Covered:
  - e-stop cert has safe=False, estop_latched=True, decision=estop_latched
  - _cb_estop_clear resets latch when LiDAR clearance >= safety_radius
  - _cb_estop_clear refuses to clear when clearance < safety_radius
  - _cb_estop_clear is a no-op when latch was not set
  - voice instruction after clear produces safe=True cert
  - certificate includes all required audit fields:
      source, camera_seen, camera_frame_id, camera_last_age_ms,
      scan_audit, u_nominal, u_safe
"""
from __future__ import annotations

import argparse
import json
import types
from pathlib import Path

import pytest

from fleet_safe_vla.vln.instruction_intake import InstructionIntake
from fleet_safe_vla.vln.vln_trace_logger import VLNTraceLogger


# ── helpers (mirrors test_vln_evidence.py pattern) ────────────────────────────

def _read_jsonl(path: Path) -> list[dict]:
    text = path.read_text().strip()
    if not text:
        return []
    return [json.loads(l) for l in text.splitlines() if l.strip()]


def _fake_scan_audit() -> dict:
    return {
        "scan0_raw_min_m": 0.10,
        "scan1_raw_min_m": 0.10,
        "scan0_valid_min_m": 0.84,
        "scan1_valid_min_m": 0.76,
        "scan0_invalid_ct": 5,
        "scan1_invalid_ct": 8,
        "effective_clearance_m": 0.80,
        "filtering_applied": True,
    }


def _fake_args(safety_radius: float = 0.30, camera_stale_sec: float = 2.0) -> argparse.Namespace:
    return argparse.Namespace(
        backbone="auto",
        safety_radius=safety_radius,
        enable_motion=False,
        max_vx=0.12,
        max_wz=0.35,
        camera_stale_sec=camera_stale_sec,
    )


def _make_mock_node(tmp_path: Path, *, safety_radius: float = 0.30) -> types.SimpleNamespace:
    trace_path = tmp_path / "trace.jsonl"
    cert_path  = tmp_path / "certs.jsonl"
    node = types.SimpleNamespace(
        _dry_run=True,
        _args=_fake_args(safety_radius=safety_radius),
        _trace_logger=VLNTraceLogger(trace_path),
        _cert_path=cert_path,
        _cert_fh=cert_path.open("a", encoding="utf-8", buffering=1),
        _cert_published=[],
    )
    from scripts.real_robot.run_vln_m3pro import VLNControllerNode
    node._emit_evidence = lambda **kw: VLNControllerNode._emit_evidence(node, **kw)
    return node


def _make_inst(text: str = "go forward", source: str = "text") -> object:
    intake = InstructionIntake()
    if source == "voice":
        return intake.from_voice_transcript(text)
    return intake.from_text(text)


def _silent_logger():
    return types.SimpleNamespace(
        info=lambda *a, **kw: None,
        warn=lambda *a, **kw: None,
        error=lambda *a, **kw: None,
    )


def _make_clear_node(safety_radius: float = 0.30) -> types.SimpleNamespace:
    """Minimal node sufficient to run _cb_estop_clear (no ROS2 needed)."""
    node = types.SimpleNamespace(
        _args=_fake_args(safety_radius=safety_radius),
    )
    node.get_logger = _silent_logger
    return node


@pytest.fixture
def tmp(tmp_path):
    return tmp_path


# ── e-stop certificate content ─────────────────────────────────────────────────

class TestEstopCert:

    def test_estop_cert_is_not_safe(self, tmp):
        """An estop_latched decision must produce safe=False in the certificate."""
        node = _make_mock_node(tmp)
        inst = _make_inst()
        node._emit_evidence(
            inst=inst, goal=None,
            decision="estop_latched", qp_status="estop_latched",
            u_nom=[0.0, 0.0], u_safe=[0.0, 0.0],
            cbf_active=False, min_dist=0.10, h_min=-1.0,
            frame_id="camera_link", camera_last_age_ms=50.0,
            latency_ms=5.0,
            scan_audit=_fake_scan_audit(),
            estop_latched=True, reason="estop_latched",
        )
        cert = _read_jsonl(node._cert_path)[0]
        assert cert["safe"] is False
        assert cert["estop_latched"] is True
        assert cert["decision"] == "estop_latched"
        assert cert["qp_status"] == "estop_latched"

    def test_estop_cert_written_even_when_latched(self, tmp):
        """Evidence must be written on every instruction, including latched paths."""
        node = _make_mock_node(tmp)
        for _ in range(3):
            node._emit_evidence(
                inst=_make_inst(), goal=None,
                decision="estop_latched", qp_status="estop_latched",
                u_nom=[0.0, 0.0], u_safe=[0.0, 0.0],
                cbf_active=False, min_dist=0.10, h_min=-1.0,
                frame_id="none", camera_last_age_ms=None,
                latency_ms=5.0,
                scan_audit=_fake_scan_audit(),
                estop_latched=True, reason="estop_latched",
            )
        certs = _read_jsonl(node._cert_path)
        assert len(certs) == 3


# ── _cb_estop_clear unit tests ─────────────────────────────────────────────────

class TestEstopClear:

    def _run_clear(self, safety_radius: float, scan_clearance: float,
                   was_latched: bool) -> bool:
        """Run _cb_estop_clear and return the resulting estop_latched state."""
        from scripts.real_robot import run_vln_m3pro as mod
        from scripts.real_robot.run_vln_m3pro import VLNControllerNode

        with mod._state_lock:
            mod._robot["estop_latched"] = was_latched
            mod._robot["scan_clearance"] = scan_clearance

        node = _make_clear_node(safety_radius=safety_radius)
        VLNControllerNode._cb_estop_clear(node, types.SimpleNamespace(data="clear"))

        with mod._state_lock:
            result = mod._robot["estop_latched"]
            # restore
            mod._robot["estop_latched"] = False
            mod._robot["scan_clearance"] = float("inf")
        return result

    def test_clears_latch_when_clearance_safe(self):
        """/fleetsafe/estop_clear resets latch when clearance >= safety_radius."""
        still_latched = self._run_clear(
            safety_radius=0.30, scan_clearance=0.80, was_latched=True
        )
        assert still_latched is False

    def test_refuses_when_clearance_too_low(self):
        """/fleetsafe/estop_clear refuses when clearance < safety_radius."""
        still_latched = self._run_clear(
            safety_radius=0.30, scan_clearance=0.10, was_latched=True
        )
        assert still_latched is True

    def test_noop_when_not_latched(self):
        """/fleetsafe/estop_clear is a no-op when estop was not set."""
        still_latched = self._run_clear(
            safety_radius=0.30, scan_clearance=0.80, was_latched=False
        )
        assert still_latched is False

    def test_clears_at_exact_safety_radius_boundary(self):
        """Clearance exactly equal to safety_radius must be refused (< is the condition)."""
        still_latched = self._run_clear(
            safety_radius=0.30, scan_clearance=0.30, was_latched=True
        )
        # 0.30 is NOT < 0.30 → should clear
        assert still_latched is False

    def test_refuses_one_mm_inside_radius(self):
        """Clearance 1 mm inside the radius must be refused."""
        still_latched = self._run_clear(
            safety_radius=0.30, scan_clearance=0.299, was_latched=True
        )
        assert still_latched is True


# ── voice after clear ─────────────────────────────────────────────────────────

class TestVoiceAfterClear:

    def test_voice_cert_safe_after_clear(self, tmp):
        """After e-stop clear, a voice instruction with h_min > 0 produces safe=True cert."""
        node = _make_mock_node(tmp)
        inst = _make_inst("move forward slowly", source="voice")
        node._emit_evidence(
            inst=inst, goal=None,
            decision="allowed", qp_status="skipped",
            u_nom=[0.10, 0.0], u_safe=[0.10, 0.0],
            cbf_active=False, min_dist=0.80, h_min=0.34,
            frame_id="camera_link", camera_last_age_ms=30.0,
            latency_ms=18.0,
            scan_audit=_fake_scan_audit(),
            estop_latched=False, reason="",
        )
        cert = _read_jsonl(node._cert_path)[0]
        assert cert["source"] == "voice"
        assert cert["safe"] is True
        assert cert["estop_latched"] is False
        assert cert["decision"] == "allowed"

    def test_voice_cert_has_all_audit_fields(self, tmp):
        """Voice certificate must include every required audit field."""
        node = _make_mock_node(tmp)
        inst = _make_inst("go to the exit", source="voice")
        node._emit_evidence(
            inst=inst, goal=None,
            decision="allowed", qp_status="skipped",
            u_nom=[0.10, 0.0], u_safe=[0.10, 0.0],
            cbf_active=False, min_dist=0.80, h_min=0.34,
            frame_id="camera_link", camera_last_age_ms=45.0,
            latency_ms=20.0,
            scan_audit=_fake_scan_audit(),
            estop_latched=False, reason="",
        )
        cert = _read_jsonl(node._cert_path)[0]
        required = {
            "source", "camera_seen", "camera_frame_id", "camera_last_age_ms",
            "scan_audit", "u_nominal", "u_safe",
            "timestamp", "instruction_id", "safe", "qp_status",
            "h_min", "min_dist_m", "safety_radius_m", "constraint_margin_min",
            "latency_ms", "cbf_active", "estop_latched", "decision",
            "reason", "dry_run",
        }
        for key in required:
            assert key in cert, f"Missing required cert field: {key!r}"

        assert cert["source"] == "voice"
        assert cert["camera_seen"] is True
        assert cert["camera_frame_id"] == "camera_link"
        assert cert["camera_last_age_ms"] == pytest.approx(45.0, abs=0.01)
        assert isinstance(cert["scan_audit"], dict)
        assert isinstance(cert["u_nominal"], list)
        assert isinstance(cert["u_safe"], list)

    def test_voice_cert_camera_seen_false_when_stale(self, tmp):
        """Even after clear, camera_seen=False when last frame is older than stale threshold."""
        node = _make_mock_node(tmp)
        inst = _make_inst("proceed", source="voice")
        node._emit_evidence(
            inst=inst, goal=None,
            decision="dry_run_zero", qp_status="skipped",
            u_nom=[0.0, 0.0], u_safe=[0.0, 0.0],
            cbf_active=False, min_dist=0.80, h_min=0.34,
            frame_id="camera_link", camera_last_age_ms=5000.0,  # 5 s > 2 s stale
            latency_ms=12.0,
            scan_audit=_fake_scan_audit(),
            estop_latched=False, reason="",
        )
        cert = _read_jsonl(node._cert_path)[0]
        assert cert["camera_seen"] is False
        assert cert["camera_frame_id"] == "camera_link"
