"""GNM — General Navigation Model.

Paper: Shah et al., "GNM: A General Navigation Model to Drive Any Robot"
       CoRL 2022.  https://arxiv.org/abs/2210.03370

What does GNM do?
-----------------
GNM is a goal-conditioned visual navigation policy.

  Input:
    obs   — last (context_size) RGB frames stacked as one tensor
    goal  — a single RGB image of the destination

  Output:
    action_pred   — predicted local waypoint (Δx, Δy) in the robot frame
    dist_pred     — predicted temporal distance to the goal (integer steps)

Why is this useful?
  Traditional navigation models are trained on one robot.  GNM trains on
  data from 6 robots with different cameras and sizes, learning a
  *robot-agnostic* navigation policy.  The key insight is normalising
  actions by the robot's action statistics so all robots speak the same
  "language" of Δx/Δy steps.

Architecture in plain English
------------------------------
  1. Stack the last N observation frames into a (N×3, H, W) tensor.
  2. Pass it through the observation encoder → 512-D vector.
  3. Pass the goal image through the goal encoder → 512-D vector.
  4. Concatenate → 1024-D vector.
  5. Two small MLP heads read from this:
       • dist_predictor  → 1 scalar (normalized distance)
       • action_predictor → 2 scalars (Δx, Δy waypoint)

Loss functions
--------------
  L_action = MSE(action_pred, action_gt)
  L_dist   = MSE(dist_pred, dist_gt)     # dist_gt is normalized: steps / MAX_DIST
  L_total  = α · L_action + (1 − α) · L_dist

  α is set to 0.5 by default (equal weight) but can be swept.

Normalized actions
------------------
  Each robot has its own action_std (standard deviation of Δx, Δy).
  At training time, actions are divided by action_std before being fed to
  the loss.  At inference time, predictions are multiplied back by
  action_std to get real-world commands.  This lets all robots share the
  same backbone without one robot "dominating" the action space.

Parameters
----------
context_size : int
    Number of past frames to stack (1 = no temporal context).
    Paper uses 5 — captures ~1 second at 5 Hz.
    More = better memory of what happened; more = heavier to compute.
goal_conditioned : bool
    If True, fuse goal encoding.  False gives a context-only policy.
action_dim : int
    Dimensionality of predicted action. Default 2 (Δx, Δy).
    Set to 3 (Δx, Δy, Δyaw) for platforms with explicit yaw control.
hidden_dim : int
    Width of the MLP heads (default 256).
encoder : str
    Which encoder backbone to use: "mobilenet" | "efficientnet".
out_dim : int
    Encoder output size (both obs and goal encoder). Default 512.
"""

from __future__ import annotations

import torch
import torch.nn as nn

from .encoders import build_encoder


class GNM(nn.Module):
    """General Navigation Model.

    Examples
    --------
    >>> model = GNM(context_size=5)
    >>> obs  = torch.randn(4, 5 * 3, 96, 96)   # batch=4, 5 frames × 3 ch
    >>> goal = torch.randn(4, 3, 96, 96)
    >>> dist, action = model(obs, goal)
    >>> dist.shape, action.shape
    (torch.Size([4, 1]), torch.Size([4, 2]))
    """

    def __init__(
        self,
        context_size: int = 5,
        goal_conditioned: bool = True,
        action_dim: int = 2,
        hidden_dim: int = 256,
        encoder: str = "mobilenet",
        out_dim: int = 512,
        pretrained: bool = True,
    ) -> None:
        super().__init__()

        self.context_size      = context_size
        self.goal_conditioned  = goal_conditioned
        self.action_dim        = action_dim
        obs_channels           = context_size * 3   # N frames × RGB

        # ── Encoders ─────────────────────────────────────────────────────────
        self.obs_encoder = build_encoder(
            encoder, in_channels=obs_channels, out_dim=out_dim, pretrained=pretrained
        )

        if goal_conditioned:
            self.goal_encoder = build_encoder(
                encoder, in_channels=3, out_dim=out_dim, pretrained=pretrained
            )
            fused_dim = out_dim * 2
        else:
            self.goal_encoder = None
            fused_dim = out_dim

        # ── Distance predictor ────────────────────────────────────────────────
        # Predicts *how many steps* away the goal is (normalized to [0, 1]).
        # Reviewer question: why predict distance?
        #   Distance gives the model a "confidence" signal: if it predicts
        #   large distance, the robot knows it is far from the goal.
        #   This enables stopping conditions and topological replanning.
        self.dist_predictor = nn.Sequential(
            nn.Linear(fused_dim, hidden_dim),
            nn.ReLU(inplace=True),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(inplace=True),
            nn.Linear(hidden_dim, 1),
        )

        # ── Action predictor ─────────────────────────────────────────────────
        # Predicts (Δx, Δy) in the robot's local frame.
        # Normalized by the robot's action_std at training time.
        self.action_predictor = nn.Sequential(
            nn.Linear(fused_dim, hidden_dim),
            nn.ReLU(inplace=True),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(inplace=True),
            nn.Linear(hidden_dim, action_dim),
        )

    def encode(
        self,
        obs: torch.Tensor,
        goal: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """Encode obs (and optionally goal) into a single feature vector.

        Parameters
        ----------
        obs : (B, context_size*3, H, W)
        goal: (B, 3, H, W) or None

        Returns
        -------
        fused : (B, fused_dim)
        """
        obs_feat = self.obs_encoder(obs)                        # (B, out_dim)
        if self.goal_conditioned and self.goal_encoder is not None:
            if goal is None:
                raise ValueError("goal must be provided when goal_conditioned=True")
            goal_feat = self.goal_encoder(goal)                 # (B, out_dim)
            fused = torch.cat([obs_feat, goal_feat], dim=-1)    # (B, 2*out_dim)
        else:
            fused = obs_feat
        return fused

    def forward(
        self,
        obs: torch.Tensor,
        goal: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Forward pass.

        Parameters
        ----------
        obs : (B, context_size*3, H, W)  stacked observation frames
        goal: (B, 3, H, W)               goal image

        Returns
        -------
        dist_pred   : (B, 1)   normalized temporal distance to goal
        action_pred : (B, action_dim)  local waypoint (Δx, Δy [, Δyaw])
        """
        fused = self.encode(obs, goal)
        dist_pred   = self.dist_predictor(fused)    # (B, 1)
        action_pred = self.action_predictor(fused)  # (B, action_dim)
        return dist_pred, action_pred

    # ── Parameter helpers ─────────────────────────────────────────────────────

    def freeze_encoder(self) -> None:
        """Freeze all encoder weights (useful before LoRA injection)."""
        for p in self.obs_encoder.parameters():
            p.requires_grad = False
        if self.goal_encoder is not None:
            for p in self.goal_encoder.parameters():
                p.requires_grad = False

    def unfreeze_heads(self) -> None:
        """Ensure prediction heads are trainable."""
        for p in self.dist_predictor.parameters():
            p.requires_grad = True
        for p in self.action_predictor.parameters():
            p.requires_grad = True

    def count_parameters(self) -> dict[str, int]:
        total    = sum(p.numel() for p in self.parameters())
        frozen   = sum(p.numel() for p in self.parameters() if not p.requires_grad)
        encoder_params = list(self.obs_encoder.parameters())
        if self.goal_encoder is not None:
            encoder_params += list(self.goal_encoder.parameters())
        encoder  = sum(p.numel() for p in encoder_params)
        heads    = (
            sum(p.numel() for p in self.dist_predictor.parameters())
            + sum(p.numel() for p in self.action_predictor.parameters())
        )
        return {
            "total":     total,
            "trainable": total - frozen,
            "frozen":    frozen,
            "encoder":   encoder,
            "heads":     heads,
        }


# ── Convenience builder ───────────────────────────────────────────────────────

def build_gnm(cfg: dict) -> GNM:
    """Build a GNM from a config dictionary (loaded from YAML)."""
    return GNM(
        context_size    = cfg.get("context_size", 5),
        goal_conditioned= cfg.get("goal_conditioned", True),
        action_dim      = cfg.get("action_dim", 2),
        hidden_dim      = cfg.get("hidden_dim", 256),
        encoder         = cfg.get("encoder", "mobilenet"),
        out_dim         = cfg.get("out_dim", 512),
        pretrained      = cfg.get("pretrained", True),
    )
