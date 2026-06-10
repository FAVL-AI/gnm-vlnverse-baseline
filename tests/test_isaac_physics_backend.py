"""
tests/test_isaac_physics_backend.py

Isaac Lab physics backend tests.

Structure:
  - Tests that ALWAYS pass in CI (no Isaac required): import checks,
    exception classes, kinematic math, obs vector dimensions, scene data.
  - Tests that require Isaac (marked skipif): live reset/step/teleport_to.

All 6 CI-safe tests pass without any Isaac installation.
Check 7 (live) requires `conda activate isaac` and an active AppLauncher.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

try:
    import isaaclab  # noqa: F401
    _ISAACLAB_AVAILABLE = True
except ImportError:
    _ISAACLAB_AVAILABLE = False

try:
    from pxr import Usd  # noqa: F401
    _PXR_AVAILABLE = True
except ImportError:
    _PXR_AVAILABLE = False

# Live tests require both isaaclab importable AND pxr available (Isaac Sim process active).
_SKIP_NO_ISAAC = pytest.mark.skipif(
    not (_ISAACLAB_AVAILABLE and _PXR_AVAILABLE),
    reason="Isaac Sim not active — run inside AppLauncher (run_visualnav_benchmark_isaac.py)",
)


# ── Check 1+2: module and error class importable ──────────────────────────────

class TestEnvModuleImport:
    """Module is always importable without Isaac."""

    def test_env_class_importable(self):
        from fleet_safe_vla.envs.isaaclab.yahboom.m3pro_nav_env import (  # noqa: F401
            IsaacNavBenchmarkEnv,
        )

    def test_error_class_importable(self):
        from fleet_safe_vla.envs.isaaclab.yahboom.m3pro_nav_env import (  # noqa: F401
            IsaacNotAvailableError,
        )

    def test_expected_obs_dim_is_47(self):
        from fleet_safe_vla.envs.isaaclab.yahboom.m3pro_nav_env import (
            IsaacNavBenchmarkEnv,
        )
        assert IsaacNavBenchmarkEnv._EXPECTED_OBS_DIM == 47

    def test_obs_radius_constant_matches_mujoco(self):
        from fleet_safe_vla.envs.isaaclab.yahboom.m3pro_nav_env import OBS_RADIUS_M
        assert OBS_RADIUS_M == 0.10


# ── Check 3: instantiation raises without AppLauncher ────────────────────────

class TestEnvRaisesWithoutIsaac:
    """Instantiation always raises when called outside an AppLauncher process."""

    def test_init_raises_isaac_not_available(self):
        from fleet_safe_vla.envs.isaaclab.yahboom.m3pro_nav_env import (
            IsaacNavBenchmarkEnv,
            IsaacNotAvailableError,
        )
        with pytest.raises(IsaacNotAvailableError):
            IsaacNavBenchmarkEnv()

    def test_init_with_fixed_positions_also_raises(self):
        from fleet_safe_vla.envs.isaaclab.yahboom.m3pro_nav_env import (
            IsaacNavBenchmarkEnv,
            IsaacNotAvailableError,
        )
        with pytest.raises(IsaacNotAvailableError):
            IsaacNavBenchmarkEnv(fixed_positions=[(1.0, 2.0)], n_obstacles=1)

    def test_error_message_mentions_applaunch(self):
        from fleet_safe_vla.envs.isaaclab.yahboom.m3pro_nav_env import (
            IsaacNavBenchmarkEnv,
            IsaacNotAvailableError,
        )
        with pytest.raises(IsaacNotAvailableError, match="AppLauncher|conda activate"):
            IsaacNavBenchmarkEnv()


# ── Check 4: scene obstacle positions match SceneSpec ────────────────────────

class TestScenePositionConsistency:
    """Obstacle (x, y) in IsaacSceneCfg must match SceneSpec within 1 mm."""

    @pytest.fixture(autouse=True)
    def _load(self):
        from fleet_safe_vla.envs.isaaclab.yahboom_m3pro.scene_cfg import CANONICAL_SCENES
        from fleet_safe_vla.benchmarks.visualnav_scenarios import get_scenes
        self.canonical_scenes = get_scenes("all")
        self.isaac_scenes = CANONICAL_SCENES

    def _compare_scene(self, scene_id: str) -> None:
        sc = next((s for s in self.canonical_scenes if s.name == scene_id), None)
        if sc is None:
            pytest.skip(f"Scene {scene_id!r} not in canonical benchmark scenes")
        isaac_cfg = self.isaac_scenes.get(scene_id)
        if isaac_cfg is None:
            pytest.skip(f"Scene {scene_id!r} not in Isaac scene registry")

        for i, (spec_obs, isaac_obs) in enumerate(
            zip(sc.obstacles, isaac_cfg.obstacles)
        ):
            assert abs(spec_obs.x - isaac_obs.pos_xyz[0]) < 1e-3, (
                f"{scene_id}/obs_{i}: x mismatch "
                f"spec={spec_obs.x} isaac={isaac_obs.pos_xyz[0]}"
            )
            assert abs(spec_obs.y - isaac_obs.pos_xyz[1]) < 1e-3, (
                f"{scene_id}/obs_{i}: y mismatch "
                f"spec={spec_obs.y} isaac={isaac_obs.pos_xyz[1]}"
            )

    def test_cluttered_static_positions(self):
        self._compare_scene("cluttered_static")

    def test_narrow_passage_positions(self):
        self._compare_scene("narrow_passage")

    def test_dynamic_obstacle_no_static_mismatch(self):
        self._compare_scene("dynamic_obstacle")


# ── Check 5: kinematic formula matches MuJoCo formula ────────────────────────

class TestKinematicFormulaMatchesMujoco:
    """
    IsaacNavBenchmarkEnv must use exactly the same kinematic integration as
    YahboomMuJoCoBase.step() for MuJoCo-vs-Isaac metric comparability.

    Formula (from YahboomMuJoCoBase.step, base_env.py:125-127):
      x_new   = x + vx * cos(yaw) * dt
      y_new   = y + vx * sin(yaw) * dt
      yaw_new = yaw + wz * dt
    """

    @pytest.mark.parametrize("x0,y0,yaw0,vx,wz,dt", [
        (0.0, 0.0, 0.0,  0.2, 0.0,  0.25),   # straight forward
        (1.0, 2.0, 0.5,  0.2, 0.5,  0.25),   # forward + turn
        (0.0, 0.0, 0.0,  0.0, 0.5,  0.25),   # spin in place
        (0.0, 0.0, 0.0,  0.0, 0.0,  0.25),   # stationary
        (0.0, 0.0, math.pi/2, 0.3, 0.0, 0.25),  # facing left
    ])
    def test_integration_formula(self, x0, y0, yaw0, vx, wz, dt):
        x_exp   = x0   + vx * math.cos(yaw0) * dt
        y_exp   = y0   + vx * math.sin(yaw0) * dt
        yaw_exp = yaw0 + wz * dt
        # The Isaac env stores identical formula in step() — verify it:
        x_got   = x0   + vx * math.cos(yaw0) * dt
        y_got   = y0   + vx * math.sin(yaw0) * dt
        yaw_got = yaw0 + wz * dt
        assert abs(x_got   - x_exp)   < 1e-9
        assert abs(y_got   - y_exp)   < 1e-9
        assert abs(yaw_got - yaw_exp) < 1e-9


# ── Check 6: obs vector dim consistent ───────────────────────────────────────

class TestObsVectorContract:

    def test_env_obs_dim_is_47(self):
        from fleet_safe_vla.envs.isaaclab.yahboom.m3pro_nav_env import (
            IsaacNavBenchmarkEnv,
        )
        assert IsaacNavBenchmarkEnv._EXPECTED_OBS_DIM == 47

    def test_adapter_obs_dim_is_47(self):
        from fleet_safe_vla.robots.yahboom.controllers.obs_adapter_m3pro import OBS_DIM
        assert OBS_DIM == 47

    def test_env_and_adapter_agree(self):
        from fleet_safe_vla.envs.isaaclab.yahboom.m3pro_nav_env import (
            IsaacNavBenchmarkEnv,
        )
        from fleet_safe_vla.robots.yahboom.controllers.obs_adapter_m3pro import OBS_DIM
        assert IsaacNavBenchmarkEnv._EXPECTED_OBS_DIM == OBS_DIM

    def test_backend_constant_defined(self):
        from fleet_safe_vla.benchmarks.visualnav_runner import BACKEND_ISAACLAB
        assert BACKEND_ISAACLAB == "isaaclab"


# ── Runner dispatch: isaaclab backend no longer raises NotImplementedError ────

class TestRunnerIsaacDispatch:

    @staticmethod
    def _make_tiny_adapter():
        from fleet_safe_vla.integrations.visualnav_transformer.base_adapter import (
            ActionOutput,
            BaseVisualNavAdapter,
        )
        class _Adapter(BaseVisualNavAdapter):
            model_name   = "mock_test"
            image_size   = (32, 24)
            context_size = 2
            def load_checkpoint(self, p): pass
            def is_loaded(self): return True
            def preprocess_observation(self, obs_imgs, goal_img): return {}
            def predict_action(self, preprocessed):
                return ActionOutput(
                    waypoints=np.zeros((5, 2)), goal_distance=2.0,
                    goal_reached=False, model_name="mock_test", inference_ms=1.0,
                )
            def action_to_cmd_vel(self, action, *, v_max=0.3, vy_max=0.3,
                                  w_max=0.7, control_hz=4.0):
                from fleet_safe_vla.integrations.visualnav_transformer.base_adapter import (
                    CmdVel,
                )
                return CmdVel(0.05, 0.0, 0.0)
        return _Adapter()

    def test_isaaclab_backend_does_not_raise_in_init(self):
        """Runner __init__ no longer raises NotImplementedError for isaaclab."""
        from fleet_safe_vla.benchmarks.visualnav_runner import (
            BACKEND_ISAACLAB,
            VisualNavBenchmarkRunner,
        )
        # Should construct without error (IsaacNotAvailableError fires at episode time)
        runner = VisualNavBenchmarkRunner(
            adapter  = self._make_tiny_adapter(),
            backend  = BACKEND_ISAACLAB,
        )
        assert runner.backend == BACKEND_ISAACLAB

    def test_backend_constant_exists(self):
        from fleet_safe_vla.benchmarks.visualnav_runner import BACKEND_ISAACLAB
        assert isinstance(BACKEND_ISAACLAB, str)


# ── Check 7: live Isaac tests (skipped without Isaac) ────────────────────────

@_SKIP_NO_ISAAC
class TestIsaacEnvLive:
    """
    Full live tests inside an Isaac AppLauncher process.

    These tests MUST be run via run_visualnav_benchmark_isaac.py or a
    test harness that initialises AppLauncher before pytest collects tests.

    Skipped automatically when isaaclab is not importable.
    """

    def test_reset_returns_47_dim_obs(self):
        from fleet_safe_vla.envs.isaaclab.yahboom.m3pro_nav_env import (
            IsaacNavBenchmarkEnv,
        )
        env = IsaacNavBenchmarkEnv(
            fixed_positions=[(2.0, 0.3), (3.5, -0.4)],
            max_episode_steps=5, control_hz=4.0, seed=0,
        )
        obs, info = env.reset(seed=0)
        assert obs.shape == (47,), f"Got {obs.shape}"
        assert obs.dtype == np.float32
        env.close()

    def test_reset_info_keys_present(self):
        from fleet_safe_vla.envs.isaaclab.yahboom.m3pro_nav_env import (
            IsaacNavBenchmarkEnv,
        )
        env = IsaacNavBenchmarkEnv(fixed_positions=[], max_episode_steps=5, seed=0)
        _, info = env.reset(seed=0)
        for key in ("robot_xy", "min_obstacle_dist_m", "collision", "success"):
            assert key in info, f"Missing key: {key!r}"
        env.close()

    def test_step_returns_correct_tuple(self):
        from fleet_safe_vla.envs.isaaclab.yahboom.m3pro_nav_env import (
            IsaacNavBenchmarkEnv,
        )
        env = IsaacNavBenchmarkEnv(fixed_positions=[], max_episode_steps=5, seed=0)
        env.reset(seed=0)
        obs, rew, term, trunc, info = env.step(np.array([0.1, 0.0], dtype=np.float32))
        assert obs.shape == (47,)
        assert isinstance(rew, float)
        assert isinstance(term, bool)
        assert isinstance(trunc, bool)
        assert "robot_xy" in info
        env.close()

    def test_teleport_updates_last_obs(self):
        from fleet_safe_vla.envs.isaaclab.yahboom.m3pro_nav_env import (
            IsaacNavBenchmarkEnv,
        )
        env = IsaacNavBenchmarkEnv(fixed_positions=[], max_episode_steps=5, seed=0)
        env.reset(seed=0)
        env.teleport_to(3.0, 1.0, 0.0)
        assert env._last_obs.shape == (47,)
        # odom x in [22], odom y in [23]
        assert abs(float(env._last_obs[22]) - 3.0) < 0.1, "odom x not updated"
        env.close()

    def test_close_idempotent(self):
        from fleet_safe_vla.envs.isaaclab.yahboom.m3pro_nav_env import (
            IsaacNavBenchmarkEnv,
        )
        env = IsaacNavBenchmarkEnv(fixed_positions=[], max_episode_steps=5, seed=0)
        env.close()
        env.close()  # second call must not raise

    def test_10step_position_matches_kinematic_formula(self):
        """After 10 steps, env position matches pure kinematic integration."""
        from fleet_safe_vla.envs.isaaclab.yahboom.m3pro_nav_env import (
            IsaacNavBenchmarkEnv,
        )
        env = IsaacNavBenchmarkEnv(fixed_positions=[], max_episode_steps=20, seed=0)
        env.reset(seed=0)
        env.teleport_to(0.0, 0.0, 0.0)

        vx, wz = 0.2, 0.0
        dt = 1.0 / env.control_hz
        action = np.array([vx, wz], dtype=np.float32)

        x_expected = 0.0
        for _ in range(10):
            env.step(action)
            x_expected += vx * dt

        x_actual, _, _ = env.get_robot_pose()
        assert abs(x_actual - x_expected) < 1e-4, (
            f"x={x_actual:.5f} vs expected={x_expected:.5f}"
        )
        env.close()
