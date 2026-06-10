"""
Streaming router — MJPEG, WebRTC signaling, Foxglove launcher, telemetry WS.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..config import ALLOWED_SCRIPTS, settings
from ..services import stream_manager, mjpeg_source, webrtc_server, telemetry, ros2_bridge
from ..services.process_manager import process_manager

router = APIRouter(prefix="/api", tags=["stream"])


# ── Stream registry ────────────────────────────────────────────────────────────

@router.get("/streams")
async def list_streams() -> list[dict]:
    await stream_manager.refresh_status()
    return stream_manager.all_stream_info()


@router.get("/streams/{stream_id}")
async def get_stream(stream_id: str) -> dict:
    await stream_manager.refresh_status(stream_id)
    info = stream_manager.stream_info(stream_id)
    if not info:
        raise HTTPException(404, f"Stream {stream_id!r} not found")
    return info


# ── Foxglove bridge launcher ───────────────────────────────────────────────────

@router.post("/streams/{stream_id}/launch")
async def launch_foxglove(stream_id: str) -> dict:
    s = stream_manager.STREAMS.get(stream_id)
    if not s or not s.foxglove_launch:
        raise HTTPException(400, "Stream has no launcher")
    job = await process_manager.launch(
        script_key=f"foxglove_{stream_id}",
        label=f"Foxglove bridge ({s.label})",
        cmd=s.foxglove_launch,
        cwd=settings.repo_root,
    )
    return {"job_id": job.job_id, "status": job.status}


# ── MJPEG stream ──────────────────────────────────────────────────────────────

@router.get("/stream/mjpeg/{stream_id}")
async def mjpeg_stream(stream_id: str, fps: int = 15) -> StreamingResponse:
    s = stream_manager.STREAMS.get(stream_id)
    if not s or s.type != "mjpeg":
        raise HTTPException(404, f"No MJPEG stream for {stream_id!r}")

    fps = max(1, min(30, fps))
    boundary = b"--frame"

    async def generate():
        async for frame in mjpeg_source.frame_generator(stream_id, fps=fps):
            yield boundary + b"\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Accel-Buffering": "no",
        },
    )


# ── WebRTC signaling ──────────────────────────────────────────────────────────

class WebRTCOffer(BaseModel):
    stream_id: str
    sdp: str
    type: str


@router.post("/webrtc/offer")
async def webrtc_offer(req: WebRTCOffer) -> dict:
    result = await webrtc_server.handle_offer(req.stream_id, req.sdp, req.type)
    if "error" in result:
        raise HTTPException(503, result["error"])
    return result


# ── Telemetry WebSocket ────────────────────────────────────────────────────────

@router.websocket("/ws/telemetry")
async def telemetry_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        async for data in telemetry.telemetry_stream(hz=10):
            await websocket.send_text(json.dumps(data))
    except WebSocketDisconnect:
        pass
    finally:
        pass


# ── ROS2 status ───────────────────────────────────────────────────────────────

@router.get("/ros2/status")
async def ros2_status() -> dict:
    snap = ros2_bridge.get_snapshot()
    return {
        "live":         ros2_bridge.is_live(),
        "source":       snap.get("source", "mock"),
        "last_update":  snap.get("last_update", 0.0),
        "zone":         snap.get("zone"),
        "detection_count": snap.get("detection_count", 0),
    }


# ── Screenshot capture endpoint (delegates to frontend/browser) ───────────────

@router.get("/streams/{stream_id}/snapshot_url")
async def snapshot_url(stream_id: str) -> dict:
    """Return the URL to grab a single JPEG frame from."""
    s = stream_manager.STREAMS.get(stream_id)
    if not s:
        raise HTTPException(404)
    if s.type == "mjpeg":
        return {"url": f"/api/stream/mjpeg/{stream_id}?fps=1"}
    return {"url": None, "note": "snapshot not available for this stream type"}
