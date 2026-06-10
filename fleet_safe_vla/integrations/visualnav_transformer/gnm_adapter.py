"""
gnm_adapter.py — FleetSafe adapter for GNM (General Navigation Model).

Upstream: train/gnm_train/models/gnm.py in visualnav-transformer.
No upstream files are modified.  This file wraps the upstream model only.

GNM interface
-------------
  model = GNM(context_size, len_traj_pred, learn_angle, ...)
  obs_tensor  : (1, 3*context_size, H, W)   stacked context frames
  goal_tensor : (1, 3, H, W)
  waypoints, goal_dist = model(obs_tensor, goal_tensor)
    waypoints  : (1, len_traj_pred, 2)   (dx, dy) in robot frame [m]
    goal_dist  : (1,)                    estimated steps to goal

Default image size : 85 × 64 (W × H) — from upstream gnm_train config.
Default context    : 5 past frames.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np

from fleet_safe_vla.integrations.visualnav_transformer.base_adapter import (
    ActionOutput,
    BaseVisualNavAdapter,
    CheckpointNotFoundError,
    UpstreamNotFoundError,
    find_repo_root,
    waypoints_to_cmd_vel,
)

_REPO_ROOT  = find_repo_root()
_VNT_ROOT   = _REPO_ROOT / "third_party" / "visualnav-transformer"
_TRAIN_DIR  = _VNT_ROOT / "train"

# ImageNet normalisation (standard for all three models)
_IMAGENET_MEAN = [0.485, 0.456, 0.406]
_IMAGENET_STD  = [0.229, 0.224, 0.225]


def _add_upstream_to_path() -> None:
    for p in (str(_VNT_ROOT), str(_TRAIN_DIR)):
        if p not in sys.path:
            sys.path.insert(0, p)


class GNMAdapter(BaseVisualNavAdapter):
    """
    Adapter that wraps the upstream GNM model for use in the FleetSafe benchmark.

    Parameters
    ----------
    context_size    : number of past frames (default 5, must match checkpoint).
    action_horizon  : number of waypoints to predict (default 5).
    image_size      : (width, height) in pixels (default (85, 64)).
    device          : "cpu" or "cuda" (auto-selected if None).
    """

    model_name = "gnm"

    def __init__(
        self,
        context_size:   int          = 5,
        action_horizon: int          = 5,
        image_size:     tuple        = (85, 64),
        device:         str | None   = None,
    ) -> None:
        super().__init__()
        self.context_size   = context_size
        self.action_horizon = action_horizon
        self.image_size     = image_size   # (W, H)
        self._device_str    = device
        self._model: Any    = None
        self._torch: Any    = None

    # ── Gate 0 + 1 ───────────────────────────────────────────────────────────

    def load_checkpoint(self, checkpoint_path: Path) -> None:
        """
        Load GNM weights from checkpoint_path.

        Raises
        ------
        UpstreamNotFoundError   if third_party/visualnav-transformer not cloned.
        CheckpointNotFoundError if checkpoint_path does not exist.
        RuntimeError            if upstream GNM class cannot be imported.
        """
        self._check_upstream(_VNT_ROOT)
        self._check_checkpoint(checkpoint_path)

        _add_upstream_to_path()

        try:
            import torch
            from vint_train.models.gnm.gnm import GNM
        except ImportError as exc:
            raise RuntimeError(
                "Failed to import GNM from upstream.\n"
                f"  upstream root : {_VNT_ROOT}\n"
                f"  ImportError   : {exc}\n"
                "Re-run: bash scripts/visualnav/setup_visualnav.sh"
            ) from exc

        self._torch = torch
        device = torch.device(
            self._device_str if self._device_str else
            ("cuda" if torch.cuda.is_available() else "cpu")
        )
        self._device = device

        model = GNM(
            context_size      = self.context_size,
            len_traj_pred     = self.action_horizon,
            learn_angle       = True,
            obs_encoding_size = 1024,
            goal_encoding_size= 1024,
        )
        # weights_only=False required: upstream checkpoint stores a full nn.Module
        # object under "model", not a plain state_dict.  Only load from trusted sources.
        checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
        if isinstance(checkpoint, dict) and "model" in checkpoint:
            saved = checkpoint["model"]
            try:
                state_dict = saved.module.state_dict()   # DataParallel wrapper
            except AttributeError:
                state_dict = saved.state_dict()
        else:
            state_dict = checkpoint
        model.load_state_dict(state_dict, strict=False)
        model.to(device)
        model.eval()
        self._model = model
        self._loaded = True

    # ── Gate 2 ───────────────────────────────────────────────────────────────

    def preprocess_observation(
        self,
        obs_imgs: list[np.ndarray],
        goal_img: np.ndarray,
    ) -> dict:
        """
        Resize, normalise, and stack context frames + goal image.

        Returns
        -------
        dict with:
          "obs_tensor"  : torch.Tensor (1, 3*context_size, H, W) float32
          "goal_tensor" : torch.Tensor (1, 3, H, W) float32
        """
        import torch
        from torchvision import transforms

        W, H = self.image_size
        tf = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize(mean=_IMAGENET_MEAN, std=_IMAGENET_STD),
        ])

        def _process_frame(img: np.ndarray) -> "torch.Tensor":
            from PIL import Image
            pil = Image.fromarray(img).resize((W, H))
            return tf(pil)

        # GNM obs mobilenet expects (1 + context_size) stacked frames = 18 channels.
        # The upstream context_queue holds context_size+1 frames (current + past).
        n_frames = self.context_size + 1
        while len(obs_imgs) < n_frames:
            obs_imgs = [obs_imgs[0]] + obs_imgs

        frames = [_process_frame(f) for f in obs_imgs[-n_frames:]]
        obs_tensor  = torch.cat(frames, dim=0).unsqueeze(0)   # (1, 3*(C+1), H, W)
        goal_tensor = _process_frame(goal_img).unsqueeze(0)    # (1, 3, H, W)

        return {
            "obs_tensor":  obs_tensor.to(self._device),
            "goal_tensor": goal_tensor.to(self._device),
        }

    # ── Gate 4 ───────────────────────────────────────────────────────────────

    def predict_action(self, preprocessed: dict) -> ActionOutput:
        """Run one GNM forward pass and return structured ActionOutput."""
        if not self._loaded:
            raise RuntimeError("Call load_checkpoint() before predict_action().")

        import torch
        obs_t  = preprocessed["obs_tensor"]
        goal_t = preprocessed["goal_tensor"]

        def _forward():
            with torch.no_grad():
                return self._model(obs_t, goal_t)

        # GNM forward: returns (dist_pred, action_pred) — dist first, waypoints second
        (dist_t, action_t), ms = self._timeit(_forward)

        # action_t: (1, len_traj_pred, 3) if learn_angle else (1, len_traj_pred, 2)
        waypoints  = action_t[0, :, :2].cpu().numpy()  # (len_traj_pred, 2) x,y only
        goal_dist  = float(dist_t[0].cpu().item())
        goal_reached = goal_dist < 1.0

        return ActionOutput(
            waypoints     = waypoints,
            goal_distance = goal_dist,
            goal_reached  = goal_reached,
            raw_output    = {
                "waypoints_raw": action_t[0].cpu().numpy().tolist(),
                "goal_dist_raw": goal_dist,
            },
            model_name    = self.model_name,
            inference_ms  = ms,
        )
