"""
Fleet-Safe State Estimator — wraps robot-lab StateEstimator.

Provides fleet-aware state estimation with:
  - Complementary filter for IMU fusion (via robot-lab StateEstimator)
  - Base height estimation from joint kinematics
  - Fleet-wide state synchronization hooks
  - Telemetry for monitoring

Usage:
    from fleet_safe_vla.sim2real.state_estimation.estimator import FleetStateEstimator
    est = FleetStateEstimator()
    state = est.update(imu_quat, imu_gyro, joint_pos)
    # state keys: proj_gravity, base_ang_vel, base_height, base_vel_est
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from robot_lab.sim2real.state_estimator import StateEstimator, StateEstimatorConfig


@dataclass
class FleetStateEstimatorConfig:
    """Extended config for fleet state estimation."""
    # Complementary filter parameters (passed to robot-lab StateEstimator)
    alpha: float = 0.98
    dt_imu: float = 0.01           # IMU rate (100 Hz)
    standing_height_m: float = 1.0

    # Height estimation parameters
    use_kinematic_height: bool = True  # estimate height from joint kinematics
    height_ema_alpha: float = 0.3      # EMA smoothing for height estimate

    # Velocity estimation (finite difference from position history)
    estimate_base_velocity: bool = True
    vel_filter_alpha: float = 0.7


# H1 standing leg geometry (approximate)
# Used for height estimation from joint angles
_THIGH_LENGTH = 0.35   # m
_SHANK_LENGTH = 0.35   # m
_ANKLE_HEIGHT = 0.06   # m (ankle to ground)


def _estimate_base_height(
    hip_pitch_l: float,
    knee_l: float,
    ankle_l: float,
    hip_pitch_r: float,
    knee_r: float,
    ankle_r: float,
) -> float:
    """
    Estimate base height from leg joint angles using forward kinematics.

    Assumes flat ground. Uses simplified 2D planar model (sagittal plane).
    Returns height of pelvis above ground in meters.
    """
    def _leg_height(hip_p: float, knee: float, ankle: float) -> float:
        """Height of pelvis above ground for one leg."""
        # Thigh vertical projection
        thigh_z = _THIGH_LENGTH * np.cos(hip_p)
        # Shank vertical projection (knee bends backward)
        shank_z = _SHANK_LENGTH * np.cos(hip_p + knee)
        # Foot height (ankle link)
        return thigh_z + shank_z + _ANKLE_HEIGHT

    h_left  = _leg_height(hip_pitch_l, knee_l, ankle_l)
    h_right = _leg_height(hip_pitch_r, knee_r, ankle_r)
    # Take max of both legs (supporting leg)
    return float(max(h_left, h_right))


class FleetStateEstimator:
    """
    Extended state estimator for fleet deployment.

    Wraps robot-lab's StateEstimator and adds:
      - Kinematic height estimation from joint positions
      - Filtered base velocity estimate
      - Telemetry accumulation

    Output dict keys:
        proj_gravity  (3,) float32
        base_ang_vel  (3,) float32
        base_height   float32
        base_vel_est  (3,) float32  — estimated base velocity
        tilt_rad      float32       — estimated tilt angle
    """

    def __init__(self, cfg: FleetStateEstimatorConfig | None = None) -> None:
        self.cfg = cfg or FleetStateEstimatorConfig()

        # robot-lab core estimator
        self._est = StateEstimator(StateEstimatorConfig(
            alpha=self.cfg.alpha,
            accel_gravity=9.81,
            dt=self.cfg.dt_imu,
            standing_height_m=self.cfg.standing_height_m,
        ))

        self._height_estimate = self.cfg.standing_height_m
        self._vel_estimate = np.zeros(3, dtype=np.float32)
        self._last_height: float | None = None

    def update(
        self,
        imu_quat: np.ndarray,
        imu_gyro: np.ndarray,
        joint_pos: np.ndarray | None = None,
    ) -> dict[str, np.ndarray | float]:
        """
        Update state estimate.

        Args:
            imu_quat:  (4,) [x, y, z, w] quaternion from IMU
            imu_gyro:  (3,) angular velocity (rad/s) from IMU gyro
            joint_pos: (18,) joint positions for height estimation

        Returns:
            dict with state estimates
        """
        # robot-lab complementary filter
        est = self._est.update(imu_quat, imu_gyro, joint_pos)

        proj_grav = est["proj_gravity"]
        ang_vel   = est["base_ang_vel"]

        # Tilt angle from gravity projection
        cos_tilt = float(np.clip(-proj_grav[2], -1.0, 1.0))
        tilt_rad = float(np.arccos(cos_tilt))

        # Height estimation
        if self.cfg.use_kinematic_height and joint_pos is not None and len(joint_pos) >= 10:
            # joint_pos order: [lhy, lhr, lhp, lk, la, rhy, rhr, rhp, rk, ra, ...]
            h_kin = _estimate_base_height(
                hip_pitch_l=float(joint_pos[2]),
                knee_l=float(joint_pos[3]),
                ankle_l=float(joint_pos[4]),
                hip_pitch_r=float(joint_pos[7]),
                knee_r=float(joint_pos[8]),
                ankle_r=float(joint_pos[9]),
            )
            # EMA smoothing
            alpha_h = self.cfg.height_ema_alpha
            self._height_estimate = (
                (1 - alpha_h) * self._height_estimate + alpha_h * h_kin
            )
        else:
            self._height_estimate = float(est["base_height"])

        # Velocity estimation (finite differences on height)
        if self.cfg.estimate_base_velocity and self._last_height is not None:
            dh = self._height_estimate - self._last_height
            vz_est = dh / self.cfg.dt_imu
            alpha_v = self.cfg.vel_filter_alpha
            self._vel_estimate[2] = (
                (1 - alpha_v) * self._vel_estimate[2] + alpha_v * vz_est
            )
        self._last_height = self._height_estimate

        return {
            "proj_gravity": proj_grav,
            "base_ang_vel": ang_vel,
            "base_height": np.float32(self._height_estimate),
            "base_vel_est": self._vel_estimate.copy(),
            "tilt_rad": np.float32(tilt_rad),
            "orientation_quat": self._est.orientation_quat,
        }

    def reset(self) -> None:
        self._est.reset()
        self._height_estimate = self.cfg.standing_height_m
        self._vel_estimate = np.zeros(3, dtype=np.float32)
        self._last_height = None
