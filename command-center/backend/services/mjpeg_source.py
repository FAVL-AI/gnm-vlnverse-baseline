"""
MJPEG frame source — generates JPEG frames for the multipart stream.

Sources:
  mock        — animated test card (timestamp, zone colour, risk bars)
  ros_topic   — ROS2 image topic subscriber (requires rclpy)
  isaac       — Isaac Sim Python API frame grab (requires omni)

Falls back to mock if the real source is unavailable.
"""
from __future__ import annotations

import asyncio
import io
import math
import time
from typing import AsyncIterator

try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL = True
except ImportError:
    _PIL = False

# ── Minimal fallback JPEG (1×1 black pixel) ───────────────────────────────────
_FALLBACK_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c"
    b"\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c"
    b"\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\x1edL\xa3B\x81\xa3CB\x00\x00"
    b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00"
    b"\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01"
    b"\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x10\x00\x02\x01\x03"
    b"\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05"
    b"\x12!1A\x06\x13Qa\x07\"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br"
    b"\x82\t\n\x16\x17\x18\x19\x1a%&'()*456789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz"
    b"\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2"
    b"\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2"
    b"\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe1"
    b"\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9"
    b"\xfa\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xfb\xd5P\x00\x00\x00\x1f\xff\xd9"
)

# ── Zone colours ──────────────────────────────────────────────────────────────
_ZONE_RGB = {
    "GREEN": (34, 197, 94),
    "AMBER": (245, 158, 11),
    "RED":   (239, 68, 68),
}

W, H = 640, 360


def _make_mock_frame(stream_id: str, tick: int) -> bytes:
    """Draw an animated test card showing stream label, timestamp, mock data."""
    if not _PIL:
        return _FALLBACK_JPEG

    img = Image.new("RGB", (W, H), color=(10, 10, 10))
    draw = ImageDraw.Draw(img)

    # Animated sine-wave zone indicator
    phase = (tick % 300) / 300.0
    risk  = 0.25 + 0.2 * math.sin(phase * 2 * math.pi)
    zone  = "GREEN" if risk < 0.30 else ("AMBER" if risk < 0.55 else "RED")
    zrgb  = _ZONE_RGB[zone]

    # Background gradient bar at top
    for x in range(W):
        r = int(zrgb[0] * (x / W) * 0.3)
        g = int(zrgb[1] * (x / W) * 0.3)
        b = int(zrgb[2] * (x / W) * 0.3)
        draw.line([(x, 0), (x, 3)], fill=(r, g, b))

    # Grid overlay
    for x in range(0, W, 40):
        draw.line([(x, 0), (x, H)], fill=(30, 30, 30))
    for y in range(0, H, 40):
        draw.line([(0, y), (W, y)], fill=(30, 30, 30))

    # Centre crosshair
    cx, cy = W // 2, H // 2
    draw.line([(cx - 20, cy), (cx + 20, cy)], fill=(80, 80, 80), width=1)
    draw.line([(cx, cy - 20), (cx, cy + 20)], fill=(80, 80, 80), width=1)

    # Mock robot position (animated)
    rx = cx + int(80 * math.cos(phase * 2 * math.pi))
    ry = cy + int(40 * math.sin(phase * 2 * math.pi))
    draw.ellipse([(rx - 8, ry - 8), (rx + 8, ry + 8)], outline=(200, 200, 200), width=2)
    draw.line([(rx, ry), (cx, cy)], fill=(60, 60, 60), width=1)

    # Mock agent detections
    for i, (ax, ay) in enumerate([(100, 120), (480, 200), (300, 280)]):
        draw.rectangle([(ax - 15, ay - 30), (ax + 15, ay + 5)],
                       outline=_ZONE_RGB["AMBER"], width=1)
        draw.text((ax - 12, ay - 45), f"p{i}", fill=(180, 180, 180))

    # Stream label
    try:
        font_lg = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 22)
        font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 11)
    except Exception:
        font_lg = font_sm = None

    label = stream_id.upper()
    draw.text((16, 16), label, fill=(220, 220, 220), font=font_lg)

    ts = time.strftime("%H:%M:%S UTC", time.gmtime())
    draw.text((16, 46), ts, fill=(120, 120, 120), font=font_sm)

    # Zone badge
    bx, by = W - 100, 16
    draw.rectangle([(bx, by), (bx + 80, by + 24)], fill=zrgb, outline=None)
    draw.text((bx + 4, by + 4), f"● {zone}", fill=(10, 10, 10), font=font_sm)

    # Risk bar
    bar_y = H - 20
    bar_w = int(W * risk)
    draw.rectangle([(0, bar_y), (W, H)], fill=(15, 15, 15))
    draw.rectangle([(0, bar_y + 4), (bar_w, H - 4)], fill=zrgb)
    draw.text((4, bar_y + 2), f"risk {risk:.2f}", fill=(160, 160, 160), font=font_sm)

    # NOT CONNECTED watermark
    draw.text((cx - 60, cy + 30), "[ MOCK STREAM ]", fill=(50, 50, 50), font=font_sm)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return buf.getvalue()


# ── ROS2 source ───────────────────────────────────────────────────────────────

class _RosFrameCache:
    def __init__(self) -> None:
        self._frame: bytes | None = None
        self._ok = False

    def update(self, frame: bytes) -> None:
        self._frame = frame
        self._ok = True

    def get(self) -> bytes | None:
        return self._frame


_ros_caches: dict[str, _RosFrameCache] = {}


def _try_ros_source(topic: str) -> _RosFrameCache:
    if topic not in _ros_caches:
        cache = _RosFrameCache()
        _ros_caches[topic] = cache
        try:
            import rclpy
            from rclpy.node import Node
            from sensor_msgs.msg import Image as RosImage
            import threading

            def _spin() -> None:
                rclpy.init(args=[])
                node = rclpy.create_node("cc_mjpeg_bridge")

                def _cb(msg: RosImage) -> None:
                    try:
                        from PIL import Image as PIL_Image
                        img = PIL_Image.frombytes("RGB", (msg.width, msg.height),
                                                  bytes(msg.data), "raw", "RGB")
                        buf = io.BytesIO()
                        img.save(buf, format="JPEG", quality=60)
                        cache.update(buf.getvalue())
                    except Exception:
                        pass

                node.create_subscription(RosImage, topic, _cb, 10)
                rclpy.spin(node)

            t = threading.Thread(target=_spin, daemon=True)
            t.start()
        except Exception:
            pass
    return _ros_caches[topic]


# ── Public stream generators ───────────────────────────────────────────────────

async def frame_generator(stream_id: str, fps: int = 15) -> AsyncIterator[bytes]:
    """Yield JPEG frames for a given stream_id at ~fps."""
    from .stream_manager import STREAMS

    s = STREAMS.get(stream_id)
    interval = 1.0 / fps
    tick = 0

    if s is None or s.type != "mjpeg":
        # Shouldn't happen, but yield a fallback indefinitely
        while True:
            yield _FALLBACK_JPEG
            await asyncio.sleep(interval)
            return

    cache: _RosFrameCache | None = None
    if s.mjpeg_source == "ros_topic" and s.ros_topic:
        cache = _try_ros_source(s.ros_topic)

    while True:
        if cache is not None:
            frame = cache.get()
            if frame is None:
                frame = _make_mock_frame(stream_id, tick)
        else:
            frame = _make_mock_frame(stream_id, tick)

        yield frame
        tick += 1
        await asyncio.sleep(interval)
