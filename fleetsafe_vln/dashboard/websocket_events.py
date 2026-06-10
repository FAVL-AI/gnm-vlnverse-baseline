"""Dashboard websocket event schema for FleetSafe-VLN episodes."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional


class EventType(str, Enum):
    EPISODE_START   = "episode_start"
    STEP            = "step"
    CBF_INTERVENTION = "cbf_intervention"
    NEAR_MISS       = "near_miss"
    COLLISION       = "collision"
    GOAL_REACHED    = "goal_reached"
    EPISODE_END     = "episode_end"
    SAFETY_CERT     = "safety_cert"
    ERROR           = "error"


@dataclass
class DashboardEvent:
    event_type: str
    t: float = field(default_factory=time.time)
    run_id: str = ""
    step: int = 0
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def step_event(
        cls,
        run_id: str,
        step: int,
        pose: tuple,
        u_nom: list,
        u_safe: list,
        cbf_active: bool,
        barrier_h: float,
        min_obs_m: float,
        min_human_m: float,
        cert_valid: bool,
    ) -> "DashboardEvent":
        return cls(
            event_type=EventType.STEP.value,
            run_id=run_id,
            step=step,
            payload={
                "pose": list(pose),
                "u_nominal": list(u_nom),
                "u_safe": list(u_safe),
                "cbf_active": cbf_active,
                "barrier_h": barrier_h,
                "min_obstacle_m": min_obs_m,
                "min_human_m": min_human_m,
                "cert_valid": cert_valid,
            },
        )

    @classmethod
    def episode_end_event(cls, run_id: str, success: bool, summary: dict) -> "DashboardEvent":
        return cls(
            event_type=EventType.EPISODE_END.value,
            run_id=run_id,
            payload={"success": success, "summary": summary},
        )


class DashboardBroadcaster:
    """Send events to a FastAPI websocket endpoint if backend is running."""

    def __init__(self, ws_url: str = "ws://localhost:8000/ws/episode"):
        self._url = ws_url
        self._ws = None
        self._connected = False
        self._try_connect()

    def _try_connect(self) -> None:
        try:
            import websocket  # type: ignore
            self._ws = websocket.WebSocket()
            self._ws.connect(self._url, timeout=2)
            self._connected = True
            print(f"[dashboard] Connected to {self._url}")
        except Exception:
            self._connected = False

    def send(self, event: DashboardEvent) -> None:
        if not self._connected or self._ws is None:
            return
        try:
            self._ws.send(event.to_json())
        except Exception:
            self._connected = False

    def close(self) -> None:
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None
