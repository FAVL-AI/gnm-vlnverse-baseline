"""
tests/test_isaac_replay_contract.py

Tests for the Isaac Intervention Replay Viewer contract:
  - Missing artifact detection
  - Graph edge parsing and color mapping
  - Intervention frame detection
  - Action delta render inputs
  - Counterfactual loading
  - Version mismatch detection
  - Overlay text generation
  - Trajectory trail building
  - Timeline navigation
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fleet_safe_vla.envs.isaaclab.replay.replay_scene import (
    ArtifactLoader,
    ArtifactManifest,
    ReplayFrame,
    _extract_obstacles,
    _extract_edges,
    _extract_goal,
    _robot_xy_from_graph,
)
from fleet_safe_vla.envs.isaaclab.replay.replay_overlay import (
    OverlayData,
    build_overlay,
)
from fleet_safe_vla.envs.isaaclab.replay.scene_graph_visualizer import (
    EDGE_COLOR_MAP,
    SceneGraphRenderer,
    CounterfactualRenderData,
)
from fleet_safe_vla.envs.isaaclab.replay.trajectory_visualizer import (
    TrajectoryData,
    ReplayTimeline,
    build_action_vectors,
)
from fleet_safe_vla.envs.isaaclab.replay.intervention_replay import (
    InterventionReplayViewer,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _make_evidence_record(
    step: int = 0,
    intervention: bool = False,
    robot_xy: tuple = (1.0, 0.5),
    obstacle_xy: tuple = (1.5, 0.5),
    obs_dist: float = 0.35,
    raw_action: list = None,
    safe_action: list = None,
    backend: str = "mock",
    model_name: str = "gnm",
) -> dict:
    raw_action  = raw_action  or [0.28, 0.0, 0.12]
    safe_action = safe_action or [0.08, 0.0, 0.12]
    delta       = [safe_action[i] - raw_action[i] for i in range(3)]
    return {
        "episode_id":              "test_ep_0001",
        "step_idx":                step,
        "timestamp":               float(step) * 0.25,
        "scene_id":                "narrow_passage",
        "model_name":              model_name,
        "backend":                 backend,
        "benchmark_version":       "0.1.0",
        "protocol_version":        "0.1.0",
        "raw_action":              raw_action,
        "safe_action":             safe_action,
        "action_delta":            delta,
        "intervention_applied":    intervention,
        "intervention_reason":     "FleetSafe reduced vx" if intervention else "",
        "safety_margin_before":    obs_dist,
        "safety_margin_after":     obs_dist + 0.02,
        "nearest_obstacle_id":     "obstacle_0",
        "nearest_obstacle_distance_m": obs_dist,
        "active_constraints": (
            ["robot→obstacle_0:violates_margin@0.18m"] if intervention else []
        ),
        "causal_explanation": (
            "FleetSafe reduced vx because obstacle was within margin." if intervention
            else "No intervention this step."
        ),
        "counterfactual_explanation": (
            "If obstacle_0 were 0.13m farther, action would be accepted." if intervention
            else "No intervention this step."
        ),
        "counterfactual_rollout_id": "abc12345",
        "rgb_frame_ref":   "",
        "depth_frame_ref": "",
        "lidar_ref":       "",
        "trajectory_ref":  "trajectory.csv",
        "reproducibility_hash": "a" * 16,
        "scene_graph_before": {
            "step": step, "timestamp_s": float(step) * 0.25,
            "nodes": [
                {"node_id": "robot",      "node_type": "robot",
                 "position": list(robot_xy),    "radius_m": 0.15, "velocity": [0.08, 0.0], "metadata": {}},
                {"node_id": "obstacle_0", "node_type": "obstacle",
                 "position": list(obstacle_xy), "radius_m": 0.15, "velocity": [0.0,  0.0], "metadata": {}},
                {"node_id": "goal",       "node_type": "goal",
                 "position": [3.0, 0.5],         "radius_m": 0.20, "velocity": [0.0,  0.0], "metadata": {}},
            ],
            "edges": [
                {"source_id": "robot", "target_id": "obstacle_0",
                 "relation": "violates_margin", "distance_m": obs_dist, "attributes": {}},
                {"source_id": "robot", "target_id": "obstacle_0",
                 "relation": "near", "distance_m": obs_dist, "attributes": {}},
            ] if intervention else [
                {"source_id": "robot", "target_id": "obstacle_0",
                 "relation": "near", "distance_m": obs_dist, "attributes": {}},
            ],
        },
        "scene_graph_after": {
            "step": step + 1, "timestamp_s": float(step + 1) * 0.25,
            "nodes": [
                {"node_id": "robot",      "node_type": "robot",
                 "position": [robot_xy[0] + 0.02, robot_xy[1]], "radius_m": 0.15,
                 "velocity": [0.08, 0.0], "metadata": {}},
                {"node_id": "obstacle_0", "node_type": "obstacle",
                 "position": list(obstacle_xy), "radius_m": 0.15, "velocity": [0.0, 0.0], "metadata": {}},
                {"node_id": "goal",       "node_type": "goal",
                 "position": [3.0, 0.5],          "radius_m": 0.20, "velocity": [0.0, 0.0], "metadata": {}},
            ],
            "edges": [],
        },
        "scene_graph_delta": {
            "added_nodes": [], "removed_nodes": [],
            "changed_attributes": {},
            "added_edges":   [],
            "removed_edges": [
                {"source_id": "robot", "target_id": "obstacle_0",
                 "relation": "violates_margin", "distance_m": obs_dist, "attributes": {}}
            ] if intervention else [],
            "changed_edges": [],
        },
    }


def _write_episode_dir(
    tmp_path: Path,
    n_steps: int = 5,
    n_interventions: int = 2,
    backend: str = "mock",
    include_metadata: bool = True,
) -> Path:
    ep_dir = tmp_path / "episode_0001"
    ep_dir.mkdir()

    # intervention_evidence.jsonl
    records = []
    for step in range(n_steps):
        is_intervention = (step % (n_steps // max(1, n_interventions)) == 1)
        records.append(_make_evidence_record(
            step=step,
            intervention=is_intervention and n_interventions > 0,
            backend=backend,
        ))
    ev_path = ep_dir / "intervention_evidence.jsonl"
    with ev_path.open("w") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")

    # metadata.yaml (written in run_dir = tmp_path)
    if include_metadata:
        meta_lines = [
            "run_id: test_run",
            "model: gnm",
            "backend: mock",
            "benchmark_version: 0.1.0",
            "protocol_version: 0.1.0",
            "git_commit: abc1234",
        ]
        (tmp_path / "metadata.yaml").write_text("\n".join(meta_lines) + "\n")

    return ep_dir


# ── Test 1: missing artifact detection ────────────────────────────────────────

def test_missing_evidence_file_detected(tmp_path):
    ep_dir = tmp_path / "episode_empty"
    ep_dir.mkdir()
    loader = ArtifactLoader(ep_dir)
    manifest = loader.check_manifest()
    assert "intervention_evidence.jsonl" in manifest.missing_required
    assert not manifest.is_valid


def test_missing_metadata_detected(tmp_path):
    ep_dir = _write_episode_dir(tmp_path, include_metadata=False)
    loader = ArtifactLoader(ep_dir, run_dir=tmp_path)
    manifest = loader.check_manifest()
    assert "metadata.yaml" in manifest.missing_required


def test_valid_episode_manifest_passes(tmp_path):
    ep_dir = _write_episode_dir(tmp_path)
    loader = ArtifactLoader(ep_dir, run_dir=tmp_path)
    manifest = loader.check_manifest()
    assert manifest.is_valid, f"Expected valid manifest, got: {manifest.missing_required}"


# ── Test 2: graph edge parsing and color mapping ──────────────────────────────

def test_edge_parsing_extracts_relation():
    graph = {
        "nodes": [
            {"node_id": "robot",      "node_type": "robot",
             "position": [0.0, 0.0], "radius_m": 0.15, "velocity": [0.0, 0.0]},
            {"node_id": "obstacle_0", "node_type": "obstacle",
             "position": [0.4, 0.0], "radius_m": 0.15, "velocity": [0.0, 0.0]},
        ],
        "edges": [
            {"source_id": "robot", "target_id": "obstacle_0",
             "relation": "violates_margin", "distance_m": 0.10, "attributes": {}},
        ],
    }
    edges = _extract_edges(graph)
    assert len(edges) == 1
    assert edges[0].relation == "violates_margin"
    assert edges[0].distance_m == pytest.approx(0.10)


def test_edge_color_map_has_all_relations():
    expected_relations = {
        "near", "moving_towards", "occludes",
        "blocks_path", "violates_margin", "intervention_caused_by",
    }
    for rel in expected_relations:
        assert rel in EDGE_COLOR_MAP, f"Missing color for relation: {rel!r}"


def test_causal_edge_gets_red_color():
    color = EDGE_COLOR_MAP["violates_margin"]
    # Red channel should dominate
    assert color[0] > 0.7, f"Expected red-dominant color for violates_margin, got {color}"
    assert color[0] > color[1]
    assert color[0] > color[2]


def test_safe_near_edge_gets_non_red_color():
    # 'near' should be yellow (warning), not red
    color = EDGE_COLOR_MAP["near"]
    assert color[0] > 0.5, "Near should be bright"
    assert color[1] > 0.5, "Near should be yellow-ish (high G)"


# ── Test 3: intervention frame detection ──────────────────────────────────────

def test_intervention_frames_detected(tmp_path):
    ep_dir = _write_episode_dir(tmp_path, n_steps=6, n_interventions=2)
    loader = ArtifactLoader(ep_dir, run_dir=tmp_path)
    frames, _ = loader.load()
    intervention_frames = [f for f in frames if f.intervention_applied]
    assert len(intervention_frames) > 0, "Expected at least one intervention frame"
    for f in intervention_frames:
        assert f.intervention_reason != "", "Intervention frame should have a reason"


def test_non_intervention_frames_have_empty_reason(tmp_path):
    ep_dir = _write_episode_dir(tmp_path, n_steps=6, n_interventions=2)
    loader = ArtifactLoader(ep_dir, run_dir=tmp_path)
    frames, _ = loader.load()
    non_intervention = [f for f in frames if not f.intervention_applied]
    assert len(non_intervention) > 0
    for f in non_intervention:
        assert f.intervention_reason == ""


# ── Test 4: action delta render inputs ────────────────────────────────────────

def test_action_vectors_raw_preserved(tmp_path):
    ep_dir = _write_episode_dir(tmp_path, n_steps=3, n_interventions=1)
    loader = ArtifactLoader(ep_dir, run_dir=tmp_path)
    frames, _ = loader.load()
    for frame in frames:
        av = build_action_vectors(frame, heading=0.0)
        # With heading=0, world-frame vx = body-frame vx
        assert av.raw_vx_world == pytest.approx(frame.raw_action[0], abs=1e-6)
        assert av.safe_vx_world == pytest.approx(frame.safe_action[0], abs=1e-6)


def test_action_delta_l2_is_correct(tmp_path):
    ep_dir = _write_episode_dir(tmp_path, n_steps=3, n_interventions=1)
    loader = ArtifactLoader(ep_dir, run_dir=tmp_path)
    frames, _ = loader.load()
    for frame in frames:
        expected_l2 = (
            frame.action_delta[0] ** 2 +
            frame.action_delta[1] ** 2 +
            frame.action_delta[2] ** 2
        ) ** 0.5
        assert frame.action_delta_l2 == pytest.approx(expected_l2, abs=1e-9)


# ── Test 5: counterfactual loading ────────────────────────────────────────────

def test_counterfactual_rollout_runs_for_intervention_frame(tmp_path):
    ep_dir = _write_episode_dir(tmp_path, n_steps=5, n_interventions=2)
    loader = ArtifactLoader(ep_dir, run_dir=tmp_path)
    frames, _ = loader.load()

    renderer = SceneGraphRenderer()
    for frame in frames:
        if frame.intervention_applied:
            cf = renderer.build_counterfactual(frame)
            assert isinstance(cf, CounterfactualRenderData)
            assert len(cf.raw_trajectory)  > 1
            assert len(cf.safe_trajectory) > 1
            assert cf.is_mock


def test_counterfactual_rollout_id_preserved(tmp_path):
    ep_dir = _write_episode_dir(tmp_path, n_steps=3, n_interventions=1)
    loader = ArtifactLoader(ep_dir, run_dir=tmp_path)
    frames, _ = loader.load()
    for frame in frames:
        if frame.intervention_applied:
            assert frame.counterfactual_rollout_id == "abc12345"


# ── Test 6: version mismatch detection ────────────────────────────────────────

def test_version_mismatch_detected(tmp_path):
    ep_dir = _write_episode_dir(tmp_path)
    # Overwrite metadata with old version
    (tmp_path / "metadata.yaml").write_text(
        "run_id: test_run\n"
        "model: gnm\n"
        "backend: mock\n"
        "benchmark_version: 0.0.1\n"   # old — will mismatch
        "protocol_version: 0.0.1\n"
        "git_commit: abc1234\n"
    )
    loader = ArtifactLoader(ep_dir, run_dir=tmp_path)
    warnings = loader.check_version_mismatch()
    # Mismatch only if current repo version differs from artifact version
    # In CI the current version is 0.1.0; artifact says 0.0.1 → mismatch
    # (This test passes in all environments since 0.0.1 ≠ 0.1.0)
    assert any("benchmark_version" in w or "protocol_version" in w for w in warnings), (
        f"Expected version mismatch warning, got: {warnings}"
    )


def test_matching_versions_produce_no_warnings(tmp_path):
    from fleet_safe_vla.benchmark_version import BENCHMARK_VERSION, PROTOCOL_VERSION
    ep_dir = _write_episode_dir(tmp_path)
    (tmp_path / "metadata.yaml").write_text(
        "run_id: test_run\n"
        f"benchmark_version: {BENCHMARK_VERSION}\n"
        f"protocol_version: {PROTOCOL_VERSION}\n"
        "git_commit: abc1234\n"
    )
    loader = ArtifactLoader(ep_dir, run_dir=tmp_path)
    assert loader.check_version_mismatch() == []


# ── Test 7: overlay text generation ──────────────────────────────────────────

def test_overlay_contains_intervention_reason(tmp_path):
    ep_dir = _write_episode_dir(tmp_path, n_steps=3, n_interventions=1)
    loader = ArtifactLoader(ep_dir, run_dir=tmp_path)
    frames, _ = loader.load()

    intervention_frames = [f for f in frames if f.intervention_applied]
    assert intervention_frames, "Need at least one intervention frame"

    frame = intervention_frames[0]
    ov = build_overlay(frame, total_frames=len(frames))
    text = ov.to_terminal_string()
    assert "INTERVENTION" in text or "intervention" in text.lower()
    assert frame.nearest_obstacle_id in text


def test_overlay_contains_mock_warning(tmp_path):
    ep_dir = _write_episode_dir(tmp_path, n_steps=3, n_interventions=1)
    loader = ArtifactLoader(ep_dir, run_dir=tmp_path)
    frames, _ = loader.load()
    frame = frames[0]
    ov = build_overlay(frame, total_frames=len(frames))
    assert ov.is_mock_rollout
    text = ov.to_terminal_string()
    assert "MOCK" in text or "mock" in text.lower()


def test_overlay_shows_missing_artifact_warning(tmp_path):
    ep_dir = _write_episode_dir(tmp_path, n_steps=2, n_interventions=0)
    loader = ArtifactLoader(ep_dir, run_dir=tmp_path)
    frames, _ = loader.load()
    frame = frames[0]
    ov = build_overlay(
        frame, total_frames=len(frames),
        missing_artifacts=["scene_graphs.jsonl"]
    )
    text = ov.to_terminal_string()
    assert "scene_graphs.jsonl" in text


# ── Test 8: trajectory trail building ─────────────────────────────────────────

def test_trajectory_trail_colored_by_intervention(tmp_path):
    ep_dir = _write_episode_dir(tmp_path, n_steps=6, n_interventions=2)
    loader = ArtifactLoader(ep_dir, run_dir=tmp_path)
    frames, _ = loader.load()
    traj = TrajectoryData.build(frames)

    for pt in traj.points:
        frame = frames[pt.frame_idx]
        if frame.intervention_applied:
            # Red channel should dominate
            assert pt.color_rgb[0] > pt.color_rgb[1], (
                f"Intervention frame should be red, got {pt.color_rgb}"
            )


def test_trajectory_trail_up_to_frame(tmp_path):
    ep_dir = _write_episode_dir(tmp_path, n_steps=8, n_interventions=0)
    loader = ArtifactLoader(ep_dir, run_dir=tmp_path)
    frames, _ = loader.load()
    traj = TrajectoryData.build(frames)

    trail = traj.get_trail_up_to(4)
    assert len(trail) == 5   # frames 0..4
    assert all(p.frame_idx <= 4 for p in trail)


# ── Test 9: timeline navigation ───────────────────────────────────────────────

def test_timeline_step_forward(tmp_path):
    ep_dir = _write_episode_dir(tmp_path, n_steps=5, n_interventions=1)
    loader = ArtifactLoader(ep_dir, run_dir=tmp_path)
    frames, _ = loader.load()
    tl = ReplayTimeline(frames)
    assert tl.frame_idx == 0
    assert tl.step_forward()
    assert tl.frame_idx == 1


def test_timeline_jump_to_intervention(tmp_path):
    ep_dir = _write_episode_dir(tmp_path, n_steps=6, n_interventions=2)
    loader = ArtifactLoader(ep_dir, run_dir=tmp_path)
    frames, _ = loader.load()
    tl = ReplayTimeline(frames)
    result = tl.jump_to_next_intervention()
    if result:
        assert tl.current.intervention_applied


def test_timeline_at_end(tmp_path):
    ep_dir = _write_episode_dir(tmp_path, n_steps=3, n_interventions=0)
    loader = ArtifactLoader(ep_dir, run_dir=tmp_path)
    frames, _ = loader.load()
    tl = ReplayTimeline(frames)
    tl.jump_to(len(frames) - 1)
    assert not tl.step_forward()   # can't go forward at end


# ── Test 10: viewer integration ───────────────────────────────────────────────

def test_viewer_loads_and_counts_interventions(tmp_path):
    ep_dir = _write_episode_dir(tmp_path, n_steps=6, n_interventions=2)
    viewer = InterventionReplayViewer(ep_dir, run_dir=tmp_path).load()
    assert viewer.is_valid()
    assert viewer.n_frames == 6
    assert viewer.intervention_count > 0


def test_viewer_overlay_accessible_for_all_frames(tmp_path):
    ep_dir = _write_episode_dir(tmp_path, n_steps=4, n_interventions=1)
    viewer = InterventionReplayViewer(ep_dir, run_dir=tmp_path).load()
    for frame in viewer.frames:
        ov = viewer.overlay_for(frame)
        lines = ov.to_lines()
        assert len(lines) > 5


def test_viewer_requires_load_before_access(tmp_path):
    ep_dir = _write_episode_dir(tmp_path, n_steps=3, n_interventions=0)
    viewer = InterventionReplayViewer(ep_dir, run_dir=tmp_path)
    with pytest.raises(RuntimeError, match="Call load()"):
        _ = viewer.n_frames


def test_viewer_graph_edges_for_frame(tmp_path):
    ep_dir = _write_episode_dir(tmp_path, n_steps=3, n_interventions=2)
    viewer = InterventionReplayViewer(ep_dir, run_dir=tmp_path).load()
    for frame in viewer.frames:
        edges = viewer.graph_edges_for(frame)
        # Every edge must have valid color
        for edge in edges:
            assert len(edge.color_rgb) == 3
            assert all(0.0 <= c <= 1.0 for c in edge.color_rgb)
