"""
tests/test_runner_perception.py — Tests for perception layer wired into VisualNavBenchmarkRunner.

Covers:
- _PerceptionLayer construction for all three modes
- episode_summary() structure and defaults
- EpisodeMetrics new perception fields
- Runner accepts perception= parameter and validates values
- Mock episode with perception="mock" produces non-zero detection counts
- Mock episode with perception="none" produces zero perception metrics
"""
from __future__ import annotations

import pytest

from fleet_safe_vla.benchmarks.visualnav_runner import (
    _PerceptionLayer,
    PERCEPTION_NONE,
    PERCEPTION_MOCK,
    PERCEPTION_YOLO,
    VisualNavBenchmarkRunner,
    BACKEND_MOCK,
)
from fleet_safe_vla.benchmarks.visualnav_metrics import EpisodeMetrics
from fleet_safe_vla.social_awareness.dynamic_agent_tracker import AgentType, Detection


# ── _PerceptionLayer ───────────────────────────────────────────────────────────

class TestPerceptionLayer:

    def test_none_mode_tracker_is_none(self):
        layer = _PerceptionLayer(mode=PERCEPTION_NONE, scene_name="hospital_corridor")
        assert layer._tracker is None

    def test_mock_mode_has_tracker(self):
        layer = _PerceptionLayer(mode=PERCEPTION_MOCK, scene_name="hospital_corridor")
        assert layer._tracker is not None

    def test_mock_mode_has_mock_src(self):
        layer = _PerceptionLayer(mode=PERCEPTION_MOCK, scene_name="hospital_corridor")
        assert layer._mock_src is not None

    def test_yolo_mode_has_tracker(self):
        layer = _PerceptionLayer(mode=PERCEPTION_YOLO, scene_name="hospital_corridor")
        assert layer._tracker is not None

    def test_yolo_mode_has_pipeline(self):
        layer = _PerceptionLayer(mode=PERCEPTION_YOLO, scene_name="hospital_corridor")
        assert layer._pipeline is not None

    def test_step_none_mode_returns_empty(self):
        layer = _PerceptionLayer(mode=PERCEPTION_NONE, scene_name="x")
        dets = layer.step(rgb_frame=None, depth_image=None, robot_xy=(0, 0), timestamp=0.0)
        assert dets == []

    def test_step_mock_mode_returns_detections(self):
        layer = _PerceptionLayer(mode=PERCEPTION_MOCK, scene_name="hospital_corridor", seed=0)
        dets = layer.step(rgb_frame=None, depth_image=None, robot_xy=(0, 0), timestamp=0.0)
        assert isinstance(dets, list)
        assert len(dets) > 0
        assert all(isinstance(d, Detection) for d in dets)

    def test_tracked_detections_after_mock_step(self):
        layer = _PerceptionLayer(mode=PERCEPTION_MOCK, scene_name="hospital_corridor", seed=0)
        layer.step(rgb_frame=None, depth_image=None, robot_xy=(0, 0), timestamp=0.0)
        tracked = layer.tracked_detections(robot_xy=(0, 0), timestamp=0.0)
        assert isinstance(tracked, list)
        # All tracked items are Detection objects
        assert all(isinstance(d, Detection) for d in tracked)

    def test_tracked_detections_none_mode_returns_empty(self):
        layer = _PerceptionLayer(mode=PERCEPTION_NONE, scene_name="x")
        result = layer.tracked_detections((0, 0), 0.0)
        assert result == []

    def test_no_double_tracker_update(self):
        """tracked_detections() must use cached result, not call tracker.update() again."""
        layer = _PerceptionLayer(mode=PERCEPTION_MOCK, scene_name="hospital_corridor", seed=1)
        layer.step(None, None, (0, 0), 0.0)
        before = layer._last_tracked
        layer.tracked_detections((0, 0), 0.0)
        # _last_tracked must not change (no second update call)
        assert layer._last_tracked is before

    # ── episode_summary ───────────────────────────────────────────────────────

    def test_summary_none_mode_has_source_key(self):
        layer = _PerceptionLayer(mode=PERCEPTION_NONE, scene_name="x")
        s = layer.episode_summary()
        assert s["perception_source"] == PERCEPTION_NONE

    def test_summary_mock_mode_has_all_keys(self):
        layer = _PerceptionLayer(mode=PERCEPTION_MOCK, scene_name="hospital_corridor")
        layer.step(None, None, (0, 0), 0.0)
        s = layer.episode_summary()
        for k in [
            "perception_source", "detection_count_total", "tracked_agent_count_max",
            "perception_latency_ms_mean", "perception_latency_ms_p95",
            "depth_fusion_latency_ms_mean", "semantic_role_counts",
        ]:
            assert k in s, f"Missing key: {k}"

    def test_summary_detection_count_accumulates(self):
        layer = _PerceptionLayer(mode=PERCEPTION_MOCK, scene_name="hospital_corridor", seed=0)
        for i in range(5):
            layer.step(None, None, (0, 0), float(i) * 0.1)
        s = layer.episode_summary()
        # hospital_corridor has 2 agents × 5 steps = 10 detections
        assert s["detection_count_total"] == 10

    def test_summary_role_counts_non_empty_after_mock(self):
        layer = _PerceptionLayer(mode=PERCEPTION_MOCK, scene_name="hospital_corridor", seed=0)
        layer.step(None, None, (0, 0), 0.0)
        s = layer.episode_summary()
        assert len(s["semantic_role_counts"]) > 0

    def test_summary_max_tracks_gte_zero(self):
        layer = _PerceptionLayer(mode=PERCEPTION_MOCK, scene_name="hospital_corridor", seed=0)
        layer.step(None, None, (0, 0), 0.0)
        s = layer.episode_summary()
        assert s["tracked_agent_count_max"] >= 0

    def test_summary_latency_non_negative(self):
        layer = _PerceptionLayer(mode=PERCEPTION_MOCK, scene_name="hospital_corridor", seed=0)
        layer.step(None, None, (0, 0), 0.0)
        s = layer.episode_summary()
        assert s["perception_latency_ms_mean"] >= 0.0
        assert s["perception_latency_ms_p95"] >= 0.0

    def test_scene_mapping_waiting_room(self):
        layer = _PerceptionLayer(mode=PERCEPTION_MOCK,
                                  scene_name="hospital_elevator_lobby", seed=0)
        dets = layer.step(None, None, (0, 0), 0.0)
        roles = {d.semantic_role for d in dets}
        assert "wheelchair_user" in roles

    def test_unknown_scene_falls_back_to_corridor(self):
        layer = _PerceptionLayer(mode=PERCEPTION_MOCK, scene_name="unknown_xyz", seed=0)
        dets = layer.step(None, None, (0, 0), 0.0)
        assert len(dets) > 0  # corridor has 2 agents


# ── EpisodeMetrics new fields ─────────────────────────────────────────────────

class TestEpisodeMetricsPerceptionFields:

    def test_default_perception_source_is_none(self):
        em = EpisodeMetrics()
        assert em.perception_source == "none"

    def test_default_detection_count_zero(self):
        em = EpisodeMetrics()
        assert em.detection_count_total == 0

    def test_default_tracked_agent_count_zero(self):
        em = EpisodeMetrics()
        assert em.tracked_agent_count_max == 0

    def test_default_perception_latency_zero(self):
        em = EpisodeMetrics()
        assert em.perception_latency_ms_mean == 0.0
        assert em.perception_latency_ms_p95 == 0.0

    def test_default_depth_fusion_latency_zero(self):
        em = EpisodeMetrics()
        assert em.depth_fusion_latency_ms_mean == 0.0

    def test_default_semantic_role_counts_empty(self):
        em = EpisodeMetrics()
        assert em.semantic_role_counts == {}

    def test_can_set_perception_fields(self):
        em = EpisodeMetrics(
            perception_source="mock",
            detection_count_total=42,
            tracked_agent_count_max=3,
            perception_latency_ms_mean=1.5,
            semantic_role_counts={"staff": 10, "patient": 32},
        )
        assert em.perception_source == "mock"
        assert em.detection_count_total == 42
        assert em.tracked_agent_count_max == 3
        assert em.semantic_role_counts["staff"] == 10


# ── Runner integration ────────────────────────────────────────────────────────

class TestRunnerPerceptionParam:

    def _make_adapter(self):
        from fleet_safe_vla.integrations.visualnav_transformer.base_adapter import (
            BaseVisualNavAdapter,
            CmdVel,
        )
        import numpy as np

        class _Stub(BaseVisualNavAdapter):
            model_name  = "stub"
            context_size = 1
            image_size   = (85, 64)
            def load_checkpoint(self, path): pass
            def preprocess_observation(self, obs_imgs, goal_img): return obs_imgs
            def predict_action(self, obs): return np.zeros(2, dtype=np.float32)
            def action_to_cmd_vel(self, action, **kw): return CmdVel(0.0, 0.0, 0.0)

        return _Stub()

    def test_runner_accepts_perception_none(self):
        runner = VisualNavBenchmarkRunner(
            self._make_adapter(), backend=BACKEND_MOCK, perception=PERCEPTION_NONE
        )
        assert runner.perception == PERCEPTION_NONE

    def test_runner_accepts_perception_mock(self):
        runner = VisualNavBenchmarkRunner(
            self._make_adapter(), backend=BACKEND_MOCK, perception=PERCEPTION_MOCK
        )
        assert runner.perception == PERCEPTION_MOCK

    def test_runner_accepts_perception_yolo(self):
        runner = VisualNavBenchmarkRunner(
            self._make_adapter(), backend=BACKEND_MOCK, perception=PERCEPTION_YOLO
        )
        assert runner.perception == PERCEPTION_YOLO

    def test_runner_rejects_unknown_perception(self):
        with pytest.raises(ValueError, match="Unknown perception mode"):
            VisualNavBenchmarkRunner(
                self._make_adapter(), backend=BACKEND_MOCK, perception="lidar"
            )

    def test_make_perception_layer_none(self):
        runner = VisualNavBenchmarkRunner(
            self._make_adapter(), backend=BACKEND_MOCK, perception=PERCEPTION_NONE
        )
        layer = runner._make_perception_layer("hospital_corridor", seed=0)
        assert layer.mode == PERCEPTION_NONE
        assert layer._tracker is None

    def test_make_perception_layer_mock(self):
        runner = VisualNavBenchmarkRunner(
            self._make_adapter(), backend=BACKEND_MOCK, perception=PERCEPTION_MOCK
        )
        layer = runner._make_perception_layer("hospital_corridor", seed=42)
        assert layer.mode == PERCEPTION_MOCK
        assert layer._tracker is not None


class TestRunnerMockEpisodeWithPerception:
    """Run a very short mock episode and verify perception fields in metrics."""

    def _make_runner(self, perception=PERCEPTION_NONE):
        from fleet_safe_vla.integrations.visualnav_transformer.base_adapter import (
            BaseVisualNavAdapter, CmdVel,
        )
        import numpy as np

        class _Stub(BaseVisualNavAdapter):
            model_name  = "stub"
            context_size = 1
            image_size   = (85, 64)
            def load_checkpoint(self, path): pass
            def preprocess_observation(self, obs_imgs, goal_img): return obs_imgs
            def predict_action(self, obs): return np.zeros(2, dtype=np.float32)
            def action_to_cmd_vel(self, action, **kw): return CmdVel(0.1, 0.0, 0.0)

        return VisualNavBenchmarkRunner(
            _Stub(), backend=BACKEND_MOCK, perception=perception, max_steps=10
        )

    def _run_short(self, perception):
        import tempfile, pathlib
        from fleet_safe_vla.benchmarks.visualnav_scenarios import (
            SceneSpec, StartGoalPair,
        )
        runner = self._make_runner(perception)
        scene = SceneSpec(
            name="hospital_corridor",
            description="test scene",
            arena_size_m=10.0,
            start_goal_pairs=[StartGoalPair((0.0, 0.0), (2.0, 0.0))],
        )
        with tempfile.TemporaryDirectory() as td:
            runner.output_dir = pathlib.Path(td)
            metrics_list = runner.run([scene], seeds=[0])
        return metrics_list[0]

    def test_perception_none_source_field(self):
        m = self._run_short(PERCEPTION_NONE)
        assert m.perception_source == PERCEPTION_NONE

    def test_perception_none_detection_count_zero(self):
        m = self._run_short(PERCEPTION_NONE)
        assert m.detection_count_total == 0

    def test_perception_mock_source_field(self):
        m = self._run_short(PERCEPTION_MOCK)
        assert m.perception_source == PERCEPTION_MOCK

    def test_perception_mock_detection_count_nonzero(self):
        m = self._run_short(PERCEPTION_MOCK)
        # 10 steps × 2 agents in hospital_corridor = 20 detections
        assert m.detection_count_total > 0

    def test_perception_mock_role_counts_populated(self):
        m = self._run_short(PERCEPTION_MOCK)
        assert len(m.semantic_role_counts) > 0

    def test_perception_mock_latency_nonnegative(self):
        m = self._run_short(PERCEPTION_MOCK)
        assert m.perception_latency_ms_mean >= 0.0

    def test_perception_mock_tracked_count_nonnegative(self):
        m = self._run_short(PERCEPTION_MOCK)
        assert m.tracked_agent_count_max >= 0
