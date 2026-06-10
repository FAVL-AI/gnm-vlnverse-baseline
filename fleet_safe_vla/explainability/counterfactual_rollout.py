"""
counterfactual_rollout.py — Short kinematic rollout for intervention counterfactuals.

For each intervention, rolls out both the raw (unmodified) policy action and the
safe (FleetSafe-corrected) action over a short horizon (default 2 s) to show:

  raw_action  → predicted trajectory → collision at X m
  safe_action → predicted trajectory → clearance of Y m

Backend contract
----------------
  "mock"    — 2-D constant-action kinematic rollout.  Valid for engineering/CI.
  "isaac"   — raises NotImplementedError with explicit message.
              No publication claim is allowed until Isaac branching rollout is
              implemented and validated.

The rollout is deliberately simple: constant velocity applied in body frame with
incremental heading integration.  It is not a physics simulation; it is a
transparency tool to show *why* the intervention mattered, not to make
quantitative trajectory predictions.
"""
from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Sequence


@dataclass
class CounterfactualRolloutRequest:
    raw_action:            tuple[float, float, float]   # (vx, vy, wz) body frame
    safe_action:           tuple[float, float, float]
    robot_xy:              tuple[float, float]           # world frame
    robot_heading:         float                         # radians
    obstacles:             list[tuple[float, float, float]]  # (x, y, radius_m) world frame
    rollout_horizon_s:     float = 2.0
    dt_s:                  float = 0.25
    collision_threshold_m: float = 0.10


@dataclass
class CounterfactualRolloutResult:
    raw_action_rollout:       list[list[float]]   # [[x, y], ...] world frame
    safe_action_rollout:      list[list[float]]
    raw_min_distance:         float               # min clearance over horizon
    safe_min_distance:        float
    raw_collision_predicted:  bool
    safe_collision_predicted: bool
    rollout_horizon_s:        float
    dt_s:                     float
    backend:                  str
    rollout_id:               str

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_action_rollout":       self.raw_action_rollout,
            "safe_action_rollout":      self.safe_action_rollout,
            "raw_min_distance":         self.raw_min_distance,
            "safe_min_distance":        self.safe_min_distance,
            "raw_collision_predicted":  self.raw_collision_predicted,
            "safe_collision_predicted": self.safe_collision_predicted,
            "rollout_horizon_s":        self.rollout_horizon_s,
            "dt_s":                     self.dt_s,
            "backend":                  self.backend,
            "rollout_id":               self.rollout_id,
        }


class CounterfactualRolloutEngine:
    """
    Backend-neutral counterfactual rollout engine.

    Parameters
    ----------
    backend              : "mock" for kinematic rollout, "isaac" for Isaac Sim branching.
    collision_threshold_m: Clearance below which a rollout predicts collision.
    """

    MOCK_BACKEND   = "mock"
    ISAAC_BACKEND  = "isaac"

    def __init__(
        self,
        backend:               str   = "mock",
        collision_threshold_m: float = 0.10,
    ) -> None:
        if backend not in (self.MOCK_BACKEND, self.ISAAC_BACKEND):
            raise ValueError(f"Unknown rollout backend: {backend!r}")
        self.backend               = backend
        self.collision_threshold_m = collision_threshold_m

    def rollout(self, request: CounterfactualRolloutRequest) -> CounterfactualRolloutResult:
        if self.backend == self.MOCK_BACKEND:
            return self._mock_rollout(request)
        # Isaac: explicit not-implemented so no accidental publication claim
        raise NotImplementedError(
            "Isaac branching rollout pending; no publication claim allowed. "
            "Implement fleet_safe_vla/envs/isaaclab/yahboom/ rollout integration "
            "before using this backend for any benchmark claim."
        )

    # ── Mock 2-D kinematic rollout ─────────────────────────────────────────────

    def _mock_rollout(self, request: CounterfactualRolloutRequest) -> CounterfactualRolloutResult:
        rollout_id = str(uuid.uuid4())[:8]
        raw_traj  = self._simulate(request, request.raw_action)
        safe_traj = self._simulate(request, request.safe_action)

        raw_min  = self._min_clearance(raw_traj,  request.obstacles)
        safe_min = self._min_clearance(safe_traj, request.obstacles)

        return CounterfactualRolloutResult(
            raw_action_rollout       = raw_traj,
            safe_action_rollout      = safe_traj,
            raw_min_distance         = raw_min,
            safe_min_distance        = safe_min,
            raw_collision_predicted  = raw_min  < self.collision_threshold_m,
            safe_collision_predicted = safe_min < self.collision_threshold_m,
            rollout_horizon_s        = request.rollout_horizon_s,
            dt_s                     = request.dt_s,
            backend                  = self.MOCK_BACKEND,
            rollout_id               = rollout_id,
        )

    @staticmethod
    def _simulate(
        request: CounterfactualRolloutRequest,
        action:  tuple[float, float, float],
    ) -> list[list[float]]:
        """Constant-action 2-D holonomic rollout.  Returns [[x, y], ...] including start."""
        vx, vy, wz = action
        x, y = request.robot_xy
        heading = request.robot_heading
        dt = request.dt_s
        n_steps = max(1, int(round(request.rollout_horizon_s / dt)))

        traj = [[x, y]]
        for _ in range(n_steps):
            cos_h = math.cos(heading)
            sin_h = math.sin(heading)
            x += (vx * cos_h - vy * sin_h) * dt
            y += (vx * sin_h + vy * cos_h) * dt
            heading += wz * dt
            traj.append([x, y])
        return traj

    @staticmethod
    def _min_clearance(
        traj:      list[list[float]],
        obstacles: list[tuple[float, float, float]],
    ) -> float:
        """Return the minimum surface-to-surface clearance along the trajectory."""
        if not obstacles:
            return float("inf")
        min_d = float("inf")
        for x, y in traj:
            for ox, oy, orad in obstacles:
                d = math.hypot(x - ox, y - oy) - orad
                if d < min_d:
                    min_d = d
        return min_d
