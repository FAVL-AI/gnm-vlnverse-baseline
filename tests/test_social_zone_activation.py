"""
test_social_zone_activation.py — Verify social-risk scenes trigger correct zones.

Confirms:
  crowded_corridor      → RED at step 0 (≥4 agents within hospital crowding radius)
  crossing_pedestrian   → RED at step 0 (human 0.58 m < stop_distance_red 0.60 m)
  blind_corner          → AMBER as robot approaches (occlusion_risk > 0.3 at y=-1.5)
  social_red_zone_smoke → RED at step 0 (human 0.35 m < stop_distance_red 0.60 m)
  social scenes         → use hospital profile (not default or shopping_mall/office)
  crowding_score        → positive for crowded_corridor at step 0
"""
from __future__ import annotations

import math

import pytest

from fleet_safe_vla.benchmarks.visualnav_scenarios import (
    ALL_SCENES,
    SCENE_BLIND_CORNER,
    SCENE_CROWDED_CORRIDOR,
    SCENE_CROSSING_PEDESTRIAN,
    SCENE_SOCIAL_RED_ZONE_SMOKE,
)
from fleet_safe_vla.social_awareness.dynamic_agent_tracker import AgentType, DynamicAgent
from fleet_safe_vla.social_awareness.environment_profiles import get_profile
from fleet_safe_vla.social_awareness.occlusion_risk import OcclusionRisk
from fleet_safe_vla.social_awareness.crowding_estimator import CrowdingEstimator
from fleet_safe_vla.social_awareness.safety_zones import SafetyZone, SafetyZoneClassifier

HOSPITAL = get_profile("hospital")
CLF = SafetyZoneClassifier(HOSPITAL)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _agents_from_scene(scene, t: float = 0.0) -> list[DynamicAgent]:
    """Instantiate DynamicAgent objects from scene dynamic_agents at time t."""
    result = []
    for i, spec in enumerate(scene.dynamic_agents):
        x, y = spec.position_at(t)
        atype = AgentType.HUMAN if spec.agent_type == "human" else AgentType.ROBOT
        result.append(DynamicAgent(
            agent_id=f"agent_{i}",
            agent_type=atype,
            position_xy=(x, y),
            velocity_xy=(0.0, 0.0),
            speed_ms=0.0,
            timestamp=t,
            confidence=1.0,
        ))
    return result


# ── Scene registry ────────────────────────────────────────────────────────────

def test_all_scenes_has_fourteen_entries():
    assert len(ALL_SCENES) >= 14


def test_social_red_zone_smoke_in_registry():
    assert "social_red_zone_smoke" in ALL_SCENES


# ── Profile mapping ───────────────────────────────────────────────────────────

def test_social_scenes_use_hospital_profile():
    """Critical social scenes must map to hospital profile after the Phase-3 fix."""
    from fleet_safe_vla.benchmarks.visualnav_runner import VisualNavBenchmarkRunner

    runner = VisualNavBenchmarkRunner.__new__(VisualNavBenchmarkRunner)
    runner.social_profile = "default"

    hospital_scenes = (
        "crowded_corridor",
        "crossing_pedestrian",
        "blind_corner",
        "doorway_bottleneck",
        "social_red_zone_smoke",
    )
    for scene_name in hospital_scenes:
        filt = runner._make_social_filter(scene_name)
        assert filt is not None, f"{scene_name}: filter is None"
        assert filt._profile.name == "hospital", (
            f"{scene_name}: expected hospital profile, got {filt._profile.name!r}"
        )


def test_non_social_scene_falls_back_to_default_profile():
    """straight_corridor has no dedicated profile entry — should use runner default."""
    from fleet_safe_vla.benchmarks.visualnav_runner import VisualNavBenchmarkRunner

    runner = VisualNavBenchmarkRunner.__new__(VisualNavBenchmarkRunner)
    runner.social_profile = "default"
    filt = runner._make_social_filter("straight_corridor")
    assert filt is not None
    assert filt._profile.name == "default"


# ── Crowded corridor ──────────────────────────────────────────────────────────

def test_crowded_corridor_agents_within_radius_at_t0():
    """All 4 agents must be within hospital crowding_radius_m of robot start at t=0."""
    robot_xy = SCENE_CROWDED_CORRIDOR.start_goal_pairs[0].start_xy
    agents = _agents_from_scene(SCENE_CROWDED_CORRIDOR, t=0.0)
    rx, ry = robot_xy
    count_in_radius = sum(
        1 for a in agents
        if math.hypot(a.position_xy[0] - rx, a.position_xy[1] - ry) <= HOSPITAL.crowding_radius_m
    )
    assert count_in_radius >= HOSPITAL.red_crowding_agents, (
        f"Expected ≥{HOSPITAL.red_crowding_agents} agents in {HOSPITAL.crowding_radius_m}m radius, "
        f"got {count_in_radius}"
    )


def test_crowded_corridor_triggers_red_at_t0():
    """4 agents within hospital crowding radius → RED zone at step 0."""
    robot_xy = SCENE_CROWDED_CORRIDOR.start_goal_pairs[0].start_xy
    agents = _agents_from_scene(SCENE_CROWDED_CORRIDOR, t=0.0)
    result = CLF.classify(agents=agents, robot_xy=robot_xy,
                          crowding_score=0.0, occlusion_risk=0.0)
    assert result.zone == SafetyZone.RED, (
        f"crowded_corridor should be RED at t=0; got {result.zone}, reasons={result.reasons}"
    )


def test_crowded_corridor_crowding_score_positive():
    """CrowdingEstimator returns score > 0 for crowded_corridor at t=0."""
    est = CrowdingEstimator(max_expected_agents=10)
    robot_xy = SCENE_CROWDED_CORRIDOR.start_goal_pairs[0].start_xy
    agents = _agents_from_scene(SCENE_CROWDED_CORRIDOR, t=0.0)
    score = est.compute_crowding_score(agents, robot_xy=robot_xy,
                                       radius_m=HOSPITAL.crowding_radius_m)
    assert score > 0.0, f"crowding_score should be positive; got {score}"


def test_crowded_corridor_no_agent_collision_at_t0():
    """No agent is within collision threshold of the robot start at t=0."""
    robot_xy = SCENE_CROWDED_CORRIDOR.start_goal_pairs[0].start_xy
    rx, ry = robot_xy
    collision_m = 0.10
    for spec in SCENE_CROWDED_CORRIDOR.dynamic_agents:
        x, y = spec.position_at(0.0)
        surface_dist = math.hypot(x - rx, y - ry) - spec.obstacle_radius_m
        assert surface_dist > collision_m, (
            f"crowded_corridor agent at ({x:.2f},{y:.2f}): "
            f"surface_dist={surface_dist:.3f}m ≤ collision_m={collision_m}"
        )


# ── Crossing pedestrian ───────────────────────────────────────────────────────

def test_crossing_pedestrian_human_within_red_dist_at_t0():
    """Human must be within hospital stop_distance_red_m at t=0."""
    robot_xy = SCENE_CROSSING_PEDESTRIAN.start_goal_pairs[0].start_xy
    agents = _agents_from_scene(SCENE_CROSSING_PEDESTRIAN, t=0.0)
    rx, ry = robot_xy
    human_dists = [
        math.hypot(a.position_xy[0] - rx, a.position_xy[1] - ry)
        for a in agents if a.agent_type == AgentType.HUMAN
    ]
    assert human_dists, "No human agents found in crossing_pedestrian"
    min_dist = min(human_dists)
    assert min_dist < HOSPITAL.stop_distance_red_m, (
        f"Closest human at {min_dist:.3f}m should be < {HOSPITAL.stop_distance_red_m}m (RED)"
    )


def test_crossing_pedestrian_triggers_red_at_t0():
    """crossing_pedestrian must classify as RED at step 0."""
    robot_xy = SCENE_CROSSING_PEDESTRIAN.start_goal_pairs[0].start_xy
    agents = _agents_from_scene(SCENE_CROSSING_PEDESTRIAN, t=0.0)
    result = CLF.classify(agents=agents, robot_xy=robot_xy,
                          crowding_score=0.0, occlusion_risk=0.0)
    assert result.zone == SafetyZone.RED, (
        f"crossing_pedestrian should be RED at t=0; got {result.zone}, reasons={result.reasons}"
    )


# ── Blind corner ──────────────────────────────────────────────────────────────

def test_blind_corner_occlusion_risk_above_amber_threshold_at_mid_range():
    """Pillar at (0,0) r=0.5 subtends enough angle at robot y=-1.5 → risk > 0.3."""
    robot_xy = (0.0, -1.5)
    pillar = next(o for o in SCENE_BLIND_CORNER.obstacles if o.radius_m == 0.50)
    oc = OcclusionRisk()
    zones = oc.estimate_occlusion_zones(
        robot_xy=robot_xy,
        obstacle_positions=[(pillar.x, pillar.y)],
        obstacle_radii=[pillar.radius_m],
    )
    risk = oc.compute_risk_score(zones, robot_speed_ms=0.2)
    assert risk > 0.3, (
        f"occlusion_risk={risk:.3f} at robot y=-1.5 should be > 0.3 (AMBER threshold)"
    )


def test_blind_corner_classifier_amber_at_mid_range():
    """SafetyZoneClassifier responds to occlusion_risk > 0.3 with AMBER."""
    robot_xy = (0.0, -1.5)
    pillar = next(o for o in SCENE_BLIND_CORNER.obstacles if o.radius_m == 0.50)
    oc = OcclusionRisk()
    zones = oc.estimate_occlusion_zones(
        robot_xy=robot_xy,
        obstacle_positions=[(pillar.x, pillar.y)],
        obstacle_radii=[pillar.radius_m],
    )
    risk = oc.compute_risk_score(zones, robot_speed_ms=0.2)
    result = CLF.classify(agents=[], robot_xy=robot_xy,
                          crowding_score=0.0, occlusion_risk=risk)
    assert result.zone == SafetyZone.AMBER, (
        f"blind_corner at y=-1.5: occlusion_risk={risk:.3f} should give AMBER; "
        f"got {result.zone}"
    )


def test_blind_corner_occlusion_risk_below_amber_at_start():
    """At robot start (0,-3.0), pillar is far → occlusion_risk < 0.3 (GREEN start)."""
    robot_xy = (0.0, -3.0)
    pillar = next(o for o in SCENE_BLIND_CORNER.obstacles if o.radius_m == 0.50)
    oc = OcclusionRisk()
    zones = oc.estimate_occlusion_zones(
        robot_xy=robot_xy,
        obstacle_positions=[(pillar.x, pillar.y)],
        obstacle_radii=[pillar.radius_m],
    )
    risk = oc.compute_risk_score(zones, robot_speed_ms=0.2)
    assert risk < 0.30, (
        f"occlusion_risk={risk:.3f} at robot start (0,-3.0) should be < 0.30"
    )


# ── Social red zone smoke ─────────────────────────────────────────────────────

def test_social_red_zone_smoke_human_within_red_dist_at_t0():
    """Human 0.35m from robot start → within hospital stop_distance_red_m=0.60m."""
    robot_xy = SCENE_SOCIAL_RED_ZONE_SMOKE.start_goal_pairs[0].start_xy
    agents = _agents_from_scene(SCENE_SOCIAL_RED_ZONE_SMOKE, t=0.0)
    rx, ry = robot_xy
    human_dists = [
        math.hypot(a.position_xy[0] - rx, a.position_xy[1] - ry)
        for a in agents if a.agent_type == AgentType.HUMAN
    ]
    min_dist = min(human_dists)
    assert min_dist < HOSPITAL.stop_distance_red_m, (
        f"Closest human at {min_dist:.3f}m should be < {HOSPITAL.stop_distance_red_m}m"
    )


def test_social_red_zone_smoke_triggers_red_at_t0():
    """social_red_zone_smoke must classify as RED at step 0."""
    robot_xy = SCENE_SOCIAL_RED_ZONE_SMOKE.start_goal_pairs[0].start_xy
    agents = _agents_from_scene(SCENE_SOCIAL_RED_ZONE_SMOKE, t=0.0)
    result = CLF.classify(agents=agents, robot_xy=robot_xy,
                          crowding_score=0.0, occlusion_risk=0.0)
    assert result.zone == SafetyZone.RED, (
        f"social_red_zone_smoke should be RED at t=0; got {result.zone}, "
        f"reasons={result.reasons}"
    )


def test_social_red_zone_smoke_no_collision_at_t0():
    """Agents in smoke scene must not collide with robot at t=0 (surface_dist > 0.10m)."""
    robot_xy = SCENE_SOCIAL_RED_ZONE_SMOKE.start_goal_pairs[0].start_xy
    rx, ry = robot_xy
    collision_m = 0.10
    for spec in SCENE_SOCIAL_RED_ZONE_SMOKE.dynamic_agents:
        x, y = spec.position_at(0.0)
        surface_dist = math.hypot(x - rx, y - ry) - spec.obstacle_radius_m
        assert surface_dist > collision_m, (
            f"smoke agent at ({x:.2f},{y:.2f}): "
            f"surface_dist={surface_dist:.3f}m ≤ collision_m={collision_m}"
        )


# ── Occlusion AMBER threshold ─────────────────────────────────────────────────

def test_occlusion_threshold_is_0_3():
    """SafetyZoneClassifier triggers AMBER when occlusion_risk just exceeds 0.3."""
    result_above = CLF.classify(agents=[], robot_xy=(0.0, 0.0),
                                crowding_score=0.0, occlusion_risk=0.31)
    result_below = CLF.classify(agents=[], robot_xy=(0.0, 0.0),
                                crowding_score=0.0, occlusion_risk=0.29)
    assert result_above.zone == SafetyZone.AMBER, (
        f"occlusion_risk=0.31 should give AMBER, got {result_above.zone}"
    )
    assert result_below.zone == SafetyZone.GREEN, (
        f"occlusion_risk=0.29 should give GREEN, got {result_below.zone}"
    )
