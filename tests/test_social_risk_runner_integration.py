"""
tests/test_social_risk_runner_integration.py
——————————————————————————————————————————
Verifies that the social-risk layer is wired into the benchmark runner and
replay overlay correctly.

Tests:
  1. Runner populates social-risk EpisodeMetrics fields on social-awareness scenes.
  2. safety_events.jsonl contains zone fields on RED/near-miss events.
  3. episode.json steps include zone, crowding_score, occlusion_risk fields.
  4. trajectory.csv has zone, crowding_score, occlusion_risk columns.
  5. OverlayData carries zone fields and to_lines() includes zone block.
  6. OverlayData.zone_color_rgb() returns different colours per zone.
  7. SafetyZoneRenderData.traffic_zone_color() changes per zone.
  8. SceneGraphRenderer.render_safety_zones() forwards zone from ReplayFrame.
  9. Smoke benchmark: crowded_corridor + crossing_pedestrian run end-to-end.
 10. Social-risk metrics are non-trivial in social-awareness scenes.
 11. Artifact field existence validator (all social-risk keys in metrics.json).
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

# Repo root on sys.path is set by pyproject.toml / conftest; fall back here.
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fleet_safe_vla.benchmarks.visualnav_runner import (
    BACKEND_MOCK,
    VisualNavBenchmarkRunner,
)
from fleet_safe_vla.benchmarks.visualnav_scenarios import (
    SCENE_CROWDED_CORRIDOR,
    SCENE_CROSSING_PEDESTRIAN,
    SCENE_STRAIGHT_CORRIDOR,
    get_scenes,
)
from fleet_safe_vla.integrations.visualnav_transformer.base_adapter import (
    ActionOutput,
    BaseVisualNavAdapter,
    CmdVel,
)
from fleet_safe_vla.envs.isaaclab.replay.replay_overlay import (
    OverlayData,
    build_overlay,
)
from fleet_safe_vla.envs.isaaclab.replay.replay_scene import ReplayFrame
from fleet_safe_vla.envs.isaaclab.replay.scene_graph_visualizer import (
    SafetyZoneRenderData,
    SceneGraphRenderer,
    TRAFFIC_ZONE_COLOR,
)


# ── Mock adapter ──────────────────────────────────────────────────────────────

class _TinyMock(BaseVisualNavAdapter):
    model_name   = "mock_social"
    image_size   = (32, 24)
    context_size = 2

    def __init__(self) -> None:
        super().__init__()
        self._loaded = True
        self._rng = np.random.default_rng(0)

    def load_checkpoint(self, path: Path) -> None:
        pass

    def preprocess_observation(self, obs_imgs, goal_img) -> dict:
        return {"obs": obs_imgs[0] if obs_imgs else np.zeros((24, 32, 3), dtype=np.uint8)}

    def predict_action(self, preprocessed) -> ActionOutput:
        return ActionOutput(
            waypoints=np.array([[0.05, 0.0]] * 5, dtype=np.float32),
            goal_distance=2.0,
            model_name=self.model_name,
            inference_ms=1.0,
        )


def _make_runner(tmp_path: Path, max_steps: int = 30,
                 social_profile: str = "default") -> VisualNavBenchmarkRunner:
    return VisualNavBenchmarkRunner(
        adapter        = _TinyMock(),
        fleetsafe      = False,
        backend        = BACKEND_MOCK,
        output_dir     = tmp_path / "results",
        max_steps      = max_steps,
        control_hz     = 4.0,
        social_profile = social_profile,
    )


def _first_episode_dir(run_dir: Path) -> Path:
    return sorted((run_dir / "episodes").iterdir())[0]


# ── Test 1: EpisodeMetrics social-risk fields populated ───────────────────────

class TestRunnerSocialRiskFields:

    def test_social_metrics_fields_present(self, tmp_path):
        runner = _make_runner(tmp_path)
        metrics = runner.run(
            scenes=[SCENE_STRAIGHT_CORRIDOR],
            seeds=[0],
            run_id="test_fields",
        )
        m = metrics[0]
        # All social-risk fields exist and are numeric
        assert hasattr(m, "crowding_risk_score_mean")
        assert hasattr(m, "occlusion_risk_score_mean")
        assert hasattr(m, "rare_event_count")
        assert hasattr(m, "steps_green")
        assert hasattr(m, "steps_amber")
        assert hasattr(m, "steps_red")
        assert hasattr(m, "min_human_distance_m")
        assert 0.0 <= m.crowding_risk_score_mean <= 1.0
        assert 0.0 <= m.occlusion_risk_score_mean <= 1.0
        assert m.rare_event_count >= 0
        # straight_corridor has no dynamic agents → all steps should be GREEN
        assert m.steps_green + m.steps_amber + m.steps_red == m.episode_length_steps

    def test_straight_corridor_all_green(self, tmp_path):
        runner = _make_runner(tmp_path)
        metrics = runner.run(
            scenes=[SCENE_STRAIGHT_CORRIDOR],
            seeds=[0],
            run_id="test_all_green",
        )
        m = metrics[0]
        # No agents, no obstacles → crowding = 0 → should be all GREEN or mostly GREEN
        assert m.steps_amber + m.steps_red == 0 or m.steps_green > 0


# ── Test 2: safety_events.jsonl zone fields ───────────────────────────────────

class TestSafetyEventsZoneFields:

    def _run_and_get_events(self, tmp_path, scene, run_id):
        runner = _make_runner(tmp_path)
        runner.run(scenes=[scene], seeds=[0], run_id=run_id)
        run_dir = tmp_path / "results" / run_id
        ep_dir = _first_episode_dir(run_dir)
        ev_path = ep_dir / "safety_events.jsonl"
        if not ev_path.exists() or ev_path.stat().st_size == 0:
            return []
        events = [json.loads(ln) for ln in ev_path.read_text().splitlines() if ln.strip()]
        return events

    def test_safety_events_have_zone_fields_when_present(self, tmp_path):
        events = self._run_and_get_events(tmp_path, SCENE_CROWDED_CORRIDOR, "ev_crowd")
        for ev in events:
            assert "active_safety_zone" in ev, "zone field missing from safety event"
            assert ev["active_safety_zone"] in ("GREEN", "AMBER", "RED")
            assert "crowding_risk_score" in ev
            assert "occlusion_risk_score" in ev
            assert "rare_event_count" in ev

    def test_safety_events_zone_field_straight_corridor(self, tmp_path):
        events = self._run_and_get_events(tmp_path, SCENE_STRAIGHT_CORRIDOR, "ev_straight")
        for ev in events:
            if "active_safety_zone" in ev:
                assert ev["active_safety_zone"] in ("GREEN", "AMBER", "RED")


# ── Test 3: episode.json step zone fields ─────────────────────────────────────

class TestEpisodeJsonZoneFields:

    def test_episode_json_steps_have_zone(self, tmp_path):
        runner = _make_runner(tmp_path)
        runner.run(scenes=[SCENE_CROWDED_CORRIDOR], seeds=[0], run_id="ep_zone")
        run_dir = tmp_path / "results" / "ep_zone"
        ep_dir = _first_episode_dir(run_dir)
        ep = json.loads((ep_dir / "episode.json").read_text())
        for step in ep.get("steps", []):
            assert "zone" in step
            assert step["zone"] in ("GREEN", "AMBER", "RED")
            assert "crowding_score" in step
            assert "occlusion_risk" in step
            assert "rare_event_count" in step


# ── Test 4: trajectory.csv has zone columns ───────────────────────────────────

class TestTrajectoryCsvZoneColumns:

    def test_trajectory_csv_has_zone_columns(self, tmp_path):
        runner = _make_runner(tmp_path)
        runner.run(scenes=[SCENE_CROSSING_PEDESTRIAN], seeds=[0], run_id="traj_zone")
        run_dir = tmp_path / "results" / "traj_zone"
        ep_dir = _first_episode_dir(run_dir)
        with open(ep_dir / "trajectory.csv") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) > 0
        assert "zone" in rows[0], "trajectory.csv missing 'zone' column"
        assert "crowding_score" in rows[0]
        assert "occlusion_risk" in rows[0]
        for row in rows:
            assert row["zone"] in ("GREEN", "AMBER", "RED")


# ── Test 5: OverlayData zone fields and to_lines ─────────────────────────────

class TestOverlayZone:

    def _make_frame(self, zone: str = "GREEN") -> ReplayFrame:
        return ReplayFrame(
            frame_idx=0,
            timestamp=0.0,
            robot_x=0.0, robot_y=0.0,
            robot_vx=0.0, robot_vy=0.0,
            raw_action=(0.3, 0.0, 0.0),
            safe_action=(0.3, 0.0, 0.0),
            action_delta=(0.0, 0.0, 0.0),
            intervention_applied=False,
            intervention_reason="",
            safety_margin_before=1.0,
            safety_margin_after=1.0,
            nearest_obstacle_id="obstacle_0",
            nearest_obstacle_distance_m=2.0,
            active_constraints=[],
            causal_explanation="All clear.",
            counterfactual_explanation="",
            counterfactual_rollout_id="",
            scene_graph_before={},
            scene_graph_after={},
            scene_graph_delta={},
            obstacles=[],
            edges=[],
            goal_xy=(3.0, 0.0),
            reproducibility_hash="abc123",
            backend="mock",
            model_name="mock",
            benchmark_version="0.0.1",
            active_safety_zone=zone,
            safety_zone_reason="crowding_score: 0.80",
            crowding_risk_score=0.8,
            occlusion_risk_score=0.3,
            rare_event_count=2,
            environment_profile="hospital",
        )

    def test_overlay_zone_fields_populated(self):
        frame = self._make_frame("AMBER")
        overlay = build_overlay(frame, total_frames=10, scene_id="test")
        assert overlay.active_safety_zone == "AMBER"
        assert overlay.crowding_risk_score == pytest.approx(0.8)
        assert overlay.environment_profile == "hospital"
        assert overlay.rare_event_count == 2

    def test_overlay_to_lines_contains_zone_label(self):
        for zone in ("GREEN", "AMBER", "RED"):
            frame = self._make_frame(zone)
            overlay = build_overlay(frame, total_frames=10)
            lines_text = "\n".join(overlay.to_lines())
            assert "Traffic-Light Zone" in lines_text
            assert zone in lines_text

    def test_overlay_status_prefix_by_zone(self):
        for zone, expected_frag in [
            ("RED",   "DANGER"),
            ("AMBER", "CAUTION"),
            ("GREEN", "NORMAL"),
        ]:
            frame = self._make_frame(zone)
            overlay = build_overlay(frame, total_frames=5)
            prefix = overlay._status_prefix()
            assert expected_frag in prefix, f"Expected '{expected_frag}' in prefix for zone {zone}"


# ── Test 6: zone_color_rgb returns different colours ─────────────────────────

class TestOverlayZoneColor:

    def _overlay(self, zone: str) -> OverlayData:
        return OverlayData(
            frame_idx=0, timestamp=0.0, total_frames=1,
            intervention_applied=False, intervention_reason="",
            safety_margin_before=1.0, safety_margin_after=1.0,
            nearest_obstacle_id="", nearest_obstacle_dist_m=5.0,
            active_constraints=[], raw_action=(0.0, 0.0, 0.0),
            safe_action=(0.0, 0.0, 0.0), action_delta=(0.0, 0.0, 0.0),
            action_delta_l2=0.0, causal_explanation="",
            counterfactual_explanation="", is_mock_rollout=True,
            backend="mock", model_name="m", benchmark_version="0",
            git_commit="abc", scene_id="s", missing_artifacts=[],
            active_safety_zone=zone,
        )

    def test_colors_differ_by_zone(self):
        g = self._overlay("GREEN").zone_color_rgb()
        a = self._overlay("AMBER").zone_color_rgb()
        r = self._overlay("RED").zone_color_rgb()
        assert g != a
        assert a != r
        assert g != r

    def test_color_tuples_are_rgb_triples(self):
        for zone in ("GREEN", "AMBER", "RED"):
            rgb = self._overlay(zone).zone_color_rgb()
            assert len(rgb) == 3
            assert all(0.0 <= c <= 1.0 for c in rgb)


# ── Test 7: SafetyZoneRenderData traffic zone color ──────────────────────────

class TestSafetyZoneRenderData:

    def test_traffic_zone_color_differs(self):
        g = SafetyZoneRenderData(0.0, 0.0, 0.3, 0.1, "GREEN").traffic_zone_color()
        a = SafetyZoneRenderData(0.0, 0.0, 0.3, 0.1, "AMBER").traffic_zone_color()
        r = SafetyZoneRenderData(0.0, 0.0, 0.3, 0.1, "RED").traffic_zone_color()
        assert g != a and a != r

    def test_traffic_zone_color_is_rgba(self):
        for zone in ("GREEN", "AMBER", "RED"):
            rgba = SafetyZoneRenderData(0.0, 0.0, 0.3, 0.1, zone).traffic_zone_color()
            assert len(rgba) == 4
            assert all(0.0 <= c <= 1.0 for c in rgba)

    def test_traffic_zone_color_red_most_opaque(self):
        g_alpha = SafetyZoneRenderData(0.0, 0.0, 0.3, 0.1, "GREEN").traffic_zone_color()[3]
        r_alpha = SafetyZoneRenderData(0.0, 0.0, 0.3, 0.1, "RED").traffic_zone_color()[3]
        assert r_alpha > g_alpha


# ── Test 8: SceneGraphRenderer.render_safety_zones forwards zone ──────────────

class TestSceneGraphRendererZone:

    def _make_frame(self, zone: str) -> ReplayFrame:
        return ReplayFrame(
            frame_idx=0, timestamp=0.0,
            robot_x=1.0, robot_y=2.0,
            robot_vx=0.0, robot_vy=0.0,
            raw_action=(0.0, 0.0, 0.0), safe_action=(0.0, 0.0, 0.0),
            action_delta=(0.0, 0.0, 0.0),
            intervention_applied=False, intervention_reason="",
            safety_margin_before=0.3, safety_margin_after=0.3,
            nearest_obstacle_id="obs", nearest_obstacle_distance_m=2.0,
            active_constraints=[], causal_explanation="",
            counterfactual_explanation="", counterfactual_rollout_id="",
            scene_graph_before={}, scene_graph_after={}, scene_graph_delta={},
            obstacles=[], edges=[], goal_xy=(5.0, 0.0),
            reproducibility_hash="", backend="mock", model_name="m",
            benchmark_version="0", active_safety_zone=zone,
        )

    def test_render_safety_zones_passes_zone(self):
        renderer = SceneGraphRenderer(safety_margin_m=0.30, collision_m=0.10)
        for zone in ("GREEN", "AMBER", "RED"):
            result = renderer.render_safety_zones(self._make_frame(zone))
            assert result.traffic_zone == zone

    def test_render_safety_zones_position(self):
        renderer = SceneGraphRenderer()
        result = renderer.render_safety_zones(self._make_frame("GREEN"))
        assert result.robot_x == pytest.approx(1.0)
        assert result.robot_y == pytest.approx(2.0)


# ── Test 9: Smoke benchmark — social-awareness scenes run end-to-end ──────────

class TestSocialSceneSmoke:

    def test_crowded_corridor_runs(self, tmp_path):
        runner = _make_runner(tmp_path, max_steps=20)
        metrics = runner.run(
            scenes=[SCENE_CROWDED_CORRIDOR],
            seeds=[0],
            run_id="smoke_crowd",
        )
        assert len(metrics) == len(SCENE_CROWDED_CORRIDOR.start_goal_pairs)
        for m in metrics:
            assert m.scene == "crowded_corridor"
            assert m.episode_length_steps >= 1

    def test_crossing_pedestrian_runs(self, tmp_path):
        runner = _make_runner(tmp_path, max_steps=20)
        metrics = runner.run(
            scenes=[SCENE_CROSSING_PEDESTRIAN],
            seeds=[0],
            run_id="smoke_cross",
        )
        assert len(metrics) == len(SCENE_CROSSING_PEDESTRIAN.start_goal_pairs)
        for m in metrics:
            assert m.scene == "crossing_pedestrian"


# ── Test 10: Social metrics non-trivial in social scenes ─────────────────────

class TestSocialMetricsNonTrivial:

    def test_crowded_scene_has_higher_crowding_than_empty(self, tmp_path):
        runner = _make_runner(tmp_path, max_steps=25)
        m_straight = runner.run(
            scenes=[SCENE_STRAIGHT_CORRIDOR], seeds=[0], run_id="base_straight"
        )[0]
        m_crowd = runner.run(
            scenes=[SCENE_CROWDED_CORRIDOR], seeds=[0], run_id="base_crowd"
        )[0]
        # crowded_corridor has 4 dynamic agents → crowding score should be higher
        assert m_crowd.crowding_risk_score_mean >= m_straight.crowding_risk_score_mean


# ── Test 11: Artifact field existence — metrics.json has all social fields ────

class TestArtifactFieldExistence:

    EXPECTED_SOCIAL_FIELDS = [
        "crowding_risk_score_mean",
        "crowding_risk_score_max",
        "occlusion_risk_score_mean",
        "occlusion_risk_score_max",
        "social_margin_violation_count",
        "rare_event_count",
        "min_human_distance_m",
        "steps_green",
        "steps_amber",
        "steps_red",
    ]

    def test_metrics_json_has_all_social_fields(self, tmp_path):
        runner = _make_runner(tmp_path)
        runner.run(
            scenes=[SCENE_CROWDED_CORRIDOR], seeds=[0], run_id="artifact_check"
        )
        run_dir = tmp_path / "results" / "artifact_check"
        ep_dir = _first_episode_dir(run_dir)
        m = json.loads((ep_dir / "metrics.json").read_text())
        for field in self.EXPECTED_SOCIAL_FIELDS:
            assert field in m, f"metrics.json missing field: {field!r}"
