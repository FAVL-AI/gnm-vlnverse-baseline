#!/usr/bin/env python3
"""FleetSafe real robot camera web viewer.

Subscribes to a ROS2 sensor_msgs/msg/Image topic and serves the latest
frame as a BMP via a minimal stdlib HTTP server.  No external dependencies
beyond rclpy and the standard library.

Run with /usr/bin/python3 after sourcing /opt/ros/humble/setup.bash.

Usage:
    /usr/bin/python3 scripts/viewers/ros_camera_bmp_server.py
    /usr/bin/python3 scripts/viewers/ros_camera_bmp_server.py \\
        --topic /camera/color/image_raw --port 8081
"""

import argparse
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

# ROS2 imports — available after source /opt/ros/humble/setup.bash
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image

# ── Globals shared between ROS thread and HTTP thread ────────────────────────
_lock = threading.Lock()
_latest_bmp: bytes = b""
_frame_count = 0
_last_topic = ""

# ── BMP encoder (stdlib only) ─────────────────────────────────────────────────

def _rgb8_to_bmp(width: int, height: int, data: bytes) -> bytes:
    """Encode raw RGB8 pixel data to a 24-bit BMP byte string."""
    # BMP rows must be padded to 4-byte boundaries; stored bottom-up
    row_bytes = width * 3
    pad = (4 - (row_bytes % 4)) % 4
    padded_row = row_bytes + pad
    pixel_data_size = padded_row * height
    file_size = 54 + pixel_data_size

    file_header = struct.pack(
        "<2sIHHI",
        b"BM",
        file_size,
        0, 0,
        54,  # pixel data offset
    )
    info_header = struct.pack(
        "<IiiHHIIiiII",
        40,          # header size
        width,
        -height,     # negative = top-down (skip row reversal)
        1,           # color planes
        24,          # bits per pixel
        0,           # no compression
        pixel_data_size,
        2835, 2835,  # ~72 dpi
        0, 0,        # colors in table
    )
    # Convert RGB → BGR (BMP native) and add row padding
    rows = []
    for y in range(height):
        row_start = y * width * 3
        row = bytearray()
        for x in range(width):
            o = row_start + x * 3
            r, g, b = data[o], data[o + 1], data[o + 2]
            row += bytes([b, g, r])
        row += b"\x00" * pad
        rows.append(bytes(row))
    return file_header + info_header + b"".join(rows)


def _bgr8_to_bmp(width: int, height: int, data: bytes) -> bytes:
    """Encode raw BGR8 pixel data to a 24-bit BMP byte string."""
    row_bytes = width * 3
    pad = (4 - (row_bytes % 4)) % 4
    padded_row = row_bytes + pad
    pixel_data_size = padded_row * height
    file_size = 54 + pixel_data_size

    file_header = struct.pack("<2sIHHI", b"BM", file_size, 0, 0, 54)
    info_header = struct.pack(
        "<IiiHHIIiiII", 40, width, -height, 1, 24, 0, pixel_data_size, 2835, 2835, 0, 0
    )
    rows = []
    for y in range(height):
        row_start = y * width * 3
        row = data[row_start : row_start + width * 3]
        rows.append(row + b"\x00" * pad)
    return file_header + info_header + b"".join(rows)


# ── ROS2 subscriber node ──────────────────────────────────────────────────────

class CameraViewerNode(Node):
    def __init__(self, topic: str):
        super().__init__("fleetsafe_camera_viewer")
        self._sub = self.create_subscription(Image, topic, self._cb, 1)
        self.get_logger().info(f"Subscribed to {topic}")

    def _cb(self, msg: Image):
        global _latest_bmp, _frame_count, _last_topic
        encoding = msg.encoding.lower()
        data = bytes(msg.data)
        try:
            if encoding in ("rgb8",):
                bmp = _rgb8_to_bmp(msg.width, msg.height, data)
            elif encoding in ("bgr8",):
                bmp = _bgr8_to_bmp(msg.width, msg.height, data)
            elif encoding in ("mono8",):
                # Convert mono to RGB for simplicity
                rgb = bytearray(msg.width * msg.height * 3)
                for i, v in enumerate(data[: msg.width * msg.height]):
                    rgb[i * 3] = rgb[i * 3 + 1] = rgb[i * 3 + 2] = v
                bmp = _rgb8_to_bmp(msg.width, msg.height, bytes(rgb))
            else:
                self.get_logger().warning(
                    f"Unsupported encoding '{encoding}', skipping frame"
                )
                return
        except Exception as exc:  # noqa: BLE001
            self.get_logger().error(f"BMP encode error: {exc}")
            return

        with _lock:
            _latest_bmp = bmp
            _frame_count += 1
            _last_topic = msg.header.frame_id or "camera"


# ── HTTP handler ──────────────────────────────────────────────────────────────

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>FleetSafe Real Robot Camera</title>
<meta http-equiv="refresh" content="0.2">
<style>
body {{background:#111;color:#eee;font-family:monospace;text-align:center;margin:0;padding:0}}
h2 {{margin:0.4em 0 0.2em;font-size:1.1em;color:#7cf}}
img {{max-width:100%;border:2px solid #444;display:block;margin:0 auto}}
p {{font-size:0.8em;color:#888;margin:0.2em}}
</style>
</head>
<body>
<h2>FleetSafe Real Robot Camera</h2>
<img src="/frame.bmp" alt="camera frame">
<p>Topic: {topic} &nbsp;|&nbsp; Frames: {frames} &nbsp;|&nbsp; {ts}</p>
</body>
</html>
"""


class CameraHTTPHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # silence access log
        pass

    def do_GET(self):  # noqa: N802
        if self.path == "/frame.bmp":
            with _lock:
                data = _latest_bmp
            if not data:
                self.send_response(503)
                self.end_headers()
                self.wfile.write(b"No frame yet")
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/bmp")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        else:
            with _lock:
                frames = _frame_count
                topic = _last_topic
            html = _HTML_TEMPLATE.format(
                topic=topic or "(waiting…)",
                frames=frames,
                ts=time.strftime("%H:%M:%S"),
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="FleetSafe ROS2 camera web viewer")
    parser.add_argument(
        "--topic",
        default="/camera/color/image_raw",
        help="ROS2 image topic (default: /camera/color/image_raw)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8081,
        help="HTTP port (default: 8081)",
    )
    args = parser.parse_args()

    rclpy.init()
    node = CameraViewerNode(args.topic)

    ros_thread = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
    ros_thread.start()

    server = HTTPServer(("0.0.0.0", args.port), CameraHTTPHandler)
    print(f"[fleetsafe-viewer] Listening on http://127.0.0.1:{args.port}")
    print(f"[fleetsafe-viewer] Subscribing to {args.topic}")
    print("[fleetsafe-viewer] Ctrl-C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
