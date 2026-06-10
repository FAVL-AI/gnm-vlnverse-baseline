"""
Safety supervisor — aggregates safety events from all robots.

Thread-safe. Version counter lets WS endpoint poll for new events
without subscribing queues, avoiding cross-thread asyncio issues.
"""
from __future__ import annotations

import threading
import time
import uuid


class SafetySupervisor:
    def __init__(self) -> None:
        self._events: list[dict] = []
        self._version: int = 0
        self._estopped: set[str] = set()
        self._lock = threading.Lock()

    def record(self, event: dict) -> dict:
        ev = dict(event)
        ev.setdefault("event_id", str(uuid.uuid4())[:8])
        ev.setdefault("timestamp", time.time())
        with self._lock:
            self._events.append(ev)
            if len(self._events) > 500:
                self._events = self._events[-500:]
            self._version += 1
        return ev

    def get_history(self, n: int = 50) -> list[dict]:
        with self._lock:
            return list(self._events[-n:])

    def get_version(self) -> int:
        return self._version

    def get_since(self, version: int) -> tuple[int, list[dict]]:
        """Return (current_version, events_since_version)."""
        with self._lock:
            v = self._version
            delta = v - version
            if delta <= 0:
                return v, []
            return v, list(self._events[-delta:])

    # ── E-stop ─────────────────────────────────────────────────────────────────

    def estop(self, robot_id: str) -> dict:
        with self._lock:
            self._estopped.add(robot_id)
        return self.record({
            "robot_id":   robot_id,
            "event_type": "estop",
            "severity":   "critical",
            "zone":       "RED",
            "risk":       1.0,
            "min_dist_m": None,
            "details":    {"source": "manual_override"},
        })

    def clear_estop(self, robot_id: str) -> None:
        with self._lock:
            self._estopped.discard(robot_id)

    def estop_all(self) -> list[str]:
        from .robot_registry import robot_registry
        ids = [r["robot_id"] for r in robot_registry.all()]
        for rid in ids:
            self.estop(rid)
        return ids

    def is_estopped(self, robot_id: str) -> bool:
        return robot_id in self._estopped

    def estopped_robots(self) -> list[str]:
        with self._lock:
            return list(self._estopped)


safety_supervisor = SafetySupervisor()
