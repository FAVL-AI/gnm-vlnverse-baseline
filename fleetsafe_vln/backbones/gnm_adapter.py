"""GNM backbone adapter for FleetSafe-VLN.

Wraps the GNM (General Navigation Model) from visualnav-transformer.
Falls back gracefully if the checkpoint or torch are unavailable.

The GNM input convention (from drive-any-robot):
  obs_image  : [B, C*context_size, H, W]  stacked past frames, normalised
  goal_image : [B, 3, H, W]               goal frame, normalised
  Output     : waypoints  [B, pred_horizon, 2]  in robot frame (dx, dy)

The first predicted waypoint is projected to (vx, wz) at 4 Hz.

Usage:
    adapter = GNMAdapter()
    action  = adapter.run_nominal_policy(goal, camera_context=rgb_frame)
    u_nom   = action.as_list()     # [vx, wz]
"""
from __future__ import annotations

import collections
import math
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

# ── Nominal action compatible with BackboneRouter ──────────────────────────────

class NominalAction:
    def __init__(self, vx: float = 0.0, wz: float = 0.0,
                 backbone: str = "gnm", inference_ms: float = 0.0,
                 waypoints: Optional[List[List[float]]] = None):
        self.vx = vx
        self.wz = wz
        self.backbone = backbone
        self.inference_ms = inference_ms
        self.waypoints = waypoints or []

    def as_list(self) -> List[float]:
        return [self.vx, self.wz]


# ── GNM image preprocessing constants ─────────────────────────────────────────

_IMAGE_SIZE = (160, 120)          # (W, H) — GNM default
_CONTEXT_SIZE = 5                 # number of past frames stacked as observation
_PRED_HORIZON = 5                 # waypoints returned by GNM
_CONTROL_HZ = 4.0                 # Hz — used for waypoint→velocity conversion
_NORM_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_NORM_STD  = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# ── Checkpoint discovery ───────────────────────────────────────────────────────

def _default_ckpt_paths() -> List[Path]:
    repo = Path(__file__).parents[3]
    return [
        repo / "third_party" / "visualnav-transformer" / "model_weights" / "gnm_large.pth",
        repo / "third_party" / "visualnav-transformer" / "model_weights" / "gnm.pth",
        repo / "third_party" / "visualnav-transformer" / "model_weights" / "gnm_fleetsafe.pth",
    ]


def _default_config_paths() -> List[Path]:
    repo = Path(__file__).parents[3]
    return [
        repo / "third_party" / "visualnav-transformer" / "train" / "config" / "gnm" / "gnm_large.yaml",
        repo / "third_party" / "visualnav-transformer" / "train" / "config" / "gnm" / "gnm.yaml",
    ]


# ── Image normalisation ────────────────────────────────────────────────────────

def _preprocess_frame(frame: Any) -> np.ndarray:
    """Resize + normalise one RGB frame to (3, H, W) float32."""
    try:
        from PIL import Image
    except ImportError:
        img = np.zeros((3, _IMAGE_SIZE[1], _IMAGE_SIZE[0]), dtype=np.float32)
        return img

    if isinstance(frame, np.ndarray):
        pil = Image.fromarray(frame.astype(np.uint8))
    else:
        pil = frame

    pil = pil.resize(_IMAGE_SIZE, Image.BILINEAR).convert("RGB")
    arr = np.array(pil, dtype=np.float32) / 255.0            # (H, W, 3)
    arr = (arr - _NORM_MEAN) / _NORM_STD
    return arr.transpose(2, 0, 1)                             # (3, H, W)


# ── Waypoint → velocity ────────────────────────────────────────────────────────

def _waypoint_to_velocity(
    wp: np.ndarray,
    max_vx: float = 0.30,
    max_wz: float = 0.70,
    dt: float = 1.0 / _CONTROL_HZ,
    wz_gain: float = 2.0,
) -> tuple[float, float]:
    """Convert GNM (dx, dy) waypoint in robot frame to (vx, wz)."""
    dx, dy = float(wp[0]), float(wp[1])
    dist = math.hypot(dx, dy)
    vx = min(dist / dt, max_vx)
    # dy positive → turn left → positive wz
    wz = math.atan2(dy, max(dx, 1e-6)) * wz_gain
    wz = max(-max_wz, min(max_wz, wz))
    return vx, wz


# ── GNM model loader ───────────────────────────────────────────────────────────

def _try_load_gnm_model(ckpt_path: Path) -> Any:
    """Load GNM model from checkpoint. Returns model or None."""
    if not ckpt_path.exists():
        return None
    try:
        import torch
    except ImportError:
        return None

    # Try loading the model class from visualnav-transformer
    repo = Path(__file__).parents[3]
    train_dir = repo / "third_party" / "visualnav-transformer" / "train"
    vnt_train_dir = train_dir / "vint_train"

    import sys
    for p in [str(train_dir), str(vnt_train_dir)]:
        if p not in sys.path:
            sys.path.insert(0, p)

    try:
        from vint_train.models.gnm.gnm import GNM  # type: ignore
        model = GNM(
            context_size=_CONTEXT_SIZE,
            len_traj_pred=_PRED_HORIZON,
            learn_angle=False,
            obs_encoding_size=1024,
            goal_encoding_size=1024,
        )
        state = torch.load(str(ckpt_path), map_location="cpu")
        # Checkpoints may be wrapped in a 'model' key
        if isinstance(state, dict) and "model" in state:
            state = state["model"]
        elif isinstance(state, dict) and "state_dict" in state:
            state = state["state_dict"]
        model.load_state_dict(state, strict=False)
        model.eval()
        return model
    except Exception as exc:
        print(f"[gnm_adapter] Model load failed ({ckpt_path.name}): {exc}")
        return None


# ── GNMAdapter ────────────────────────────────────────────────────────────────

class GNMAdapter:
    """FleetSafe GNM backbone adapter.

    Wraps the GNM model from visualnav-transformer. Falls back to a simple
    forward-moving mock when the checkpoint or torch are unavailable.

    Parameters
    ----------
    ckpt_path  : explicit checkpoint path; None → search default locations
    context_size : number of past frames to stack (default 5)
    max_vx, max_wz : velocity limits clipped at output
    """

    backbone_name = "gnm"

    def __init__(
        self,
        ckpt_path: Optional[str | Path] = None,
        context_size: int = _CONTEXT_SIZE,
        max_vx: float = 0.30,
        max_wz: float = 0.70,
    ):
        self._context_size = context_size
        self._max_vx = max_vx
        self._max_wz = max_wz

        # Ring buffer of preprocessed context frames (3, H, W) each
        self._context: collections.deque = collections.deque(maxlen=context_size)

        # Resolve checkpoint
        if ckpt_path is not None:
            ckpt_paths = [Path(ckpt_path)]
        else:
            ckpt_paths = _default_ckpt_paths()

        self._model = None
        for p in ckpt_paths:
            m = _try_load_gnm_model(p)
            if m is not None:
                self._model = m
                self._ckpt_path = p
                print(f"[gnm_adapter] Loaded GNM from {p.name}")
                break

        if self._model is None:
            print("[gnm_adapter] No GNM checkpoint found — running mock backbone.")

    # ── Public API (compatible with BackboneRouter interface) ──────────────────

    def run_nominal_policy(
        self,
        goal: Any,
        camera_context: Optional[Any] = None,
        instruction: Optional[Any] = None,
    ) -> NominalAction:
        """Return nominal (vx, wz) action.

        Parameters
        ----------
        goal           : goal image (numpy RGB array) or a GroundedGoal object
        camera_context : current RGB frame (numpy array H×W×3)
        instruction    : ignored (GNM uses image goal, not text)
        """
        t0 = time.perf_counter()

        # Extract goal image
        goal_img = self._extract_goal_image(goal)

        # Push current frame into context buffer
        if camera_context is not None:
            self._context.append(_preprocess_frame(camera_context))

        # Fill context to required size with blank frames if needed
        while len(self._context) < self._context_size:
            self._context.append(
                np.zeros((3, _IMAGE_SIZE[1], _IMAGE_SIZE[0]), dtype=np.float32)
            )

        if self._model is None:
            # Mock: go mostly forward, slight wz from goal bearing
            vx, wz = self._mock_action(goal)
            return NominalAction(
                vx=vx, wz=wz, backbone="gnm_mock",
                inference_ms=(time.perf_counter() - t0) * 1000,
            )

        waypoints = self._run_gnm_inference(goal_img)
        if waypoints is None:
            vx, wz = self._mock_action(goal)
        else:
            vx, wz = _waypoint_to_velocity(
                waypoints[0], self._max_vx, self._max_wz
            )

        return NominalAction(
            vx=vx,
            wz=wz,
            backbone=self.backbone_name,
            inference_ms=(time.perf_counter() - t0) * 1000,
            waypoints=waypoints.tolist() if waypoints is not None else [],
        )

    @classmethod
    def is_available(cls) -> bool:
        """Return True if at least one default checkpoint exists."""
        return any(p.exists() for p in _default_ckpt_paths())

    def reset_context(self) -> None:
        """Clear context buffer — call at episode start."""
        self._context.clear()

    # ── Internals ──────────────────────────────────────────────────────────────

    def _run_gnm_inference(self, goal_img: np.ndarray) -> Optional[np.ndarray]:
        """Run GNM forward pass. Returns waypoints [pred_horizon, 2] or None."""
        try:
            import torch
            with torch.no_grad():
                # obs: (1, context_size*3, H, W)
                obs = np.stack(list(self._context), axis=0)           # (C_size, 3, H, W)
                obs = obs.reshape(1, -1, _IMAGE_SIZE[1], _IMAGE_SIZE[0])  # (1, C*3, H, W)
                obs_t = torch.from_numpy(obs)

                # goal: (1, 3, H, W)
                goal_t = torch.from_numpy(goal_img[None])

                out = self._model(obs_t, goal_t)

                # GNM returns (waypoints,) or (waypoints, goal_distance)
                if isinstance(out, (tuple, list)):
                    waypoints = out[0]
                else:
                    waypoints = out

                wp = waypoints[0].cpu().numpy()  # (pred_horizon, 2)
                return wp
        except Exception as exc:
            print(f"[gnm_adapter] Inference error: {exc}")
            return None

    def _extract_goal_image(self, goal: Any) -> np.ndarray:
        """Extract and preprocess a goal image from various input types."""
        if isinstance(goal, np.ndarray):
            return _preprocess_frame(goal)
        # GroundedGoal or similar object with image_goal attribute
        if hasattr(goal, "image_goal") and goal.image_goal is not None:
            return _preprocess_frame(goal.image_goal)
        # Blank goal
        return np.zeros((3, _IMAGE_SIZE[1], _IMAGE_SIZE[0]), dtype=np.float32)

    def _mock_action(self, goal: Any) -> tuple[float, float]:
        """Simple mock: go forward, slight turn toward semantic goal direction."""
        vx = self._max_vx * 0.6
        wz = 0.0
        # If the goal has a bearing hint, use it
        if hasattr(goal, "nominal_wz"):
            wz = max(-self._max_wz, min(self._max_wz, float(goal.nominal_wz)))
        return vx, wz
