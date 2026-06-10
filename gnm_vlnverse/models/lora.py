"""LoRA (Low-Rank Adaptation) for GNM.

What is LoRA in plain English?
------------------------------
Imagine you have a giant weight matrix W (say 1024×1024 = 1 million numbers).
Fine-tuning normally updates all 1 million numbers, which is slow and uses a
lot of memory.

LoRA says: "Instead of updating W directly, learn two SMALL matrices A and B
so that the update ΔW = B @ A, where A is (rank × 1024) and B is (1024 × rank).
If rank=8, that is 8×1024 + 1024×8 = 16,384 numbers — just 1.6% of the original."

At inference time:  W_effective = W_frozen + (B @ A) × scale
                    where scale = alpha / rank

Why does it work?
  The key insight is that fine-tuning updates live in a low-rank subspace.
  You do not need to update all directions of W — just the most important ones.

Reviewer questions answered
---------------------------
Q: Why LoRA for GNM on VLNVerse?
A: The original GNM was trained on 6 robots with outdoor/indoor navigation.
   VLNVerse has a specific embodiment (Yahboom M3 Pro), specific camera FOV,
   and language-guided tasks.  Full fine-tuning risks destroying the cross-robot
   generalization.  LoRA adapts the model to VLNVerse while preserving most of
   the pretrained knowledge.

Q: Which layers to adapt?
A: The projection layers in the encoders (nn.Linear inside MobileNetV2's
   inverted residual blocks) and the GNM head linear layers.  We do NOT adapt
   the depthwise convolutions — those capture low-level visual features that
   transfer well.

Q: How does rank affect performance?
A: rank=4  → minimal adaptation (~0.1% params), good for small datasets
   rank=8  → balanced (default), recommended starting point
   rank=16 → more capacity, needed if the domain gap is large

Implementation
--------------
LoRALinear wraps an existing nn.Linear layer.
inject_lora walks the model and replaces target nn.Linear layers with LoRALinear.
"""

from __future__ import annotations

import math
import re
from typing import Iterator

import torch
import torch.nn as nn


class LoRALinear(nn.Module):
    """A nn.Linear layer wrapped with a LoRA bypass.

    Forward:
        output = x @ W.T + b + (x @ A.T @ B.T) * scale

    Parameters
    ----------
    linear : nn.Linear
        The original frozen linear layer to wrap.
    rank : int
        LoRA rank r.  Typical values: 4, 8, 16.
    alpha : float
        LoRA scaling factor.  scale = alpha / rank.
        Setting alpha = rank gives scale = 1.0.
    dropout : float
        Dropout on the LoRA path (regularization).
    """

    def __init__(
        self,
        linear: nn.Linear,
        rank: int = 8,
        alpha: float = 16.0,
        dropout: float = 0.05,
    ) -> None:
        super().__init__()
        in_features  = linear.in_features
        out_features = linear.out_features

        # Frozen original weights
        self.weight = linear.weight  # (out, in)  — NOT a parameter, just a reference
        self.bias   = linear.bias

        # Freeze the original weight
        self.weight.requires_grad_(False)
        if self.bias is not None:
            self.bias.requires_grad_(False)

        # LoRA matrices
        self.lora_A = nn.Parameter(torch.empty(rank, in_features))
        self.lora_B = nn.Parameter(torch.zeros(out_features, rank))

        # Kaiming uniform init for A (same as nn.Linear default)
        nn.init.kaiming_uniform_(self.lora_A, a=math.sqrt(5))

        self.scale   = alpha / rank
        self.dropout = nn.Dropout(p=dropout) if dropout > 0 else nn.Identity()
        self.rank    = rank

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        base = nn.functional.linear(x, self.weight, self.bias)
        lora = self.dropout(x) @ self.lora_A.T @ self.lora_B.T
        return base + lora * self.scale

    def extra_repr(self) -> str:
        return f"rank={self.rank}, scale={self.scale:.3f}"


def inject_lora(
    model: nn.Module,
    target_modules: list[str],
    rank: int = 8,
    alpha: float = 16.0,
    dropout: float = 0.05,
) -> nn.Module:
    """Walk *model* and replace matching nn.Linear layers with LoRALinear.

    Parameters
    ----------
    model : nn.Module
        The model to modify in-place.
    target_modules : list[str]
        Regex patterns.  Any nn.Linear whose fully-qualified name matches
        ANY pattern will be replaced.  Examples:
            ["project", "linear_layers", "dist_predictor", "action_predictor"]
    rank, alpha, dropout:
        Passed to LoRALinear.

    Returns
    -------
    model : nn.Module (modified in-place, also returned for chaining)
    """
    patterns = [re.compile(p) for p in target_modules]

    def _replace_in(parent: nn.Module, prefix: str) -> None:
        for name, child in list(parent.named_children()):
            full_name = f"{prefix}.{name}" if prefix else name
            if isinstance(child, nn.Linear) and any(p.search(full_name) for p in patterns):
                setattr(parent, name, LoRALinear(child, rank=rank, alpha=alpha, dropout=dropout))
            else:
                _replace_in(child, full_name)

    _replace_in(model, "")
    return model


def count_lora_params(model: nn.Module) -> dict[str, int]:
    """Return total, trainable, and LoRA-specific parameter counts."""
    total     = sum(p.numel() for p in model.parameters())
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    lora_only = sum(
        p.numel()
        for m in model.modules()
        if isinstance(m, LoRALinear)
        for p in [m.lora_A, m.lora_B]
    )
    return {
        "total":     total,
        "trainable": trainable,
        "lora_only": lora_only,
        "pct":       100 * trainable / max(total, 1),
    }


def lora_state_dict(model: nn.Module) -> dict[str, torch.Tensor]:
    """Return only the LoRA weights (for lightweight checkpoint saving)."""
    return {
        k: v
        for k, v in model.state_dict().items()
        if "lora_A" in k or "lora_B" in k
    }


def load_lora_weights(model: nn.Module, state: dict[str, torch.Tensor]) -> None:
    """Load LoRA weights into a model that already has LoRA layers injected."""
    missing = model.load_state_dict(state, strict=False)
    unexpected = [k for k in missing.unexpected_keys if "lora" in k.lower()]
    if unexpected:
        raise ValueError(f"Unexpected LoRA keys: {unexpected}")


def lora_parameters(model: nn.Module) -> Iterator[nn.Parameter]:
    """Yield only the LoRA parameters (convenience for optimizers)."""
    for m in model.modules():
        if isinstance(m, LoRALinear):
            yield m.lora_A
            yield m.lora_B


def freeze_non_lora(model: nn.Module) -> None:
    """Freeze everything that is NOT a LoRA parameter or prediction head."""
    for name, param in model.named_parameters():
        is_lora = "lora_A" in name or "lora_B" in name
        is_head = "dist_predictor" in name or "action_predictor" in name
        param.requires_grad_(is_lora or is_head)
