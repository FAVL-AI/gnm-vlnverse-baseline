"""Exponential Moving Average (EMA) of model weights.

Why EMA?
--------
At each training step the model weights jump noisily due to batch variance.
EMA maintains a shadow copy that is a weighted average of all past weights:

  shadow[t] = decay × shadow[t-1] + (1 - decay) × param[t]

With decay=0.9999, the shadow lags the live weights by ~10,000 steps.
This smooths over the noise and consistently produces better val/test metrics
(1-3% SR improvement in practice) at zero compute cost beyond a memcpy.

The shadow weights are used for validation and saved in best.pt.
Live weights are used for the gradient update.
"""

from __future__ import annotations

import copy
from typing import Iterator

import torch
import torch.nn as nn


class EMA:
    """Maintains EMA shadow weights for a model.

    Parameters
    ----------
    model : nn.Module
        The live model being trained.
    decay : float
        EMA decay factor.  0.9999 is standard for training runs >10k steps.
        Lower decay (0.999, 0.99) reacts faster — useful for short runs.
    """

    def __init__(self, model: nn.Module, decay: float = 0.9999) -> None:
        self.decay  = decay
        self.shadow = copy.deepcopy(model)
        self.shadow.eval()
        # Shadow is never trained — disable gradients
        for p in self.shadow.parameters():
            p.requires_grad_(False)

    @torch.no_grad()
    def update(self, model: nn.Module) -> None:
        """Update shadow weights from the live model."""
        for (name, s_param), (_, m_param) in zip(
            self.shadow.named_parameters(), model.named_parameters()
        ):
            s_param.data.mul_(self.decay).add_(m_param.data, alpha=1.0 - self.decay)

    def state_dict(self) -> dict:
        return self.shadow.state_dict()

    def load_state_dict(self, state: dict) -> None:
        self.shadow.load_state_dict(state)

    def __call__(self, *args, **kwargs):
        return self.shadow(*args, **kwargs)
