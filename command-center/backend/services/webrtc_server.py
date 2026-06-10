"""
aiortc WebRTC server — serves animated frames over WebRTC for simulation backends.

For Isaac Sim: proxies Isaac's native WebRTC offer/answer.
For MuJoCo/mock: renders frames via mjpeg_source and encodes them as H264.

Gracefully disabled if aiortc is not installed.
"""
from __future__ import annotations

import asyncio
import io
import time
from typing import Any

try:
    from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
    from aiortc.contrib.media import MediaPlayer
    import av
    _AIORTC = True
except ImportError:
    _AIORTC = False

import aiohttp

from .mjpeg_source import _make_mock_frame, _PIL, W, H

_pcs: set = set()


# ── Video track that renders mock frames ──────────────────────────────────────

if _AIORTC and _PIL:
    from PIL import Image as PIL_Image
    import fractions

    class MockVideoTrack(VideoStreamTrack):
        kind = "video"

        def __init__(self, stream_id: str) -> None:
            super().__init__()
            self._stream_id = stream_id
            self._tick = 0
            self._pts  = 0

        async def recv(self):
            await asyncio.sleep(1 / 20)  # 20 fps
            frame_bytes = _make_mock_frame(self._stream_id, self._tick)
            self._tick += 1

            img = PIL_Image.open(io.BytesIO(frame_bytes)).convert("RGB")
            frame = av.VideoFrame.from_image(img)
            frame.pts = self._pts
            frame.time_base = fractions.Fraction(1, 20)
            self._pts += 1
            return frame


# ── Isaac proxy ───────────────────────────────────────────────────────────────

async def _proxy_isaac_offer(offer_sdp: str, offer_type: str,
                             isaac_url: str) -> dict[str, str] | None:
    """Forward the browser's offer to Isaac's WebRTC endpoint and return its answer."""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                isaac_url,
                json={"sdp": offer_sdp, "type": offer_type},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as r:
                if r.status == 200:
                    return await r.json()
    except Exception:
        pass
    return None


# ── Public API ────────────────────────────────────────────────────────────────

async def handle_offer(stream_id: str, sdp: str, sdp_type: str) -> dict[str, Any]:
    """
    Process a WebRTC offer from the browser.

    For Isaac: proxy to Isaac's native endpoint.
    For others: create a local RTCPeerConnection with a mock/rendered video track.
    """
    if not _AIORTC:
        return {"error": "aiortc not installed — run: pip install aiortc av"}

    from .stream_manager import STREAMS

    s = STREAMS.get(stream_id)
    if s is None:
        return {"error": f"Unknown stream: {stream_id}"}

    # ── Isaac: proxy to native WebRTC ─────────────────────────────────────────
    if s.type == "webrtc" and s.webrtc_offer_url:
        result = await _proxy_isaac_offer(sdp, sdp_type, s.webrtc_offer_url)
        if result:
            return result
        # Fall through to mock on Isaac connection failure

    # ── Our own aiortc peer connection with mock/rendered video ───────────────
    if not _PIL:
        return {"error": "Pillow not installed for frame rendering"}

    pc = RTCPeerConnection()
    _pcs.add(pc)

    @pc.on("connectionstatechange")
    async def _state_change():
        if pc.connectionState in ("failed", "closed"):
            _pcs.discard(pc)

    pc.addTrack(MockVideoTrack(stream_id))

    offer = RTCSessionDescription(sdp=sdp, type=sdp_type)
    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return {
        "sdp":  pc.localDescription.sdp,
        "type": pc.localDescription.type,
    }


async def close_all() -> None:
    await asyncio.gather(*[pc.close() for pc in list(_pcs)])
    _pcs.clear()
