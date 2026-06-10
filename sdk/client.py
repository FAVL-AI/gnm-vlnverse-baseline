"""Thin synchronous client for the FleetSafe REST API."""
from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Any, Generator


class FleetSafeClient:
    def __init__(self, base_url: str = "http://localhost:8000", timeout: int = 10) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ── internals ──────────────────────────────────────────────────────────────

    def _get(self, path: str) -> Any:
        url = f"{self.base_url}{path}"
        with urllib.request.urlopen(url, timeout=self.timeout) as r:
            return json.loads(r.read())

    def _post(self, path: str, payload: dict) -> Any:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read())

    # ── public API ─────────────────────────────────────────────────────────────

    def health(self) -> dict:
        return self._get("/health")

    def get_robots(self) -> list[dict]:
        return self._get("/fleet/robots")

    def get_robot(self, robot_id: str) -> dict:
        return self._get(f"/fleet/robots/{robot_id}")

    def inject_safety_event(self, robot_id: str, event_type: str,
                            payload: dict | None = None) -> dict:
        return self._post("/safety/events", {
            "robot_id": robot_id,
            "event_type": event_type,
            "payload": payload or {},
        })

    def replay_episode(self, episode_id: str, speed: float = 1.0) -> dict:
        return self._post("/replay/start", {
            "episode_id": episode_id,
            "speed": speed,
        })

    def stream_telemetry(
        self,
        robot_id: str,
        max_events: int = 1000,
    ) -> Generator[dict, None, None]:
        """Yield telemetry events from the SSE endpoint."""
        url = f"{self.base_url}/stream/telemetry?robot_id={robot_id}"
        req = urllib.request.Request(url, headers={"Accept": "text/event-stream"})
        count = 0
        with urllib.request.urlopen(req, timeout=None) as r:
            for raw_line in r:
                line = raw_line.decode().strip()
                if line.startswith("data:"):
                    try:
                        yield json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        pass
                    count += 1
                    if count >= max_events:
                        break
