"""
tests/test_perception.py — unit tests for fleet_safe_vla.perception

All tests run without ultralytics, numpy, or real camera hardware.
"""
from __future__ import annotations

import math
import sys
import types
import pytest

from fleet_safe_vla.social_awareness.dynamic_agent_tracker import AgentType, Detection


# ══════════════════════════════════════════════════════════════════════════════
# RoleClassifier
# ══════════════════════════════════════════════════════════════════════════════

class TestRoleClassifier:
    def _make(self, extra=None):
        from fleet_safe_vla.perception.semantic_detector import RoleClassifier
        return RoleClassifier(extra_rules=extra)

    def test_person_maps_to_patient(self):
        rc = self._make()
        role, atype = rc.classify("person")
        assert role == "patient"
        assert atype == AgentType.HUMAN

    def test_nurse_maps_to_staff(self):
        rc = self._make()
        role, atype = rc.classify("nurse")
        assert role == "staff"
        assert atype == AgentType.HUMAN

    def test_doctor_maps_to_staff(self):
        rc = self._make()
        role, atype = rc.classify("doctor")
        assert role == "staff"

    def test_wheelchair_user(self):
        rc = self._make()
        role, atype = rc.classify("wheelchair_user")
        assert role == "wheelchair_user"
        assert atype == AgentType.HUMAN

    def test_wheelchair_fragment(self):
        rc = self._make()
        role, _ = rc.classify("wheelchair")
        assert role == "wheelchair_user"

    def test_gurney(self):
        rc = self._make()
        role, _ = rc.classify("gurney")
        assert role == "gurney"

    def test_stretcher_maps_to_gurney(self):
        rc = self._make()
        role, _ = rc.classify("stretcher")
        assert role == "gurney"

    def test_robot_class(self):
        rc = self._make()
        role, atype = rc.classify("robot")
        assert role == "robot"
        assert atype == AgentType.ROBOT

    def test_unknown_class(self):
        rc = self._make()
        role, atype = rc.classify("cat")
        assert role == "unknown"
        assert atype == AgentType.UNKNOWN

    def test_case_insensitive(self):
        rc = self._make()
        role, _ = rc.classify("NURSE")
        assert role == "staff"

    def test_extra_rules_take_priority(self):
        from fleet_safe_vla.perception.semantic_detector import RoleClassifier
        extra = [("person", "visitor", AgentType.HUMAN)]
        rc = RoleClassifier(extra_rules=extra)
        role, _ = rc.classify("person")
        assert role == "visitor"

    def test_visitor_class(self):
        rc = self._make()
        role, atype = rc.classify("visitor")
        assert role == "visitor"
        assert atype == AgentType.HUMAN


# ══════════════════════════════════════════════════════════════════════════════
# DetectionResult
# ══════════════════════════════════════════════════════════════════════════════

class TestDetectionResult:
    def _make_det(self, **kw):
        from fleet_safe_vla.perception.semantic_detector import DetectionResult
        defaults = dict(
            bbox_xyxy=(10.0, 20.0, 50.0, 80.0),
            class_name="nurse",
            confidence=0.87,
            semantic_role="staff",
            agent_type=AgentType.HUMAN,
            timestamp=1.5,
        )
        defaults.update(kw)
        return DetectionResult(**defaults)

    def test_center_xy_px(self):
        det = self._make_det(bbox_xyxy=(10.0, 20.0, 50.0, 80.0))
        cx, cy = det.center_xy_px
        assert cx == 30.0
        assert cy == 50.0

    def test_to_detection(self):
        det = self._make_det(position_xy=(1.5, -0.3), confidence=0.87, timestamp=2.0)
        d = det.to_detection()
        assert isinstance(d, Detection)
        assert d.position_xy == (1.5, -0.3)
        assert d.agent_type == AgentType.HUMAN
        assert d.confidence == pytest.approx(0.87)
        assert d.semantic_role == "staff"
        assert d.timestamp == pytest.approx(2.0)

    def test_default_position_xy(self):
        det = self._make_det()
        assert det.position_xy == (0.0, 0.0)

    def test_track_id_none_by_default(self):
        det = self._make_det()
        assert det.track_id is None


# ══════════════════════════════════════════════════════════════════════════════
# SemanticDetector — stub (no ultralytics)
# ══════════════════════════════════════════════════════════════════════════════

class TestSemanticDetectorStub:
    def _make(self, model_path="yolov8n.pt"):
        from fleet_safe_vla.perception.semantic_detector import SemanticDetector
        return SemanticDetector(model_path=model_path)

    def test_disabled_when_no_ultralytics(self):
        det = self._make()
        # ultralytics not installed in test env → should be disabled
        assert not det.enabled

    def test_detect_returns_empty_when_disabled(self):
        det = self._make()
        result = det.detect(None, timestamp=0.0)
        assert result == []

    def test_detect_returns_empty_for_none_frame(self):
        det = self._make()
        result = det.detect(None)
        assert result == []

    def test_disabled_when_model_path_none(self):
        from fleet_safe_vla.perception.semantic_detector import SemanticDetector
        det = SemanticDetector(model_path=None)
        assert not det.enabled

    def test_detect_empty_for_no_model(self):
        from fleet_safe_vla.perception.semantic_detector import SemanticDetector
        det = SemanticDetector(model_path=None)
        assert det.detect(object()) == []


# ══════════════════════════════════════════════════════════════════════════════
# DepthFusion
# ══════════════════════════════════════════════════════════════════════════════

class TestDepthFusion:
    def _make(self, **kw):
        from fleet_safe_vla.perception.depth_fusion import CameraIntrinsics, DepthFusion
        ci = CameraIntrinsics(fx=615.0, fy=615.0, cx=320.0, cy=240.0)
        return DepthFusion(intrinsics=ci, **kw)

    def test_pixel_to_world_no_numpy_returns_none_or_value(self):
        fusion = self._make()
        # With numpy absent, should either return None or a value without crashing
        try:
            import numpy as np
            depth = np.zeros((480, 640), dtype=np.uint16)
            depth[240, 320] = 2000  # 2.0 m
            result = fusion.pixel_to_world(320.0, 240.0, depth)
            assert result is not None
            x, y = result
            assert abs(x - 2.0) < 0.1  # ~2 m forward
            assert abs(y) < 0.1         # ~centre → ~0 left
        except ImportError:
            result = fusion.pixel_to_world(320.0, 240.0, None)
            assert result is None

    def test_rejects_zero_depth(self):
        try:
            import numpy as np
        except ImportError:
            pytest.skip("numpy required")
        fusion = self._make()
        depth = np.zeros((480, 640), dtype=np.uint16)
        result = fusion.pixel_to_world(320, 240, depth)
        assert result is None

    def test_rejects_beyond_max_depth(self):
        try:
            import numpy as np
        except ImportError:
            pytest.skip("numpy required")
        fusion = self._make(max_depth_m=3.0)
        depth = np.zeros((480, 640), dtype=np.uint16)
        depth[235:245, 315:325] = 5000  # 5.0 m — beyond max
        result = fusion.pixel_to_world(320, 240, depth)
        assert result is None

    def test_fill_positions_no_depth_leaves_zeros(self):
        from fleet_safe_vla.perception.semantic_detector import DetectionResult
        fusion = self._make()
        det = DetectionResult(
            bbox_xyxy=(100.0, 100.0, 200.0, 200.0),
            class_name="person",
            confidence=0.8,
            semantic_role="patient",
            agent_type=AgentType.HUMAN,
        )
        result = fusion.fill_positions([det], depth_image=None)
        assert result[0].position_xy == (0.0, 0.0)

    def test_fill_positions_returns_same_list(self):
        from fleet_safe_vla.perception.semantic_detector import DetectionResult
        fusion = self._make()
        dets = [DetectionResult(
            bbox_xyxy=(100.0, 100.0, 200.0, 200.0),
            class_name="person",
            confidence=0.8,
            semantic_role="patient",
            agent_type=AgentType.HUMAN,
        )]
        returned = fusion.fill_positions(dets, depth_image=None)
        assert returned is dets

    def test_left_of_centre_gives_positive_y(self):
        """Pixel to the left of principal point → positive y (robot-left convention)."""
        try:
            import numpy as np
        except ImportError:
            pytest.skip("numpy required")
        from fleet_safe_vla.perception.depth_fusion import CameraIntrinsics, DepthFusion
        ci = CameraIntrinsics(fx=615.0, fy=615.0, cx=320.0, cy=240.0)
        fusion = DepthFusion(intrinsics=ci)
        depth = np.zeros((480, 640), dtype=np.uint16)
        depth[235:245, 155:165] = 2000  # 2 m, pixel u ≈ 160 (left of cx=320)
        result = fusion.pixel_to_world(160.0, 240.0, depth)
        assert result is not None
        assert result[1] > 0.0  # left of robot → +y


# ══════════════════════════════════════════════════════════════════════════════
# PerceptionPipeline
# ══════════════════════════════════════════════════════════════════════════════

class TestPerceptionPipeline:
    def _make(self, model_path=None):
        from fleet_safe_vla.perception.perception_pipeline import (
            PerceptionConfig, PerceptionPipeline,
        )
        cfg = PerceptionConfig(model_path=model_path)
        return PerceptionPipeline.from_config(cfg)

    def test_from_config_no_model(self):
        pipeline = self._make(model_path=None)
        assert not pipeline.detector_enabled

    def test_process_none_frame_returns_empty(self):
        pipeline = self._make()
        result = pipeline.process(None)
        assert result == []

    def test_process_increments_frame_count(self):
        pipeline = self._make()
        pipeline.process(None)
        pipeline.process(None)
        assert pipeline.stats["frames_processed"] == 2

    def test_process_returns_detection_objects(self):
        pipeline = self._make()
        result = pipeline.process(None, timestamp=5.0)
        assert isinstance(result, list)

    def test_process_raw_returns_list(self):
        pipeline = self._make()
        result = pipeline.process_raw(None)
        assert isinstance(result, list)

    def test_stats_initial(self):
        pipeline = self._make()
        s = pipeline.stats
        assert s["frames_processed"] == 0
        assert s["total_detections"] == 0

    def test_from_config_default(self):
        from fleet_safe_vla.perception.perception_pipeline import (
            PerceptionConfig, PerceptionPipeline,
        )
        # default config tries yolov8n.pt — will fail gracefully without ultralytics
        cfg = PerceptionConfig()
        pipeline = PerceptionPipeline.from_config(cfg)
        assert isinstance(pipeline, PerceptionPipeline)


# ══════════════════════════════════════════════════════════════════════════════
# MockPerceptionSource
# ══════════════════════════════════════════════════════════════════════════════

class TestMockPerceptionSource:
    def _make(self, scenario="hospital_corridor", **kw):
        from fleet_safe_vla.perception.mock_source import MockPerceptionSource
        return MockPerceptionSource(scenario=scenario, **kw)

    # ── Basic API ──────────────────────────────────────────────────────────

    def test_step_returns_detections(self):
        src = self._make()
        dets = src.step()
        assert isinstance(dets, list)
        assert len(dets) > 0

    def test_detection_type(self):
        src = self._make()
        for d in src.step():
            assert isinstance(d, Detection)

    def test_step_increments_counter(self):
        src = self._make()
        src.step()
        src.step()
        assert src.current_step == 2

    def test_reset(self):
        src = self._make()
        src.step(); src.step()
        src.reset()
        assert src.current_step == 0

    def test_timestamp_default(self):
        src = self._make()
        dets = src.step()
        # step 0 → timestamp = 0 * 0.1 = 0.0
        assert all(d.timestamp == pytest.approx(0.0) for d in dets)

    def test_timestamp_explicit(self):
        src = self._make()
        dets = src.step(timestamp=99.9)
        assert all(d.timestamp == pytest.approx(99.9) for d in dets)

    # ── Scenarios ──────────────────────────────────────────────────────────

    def test_corridor_has_nurse_and_patient(self):
        src = self._make("hospital_corridor")
        dets = src.step()
        roles = {d.semantic_role for d in dets}
        assert "staff" in roles
        assert "patient" in roles

    def test_waiting_room_has_wheelchair(self):
        src = self._make("waiting_room")
        dets = src.step()
        roles = {d.semantic_role for d in dets}
        assert "wheelchair_user" in roles

    def test_empty_scenario(self):
        src = self._make("empty")
        dets = src.step()
        assert dets == []

    def test_unknown_scenario_raises(self):
        from fleet_safe_vla.perception.mock_source import MockPerceptionSource
        with pytest.raises(ValueError, match="Unknown scenario"):
            MockPerceptionSource(scenario="moon_landing")

    def test_random_scenario(self):
        from fleet_safe_vla.perception.mock_source import MockPerceptionSource
        src = MockPerceptionSource(scenario=None, n_random_agents=4, seed=7)
        dets = src.step()
        assert len(dets) == 4

    # ── Determinism ────────────────────────────────────────────────────────

    def test_reproducible_across_instances(self):
        from fleet_safe_vla.perception.mock_source import MockPerceptionSource
        src1 = MockPerceptionSource(scenario=None, n_random_agents=3, seed=42)
        src2 = MockPerceptionSource(scenario=None, n_random_agents=3, seed=42)
        for _ in range(10):
            d1 = src1.step()
            d2 = src2.step()
            positions1 = [x.position_xy for x in d1]
            positions2 = [x.position_xy for x in d2]
            assert positions1 == positions2

    def test_different_seeds_differ(self):
        from fleet_safe_vla.perception.mock_source import MockPerceptionSource
        src1 = MockPerceptionSource(scenario=None, n_random_agents=3, seed=1)
        src2 = MockPerceptionSource(scenario=None, n_random_agents=3, seed=2)
        d1 = src1.step()
        d2 = src2.step()
        positions1 = [x.position_xy for x in d1]
        positions2 = [x.position_xy for x in d2]
        assert positions1 != positions2

    # ── Detection content ──────────────────────────────────────────────────

    def test_agent_type_is_human_for_corridor(self):
        src = self._make("hospital_corridor")
        dets = src.step()
        assert all(d.agent_type == AgentType.HUMAN for d in dets)

    def test_confidence_in_range(self):
        src = self._make("hospital_corridor", conf_jitter=0.1)
        for _ in range(20):
            for d in src.step():
                assert 0.0 <= d.confidence <= 1.0

    def test_drop_prob_zero_no_drops(self):
        src = self._make("hospital_corridor", drop_prob=0.0)
        counts = [len(src.step()) for _ in range(10)]
        assert all(c == 2 for c in counts)

    def test_drop_prob_one_drops_all(self):
        src = self._make("hospital_corridor", drop_prob=1.0)
        dets = src.step()
        assert dets == []

    def test_positions_move_over_time(self):
        src = self._make("hospital_corridor")
        dets0 = src.step()
        for _ in range(10):
            src.step()
        dets10 = src.step()
        pos0 = sorted(d.position_xy for d in dets0)
        pos10 = sorted(d.position_xy for d in dets10)
        assert pos0 != pos10

    def test_available_scenarios(self):
        src = self._make()
        scenarios = src.available_scenarios
        assert "hospital_corridor" in scenarios
        assert "waiting_room" in scenarios
        assert "empty" in scenarios

    # ── MockAgentTrack ─────────────────────────────────────────────────────

    def test_agent_track_loop(self):
        from fleet_safe_vla.perception.mock_source import MockAgentTrack
        track = MockAgentTrack(
            agent_id="t0", semantic_role="staff", agent_type=AgentType.HUMAN,
            positions=[(0.0, 0.0), (1.0, 0.0)], loop=True,
        )
        assert track.position_at(0) == (0.0, 0.0)
        assert track.position_at(1) == (1.0, 0.0)
        assert track.position_at(2) == (0.0, 0.0)  # loops

    def test_agent_track_no_loop_clamps(self):
        from fleet_safe_vla.perception.mock_source import MockAgentTrack
        track = MockAgentTrack(
            agent_id="t0", semantic_role="staff", agent_type=AgentType.HUMAN,
            positions=[(0.0, 0.0), (1.0, 0.0)], loop=False,
        )
        assert track.position_at(100) == (1.0, 0.0)  # clamped to last

    def test_agent_track_empty_positions(self):
        from fleet_safe_vla.perception.mock_source import MockAgentTrack
        track = MockAgentTrack(
            agent_id="t0", semantic_role="staff", agent_type=AgentType.HUMAN,
            positions=[], loop=False,
        )
        assert track.position_at(0) == (0.0, 0.0)


# ══════════════════════════════════════════════════════════════════════════════
# Public API __init__ imports
# ══════════════════════════════════════════════════════════════════════════════

class TestPublicAPI:
    def test_all_symbols_importable(self):
        from fleet_safe_vla.perception import (
            SemanticDetector,
            DetectionResult,
            RoleClassifier,
            DepthFusion,
            PerceptionPipeline,
            PerceptionConfig,
            MockPerceptionSource,
        )

    def test_all_symbols_in_dunder_all(self):
        import fleet_safe_vla.perception as p
        for name in [
            "SemanticDetector", "DetectionResult", "RoleClassifier",
            "DepthFusion", "PerceptionPipeline", "PerceptionConfig",
            "MockPerceptionSource",
        ]:
            assert name in p.__all__, f"{name} missing from __all__"
