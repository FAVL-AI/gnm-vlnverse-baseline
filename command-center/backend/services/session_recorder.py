"""
Session recorder — saves robot telemetry + safety events to disk.

Layout:
  command-center/recordings/{session_id}/
    telemetry.jsonl   — one TelemetryData frame per tick
    events.jsonl      — SafetyEvent lines
    session.json      — metadata (written on stop)
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, asdict, field
from pathlib import Path

from ..config import settings


@dataclass
class RecordingSession:
    session_id: str
    robot_id: str
    started_at: float
    stopped_at: float | None = None
    n_frames: int = 0
    n_events: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["is_active"] = self.stopped_at is None
        return d


class SessionRecorder:
    def __init__(self) -> None:
        self._sessions: dict[str, RecordingSession] = {}
        self._active: dict[str, str] = {}   # robot_id → session_id
        self._writers: dict[str, dict] = {} # session_id → {tel, ev, path}
        self._lock = threading.Lock()

    @property
    def _recordings_dir(self) -> Path:
        d = settings.repo_root / "command-center" / "recordings"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def start(self, robot_id: str) -> RecordingSession:
        # Stop existing recording for this robot first
        existing_id = self._active.get(robot_id)
        if existing_id:
            self.stop(existing_id)

        session_id = str(uuid.uuid4())[:8]
        session = RecordingSession(session_id=session_id, robot_id=robot_id, started_at=time.time())
        path = self._recordings_dir / session_id
        path.mkdir(parents=True, exist_ok=True)

        with self._lock:
            self._sessions[session_id] = session
            self._active[robot_id] = session_id
            self._writers[session_id] = {
                "tel":  open(path / "telemetry.jsonl", "w"),
                "ev":   open(path / "events.jsonl", "w"),
                "path": path,
            }
        return session

    def stop(self, session_id: str) -> RecordingSession | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session or session.stopped_at is not None:
                return session
            session.stopped_at = time.time()
            writers = self._writers.pop(session_id, {})
            if self._active.get(session.robot_id) == session_id:
                del self._active[session.robot_id]

        for key in ("tel", "ev"):
            try:
                writers[key].close()
            except Exception:
                pass
        p: Path | None = writers.get("path")
        if p:
            (p / "session.json").write_text(json.dumps(session.to_dict(), indent=2))
        return session

    def record_telemetry(self, robot_id: str, data: dict) -> bool:
        with self._lock:
            sid = self._active.get(robot_id)
            if not sid:
                return False
            session = self._sessions[sid]
            w = self._writers.get(sid)
        if not w:
            return False
        w["tel"].write(json.dumps(data) + "\n")
        w["tel"].flush()
        session.n_frames += 1
        return True

    def record_event(self, event: dict) -> bool:
        robot_id = event.get("robot_id")
        if not robot_id:
            return False
        with self._lock:
            sid = self._active.get(robot_id)
            if not sid:
                return False
            session = self._sessions[sid]
            w = self._writers.get(sid)
        if not w:
            return False
        w["ev"].write(json.dumps(event) + "\n")
        w["ev"].flush()
        session.n_events += 1
        return True

    def is_recording(self, robot_id: str) -> bool:
        return robot_id in self._active

    def active_session_id(self, robot_id: str) -> str | None:
        return self._active.get(robot_id)

    def list_sessions(self) -> list[dict]:
        result: dict[str, dict] = {}
        with self._lock:
            for s in self._sessions.values():
                result[s.session_id] = s.to_dict()
        # Scan disk for past sessions
        for p in sorted(self._recordings_dir.iterdir(), reverse=True):
            if not p.is_dir() or p.name in result:
                continue
            meta = p / "session.json"
            if meta.exists():
                try:
                    d = json.loads(meta.read_text())
                    d["is_active"] = False
                    result[p.name] = d
                except Exception:
                    pass
        return sorted(result.values(), key=lambda s: -(s.get("started_at") or 0))

    def get_trajectory(self, session_id: str) -> list[dict]:
        p = self._recordings_dir / session_id / "telemetry.jsonl"
        if not p.exists():
            return []
        out, step = [], 0
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                odom = d.get("odom") or {}
                out.append({
                    "step":       step,
                    "x":          float(odom.get("x", 0)),
                    "y":          float(odom.get("y", 0)),
                    "heading":    float(odom.get("heading", 0)),
                    "latency_ms": float(d.get("latency_ms", 0)),
                })
                step += 1
            except Exception:
                pass
        return out

    def get_events(self, session_id: str) -> list[dict]:
        p = self._recordings_dir / session_id / "events.jsonl"
        if not p.exists():
            return []
        out = []
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                pass
        return out


session_recorder = SessionRecorder()
