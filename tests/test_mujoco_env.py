"""
MuJoCo Environment Tests — no GPU required.

Tests the full interface:
    import → reset → step × N → save_metrics → close
"""
from __future__ import annotations

import numpy as np
import pytest


class TestH1MuJoCoEnv:
    """Test H1MuJoCoEnv interface and physics."""

    def test_import(self):
        """Environment can be imported without GPU."""
        from fleet_safe_vla.envs.mujoco.h1_mujoco_env import H1MuJoCoEnv
        assert H1MuJoCoEnv is not None

    def test_instantiation(self):
        """Environment creates without error."""
        from fleet_safe_vla.envs.mujoco.h1_mujoco_env import H1MuJoCoEnv
        env = H1MuJoCoEnv(max_episode_steps=100)
        env.close()

    def test_observation_space(self):
        """Observation space has correct dimensions."""
        from fleet_safe_vla.envs.mujoco.h1_mujoco_env import H1MuJoCoEnv
        env = H1MuJoCoEnv()
        assert env.observation_space.shape == (45,), \
            f"Expected obs dim 45, got {env.observation_space.shape}"
        env.close()

    def test_action_space(self):
        """Action space has correct dimensions and valid bounds."""
        from fleet_safe_vla.envs.mujoco.h1_mujoco_env import H1MuJoCoEnv
        env = H1MuJoCoEnv()
        assert env.action_space.shape == (18,), \
            f"Expected action dim 18, got {env.action_space.shape}"
        assert np.all(env.action_space.low < env.action_space.high), \
            "Action space lower bounds must be < upper bounds"
        env.close()

    def test_reset_returns_obs(self):
        """reset() returns observation of correct shape."""
        from fleet_safe_vla.envs.mujoco.h1_mujoco_env import H1MuJoCoEnv
        env = H1MuJoCoEnv()
        result = env.reset(seed=42)
        if isinstance(result, tuple):
            obs, info = result
            assert isinstance(info, dict)
        else:
            obs = result
        assert obs.shape == (45,), f"reset() obs shape: {obs.shape}"
        assert np.all(np.isfinite(obs)), "reset() obs must be finite"
        env.close()

    def test_step_returns_correct_signature(self):
        """step() returns (obs, reward, done, info) or 5-tuple."""
        from fleet_safe_vla.envs.mujoco.h1_mujoco_env import H1MuJoCoEnv
        env = H1MuJoCoEnv()
        env.reset(seed=0)
        action = env.action_space.sample()
        result = env.step(action)
        assert len(result) in (4, 5), f"step() must return 4 or 5 values, got {len(result)}"
        if len(result) == 5:
            obs, rew, terminated, truncated, info = result
            assert isinstance(terminated, bool)
            assert isinstance(truncated, bool)
        else:
            obs, rew, done, info = result
            assert isinstance(done, bool)
        assert obs.shape == (45,)
        assert isinstance(rew, float)
        assert isinstance(info, dict)
        env.close()

    def test_10_step_smoke(self):
        """Run 10 steps without crashing."""
        from fleet_safe_vla.envs.mujoco.h1_mujoco_env import H1MuJoCoEnv
        env = H1MuJoCoEnv(max_episode_steps=100)
        env.reset(seed=123)
        for i in range(10):
            action = env.action_space.sample()
            result = env.step(action)
            if len(result) == 5:
                obs, rew, terminated, truncated, info = result
                done = terminated or truncated
            else:
                obs, rew, done, info = result
            assert obs.shape == (45,)
            assert np.all(np.isfinite(obs)), f"Step {i}: obs is not finite"
            assert "base_height_m" in info
            if done:
                break
        env.close()

    def test_reset_reproducibility(self):
        """Same seed gives same initial observation."""
        from fleet_safe_vla.envs.mujoco.h1_mujoco_env import H1MuJoCoEnv
        env = H1MuJoCoEnv()
        r1 = env.reset(seed=42)
        obs1 = r1[0] if isinstance(r1, tuple) else r1
        r2 = env.reset(seed=42)
        obs2 = r2[0] if isinstance(r2, tuple) else r2
        np.testing.assert_allclose(obs1, obs2, atol=1e-6)
        env.close()

    def test_close_idempotent(self):
        """close() can be called multiple times."""
        from fleet_safe_vla.envs.mujoco.h1_mujoco_env import H1MuJoCoEnv
        env = H1MuJoCoEnv()
        env.close()
        env.close()  # should not raise

    def test_context_manager(self):
        """Environment works as context manager."""
        from fleet_safe_vla.envs.mujoco.h1_mujoco_env import H1MuJoCoEnv
        with H1MuJoCoEnv() as env:
            result = env.reset(seed=0)
            obs = result[0] if isinstance(result, tuple) else result
            assert obs.shape == (45,)

    def test_full_episode_no_crash(self):
        """Run a full episode (max_episode_steps) without crashing."""
        from fleet_safe_vla.envs.mujoco.h1_mujoco_env import H1MuJoCoEnv
        env = H1MuJoCoEnv(max_episode_steps=50)
        env.reset(seed=7)
        done = False
        steps = 0
        while not done and steps < 50:
            result = env.step(env.action_space.sample())
            if len(result) == 5:
                _, _, terminated, truncated, _ = result
                done = terminated or truncated
            else:
                _, _, done, _ = result
            steps += 1
        env.close()
        assert steps > 0

    def test_info_contains_required_keys(self):
        """info dict contains expected diagnostic keys."""
        from fleet_safe_vla.envs.mujoco.h1_mujoco_env import H1MuJoCoEnv
        env = H1MuJoCoEnv()
        env.reset(seed=0)
        result = env.step(env.action_space.sample())
        info = result[-1]  # last element is always info
        assert "base_height_m" in info, "info must contain 'base_height_m'"
        assert "step" in info, "info must contain 'step'"
        env.close()
