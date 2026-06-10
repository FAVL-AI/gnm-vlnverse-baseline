"""
fleetsafe_wrapper.py — FleetSafe safety layer wrapping any VisualNav model.

Architecture
------------
  ┌──────────────┐   predict_action()    ┌─────────────────┐
  │  Adapter     │ ─────────────────────▶│ FleetSafeWrapper │
  │  (GNM/ViNT/  │                       │                  │
  │   NoMaD)     │ ◀─── preprocess() ───│ 1. call adapter  │
  └──────────────┘                       │ 2. get raw cmd   │
                                          │ 3. CBF-QP filter │
                                          │ 4. log delta     │
                                          └─────────────────┘

The wrapper:
  - Takes nominal cmd_vel from any adapter.
  - Applies YahboomCBFFilter (CBF-QP) for collision avoidance.
  - Logs raw_action, safe_action, intervention reason, min_obstacle_dist.
  - Emits the same CmdVel interface so callers need no changes.

Usage
-----
    adapter = GNMAdapter()
    adapter.load_checkpoint(ckpt_path)
    wrapper = FleetSafeWrapper(adapter, cbf_config=YahboomCBFConfig(d_safe_m=0.30))

    # Each step:
    preprocessed = adapter.preprocess_observation(obs_imgs, goal_img)
    result = wrapper.step(preprocessed, obs_vec, obstacle_positions)
    # result.safe_cmd_vel is the filtered command
    # result.info contains intervention details and logs
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import numpy as np

from fleet_safe_vla.integrations.visualnav_transformer.base_adapter import (
    ActionOutput,
    BaseVisualNavAdapter,
    CmdVel,
)
from fleet_safe_vla.fleet_safety.yahboom_cbf import YahboomCBFConfig, YahboomCBFFilter


# ── Step result ───────────────────────────────────────────────────────────────

@dataclass
class FleetSafeStepResult:
    """Full record of one wrapped inference + safety step."""

    # Timing
    total_ms: float = 0.0

    # Policy outputs
    action_output:  ActionOutput | None = None
    raw_cmd_vel:    CmdVel | None       = None
    safe_cmd_vel:   CmdVel | None       = None

    # Safety info
    intervened:     bool  = False
    estop:          bool  = False
    min_dist_m:     float = float("inf")
    intervention_reason: str = ""
    intervention_count: int  = 0

    # Derived delta metric
    @property
    def cmd_delta(self) -> np.ndarray:
        """Absolute difference between raw and safe cmd_vel as [dvx, dvy, dwz]."""
        if self.raw_cmd_vel is None or self.safe_cmd_vel is None:
            return np.zeros(3, dtype=np.float32)
        return np.abs(
            self.safe_cmd_vel.as_array() - self.raw_cmd_vel.as_array()
        )

    def to_log_dict(self) -> dict:
        return {
            "model":          self.action_output.model_name if self.action_output else "",
            "raw_vx":         self.raw_cmd_vel.vx  if self.raw_cmd_vel  else 0.0,
            "raw_vy":         self.raw_cmd_vel.vy  if self.raw_cmd_vel  else 0.0,
            "raw_wz":         self.raw_cmd_vel.wz  if self.raw_cmd_vel  else 0.0,
            "safe_vx":        self.safe_cmd_vel.vx if self.safe_cmd_vel else 0.0,
            "safe_vy":        self.safe_cmd_vel.vy if self.safe_cmd_vel else 0.0,
            "safe_wz":        self.safe_cmd_vel.wz if self.safe_cmd_vel else 0.0,
            "delta_vx":       float(self.cmd_delta[0]),
            "delta_vy":       float(self.cmd_delta[1]),
            "delta_wz":       float(self.cmd_delta[2]),
            "intervened":     self.intervened,
            "estop":          self.estop,
            "min_dist_m":     self.min_dist_m,
            "reason":         self.intervention_reason,
            "total_ms":       self.total_ms,
        }


# ── Wrapper ───────────────────────────────────────────────────────────────────

class FleetSafeWrapper:
    """
    Wraps any BaseVisualNavAdapter with the Yahboom CBF-QP safety filter.

    The wrapper keeps a running tally of intervention statistics that can be
    queried at the end of an episode for benchmark metric collection.

    Parameters
    ----------
    adapter       : Any loaded BaseVisualNavAdapter instance.
    cbf_config    : YahboomCBFConfig (default: d_safe_m=0.30, estop_dist_m=0.15).
    v_max         : Forward velocity limit passed to action_to_cmd_vel.
    vy_max        : Lateral velocity limit (0 = differential, >0 = holonomic).
    w_max         : Angular rate limit.
    control_hz    : Control frequency for waypoint-to-velocity scaling.
    """

    def __init__(
        self,
        adapter:       BaseVisualNavAdapter,
        cbf_config:    YahboomCBFConfig | None = None,
        v_max:         float = 0.3,
        vy_max:        float = 0.3,   # M3Pro is holonomic
        w_max:         float = 0.7,
        control_hz:    float = 4.0,
    ) -> None:
        self.adapter    = adapter
        self.cbf        = YahboomCBFFilter(cbf_config)
        self.v_max      = v_max
        self.vy_max     = vy_max
        self.w_max      = w_max
        self.control_hz = control_hz

        # Episode statistics
        self._total_steps:        int   = 0
        self._intervention_steps: int   = 0
        self._estop_steps:        int   = 0
        self._min_dist_seen:      float = float("inf")

    def step(
        self,
        preprocessed:        dict,
        obs_vec:             np.ndarray,
        obstacle_positions:  Sequence[np.ndarray] | None = None,
        robot_xy:            np.ndarray | None = None,
        obstacle_radii:      Sequence[float] | None = None,
    ) -> FleetSafeStepResult:
        """
        One wrapped inference + safety step.

        Embodied VLN perception contract
        ---------------------------------
        `preprocessed`  — camera-only input to the nav model (GNM/ViNT/NoMaD).
                          This is the ONLY thing the navigation policy sees.
                          It must come from the robot's egocentric forward-facing
                          camera — never from a bird's-eye or external view.

        `obs_vec`       — 47-dim kinematic state (IMU, odometry, wheel velocities).
                          Passed EXCLUSIVELY to the CBF-QP filter.  Never touches
                          the navigation model.

        `obstacle_positions` — world-frame obstacle centres for CBF computation.
                          Passed EXCLUSIVELY to the CBF-QP filter.  Never touches
                          the navigation model.  The nav model must infer obstacle
                          proximity from its camera input alone.

        Returns
        -------
        FleetSafeStepResult with both raw and safe cmd_vel populated.
        """
        t0 = time.perf_counter()
        self._total_steps += 1

        # 1. Model inference
        action = self.adapter.predict_action(preprocessed)

        # 2. Convert to nominal cmd_vel
        raw_cmd = self.adapter.action_to_cmd_vel(
            action,
            v_max      = self.v_max,
            vy_max     = self.vy_max,
            w_max      = self.w_max,
            control_hz = self.control_hz,
        )

        # 3. CBF-QP safety filter
        nominal_arr = np.array([raw_cmd.vx, raw_cmd.wz], dtype=np.float64)
        safe_arr, cbf_info = self.cbf.filter(
            obs_vec, nominal_arr, obstacle_positions,
            robot_xy=robot_xy, obstacle_radii=obstacle_radii,
        )

        # Rebuild CmdVel — CBF filters [vx, wz]; vy passes through clipped
        safe_vy = float(np.clip(raw_cmd.vy, -self.vy_max, self.vy_max))
        # If estop, zero vy too
        if cbf_info.get("estop", False):
            safe_vy = 0.0
        safe_cmd = CmdVel(
            vx = float(safe_arr[0]),
            vy = safe_vy,
            wz = float(safe_arr[1]),
        )

        # 4. Build result
        intervened = bool(cbf_info.get("intervened", False))
        estop      = bool(cbf_info.get("estop", False))
        min_dist   = float(cbf_info.get("min_dist_m", float("inf")))

        if intervened:
            self._intervention_steps += 1
        if estop:
            self._estop_steps += 1
        if min_dist < self._min_dist_seen:
            self._min_dist_seen = min_dist

        reason = ""
        if estop:
            reason = f"E-STOP: obstacle at {min_dist:.3f} m"
        elif intervened:
            reason = f"CBF: obstacle at {min_dist:.3f} m"

        total_ms = (time.perf_counter() - t0) * 1000.0
        return FleetSafeStepResult(
            total_ms            = total_ms,
            action_output       = action,
            raw_cmd_vel         = raw_cmd,
            safe_cmd_vel        = safe_cmd,
            intervened          = intervened,
            estop               = estop,
            min_dist_m          = min_dist,
            intervention_reason = reason,
            intervention_count  = self._intervention_steps,
        )

    def reset_stats(self) -> None:
        """Reset per-episode statistics (call at episode start)."""
        self._total_steps        = 0
        self._intervention_steps = 0
        self._estop_steps        = 0
        self._min_dist_seen      = float("inf")
        self.cbf._intervention_count = 0
        self.cbf._total_calls        = 0

    @property
    def intervention_rate(self) -> float:
        """Fraction of steps where CBF modified the nominal action."""
        if self._total_steps == 0:
            return 0.0
        return self._intervention_steps / self._total_steps

    @property
    def estop_rate(self) -> float:
        """Fraction of steps that triggered E-STOP."""
        if self._total_steps == 0:
            return 0.0
        return self._estop_steps / self._total_steps

    @property
    def min_obstacle_dist_m(self) -> float:
        """Minimum obstacle distance seen this episode."""
        return self._min_dist_seen

    def episode_summary(self) -> dict:
        """Return episode-level summary for benchmark metrics."""
        return {
            "model":               self.adapter.model_name,
            "fleetsafe_enabled":   True,
            "total_steps":         self._total_steps,
            "intervention_steps":  self._intervention_steps,
            "estop_steps":         self._estop_steps,
            "intervention_rate":   self.intervention_rate,
            "estop_rate":          self.estop_rate,
            "min_obstacle_dist_m": self._min_dist_seen,
        }
