"""Isaac Sim sensor utilities for GNM.

This module runs inside Isaac Sim's Python (not the training conda env).

Sensor specification
─────────────────────
  Camera: RGB 224×224, 90° HFOV, mounted at robot eye height (~1.2 m)
  Coordinate axes (Isaac convention): +X=forward, +Y=left, +Z=up
  Frame rate: 5 Hz (controlled by simulation step + decimation)

Why 224×224?
  This is the standard ImageNet resolution.  GNM is trained at 96×96 but
  we capture at 224×224 and resize to preserve fine details in the crop.
  Some ablations use 64×64 — all are converted at inference.

Why 90° HFOV?
  Wide enough to see obstacles to the sides.  Narrow enough that distant
  goals are still identifiable.  The original GNM paper used 90°.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

try:
    import omni.replicator.core as rep
    from pxr import Gf, UsdGeom
    _ISAAC_AVAILABLE = True
except ImportError:
    _ISAAC_AVAILABLE = False


class GNMCamera:
    """RGB camera sensor for GNM.

    Parameters
    ----------
    prim_path : str
        USD prim path where the camera will be created, e.g.
        "/World/YahboomM3Pro/Camera"
    resolution : tuple[int, int]
        (width, height) in pixels.  Default: (224, 224)
    hfov_deg : float
        Horizontal field-of-view in degrees.  Default: 90°
    mount_height : float
        Camera Z offset from robot base in metres.  Default: 1.2
    """

    def __init__(
        self,
        prim_path: str = "/World/YahboomM3Pro/Camera",
        resolution: tuple[int, int] = (224, 224),
        hfov_deg: float = 90.0,
        mount_height: float = 1.2,
    ) -> None:
        if not _ISAAC_AVAILABLE:
            raise ImportError(
                "This module requires Isaac Sim's bundled Python. "
                "It cannot be used in the gnm_train conda env."
            )
        self.prim_path    = prim_path
        self.resolution   = resolution
        self.hfov_deg     = hfov_deg
        self.mount_height = mount_height
        self._camera      = None
        self._render_prod = None

    def create(self) -> None:
        """Create and configure the USD camera prim."""
        import omni.usd
        from pxr import UsdGeom, Gf

        stage = omni.usd.get_context().get_stage()

        # Create camera prim
        cam_prim = stage.DefinePrim(self.prim_path, "Camera")
        camera   = UsdGeom.Camera(cam_prim)

        # Set field of view
        # Isaac uses focal length + horizontal aperture to derive FOV
        # horizontal_aperture = 2 * focal_length * tan(hfov/2)
        import math
        h_aperture   = 20.955          # mm — standard sensor size
        focal_length = h_aperture / (2 * math.tan(math.radians(self.hfov_deg / 2)))
        camera.GetFocalLengthAttr().Set(focal_length)
        camera.GetHorizontalApertureAttr().Set(h_aperture)

        # Mount height (translate camera up)
        xform = UsdGeom.Xformable(cam_prim)
        xform.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, self.mount_height))

        # Face forward (no rotation needed — Isaac +X is already forward)
        self._camera = camera

    def attach_render_product(self) -> None:
        """Attach a replicator render product for frame capture."""
        self._render_prod = rep.create.render_product(
            self.prim_path,
            resolution=self.resolution,
        )
        self._rgb_annot = rep.AnnotatorRegistry.get_annotator("rgb")
        self._rgb_annot.attach([self._render_prod])

    def capture(self) -> np.ndarray:
        """Capture one RGB frame.

        Returns
        -------
        np.ndarray of shape (H, W, 3) uint8, RGB channel order.
        """
        data = self._rgb_annot.get_data()
        # Isaac returns RGBA — drop alpha channel
        if data is None or data.size == 0:
            return np.zeros((*self.resolution[::-1], 3), dtype=np.uint8)
        rgb = data[..., :3]
        return rgb.astype(np.uint8)

    def get_intrinsics(self) -> dict:
        """Return camera intrinsic parameters (for depth estimation or mapping)."""
        import math
        w, h  = self.resolution
        fov_h = math.radians(self.hfov_deg)
        fx    = (w / 2) / math.tan(fov_h / 2)
        fov_v = 2 * math.atan(h / (2 * fx))
        fy    = (h / 2) / math.tan(fov_v / 2)
        return {
            "fx": fx, "fy": fy,
            "cx": w / 2, "cy": h / 2,
            "width": w, "height": h,
            "hfov_deg": self.hfov_deg,
        }


class GNMPoseSensor:
    """Read robot ground-truth pose from Isaac Sim.

    In a real deployment, this would come from wheel odometry or SLAM.
    For evaluation in Isaac, we use the ground-truth USD transform.
    """

    def __init__(self, robot_prim_path: str = "/World/YahboomM3Pro") -> None:
        self.prim_path = robot_prim_path

    def get_pose(self) -> tuple[float, float, float]:
        """Return (x, y, yaw_radians) in the Isaac world frame."""
        import omni.usd
        from pxr import UsdGeom, Gf
        import math

        stage = omni.usd.get_context().get_stage()
        prim  = stage.GetPrimAtPath(self.prim_path)
        if not prim.IsValid():
            return 0.0, 0.0, 0.0

        xformable = UsdGeom.Xformable(prim)
        transform  = xformable.ComputeLocalToWorldTransform(0)
        translation = transform.ExtractTranslation()
        rotation    = transform.ExtractRotation()

        x, y = float(translation[0]), float(translation[1])

        # Extract yaw from quaternion
        q = rotation.GetQuat()
        qw, qx, qy, qz = q.real, q.imaginary[0], q.imaginary[1], q.imaginary[2]
        yaw = math.atan2(2 * (qw * qz + qx * qy), 1 - 2 * (qy * qy + qz * qz))

        return x, y, yaw
