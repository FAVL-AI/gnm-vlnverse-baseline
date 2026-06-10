"""Visual encoders for GNM.

GNM (General Navigation Model) encodes:
  - The current observation stack  (context_size × H × W × 3)
  - A goal image                   (1 × H × W × 3)

Both encoders share the same backbone class but are instantiated separately
and kept independent — the observation encoder sees temporal context while
the goal encoder sees a single target frame.

Architecture
------------
MobileNetV2 is the default (matches the original GNM paper).
EfficientNet-B0 is a modern drop-in with better accuracy/compute trade-off.

Why MobileNetV2?
  - Depthwise-separable convolutions → fast on embedded hardware
  - ~3.4 M parameters — small enough to run on the Yahboom M3 Pro CPU
  - Proven in the original GNM paper across 6 robot platforms

Output
------
Both encoders produce a flat 512-D feature vector (configurable).
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torchvision.models as tvm
from torchvision.models import MobileNet_V2_Weights, EfficientNet_B0_Weights


class MobileNetEncoder(nn.Module):
    """MobileNetV2-based image encoder.

    Parameters
    ----------
    in_channels:
        Number of input channels.
        For a single frame: 3.
        For temporal context of N frames: N * 3.
    out_dim:
        Size of the output feature vector. Default: 512.
    pretrained:
        Whether to load ImageNet weights. True for transfer learning.
    """

    def __init__(
        self,
        in_channels: int = 3,
        out_dim: int = 512,
        pretrained: bool = True,
    ) -> None:
        super().__init__()
        weights = MobileNet_V2_Weights.IMAGENET1K_V1 if pretrained else None
        backbone = tvm.mobilenet_v2(weights=weights)

        # Adapt first conv for multi-channel input (temporal stack)
        if in_channels != 3:
            old_conv = backbone.features[0][0]
            backbone.features[0][0] = nn.Conv2d(
                in_channels,
                old_conv.out_channels,
                kernel_size=old_conv.kernel_size,
                stride=old_conv.stride,
                padding=old_conv.padding,
                bias=old_conv.bias is not None,
            )
            if pretrained:
                # Repeat the 3-channel weights across the extra channels
                with torch.no_grad():
                    w = old_conv.weight.data
                    reps = in_channels // 3
                    rem  = in_channels  % 3
                    new_w = torch.cat([w] * reps + ([w[:, :rem, :, :]] if rem else []), dim=1)
                    backbone.features[0][0].weight.data = new_w / (in_channels / 3)

        self.features = backbone.features       # convolutional body
        self.pool     = nn.AdaptiveAvgPool2d(1)  # global average pool → (B, 1280, 1, 1)
        self.project  = nn.Sequential(
            nn.Flatten(),
            nn.Linear(1280, out_dim),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (B, C, H, W) → (B, out_dim)"""
        x = self.features(x)
        x = self.pool(x)
        return self.project(x)


class EfficientNetEncoder(nn.Module):
    """EfficientNet-B0 image encoder — drop-in replacement for MobileNetEncoder.

    Higher accuracy than MobileNetV2 at similar compute cost.
    Recommended for training from scratch; MobileNet for fast inference.
    """

    def __init__(
        self,
        in_channels: int = 3,
        out_dim: int = 512,
        pretrained: bool = True,
    ) -> None:
        super().__init__()
        weights = EfficientNet_B0_Weights.IMAGENET1K_V1 if pretrained else None
        backbone = tvm.efficientnet_b0(weights=weights)

        # Adapt first conv for multi-channel input
        if in_channels != 3:
            old_conv = backbone.features[0][0]
            backbone.features[0][0] = nn.Conv2d(
                in_channels,
                old_conv.out_channels,
                kernel_size=old_conv.kernel_size,
                stride=old_conv.stride,
                padding=old_conv.padding,
                bias=old_conv.bias is not None,
            )

        self.features = backbone.features
        self.pool     = nn.AdaptiveAvgPool2d(1)
        self.project  = nn.Sequential(
            nn.Flatten(),
            nn.Linear(1280, out_dim),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.features(x)
        x = self.pool(x)
        return self.project(x)


ENCODER_REGISTRY: dict[str, type] = {
    "mobilenet": MobileNetEncoder,
    "efficientnet": EfficientNetEncoder,
}


def build_encoder(name: str, **kwargs) -> nn.Module:
    """Factory function — build an encoder by name."""
    cls = ENCODER_REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown encoder '{name}'. Choose from {list(ENCODER_REGISTRY)}")
    return cls(**kwargs)
