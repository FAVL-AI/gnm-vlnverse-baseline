"""
vint_adapter.py — FleetSafe adapter for ViNT (Vision-based Navigation Transformer).

Upstream: train/vint_train/models/vint.py in visualnav-transformer.
No upstream files are modified.

ViNT interface
--------------
  model = ViNT(context_size, len_traj_pred, ...)
  waypoints, goal_dist = model(obs_tensor, goal_tensor)

ViNT is architecturally similar to GNM but uses a vision transformer backbone
and a larger image resolution (160 × 120 default).  It also outputs a richer
goal-distance estimate useful for topological graph construction.

Default image size : 160 × 120 (W × H).
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
)

_REPO_ROOT  = find_repo_root()
_VNT_ROOT   = _REPO_ROOT / "third_party" / "visualnav-transformer"
_TRAIN_DIR  = _VNT_ROOT / "train"

_IMAGENET_MEAN = [0.485, 0.456, 0.406]
_IMAGENET_STD  = [0.229, 0.224, 0.225]


def _add_upstream_to_path() -> None:
    for p in (str(_VNT_ROOT), str(_TRAIN_DIR)):
        if p not in sys.path:
            sys.path.insert(0, p)


class ViNTAdapter(BaseVisualNavAdapter):
    """
    Adapter that wraps the upstream ViNT model.

    Parameters
    ----------
    context_size    : number of past frames (default 5).
    action_horizon  : number of predicted waypoints (default 5).
    image_size      : (width, height) in pixels (default (160, 120)).
    device          : "cpu" or "cuda" (auto-selected if None).
    """

    model_name = "vint"

    def __init__(
        self,
        context_size:   int         = 5,
        action_horizon: int         = 5,
        image_size:     tuple       = (85, 64),
        device:         str | None  = None,
    ) -> None:
        super().__init__()
        self.context_size   = context_size
        self.action_horizon = action_horizon
        self.image_size     = image_size
        self._device_str    = device
        self._model: Any    = None

    def load_checkpoint(self, checkpoint_path: Path) -> None:
        self._check_upstream(_VNT_ROOT)
        self._check_checkpoint(checkpoint_path)
        _add_upstream_to_path()

        try:
            import torch
            from vint_train.models.vint.vint import ViNT
        except ImportError as exc:
            raise RuntimeError(
                "Failed to import ViNT from upstream.\n"
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

        # Constructor params must match the published checkpoint (vint.yaml config).
        model = ViNT(
            context_size            = self.context_size,
            len_traj_pred           = self.action_horizon,
            learn_angle             = True,
            obs_encoder             = "efficientnet-b0",
            obs_encoding_size       = 512,
            late_fusion             = False,
            mha_num_attention_heads = 4,
            mha_num_attention_layers= 4,
            mha_ff_dim_factor       = 4,
        )
        # weights_only=False required: upstream checkpoint stores a full nn.Module
        # object under "model", not a plain state_dict.  Only load from trusted sources.
        checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
        if isinstance(checkpoint, dict) and "model" in checkpoint:
            saved = checkpoint["model"]
            try:
                state_dict = saved.module.state_dict()
            except AttributeError:
                state_dict = saved.state_dict()
        else:
            state_dict = checkpoint
        model.load_state_dict(state_dict, strict=False)
        model.to(device)
        model.eval()
        self._model = model
        self._loaded = True

    def preprocess_observation(
        self,
        obs_imgs: list[np.ndarray],
        goal_img: np.ndarray,
    ) -> dict:
        import torch
        from torchvision import transforms
        from PIL import Image

        W, H = self.image_size
        tf = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize(mean=_IMAGENET_MEAN, std=_IMAGENET_STD),
        ])

        def _process(img: np.ndarray) -> "torch.Tensor":
            return tf(Image.fromarray(img).resize((W, H)))

        # ViNT expects (context_size + 1) stacked frames — same convention as GNM.
        n_frames = self.context_size + 1
        while len(obs_imgs) < n_frames:
            obs_imgs = [obs_imgs[0]] + obs_imgs

        frames      = [_process(f) for f in obs_imgs[-n_frames:]]
        obs_tensor  = torch.cat(frames, dim=0).unsqueeze(0)  # (1, 3*(C+1), H, W)
        goal_tensor = _process(goal_img).unsqueeze(0)

        return {
            "obs_tensor":  obs_tensor.to(self._device),
            "goal_tensor": goal_tensor.to(self._device),
        }

    def predict_action(self, preprocessed: dict) -> ActionOutput:
        if not self._loaded:
            raise RuntimeError("Call load_checkpoint() before predict_action().")

        import torch
        obs_t  = preprocessed["obs_tensor"]
        goal_t = preprocessed["goal_tensor"]

        def _forward():
            with torch.no_grad():
                return self._model(obs_t, goal_t)

        # ViNT forward: returns (dist_pred, action_pred) — same order as GNM
        (dist_t, action_t), ms = self._timeit(_forward)

        waypoints    = action_t[0, :, :2].cpu().numpy()  # (len_traj_pred, 2) x,y only
        goal_dist    = float(dist_t[0].cpu().item())
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
