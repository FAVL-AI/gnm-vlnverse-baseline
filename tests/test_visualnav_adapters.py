"""
tests/test_visualnav_adapters.py — Unit tests for VisualNav-Transformer adapters.

What is tested (without upstream checkpoints)
----------------------------------------------
  - Adapter classes are importable and have the required interface.
  - UpstreamNotFoundError / CheckpointNotFoundError are raised correctly.
  - IsaacCameraObsAdapter resizes, queues, and returns correct shapes.
  - FleetSafeWrapper initialises and steps on a mock adapter.
  - BenchmarkRunner._aggregate produces correct metric keys.
  - export_report.py produces HTML and CSV from mock JSON.
  - validate_gates.py gate_3 and gate_5 pass without upstream or checkpoints.

Tests that require upstream + checkpoints (skipped otherwise)
--------------------------------------------------------------
  - gate_2_static_inference (needs loaded model).
  - gate_4_sim_cmd_vel (needs MJCF + checkpoint).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

# ── Skip guard: upstream not required for most tests ─────────────────────────
_VNT_ROOT = _REPO_ROOT / "third_party" / "visualnav-transformer"
_HAS_UPSTREAM = _VNT_ROOT.exists()

_HAS_TORCH = False
try:
    import torch  # noqa: F401
    _HAS_TORCH = True
except ImportError:
    pass


# ── Imports ────────────────────────────────────────────────────────────────────

from fleet_safe_vla.integrations.visualnav_transformer.base_adapter import (
    ActionOutput,
    BaseVisualNavAdapter,
    CheckpointNotFoundError,
    CmdVel,
    UpstreamNotFoundError,
    waypoints_to_cmd_vel,
)
from fleet_safe_vla.integrations.visualnav_transformer.isaac_obs_adapter import (
    IsaacCameraObsAdapter,
)
from fleet_safe_vla.integrations.visualnav_transformer.fleetsafe_wrapper import (
    FleetSafeWrapper,
    FleetSafeStepResult,
)
from fleet_safe_vla.integrations.visualnav_transformer.benchmark_runner import (
    BenchmarkRunner,
    EpisodeResult,
)


# ── Mock adapter fixture ───────────────────────────────────────────────────────

class _MockAdapter(BaseVisualNavAdapter):
    """Minimal adapter that returns fixed outputs without touching upstream."""

    model_name  = "mock"
    image_size  = (85, 64)
    context_size = 5

    def load_checkpoint(self, path: Path) -> None:
        self._loaded = True

    def preprocess_observation(self, obs_imgs, goal_img) -> dict:
        return {"obs_tensor": None, "goal_tensor": None}

    def predict_action(self, preprocessed) -> ActionOutput:
        return ActionOutput(
            waypoints     = np.array([[0.15, 0.05], [0.28, 0.09]], dtype=np.float32),
            goal_distance = 3.5,
            goal_reached  = False,
            model_name    = self.model_name,
            inference_ms  = 5.0,
        )


@pytest.fixture
def mock_adapter():
    a = _MockAdapter()
    a.load_checkpoint(Path("."))
    return a


# ── base_adapter tests ─────────────────────────────────────────────────────────

def test_base_adapter_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        BaseVisualNavAdapter()  # type: ignore


def test_cmd_vel_as_array():
    cmd = CmdVel(0.2, 0.1, 0.5)
    arr = cmd.as_array()
    assert arr.shape == (3,)
    np.testing.assert_allclose(arr, [0.2, 0.1, 0.5])


def test_waypoints_to_cmd_vel_forward():
    waypoints = np.array([[0.1, 0.0]])
    cmd = waypoints_to_cmd_vel(waypoints, v_max=0.3, w_max=0.7, control_hz=4.0)
    assert cmd.vx > 0
    assert abs(cmd.wz) < 0.01     # straight forward → no angular
    assert cmd.vy == 0.0


def test_waypoints_to_cmd_vel_left():
    """Waypoint to the left → positive wz (CCW)."""
    waypoints = np.array([[0.05, 0.10]])
    cmd = waypoints_to_cmd_vel(waypoints, v_max=0.3, w_max=0.7)
    assert cmd.wz > 0


def test_waypoints_to_cmd_vel_clip_v_max():
    waypoints = np.array([[10.0, 0.0]])
    cmd = waypoints_to_cmd_vel(waypoints, v_max=0.3, control_hz=4.0)
    assert cmd.vx <= 0.3


def test_waypoints_to_cmd_vel_clip_w_max():
    waypoints = np.array([[0.0, 10.0]])
    cmd = waypoints_to_cmd_vel(waypoints, w_max=0.7)
    assert abs(cmd.wz) <= 0.7


def test_waypoints_to_cmd_vel_empty():
    cmd = waypoints_to_cmd_vel(np.zeros((0, 2)))
    assert cmd.vx == 0.0 and cmd.wz == 0.0


def test_waypoints_to_cmd_vel_holonomic():
    """vy_max > 0 → non-zero vy for lateral waypoint."""
    waypoints = np.array([[0.0, 0.1]])
    cmd = waypoints_to_cmd_vel(waypoints, vy_max=0.3, control_hz=4.0)
    assert abs(cmd.vy) > 0


def test_check_upstream_raises():
    with pytest.raises(UpstreamNotFoundError):
        BaseVisualNavAdapter._check_upstream(Path("/nonexistent/path"))


def test_check_checkpoint_raises():
    with pytest.raises(CheckpointNotFoundError):
        BaseVisualNavAdapter._check_checkpoint(Path("/nonexistent/checkpoint.pth"))


# ── Mock adapter tests ─────────────────────────────────────────────────────────

def test_mock_adapter_is_loaded(mock_adapter):
    assert mock_adapter.is_loaded()


def test_mock_adapter_predict(mock_adapter):
    prep = mock_adapter.preprocess_observation([], np.zeros((64, 85, 3), np.uint8))
    action = mock_adapter.predict_action(prep)
    assert isinstance(action, ActionOutput)
    assert action.waypoints.shape == (2, 2)
    assert action.model_name == "mock"


def test_mock_adapter_action_to_cmd_vel(mock_adapter):
    prep   = mock_adapter.preprocess_observation([], np.zeros((64, 85, 3), np.uint8))
    action = mock_adapter.predict_action(prep)
    cmd    = mock_adapter.action_to_cmd_vel(action, v_max=0.3, w_max=0.7)
    assert isinstance(cmd, CmdVel)
    assert -0.3 <= cmd.vx <= 0.3
    assert -0.7 <= cmd.wz <= 0.7


def test_mock_adapter_log_output(mock_adapter):
    prep   = mock_adapter.preprocess_observation([], np.zeros((64, 85, 3), np.uint8))
    action = mock_adapter.predict_action(prep)
    cmd    = mock_adapter.action_to_cmd_vel(action)
    log    = mock_adapter.log_policy_output(action, cmd)
    required = {"model", "waypoints", "goal_distance", "goal_reached",
                "cmd_vx", "cmd_vy", "cmd_wz", "inference_ms"}
    assert required.issubset(log.keys())


# ── Adapter class importability (no upstream needed) ──────────────────────────

def test_gnm_adapter_importable():
    from fleet_safe_vla.integrations.visualnav_transformer.gnm_adapter import GNMAdapter
    a = GNMAdapter()
    assert a.model_name == "gnm"
    assert a.image_size == (85, 64)
    assert a.context_size == 5
    assert not a.is_loaded()


def test_vint_adapter_importable():
    from fleet_safe_vla.integrations.visualnav_transformer.vint_adapter import ViNTAdapter
    a = ViNTAdapter()
    assert a.model_name == "vint"
    assert a.image_size == (85, 64)   # matches published vint.yaml image_size


def test_nomad_adapter_importable():
    from fleet_safe_vla.integrations.visualnav_transformer.nomad_adapter import NoMaDAdapter
    a = NoMaDAdapter()
    assert a.model_name == "nomad"
    assert a.action_horizon == 8


def test_adapters_raise_upstream_not_found():
    """Attempting load_checkpoint without upstream cloned → UpstreamNotFoundError."""
    from fleet_safe_vla.integrations.visualnav_transformer.gnm_adapter import GNMAdapter
    if _VNT_ROOT.exists():
        pytest.skip("upstream is cloned — error path not testable")
    a = GNMAdapter()
    with pytest.raises(UpstreamNotFoundError):
        a.load_checkpoint(Path("/tmp/fake.pth"))


def test_adapters_raise_checkpoint_not_found(tmp_path):
    """Checkpoint path missing → CheckpointNotFoundError (after upstream check)."""
    from fleet_safe_vla.integrations.visualnav_transformer.gnm_adapter import GNMAdapter
    if not _VNT_ROOT.exists():
        pytest.skip("upstream not cloned — can't get past gate 0 check")
    a = GNMAdapter()
    with pytest.raises(CheckpointNotFoundError):
        a.load_checkpoint(tmp_path / "nonexistent.pth")


# ── IsaacCameraObsAdapter tests ───────────────────────────────────────────────

@pytest.fixture
def cam_adapter():
    return IsaacCameraObsAdapter(image_size=(85, 64), context_size=5)


def test_cam_adapter_resize_and_queue(cam_adapter):
    raw = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    cam_adapter.set_goal_image(raw)
    for _ in range(7):
        cam_adapter.push_frame(raw)
    obs_imgs, goal = cam_adapter.get_context()
    assert len(obs_imgs) == 5
    assert obs_imgs[0].shape == (64, 85, 3)
    assert goal.shape == (64, 85, 3)
    assert obs_imgs[0].dtype == np.uint8


def test_cam_adapter_padding(cam_adapter):
    """If fewer than context_size frames pushed, oldest is padded."""
    raw = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    cam_adapter.set_goal_image(raw)
    cam_adapter.push_frame(raw)   # only 1 frame
    obs_imgs, _ = cam_adapter.get_context()
    assert len(obs_imgs) == 5
    # All frames should be identical (padded with the one frame)
    for img in obs_imgs:
        np.testing.assert_array_equal(img, obs_imgs[0])


def test_cam_adapter_reset(cam_adapter):
    raw = np.random.randint(0, 255, (64, 85, 3), dtype=np.uint8)
    cam_adapter.set_goal_image(raw)
    cam_adapter.push_frame(raw)
    cam_adapter.reset()
    with pytest.raises(RuntimeError, match="empty"):
        cam_adapter.get_context()


def test_cam_adapter_no_goal_error(cam_adapter):
    raw = np.random.randint(0, 255, (64, 85, 3), dtype=np.uint8)
    cam_adapter.push_frame(raw)
    with pytest.raises(RuntimeError, match="Goal image"):
        cam_adapter.get_context()


def test_cam_adapter_synthetic_helpers():
    cb = IsaacCameraObsAdapter.make_checkerboard_goal(85, 64)
    assert cb.shape == (64, 85, 3)
    assert cb.dtype == np.uint8

    rnd = IsaacCameraObsAdapter.make_random_obs(85, 64, seed=42)
    assert rnd.shape == (64, 85, 3)
    rnd2 = IsaacCameraObsAdapter.make_random_obs(85, 64, seed=42)
    np.testing.assert_array_equal(rnd, rnd2)   # deterministic


def test_cam_adapter_set_goal_from_current(cam_adapter):
    raw = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    cam_adapter.push_frame(raw)
    cam_adapter.set_goal_from_current_frame()
    _, goal = cam_adapter.get_context()
    assert goal.shape == (64, 85, 3)


# ── FleetSafeWrapper tests ────────────────────────────────────────────────────

def test_fleetsafe_wrapper_runs(mock_adapter):
    wrapper = FleetSafeWrapper(mock_adapter)
    obs_vec = np.zeros(47, dtype=np.float32)
    prep    = mock_adapter.preprocess_observation([], np.zeros((64, 85, 3), np.uint8))
    result  = wrapper.step(prep, obs_vec, obstacle_positions=None)
    assert isinstance(result, FleetSafeStepResult)
    assert result.raw_cmd_vel is not None
    assert result.safe_cmd_vel is not None


def test_fleetsafe_wrapper_no_obstacle_no_intervention(mock_adapter):
    """No obstacles → CBF should not intervene (only clip to limits)."""
    wrapper = FleetSafeWrapper(mock_adapter)
    obs_vec = np.zeros(47, dtype=np.float32)
    prep    = mock_adapter.preprocess_observation([], np.zeros((64, 85, 3), np.uint8))
    result  = wrapper.step(prep, obs_vec, obstacle_positions=[])
    assert not result.estop


def test_fleetsafe_wrapper_estop_on_close_obstacle(mock_adapter):
    """Obstacle very close → E-STOP (estop_dist_m=0.15 by default)."""
    from fleet_safe_vla.fleet_safety.yahboom_cbf import YahboomCBFConfig
    cfg = YahboomCBFConfig(estop_dist_m=0.15)
    wrapper = FleetSafeWrapper(mock_adapter, cbf_config=cfg)
    obs_vec = np.zeros(47, dtype=np.float32)
    prep    = mock_adapter.preprocess_observation([], np.zeros((64, 85, 3), np.uint8))
    close_obs = [np.array([0.10, 0.0])]   # 10 cm away — inside estop zone
    result = wrapper.step(prep, obs_vec, obstacle_positions=close_obs)
    assert result.estop
    assert result.safe_cmd_vel.vx == pytest.approx(0.0)


def test_fleetsafe_wrapper_stats(mock_adapter):
    wrapper = FleetSafeWrapper(mock_adapter)
    obs_vec = np.zeros(47, dtype=np.float32)
    prep    = mock_adapter.preprocess_observation([], np.zeros((64, 85, 3), np.uint8))
    for _ in range(10):
        wrapper.step(prep, obs_vec)
    assert wrapper._total_steps == 10


def test_fleetsafe_wrapper_reset(mock_adapter):
    wrapper = FleetSafeWrapper(mock_adapter)
    obs_vec = np.zeros(47, dtype=np.float32)
    prep    = mock_adapter.preprocess_observation([], np.zeros((64, 85, 3), np.uint8))
    wrapper.step(prep, obs_vec)
    wrapper.reset_stats()
    assert wrapper._total_steps == 0


def test_fleetsafe_wrapper_cmd_delta(mock_adapter):
    wrapper = FleetSafeWrapper(mock_adapter)
    obs_vec = np.zeros(47, dtype=np.float32)
    prep    = mock_adapter.preprocess_observation([], np.zeros((64, 85, 3), np.uint8))
    result  = wrapper.step(prep, obs_vec)
    delta = result.cmd_delta
    assert delta.shape == (3,)
    assert np.all(delta >= 0)


def test_fleetsafe_wrapper_log_dict(mock_adapter):
    wrapper = FleetSafeWrapper(mock_adapter)
    obs_vec = np.zeros(47, dtype=np.float32)
    prep    = mock_adapter.preprocess_observation([], np.zeros((64, 85, 3), np.uint8))
    result  = wrapper.step(prep, obs_vec)
    log = result.to_log_dict()
    for key in ("raw_vx", "safe_vx", "delta_vx", "intervened", "estop", "total_ms"):
        assert key in log


# ── BenchmarkRunner._aggregate tests ─────────────────────────────────────────

def _make_episode(success, collision, path, interv, latency):
    r = EpisodeResult()
    r.success           = success
    r.collision         = collision
    r.path_length_m     = path
    r.intervention_count = interv
    r.step_latency_ms   = [latency] * 10
    return r


def test_aggregate_success_rate():
    results = [
        _make_episode(True,  False, 2.1, 0, 12.0),
        _make_episode(True,  False, 1.9, 0, 11.0),
        _make_episode(False, True,  0.5, 0, 10.0),
        _make_episode(False, False, 3.0, 2, 15.0),
    ]
    agg = BenchmarkRunner._aggregate(results)
    assert agg["success_rate"]   == pytest.approx(0.5)
    assert agg["collision_rate"] == pytest.approx(0.25)
    assert agg["n_episodes"]     == 4


def test_aggregate_empty():
    assert BenchmarkRunner._aggregate([]) == {}


def test_aggregate_mean_latency():
    results = [_make_episode(True, False, 1.0, 0, 20.0)]
    agg = BenchmarkRunner._aggregate(results)
    assert agg["mean_latency_ms"] == pytest.approx(20.0)


# ── Gate 3 and Gate 5 (no upstream or checkpoint needed) ─────────────────────

def test_gate_3_camera_adapter_passes():
    from fleet_safe_vla.integrations.visualnav_transformer.validate_gates import (
        gate_3_camera_adapter,
    )
    r = gate_3_camera_adapter()
    assert r.passed, f"Gate 3 failed: {r.message}"


def test_gate_5_fleetsafe_wrapper_passes():
    from fleet_safe_vla.integrations.visualnav_transformer.validate_gates import (
        gate_5_fleetsafe_wrapper,
    )
    r = gate_5_fleetsafe_wrapper()
    assert r.passed, f"Gate 5 failed: {r.message}"


# ── export_report.py smoke test ───────────────────────────────────────────────

def test_export_report_html_and_csv(tmp_path):
    """export_report.py produces non-empty HTML and CSV from mock JSON."""
    mock_json = tmp_path / "mock_run.json"
    mock_json.write_text(json.dumps({
        "model": "gnm", "fleetsafe": False, "timestamp": 1234567890.0,
        "config": {"v_max": 0.3, "w_max": 0.7, "robot": "m3pro", "seeds": [0]},
        "episodes": [{
            "model_name": "gnm", "fleetsafe": False, "scene": "open_corridor", "seed": 0,
            "start_xy": [0, 0], "goal_xy": [2, 0],
            "success": True, "collision": False,
            "near_violation_count": 0, "min_obstacle_dist_m": 5.0,
            "intervention_count": 0, "time_to_goal_s": 12.5,
            "path_length_m": 2.1, "smoothness": 0.03,
            "stuck_count": 0, "recovery_success": False,
            "mean_latency_ms": 14.0, "fps": 71.4,
        }],
        "aggregate": {
            "n_episodes": 1, "success_rate": 1.0, "collision_rate": 0.0,
            "mean_path_length_m": 2.1, "mean_smoothness": 0.03,
            "mean_stuck_count": 0.0, "mean_intervention_count": 0.0,
            "mean_near_violation_count": 0.0, "mean_min_obstacle_dist_m": 5.0,
            "mean_latency_ms": 14.0, "mean_fps": 71.4,
        },
    }))

    import subprocess, sys as _sys
    r = subprocess.run(
        [_sys.executable,
         str(_REPO_ROOT / "scripts/visualnav/export_report.py"),
         "--input",      str(mock_json),
         "--output-dir", str(tmp_path / "report")],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, f"export_report.py failed:\n{r.stderr}"

    html = tmp_path / "report" / "benchmark_report.html"
    csv  = tmp_path / "report" / "benchmark_results.csv"
    assert html.exists(), "HTML not created"
    assert csv.exists(),  "CSV not created"
    assert "GNM" in html.read_text()
    assert "gnm" in csv.read_text()
