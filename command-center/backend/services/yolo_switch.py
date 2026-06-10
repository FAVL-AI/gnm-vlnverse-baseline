"""
YOLO mode switch — v0.9.

Toggles between mock perception and real YOLOv8 on the Jetson via SSH.

  Mock mode (default): perception node publishes synthetic detections.
  YOLO mode: real YOLOv8 node runs on Jetson GPU, publishes /fleetsafe/detections
             and /fleetsafe/tracks with camera-derived detections.

Model path and package name are configurable in config.py:
  yolo_model_path  ~/models/yolov8n.pt
  yolo_node_package fleetsafe_perception

In dry_run mode all SSH calls are logged but not executed.
"""
from __future__ import annotations

import threading
import time

from .robot_ops import robot_ops, _audit
from ..config import settings


class YoloSwitch:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = False
        self._started_at: float | None = None

    async def start(self) -> dict:
        with self._lock:
            if self._active:
                return {"ok": False, "error": "YOLO node is already running"}

        cmd = (
            f"nohup ros2 run {settings.yolo_node_package} yolo_node "
            f"--ros-args -p model:={settings.yolo_model_path} "
            f"> /tmp/yolo_node.log 2>&1 & echo $!"
        )
        result = await robot_ops._run(
            "yolo_start",
            cmd,
            {"model": settings.yolo_model_path, "package": settings.yolo_node_package},
        )
        if result["ok"]:
            with self._lock:
                self._active = True
                self._started_at = time.time()

        _audit("yolo_start",
               {"model": settings.yolo_model_path, "dry_run": robot_ops.dry_run},
               "started" if result["ok"] else "error",
               dry_run=robot_ops.dry_run)
        return result

    async def stop(self) -> dict:
        cmd = f"pkill -f '{settings.yolo_node_package}.*yolo_node' || true"
        result = await robot_ops._run("yolo_stop", cmd, {})
        with self._lock:
            self._active = False
            self._started_at = None

        _audit("yolo_stop", {}, "stopped", dry_run=robot_ops.dry_run)
        return result

    def get_status(self) -> dict:
        with self._lock:
            uptime = round(time.time() - self._started_at, 1) if self._started_at else None
            return {
                "active": self._active,
                "mode": "yolo" if self._active else "mock",
                "started_at": self._started_at,
                "uptime_s": uptime,
                "model_path": settings.yolo_model_path,
                "package": settings.yolo_node_package,
                "dry_run": robot_ops.dry_run,
            }


yolo_switch = YoloSwitch()
