"""
tests/test_intervention_evidence_replay.py

Tests for the intervention evidence replay contract:
  - InterventionEvidence dataclass
  - SceneGraphDelta / diff_scene_graphs
  - CounterfactualRolloutEngine (mock + Isaac stub)
  - InterventionEvidenceRecorder
  - EventRecorder.write_intervention_evidence()
  - Benchmark runner writes intervention_evidence.jsonl
  - Artifact validator catches missing evidence
"""
from __future__ import annotations

import json
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
    SceneGraphDelta,
    diff_scene_graphs,
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
from fleet_safe_vla.explainability.intervention_evidence import (
    InterventionEvidence,
    InterventionEvidenceRecorder,
)
from fleet_safe_vla.explainability.counterfactual_rollout import (
    CounterfactualRolloutEngine,
    CounterfactualRolloutRequest,
)
from fleet_safe_vla.integrations.visualnav_transformer.base_adapter import (
    BaseVisualNavAdapter,
    ActionOutput,
)


class _MockAdapter(BaseVisualNavAdapter):
    """Minimal deterministic adapter for runner tests (no checkpoint required)."""
    model_name   = "mock_evidence_test"
    image_size   = (32, 24)
    context_size = 2

    def __init__(self) -> None:
        super().__init__()
        self._loaded = True

    def load_checkpoint(self, path) -> None:
        self._loaded = True

    def preprocess_observation(self, obs_imgs, goal_img) -> dict:
        return {"obs": obs_imgs[0] if obs_imgs else np.zeros((24, 32, 3), dtype=np.uint8)}

    def predict_action(self, preprocessed) -> ActionOutput:
        return ActionOutput(
            waypoints=np.array([[0.08, 0.01]] * 5, dtype=np.float32),
            goal_distance=2.0,
            model_name=self.model_name,
            inference_ms=1.0,
        )


# ── Helpers ────────────────────────────────────────────────────────────────────

@dataclass
class _FakeObstacle:
    x: float
    y: float
    radius_m: float = 0.15


def _make_graph(
    step: int = 0,
    robot_xy: tuple = (0.0, 0.0),
    obstacle_xy: tuple = (0.3, 0.0),
    obs_radius: float = 0.15,
    intervened: bool = False,
    raw_vx: float = 0.3,
) -> SceneGraph:
    builder = SceneGraphBuilder(
        near_threshold_m=0.45,
        margin_threshold_m=0.30,
        collision_m=0.10,
    )
    return builder.build(
        step=step,
        timestamp_s=float(step) * 0.25,
        robot_xy=robot_xy,
        robot_heading=0.0,
        goal_xy=(3.0, 0.0),
        obstacles=[_FakeObstacle(*obstacle_xy, obs_radius)],
        raw_vx=raw_vx,
        raw_vy=0.0,
        intervened=intervened,
    )


def _make_step_record(
    step: int = 0,
    raw_vx: float = 0.3,
    safe_vx: float = 0.08,
    intervened: bool = True,
    min_dist_m: float = 0.18,
    obstacle_xy: tuple = (0.3, 0.0),
) -> tuple[ExplainabilityStepRecord, SceneGraph]:
    graph = _make_graph(step=step, obstacle_xy=obstacle_xy, intervened=intervened, raw_vx=raw_vx)
    reasoner = CausalReasoner(near_miss_m=0.45, collision_m=0.10, margin_m=0.30)
    causal = reasoner.reason(
        step=step,
        scene_graph=graph,
        raw_vx=raw_vx, raw_vy=0.0, raw_wz=0.0,
        safe_vx=safe_vx, safe_vy=0.0, safe_wz=0.0,
        intervened=intervened,
        estop=False,
    )
    cf_gen = CounterfactualGenerator(margin_m=0.30)
    cf = cf_gen.generate(causal)
    exp_gen = ExplanationGenerator()
    explanation = exp_gen.generate(causal, cf, graph)
    rec = ExplainabilityStepRecord(
        step=step,
        timestamp_s=float(step) * 0.25,
        scene_graph=graph,
        causal_event=causal,
        counterfactual=cf,
        explanation=explanation,
        model_name="gnm",
        backend="mock",
        latency_ms=5.0,
    )
    return rec, graph


# ── Test 1: raw action is preserved ───────────────────────────────────────────

def test_raw_action_preserved():
    ev = InterventionEvidence.build(
        episode_id="test_ep",
        step_idx=0,
        timestamp=0.0,
        scene_id="test_scene",
        model_name="gnm",
        backend="mock",
        benchmark_version="0.1.0",
        protocol_version="0.1.0",
        raw_action=(0.28, 0.0, 0.12),
        safe_action=(0.08, 0.0, 0.12),
        intervention_applied=True,
        intervention_reason="test reason",
        safety_margin_before=0.18,
        safety_margin_after=0.22,
        nearest_obstacle_id="obstacle_0",
        nearest_obstacle_distance_m=0.18,
        active_constraints=["robot→obstacle_0:violates_margin@0.180m"],
        scene_graph_before={},
        scene_graph_after={},
        scene_graph_delta={},
        causal_explanation="FleetSafe reduced vx",
        counterfactual_explanation="If obstacle were farther ...",
        counterfactual_rollout_id="abc12345",
    )
    assert ev.raw_action == (0.28, 0.0, 0.12)


# ── Test 2: safe action is preserved ──────────────────────────────────────────

def test_safe_action_preserved():
    ev = InterventionEvidence.build(
        episode_id="test_ep",
        step_idx=0,
        timestamp=0.0,
        scene_id="test_scene",
        model_name="gnm",
        backend="mock",
        benchmark_version="0.1.0",
        protocol_version="0.1.0",
        raw_action=(0.28, 0.0, 0.12),
        safe_action=(0.08, 0.0, 0.12),
        intervention_applied=True,
        intervention_reason="test reason",
        safety_margin_before=0.18,
        safety_margin_after=0.22,
        nearest_obstacle_id="obstacle_0",
        nearest_obstacle_distance_m=0.18,
        active_constraints=[],
        scene_graph_before={},
        scene_graph_after={},
        scene_graph_delta={},
        causal_explanation="",
        counterfactual_explanation="",
        counterfactual_rollout_id="",
    )
    assert ev.safe_action == (0.08, 0.0, 0.12)


# ── Test 3: action delta computed correctly ────────────────────────────────────

def test_action_delta_computed():
    ev = InterventionEvidence.build(
        episode_id="test_ep",
        step_idx=0,
        timestamp=0.0,
        scene_id="s",
        model_name="gnm",
        backend="mock",
        benchmark_version="0.1.0",
        protocol_version="0.1.0",
        raw_action=(0.30, 0.10, 0.05),
        safe_action=(0.10, 0.05, 0.05),
        intervention_applied=True,
        intervention_reason="",
        safety_margin_before=0.15,
        safety_margin_after=0.20,
        nearest_obstacle_id="obstacle_0",
        nearest_obstacle_distance_m=0.15,
        active_constraints=[],
        scene_graph_before={},
        scene_graph_after={},
        scene_graph_delta={},
        causal_explanation="",
        counterfactual_explanation="",
        counterfactual_rollout_id="",
    )
    assert ev.action_delta[0] == pytest.approx(-0.20, abs=1e-9)
    assert ev.action_delta[1] == pytest.approx(-0.05, abs=1e-9)
    assert ev.action_delta[2] == pytest.approx(0.0,   abs=1e-9)


# ── Test 4: evidence event serializes to JSON ──────────────────────────────────

def test_evidence_serializes_to_json():
    ev = InterventionEvidence.build(
        episode_id="ep1",
        step_idx=3,
        timestamp=0.75,
        scene_id="narrow_passage",
        model_name="vint",
        backend="mock",
        benchmark_version="0.1.0",
        protocol_version="0.1.0",
        raw_action=(0.25, 0.0, 0.0),
        safe_action=(0.0, 0.0, 0.0),
        intervention_applied=True,
        intervention_reason="E-STOP",
        safety_margin_before=0.05,
        safety_margin_after=0.05,
        nearest_obstacle_id="obstacle_0",
        nearest_obstacle_distance_m=0.05,
        active_constraints=[],
        scene_graph_before={"nodes": []},
        scene_graph_after={"nodes": []},
        scene_graph_delta={"added_edges": []},
        causal_explanation="E-STOP triggered",
        counterfactual_explanation="If obstacle were 0.25m farther ...",
        counterfactual_rollout_id="xyzabc",
    )
    d = ev.to_dict()
    serialized = json.dumps(d)
    recovered = json.loads(serialized)
    assert recovered["step_idx"] == 3
    assert recovered["intervention_applied"] is True
    assert recovered["raw_action"] == [0.25, 0.0, 0.0]
    assert len(recovered["reproducibility_hash"]) == 16


# ── Test 5: scene graph delta detects added violates_margin edge ──────────────

def test_scene_graph_delta_detects_violates_margin():
    # Before: robot at (0, 0), obstacle at (1.0, 0) — far, no violation
    before = _make_graph(step=0, robot_xy=(0.0, 0.0), obstacle_xy=(1.0, 0.0))
    # After: robot at (0.75, 0), obstacle at (1.0, 0) — distance = 0.25 - 0.15 = 0.10, violates
    after  = _make_graph(step=1, robot_xy=(0.75, 0.0), obstacle_xy=(1.0, 0.0))

    delta = diff_scene_graphs(before, after)
    added_relations = {e["relation"] for e in delta.added_edges}
    assert "violates_margin" in added_relations, (
        f"Expected 'violates_margin' in added edges, got: {added_relations}"
    )


# ── Test 6: mock counterfactual rollout predicts collision for unsafe action ──

def test_mock_rollout_predicts_collision_for_unsafe_action():
    engine = CounterfactualRolloutEngine(backend="mock", collision_threshold_m=0.10)
    req = CounterfactualRolloutRequest(
        raw_action=(0.5, 0.0, 0.0),       # driving straight into obstacle
        safe_action=(0.0, 0.0, 0.0),      # stopped
        robot_xy=(0.0, 0.0),
        robot_heading=0.0,
        obstacles=[(0.4, 0.0, 0.15)],     # obstacle at 0.4m, radius 0.15m → clearance 0.25m
        rollout_horizon_s=2.0,
        dt_s=0.25,
        collision_threshold_m=0.10,
    )
    result = engine.rollout(req)
    assert result.raw_collision_predicted, (
        f"Expected raw action to predict collision, got raw_min_distance={result.raw_min_distance:.3f}"
    )


# ── Test 7: mock rollout predicts safer distance for corrected action ─────────

def test_mock_rollout_safe_action_clears_obstacle():
    engine = CounterfactualRolloutEngine(backend="mock", collision_threshold_m=0.10)
    req = CounterfactualRolloutRequest(
        raw_action=(0.5, 0.0, 0.0),
        safe_action=(0.0, 0.0, 0.0),      # stopped → stays at (0, 0), clearance = 0.25m
        robot_xy=(0.0, 0.0),
        robot_heading=0.0,
        obstacles=[(0.4, 0.0, 0.15)],
        rollout_horizon_s=2.0,
        dt_s=0.25,
        collision_threshold_m=0.10,
    )
    result = engine.rollout(req)
    assert not result.safe_collision_predicted, (
        f"Expected safe action to avoid collision, got safe_min_distance={result.safe_min_distance:.3f}"
    )
    assert result.safe_min_distance > result.raw_min_distance


# ── Test 8: benchmark runner writes intervention_evidence.jsonl ───────────────

def test_runner_writes_intervention_evidence(tmp_path):
    from fleet_safe_vla.benchmarks.visualnav_runner import VisualNavBenchmarkRunner
    from fleet_safe_vla.benchmarks.visualnav_scenarios import SceneSpec, StartGoalPair, ObstacleSpec

    adapter = _MockAdapter()
    runner = VisualNavBenchmarkRunner(
        adapter=adapter,
        fleetsafe=True,
        backend="mock",
        output_dir=tmp_path,
        max_steps=5,
    )
    obs = ObstacleSpec(x=1.0, y=0.0, radius_m=0.15)
    scene = SceneSpec(
        name="test_scene",
        description="evidence replay test scene",
        arena_size_m=4.0,
        start_goal_pairs=(StartGoalPair(
            start_xy=(0.0, 0.0),
            goal_xy=(2.0, 0.0),
            label="sg0",
        ),),
        obstacles=(obs,),
        dynamic_agents=(),
    )

    runner.run(scenes=[scene], seeds=[0], run_id="test_run")

    ep_dirs = sorted((tmp_path / "test_run" / "episodes").iterdir())
    assert len(ep_dirs) == 1, f"Expected 1 episode dir, got {len(ep_dirs)}"
    ev_path = ep_dirs[0] / "intervention_evidence.jsonl"
    assert ev_path.exists(), f"intervention_evidence.jsonl not written to {ep_dirs[0]}"

    records = [json.loads(ln) for ln in ev_path.read_text().splitlines() if ln.strip()]
    assert len(records) == 5, f"Expected 5 step records (max_steps=5), got {len(records)}"
    for rec in records:
        assert "raw_action" in rec
        assert "safe_action" in rec
        assert "action_delta" in rec
        assert "scene_graph_delta" in rec
        assert "reproducibility_hash" in rec


# ── Test 9: artifact validator fails if interventions > 0 and no evidence ─────

def test_validator_fails_if_interventions_but_no_evidence(tmp_path):
    from scripts.visualnav.validate_benchmark_artifact import (
        _validate_episode_directory,
    )

    ep_dir = tmp_path / "episode_0001"
    ep_dir.mkdir()

    # Write required files
    (ep_dir / "episode.json").write_text(json.dumps({
        "model": "gnm", "backend": "mock", "seed": 0, "scene": "test", "success": False,
    }))
    (ep_dir / "trajectory.csv").write_text("step,x,y,heading,latency_ms\n")
    (ep_dir / "actions.csv").write_text(
        "step,raw_vx,raw_vy,raw_wz,safe_vx,safe_vy,safe_wz,delta_l2,intervened,min_dist_m\n"
    )
    (ep_dir / "safety_events.jsonl").write_text("")
    (ep_dir / "metrics.json").write_text(json.dumps({"intervention_count": 3}))
    # Write EMPTY evidence file (but intervention_count > 0)
    (ep_dir / "intervention_evidence.jsonl").write_text("")

    violations = _validate_episode_directory(ep_dir, backend="mock")
    assert any("intervention_evidence" in v for v in violations), (
        f"Expected intervention_evidence violation, got: {violations}"
    )


# ── Test 10: Isaac rollout backend raises NotImplementedError ─────────────────

def test_isaac_rollout_backend_raises_not_implemented():
    engine = CounterfactualRolloutEngine(backend="isaac")
    req = CounterfactualRolloutRequest(
        raw_action=(0.3, 0.0, 0.0),
        safe_action=(0.1, 0.0, 0.0),
        robot_xy=(0.0, 0.0),
        robot_heading=0.0,
        obstacles=[(1.0, 0.0, 0.15)],
    )
    with pytest.raises(NotImplementedError, match="Isaac branching rollout pending"):
        engine.rollout(req)


# ── Test 11: no-change graph returns empty delta ──────────────────────────────

def test_identical_graphs_produce_empty_delta():
    graph = _make_graph(step=0)
    delta = diff_scene_graphs(graph, graph)
    assert delta.added_nodes   == []
    assert delta.removed_nodes == []
    assert delta.added_edges   == []
    assert delta.removed_edges == []
    # changed_attributes may be empty; changed_edges may also be empty
    assert delta.changed_attributes == {}


# ── Test 12: obstacle approaches — delta shows distance changed ───────────────

def test_delta_detects_obstacle_closer():
    before = _make_graph(step=0, robot_xy=(0.0, 0.0), obstacle_xy=(0.5, 0.0))
    after  = _make_graph(step=1, robot_xy=(0.2, 0.0), obstacle_xy=(0.5, 0.0))
    delta  = diff_scene_graphs(before, after)
    # At least one edge's distance_m should have decreased in changed_edges
    # OR a new edge was added (near/violates_margin)
    has_change = bool(delta.added_edges) or bool(delta.changed_edges)
    assert has_change, "Expected delta to show obstacle got closer, but delta is empty"


# ── Test 13: EventRecorder coverage — evidence recorder produces correct count ─

def test_event_recorder_writes_evidence_for_all_steps(tmp_path):
    n_steps = 4
    recorder = EventRecorder(
        model_name="gnm",
        backend="mock",
        fleetsafe=True,
        scene="test_scene",
        seed=0,
        episode_id="gnm_mock_test_scene_seed0_ep0001",
    )

    for step in range(n_steps):
        rec, _ = _make_step_record(
            step=step,
            raw_vx=0.3,
            safe_vx=0.08 if step % 2 == 0 else 0.3,
            intervened=(step % 2 == 0),
        )
        recorder.record(rec)

    recorder.write_all(tmp_path)

    ev_path = tmp_path / "intervention_evidence.jsonl"
    assert ev_path.exists()
    records = [json.loads(ln) for ln in ev_path.read_text().splitlines() if ln.strip()]
    assert len(records) == n_steps

    intervention_records = [r for r in records if r["intervention_applied"]]
    non_intervention_records = [r for r in records if not r["intervention_applied"]]
    assert len(intervention_records) == 2    # steps 0 and 2
    assert len(non_intervention_records) == 2  # steps 1 and 3

    for rec in records:
        assert "scene_graph_delta" in rec
        assert "counterfactual_rollout_id" in rec
        assert len(rec["reproducibility_hash"]) == 16
