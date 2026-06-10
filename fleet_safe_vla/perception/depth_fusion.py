"""
depth_fusion.py — RGB-D 2-D world position estimation from depth maps.

Given a bounding-box centre pixel and a depth image, estimates the (x, y)
position of the agent in the robot's local floor frame using a pinhole camera
model.  Assumes the camera is mounted at a fixed height pointing roughly forward.

Coordinate convention (ROS REP 103)
-------------------------------------
  x  — forward (depth direction)
  y  — left
  z  — up (not used here; we project to floor plane)

Camera intrinsics
-----------------
Pass a CameraIntrinsics instance built from your sensor spec.  Defaults match
the Intel RealSense D435i at 640×480.

Depth image format
------------------
Accepts either:
  - uint16 numpy array  (millimetres, as produced by D435i)
  - float32 numpy array (metres)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass
class CameraIntrinsics:
    """
    Pinhole camera intrinsics.

    Parameters
    ----------
    fx, fy : focal lengths in pixels
    cx, cy : principal point in pixels
    height  : image height (pixels) — used only for validity checks
    width   : image width  (pixels)
    camera_height_m : mounting height above floor (metres)
    camera_pitch_rad : downward tilt of optical axis from horizontal (radians)
                       Positive = tilted down.  0 = perfectly horizontal.
    """
    fx: float = 615.0
    fy: float = 615.0
    cx: float = 320.0
    cy: float = 240.0
    width:  int = 640
    height: int = 480
    camera_height_m:   float = 0.50
    camera_pitch_rad:  float = 0.0


class DepthFusion:
    """
    Estimate 2-D world (floor-plane) position of a detection from a depth image.

    Parameters
    ----------
    intrinsics : CameraIntrinsics
    depth_scale : multiplier to convert raw depth pixel values to metres.
                  For uint16 mm images (D435i default) use 0.001.
                  For float32 metre images use 1.0.
    max_depth_m : detections beyond this distance are rejected (returns None).
    median_kernel : pixel radius around the bbox centre used for median depth.
                    Larger values are more robust to depth holes.
    """

    def __init__(
        self,
        intrinsics: CameraIntrinsics | None = None,
        depth_scale: float = 0.001,
        max_depth_m: float = 8.0,
        median_kernel: int = 5,
    ) -> None:
        self._K = intrinsics or CameraIntrinsics()
        self._scale = depth_scale
        self._max_depth = max_depth_m
        self._kernel = max(1, median_kernel)

    def pixel_to_world(
        self,
        u: float,
        v: float,
        depth_image: Any,
    ) -> tuple[float, float] | None:
        """
        Convert a pixel (u, v) and depth image to a floor-plane (x, y) position.

        Parameters
        ----------
        u, v        : pixel coordinates (float OK, will be rounded to int)
        depth_image : numpy array HxW — uint16 (mm) or float32 (m)

        Returns
        -------
        (x_m, y_m) in robot-local floor frame, or None if depth is invalid.
        """
        try:
            import numpy as np
        except ImportError:
            return _fallback_pixel_to_world(u, v, self._K)

        ui, vi = int(round(u)), int(round(v))
        H, W = depth_image.shape[:2]

        k = self._kernel
        u0, u1 = max(0, ui - k), min(W, ui + k + 1)
        v0, v1 = max(0, vi - k), min(H, vi + k + 1)

        patch = depth_image[v0:v1, u0:u1]
        if patch.size == 0:
            return None

        raw = float(np.median(patch[patch > 0])) if np.any(patch > 0) else 0.0
        depth_m = raw * self._scale

        if depth_m <= 0.0 or depth_m > self._max_depth or math.isnan(depth_m):
            return None

        # Un-project to camera frame (pinhole)
        K = self._K
        x_cam = (u - K.cx) * depth_m / K.fx
        y_cam = (v - K.cy) * depth_m / K.fy
        z_cam = depth_m  # forward

        # Rotate from camera frame to robot floor frame
        # Camera pitched down by camera_pitch_rad → rotation around y-axis
        pitch = K.camera_pitch_rad
        cp, sp = math.cos(pitch), math.sin(pitch)
        x_world =  cp * z_cam + sp * y_cam  # forward
        y_world = -x_cam                     # left (ROS convention)
        # z_world = -sp * z_cam + cp * y_cam — not used

        return (round(x_world, 4), round(y_world, 4))

    def fill_positions(
        self,
        detections: list[Any],
        depth_image: Any,
        robot_xy: tuple[float, float] = (0.0, 0.0),
    ) -> list[Any]:
        """
        Fill position_xy on each DetectionResult using the depth image.

        Detections whose depth is invalid keep position_xy = (0, 0).

        Parameters
        ----------
        detections  : list[DetectionResult] from SemanticDetector.detect()
        depth_image : depth image (numpy HxW)
        robot_xy    : robot position in global frame (metres); added as offset.

        Returns
        -------
        The same list with position_xy mutated in-place (also returned).
        """
        if depth_image is None:
            return detections

        rx, ry = robot_xy
        for det in detections:
            u, v = det.center_xy_px
            local = self.pixel_to_world(u, v, depth_image)
            if local is not None:
                det.position_xy = (rx + local[0], ry + local[1])
        return detections


# ── Pure-Python fallback (no numpy) ──────────────────────────────────────────

def _fallback_pixel_to_world(
    u: float, v: float, K: CameraIntrinsics
) -> tuple[float, float] | None:
    """
    Rough forward-projection assuming depth = camera_height_m / tan(pitch).
    Used only when numpy is unavailable.
    """
    pitch = K.camera_pitch_rad
    if abs(pitch) < 1e-6:
        return None  # can't estimate without pitch or depth
    depth_m = K.camera_height_m / math.tan(abs(pitch))
    x_cam = (u - K.cx) * depth_m / K.fx
    y_cam = (v - K.cy) * depth_m / K.fy
    x_world = depth_m
    y_world = -x_cam
    return (round(x_world, 4), round(y_world, 4))
