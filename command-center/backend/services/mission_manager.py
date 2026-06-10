"""Mission manager — queues and tracks robot missions."""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, asdict, field


@dataclass
class Mission:
    mission_id: str
    robot_id: str
    scene: str
    goal_description: str = ""
    priority: int = 5
    status: str = "queued"   # queued / dispatching / running / done / failed / cancelled
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    result: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class MissionManager:
    def __init__(self) -> None:
        self._missions: dict[str, Mission] = {}
        self._lock = threading.Lock()

    def enqueue(self, robot_id: str, scene: str,
                goal_description: str = "", priority: int = 5) -> Mission:
        m = Mission(
            mission_id=str(uuid.uuid4())[:8],
            robot_id=robot_id,
            scene=scene,
            goal_description=goal_description,
            priority=priority,
        )
        with self._lock:
            self._missions[m.mission_id] = m
        return m

    def cancel(self, mission_id: str) -> Mission | None:
        with self._lock:
            m = self._missions.get(mission_id)
            if m and m.status in ("queued", "dispatching", "running"):
                m.status = "cancelled"
                m.finished_at = time.time()
            return m

    def update_status(self, mission_id: str, status: str,
                      result: dict | None = None) -> Mission | None:
        with self._lock:
            m = self._missions.get(mission_id)
            if not m:
                return None
            m.status = status
            if status in ("done", "failed", "cancelled") and not m.finished_at:
                m.finished_at = time.time()
            if status == "running" and not m.started_at:
                m.started_at = time.time()
            if result is not None:
                m.result = result
            return m

    def get(self, mission_id: str) -> Mission | None:
        return self._missions.get(mission_id)

    def list(self, robot_id: str | None = None) -> list[dict]:
        with self._lock:
            ms = list(self._missions.values())
        if robot_id:
            ms = [m for m in ms if m.robot_id == robot_id]
        return [m.to_dict() for m in sorted(ms, key=lambda m: -m.created_at)]


mission_manager = MissionManager()
