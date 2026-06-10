"""
Tests for RobotOpsManager (command-center/backend/services/robot_ops.py).

All tests run in dry_run=True mode by default — no real SSH calls.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# Add command-center to path so `backend` package is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "command-center"))

# Ensure settings use dry_run=True (default) even if env overrides
os.environ.setdefault("FLEETSAFE_ROBOT_DRY_RUN", "true")

from backend.services.robot_ops import (  # noqa: E402
    RobotOpsManager,
    VOICE_MAP,
    _audit,
    _AUDIT_PATH,
    _ssh_argv,
    _ssh_env,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def ops(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RobotOpsManager:
    """Fresh RobotOpsManager with audit log redirected to tmp_path."""
    import backend.services.robot_ops as mod
    monkeypatch.setattr(mod, "_AUDIT_PATH", tmp_path / "audit.jsonl")
    mgr = RobotOpsManager()
    mgr.set_dry_run(True)
    return mgr


# ── Dry-run flag ──────────────────────────────────────────────────────────────

def test_dry_run_default(ops: RobotOpsManager):
    assert ops.dry_run is True


def test_toggle_dry_run(ops: RobotOpsManager):
    ops.set_dry_run(False)
    assert ops.dry_run is False
    ops.set_dry_run(True)
    assert ops.dry_run is True


# ── Audit log ─────────────────────────────────────────────────────────────────

def test_audit_written(ops: RobotOpsManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import backend.services.robot_ops as mod
    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setattr(mod, "_AUDIT_PATH", audit_path)
    _audit("test_op", {"key": "val"}, "ok", dry_run=True)
    lines = audit_path.read_text().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["op"] == "test_op"
    assert entry["dry_run"] is True
    assert "ts" in entry


def test_get_audit_log_empty(ops: RobotOpsManager):
    entries = ops.get_audit_log()
    assert isinstance(entries, list)


def test_get_audit_log_returns_recent(ops: RobotOpsManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import backend.services.robot_ops as mod
    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setattr(mod, "_AUDIT_PATH", audit_path)
    for i in range(5):
        _audit(f"op_{i}", {}, f"result_{i}", dry_run=True)
    entries = ops.get_audit_log(3)
    assert len(entries) == 3
    # Most recent first
    assert entries[0]["op"] == "op_4"


# ── Dry-run operations ────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_start_agent_dry_run(ops: RobotOpsManager):
    r = await ops.start_agent()
    assert r["ok"] is True
    assert r["dry_run"] is True
    assert "micro_ros_agent" in r["cmd"]


@pytest.mark.anyio
async def test_start_fleetsafe_dry_run(ops: RobotOpsManager):
    r = await ops.start_fleetsafe()
    assert r["ok"] is True
    assert "fleetsafe_perception_node" in r["cmd"]


@pytest.mark.anyio
async def test_stop_fleetsafe_dry_run(ops: RobotOpsManager):
    r = await ops.stop_fleetsafe()
    assert r["ok"] is True


@pytest.mark.anyio
async def test_stop_conflicting_dry_run(ops: RobotOpsManager):
    r = await ops.stop_conflicting()
    assert r["ok"] is True
    assert r["dry_run"] is True


@pytest.mark.anyio
async def test_start_relay_dry_run(ops: RobotOpsManager):
    r = await ops.start_relay()
    assert r["ok"] is True
    assert "relay_enabled" in r["cmd"]


@pytest.mark.anyio
async def test_stop_relay_dry_run(ops: RobotOpsManager):
    r = await ops.stop_relay()
    assert r["ok"] is True


@pytest.mark.anyio
async def test_zero_dry_run(ops: RobotOpsManager):
    r = await ops.zero()
    assert r["ok"] is True
    assert "/cmd_vel_raw" in r["cmd"]
    assert "/cmd_vel" in r["cmd"]  # direct emergency stop too


@pytest.mark.anyio
async def test_pulse_dry_run(ops: RobotOpsManager):
    r = await ops.pulse(vx=0.1, vy=0.0, wz=0.0, duration_ms=300)
    assert r["ok"] is True
    assert r["dry_run"] is True


# ── Zero stop enforced ────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_pulse_targets_cmd_vel_raw(ops: RobotOpsManager):
    """Pulse must publish to /cmd_vel_raw, not directly to /cmd_vel."""
    r = await ops.pulse(vx=0.1, duration_ms=300)
    cmd = r["cmd"]
    assert "/cmd_vel_raw" in cmd


@pytest.mark.anyio
async def test_pulse_issues_zero_after(ops: RobotOpsManager):
    """Pulse command must zero both /cmd_vel_raw and /cmd_vel after the delay."""
    r = await ops.pulse(vx=0.2, duration_ms=200)
    cmd = r["cmd"]
    assert cmd.count("cmd_vel_raw") >= 2   # motion publish + zero
    assert "/cmd_vel" in cmd               # direct emergency zero included
    assert "{}" in cmd                     # zero twist present


# ── Relay guard in dry-run ────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_relay_guard_dry_run_passes(ops: RobotOpsManager):
    """In dry-run mode all checks should pass (simulated OK)."""
    r = await ops.relay_guard_check()
    assert r["dry_run"] is True
    assert r["pass"] is True
    assert len(r["checks"]) == 4
    for check in r["checks"]:
        assert check["pass"] is True


@pytest.mark.anyio
async def test_relay_guard_check_ids(ops: RobotOpsManager):
    r = await ops.relay_guard_check()
    ids = {c["id"] for c in r["checks"]}
    assert "cmd_vel_subscriber" in ids
    assert "cmd_vel_no_publisher" in ids
    assert "cmd_vel_safe_publisher" in ids
    assert "cmd_vel_raw_subscriber" in ids


# ── Graph verification in dry-run ─────────────────────────────────────────────

@pytest.mark.anyio
async def test_verify_graph_dry_run(ops: RobotOpsManager):
    r = await ops.verify_graph()
    assert r["ok"] is True
    assert r["dry_run"] is True
    assert "YB_Node" in r["nodes"]
    assert "fleetsafe_perception" in r["nodes"]


# ── Voice command map ─────────────────────────────────────────────────────────

def test_voice_map_has_neo_stop():
    assert "neo stop" in VOICE_MAP
    assert VOICE_MAP["neo stop"] == "zero"


def test_voice_map_relay_on():
    assert "neo relay on" in VOICE_MAP
    assert VOICE_MAP["neo relay on"] == "start_relay"


def test_voice_map_relay_off():
    assert "neo relay off" in VOICE_MAP
    assert VOICE_MAP["neo relay off"] == "stop_relay"


def test_voice_map_safe_mode():
    assert "neo safe mode" in VOICE_MAP
    assert VOICE_MAP["neo safe mode"] == "stop_relay"


def test_voice_map_all_have_neo_prefix():
    for phrase in VOICE_MAP:
        assert phrase.startswith("neo "), f"Phrase without 'neo' prefix: {phrase!r}"


def test_voice_map_ops_are_valid():
    valid_ops = {
        "zero", "pulse_forward", "pulse_back", "pulse_left", "pulse_right",
        "stop_relay", "start_relay", "start_fleetsafe",
    }
    for phrase, op in VOICE_MAP.items():
        assert op in valid_ops, f"{phrase!r} maps to unknown op {op!r}"


# ── Keyboard shortcut → op mapping ────────────────────────────────────────────

def test_all_op_handlers_covered():
    """Every op in OP_HANDLERS in the router should have a backend method."""
    ui_ops = {
        "start_agent", "start_fleetsafe", "stop_fleetsafe", "stop_conflicting",
        "start_relay", "stop_relay", "zero",
        "pulse_forward", "pulse_back", "pulse_left", "pulse_right",
    }
    for op in ui_ops:
        assert hasattr(RobotOpsManager, op) or op.startswith("pulse_"), (
            f"RobotOpsManager missing method for op: {op}"
        )


# ── SSH argv / env helpers ────────────────────────────────────────────────────

def test_ssh_argv_no_password_uses_plain_ssh(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("FLEETSAFE_ROBOT_PASSWORD", raising=False)
    argv = _ssh_argv("jetson@host", 5.0)
    assert argv[0] == "ssh"
    assert "BatchMode=yes" in " ".join(argv)
    assert "sshpass" not in " ".join(argv)


def test_ssh_argv_with_password_uses_sshpass(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FLEETSAFE_ROBOT_PASSWORD", "s3cr3t")
    import shutil as _shutil
    monkeypatch.setattr(_shutil, "which", lambda x: "/usr/bin/sshpass" if x == "sshpass" else None)
    argv = _ssh_argv("jetson@host", 5.0)
    assert argv[0] == "sshpass"
    assert argv[1] == "-e"
    assert "ssh" in argv
    # Password must NOT appear anywhere in argv
    assert "s3cr3t" not in " ".join(argv)


def test_ssh_argv_sshpass_drops_batchmode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FLEETSAFE_ROBOT_PASSWORD", "s3cr3t")
    import shutil as _shutil
    monkeypatch.setattr(_shutil, "which", lambda x: "/usr/bin/sshpass" if x == "sshpass" else None)
    argv = _ssh_argv("jetson@host", 5.0)
    # BatchMode=yes must be absent when sshpass is used
    assert "BatchMode=yes" not in " ".join(argv)


def test_ssh_argv_falls_back_to_plain_when_sshpass_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FLEETSAFE_ROBOT_PASSWORD", "s3cr3t")
    import shutil as _shutil
    monkeypatch.setattr(_shutil, "which", lambda x: None)  # sshpass not installed
    argv = _ssh_argv("jetson@host", 5.0)
    assert argv[0] == "ssh"
    assert "sshpass" not in " ".join(argv)


def test_ssh_env_no_password_returns_none(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("FLEETSAFE_ROBOT_PASSWORD", raising=False)
    assert _ssh_env() is None


def test_ssh_env_with_password_sets_sshpass(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FLEETSAFE_ROBOT_PASSWORD", "s3cr3t")
    env = _ssh_env()
    assert env is not None
    assert env["SSHPASS"] == "s3cr3t"


def test_password_not_in_audit_entry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Password must never appear in any audit log entry."""
    import backend.services.robot_ops as mod
    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setattr(mod, "_AUDIT_PATH", audit_path)
    monkeypatch.setenv("FLEETSAFE_ROBOT_PASSWORD", "sup3rs3cr3t")

    _audit("ssh_test", {"host": "jetson@host"}, "ok", dry_run=True)
    raw = audit_path.read_text()
    assert "sup3rs3cr3t" not in raw


@pytest.mark.anyio
async def test_dry_run_audit_does_not_log_password(
    ops: RobotOpsManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Even in live-mode dry_run, the audit entry must not contain the password."""
    import backend.services.robot_ops as mod
    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setattr(mod, "_AUDIT_PATH", audit_path)
    monkeypatch.setenv("FLEETSAFE_ROBOT_PASSWORD", "sup3rs3cr3t")

    r = await ops.zero()  # dry_run=True on the fixture
    assert r["dry_run"] is True
    raw = audit_path.read_text()
    assert "sup3rs3cr3t" not in raw


# ── Live SSH path (skipped unless FLEETSAFE_ROBOT_DRY_RUN=false) ──────────────

@pytest.mark.skipif(
    os.environ.get("FLEETSAFE_ROBOT_DRY_RUN", "true").lower() != "false",
    reason="Skipped in dry-run mode",
)
@pytest.mark.anyio
async def test_live_ssh_echo(ops: RobotOpsManager):
    ops.set_dry_run(False)
    r = await ops._run("echo_test", "echo hello", {})
    assert r["ok"] is True
    assert r["output"] == "hello"
