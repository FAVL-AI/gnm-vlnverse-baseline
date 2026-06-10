"""
Robot registry — tracks all active robots (real + simulated).

Auto-populates via:
  - start_mock_fleet()   — 3 animated mock robots
  - ros2_bridge         — real robot when ROS2 is live
  - manual register()   — arbitrary robot injection
"""
from __future__ import annotations

import math
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any

_lock = threading.Lock()
_MOCK_STARTED = False


@dataclass
class RobotRecord:
    robot_id: str
    name: str
    robot_type: str = "unknown"       # "real" | "simulated" | "unknown"
    status: str = "online"            # "online" | "offline" | "mission" | "error" | "estop"
    zone: str = "GREEN"
    risk: float = 0.0
    crowding_risk: float = 0.0
    battery_pct: float | None = None
    battery_charging: bool = False
    odom: dict = field(default_factory=lambda: {"x": 0.0, "y": 0.0, "heading": 0.0})
    cmd_vel: dict = field(default_factory=lambda: {"vx": 0.0, "vy": 0.0, "wz": 0.0})
    active_mission_id: str | None = None
    intervention_active: bool = False
    detection_count: int = 0
    tracked_count: int = 0
    latency_ms: float = 0.0
    source: str = "unknown"
    last_update: float = field(default_factory=time.monotonic)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("last_update", None)
        return d


class RobotRegistry:
    def __init__(self) -> None:
        self._robots: dict[str, RobotRecord] = {}

    def register(self, robot_id: str, name: str,
                 robot_type: str = "unknown", source: str = "unknown") -> RobotRecord:
        with _lock:
            if robot_id not in self._robots:
                self._robots[robot_id] = RobotRecord(
                    robot_id=robot_id, name=name,
                    robot_type=robot_type, source=source,
                )
            return self._robots[robot_id]

    def update(self, robot_id: str, **fields: Any) -> RobotRecord | None:
        with _lock:
            r = self._robots.get(robot_id)
            if not r:
                return None
            for k, v in fields.items():
                if hasattr(r, k):
                    setattr(r, k, v)
            r.last_update = time.monotonic()
            return r

    def get(self, robot_id: str) -> RobotRecord | None:
        with _lock:
            return self._robots.get(robot_id)

    def all(self) -> list[dict]:
        cutoff = time.monotonic() - 5.0
        with _lock:
            out = []
            for r in self._robots.values():
                if r.last_update < cutoff and r.status not in ("offline", "estop"):
                    r.status = "offline"
                out.append(r.to_dict())
        return out

    def deregister(self, robot_id: str) -> bool:
        with _lock:
            return bool(self._robots.pop(robot_id, None))


robot_registry = RobotRegistry()


# ── Mock fleet ─────────────────────────────────────────────────────────────────

_MOCK_CFG = [
    {"robot_id": "m3pro-01",     "name": "M3Pro · Real Robot",   "robot_type": "real",      "battery_pct": 87.0, "ph": 0.0, "ox": 0.0, "oy": 0.0},
    {"robot_id": "isaac-hosp-a", "name": "Isaac · Hospital A",   "robot_type": "simulated", "battery_pct": None, "ph": 1.2, "ox": 3.0, "oy": 1.5},
    {"robot_id": "isaac-hosp-b", "name": "Isaac · Hospital B",   "robot_type": "simulated", "battery_pct": None, "ph": 2.7, "ox": 8.0, "oy": 5.0},
]


def _robot_state(cfg: dict, t: float) -> dict:
    ph = cfg["ph"]
    risk = 0.25 + 0.22 * math.sin(t * 0.7 + ph) + 0.10 * math.sin(t * 1.3 + ph)
    risk = max(0.0, min(1.0, risk))
    crowding = max(0.0, min(1.0, risk + 0.05 * math.sin(t * 2.1 + ph)))
    zone = "GREEN" if risk < 0.30 else ("AMBER" if risk < 0.60 else "RED")
    spd = 0.3 * (1.0 if zone == "GREEN" else (0.4 if zone == "AMBER" else 0.0))
    heading = (t * 0.08 + ph) % (2 * math.pi)
    det_n = max(0, int(2 + 2 * math.sin(t * 0.4 + ph)))
    return {
        "status": "online",
        "zone": zone,
        "risk": round(risk, 3),
        "crowding_risk": round(crowding, 3),
        "intervention_active": zone == "RED",
        "detection_count": det_n,
        "tracked_count": max(0, det_n - 1),
        "cmd_vel": {
            "vx": round(spd * math.cos(heading), 3),
            "vy": 0.0,
            "wz": round(0.1 * math.sin(t * 0.15 + ph), 3),
        },
        "odom": {
            "x": round(cfg["ox"] + 1.5 * math.cos(t * 0.1 + ph), 3),
            "y": round(cfg["oy"] + 1.5 * math.sin(t * 0.08 + ph), 3),
            "heading": round(heading, 3),
        },
        "latency_ms": round(8.0 + 2.0 * math.sin(t * 3.0 + ph), 1),
    }


def _mock_fleet_loop() -> None:
    import random
    for cfg in _MOCK_CFG:
        r = robot_registry.register(cfg["robot_id"], cfg["name"], cfg["robot_type"], source="mock")
        r.battery_pct = cfg["battery_pct"]

    prev_zones: dict[str, str] = {c["robot_id"]: "GREEN" for c in _MOCK_CFG}

    while True:
        t = time.monotonic()
        for cfg in _MOCK_CFG:
            state = _robot_state(cfg, t)
            robot_registry.update(cfg["robot_id"], **state)

            rid = cfg["robot_id"]
            new_z = state["zone"]
            old_z = prev_zones.get(rid, "GREEN")
            if new_z != old_z:
                from .safety_supervisor import safety_supervisor
                safety_supervisor.record({
                    "robot_id": rid,
                    "event_type": "zone_change",
                    "severity": "warning" if new_z in ("AMBER", "RED") else "info",
                    "zone": new_z,
                    "risk": state["risk"],
                    "min_dist_m": None,
                    "details": {"from": old_z, "to": new_z},
                })
                prev_zones[rid] = new_z

            # Stochastic intervention events for simulated robots in RED
            if cfg["robot_type"] == "simulated" and state["zone"] == "RED":
                if random.random() < 0.004:
                    from .safety_supervisor import safety_supervisor
                    safety_supervisor.record({
                        "robot_id": rid,
                        "event_type": "intervention",
                        "severity": "warning",
                        "zone": "RED",
                        "risk": state["risk"],
                        "min_dist_m": round(0.25 + 0.5 * random.random(), 2),
                        "details": {"cbf_triggered": True, "raw_vx": 0.3, "safe_vx": 0.0},
                    })

        time.sleep(0.1)


def start_mock_fleet() -> None:
    global _MOCK_STARTED
    if _MOCK_STARTED:
        return
    _MOCK_STARTED = True
    threading.Thread(target=_mock_fleet_loop, daemon=True, name="mock_fleet").start()
