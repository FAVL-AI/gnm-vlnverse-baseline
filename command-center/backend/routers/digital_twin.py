"""
digital_twin.py — Real-time digital twin WebSocket + REST status.

Bridges the ROS2 bridge cache (real M3Pro state) to the frontend at 10 Hz.
The WebSocket at /api/twin/ws streams live robot pose, velocity, safety zone,
social risk, and (if available) the forward-facing camera frame.

Usage
-----
    GET  /api/twin/status  — one-shot snapshot
    WS   /api/twin/ws      — 10 Hz live stream
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..services import ros2_bridge

router = APIRouter(prefix="/api/twin", tags=["digital-twin"])


@router.get("/status")
async def twin_status() -> dict[str, Any]:
    """One-shot snapshot of the real robot state from the ROS2 bridge cache."""
    snap = ros2_bridge.get_snapshot()
    return {
        "live":            ros2_bridge.is_live(),
        "source":          snap.get("source", "mock"),
        "odom":            snap.get("odom", {"x": 0.0, "y": 0.0, "heading": 0.0}),
        "cmd_vel":         snap.get("cmd_vel", {"vx": 0.0, "vy": 0.0, "wz": 0.0}),
        "zone":            snap.get("zone", "GREEN"),
        "risk":            snap.get("risk", 0.0),
        "crowding_risk":   snap.get("crowding_risk", 0.0),
        "occlusion_risk":  snap.get("occlusion_risk", 0.0),
        "battery_pct":     snap.get("battery_pct"),
        "battery_charging": snap.get("battery_charging", False),
        "detection_count": snap.get("detection_count", 0),
        "tracked_count":   snap.get("tracked_count", 0),
        "latency_ms":      snap.get("latency_ms", 0.0),
        "perception_latency_ms": snap.get("perception_latency_ms", 0.0),
        "last_update":     snap.get("last_update", 0.0),
    }


@router.websocket("/ws")
async def twin_ws(ws: WebSocket) -> None:
    """
    10 Hz WebSocket stream of the real robot state.

    Payload fields
    --------------
    type            "twin"
    t               server Unix timestamp
    live            bool — True if ROS2 messages arrived within 2 s
    source          "ros2" | "mock"
    odom            {x, y, heading}  — odometry in robot frame (metres, rad)
    cmd_vel         {vx, vy, wz}     — last safe velocity command
    zone            "GREEN" | "AMBER" | "RED"
    risk            float 0–1 composite social risk
    crowding_risk   float 0–1
    battery_pct     float | null
    detection_count int
    tracked_count   int
    latency_ms      float — policy inference latency
    detections      list[{id, role, x, y, ...}]
    tracks          list[{id, x, y, vx, vy, ...}]
    camera_b64      "data:image/jpeg;base64,..." (only when a frame is available)
    """
    await ws.accept()
    try:
        while True:
            snap   = ros2_bridge.get_snapshot()
            camera = ros2_bridge.get_camera_b64(max_age_s=1.0)

            payload: dict[str, Any] = {
                "type":            "twin",
                "t":               time.time(),
                "live":            ros2_bridge.is_live(),
                "source":          snap.get("source", "mock"),
                "odom":            snap.get("odom", {"x": 0.0, "y": 0.0, "heading": 0.0}),
                "cmd_vel":         snap.get("cmd_vel", {"vx": 0.0, "vy": 0.0, "wz": 0.0}),
                "zone":            snap.get("zone", "GREEN"),
                "risk":            snap.get("risk", 0.0),
                "crowding_risk":   snap.get("crowding_risk", 0.0),
                "battery_pct":     snap.get("battery_pct"),
                "battery_charging": snap.get("battery_charging", False),
                "detection_count": snap.get("detection_count", 0),
                "tracked_count":   snap.get("tracked_count", 0),
                "latency_ms":      snap.get("latency_ms", 0.0),
                "perception_latency_ms": snap.get("perception_latency_ms", 0.0),
                "detections":      snap.get("detections", []),
                "tracks":          snap.get("tracks", []),
            }

            if camera:
                payload["camera_b64"] = camera

            await ws.send_text(json.dumps(payload))
            await asyncio.sleep(0.1)   # 10 Hz

    except (WebSocketDisconnect, Exception):
        pass
