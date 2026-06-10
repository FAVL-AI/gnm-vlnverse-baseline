"""
nomad_adapter.py — FleetSafe adapter for NoMaD (No-Maps Diffusion).

Upstream: train/nomad/ in visualnav-transformer.
No upstream files are modified.

NoMaD interface
---------------
NoMaD uses a diffusion policy head.  Inference requires multiple denoising steps:

  noise = torch.randn(1, action_horizon, 2)
  for t in reversed(range(num_diffusion_steps)):
      noise_pred = model(obs_tensor, goal_tensor, noise, t)
      noise = scheduler.step(noise_pred, t, noise).prev_sample
  waypoints = noise   # (1, action_horizon, 2)

The upstream deployment uses the diffusers library scheduler.

Default image size      : 96 × 96 (W × H).
Default action_horizon  : 8 waypoints.
Default diffusion_steps : 10 (fast inference; training uses more).
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


class NoMaDAdapter(BaseVisualNavAdapter):
    """
    Adapter that wraps the upstream NoMaD diffusion policy model.

    Parameters
    ----------
    context_size      : number of past frames (default 5).
    action_horizon    : waypoints to generate (default 8).
    num_diffusion_steps : denoising iterations (default 10).
    image_size        : (W, H) in pixels (default (96, 96)).
    device            : "cpu" or "cuda" (auto-selected if None).

    Notes
    -----
    NoMaD inference is slower than GNM/ViNT due to the diffusion loop.
    With num_diffusion_steps=10, expect ~50–200 ms on CPU.
    Use num_diffusion_steps=5 for real-time benchmarks on CPU hardware.
    """

    model_name = "nomad"

    def __init__(
        self,
        context_size:        int         = 3,   # nomad.yaml: context_size: 3
        action_horizon:      int         = 8,
        num_diffusion_steps: int         = 10,
        image_size:          tuple       = (96, 96),
        device:              str | None  = None,
    ) -> None:
        super().__init__()
        self.context_size        = context_size
        self.action_horizon      = action_horizon
        self.num_diffusion_steps = num_diffusion_steps
        self.image_size          = image_size
        self._device_str         = device
        self._model: Any           = None
        self._noise_scheduler: Any = None

    def load_checkpoint(self, checkpoint_path: Path) -> None:
        self._check_upstream(_VNT_ROOT)
        self._check_checkpoint(checkpoint_path)
        _add_upstream_to_path()

        try:
            import torch
        except ImportError as exc:
            raise RuntimeError("torch not installed.") from exc

        try:
            from diffusers.schedulers.scheduling_ddpm import DDPMScheduler
        except ImportError as exc:
            raise RuntimeError(
                "diffusers package not found — required by NoMaD.\n"
                "Install: pip install 'diffusers==0.11.1'\n"
                f"Error: {exc}"
            ) from exc

        try:
            from vint_train.models.nomad.nomad import NoMaD, DenseNetwork
            from vint_train.models.nomad.nomad_vint import NoMaD_ViNT, replace_bn_with_gn
        except ImportError as exc:
            raise RuntimeError(
                "Failed to import NoMaD from upstream.\n"
                f"  upstream root : {_VNT_ROOT}\n"
                f"  ImportError   : {exc}\n"
                "Re-run: bash scripts/visualnav/setup_visualnav.sh"
            ) from exc

        # NoMaD requires ConditionalUnet1D from the diffusion_policy repo:
        #   git clone https://github.com/real-stanford/diffusion_policy.git
        #   pip install -e diffusion_policy/
        try:
            from diffusion_policy.model.diffusion.conditional_unet1d import ConditionalUnet1D
        except ImportError as exc:
            raise RuntimeError(
                "diffusion_policy package not found — required by NoMaD.\n"
                "Install:\n"
                "  git clone https://github.com/real-stanford/diffusion_policy.git\n"
                "  pip install -e diffusion_policy/\n"
                f"Error: {exc}"
            ) from exc

        self._torch = torch
        device = torch.device(
            self._device_str if self._device_str else
            ("cuda" if torch.cuda.is_available() else "cpu")
        )
        self._device = device

        # Construct sub-modules matching nomad.yaml config values.
        encoding_size = 256
        vision_encoder = NoMaD_ViNT(
            obs_encoding_size        = encoding_size,
            context_size             = self.context_size,
            mha_num_attention_heads  = 4,
            mha_num_attention_layers = 4,
            mha_ff_dim_factor        = 4,
        )
        vision_encoder = replace_bn_with_gn(vision_encoder)

        noise_pred_net = ConditionalUnet1D(
            input_dim          = 2,
            global_cond_dim    = encoding_size,
            down_dims          = [64, 128, 256],
            cond_predict_scale = False,
        )
        dist_pred_net = DenseNetwork(embedding_dim=encoding_size)

        model = NoMaD(
            vision_encoder = vision_encoder,
            noise_pred_net = noise_pred_net,
            dist_pred_net  = dist_pred_net,
        )
        # NoMaD checkpoint is a raw state_dict (no "model" wrapper).
        # weights_only=False needed for checkpoints that store non-tensor objects.
        state_dict = torch.load(checkpoint_path, map_location=device, weights_only=False)
        if isinstance(state_dict, dict) and "model" in state_dict:
            state_dict = state_dict["model"]
        model.load_state_dict(state_dict, strict=False)
        model.to(device)
        model.eval()
        self._model = model

        self._noise_scheduler = DDPMScheduler(
            num_train_timesteps = 10,
            beta_schedule       = "squaredcos_cap_v2",
            clip_sample         = True,
            prediction_type     = "epsilon",
        )
        self._noise_scheduler.set_timesteps(self.num_diffusion_steps)
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

        # NoMaD_ViNT expects (context_size + 1) stacked frames — same as GNM/ViNT.
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
        """
        Run NoMaD diffusion inference.

        Denoising loop (num_diffusion_steps iterations) samples a trajectory
        from the learned action distribution conditioned on (obs, goal).
        """
        if not self._loaded:
            raise RuntimeError("Call load_checkpoint() before predict_action().")

        import torch
        obs_t  = preprocessed["obs_tensor"]
        goal_t = preprocessed["goal_tensor"]

        def _diffusion_inference():
            B = 1
            # Encode visual context once; then run diffusion loop.
            mask = torch.zeros(B, dtype=torch.long, device=self._device)
            with torch.no_grad():
                obs_cond = self._model(
                    "vision_encoder",
                    obs_img         = obs_t,
                    goal_img        = goal_t,
                    input_goal_mask = mask,
                )
                naction = torch.randn(B, self.action_horizon, 2, device=self._device)
                for k in self._noise_scheduler.timesteps:
                    noise_pred = self._model(
                        "noise_pred_net",
                        sample     = naction,
                        timestep   = k,
                        global_cond= obs_cond,
                    )
                    naction = self._noise_scheduler.step(
                        model_output = noise_pred,
                        timestep     = k,
                        sample       = naction,
                    ).prev_sample
            return naction

        waypoints_t, ms = self._timeit(_diffusion_inference)
        waypoints = waypoints_t[0].cpu().numpy()   # (action_horizon, 2)

        # NoMaD does not predict goal distance — use waypoint magnitude as proxy
        goal_dist = float(np.linalg.norm(waypoints[-1]))

        return ActionOutput(
            waypoints     = waypoints,
            goal_distance = goal_dist,
            goal_reached  = goal_dist < 0.2,
            raw_output    = {
                "waypoints_raw": waypoints.tolist(),
                "diffusion_steps": self.num_diffusion_steps,
            },
            model_name    = self.model_name,
            inference_ms  = ms,
        )
