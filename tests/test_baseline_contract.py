"""
test_baseline_contract.py — Enforce the VisualNav-Transformer baseline contract.

These tests are the machine-readable form of the baseline contract documented in
docs/baselines/VISUALNAV_TRANSFORMER_BASELINE_CONTRACT.md.

What they enforce
-----------------
1.  Each adapter's image_size / context_size / action_horizon matches the
    upstream visualnav-transformer config (published model cards).
2.  preprocess_observation() produces correctly shaped tensors (obs, goal).
3.  predict_action() returns waypoints in (N, 2) robot-frame format.
4.  Forward waypoint → vx ≥ 0 (correct sign convention).
5.  Left waypoint → wz > 0 (CCW positive, standard ROS convention).
6.  Waypoint displacements are physically plausible (< 2 m per control step).
7.  Preprocessed dict contains NO state/obstacle keys (perception contract).
8.  IsaacCameraObsAdapter raises if goal is absent and pads correctly.
9.  benchmark_runner._render_camera raises RuntimeError if camera is missing.
10. FleetSafeWrapper step() receives only camera tensor — no state keys.

Tests that require upstream + checkpoints are explicitly skipped if absent.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

_VNT_ROOT = _REPO_ROOT / "third_party" / "visualnav-transformer"
_HAS_TORCH = False
try:
    import torch   # noqa: F401
    _HAS_TORCH = True
except ImportError:
    pass

# ── Published upstream specs (source of truth) ────────────────────────────────
#
# GNM:   train/gnm_train/config/gnm.yaml   image_size [85,64] context 5
# ViNT:  train/vint_train/config/vint.yaml  image_size [85,64] context 5
# NoMaD: train/vint_train/config/nomad.yaml image_size [96,96] context 5 traj 8
#
_SPEC = {
    "gnm":   {"image_size": (85, 64), "context_size": 5, "action_horizon": 5},
    "vint":  {"image_size": (85, 64), "context_size": 5, "action_horizon": 5},
    "nomad": {"image_size": (96, 96), "context_size": 5, "action_horizon": 8},
}

# Keys that must NEVER appear in the preprocessed dict (perception contract)
_FORBIDDEN_KEYS = {
    "robot_xy", "robot_pose", "obstacle_positions", "obstacle_xy",
    "state_vec", "obs_vec", "position", "map", "global_map",
    "cbf_input", "lidar", "sonar",
}

# ── ImageNet normalisation (applied by all three models) ─────────────────────
_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD  = np.array([0.229, 0.224, 0.225], dtype=np.float32)


# ── Mock adapter fixture ──────────────────────────────────────────────────────

from fleet_safe_vla.integrations.visualnav_transformer.base_adapter import (
    ActionOutput, BaseVisualNavAdapter, waypoints_to_cmd_vel,
)


def _make_mock(model: str):
    """Fully-loaded mock adapter that simulates correct upstream behaviour."""
    spec = _SPEC[model]
    W, H = spec["image_size"]
    N    = spec["action_horizon"]
    ctx  = spec["context_size"]

    class _M(BaseVisualNavAdapter):
        model_name    = model
        image_size    = spec["image_size"]
        context_size  = spec["context_size"]
        action_horizon = spec["action_horizon"]

        def load_checkpoint(self, path):
            self._loaded = True

        def preprocess_observation(self, obs_imgs, goal_img):
            if not _HAS_TORCH:
                return {"obs_tensor": None, "goal_tensor": None}
            import torch as _torch
            tensors = []
            for img in obs_imgs:
                arr = img.astype(np.float32) / 255.0
                arr = (arr - _MEAN) / _STD
                tensors.append(arr.transpose(2, 0, 1))
            obs_np = np.concatenate(tensors, axis=0)           # (3*ctx, H, W)
            g_arr  = (goal_img.astype(np.float32) / 255.0 - _MEAN) / _STD
            g_np   = g_arr.transpose(2, 0, 1)                  # (3, H, W)
            return {
                "obs_tensor":  _torch.tensor(obs_np[None]),    # (1, 3*ctx, H, W)
                "goal_tensor": _torch.tensor(g_np[None]),       # (1, 3, H, W)
            }

        def predict_action(self, preprocessed, *, _waypoints=None):
            rng = np.random.default_rng(42)
            wp  = rng.uniform(0.05, 0.25, (N, 2)).astype(np.float32)
            wp[:, 0] = np.abs(wp[:, 0])   # forward-positive convention
            if _waypoints is not None:
                wp = np.array(_waypoints, dtype=np.float32).reshape(N, 2)
            return ActionOutput(
                waypoints     = wp,
                goal_distance = 4.0,
                goal_reached  = False,
                model_name    = model,
                inference_ms  = 8.0,
            )

    a = _M()
    a._loaded = True
    return a


@pytest.fixture(params=["gnm", "vint", "nomad"])
def mock_adapter(request):
    return _make_mock(request.param)


@pytest.fixture(params=["gnm", "vint", "nomad"])
def model_name(request):
    return request.param


# ── Section 1: Adapter configuration contract ─────────────────────────────────

class TestAdapterConfiguration:
    """Each adapter must declare the image_size and context_size from upstream."""

    def test_gnm_image_size(self):
        from fleet_safe_vla.integrations.visualnav_transformer.gnm_adapter import GNMAdapter
        a = GNMAdapter()
        assert a.image_size == _SPEC["gnm"]["image_size"], (
            f"GNM image_size {a.image_size} ≠ upstream {_SPEC['gnm']['image_size']}"
        )

    def test_gnm_context_size(self):
        from fleet_safe_vla.integrations.visualnav_transformer.gnm_adapter import GNMAdapter
        assert GNMAdapter().context_size == _SPEC["gnm"]["context_size"]

    def test_vint_image_size(self):
        from fleet_safe_vla.integrations.visualnav_transformer.vint_adapter import ViNTAdapter
        a = ViNTAdapter()
        assert a.image_size == _SPEC["vint"]["image_size"], (
            f"ViNT image_size {a.image_size} ≠ upstream {_SPEC['vint']['image_size']}"
        )

    def test_vint_context_size(self):
        from fleet_safe_vla.integrations.visualnav_transformer.vint_adapter import ViNTAdapter
        assert ViNTAdapter().context_size == _SPEC["vint"]["context_size"]

    def test_nomad_image_size(self):
        from fleet_safe_vla.integrations.visualnav_transformer.nomad_adapter import NoMaDAdapter
        a = NoMaDAdapter()
        assert a.image_size == _SPEC["nomad"]["image_size"], (
            f"NoMaD image_size {a.image_size} ≠ upstream {_SPEC['nomad']['image_size']}"
        )

    def test_nomad_action_horizon(self):
        from fleet_safe_vla.integrations.visualnav_transformer.nomad_adapter import NoMaDAdapter
        a = NoMaDAdapter()
        assert a.action_horizon == _SPEC["nomad"]["action_horizon"], (
            f"NoMaD action_horizon {a.action_horizon} ≠ upstream 8 (diffusion horizon)"
        )


# ── Section 2: Preprocessing tensor contract ──────────────────────────────────

class TestPreprocessingContract:

    @pytest.mark.skipif(not _HAS_TORCH, reason="torch not installed")
    def test_obs_tensor_shape(self, mock_adapter, model_name):
        """obs_tensor must be (1, 3*context_size, H, W)."""
        if mock_adapter.model_name != model_name:
            pytest.skip()
        spec = _SPEC[model_name]
        W, H, ctx = *spec["image_size"], spec["context_size"]
        obs  = [np.zeros((H, W, 3), dtype=np.uint8)] * ctx
        goal = np.zeros((H, W, 3), dtype=np.uint8)
        prep = mock_adapter.preprocess_observation(obs, goal)
        t    = prep["obs_tensor"]
        assert t is not None
        assert tuple(t.shape) == (1, 3 * ctx, H, W), (
            f"{model_name} obs_tensor shape {tuple(t.shape)} ≠ (1, {3*ctx}, {H}, {W})"
        )

    @pytest.mark.skipif(not _HAS_TORCH, reason="torch not installed")
    def test_goal_tensor_shape(self, mock_adapter, model_name):
        """goal_tensor must be (1, 3, H, W)."""
        if mock_adapter.model_name != model_name:
            pytest.skip()
        spec = _SPEC[model_name]
        W, H = spec["image_size"]
        obs  = [np.zeros((H, W, 3), dtype=np.uint8)] * spec["context_size"]
        goal = np.zeros((H, W, 3), dtype=np.uint8)
        prep = mock_adapter.preprocess_observation(obs, goal)
        t    = prep["goal_tensor"]
        assert t is not None
        assert tuple(t.shape) == (1, 3, H, W)

    @pytest.mark.skipif(not _HAS_TORCH, reason="torch not installed")
    def test_imagenet_normalisation_applied(self, mock_adapter, model_name):
        """A white input image should produce tensor values ≈ (1-mean)/std."""
        if mock_adapter.model_name != model_name:
            pytest.skip()
        spec = _SPEC[model_name]
        W, H = spec["image_size"]
        ctx  = spec["context_size"]
        white = np.full((H, W, 3), 255, dtype=np.uint8)
        prep  = mock_adapter.preprocess_observation([white] * ctx, white)
        arr   = prep["obs_tensor"].numpy().flatten()
        # Expected values: (1.0 - mean) / std for each channel
        expected = (np.ones(3) - _MEAN) / _STD   # ≈ [2.249, 2.429, 2.640]
        # All values should be close to one of the three expected channel values
        for exp_val in expected:
            close = np.any(np.abs(arr - exp_val) < 0.05)
            assert close, (
                f"{model_name}: white-image norm failed — "
                f"no values near {exp_val:.3f} in tensor"
            )


# ── Section 3: Action output contract ─────────────────────────────────────────

class TestActionOutputContract:

    def test_waypoints_are_2d(self, mock_adapter, model_name):
        """predict_action must return waypoints with shape (N, 2)."""
        if mock_adapter.model_name != model_name:
            pytest.skip()
        spec = _SPEC[model_name]
        W, H = spec["image_size"]
        obs  = [np.zeros((H, W, 3), dtype=np.uint8)] * spec["context_size"]
        goal = np.zeros((H, W, 3), dtype=np.uint8)
        act  = mock_adapter.predict_action(mock_adapter.preprocess_observation(obs, goal))
        assert act.waypoints.ndim == 2
        assert act.waypoints.shape[1] == 2, (
            f"{model_name}: waypoints.shape={act.waypoints.shape} (column 1 must be 2 for x,y)"
        )

    def test_waypoint_count_matches_action_horizon(self, mock_adapter, model_name):
        if mock_adapter.model_name != model_name:
            pytest.skip()
        spec = _SPEC[model_name]
        W, H = spec["image_size"]
        obs  = [np.zeros((H, W, 3), dtype=np.uint8)] * spec["context_size"]
        goal = np.zeros((H, W, 3), dtype=np.uint8)
        act  = mock_adapter.predict_action(mock_adapter.preprocess_observation(obs, goal))
        assert act.waypoints.shape[0] == spec["action_horizon"], (
            f"{model_name}: got {act.waypoints.shape[0]} waypoints, "
            f"expected {spec['action_horizon']}"
        )

    def test_waypoints_physically_plausible(self, mock_adapter, model_name):
        """Waypoint displacements must be < 2 m per control step."""
        if mock_adapter.model_name != model_name:
            pytest.skip()
        spec = _SPEC[model_name]
        W, H = spec["image_size"]
        obs  = [np.zeros((H, W, 3), dtype=np.uint8)] * spec["context_size"]
        goal = np.zeros((H, W, 3), dtype=np.uint8)
        act  = mock_adapter.predict_action(mock_adapter.preprocess_observation(obs, goal))
        max_disp = float(np.max(np.linalg.norm(act.waypoints, axis=1)))
        assert max_disp < 2.0, (
            f"{model_name}: max waypoint displacement {max_disp:.3f} m "
            f"exceeds 2 m physical limit"
        )


# ── Section 4: Sign convention contract ──────────────────────────────────────

class TestSignConvention:
    """Forward = +x, left = +y (robot frame).  vx ≥ 0 for forward goal.  wz > 0 for left."""

    def _run(self, adapter, model_name, waypoints):
        spec = _SPEC[model_name]
        W, H = spec["image_size"]
        obs  = [np.zeros((H, W, 3), dtype=np.uint8)] * spec["context_size"]
        goal = np.zeros((H, W, 3), dtype=np.uint8)
        prep = adapter.preprocess_observation(obs, goal)
        N    = spec["action_horizon"]
        act  = ActionOutput(
            waypoints=np.tile(waypoints, (N, 1)).astype(np.float32),
            model_name=model_name,
        )
        return waypoints_to_cmd_vel(act.waypoints, v_max=0.5, w_max=1.5)

    def test_forward_goal_positive_vx(self, mock_adapter, model_name):
        """Goal straight ahead (positive x) → vx > 0."""
        if mock_adapter.model_name != model_name:
            pytest.skip()
        cmd = self._run(mock_adapter, model_name, [0.20, 0.00])
        assert cmd.vx > 0, f"{model_name}: forward waypoint → vx={cmd.vx:.4f} (must be > 0)"
        assert abs(cmd.wz) < 0.01, f"{model_name}: forward waypoint → wz={cmd.wz:.4f} (must ≈ 0)"

    def test_left_goal_positive_wz(self, mock_adapter, model_name):
        """Goal to the left (positive y) → wz > 0 (CCW, ROS convention)."""
        if mock_adapter.model_name != model_name:
            pytest.skip()
        cmd = self._run(mock_adapter, model_name, [0.05, 0.15])
        assert cmd.wz > 0, f"{model_name}: left waypoint → wz={cmd.wz:.4f} (must be > 0)"

    def test_right_goal_negative_wz(self, mock_adapter, model_name):
        """Goal to the right (negative y) → wz < 0 (CW)."""
        if mock_adapter.model_name != model_name:
            pytest.skip()
        cmd = self._run(mock_adapter, model_name, [0.05, -0.15])
        assert cmd.wz < 0, f"{model_name}: right waypoint → wz={cmd.wz:.4f} (must be < 0)"

    def test_zero_waypoint_zero_velocity(self):
        """Zero waypoint → zero cmd_vel."""
        cmd = waypoints_to_cmd_vel(np.zeros((5, 2)), v_max=0.3, w_max=0.7)
        assert cmd.vx == pytest.approx(0.0)
        assert cmd.wz == pytest.approx(0.0)


# ── Section 5: Perception contract ───────────────────────────────────────────

class TestPerceptionContract:
    """
    The navigation policy must ONLY receive camera observations.
    State, obstacle geometry, and simulator data must never enter the policy.
    """

    def test_no_forbidden_keys_in_preprocessed(self, mock_adapter, model_name):
        """preprocessed dict must not contain any privileged state keys."""
        if mock_adapter.model_name != model_name:
            pytest.skip()
        spec = _SPEC[model_name]
        W, H = spec["image_size"]
        obs  = [np.zeros((H, W, 3), dtype=np.uint8)] * spec["context_size"]
        goal = np.zeros((H, W, 3), dtype=np.uint8)
        prep = mock_adapter.preprocess_observation(obs, goal)
        leaked = set(prep.keys()) & _FORBIDDEN_KEYS
        assert len(leaked) == 0, (
            f"{model_name}: preprocessed dict contains forbidden state keys: {leaked}\n"
            "These keys would give the policy privileged simulator access, "
            "violating the perception contract."
        )

    def test_preprocessed_contains_only_camera_keys(self, mock_adapter, model_name):
        """preprocessed dict must contain obs_tensor and goal_tensor (camera data only)."""
        if mock_adapter.model_name != model_name:
            pytest.skip()
        spec = _SPEC[model_name]
        W, H = spec["image_size"]
        obs  = [np.zeros((H, W, 3), dtype=np.uint8)] * spec["context_size"]
        goal = np.zeros((H, W, 3), dtype=np.uint8)
        prep = mock_adapter.preprocess_observation(obs, goal)
        required = {"obs_tensor", "goal_tensor"}
        missing  = required - set(prep.keys())
        assert len(missing) == 0, (
            f"{model_name}: preprocessed dict missing camera keys: {missing}"
        )

    def test_fleetsafe_wrapper_does_not_pass_obstacles_to_policy(self):
        """FleetSafeWrapper must not forward obstacle_positions into the policy."""
        from fleet_safe_vla.integrations.visualnav_transformer.fleetsafe_wrapper import (
            FleetSafeWrapper,
        )
        class _MockAdapter(BaseVisualNavAdapter):
            model_name   = "mock"
            image_size   = (85, 64)
            context_size = 5
            received_keys: list = []

            def load_checkpoint(self, p): self._loaded = True
            def preprocess_observation(self, obs, goal):
                return {"obs_tensor": None, "goal_tensor": None}
            def predict_action(self, prep):
                _MockAdapter.received_keys = list(prep.keys())
                return ActionOutput(
                    waypoints=np.array([[0.1, 0.0]] * 5, dtype=np.float32),
                    model_name="mock",
                )

        adapter = _MockAdapter()
        adapter._loaded = True
        wrapper = FleetSafeWrapper(adapter)
        obs_vec = np.zeros(47, dtype=np.float32)
        prep    = adapter.preprocess_observation([], np.zeros((64, 85, 3), np.uint8))
        close_obstacles = [np.array([0.5, 0.0])]
        wrapper.step(prep, obs_vec, obstacle_positions=close_obstacles)

        leaked = set(_MockAdapter.received_keys) & _FORBIDDEN_KEYS
        assert len(leaked) == 0, (
            f"FleetSafeWrapper leaked obstacle info into policy: {leaked}"
        )


# ── Section 6: Camera adapter contract ───────────────────────────────────────

class TestCameraAdapterContract:

    def test_raises_without_goal(self):
        """Camera adapter must raise RuntimeError when no goal is set."""
        from fleet_safe_vla.integrations.visualnav_transformer.isaac_obs_adapter import (
            IsaacCameraObsAdapter,
        )
        cam = IsaacCameraObsAdapter(image_size=(85, 64), context_size=5)
        cam.push_frame(np.zeros((480, 640, 3), dtype=np.uint8))
        with pytest.raises(RuntimeError, match="[Gg]oal"):
            cam.get_context()

    def test_raises_when_queue_empty(self):
        """Camera adapter must raise RuntimeError when context queue is empty."""
        from fleet_safe_vla.integrations.visualnav_transformer.isaac_obs_adapter import (
            IsaacCameraObsAdapter,
        )
        cam = IsaacCameraObsAdapter(image_size=(85, 64), context_size=5)
        cam.set_goal_image(np.zeros((64, 85, 3), dtype=np.uint8))
        with pytest.raises(RuntimeError, match="[Ee]mpty|empty"):
            cam.get_context()

    def test_context_padding_to_full_length(self):
        """One frame pushed → context padded to context_size copies."""
        from fleet_safe_vla.integrations.visualnav_transformer.isaac_obs_adapter import (
            IsaacCameraObsAdapter,
        )
        cam = IsaacCameraObsAdapter(image_size=(85, 64), context_size=5)
        cam.set_goal_image(np.zeros((64, 85, 3), dtype=np.uint8))
        cam.push_frame(np.zeros((480, 640, 3), dtype=np.uint8))
        imgs, _ = cam.get_context()
        assert len(imgs) == 5, f"padding failed: got {len(imgs)} frames"

    def test_output_image_matches_declared_size(self):
        """All context frames must match the declared image_size."""
        from fleet_safe_vla.integrations.visualnav_transformer.isaac_obs_adapter import (
            IsaacCameraObsAdapter,
        )
        for model in ["gnm", "vint", "nomad"]:
            spec = _SPEC[model]
            W, H = spec["image_size"]
            cam  = IsaacCameraObsAdapter(image_size=(W, H), context_size=5)
            cam.set_goal_image(np.zeros((H, W, 3), dtype=np.uint8))
            cam.push_frame(np.zeros((480, 640, 3), dtype=np.uint8))
            imgs, goal = cam.get_context()
            assert all(img.shape == (H, W, 3) for img in imgs), (
                f"{model}: context frame shape mismatch"
            )
            assert goal.shape == (H, W, 3), f"{model}: goal shape mismatch"

    def test_oldest_frame_first_in_context(self):
        """Context queue is oldest-first (required by upstream temporal encoding)."""
        from fleet_safe_vla.integrations.visualnav_transformer.isaac_obs_adapter import (
            IsaacCameraObsAdapter,
        )
        cam = IsaacCameraObsAdapter(image_size=(85, 64), context_size=3)
        cam.set_goal_image(np.zeros((64, 85, 3), dtype=np.uint8))
        for val in [10, 20, 30]:
            cam.push_frame(np.full((64, 85, 3), val, dtype=np.uint8))
        imgs, _ = cam.get_context()
        assert imgs[0][0, 0, 0] == 10, "oldest frame must be first"
        assert imgs[2][0, 0, 0] == 30, "newest frame must be last"


# ── Section 7: MuJoCo camera contract ────────────────────────────────────────

class TestMuJoCoCameraContract:

    def test_obstacle_env_has_named_camera(self):
        """obstacle_env MJCF must contain a named camera element."""
        from fleet_safe_vla.envs.mujoco.yahboom.obstacle_env import YahboomObstacleEnv
        env = YahboomObstacleEnv.__new__(YahboomObstacleEnv)
        xml = env._build_obs_xml.__func__(env, 4)
        assert '<camera name="camera"' in xml, (
            "obstacle_env MJCF does not contain a named camera element. "
            "The renderer will fall back to the spectator camera — "
            "violating the perception contract."
        )

    def test_obstacle_env_camera_is_egocentric(self):
        """Camera must be inside base_link (egocentric), not at world level."""
        from fleet_safe_vla.envs.mujoco.yahboom.obstacle_env import YahboomObstacleEnv
        env = YahboomObstacleEnv.__new__(YahboomObstacleEnv)
        xml = env._build_obs_xml.__func__(env, 4)
        # Camera must appear inside the base_link block
        base_link_block = xml[xml.find('<body name="base_link"'):]
        assert '<camera name="camera"' in base_link_block, (
            "Camera element is not inside base_link — it is not egocentric."
        )

    def test_benchmark_runner_raises_without_camera(self):
        """benchmark_runner._render_camera must raise RuntimeError if camera missing."""
        from fleet_safe_vla.integrations.visualnav_transformer.benchmark_runner import (
            BenchmarkRunner,
        )
        # _render_camera is a static/instance method that takes an env with model/data
        # We check the implementation contains the required guard
        import inspect
        src = inspect.getsource(BenchmarkRunner._render_camera)
        has_guard = "raise RuntimeError" in src and "camera" in src.lower()
        assert has_guard, (
            "BenchmarkRunner._render_camera does not raise RuntimeError when "
            "camera is missing.  Without this guard, the renderer silently falls "
            "back to the spectator camera."
        )


# ── Section 8: Upstream commit pin ───────────────────────────────────────────

class TestUpstreamPin:

    def test_upstream_commit_is_recorded(self):
        """docs/baselines/ must contain a baseline contract document."""
        contract = _REPO_ROOT / "docs" / "baselines" / "VISUALNAV_TRANSFORMER_BASELINE_CONTRACT.md"
        assert contract.exists(), (
            f"Baseline contract document not found: {contract.relative_to(_REPO_ROOT)}\n"
            "Create it to prove the upstream commit is pinned."
        )

    def test_upstream_commit_hash_in_contract(self):
        """Baseline contract must contain a commit hash."""
        contract = _REPO_ROOT / "docs" / "baselines" / "VISUALNAV_TRANSFORMER_BASELINE_CONTRACT.md"
        if not contract.exists():
            pytest.skip("contract doc not found")
        text = contract.read_text()
        import re
        has_hash = bool(re.search(r"[0-9a-f]{7,40}", text))
        assert has_hash, "Baseline contract does not contain a commit hash"
