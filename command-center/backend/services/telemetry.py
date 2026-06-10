"""
Telemetry service — 10Hz JSON stream over WebSocket.

Priority:
  1. Live ROS2 data (ros2_bridge.is_live() == True)
  2. Animated mock (always available fallback)

Extended payload (v0.3):
  zone, risk, crowding_risk, occlusion_risk,
  detection_count, tracked_count, detections[], tracks[],
  intervention_active,
  cmd_vel {vx, vy, wz},
  odom {x, y, heading},
  battery_pct, battery_charging,
  latency_ms, perception_latency_ms, sim_fps,
  source ("ros2"|"mock"), timestamp
"""
from __future__ import annotations

import asyncio
import math
import time
from typing import Any, AsyncIterator

from . import ros2_bridge


# ── Mock generator ─────────────────────────────────────────────────────────────

def _mock(tick: int) -> dict[str, Any]:
    t = tick / 10.0
    risk = 0.25 + 0.20 * math.sin(t * 0.7) + 0.10 * math.sin(t * 1.3)
    risk = max(0.0, min(1.0, risk))
    crowding  = max(0.0, min(1.0, risk + 0.05 * math.sin(t * 2.1)))
    occlusion = max(0.0, min(1.0, 0.15 + 0.12 * math.sin(t * 0.5)))
    zone = "GREEN" if risk < 0.30 else ("AMBER" if risk < 0.60 else "RED")
    scale = 1.0 if zone == "GREEN" else (0.4 if zone == "AMBER" else 0.0)
    det_n = max(0, int(3 + 2 * math.sin(t * 0.3)))

    return {
        "zone":               zone,
        "risk":               round(risk, 3),
        "crowding_risk":      round(crowding, 3),
        "occlusion_risk":     round(occlusion, 3),
        "detection_count":    det_n,
        "tracked_count":      max(0, int(det_n * 0.8)),
        "intervention_active": zone == "RED",
        "cmd_vel": {
            "vx": round(0.3 * scale * math.cos(t * 0.2), 3),
            "vy": 0.0,
            "wz": round(0.1 * math.sin(t * 0.15), 3),
        },
        "odom": {
            "x":       round(0.5 * math.sin(t * 0.1), 3),
            "y":       round(0.5 * math.cos(t * 0.08), 3),
            "heading": round(t * 0.05 % (2 * math.pi), 3),
        },
        "battery_pct":        None,
        "battery_charging":   False,
        "latency_ms":         round(8.0 + 2.0 * math.sin(t * 3.0), 1),
        "perception_latency_ms": 0.0,
        "sim_fps":            0.0,
        "detections":         [
            {"id": i, "role": "patient", "x": round(math.cos(t + i), 2),
             "y": round(math.sin(t * 0.7 + i), 2)}
            for i in range(det_n)
        ],
        "tracks":             [],
        "source":             "mock",
        "timestamp":          time.time(),
    }


# ── Public async generator ────────────────────────────────────────────────────

async def telemetry_stream(hz: int = 10) -> AsyncIterator[dict[str, Any]]:
    ros2_bridge.start()
    interval = 1.0 / hz
    tick = 0
    while True:
        if ros2_bridge.is_live():
            data = ros2_bridge.get_snapshot()
            data["timestamp"] = time.time()
        else:
            data = _mock(tick)
        yield data
        tick += 1
        await asyncio.sleep(interval)
