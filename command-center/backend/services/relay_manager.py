"""
Managed relay — the single authority on whether relay is active.

start():
  • Rejects if safety_latch is latched.
  • Rejects if relay already active.
  • Calls robot_ops.start_relay().
  • Records start time.

stop(reason):
  • Calls robot_ops.stop_relay() first.
  • Then calls robot_ops.zero() to guarantee zero on both topics.
  • Records stop reason.

_set_inactive(reason):
  Sync-safe; called by the watchdog from its thread after it has already
  published zeros directly via subprocess.
"""
from __future__ import annotations

import threading
import time

from .robot_ops import robot_ops, _audit
from .safety_latch import safety_latch


class RelayManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = False
        self._start_time: float | None = None
        self._stop_reason = ""

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._active

    async def start(self) -> dict:
        if safety_latch.is_latched:
            return {
                "ok": False,
                "error": "E-stop is latched — call /api/robot/estop/clear before enabling relay.",
            }
        with self._lock:
            if self._active:
                return {"ok": False, "error": "Relay already active."}

        result = await robot_ops.start_relay()
        if result["ok"]:
            with self._lock:
                self._active = True
                self._start_time = time.time()
        return result

    async def stop(self, reason: str = "manual") -> dict:
        relay_result = await robot_ops.stop_relay()
        zero_result = await robot_ops.zero()
        self._set_inactive(reason)
        _audit("relay_stop", {"reason": reason}, f"relay={relay_result['ok']} zero={zero_result['ok']}", dry_run=robot_ops.dry_run)
        return {
            **relay_result,
            "zeroed": zero_result["ok"],
            "reason": reason,
        }

    def _set_inactive(self, reason: str) -> None:
        """Sync path — safe to call from watchdog thread."""
        with self._lock:
            self._active = False
            self._stop_reason = reason
            self._start_time = None

    def get_status(self) -> dict:
        with self._lock:
            return {
                "active": self._active,
                "start_time": self._start_time,
                "uptime_s": (time.time() - self._start_time) if self._active and self._start_time else None,
                "stop_reason": self._stop_reason,
            }


relay_manager = RelayManager()
