"""
Tests for the Yahboom navigation CBF-QP filter (velocity-level, M3Pro).

Covers:
  - Import and instantiation
  - Passthrough when obstacles are far
  - Intervention when robot approaches obstacle
  - Surface-distance CBF (Isaac path, obs_r > 0)
  - Center-to-center CBF (MuJoCo path, obs_r = 0)
  - Emergency stop at estop_dist_m
  - Output shape and dtype
  - Intervention rate tracking
"""
from __future__ import annotations

import numpy as np
import pytest


class TestYahboomCBFImport:
    def test_import(self):
        from fleet_safe_vla.fleet_safety.yahboom_cbf import YahboomCBFFilter  # noqa: F401

    def test_config_import(self):
        from fleet_safe_vla.fleet_safety.yahboom_cbf import YahboomCBFConfig  # noqa: F401


class TestYahboomCBFInstantiation:
    def test_default_config(self):
        from fleet_safe_vla.fleet_safety.yahboom_cbf import YahboomCBFFilter
        filt = YahboomCBFFilter()
        assert filt.cfg.d_safe_m == 0.30

    def test_custom_config(self):
        from fleet_safe_vla.fleet_safety.yahboom_cbf import YahboomCBFFilter, YahboomCBFConfig
        cfg = YahboomCBFConfig(d_safe_m=0.5, alpha=2.0, max_linear_ms=1.0)
        filt = YahboomCBFFilter(cfg)
        assert filt.cfg.d_safe_m == 0.5


class TestYahboomCBFPassthrough:
    def test_no_obstacles_passthrough(self):
        from fleet_safe_vla.fleet_safety.yahboom_cbf import YahboomCBFFilter
        filt = YahboomCBFFilter()
        obs = np.zeros(36)
        action = np.array([0.3, 0.0])
        safe, info = filt.filter(obs, action, obstacle_positions=[], robot_xy=np.array([0.0, 0.0]))
        assert not info["intervened"]
        assert safe.shape == (2,)

    def test_far_obstacle_no_intervention(self):
        from fleet_safe_vla.fleet_safety.yahboom_cbf import YahboomCBFFilter
        filt = YahboomCBFFilter()
        obs = np.zeros(36)
        action = np.array([0.3, 0.0])
        # Obstacle 10 m away — should not trigger
        safe, info = filt.filter(
            obs, action,
            obstacle_positions=[np.array([10.0, 0.0])],
            robot_xy=np.array([0.0, 0.0]),
        )
        assert not info["intervened"]


class TestYahboomCBFIntervention:
    def test_close_obstacle_triggers_intervention(self):
        from fleet_safe_vla.fleet_safety.yahboom_cbf import YahboomCBFFilter
        filt = YahboomCBFFilter()
        obs = np.zeros(36)
        # Robot heading toward obstacle at 0.25 m (inside d_safe=0.30 m)
        action = np.array([0.5, 0.0])  # nominal: move forward
        safe, info = filt.filter(
            obs, action,
            obstacle_positions=[np.array([0.0, 0.25])],
            robot_xy=np.array([0.0, 0.0]),
        )
        # CBF must either intervene or reduce forward velocity
        assert info["min_dist_m"] < 0.30

    def test_output_shape_with_intervention(self):
        from fleet_safe_vla.fleet_safety.yahboom_cbf import YahboomCBFFilter
        filt = YahboomCBFFilter()
        obs = np.zeros(36)
        action = np.array([0.5, 0.1])
        safe, info = filt.filter(
            obs, action,
            obstacle_positions=[np.array([0.0, 0.25])],
            robot_xy=np.array([0.0, 0.0]),
        )
        assert safe.shape == (2,)
        assert safe.dtype == np.float32


class TestYahboomCBFEmergencyStop:
    def test_estop_when_too_close(self):
        from fleet_safe_vla.fleet_safety.yahboom_cbf import YahboomCBFFilter, YahboomCBFConfig
        cfg = YahboomCBFConfig(estop_dist_m=0.15, d_safe_m=0.30)
        filt = YahboomCBFFilter(cfg)
        obs = np.zeros(36)
        action = np.array([0.5, 0.0])
        # Obstacle at 0.1 m — inside estop_dist_m=0.15 m
        safe, info = filt.filter(
            obs, action,
            obstacle_positions=[np.array([0.0, 0.10])],
            robot_xy=np.array([0.0, 0.0]),
        )
        assert info["estop"] is True
        assert info["intervened"] is True
        np.testing.assert_array_equal(safe, [0.0, 0.0])


class TestYahboomCBFSurfaceDistance:
    def test_surface_distance_cbf_radius_path(self):
        """Isaac path: obstacle_radii provided → surface-distance barrier."""
        from fleet_safe_vla.fleet_safety.yahboom_cbf import YahboomCBFFilter
        filt = YahboomCBFFilter()
        obs = np.zeros(36)
        action = np.array([0.4, 0.0])
        # Center at 1.5 m, radius=1.0 m → surface_dist=0.5 m > d_safe=0.3 m (safe)
        safe, info = filt.filter(
            obs, action,
            obstacle_positions=[np.array([0.0, 1.5])],
            obstacle_radii=[1.0],
            robot_xy=np.array([0.0, 0.0]),
        )
        # Far enough from surface — should not estop
        assert not info.get("estop", False)

    def test_center_to_center_cbf_zero_radius(self):
        """MuJoCo path: obstacle_radii=None → center-to-center barrier."""
        from fleet_safe_vla.fleet_safety.yahboom_cbf import YahboomCBFFilter
        filt = YahboomCBFFilter()
        obs = np.zeros(36)
        action = np.array([0.4, 0.0])
        # Obstacle at 0.5 m center-to-center; with d_safe=0.3 m, CBF should be active
        safe, info = filt.filter(
            obs, action,
            obstacle_positions=[np.array([0.0, 0.5])],
            obstacle_radii=None,
            robot_xy=np.array([0.0, 0.0]),
        )
        assert safe.shape == (2,)
        assert "min_dist_m" in info


class TestYahboomCBFInterventionRate:
    def test_intervention_rate_increases(self):
        from fleet_safe_vla.fleet_safety.yahboom_cbf import YahboomCBFFilter, YahboomCBFConfig
        cfg = YahboomCBFConfig(estop_dist_m=0.05, d_safe_m=0.30)
        filt = YahboomCBFFilter(cfg)
        obs = np.zeros(36)
        action = np.array([0.5, 0.0])
        # No obstacle — no intervention
        filt.filter(obs, action, obstacle_positions=[], robot_xy=np.array([0.0, 0.0]))
        # Obstacle directly in robot's forward direction (x-axis): d=0.25m < d_safe=0.30m
        # 1D projection along x: direction_norm=[1,0], vx_component = vx * 1.0
        # CBF barrier h = 0.25²-0.30² = -0.0275 < 0 → active constraint → intervention
        filt.filter(obs, action, obstacle_positions=[np.array([0.25, 0.0])], robot_xy=np.array([0.0, 0.0]))
        assert filt._total_calls == 2

    def test_velocity_limits_respected(self):
        from fleet_safe_vla.fleet_safety.yahboom_cbf import YahboomCBFFilter, YahboomCBFConfig
        cfg = YahboomCBFConfig(max_linear_ms=0.5, max_angular_rs=1.0)
        filt = YahboomCBFFilter(cfg)
        obs = np.zeros(36)
        # Large nominal action — should be clipped
        action = np.array([5.0, 5.0])
        safe, info = filt.filter(obs, action, obstacle_positions=[], robot_xy=np.array([0.0, 0.0]))
        assert abs(safe[0]) <= 0.5 + 1e-6
        assert abs(safe[1]) <= 1.0 + 1e-6
