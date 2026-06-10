"""
base_adapter.py — Abstract interface for VisualNav-Transformer model adapters.

Every concrete adapter (GNM, ViNT, NoMaD) subclasses BaseVisualNavAdapter and
implements the five required methods.  FleetSafeWrapper wraps any adapter instance.

Design rules
------------
- No upstream imports at module level; import inside load_checkpoint() so
  the module is always importable even when upstream is not cloned yet.
- Fail with UpstreamNotFoundError / CheckpointNotFoundError — not ImportError — so
  validate_gates.py can distinguish the two failure modes.
- action_to_cmd_vel() is a concrete default (proportional waypoint controller);
  subclasses may override for model-specific tuning.
"""
from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


def find_repo_root() -> Path:
    """Walk upward from this file until pyproject.toml + scripts/visualnav are found."""
    env_root = os.environ.get("FLEETSAFE_REPO_ROOT")
    if env_root:
        return Path(env_root).resolve()
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").exists() and (candidate / "scripts" / "visualnav").exists():
            return candidate
    raise RuntimeError(
        f"Cannot locate repo root from {Path(__file__).resolve()}. "
        "Set FLEETSAFE_REPO_ROOT to the Fleet-Safe-VLA-OS directory."
    )

# ── Custom exceptions ─────────────────────────────────────────────────────────

class UpstreamNotFoundError(RuntimeError):
    """Raised when third_party/visualnav-transformer is not cloned."""

class CheckpointNotFoundError(FileNotFoundError):
    """Raised when a model checkpoint file is missing."""


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class CmdVel:
    """3-DoF velocity command (holonomic)."""
    vx: float        # forward velocity (m/s)
    vy: float        # lateral velocity (m/s); 0 for differential drive
    wz: float        # yaw rate (rad/s)

    def as_array(self) -> np.ndarray:
        return np.array([self.vx, self.vy, self.wz], dtype=np.float32)


@dataclass
class ActionOutput:
    """
    Structured output from a VisualNav model inference step.

    waypoints   — (N, 2) predicted waypoints in robot frame (metres).
                  Column 0 = forward (x), Column 1 = lateral (y).
                  N = action_horizon (model-specific, typically 5–8).
    goal_distance — estimated number of control steps to goal (float).
                    None if the model does not predict it.
    goal_reached  — True if model predicts the goal is reachable within 1 step.
    raw_output    — Full dict of tensors/arrays from the model (for logging).
    model_name    — Tag identifying the model (e.g. "gnm", "vint", "nomad").
    inference_ms  — Wall-clock inference time for latency tracking.
    """
    waypoints:      np.ndarray
    goal_distance:  float | None = None
    goal_reached:   bool         = False
    raw_output:     dict         = field(default_factory=dict)
    model_name:     str          = ""
    inference_ms:   float        = 0.0


# ── Proportional waypoint controller (shared default) ────────────────────────

def waypoints_to_cmd_vel(
    waypoints: np.ndarray,
    *,
    v_max: float  = 0.3,
    vy_max: float = 0.0,
    w_max: float  = 0.7,
    control_hz: float = 4.0,
) -> CmdVel:
    """
    Convert the first predicted waypoint to a velocity command.

    waypoints[0] = (dx, dy) displacement in robot frame [metres] over one
    control step (dt = 1 / control_hz).

    Proportional controller:
      vx  = clip(dx * control_hz, 0, v_max)     — scale distance → speed
      vy  = clip(dy * control_hz, -vy_max, vy_max)  — holonomic strafe
      wz  = clip(atan2(dy, dx), -w_max, w_max)  — heading error
    """
    if len(waypoints) == 0:
        return CmdVel(0.0, 0.0, 0.0)

    dx, dy = float(waypoints[0, 0]), float(waypoints[0, 1])
    heading = float(np.arctan2(dy, dx))
    dist    = float(np.hypot(dx, dy))

    vx  = float(np.clip(dist * control_hz, 0.0, v_max))
    vy  = float(np.clip(dy * control_hz, -vy_max, vy_max)) if vy_max > 0 else 0.0
    wz  = float(np.clip(heading, -w_max, w_max))

    return CmdVel(vx=vx, vy=vy, wz=wz)


# ── Abstract base class ───────────────────────────────────────────────────────

class BaseVisualNavAdapter(ABC):
    """
    Abstract adapter for a VisualNav-Transformer model.

    Concrete subclasses: GNMAdapter, ViNTAdapter, NoMaDAdapter.

    Usage
    -----
        adapter = GNMAdapter()
        adapter.load_checkpoint(Path("third_party/visualnav-transformer/model_weights/gnm/gnm.pth"))
        preprocessed = adapter.preprocess_observation(obs_imgs, goal_img)
        action = adapter.predict_action(preprocessed)
        cmd = adapter.action_to_cmd_vel(action)
    """

    #: Override in each subclass.
    model_name: str = "base"

    def __init__(self) -> None:
        self._loaded: bool = False
        self._device: Any  = None

    @abstractmethod
    def load_checkpoint(self, checkpoint_path: Path) -> None:
        """
        Load model weights from checkpoint_path.

        Raises
        ------
        UpstreamNotFoundError  if the upstream repo is not cloned.
        CheckpointNotFoundError  if checkpoint_path does not exist.
        """

    @abstractmethod
    def preprocess_observation(
        self,
        obs_imgs: list[np.ndarray],
        goal_img: np.ndarray,
    ) -> dict:
        """
        Prepare inputs for model inference.

        Parameters
        ----------
        obs_imgs  : list of (H, W, 3) uint8 RGB images, len == context_size.
                    Oldest frame first.
        goal_img  : (H, W, 3) uint8 RGB goal image.

        Returns
        -------
        dict with keys "obs_tensor" and "goal_tensor" (torch.Tensor).
        """

    @abstractmethod
    def predict_action(self, preprocessed: dict) -> ActionOutput:
        """
        Run a forward pass and return a structured ActionOutput.

        Must not be called before load_checkpoint().
        Raises RuntimeError if model is not loaded.
        """

    def action_to_cmd_vel(
        self,
        action: ActionOutput,
        *,
        v_max: float  = 0.3,
        vy_max: float = 0.0,
        w_max: float  = 0.7,
        control_hz: float = 4.0,
    ) -> CmdVel:
        """
        Convert ActionOutput to CmdVel using the proportional waypoint controller.

        Override in subclasses for model-specific tuning (e.g. NoMaD may use
        a diffusion-specific action post-processor).

        Parameters
        ----------
        vy_max : Non-zero only for holonomic robots (M3Pro).  Set to 0 for X3.
        """
        return waypoints_to_cmd_vel(
            action.waypoints,
            v_max=v_max,
            vy_max=vy_max,
            w_max=w_max,
            control_hz=control_hz,
        )

    def log_policy_output(self, action: ActionOutput, cmd_vel: CmdVel) -> dict:
        """Default structured log entry for one inference step."""
        return {
            "model":          action.model_name,
            "waypoints":      action.waypoints.tolist(),
            "goal_distance":  action.goal_distance,
            "goal_reached":   action.goal_reached,
            "cmd_vx":         cmd_vel.vx,
            "cmd_vy":         cmd_vel.vy,
            "cmd_wz":         cmd_vel.wz,
            "inference_ms":   action.inference_ms,
        }

    def is_loaded(self) -> bool:
        """True after load_checkpoint() completes successfully."""
        return self._loaded

    # ── shared helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _check_upstream(vnt_root: Path) -> None:
        """Raise UpstreamNotFoundError if the upstream repo is not present."""
        if not vnt_root.exists():
            raise UpstreamNotFoundError(
                f"Upstream repo not found: {vnt_root}\n"
                "Clone it first:\n"
                "  bash scripts/visualnav/setup_visualnav.sh"
            )

    @staticmethod
    def _check_checkpoint(path: Path) -> None:
        """Raise CheckpointNotFoundError if path does not exist."""
        if not path.exists():
            raise CheckpointNotFoundError(
                f"Checkpoint not found: {path}\n"
                "Download checkpoints:\n"
                "  bash scripts/visualnav/setup_visualnav.sh --download-weights"
            )

    @staticmethod
    def _timeit(fn, *args, **kwargs):
        t0 = time.perf_counter()
        result = fn(*args, **kwargs)
        ms = (time.perf_counter() - t0) * 1000.0
        return result, ms
