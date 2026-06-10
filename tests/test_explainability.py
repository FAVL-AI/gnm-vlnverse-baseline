"""
tests/test_explainability.py
Unit tests for fleet_safe_vla.explainability.*
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fleet_safe_vla.explainability.scene_graph import (
    SceneEdge,
    SceneGraph,
    SceneGraphBuilder,
    SceneNode,
    SceneNodeType,
    SceneRelation,
)
from fleet_safe_vla.explainability.causal_reasoner import (
    CausalEvent,
    CausalEventType,
    CausalReasoner,
)
from fleet_safe_vla.explainability.counterfactuals import (
    Counterfactual,
    CounterfactualGenerator,
)
from fleet_safe_vla.explainability.explanation_generator import (
    Explanation,
    ExplanationGenerator,
)
from fleet_safe_vla.explainability.event_recorder import (
    EventRecorder,
    ExplainabilityStepRecord,
)
from fleet_safe_vla.explainability.scenario_generator import (
    ScenarioGenerator,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

@dataclass
class _FakeObstacle:
    x: float
    y: float
    radius_m: float = 0.15


def _build_graph_with_obstacle(
    robot_xy=(0.0, 0.0),
    obstacle_xy=(0.3, 0.0),
    obs_radius=0.15,
    goal_xy=(3.0, 0.0),
    raw_vx=0.2,
    raw_vy=0.0,
    intervened=False,
) -> SceneGraph:
    builder = SceneGraphBuilder(
        near_threshold_m=0.45,
        margin_threshold_m=0.30,
        collision_m=0.10,
    )
    return builder.build(
        step=0,
        timestamp_s=0.0,
        robot_xy=robot_xy,
        robot_heading=0.0,
        goal_xy=goal_xy,
        obstacles=[_FakeObstacle(obstacle_xy[0], obstacle_xy[1], obs_radius)],
        raw_vx=raw_vx,
        raw_vy=raw_vy,
        intervened=intervened,
    )


def _make_step_record(
    step=0,
    graph=None,
    event_type=CausalEventType.NO_EVENT,
    intervened=False,
    raw_cmd=(0.2, 0.0, 0.0),
    safe_cmd=(0.2, 0.0, 0.0),
) -> ExplainabilityStepRecord:
    if graph is None:
        graph = _build_graph_with_obstacle()
    reasoner = CausalReasoner()
    cf_gen   = CounterfactualGenerator()
    exp_gen  = ExplanationGenerator()
    causal   = CausalEvent(
        step=step, event_type=event_type,
        obstacle_id="obstacle_0",
        obstacle_distance_m=1.0,
        safety_margin_m=0.30,
        raw_cmd=raw_cmd, safe_cmd=safe_cmd,
        action_delta_l2=float(np.linalg.norm(np.array(safe_cmd) - np.array(raw_cmd))),
        description="test", evidence={},
    )
    cf  = cf_gen.generate(causal)
    expl = exp_gen.generate(causal, cf, graph)
    return ExplainabilityStepRecord(
        step=step, timestamp_s=float(step) * 0.25,
        scene_graph=graph, causal_event=causal,
        counterfactual=cf, explanation=expl,
        latency_ms=1.0,
    )


# ── SceneGraph ─────────────────────────────────────────────────────────────────

class TestSceneGraph:
    def test_add_node_and_retrieve(self):
        g = SceneGraph(step=0, timestamp_s=0.0)
        node = SceneNode("robot", SceneNodeType.ROBOT, (0.0, 0.0))
        g.add_node(node)
        assert "robot" in g.nodes
        assert g.nodes["robot"].node_type == SceneNodeType.ROBOT

    def test_add_edge(self):
        g = SceneGraph(step=0, timestamp_s=0.0)
        g.add_edge(SceneEdge("robot", "obstacle_0", SceneRelation.NEAR, 0.3))
        assert len(g.edges) == 1
        assert g.edges[0].relation == SceneRelation.NEAR

    def test_get_edges_for_node(self):
        g = SceneGraph(step=0, timestamp_s=0.0)
        g.add_edge(SceneEdge("robot", "obstacle_0", SceneRelation.NEAR, 0.3))
        g.add_edge(SceneEdge("robot", "obstacle_1", SceneRelation.NEAR, 0.4))
        g.add_edge(SceneEdge("goal", "obstacle_0", SceneRelation.OCCLUDES, 0.1))
        edges = g.get_edges_for("robot")
        assert len(edges) == 2

    def test_get_edges_filtered_by_relation(self):
        g = SceneGraph(step=0, timestamp_s=0.0)
        g.add_edge(SceneEdge("robot", "obstacle_0", SceneRelation.NEAR, 0.3))
        g.add_edge(SceneEdge("robot", "obstacle_0", SceneRelation.VIOLATES_MARGIN, 0.3))
        near_only = g.get_edges_for("robot", SceneRelation.NEAR)
        assert len(near_only) == 1

    def test_nearest_obstacle_returns_closest(self):
        g = SceneGraph(step=0, timestamp_s=0.0)
        g.add_node(SceneNode("robot",      SceneNodeType.ROBOT,    (0.0, 0.0), 0.15))
        g.add_node(SceneNode("obstacle_0", SceneNodeType.OBSTACLE, (0.5, 0.0), 0.15))
        g.add_node(SceneNode("obstacle_1", SceneNodeType.OBSTACLE, (2.0, 0.0), 0.15))
        nearest, dist = g.nearest_obstacle("robot")
        assert nearest.node_id == "obstacle_0"
        # nearest_obstacle subtracts obstacle.radius_m only (centre-to-centre minus obs radius)
        assert dist == pytest.approx(0.5 - 0.15, abs=1e-6)

    def test_nearest_obstacle_no_obstacles_returns_inf(self):
        g = SceneGraph(step=0, timestamp_s=0.0)
        g.add_node(SceneNode("robot", SceneNodeType.ROBOT, (0.0, 0.0), 0.15))
        _, dist = g.nearest_obstacle("robot")
        assert dist == float("inf")

    def test_to_dict_contains_all_keys(self):
        g = SceneGraph(step=3, timestamp_s=0.75)
        g.add_node(SceneNode("robot", SceneNodeType.ROBOT, (0.0, 0.0)))
        g.add_edge(SceneEdge("robot", "goal", SceneRelation.NEAR, 1.0))
        d = g.to_dict()
        assert d["step"] == 3
        assert d["timestamp_s"] == pytest.approx(0.75)
        assert len(d["nodes"]) == 1
        assert len(d["edges"]) == 1


# ── SceneGraphBuilder ──────────────────────────────────────────────────────────

class TestSceneGraphBuilder:
    def test_robot_and_goal_always_present(self):
        g = _build_graph_with_obstacle()
        assert "robot" in g.nodes
        assert "goal"  in g.nodes

    def test_obstacle_node_added(self):
        g = _build_graph_with_obstacle()
        assert "obstacle_0" in g.nodes

    def test_near_edge_added_when_close(self):
        g = _build_graph_with_obstacle(robot_xy=(0.0, 0.0), obstacle_xy=(0.3, 0.0))
        relations = {e.relation for e in g.edges}
        assert SceneRelation.NEAR in relations

    def test_no_near_edge_when_far(self):
        g = _build_graph_with_obstacle(robot_xy=(0.0, 0.0), obstacle_xy=(5.0, 0.0))
        relations = {e.relation for e in g.edges}
        assert SceneRelation.NEAR not in relations

    def test_violates_margin_edge_added(self):
        g = _build_graph_with_obstacle(robot_xy=(0.0, 0.0), obstacle_xy=(0.2, 0.0))
        relations = {e.relation for e in g.edges}
        assert SceneRelation.VIOLATES_MARGIN in relations

    def test_intervention_caused_by_edge_when_intervened(self):
        g = _build_graph_with_obstacle(
            robot_xy=(0.0, 0.0), obstacle_xy=(0.2, 0.0), intervened=True
        )
        relations = {e.relation for e in g.edges}
        assert SceneRelation.INTERVENTION_CAUSED_BY in relations

    def test_no_intervention_edge_when_not_intervened(self):
        g = _build_graph_with_obstacle(
            robot_xy=(0.0, 0.0), obstacle_xy=(0.2, 0.0), intervened=False
        )
        relations = {e.relation for e in g.edges}
        assert SceneRelation.INTERVENTION_CAUSED_BY not in relations

    def test_waypoints_added_to_graph(self):
        builder = SceneGraphBuilder()
        g = builder.build(
            step=0, timestamp_s=0.0,
            robot_xy=(0.0, 0.0), robot_heading=0.0,
            goal_xy=(3.0, 0.0),
            obstacles=[],
            waypoints=[(1.0, 0.0), (2.0, 0.0)],
        )
        assert "waypoint_0" in g.nodes
        assert "waypoint_1" in g.nodes


# ── CausalReasoner ─────────────────────────────────────────────────────────────

class TestCausalReasoner:
    def _reason(self, robot_xy, obs_xy, obs_rad=0.15, intervened=False, estop=False):
        graph    = _build_graph_with_obstacle(robot_xy, obs_xy, obs_rad, intervened=intervened)
        reasoner = CausalReasoner()
        return reasoner.reason(
            step=0, scene_graph=graph,
            raw_vx=0.2, raw_vy=0.0, raw_wz=0.0,
            safe_vx=0.05 if intervened else 0.2,
            safe_vy=0.0, safe_wz=0.0,
            intervened=intervened, estop=estop,
        )

    def test_no_event_when_far(self):
        ev = self._reason((0.0, 0.0), (5.0, 0.0))
        assert ev.event_type in (CausalEventType.GOAL_PURSUIT, CausalEventType.NO_EVENT)

    def test_near_violation_when_close_but_no_intervention(self):
        ev = self._reason((0.0, 0.0), (0.3, 0.0))
        assert ev.event_type == CausalEventType.NEAR_VIOLATION

    def test_cbf_intervention_when_intervened(self):
        ev = self._reason((0.0, 0.0), (0.2, 0.0), intervened=True)
        assert ev.event_type == CausalEventType.CBF_INTERVENTION

    def test_estop_when_estop_flag(self):
        ev = self._reason((0.0, 0.0), (0.05, 0.0), intervened=True, estop=True)
        assert ev.event_type == CausalEventType.ESTOP

    def test_description_mentions_obstacle_id(self):
        ev = self._reason((0.0, 0.0), (0.2, 0.0), intervened=True)
        assert "obstacle_0" in ev.description

    def test_description_mentions_distance(self):
        ev = self._reason((0.0, 0.0), (0.2, 0.0), intervened=True)
        assert "m" in ev.description   # distance is mentioned in metres

    def test_evidence_contains_graph_edges(self):
        ev = self._reason((0.0, 0.0), (0.2, 0.0), intervened=True)
        assert "graph_edges" in ev.evidence
        assert isinstance(ev.evidence["graph_edges"], list)

    def test_to_dict_round_trips(self):
        ev = self._reason((0.0, 0.0), (0.3, 0.0))
        d  = ev.to_dict()
        assert d["step"] == 0
        assert "event_type" in d
        assert "description" in d


# ── CounterfactualGenerator ────────────────────────────────────────────────────

class TestCounterfactualGenerator:
    def _make_intervention_event(self, dist_m=0.20):
        return CausalEvent(
            step=0,
            event_type=CausalEventType.CBF_INTERVENTION,
            obstacle_id="obstacle_0",
            obstacle_distance_m=dist_m,
            safety_margin_m=0.30,
            raw_cmd=(0.28, 0.0, 0.0),
            safe_cmd=(0.05, 0.0, 0.0),
            action_delta_l2=0.23,
            description="test",
            evidence={},
        )

    def _make_no_event(self):
        return CausalEvent(
            step=0,
            event_type=CausalEventType.NO_EVENT,
            obstacle_id="none",
            obstacle_distance_m=2.0,
            safety_margin_m=0.30,
            raw_cmd=(0.28, 0.0, 0.0),
            safe_cmd=(0.28, 0.0, 0.0),
            action_delta_l2=0.0,
            description="no event",
            evidence={},
        )

    def test_no_intervention_returns_accepted(self):
        cf = CounterfactualGenerator().generate(self._make_no_event())
        assert cf.was_intervention is False
        assert cf.action_accepted is True

    def test_shift_equals_margin_minus_distance(self):
        ev = self._make_intervention_event(dist_m=0.18)
        cf = CounterfactualGenerator(margin_m=0.30, buffer_m=0.01).generate(ev)
        expected_shift = 0.30 + 0.01 - 0.18
        assert cf.distance_shift_m == pytest.approx(expected_shift, abs=1e-6)

    def test_hypothetical_distance_exceeds_margin(self):
        ev = self._make_intervention_event(dist_m=0.18)
        cf = CounterfactualGenerator(margin_m=0.30, buffer_m=0.01).generate(ev)
        assert cf.hypothetical_distance_m > 0.30

    def test_explanation_mentions_obstacle_id(self):
        ev = self._make_intervention_event()
        cf = CounterfactualGenerator().generate(ev)
        assert "obstacle_0" in cf.explanation

    def test_explanation_mentions_shift(self):
        ev = self._make_intervention_event(dist_m=0.18)
        cf = CounterfactualGenerator().generate(ev)
        assert "m farther" in cf.explanation

    def test_zero_shift_when_already_at_margin(self):
        ev = self._make_intervention_event(dist_m=0.32)   # already past margin
        cf = CounterfactualGenerator(margin_m=0.30, buffer_m=0.01).generate(ev)
        assert cf.distance_shift_m == pytest.approx(0.0)

    def test_to_dict_round_trips(self):
        ev = self._make_intervention_event()
        cf = CounterfactualGenerator().generate(ev)
        d  = cf.to_dict()
        assert "explanation" in d
        assert "distance_shift_m" in d


# ── ExplanationGenerator ───────────────────────────────────────────────────────

class TestExplanationGenerator:
    def _make_intervention(self):
        graph = _build_graph_with_obstacle(
            robot_xy=(0.0, 0.0), obstacle_xy=(0.2, 0.0), intervened=True
        )
        reasoner = CausalReasoner()
        causal   = reasoner.reason(
            step=5, scene_graph=graph,
            raw_vx=0.28, raw_vy=0.0, raw_wz=0.0,
            safe_vx=0.05, safe_vy=0.0, safe_wz=0.0,
            intervened=True, estop=False,
        )
        cf  = CounterfactualGenerator().generate(causal)
        return causal, cf, graph

    def test_returns_explanation_object(self):
        causal, cf, graph = self._make_intervention()
        expl = ExplanationGenerator().generate(causal, cf, graph)
        assert isinstance(expl, Explanation)

    def test_natural_language_not_empty(self):
        causal, cf, graph = self._make_intervention()
        expl = ExplanationGenerator().generate(causal, cf, graph)
        assert len(expl.natural_language) > 0

    def test_natural_language_mentions_step(self):
        causal, cf, graph = self._make_intervention()
        expl = ExplanationGenerator().generate(causal, cf, graph)
        assert "Step 5" in expl.natural_language

    def test_action_delta_is_positive(self):
        causal, cf, graph = self._make_intervention()
        expl = ExplanationGenerator().generate(causal, cf, graph)
        assert expl.action_delta_l2 > 0.0

    def test_active_constraints_non_empty_on_intervention(self):
        causal, cf, graph = self._make_intervention()
        expl = ExplanationGenerator().generate(causal, cf, graph)
        assert len(expl.active_constraints) > 0

    def test_to_dict_has_required_keys(self):
        causal, cf, graph = self._make_intervention()
        expl = ExplanationGenerator().generate(causal, cf, graph)
        d    = expl.to_dict()
        for key in ("step", "natural_language", "causal_summary", "action_delta_l2"):
            assert key in d


# ── EventRecorder ──────────────────────────────────────────────────────────────

class TestEventRecorder:
    def test_records_accumulate(self):
        recorder = EventRecorder()
        for i in range(5):
            recorder.record(_make_step_record(step=i))
        assert len(recorder._records) == 5

    def test_write_explanation_log_creates_file(self, tmp_path):
        recorder = EventRecorder()
        for i in range(3):
            recorder.record(_make_step_record(step=i))
        path = tmp_path / "explanation_log.jsonl"
        recorder.write_explanation_log(path)
        assert path.exists()
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 3

    def test_write_scene_graphs_creates_file(self, tmp_path):
        recorder = EventRecorder()
        recorder.record(_make_step_record(step=0))
        recorder.write_scene_graphs(tmp_path / "scene_graphs.jsonl")
        assert (tmp_path / "scene_graphs.jsonl").exists()

    def test_write_counterfactuals_creates_file(self, tmp_path):
        recorder = EventRecorder()
        recorder.record(_make_step_record(step=0))
        recorder.write_counterfactuals(tmp_path / "counterfactuals.jsonl")
        assert (tmp_path / "counterfactuals.jsonl").exists()

    def test_write_audit_trail_creates_file(self, tmp_path):
        recorder = EventRecorder(model_name="gnm", backend="mock")
        recorder.record(_make_step_record(step=0))
        recorder.write_audit_trail(tmp_path / "audit_trail.json")
        assert (tmp_path / "audit_trail.json").exists()

    def test_audit_trail_labels_mock_backend(self, tmp_path):
        recorder = EventRecorder(backend="mock")
        recorder.record(_make_step_record(step=0))
        p = tmp_path / "audit_trail.json"
        recorder.write_audit_trail(p)
        data = json.loads(p.read_text())
        assert "engineering" in data["backend_label"].lower()

    def test_write_all_creates_four_files(self, tmp_path):
        recorder = EventRecorder(model_name="gnm", backend="mock")
        recorder.record(_make_step_record(step=0))
        recorder.write_all(tmp_path)
        for fname in ("explanation_log.jsonl", "scene_graphs.jsonl",
                      "counterfactuals.jsonl", "audit_trail.json"):
            assert (tmp_path / fname).exists()

    def test_coverage_metrics_keys_present(self):
        recorder = EventRecorder()
        for i in range(5):
            recorder.record(_make_step_record(step=i))
        metrics = recorder.coverage_metrics()
        for key in (
            "explanation_coverage",
            "intervention_explanation_rate",
            "counterfactual_validity_rate",
            "causal_graph_size_mean",
            "explanation_latency_ms_mean",
        ):
            assert key in metrics

    def test_coverage_is_one_when_all_explained(self):
        recorder = EventRecorder()
        for i in range(10):
            recorder.record(_make_step_record(step=i))
        metrics = recorder.coverage_metrics()
        assert metrics["explanation_coverage"] == pytest.approx(1.0)


# ── ScenarioGenerator ──────────────────────────────────────────────────────────

class TestScenarioGenerator:
    def _base_graph(self):
        return _build_graph_with_obstacle(
            robot_xy=(0.0, 0.0), obstacle_xy=(1.0, 0.0)
        )

    def test_from_scene_graph_returns_n_variants(self):
        gen      = ScenarioGenerator(rng_seed=0)
        graph    = self._base_graph()
        variants = gen.from_scene_graph(graph, n_variants=5)
        assert len(variants) == 5

    def test_translate_obstacle_changes_position(self):
        gen      = ScenarioGenerator(rng_seed=0)
        graph    = self._base_graph()
        new_g, mut = gen.translate_obstacle(graph, "obstacle_0", 0.5, 0.0)
        orig_x = graph.nodes["obstacle_0"].position[0]
        new_x  = new_g.nodes["obstacle_0"].position[0]
        assert new_x == pytest.approx(orig_x + 0.5)
        assert mut.mutation_type == "translate_obstacle"

    def test_translate_does_not_mutate_original(self):
        gen   = ScenarioGenerator(rng_seed=0)
        graph = self._base_graph()
        orig_pos = graph.nodes["obstacle_0"].position
        gen.translate_obstacle(graph, "obstacle_0", 1.0, 0.0)
        assert graph.nodes["obstacle_0"].position == orig_pos

    def test_remove_obstacle_removes_node(self):
        gen     = ScenarioGenerator(rng_seed=0)
        graph   = self._base_graph()
        new_g, mut = gen.remove_obstacle(graph, "obstacle_0")
        assert "obstacle_0" not in new_g.nodes
        assert mut.mutation_type == "remove_obstacle"

    def test_remove_obstacle_removes_edges(self):
        gen   = ScenarioGenerator(rng_seed=0)
        graph = self._base_graph()
        # Ensure the source graph has edges involving obstacle_0
        new_g, _ = gen.remove_obstacle(graph, "obstacle_0")
        for edge in new_g.edges:
            assert edge.source_id != "obstacle_0"
            assert edge.target_id != "obstacle_0"

    def test_add_noise_obstacles_increases_node_count(self):
        gen   = ScenarioGenerator(rng_seed=0)
        graph = self._base_graph()
        n_before = len(graph.nodes)
        new_g, mut = gen.add_noise_obstacles(graph, n=3)
        assert len(new_g.nodes) == n_before + 3

    def test_scale_scene_changes_goal_position(self):
        gen   = ScenarioGenerator(rng_seed=0)
        graph = self._base_graph()
        orig_goal = graph.nodes["goal"].position
        new_g, mut = gen.scale_scene(graph, factor=2.0)
        new_goal = new_g.nodes["goal"].position
        assert new_goal[0] != pytest.approx(orig_goal[0])
