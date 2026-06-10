"""GNM loss functions.

GNM Loss (from the paper)
--------------------------
The model makes two predictions at every training step:

  1. dist_pred  — how far (in normalised time steps) the goal is
  2. action_pred — the local waypoint (Δx, Δy) in the robot frame

The loss is:

  L_action = (1/B) Σ ||action_pred_i − action_gt_i||²      (MSE)
  L_dist   = (1/B) Σ (dist_pred_i − dist_gt_i)²            (MSE)
  L_total  = α · L_action + (1 − α) · L_dist

Where:
  α is the action weight (default 0.5, equal weighting)
  B is the batch size
  dist_gt = (t_goal − t_obs) / max_goal_dist  ∈ [0, 1]

Why MSE and not L1 / Huber?
  MSE penalises large errors more than L1.  For smooth navigation, being far
  off on a single step is much worse than being slightly off on all steps.
  Huber (a mix of MSE + L1) is an alternative — we provide it as an option.

Why predict distance?
  Without a distance signal, the model cannot know when it has reached the
  goal (the goal image will never perfectly match the current view).  The
  distance head provides a stopping condition: stop when dist_pred < threshold.

Action normalisation note:
  action_gt is already normalised by action_std BEFORE being passed to the
  loss.  Normalisation happens inside the dataset, not here.
  This means L_action is scale-free — it does not matter if the robot moves
  1 cm or 1 m per step; the loss magnitude stays similar.
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


class GNMLoss(nn.Module):
    """Combined GNM training loss.

    Parameters
    ----------
    action_weight : float
        Weight α on the action MSE term.  Default 0.5 (equal weight).
    loss_type : str
        "mse" | "huber".  Huber is more robust to outlier waypoints.
    huber_delta : float
        Transition point between L1 and L2 for Huber loss.
    """

    def __init__(
        self,
        action_weight: float = 0.5,
        loss_type: str = "mse",
        huber_delta: float = 1.0,
    ) -> None:
        super().__init__()
        assert 0.0 <= action_weight <= 1.0, "action_weight must be in [0, 1]"
        self.action_weight = action_weight
        self.dist_weight   = 1.0 - action_weight
        self.loss_type     = loss_type
        self.huber_delta   = huber_delta

    def forward(
        self,
        dist_pred:   torch.Tensor,   # (B, 1)
        action_pred: torch.Tensor,   # (B, action_dim)
        dist_gt:     torch.Tensor,   # (B, 1)
        action_gt:   torch.Tensor,   # (B, action_dim)
    ) -> tuple[torch.Tensor, dict[str, float]]:
        """Compute total loss and a dict of component losses for logging.

        Returns
        -------
        loss    : scalar tensor (for .backward())
        metrics : dict with "loss_action", "loss_dist", "loss_total"
        """
        l_action = self._elem_loss(action_pred, action_gt)
        l_dist   = self._elem_loss(dist_pred, dist_gt)

        l_total = self.action_weight * l_action + self.dist_weight * l_dist

        metrics = {
            "loss_action": l_action.item(),
            "loss_dist":   l_dist.item(),
            "loss_total":  l_total.item(),
        }
        return l_total, metrics

    def _elem_loss(self, pred: torch.Tensor, gt: torch.Tensor) -> torch.Tensor:
        if self.loss_type == "mse":
            return F.mse_loss(pred, gt)
        elif self.loss_type == "huber":
            return F.huber_loss(pred, gt, delta=self.huber_delta)
        else:
            raise ValueError(f"Unknown loss type: {self.loss_type}")


def gnm_loss(
    dist_pred: torch.Tensor,
    action_pred: torch.Tensor,
    dist_gt: torch.Tensor,
    action_gt: torch.Tensor,
    action_weight: float = 0.5,
) -> tuple[torch.Tensor, dict[str, float]]:
    """Functional form of GNM loss (no module state needed)."""
    criterion = GNMLoss(action_weight=action_weight)
    return criterion(dist_pred, action_pred, dist_gt, action_gt)
