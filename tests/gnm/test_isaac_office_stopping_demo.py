"""
tests/gnm/test_isaac_office_stopping_demo.py

CI tests for the v2.8 Isaac Office Stopping Demo.
No Isaac Sim required — all tests are headless.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from scripts.gnm.isaac_office_stopping_demo import (
    CLAIM_BOUNDARY_LINES,
    GOAL_RADIUS_M,
    REQUIRED_CAMERA_NAMES,
    REQUIRED_MARKER_NAMES,
    build_overlay_markers,
    build_trajectory,
    load_config,
    select_episode,
)

DOC = REPO / "docs/v2.8_isaac_office_stopping_demo.md"
CFG_PATH = REPO / "configs/gnm/isaac_office_stopping_demo.yaml"
PROVENANCE_CSV = REPO / "results/research_audit/tracka_all_methods_per_episode_metric_provenance.csv"


# ── config ────────────────────────────────────────────────────────────────────

def test_config_loads():
    cfg = load_config()
    assert isinstance(cfg, dict), "Config should be a dict"
    assert "demo" in cfg
    assert "episode_selection" in cfg
    assert "cameras" in cfg
    assert "markers" in cfg


def test_goal_radius_is_3m():
    cfg = load_config()
    assert cfg["markers"]["goal_radius_m"] == GOAL_RADIUS_M, (
        f"goal_radius_m must be {GOAL_RADIUS_M} m, got {cfg['markers']['goal_radius_m']}"
    )


def test_module_constant_goal_radius():
    assert GOAL_RADIUS_M == 3.0


# ── cameras ───────────────────────────────────────────────────────────────────

def test_required_camera_names_in_config():
    cfg = load_config()
    configured = set(cfg["cameras"]["names"])
    missing = REQUIRED_CAMERA_NAMES - configured
    assert not missing, f"Camera names missing from config: {missing}"


def test_required_camera_names_constant():
    assert REQUIRED_CAMERA_NAMES == {"overview", "start_state", "robot_pov", "goal_state"}


# ── markers ───────────────────────────────────────────────────────────────────

def test_required_marker_names_constant():
    expected = {"start", "goal", "goal_radius", "robot", "closest_to_goal", "final_stop"}
    assert REQUIRED_MARKER_NAMES == expected


# ── episode selection ─────────────────────────────────────────────────────────

@pytest.mark.skipif(not PROVENANCE_CSV.exists(), reason="provenance CSV not found")
def test_auto_osr_not_sr_selects_valid_episode():
    cfg = load_config()
    ep = select_episode(cfg, "baseline_gnm", "auto_osr_not_sr")
    assert ep["oracle_success_flag"].strip() == "True", (
        f"Selected episode must have OSR=True, got {ep['oracle_success_flag']}"
    )
    assert ep["success_flag"].strip() == "False", (
        f"Selected episode must have SR=False, got {ep['success_flag']}"
    )


@pytest.mark.skipif(not PROVENANCE_CSV.exists(), reason="provenance CSV not found")
def test_auto_osr_not_sr_selects_smallest_min_dist():
    """The auto-selector should prefer the episode with the deepest goal penetration."""
    import csv
    cfg = load_config()
    ep = select_episode(cfg, "baseline_gnm", "auto_osr_not_sr")
    selected_min = float(ep["minimum_distance_to_goal"])

    with PROVENANCE_CSV.open() as f:
        all_rows = list(csv.DictReader(f))
    candidates = [
        r for r in all_rows
        if r["method"] == "baseline_gnm"
        and r["oracle_success_flag"].strip() == "True"
        and r["success_flag"].strip() == "False"
    ]
    min_of_all = min(float(r["minimum_distance_to_goal"]) for r in candidates)
    assert selected_min <= min_of_all + 1e-6, (
        f"Expected smallest min_dist {min_of_all}, selected {selected_min}"
    )


@pytest.mark.skipif(not PROVENANCE_CSV.exists(), reason="provenance CSV not found")
def test_selected_episode_inside_goal_radius():
    cfg = load_config()
    ep = select_episode(cfg, "baseline_gnm", "auto_osr_not_sr")
    min_dist = float(ep["minimum_distance_to_goal"])
    r = float(ep["success_radius"])
    assert min_dist < r, (
        f"Episode min_dist {min_dist}m should be < success_radius {r}m (OSR requires entry)"
    )


@pytest.mark.skipif(not PROVENANCE_CSV.exists(), reason="provenance CSV not found")
def test_selected_episode_final_dist_outside_goal_radius():
    cfg = load_config()
    ep = select_episode(cfg, "baseline_gnm", "auto_osr_not_sr")
    final_dist = float(ep["final_distance_to_goal"])
    r = float(ep["success_radius"])
    assert final_dist >= r, (
        f"Episode final_dist {final_dist}m should be >= success_radius {r}m (SR=False)"
    )


# ── trajectory ────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not PROVENANCE_CSV.exists(), reason="provenance CSV not found")
def test_trajectory_min_dist_matches_episode():
    import math
    cfg = load_config()
    ep = select_episode(cfg, "baseline_gnm", "auto_osr_not_sr")
    traj = build_trajectory(ep)
    expected_min = float(ep["minimum_distance_to_goal"])
    actual_min = min(math.dist(xy, traj["goal_xy"]) for xy in traj["waypoints"])
    assert actual_min <= expected_min + 0.01, (
        f"Trajectory closest approach {actual_min:.3f}m > expected {expected_min}m"
    )


@pytest.mark.skipif(not PROVENANCE_CSV.exists(), reason="provenance CSV not found")
def test_trajectory_final_dist_matches_episode():
    import math
    cfg = load_config()
    ep = select_episode(cfg, "baseline_gnm", "auto_osr_not_sr")
    traj = build_trajectory(ep)
    final_xy = traj["waypoints"][-1]
    actual_final = math.dist(final_xy, traj["goal_xy"])
    expected_final = float(ep["final_distance_to_goal"])
    assert abs(actual_final - expected_final) <= 0.1, (
        f"Trajectory final dist {actual_final:.3f}m != expected {expected_final}m"
    )


def test_trajectory_has_waypoints():
    ep = {
        "episode_id": "test_ep", "method": "baseline_gnm",
        "success_radius": "3.0",
        "final_distance_to_goal": "4.55",
        "minimum_distance_to_goal": "1.40",
        "success_flag": "False",
        "oracle_success_flag": "True",
        "navigation_error": "4.55",
    }
    traj = build_trajectory(ep)
    assert len(traj["waypoints"]) > 10
    assert traj["synthetic"] is True
    assert traj["success_radius"] == 3.0


# ── overlays ──────────────────────────────────────────────────────────────────

def test_overlay_markers_empty_when_no_overlays():
    ep = {"minimum_distance_to_goal": "1.4", "final_distance_to_goal": "4.55",
          "success_radius": "3.0"}
    traj = build_trajectory(ep)
    markers = build_overlay_markers(ep, traj, [])
    assert markers == {}


def test_overlay_geometry_oracle_at_closest_approach():
    import math
    ep = {"minimum_distance_to_goal": "1.4", "final_distance_to_goal": "4.55",
          "success_radius": "3.0"}
    traj = build_trajectory(ep)
    markers = build_overlay_markers(ep, traj, ["geometry_oracle"])
    assert "geometry_oracle" in markers
    oracle_xy = markers["geometry_oracle"]
    dist = math.dist(oracle_xy, traj["goal_xy"])
    assert dist <= 3.0, f"Oracle stop should be within goal radius, got dist={dist:.3f}m"


def test_overlay_temporal_stop_head_within_goal_radius():
    import math
    ep = {"minimum_distance_to_goal": "1.4", "final_distance_to_goal": "4.55",
          "success_radius": "3.0"}
    traj = build_trajectory(ep)
    markers = build_overlay_markers(ep, traj, ["temporal_stop_head"])
    assert "temporal_stop_head" in markers
    dist = math.dist(markers["temporal_stop_head"], traj["goal_xy"])
    assert dist <= 3.0, f"temporal_stop_head stop should be within goal radius, got {dist:.3f}m"


# ── claim boundaries ──────────────────────────────────────────────────────────

def test_claim_boundary_lines_not_empty():
    assert len(CLAIM_BOUNDARY_LINES) >= 5


def test_claim_boundary_no_deployment():
    joined = " ".join(CLAIM_BOUNDARY_LINES).lower()
    assert "yahboom" in joined or "deployment" in joined, (
        "Claim boundary text must mention deployment constraint"
    )


def test_claim_boundary_oracle_diagnostic():
    joined = " ".join(CLAIM_BOUNDARY_LINES).lower()
    assert "diagnostic" in joined, (
        "Claim boundary text must label oracle as diagnostic only"
    )


def test_doc_claim_boundaries_present():
    assert DOC.exists(), f"Demo doc not found: {DOC}"
    text = DOC.read_text()
    required_phrases = [
        "Visual evidence demo only",
        "No physical Yahboom",
        "No Track B completion claim",
        "No global superiority claim",
        "DIAGNOSTIC ONLY",
    ]
    for phrase in required_phrases:
        assert phrase in text, f"Claim boundary phrase missing from doc: '{phrase}'"


def test_doc_claim_boundary_section_exists():
    text = DOC.read_text()
    assert "## Claim boundaries" in text or "Claim boundaries" in text


# ── dry-run integration ───────────────────────────────────────────────────────

@pytest.mark.skipif(not PROVENANCE_CSV.exists(), reason="provenance CSV not found")
def test_dry_run_main(capsys):
    from scripts.gnm.isaac_office_stopping_demo import main
    main(["--dry-run"])
    out = capsys.readouterr().out
    assert "dry-run" in out
    assert "config loaded OK" in out
