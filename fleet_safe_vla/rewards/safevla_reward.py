"""
safevla_reward.py — SafeVLA CMDP reward + cost functions.

Implements the reward structure for safe goal-conditioned visual navigation
under Constrained Markov Decision Process (CMDP) constraints:

    max_π  E[Σ r(s,a)]
    s.t.   E[Σ c_i(s,a)] ≤ d_i   ∀ constraint i

Reward components
-----------------
  r_progress   : Negative distance to goal — encourages forward progress.
                 Computed as Δ||p_robot − p_goal|| (improvement in distance).
  r_success    : Large positive reward on reaching goal (d_to_goal < 0.30m).
  r_smooth     : Negative L2 norm of velocity change — penalises jerky motion.
  r_social     : Penalty for entering personal space of nearby humans.
  r_timeout    : Negative reward if episode exceeds time limit.

Safety cost (separate from reward — used by CMDP/CPO/PPO-Lagrangian)
----------------------------------------------------------------------
  c_collision  : 1.0 if collision (d_surface < 0), else 0.
  c_near_miss  : Smooth cost ∈ [0,1] based on minimum obstacle distance.
  c_cbf        : Magnitude of CBF velocity correction (|u_nom − u_safe|).
  c_social     : 1.0 if robot enters personal space (<0.5m) of any human.

Usage
-----
  from fleet_safe_vla.rewards.safevla_reward import SafeVLAReward, SafetyConfig

  cfg  = SafetyConfig(d_safe=0.50, personal_space=0.80, w_progress=1.0)
  rew  = SafeVLAReward(cfg)

  # Each step:
  step_out = rew.step(
      robot_xy      = np.array([x, y]),
      goal_xy       = np.array([gx, gy]),
      prev_goal_dist= prev_dist,
      cmd_vel_nom   = np.array([vx_nom, wz_nom]),
      cmd_vel_safe  = np.array([vx_safe, wz_safe]),
      obstacle_dists= [d1, d2, ...],   # surface distances to obstacles
      human_dists   = [h1, h2, ...],   # distances to humans (None if no humans)
      step:         = step_idx,
      max_steps     = 600,
  )

  total_reward = step_out.reward
  safety_cost  = step_out.cost_collision + step_out.cost_near_miss

Integration with PPO / CPO
--------------------------
  Pass `total_reward` as the RL reward signal.
  Pass `safety_cost` as the constraint cost for:
    - PPO-Lagrangian: augment reward as r − λ·cost
    - CPO / TRPO-Lagrangian: enforce E[cost] ≤ d
    - FleetSafe (inference-time): CBF-QP bypasses RL entirely for safety
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np


# ── Configuration ─────────────────────────────────────────────────────────────

@dataclass
class SafetyConfig:
    """Hyperparameters for SafeVLA reward and cost functions."""

    # Safety thresholds
    d_safe:         float = 0.50  # CBF activation distance (surface)
    estop_dist:     float = 0.30  # emergency stop distance
    personal_space: float = 0.80  # minimum acceptable distance to humans (m)
    near_miss_dist: float = 0.45  # distance below which near-miss cost activates

    # Goal reaching
    goal_radius:    float = 0.30  # success radius (m)

    # Reward weights
    w_progress:     float = 1.0   # distance-improvement weight
    w_success:      float = 100.0 # goal-reached bonus
    w_smooth:       float = 0.10  # velocity-smoothness penalty
    w_social:       float = 5.0   # personal-space penalty
    w_timeout:      float = -1.0  # per-step timeout penalty (applied at last step)

    # CBF cost weight (for PPO-Lagrangian augmentation)
    lambda_cbf:     float = 0.0   # 0 = no Lagrangian; >0 = augment reward

    # Smoothness: compare against previous cmd_vel
    smooth_vel_memory: bool = True


# ── Per-step output ───────────────────────────────────────────────────────────

@dataclass
class StepOutput:
    """Reward and cost breakdown for one control step."""

    # Reward components
    r_progress:   float = 0.0
    r_success:    float = 0.0
    r_smooth:     float = 0.0
    r_social:     float = 0.0
    r_timeout:    float = 0.0

    # Safety costs (separate from reward — for CMDP constraints)
    cost_collision:  float = 0.0  # binary: 0 or 1
    cost_near_miss:  float = 0.0  # smooth ∈ [0, 1]
    cost_cbf:        float = 0.0  # |u_nom − u_safe|₂
    cost_social:     float = 0.0  # binary: 0 or 1

    # Diagnostic
    goal_dist_m:         float = 0.0
    min_obs_dist_m:      float = float("inf")
    min_human_dist_m:    float = float("inf")
    cbf_intervention:    bool  = False
    success:             bool  = False
    collision:           bool  = False

    @property
    def reward(self) -> float:
        return self.r_progress + self.r_success + self.r_smooth + self.r_social + self.r_timeout

    @property
    def total_cost(self) -> float:
        return self.cost_collision + self.cost_near_miss + self.cost_cbf + self.cost_social

    @property
    def is_terminal(self) -> bool:
        return self.success or self.collision


# ── SafeVLA reward function ───────────────────────────────────────────────────

class SafeVLAReward:
    """
    Stateful reward + cost function for SafeVLA CMDP navigation.

    State carried between steps:
      - Previous goal distance (for Δ-progress)
      - Previous cmd_vel (for smoothness)
      - Episode statistics

    Call reset() at the start of each episode.
    """

    def __init__(self, config: SafetyConfig | None = None):
        self.cfg = config or SafetyConfig()
        self._prev_goal_dist: float | None = None
        self._prev_cmd_vel:   np.ndarray   = np.zeros(2)
        self._episode_reward: float        = 0.0
        self._episode_cost:   float        = 0.0
        self._step_count:     int          = 0

    def reset(self) -> None:
        """Reset state at episode start."""
        self._prev_goal_dist = None
        self._prev_cmd_vel   = np.zeros(2)
        self._episode_reward = 0.0
        self._episode_cost   = 0.0
        self._step_count     = 0

    def step(
        self,
        robot_xy:       np.ndarray,
        goal_xy:        np.ndarray,
        cmd_vel_nom:    np.ndarray,            # [vx, wz] from navigation policy
        cmd_vel_safe:   np.ndarray,            # [vx, wz] after CBF-QP
        obstacle_dists: Sequence[float],       # surface distance per obstacle
        human_dists:    Sequence[float] | None = None,
        step:           int  = 0,
        max_steps:      int  = 600,
    ) -> StepOutput:
        out = StepOutput()
        cfg = self.cfg
        self._step_count += 1

        # ── Goal distance ─────────────────────────────────────────────────────
        goal_dist = float(np.linalg.norm(robot_xy - goal_xy))
        out.goal_dist_m = goal_dist

        # ── Progress reward ───────────────────────────────────────────────────
        if self._prev_goal_dist is not None:
            delta = self._prev_goal_dist - goal_dist   # positive = moved closer
            out.r_progress = cfg.w_progress * delta
        self._prev_goal_dist = goal_dist

        # ── Success ───────────────────────────────────────────────────────────
        if goal_dist < cfg.goal_radius:
            out.r_success = cfg.w_success
            out.success   = True

        # ── Obstacle distances ─────────────────────────────────────────────────
        obs_arr = np.array(obstacle_dists, dtype=float) if obstacle_dists else np.array([99.0])
        min_obs = float(np.min(obs_arr))
        out.min_obs_dist_m = min_obs

        # Collision cost: binary
        if min_obs < 0.0:
            out.cost_collision = 1.0
            out.collision      = True

        # Near-miss cost: smooth sigmoid  c = 1 / (1 + exp(k*(d - d_near)))
        if min_obs < cfg.near_miss_dist:
            k = 20.0  # sharpness
            d_hat = min_obs / max(cfg.near_miss_dist, 1e-6)
            out.cost_near_miss = float(1.0 / (1.0 + math.exp(k * (d_hat - 0.5))))

        # ── CBF correction cost ───────────────────────────────────────────────
        delta_vel = np.array(cmd_vel_safe, dtype=float) - np.array(cmd_vel_nom, dtype=float)
        out.cost_cbf       = float(np.linalg.norm(delta_vel))
        out.cbf_intervention = out.cost_cbf > 1e-4

        # ── Smoothness reward ─────────────────────────────────────────────────
        if cfg.smooth_vel_memory:
            delta_vel_prev = np.array(cmd_vel_safe) - self._prev_cmd_vel
            out.r_smooth = -cfg.w_smooth * float(np.sum(delta_vel_prev**2))
        self._prev_cmd_vel = np.array(cmd_vel_safe, dtype=float)

        # ── Social safety ─────────────────────────────────────────────────────
        if human_dists is not None and len(human_dists) > 0:
            h_arr = np.array(human_dists, dtype=float)
            min_h = float(np.min(h_arr))
            out.min_human_dist_m = min_h
            if min_h < cfg.personal_space:
                # Penalty proportional to intrusion depth
                intrusion = (cfg.personal_space - min_h) / cfg.personal_space
                out.r_social    = -cfg.w_social * intrusion
                out.cost_social = 1.0 if min_h < cfg.personal_space * 0.5 else intrusion

        # ── Timeout ───────────────────────────────────────────────────────────
        if step >= max_steps - 1 and not out.success:
            out.r_timeout = cfg.w_timeout

        # ── PPO-Lagrangian augmentation (optional) ────────────────────────────
        if cfg.lambda_cbf > 0:
            # Augment reward: r_aug = r - λ·cost_cbf
            # (caller still receives both separately for logging)
            pass  # reward property computes without augmentation; callers add λ·cost

        # ── Episode accumulators ──────────────────────────────────────────────
        self._episode_reward += out.reward
        self._episode_cost   += out.total_cost

        return out

    def episode_summary(self) -> dict:
        return {
            "total_reward":   round(self._episode_reward, 4),
            "total_cost":     round(self._episode_cost, 4),
            "n_steps":        self._step_count,
            "mean_reward":    round(self._episode_reward / max(self._step_count, 1), 4),
            "mean_cost":      round(self._episode_cost   / max(self._step_count, 1), 4),
        }


# ── PPO-Lagrangian augmentation helper ───────────────────────────────────────

class LagrangianAugmentor:
    """
    Adaptive Lagrangian multiplier for PPO-Lagrangian / CPO training.

    Maintains a running λ that penalises safety-cost violations.
    At each policy update:
        λ ← max(0, λ + α_λ · (E[cost] − d))
    where d is the constraint budget.

    Usage (in your training loop):
        aug = LagrangianAugmentor(budget=0.05, lr=1e-3)
        for batch in replay_buffer:
            rewards_aug = aug.augment(batch.rewards, batch.costs)
            # train policy on rewards_aug
            aug.update(mean_batch_cost)
    """

    def __init__(self, budget: float = 0.05, lr: float = 1e-3):
        self.budget  = budget
        self.lr      = lr
        self.lambda_ = 0.0

    def augment(self, rewards: np.ndarray, costs: np.ndarray) -> np.ndarray:
        """Return r − λ·c for each step."""
        return rewards - self.lambda_ * costs

    def update(self, mean_cost: float) -> None:
        """Update λ based on constraint violation."""
        self.lambda_ = max(0.0, self.lambda_ + self.lr * (mean_cost - self.budget))

    @property
    def state(self) -> dict:
        return {"lambda": self.lambda_, "budget": self.budget, "lr": self.lr}


# ── CMDP constraint budgets (paper-referenced values) ────────────────────────

#: Constraint budgets for PPO-Lagrangian / CPO training.
#: These match the SafeVLA paper's evaluation protocol.
CMDP_BUDGETS: dict[str, float] = {
    "cost_collision":   0.00,   # zero collisions allowed in expectation
    "cost_near_miss":   0.05,   # ≤5% of steps within near-miss distance
    "cost_cbf":         0.10,   # ≤0.1 m/s mean CBF velocity correction
    "cost_social":      0.02,   # ≤2% of steps in personal space
}


# ── Convenience: integrate with FleetSafe CBF output ─────────────────────────

def cbf_to_step_output(
    robot_xy:    np.ndarray,
    goal_xy:     np.ndarray,
    u_nom:       np.ndarray,
    u_safe:      np.ndarray,
    cbf_info:    dict,
    obs_dists:   list[float],
    human_dists: list[float] | None = None,
    reward_fn:   SafeVLAReward | None = None,
    step:        int = 0,
    max_steps:   int = 600,
) -> StepOutput:
    """
    Convenience wrapper: convert FleetSafe CBF filter output → SafeVLA StepOutput.

    cbf_info is the dict returned by YahboomCBFFilter.filter():
        {"intervened": bool, "h_min": float, ...}
    """
    if reward_fn is None:
        reward_fn = SafeVLAReward()
    return reward_fn.step(
        robot_xy       = robot_xy,
        goal_xy        = goal_xy,
        cmd_vel_nom    = u_nom,
        cmd_vel_safe   = u_safe,
        obstacle_dists = obs_dists,
        human_dists    = human_dists,
        step           = step,
        max_steps      = max_steps,
    )
