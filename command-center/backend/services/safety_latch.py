"""
Latched E-stop.

Once latched, relay_manager will refuse to enable relay until clear() is
called explicitly. Latch persists in-process across WebSocket reconnects.
"""
from __future__ import annotations

import threading
import time

from .robot_ops import _audit


class SafetyLatch:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latched = False
        self._reason = ""
        self._latch_ts: float | None = None
        self._clear_history: list[dict] = []

    @property
    def is_latched(self) -> bool:
        with self._lock:
            return self._latched

    def latch(self, reason: str = "manual") -> dict:
        with self._lock:
            self._latched = True
            self._reason = reason
            self._latch_ts = time.time()
        _audit("estop_latch", {"reason": reason}, "LATCHED", dry_run=False)
        return {"latched": True, "reason": reason, "ts": self._latch_ts}

    def clear(self, operator: str = "operator") -> dict:
        with self._lock:
            if not self._latched:
                return {"latched": False, "note": "was not latched"}
            record = {
                "cleared_at": time.time(),
                "operator": operator,
                "was_reason": self._reason,
            }
            self._clear_history.append(record)
            self._latched = False
            self._reason = ""
            self._latch_ts = None
        _audit("estop_clear", {"operator": operator}, "CLEARED", dry_run=False)
        return {"latched": False, "cleared_by": operator, "history": self._clear_history[-5:]}

    def get_status(self) -> dict:
        with self._lock:
            return {
                "latched": self._latched,
                "reason": self._reason,
                "latch_ts": self._latch_ts,
                "clear_count": len(self._clear_history),
                "last_clear": self._clear_history[-1] if self._clear_history else None,
            }


safety_latch = SafetyLatch()
