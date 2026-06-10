"""
Fleet-Safe Safety Filter — wraps robot-lab SafetyFilter with CBF integration.

This module provides a unified interface that combines:
  1. robot-lab's low-level SafetyFilter (joint limits, torque clamping, fall detection)
  2. fleet_safe CBFSafetyFilter (QP-based Control Barrier Function)

The combined filter is the recommended interface for deployment.

Usage:
    from fleet_safe_vla.sim2real.safety_filter.filter import FleetSafeCombinedFilter
    filt = FleetSafeCombinedFilter()
    safe_torques = filt.apply(obs, nominal_action, joint_pos, joint_vel, base_tilt)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from robot_lab.sim2real.safety_filter import (
    SafetyFilter,
    SafetyConfig,
    SafetyState,
)
from fleet_safe_vla.fleet_safety.cbf_filter import CBFSafetyFilter, CBFConfig


@dataclass
class FleetSafeCombinedConfig:
    """Combined configuration for the dual-layer safety filter."""
    # Low-level (robot-lab) parameters
    max_tilt_rad: float = 0.8
    min_base_height_m: float = 0.5
    max_torque: float = 300.0
    torque_ramp_steps: int = 50
    emergency_damping_kd: float = 5.0

    # CBF (mid-level) parameters
    cbf_max_tilt_rad: float = 0.7   # stricter than low-level
    cbf_gamma: float = 1.0

    # Joint position limits (18 DOF) — None = use H1 defaults
    joint_pos_limits: np.ndarray | None = None


class FleetSafeCombinedFilter:
    """
    Two-layer safety filter for H1 fleet deployment.

    Layer 1 (CBF): modifies target positions to satisfy barrier constraints
    Layer 2 (robot-lab SafetyFilter): final torque clamping + emergency stop

    The CBF layer runs in position space (target joint positions).
    The SafetyFilter layer runs in torque space.
    """

    def __init__(self, cfg: FleetSafeCombinedConfig | None = None) -> None:
        self.cfg = cfg or FleetSafeCombinedConfig()

        # Layer 1: CBF
        self._cbf = CBFSafetyFilter(CBFConfig(
            joint_pos_limits=self.cfg.joint_pos_limits,
            max_tilt_rad=self.cfg.cbf_max_tilt_rad,
            gamma=self.cfg.cbf_gamma,
        ))

        # Layer 2: robot-lab SafetyFilter
        self._sf = SafetyFilter(SafetyConfig(
            joint_pos_limits=self.cfg.joint_pos_limits,
            max_tilt_rad=self.cfg.max_tilt_rad,
            min_base_height_m=self.cfg.min_base_height_m,
            max_torque=self.cfg.max_torque,
            torque_ramp_steps=self.cfg.torque_ramp_steps,
            emergency_damping_kd=self.cfg.emergency_damping_kd,
        ))

        # PD gains for converting target positions to torques
        self._kp = np.array([200, 200, 200, 300, 40, 200, 200, 200, 300, 40,
                              40,  40,  40,  10,  40,  40,  40,  10], dtype=np.float32)
        self._kd = np.array([5, 5, 5, 8, 1, 5, 5, 5, 8, 1,
                              1, 1, 1, 0.5, 1, 1, 1, 0.5], dtype=np.float32)

    def apply(
        self,
        obs: np.ndarray,
        nominal_action: np.ndarray,
        joint_pos: np.ndarray,
        joint_vel: np.ndarray,
        base_tilt: float,
        base_height: float = 1.0,
    ) -> tuple[np.ndarray, dict]:
        """
        Apply two-layer safety filter.

        Args:
            obs:            (45,) proprioceptive observation
            nominal_action: (18,) target joint positions from policy
            joint_pos:      (18,) current joint positions
            joint_vel:      (18,) current joint velocities
            base_tilt:      current base tilt angle (radians)
            base_height:    current base height above ground (meters)

        Returns:
            (safe_torques, info)
            safe_torques: (18,) final safe torque commands
            info: dict with filter diagnostics
        """
        # Layer 1: CBF position filtering
        cbf_action, cbf_info = self._cbf.filter_action(obs, nominal_action)

        # Convert to torques via PD
        raw_torques = self._kp * (cbf_action - joint_pos) - self._kd * joint_vel

        # Layer 2: robot-lab safety filter
        safe_torques = self._sf.filter(
            raw_actions=raw_torques,
            joint_pos=joint_pos,
            joint_vel=joint_vel,
            base_tilt=base_tilt,
            base_height=base_height,
        )

        info = {
            **cbf_info,
            "safety_state": self._sf.state.name,
            "is_safe": self._sf.is_safe,
        }
        return safe_torques.astype(np.float32), info

    @property
    def state(self) -> SafetyState:
        """Current low-level safety state."""
        return self._sf.state

    @property
    def is_safe(self) -> bool:
        return self._sf.is_safe

    def reset(self) -> None:
        self._cbf.reset()
        self._sf.reset()

    def get_stats(self) -> dict:
        return {
            "cbf": self._cbf.get_stats(),
            "safety_state": self._sf.state.name,
        }
