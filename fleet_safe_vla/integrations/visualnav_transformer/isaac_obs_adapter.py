"""
isaac_obs_adapter.py — Egocentric camera observation adapter for Isaac Sim / MuJoCo.

Bridges robot-mounted forward-facing camera frames to the (obs_imgs, goal_img)
format expected by VisualNav navigation model adapters (GNM, ViNT, NoMaD).

Perception contract
-------------------
The navigation backbone is constrained to **egocentric forward-facing camera
observations only**.  The safety layer (FleetSafe CBF-QP) may use robot state
and obstacle estimates, but this information is never exposed to the learned
navigation policy.  This separates perception-driven navigation from safety
supervision and removes privileged simulator observation from the policy input.

    camera frames  ──►  IsaacCameraObsAdapter  ──►  adapter.preprocess_observation()
                                                            │
                                                     navigation model (GNM/ViNT/NoMaD)
                                                            │
                                                         u_nom
                                                            │
                   robot state + obstacle geometry  ──►  CBF-QP  ──►  u_safe

The render_mujoco() method MUST be called with cam_name="camera", which refers
to the <camera name="camera"> element inside the robot's base_link body in the
MJCF.  If that camera is absent, the method falls back to the free spectator
camera — a third-person external view that violates the perception contract.
benchmark_runner._render_camera() raises RuntimeError if the camera is missing.

Responsibilities
----------------
1. Receive raw RGB frames from the robot-mounted camera (simulation or real).
2. Resize to the model's required image size.
3. Maintain a context queue (last N frames, oldest first).
4. Accept a goal image set from a reference snapshot or goal pose.
5. Support MuJoCo off-screen rendering via mujoco.Renderer.
6. Support Isaac Sim camera via omni.replicator render product.

Usage (MuJoCo)
--------------
    obs_adapter = IsaacCameraObsAdapter(image_size=(85, 64), context_size=5)
    obs_adapter.set_goal_from_file(Path("data/goal.png"))

    # Per simulation step — renders from robot's forward-facing camera:
    rgb = IsaacCameraObsAdapter.render_mujoco(model, data, cam_name="camera")
    obs_adapter.push_frame(rgb)

    obs_imgs, goal_img = obs_adapter.get_context()
    preprocessed = model_adapter.preprocess_observation(obs_imgs, goal_img)
"""
from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import NamedTuple

import numpy as np

# ── Camera descriptor ─────────────────────────────────────────────────────────

class CameraConfig(NamedTuple):
    cam_name:    str   = "camera"
    width:       int   = 640
    height:      int   = 480
    fov_deg:     float = 60.0   # horizontal FOV


# ── Adapter ───────────────────────────────────────────────────────────────────

class IsaacCameraObsAdapter:
    """
    Manages the camera context queue and goal image for VisualNav inference.

    Parameters
    ----------
    image_size    : (width, height) the model expects (e.g. (85, 64) for GNM).
    context_size  : number of past frames to maintain (must match model config).
    camera_config : camera name and resolution for MuJoCo/Isaac rendering.
    """

    def __init__(
        self,
        image_size:    tuple[int, int]    = (85, 64),
        context_size:  int                = 5,
        camera_config: CameraConfig | None = None,
    ) -> None:
        self.image_size    = image_size
        self.context_size  = context_size
        self.camera_cfg    = camera_config or CameraConfig()
        self._queue: deque[np.ndarray] = deque(maxlen=context_size)
        self._goal_img: np.ndarray | None = None

    # ── Goal image management ─────────────────────────────────────────────────

    def set_goal_image(self, goal_rgb: np.ndarray) -> None:
        """Set goal from a (H, W, 3) uint8 numpy array (RGB)."""
        self._goal_img = self._resize(goal_rgb)

    def set_goal_from_file(self, path: Path) -> None:
        """Load goal image from PNG/JPG file."""
        from PIL import Image
        img = np.array(Image.open(path).convert("RGB"))
        self.set_goal_image(img)

    def set_goal_from_current_frame(self) -> None:
        """Snapshot the most recent context frame as the goal."""
        if not self._queue:
            raise RuntimeError("No frames in queue — push at least one frame first.")
        self._goal_img = self._queue[-1].copy()

    def has_goal(self) -> bool:
        return self._goal_img is not None

    # ── Frame management ──────────────────────────────────────────────────────

    def push_frame(self, raw_rgb: np.ndarray) -> None:
        """Resize raw_rgb and append to the context queue."""
        self._queue.append(self._resize(raw_rgb))

    def reset(self) -> None:
        """Clear the context queue (call at episode start)."""
        self._queue.clear()

    def get_context(self) -> tuple[list[np.ndarray], np.ndarray]:
        """
        Return (obs_imgs, goal_img) ready for adapter.preprocess_observation().

        obs_imgs  : list of context_size (H, W, 3) uint8 arrays, oldest first.
                    Padded with the first frame if fewer frames are available.
        goal_img  : (H, W, 3) uint8 goal array.

        Raises
        ------
        RuntimeError  if no goal image is set and no frames in queue.
        """
        if not self._queue:
            raise RuntimeError(
                "Context queue is empty.  Call push_frame() at least once."
            )
        if self._goal_img is None:
            raise RuntimeError(
                "Goal image is not set.  Call set_goal_image() or "
                "set_goal_from_current_frame() before the first inference step."
            )

        imgs = list(self._queue)
        while len(imgs) < self.context_size:
            imgs = [imgs[0]] + imgs

        return imgs, self._goal_img.copy()

    # ── MuJoCo off-screen rendering ───────────────────────────────────────────

    @staticmethod
    def render_mujoco(
        model: "mujoco.MjModel",
        data:  "mujoco.MjData",
        cam_name: str = "camera",
        width:  int   = 640,
        height: int   = 480,
    ) -> np.ndarray:
        """
        Off-screen render from a named camera in a MuJoCo scene.

        Returns
        -------
        (H, W, 3) uint8 RGB array.

        Notes
        -----
        The M3Pro MJCF has a <site name="camera"> but not a <camera> element.
        To render from the robot's camera perspective, add a <camera> element
        to the MJCF pointing from the camera site, or use cam_name="free" for
        the default free camera.

        A global camera named "overview" is generated automatically if the
        MJCF has no named cameras (useful for benchmark development).
        """
        try:
            import mujoco
        except ImportError as exc:
            raise RuntimeError("mujoco not installed.") from exc

        renderer = mujoco.Renderer(model, height=height, width=width)
        cam_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, cam_name)
        if cam_id < 0:
            renderer.update_scene(data)
        else:
            renderer.update_scene(data, camera=cam_name)
        rgb = renderer.render()
        renderer.close()
        return rgb.astype(np.uint8)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _resize(self, img: np.ndarray) -> np.ndarray:
        """Resize to self.image_size using PIL (LANCZOS quality)."""
        from PIL import Image
        W, H = self.image_size
        return np.array(
            Image.fromarray(img).resize((W, H), Image.LANCZOS),
            dtype=np.uint8,
        )

    # ── Synthetic goal generator (for testing without visual data) ────────────

    @staticmethod
    def make_checkerboard_goal(
        width: int = 85, height: int = 64, block_size: int = 8
    ) -> np.ndarray:
        """
        Generate a synthetic checkerboard 'goal' image for Gate 2 and 3 testing.

        This is NOT a real navigation goal — it only exercises the preprocessing
        and inference pipeline without requiring actual training scenes.
        """
        img = np.zeros((height, width, 3), dtype=np.uint8)
        for y in range(0, height, block_size):
            for x in range(0, width, block_size):
                if (x // block_size + y // block_size) % 2 == 0:
                    img[y:y+block_size, x:x+block_size] = [200, 200, 200]
        return img

    @staticmethod
    def make_random_obs(
        width: int = 85, height: int = 64, seed: int | None = None
    ) -> np.ndarray:
        """Random RGB image for pipeline smoke tests."""
        rng = np.random.default_rng(seed)
        return rng.integers(0, 256, (height, width, 3), dtype=np.uint8)
