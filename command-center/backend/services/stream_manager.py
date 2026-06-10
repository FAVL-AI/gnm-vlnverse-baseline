"""
Stream registry and health detection for all simulation backends.

Streams can be one of three types:
  foxglove — a Foxglove WebSocket bridge (ws://), embedded as an iframe
  webrtc   — an aiortc WebRTC server (our own or Isaac's native)
  mjpeg    — multipart/x-mixed-replace JPEG stream served by this backend

Detection is async and non-blocking; callers get a cached status snapshot.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import aiohttp


# ── Stream definitions ─────────────────────────────────────────────────────────

@dataclass
class StreamDef:
    id: str
    label: str
    type: str           # "foxglove" | "webrtc" | "mjpeg"
    icon: str           # emoji shorthand for UI
    # Foxglove streams
    foxglove_ws: str | None = None
    foxglove_launch: list[str] | None = None
    # WebRTC streams
    webrtc_check_url: str | None = None   # HTTP URL to probe for liveness
    webrtc_offer_url: str | None = None   # where to POST SDP offer
    # MJPEG streams
    mjpeg_source: str = "mock"            # "mock" | "ros_topic" | "isaac"
    ros_topic: str | None = None
    # State
    status: str = "unknown"               # "connected" | "disconnected" | "unknown"
    last_checked: float = 0.0
    extra: dict = field(default_factory=dict)


STREAMS: dict[str, StreamDef] = {
    "rviz": StreamDef(
        id="rviz",
        label="RViz",
        icon="🔵",
        type="foxglove",
        foxglove_ws="ws://localhost:8765",
        foxglove_launch=["ros2", "run", "foxglove_bridge", "foxglove_bridge",
                         "--ros-args", "-p", "port:=8765"],
    ),
    "isaac": StreamDef(
        id="isaac",
        label="Isaac Sim",
        icon="⚡",
        type="webrtc",
        webrtc_check_url="http://localhost:8211/",
        webrtc_offer_url="http://localhost:8211/offer",
    ),
    "mujoco": StreamDef(
        id="mujoco",
        label="MuJoCo",
        icon="🟢",
        type="mjpeg",
        mjpeg_source="mock",
    ),
    "gazebo": StreamDef(
        id="gazebo",
        label="Gazebo",
        icon="🟠",
        type="foxglove",
        foxglove_ws="ws://localhost:8766",
        foxglove_launch=["ros2", "run", "foxglove_bridge", "foxglove_bridge",
                         "--ros-args", "-p", "port:=8766"],
    ),
    "real": StreamDef(
        id="real",
        label="Real Robot",
        icon="🤖",
        type="mjpeg",
        mjpeg_source="ros_topic",
        ros_topic="/camera/color/image_raw",
    ),
}

_CACHE_TTL = 5.0   # seconds


# ── Detection ─────────────────────────────────────────────────────────────────

async def _probe_http(url: str, timeout: float = 1.5) -> bool:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                return r.status < 500
    except Exception:
        return False


async def _probe_ws(url: str, timeout: float = 1.5) -> bool:
    try:
        import websockets
        async with asyncio.timeout(timeout):
            async with websockets.connect(url) as _ws:
                return True
    except Exception:
        return False


async def _check_stream(s: StreamDef) -> str:
    if s.type == "foxglove" and s.foxglove_ws:
        ok = await _probe_ws(s.foxglove_ws)
        return "connected" if ok else "disconnected"
    elif s.type == "webrtc" and s.webrtc_check_url:
        ok = await _probe_http(s.webrtc_check_url)
        return "connected" if ok else "disconnected"
    elif s.type == "mjpeg":
        # MJPEG streams served by this backend are always "available" (mock frames)
        return "available"
    return "unknown"


async def refresh_status(stream_id: str | None = None) -> None:
    targets = [STREAMS[stream_id]] if stream_id else list(STREAMS.values())
    now = time.monotonic()
    stale = [s for s in targets if now - s.last_checked > _CACHE_TTL]
    if stale:
        results = await asyncio.gather(*[_check_stream(s) for s in stale])
        for s, status in zip(stale, results):
            s.status = status
            s.last_checked = now


def stream_info(stream_id: str) -> dict[str, Any]:
    s = STREAMS.get(stream_id)
    if not s:
        return {}
    return {
        "id": s.id,
        "label": s.label,
        "icon": s.icon,
        "type": s.type,
        "status": s.status,
        "foxglove_ws": s.foxglove_ws,
        "webrtc_offer_url": s.webrtc_offer_url,
        "mjpeg_url": f"/api/stream/mjpeg/{s.id}" if s.type == "mjpeg" else None,
        "has_launcher": bool(s.foxglove_launch),
    }


def all_stream_info() -> list[dict[str, Any]]:
    return [stream_info(sid) for sid in STREAMS]
