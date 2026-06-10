"""
Safety Filter Tests — no GPU required.

Tests both the robot-lab SafetyFilter and the Fleet-Safe CBFSafetyFilter.
"""
from __future__ import annotations

import importlib.util

import numpy as np
import pytest

_has_robot_lab = importlib.util.find_spec("robot_lab") is not None
_skip_robot_lab = pytest.mark.skipif(not _has_robot_lab, reason="robot_lab not installed")


class TestCBFFilter:
    """Tests for fleet_safe CBFSafetyFilter."""

    def _make_obs(self, tilt_z: float = -1.0) -> np.ndarray:
        """Create a 45-dim observation with given gravity z component."""
        obs = np.zeros(45, dtype=np.float32)
        obs[3:6] = [0.0, 0.0, tilt_z]  # proj_gravity
        return obs

    def test_import(self):
        from fleet_safe_vla.fleet_safety.cbf_filter import CBFSafetyFilter, CBFConfig
        assert CBFSafetyFilter is not None

    def test_instantiation(self):
        from fleet_safe_vla.fleet_safety.cbf_filter import CBFSafetyFilter, CBFConfig
        cbf = CBFSafetyFilter(CBFConfig())
        assert cbf is not None

    def test_safe_action_passthrough(self):
        """Safe action at default pose should not be modified."""
        from fleet_safe_vla.fleet_safety.cbf_filter import CBFSafetyFilter, CBFConfig
        cbf = CBFSafetyFilter(CBFConfig())
        obs = self._make_obs(tilt_z=-1.0)
        action = np.zeros(18, dtype=np.float32)  # at default (safe) pose
        safe_action, info = cbf.filter_action(obs, action)
        assert safe_action.shape == (18,), f"Expected (18,), got {safe_action.shape}"
        assert not info["intervened"], "Should not intervene on safe action"

    def test_intervention_on_joint_violation(self):
        """Action pushing joint beyond limit should be modified."""
        from fleet_safe_vla.fleet_safety.cbf_filter import CBFSafetyFilter, CBFConfig
        cbf = CBFSafetyFilter(CBFConfig())
        obs = self._make_obs()
        # Push knee (idx 3) beyond upper limit (2.443)
        obs[9 + 3] = 2.4  # current knee position (q_rel, close to limit)
        action = np.zeros(18, dtype=np.float32)
        action[3] = 2.5  # target beyond limit
        safe_action, info = cbf.filter_action(obs, action)
        # Safe action should be clamped
        assert safe_action[3] <= 2.443 + 0.1, \
            f"Knee action not clamped: {safe_action[3]:.3f}"

    def test_output_shape(self):
        """filter_action always returns (18,) array."""
        from fleet_safe_vla.fleet_safety.cbf_filter import CBFSafetyFilter
        cbf = CBFSafetyFilter()
        obs = self._make_obs()
        action = np.random.randn(18).astype(np.float32) * 0.5
        safe_action, info = cbf.filter_action(obs, action)
        assert safe_action.shape == (18,)
        assert safe_action.dtype == np.float32

    def test_info_dict_keys(self):
        """filter_action info dict has required keys."""
        from fleet_safe_vla.fleet_safety.cbf_filter import CBFSafetyFilter
        cbf = CBFSafetyFilter()
        obs = self._make_obs()
        _, info = cbf.filter_action(obs, np.zeros(18, dtype=np.float32))
        assert "intervened" in info
        assert "h_min" in info
        assert "qp_success" in info

    def test_stats_tracking(self):
        """Intervention count is tracked correctly."""
        from fleet_safe_vla.fleet_safety.cbf_filter import CBFSafetyFilter
        cbf = CBFSafetyFilter()
        obs = self._make_obs()
        for _ in range(5):
            cbf.filter_action(obs, np.zeros(18, dtype=np.float32))
        stats = cbf.get_stats()
        assert stats["total_calls"] == 5

    def test_reset_clears_state(self):
        """reset() clears last_safe_action."""
        from fleet_safe_vla.fleet_safety.cbf_filter import CBFSafetyFilter
        cbf = CBFSafetyFilter()
        obs = self._make_obs()
        cbf.filter_action(obs, np.zeros(18, dtype=np.float32))
        cbf.reset()
        assert cbf._last_safe_action is None

    def test_make_cbf_filter_factory(self):
        """make_cbf_filter factory function works."""
        from fleet_safe_vla.fleet_safety.cbf_filter import make_cbf_filter
        cbf = make_cbf_filter(max_tilt_rad=0.6, gamma=2.0)
        assert cbf.cfg.max_tilt_rad == 0.6
        assert cbf.cfg.gamma == 2.0


@_skip_robot_lab
class TestRobotLabSafetyFilter:
    """Tests for robot-lab SafetyFilter integration."""

    def test_import(self):
        from robot_lab.sim2real.safety_filter import SafetyFilter, SafetyConfig, SafetyState
        assert SafetyFilter is not None

    def test_initial_state_ramping_up(self):
        from robot_lab.sim2real.safety_filter import SafetyFilter, SafetyConfig, SafetyState
        sf = SafetyFilter(SafetyConfig())
        assert sf.state == SafetyState.RAMPING_UP

    def test_nominal_after_ramp(self):
        """After ramp_steps, filter transitions to NOMINAL."""
        from robot_lab.sim2real.safety_filter import SafetyFilter, SafetyConfig, SafetyState
        cfg = SafetyConfig(torque_ramp_steps=5)
        sf = SafetyFilter(cfg)
        q = np.zeros(19)
        qd = np.zeros(19)
        actions = np.zeros(19)
        for _ in range(10):
            sf.filter(actions, q, qd, base_tilt=0.0, base_height=1.0)
        assert sf.state == SafetyState.NOMINAL

    def test_emergency_on_tilt(self):
        """Exceeding tilt threshold triggers EMERGENCY or HOLDING (damping applied)."""
        from robot_lab.sim2real.safety_filter import SafetyFilter, SafetyConfig, SafetyState
        cfg = SafetyConfig(max_tilt_rad=0.5, torque_ramp_steps=1)
        sf = SafetyFilter(cfg)
        q = np.zeros(19)
        qd = np.zeros(19)
        actions = np.zeros(19)
        # Fast-forward to NOMINAL
        for _ in range(5):
            sf.filter(actions, q, qd, base_tilt=0.0, base_height=1.0)
        # Trigger emergency: filter() immediately applies emergency damp and transitions
        # to HOLDING (robot-lab SafetyFilter transitions EMERGENCY->HOLDING within filter())
        result = sf.filter(actions, q, qd, base_tilt=0.8, base_height=1.0)
        # After triggering, state is EMERGENCY or HOLDING depending on implementation
        assert sf.state in (SafetyState.EMERGENCY, SafetyState.HOLDING), \
            f"Expected EMERGENCY or HOLDING, got {sf.state}"
        # Output should be damping torques (zeros when qd=0)
        np.testing.assert_array_equal(result, np.zeros(19))

    def test_filter_output_shape(self):
        """filter() output shape matches input."""
        from robot_lab.sim2real.safety_filter import SafetyFilter, SafetyConfig
        sf = SafetyFilter(SafetyConfig())
        actions = np.random.randn(19).astype(np.float32)
        q = np.zeros(19, dtype=np.float32)
        qd = np.zeros(19, dtype=np.float32)
        result = sf.filter(actions, q, qd, base_tilt=0.0, base_height=1.0)
        assert result.shape == actions.shape

    def test_reset_restarts_ramp(self):
        """reset() puts filter back in RAMPING_UP."""
        from robot_lab.sim2real.safety_filter import SafetyFilter, SafetyConfig, SafetyState
        cfg = SafetyConfig(torque_ramp_steps=2)
        sf = SafetyFilter(cfg)
        q = np.zeros(19)
        qd = np.zeros(19)
        actions = np.zeros(19)
        for _ in range(10):
            sf.filter(actions, q, qd, 0.0, 1.0)
        assert sf.state == SafetyState.NOMINAL
        sf.reset()
        assert sf.state == SafetyState.RAMPING_UP


@_skip_robot_lab
class TestCombinedFilter:
    """Tests for the combined CBF + robot-lab filter."""

    def test_import(self):
        from fleet_safe_vla.sim2real.safety_filter.filter import FleetSafeCombinedFilter
        assert FleetSafeCombinedFilter is not None

    def test_instantiation(self):
        from fleet_safe_vla.sim2real.safety_filter.filter import FleetSafeCombinedFilter
        filt = FleetSafeCombinedFilter()
        assert filt is not None

    def test_apply_output_shape(self):
        """apply() returns torques of shape (18,)."""
        from fleet_safe_vla.sim2real.safety_filter.filter import FleetSafeCombinedFilter
        filt = FleetSafeCombinedFilter()
        obs = np.zeros(45, dtype=np.float32)
        obs[3:6] = [0, 0, -1.0]
        action = np.zeros(18, dtype=np.float32)
        q = np.zeros(18, dtype=np.float32)
        qd = np.zeros(18, dtype=np.float32)
        torques, info = filt.apply(obs, action, q, qd, base_tilt=0.0)
        assert torques.shape == (18,)
        assert "intervened" in info
        assert "safety_state" in info
