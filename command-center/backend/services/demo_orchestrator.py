"""
Demo mode orchestrator.

One-button safe demo sequence:
  IDLE → VERIFYING → STARTING_FLEETSAFE → ENABLING_RELAY
       → RUNNING_PATH → STOPPING → DONE / ERROR

On any error the sequence auto-zeros and latches the e-stop.
Scripted path: 3 × (forward 0.5 s, pause 1 s) — total ~4.5 s motion.
"""
from __future__ import annotations

import asyncio
import time
from typing import Callable

from .robot_ops import robot_ops, _audit
from .safety_latch import safety_latch
from .relay_manager import relay_manager

DEMO_STATES = (
    "IDLE", "VERIFYING", "STARTING_FLEETSAFE",
    "ENABLING_RELAY", "RUNNING_PATH", "STOPPING", "DONE", "ERROR",
)


class DemoOrchestrator:
    def __init__(self) -> None:
        self._state = "IDLE"
        self._log: list[str] = []
        self._start_ts: float | None = None
        self._end_ts: float | None = None
        self._task: asyncio.Task | None = None  # type: ignore[type-arg]

    @property
    def state(self) -> str:
        return self._state

    def get_status(self) -> dict:
        return {
            "state": self._state,
            "log": list(self._log),
            "start_ts": self._start_ts,
            "end_ts": self._end_ts,
        }

    async def start(self) -> dict:
        if self._state not in ("IDLE", "DONE", "ERROR"):
            return {"ok": False, "error": f"Demo already in progress: {self._state}"}
        if safety_latch.is_latched:
            return {"ok": False, "error": "E-stop latched — clear before running demo."}
        if relay_manager.is_active:
            return {"ok": False, "error": "Relay already active — stop it first."}

        self._log.clear()
        self._state = "IDLE"
        self._start_ts = time.time()
        self._end_ts = None
        self._task = asyncio.create_task(self._run())
        return {"ok": True, "state": self._state}

    async def abort(self) -> dict:
        if self._task and not self._task.done():
            self._task.cancel()
        await self._emergency_stop("manual_abort")
        return {"ok": True, "state": self._state}

    # ── Sequence ──────────────────────────────────────────────────────────────

    async def _run(self) -> None:
        try:
            await self._transition("VERIFYING", self._verify)
            await self._transition("STARTING_FLEETSAFE", self._start_fleetsafe)
            await asyncio.sleep(2.0)  # let node settle
            await self._transition("ENABLING_RELAY", self._enable_relay)
            await asyncio.sleep(0.5)  # relay settle
            await self._transition("RUNNING_PATH", self._run_path)
            await self._transition("STOPPING", self._stop_relay)
            self._state = "DONE"
        except asyncio.CancelledError:
            await self._emergency_stop("cancelled")
        except Exception as e:
            self._push(f"ERROR: {e}")
            await self._emergency_stop(f"exception: {e}")
        finally:
            self._end_ts = time.time()
            _audit("demo_finished", {"state": self._state}, self._state, dry_run=robot_ops.dry_run)

    async def _transition(self, state: str, fn: Callable) -> None:  # type: ignore[type-arg]
        self._state = state
        self._push(f"→ {state}")
        await fn()

    async def _verify(self) -> None:
        guard = await robot_ops.relay_guard_check()
        passed = guard["pass"]
        self._push(f"Relay guard: {'PASS' if passed else 'FAIL'}")
        if not passed and not robot_ops.dry_run:
            raise RuntimeError("Relay guard failed — fix checks before demo")
        graph = await robot_ops.verify_graph()
        self._push(f"Graph: {len(graph['nodes'])} nodes, {len(graph['topics'])} topics")

    async def _start_fleetsafe(self) -> None:
        r = await robot_ops.start_fleetsafe()
        self._push(f"FleetSafe: {'started' if r['ok'] else 'ERROR'}")

    async def _enable_relay(self) -> None:
        r = await relay_manager.start()
        if not r["ok"]:
            raise RuntimeError(f"Relay start failed: {r.get('error')}")
        self._push("Relay ENABLED")

    async def _run_path(self) -> None:
        for i in range(3):
            r = await robot_ops.pulse(vx=0.1, duration_ms=500)
            self._push(f"Pulse {i + 1}/3: {'ok' if r['ok'] else 'ERR'}")
            await asyncio.sleep(1.0)

    async def _stop_relay(self) -> None:
        r = await relay_manager.stop("demo_complete")
        self._push(f"Relay stopped, zeroed={r.get('zeroed')}")

    async def _emergency_stop(self, reason: str) -> None:
        self._state = "ERROR"
        self._push(f"EMERGENCY STOP: {reason}")
        await robot_ops.zero()
        if relay_manager.is_active:
            relay_manager._set_inactive(f"demo_error: {reason}")
        safety_latch.latch(f"demo_error: {reason}")

    def _push(self, msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self._log.append(f"[{ts}] {msg}")


demo_orchestrator = DemoOrchestrator()
