"""
v0.7 Safety Supervisor tests — every unsafe transition must be rejected.

Tests are grouped by invariant:
  A. Latch: once set, relay cannot start until explicitly cleared.
  B. RelayManager: rejects double-start, auto-zeros on stop.
  C. Watchdog: triggers estop when fleetsafe disappears (mocked SSH).
  D. DemoOrchestrator: sequences, error path, auto-latch on failure.
  E. Integration: latch → relay rejected → clear → relay allowed.
"""
from __future__ import annotations

import asyncio
import os
import sys
import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "command-center"))
os.environ.setdefault("FLEETSAFE_ROBOT_DRY_RUN", "true")


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def fresh_services(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Give each test isolated, freshly constructed service instances."""
    import backend.services.robot_ops as ops_mod
    import backend.services.safety_latch as latch_mod
    import backend.services.relay_manager as relay_mod
    import backend.services.watchdog as wd_mod
    import backend.services.demo_orchestrator as demo_mod

    monkeypatch.setattr(ops_mod, "_AUDIT_PATH", tmp_path / "audit.jsonl")

    from backend.services.robot_ops import RobotOpsManager
    fresh_ops = RobotOpsManager()
    fresh_ops.set_dry_run(True)
    monkeypatch.setattr(ops_mod, "robot_ops", fresh_ops)

    from backend.services.safety_latch import SafetyLatch
    fresh_latch = SafetyLatch()
    monkeypatch.setattr(latch_mod, "safety_latch", fresh_latch)

    from backend.services.relay_manager import RelayManager
    fresh_relay = RelayManager()
    monkeypatch.setattr(relay_mod, "relay_manager", fresh_relay)
    # relay_manager imports safety_latch at module level — patch its reference too
    monkeypatch.setattr(relay_mod, "safety_latch", fresh_latch)

    from backend.services.watchdog import Watchdog
    fresh_wd = Watchdog()
    monkeypatch.setattr(wd_mod, "watchdog", fresh_wd)
    monkeypatch.setattr(wd_mod, "relay_manager", fresh_relay)
    monkeypatch.setattr(wd_mod, "safety_latch", fresh_latch)
    monkeypatch.setattr(wd_mod, "robot_ops", fresh_ops)

    from backend.services.demo_orchestrator import DemoOrchestrator
    fresh_demo = DemoOrchestrator()
    monkeypatch.setattr(demo_mod, "demo_orchestrator", fresh_demo)
    monkeypatch.setattr(demo_mod, "relay_manager", fresh_relay)
    monkeypatch.setattr(demo_mod, "safety_latch", fresh_latch)
    monkeypatch.setattr(demo_mod, "robot_ops", fresh_ops)

    yield {
        "ops": fresh_ops,
        "latch": fresh_latch,
        "relay": fresh_relay,
        "wd": fresh_wd,
        "demo": fresh_demo,
    }


# ── A. SafetyLatch ────────────────────────────────────────────────────────────

def test_latch_initial_state(fresh_services):
    latch = fresh_services["latch"]
    assert latch.is_latched is False
    s = latch.get_status()
    assert s["latched"] is False
    assert s["latch_ts"] is None


def test_latch_sets_state(fresh_services):
    latch = fresh_services["latch"]
    r = latch.latch("test_reason")
    assert r["latched"] is True
    assert latch.is_latched is True
    assert latch.get_status()["reason"] == "test_reason"


def test_latch_clear_resets_state(fresh_services):
    latch = fresh_services["latch"]
    latch.latch("reason")
    r = latch.clear("test_operator")
    assert r["latched"] is False
    assert latch.is_latched is False
    assert latch.get_status()["clear_count"] == 1


def test_clear_when_not_latched_is_safe(fresh_services):
    latch = fresh_services["latch"]
    r = latch.clear("nobody")
    assert r["latched"] is False
    assert "was not latched" in r["note"]


def test_latch_records_ts(fresh_services):
    latch = fresh_services["latch"]
    before = time.time()
    latch.latch("ts_test")
    assert latch.get_status()["latch_ts"] >= before


# ── B. RelayManager ───────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_relay_start_when_latched_rejected(fresh_services):
    latch = fresh_services["latch"]
    relay = fresh_services["relay"]
    latch.latch("estop")
    r = await relay.start()
    assert r["ok"] is False
    assert "latched" in r["error"].lower()
    assert relay.is_active is False


@pytest.mark.anyio
async def test_relay_start_when_already_active_rejected(fresh_services):
    relay = fresh_services["relay"]
    r1 = await relay.start()
    assert r1["ok"] is True
    r2 = await relay.start()
    assert r2["ok"] is False
    assert "already active" in r2["error"].lower()


@pytest.mark.anyio
async def test_relay_stop_zeroes_both_topics(fresh_services):
    relay = fresh_services["relay"]
    ops = fresh_services["ops"]

    await relay.start()
    assert relay.is_active is True

    r = await relay.stop("test_stop")
    assert r["ok"] is True
    assert r["zeroed"] is True
    assert relay.is_active is False
    assert relay.get_status()["stop_reason"] == "test_stop"


@pytest.mark.anyio
async def test_relay_stop_when_not_active_still_zeroes(fresh_services):
    relay = fresh_services["relay"]
    # Stop without starting — should still zero (idempotent safety)
    r = await relay.stop("precaution")
    assert r["zeroed"] is True


@pytest.mark.anyio
async def test_relay_uptime_tracked(fresh_services):
    relay = fresh_services["relay"]
    await relay.start()
    await asyncio.sleep(0.05)
    s = relay.get_status()
    assert s["active"] is True
    assert s["uptime_s"] is not None and s["uptime_s"] >= 0


def test_relay_set_inactive_is_sync(fresh_services):
    relay = fresh_services["relay"]
    relay._set_inactive("watchdog_test")
    assert relay.is_active is False
    assert relay.get_status()["stop_reason"] == "watchdog_test"


# ── C. Watchdog ───────────────────────────────────────────────────────────────

def test_watchdog_initial_state(fresh_services):
    wd = fresh_services["wd"]
    s = wd.get_status()
    assert s["running"] is False
    assert s["total_triggers"] == 0


def test_watchdog_start_stop(fresh_services):
    wd = fresh_services["wd"]
    wd.start()
    assert wd.get_status()["running"] is True
    wd.stop()
    assert wd.get_status()["running"] is False


def test_watchdog_no_trigger_when_relay_inactive(fresh_services):
    """Watchdog should not fire when relay is off, even if probe would fail."""
    wd = fresh_services["wd"]
    relay = fresh_services["relay"]
    assert relay.is_active is False

    # Simulate probe failure - but relay is off, so no trigger
    with patch("backend.services.watchdog._ssh_sync", return_value=(-1, "")):
        wd._tick()

    assert wd.get_status()["total_triggers"] == 0


def test_watchdog_triggers_when_fleetsafe_gone(fresh_services):
    """When relay active and node list lacks fleetsafe, trigger after MAX_FAILURES."""
    wd = fresh_services["wd"]
    relay = fresh_services["relay"]
    latch = fresh_services["latch"]
    ops = fresh_services["ops"]

    relay._active = True
    ops.set_dry_run(False)  # probe must run; _zero_sync is patched below

    with patch("backend.services.watchdog._ssh_sync", return_value=(0, "/YB_Node")), \
         patch("backend.services.watchdog._zero_sync"):
        wd._tick()
        assert wd.get_status()["consecutive_failures"] == 1
        wd._tick()  # second failure → trigger

    assert wd.get_status()["total_triggers"] == 1
    assert latch.is_latched is True
    assert "fleetsafe" in latch.get_status()["reason"]
    assert relay.is_active is False


def test_watchdog_resets_failures_on_recovery(fresh_services):
    """A clean probe resets the consecutive failure counter."""
    wd = fresh_services["wd"]
    relay = fresh_services["relay"]
    ops = fresh_services["ops"]

    relay._active = True
    ops.set_dry_run(False)  # probe must run

    with patch("backend.services.watchdog._ssh_sync", return_value=(0, "/YB_Node")), \
         patch("backend.services.watchdog._zero_sync"):
        wd._tick()  # 1 failure
    assert wd.get_status()["consecutive_failures"] == 1

    # Good probe — both calls (node list + topic info) return OK
    with patch("backend.services.watchdog._ssh_sync", return_value=(0, "/fleetsafe_perception\n/YB_Node")):
        wd._tick()
    assert wd.get_status()["consecutive_failures"] == 0


def test_watchdog_dry_run_always_ok(fresh_services):
    """In dry_run mode the watchdog probe always returns OK."""
    wd = fresh_services["wd"]
    relay = fresh_services["relay"]
    relay._active = True

    # Even without SSH available the watchdog should not fire in dry_run
    wd._tick()
    wd._tick()
    assert wd.get_status()["total_triggers"] == 0


# ── D. DemoOrchestrator ───────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_demo_rejected_when_latched(fresh_services):
    demo = fresh_services["demo"]
    fresh_services["latch"].latch("pre_latch")
    r = await demo.start()
    assert r["ok"] is False
    assert "latched" in r["error"].lower()


@pytest.mark.anyio
async def test_demo_rejected_when_relay_active(fresh_services):
    demo = fresh_services["demo"]
    fresh_services["relay"]._active = True
    r = await demo.start()
    assert r["ok"] is False
    assert "relay" in r["error"].lower()


@pytest.mark.anyio
async def test_demo_rejected_when_in_progress(fresh_services):
    demo = fresh_services["demo"]
    demo._state = "VERIFYING"  # simulate in-progress
    r = await demo.start()
    assert r["ok"] is False
    assert "progress" in r["error"].lower()


@pytest.mark.anyio
async def test_demo_runs_full_sequence_dry_run(fresh_services):
    """Full demo sequence should complete and end in DONE in dry_run mode."""
    demo = fresh_services["demo"]

    r = await demo.start()
    assert r["ok"] is True

    # Wait for async task
    assert demo._task is not None
    await demo._task

    assert demo.state == "DONE"
    log = demo.get_status()["log"]
    assert any("VERIFYING" in l for l in log)
    assert any("ENABLING_RELAY" in l for l in log)
    assert any("RUNNING_PATH" in l for l in log)
    assert any("STOPPING" in l for l in log)


@pytest.mark.anyio
async def test_demo_latches_on_error(fresh_services):
    """If verify fails in live mode, demo should latch e-stop."""
    demo = fresh_services["demo"]
    ops = fresh_services["ops"]
    ops.set_dry_run(False)  # live mode so guard failure matters

    # Make relay_guard_check fail
    with patch.object(ops, "relay_guard_check", new_callable=AsyncMock,
                      return_value={"pass": False, "dry_run": False, "checks": []}), \
         patch.object(ops, "zero", new_callable=AsyncMock,
                      return_value={"ok": True, "dry_run": False, "op": "zero [/cmd_vel_raw + /cmd_vel]"}):
        r = await demo.start()
        assert r["ok"] is True
        await demo._task

    assert demo.state == "ERROR"
    assert fresh_services["latch"].is_latched is True


@pytest.mark.anyio
async def test_demo_abort_triggers_estop(fresh_services):
    """Aborting a running demo should zero and latch."""
    demo = fresh_services["demo"]
    demo._state = "RUNNING_PATH"  # simulate mid-run

    with patch.object(fresh_services["ops"], "zero", new_callable=AsyncMock,
                      return_value={"ok": True, "dry_run": True, "op": "zero"}):
        r = await demo.abort()

    assert r["ok"] is True
    assert fresh_services["latch"].is_latched is True


# ── E. Integration: full unsafe-transition chain ──────────────────────────────

@pytest.mark.anyio
async def test_integration_latch_blocks_relay_clear_allows(fresh_services):
    latch = fresh_services["latch"]
    relay = fresh_services["relay"]

    # Latch → relay rejected
    latch.latch("integration_test")
    r = await relay.start()
    assert r["ok"] is False

    # Clear → relay allowed
    latch.clear("operator")
    r = await relay.start()
    assert r["ok"] is True
    assert relay.is_active is True


@pytest.mark.anyio
async def test_integration_watchdog_trigger_blocks_relay(fresh_services):
    relay = fresh_services["relay"]
    latch = fresh_services["latch"]
    wd = fresh_services["wd"]
    ops = fresh_services["ops"]

    relay._active = True
    ops.set_dry_run(False)  # probe must run; _zero_sync is patched below

    with patch("backend.services.watchdog._ssh_sync", return_value=(0, "/YB_Node")), \
         patch("backend.services.watchdog._zero_sync"):
        wd._tick(); wd._tick()  # two failures → trigger

    assert latch.is_latched is True
    ops.set_dry_run(True)  # back to dry_run for the relay start call
    r = await relay.start()
    assert r["ok"] is False
    assert "latched" in r["error"].lower()
