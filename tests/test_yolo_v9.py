"""
v0.9 Live Camera/YOLO Evidence Capture tests.

Invariants tested:
  A. RealSession: 14-topic bag, auto-evidence on stop, SHA256 of metadata.
  B. EvidenceLedger: real_robot_session entries have correct claim scope + GT type.
  C. YoloSwitch: start/stop state, dry-run safe, double-start rejected.
  D. Evidence linkage: evidence_id in session matches ledger.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "command-center"))
os.environ.setdefault("FLEETSAFE_ROBOT_DRY_RUN", "true")

EXPECTED_TOPICS = [
    "/camera/color/image_raw",
    "/camera/depth/image_raw",
    "/camera/color/camera_info",
    "/odom_raw",
    "/scan0",
    "/battery",
    "/cmd_vel_raw",
    "/cmd_vel_safe",
    "/cmd_vel",
    "/fleetsafe/zone",
    "/fleetsafe/social_risk",
    "/fleetsafe/detections",
    "/fleetsafe/tracks",
    "/fleetsafe/latency",
]


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Fresh RealSessionRecorder with evidence ledger in tmp."""
    import backend.services.real_session as sess_mod
    import backend.services.evidence_ledger as led_mod

    ledger_path = tmp_path / "evidence_ledger.jsonl"
    monkeypatch.setattr(led_mod, "LEDGER_PATH", ledger_path)
    monkeypatch.setattr(sess_mod, "RECORDINGS_DIR", tmp_path / "recordings")

    # Patch robot_ops._run to succeed without SSH (env var sets dry_run=True)
    async def fake_run(op, cmd, args=None):
        return {"ok": True, "dry_run": True, "op": op, "output": "pid:1234"}

    monkeypatch.setattr(sess_mod.robot_ops, "_run", fake_run)
    monkeypatch.setattr(sess_mod.robot_ops, "_dry_run", True)

    from backend.services.real_session import RealSessionRecorder
    from backend.services.evidence_ledger import EvidenceLedger

    # Fresh ledger instance
    new_ledger = EvidenceLedger.__new__(EvidenceLedger)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(sess_mod, "evidence_ledger", new_ledger)

    recorder = RealSessionRecorder()
    return recorder, new_ledger, ledger_path, tmp_path


@pytest.fixture()
def tmp_yolo(monkeypatch: pytest.MonkeyPatch):
    """Fresh YoloSwitch with mocked robot_ops."""
    import backend.services.yolo_switch as yolo_mod

    async def fake_run(op, cmd, args=None):
        return {"ok": True, "dry_run": True, "op": op, "output": "ok"}

    monkeypatch.setattr(yolo_mod.robot_ops, "_run", fake_run)
    monkeypatch.setattr(yolo_mod.robot_ops, "_dry_run", True)

    from backend.services.yolo_switch import YoloSwitch
    return YoloSwitch()


# ── A. Session: 14 topics ─────────────────────────────────────────────────────

class TestSessionTopics:
    def test_session_records_14_topics(self, tmp_session):
        recorder, ledger, ledger_path, tmp = tmp_session
        import backend.services.real_session as mod
        assert len(mod.TOPICS) == 14

    def test_all_required_topics_present(self, tmp_session):
        import backend.services.real_session as mod
        for topic in EXPECTED_TOPICS:
            assert topic in mod.TOPICS, f"Missing required topic: {topic}"

    def test_fleetsafe_topics_included(self, tmp_session):
        import backend.services.real_session as mod
        fs_topics = [t for t in mod.TOPICS if "/fleetsafe/" in t]
        assert len(fs_topics) >= 4, "At least 4 FleetSafe topics required"

    def test_depth_and_rgb_included(self, tmp_session):
        import backend.services.real_session as mod
        assert "/camera/color/image_raw" in mod.TOPICS
        assert "/camera/depth/image_raw" in mod.TOPICS

    @pytest.mark.anyio
    async def test_start_returns_n_topics(self, tmp_session):
        recorder, ledger, ledger_path, tmp = tmp_session
        meta = await recorder.start("m3pro")
        assert meta["n_topics"] == 14
        assert len(meta["topics"]) == 14

    @pytest.mark.anyio
    async def test_session_id_format(self, tmp_session):
        recorder, ledger, ledger_path, tmp = tmp_session
        meta = await recorder.start("m3pro")
        assert meta["session_id"].startswith("real_m3pro_")

    @pytest.mark.anyio
    async def test_start_sets_started_at(self, tmp_session):
        recorder, ledger, ledger_path, tmp = tmp_session
        before = time.time()
        meta = await recorder.start("m3pro")
        after = time.time()
        assert before <= meta["started_at"] <= after

    @pytest.mark.anyio
    async def test_start_stopped_at_is_null(self, tmp_session):
        recorder, ledger, ledger_path, tmp = tmp_session
        meta = await recorder.start("m3pro")
        assert meta["stopped_at"] is None


# ── B. Auto-evidence on stop ──────────────────────────────────────────────────

class TestAutoEvidence:
    @pytest.mark.anyio
    async def test_stop_writes_evidence_entry(self, tmp_session):
        recorder, ledger, ledger_path, tmp = tmp_session
        meta = await recorder.start("m3pro")
        result = await recorder.stop(meta["session_id"])
        assert ledger_path.exists(), "Evidence ledger must be created on stop"
        entries = [json.loads(l) for l in ledger_path.read_text().splitlines()]
        assert len(entries) == 1

    @pytest.mark.anyio
    async def test_evidence_claim_scope_is_real_robot_session(self, tmp_session):
        recorder, ledger, ledger_path, tmp = tmp_session
        meta = await recorder.start("m3pro")
        await recorder.stop(meta["session_id"])
        entry = json.loads(ledger_path.read_text().splitlines()[0])
        assert entry["claim_scope"] == "real_robot_session"

    @pytest.mark.anyio
    async def test_evidence_source_is_real_robot(self, tmp_session):
        recorder, ledger, ledger_path, tmp = tmp_session
        meta = await recorder.start("m3pro")
        await recorder.stop(meta["session_id"])
        entry = json.loads(ledger_path.read_text().splitlines()[0])
        assert entry["source"] == "real_robot"

    @pytest.mark.anyio
    async def test_evidence_gt_type_is_sensor_derived(self, tmp_session):
        recorder, ledger, ledger_path, tmp = tmp_session
        meta = await recorder.start("m3pro")
        await recorder.stop(meta["session_id"])
        entry = json.loads(ledger_path.read_text().splitlines()[0])
        assert entry["ground_truth_type"] == "sensor_derived"

    @pytest.mark.anyio
    async def test_stop_returns_sha256(self, tmp_session):
        recorder, ledger, ledger_path, tmp = tmp_session
        meta = await recorder.start("m3pro")
        result = await recorder.stop(meta["session_id"])
        assert "sha256" in result
        assert result["sha256"] is not None
        assert len(result["sha256"]) == 64

    @pytest.mark.anyio
    async def test_stop_returns_evidence_id(self, tmp_session):
        recorder, ledger, ledger_path, tmp = tmp_session
        meta = await recorder.start("m3pro")
        result = await recorder.stop(meta["session_id"])
        assert "evidence_id" in result
        assert result["evidence_id"] is not None

    @pytest.mark.anyio
    async def test_evidence_id_matches_ledger(self, tmp_session):
        recorder, ledger, ledger_path, tmp = tmp_session
        meta = await recorder.start("m3pro")
        result = await recorder.stop(meta["session_id"])
        entry = json.loads(ledger_path.read_text().splitlines()[0])
        assert entry["id"] == result["evidence_id"]

    @pytest.mark.anyio
    async def test_stop_writes_local_session_json(self, tmp_session):
        recorder, ledger, ledger_path, tmp = tmp_session
        meta = await recorder.start("m3pro")
        await recorder.stop(meta["session_id"])
        session_json = tmp / "recordings" / meta["session_id"] / "session.json"
        assert session_json.exists(), "Local session.json must be written on stop"
        data = json.loads(session_json.read_text())
        assert data["session_id"] == meta["session_id"]

    @pytest.mark.anyio
    async def test_stop_records_duration(self, tmp_session):
        recorder, ledger, ledger_path, tmp = tmp_session
        meta = await recorder.start("m3pro")
        result = await recorder.stop(meta["session_id"])
        assert result["duration_s"] is not None
        assert result["duration_s"] >= 0

    @pytest.mark.anyio
    async def test_stop_unknown_session_returns_error(self, tmp_session):
        recorder, ledger, ledger_path, tmp = tmp_session
        result = await recorder.stop("nonexistent_session")
        assert result["ok"] is False
        assert "Unknown session" in result["error"]

    @pytest.mark.anyio
    async def test_stop_does_not_write_evidence_for_unknown_session(self, tmp_session):
        recorder, ledger, ledger_path, tmp = tmp_session
        await recorder.stop("nonexistent_session")
        assert not ledger_path.exists(), "No ledger entry for unknown session"


# ── C. YOLO switch ────────────────────────────────────────────────────────────

class TestYoloSwitch:
    def test_initial_state_is_mock(self, tmp_yolo):
        status = tmp_yolo.get_status()
        assert status["active"] is False
        assert status["mode"] == "mock"

    @pytest.mark.anyio
    async def test_start_sets_active(self, tmp_yolo):
        await tmp_yolo.start()
        assert tmp_yolo.get_status()["active"] is True

    @pytest.mark.anyio
    async def test_start_sets_mode_to_yolo(self, tmp_yolo):
        await tmp_yolo.start()
        assert tmp_yolo.get_status()["mode"] == "yolo"

    @pytest.mark.anyio
    async def test_stop_returns_to_mock(self, tmp_yolo):
        await tmp_yolo.start()
        await tmp_yolo.stop()
        assert tmp_yolo.get_status()["active"] is False
        assert tmp_yolo.get_status()["mode"] == "mock"

    @pytest.mark.anyio
    async def test_double_start_rejected(self, tmp_yolo):
        await tmp_yolo.start()
        result = await tmp_yolo.start()
        assert result["ok"] is False
        assert "already running" in result["error"]

    @pytest.mark.anyio
    async def test_start_returns_ok(self, tmp_yolo):
        result = await tmp_yolo.start()
        assert result["ok"] is True

    @pytest.mark.anyio
    async def test_status_includes_model_path(self, tmp_yolo):
        status = tmp_yolo.get_status()
        assert "model_path" in status
        assert len(status["model_path"]) > 0

    @pytest.mark.anyio
    async def test_status_includes_uptime_when_active(self, tmp_yolo):
        await tmp_yolo.start()
        status = tmp_yolo.get_status()
        assert status["uptime_s"] is not None
        assert status["uptime_s"] >= 0

    def test_status_uptime_null_when_inactive(self, tmp_yolo):
        assert tmp_yolo.get_status()["uptime_s"] is None

    @pytest.mark.anyio
    async def test_stop_when_not_active_succeeds(self, tmp_yolo):
        result = await tmp_yolo.stop()
        assert result["ok"] is True
        assert tmp_yolo.get_status()["active"] is False


# ── D. List sessions ──────────────────────────────────────────────────────────

class TestSessionList:
    @pytest.mark.anyio
    async def test_list_empty_initially(self, tmp_session):
        recorder, _, _, _ = tmp_session
        assert recorder.list_sessions() == []

    @pytest.mark.anyio
    async def test_list_after_start(self, tmp_session):
        recorder, _, _, _ = tmp_session
        await recorder.start("m3pro")
        sessions = recorder.list_sessions()
        assert len(sessions) == 1

    @pytest.mark.anyio
    async def test_get_session_by_id(self, tmp_session):
        recorder, _, _, _ = tmp_session
        meta = await recorder.start("m3pro")
        found = recorder.get_session(meta["session_id"])
        assert found is not None
        assert found["session_id"] == meta["session_id"]

    @pytest.mark.anyio
    async def test_get_unknown_session_returns_none(self, tmp_session):
        recorder, _, _, _ = tmp_session
        assert recorder.get_session("does_not_exist") is None
