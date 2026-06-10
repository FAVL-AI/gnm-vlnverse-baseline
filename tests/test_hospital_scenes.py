"""
test_hospital_scenes.py — Hospital scene geometry, profiles, and zone activation.

Covers:
  - Hospital scenes are in HOSPITAL_SCENES dict
  - Zone maps load without error
  - ICU profile is more conservative than emergency corridor profile
  - Hospital semantic scenes have correct agent roles
  - SocialRiskFilter with zone_map switches profiles by position
"""
from __future__ import annotations

import pytest

from fleet_safe_vla.benchmarks.hospital_scenes import (
    HOSPITAL_SCENES,
    HOSPITAL_ZONE_MAPS,
    SCENE_HOSPITAL_CORRIDOR,
    SCENE_HOSPITAL_ICU_APPROACH,
    SCENE_HOSPITAL_ELEVATOR_LOBBY,
)
from fleet_safe_vla.social_awareness.environment_profiles import (
    ICU_PROFILE,
    EMERGENCY_CORRIDOR_PROFILE,
    WAITING_ROOM_PROFILE,
)


# ── Scene registry ────────────────────────────────────────────────────────────

def test_hospital_scenes_dict_has_three_entries():
    assert len(HOSPITAL_SCENES) == 3


def test_hospital_corridor_in_registry():
    assert "hospital_corridor" in HOSPITAL_SCENES


def test_hospital_icu_approach_in_registry():
    assert "hospital_icu_approach" in HOSPITAL_SCENES


def test_hospital_elevator_lobby_in_registry():
    assert "hospital_elevator_lobby" in HOSPITAL_SCENES


# ── Zone maps ────────────────────────────────────────────────────────────────

def test_all_hospital_scenes_have_zone_maps():
    for name in HOSPITAL_SCENES:
        assert name in HOSPITAL_ZONE_MAPS, f"Missing ZoneMap for {name}"


# ── Profile conservatism ordering ─────────────────────────────────────────────

def test_icu_speed_lower_than_emergency_corridor():
    assert ICU_PROFILE.max_speed_nominal_ms < EMERGENCY_CORRIDOR_PROFILE.max_speed_nominal_ms


def test_icu_stop_distance_larger_than_emergency_corridor():
    assert ICU_PROFILE.stop_distance_red_m > EMERGENCY_CORRIDOR_PROFILE.stop_distance_red_m


def test_icu_amber_crowding_threshold_lower():
    assert ICU_PROFILE.amber_crowding_agents < EMERGENCY_CORRIDOR_PROFILE.amber_crowding_agents


def test_waiting_room_crowding_radius_geq_hospital():
    from fleet_safe_vla.social_awareness.environment_profiles import HOSPITAL_PROFILE
    assert WAITING_ROOM_PROFILE.crowding_radius_m >= HOSPITAL_PROFILE.crowding_radius_m


# ── Scene agent semantic roles ────────────────────────────────────────────────

def test_hospital_corridor_has_nurse_agents():
    roles = [a.semantic_role for a in SCENE_HOSPITAL_CORRIDOR.dynamic_agents]
    assert "nurse" in roles


def test_hospital_corridor_has_gurney():
    roles = [a.semantic_role for a in SCENE_HOSPITAL_CORRIDOR.dynamic_agents]
    assert "gurney" in roles


def test_icu_approach_has_wheelchair_user():
    roles = [a.semantic_role for a in SCENE_HOSPITAL_ICU_APPROACH.dynamic_agents]
    assert "wheelchair_user" in roles


def test_icu_approach_has_patient():
    roles = [a.semantic_role for a in SCENE_HOSPITAL_ICU_APPROACH.dynamic_agents]
    assert "patient" in roles


def test_elevator_lobby_has_visitor():
    roles = [a.semantic_role for a in SCENE_HOSPITAL_ELEVATOR_LOBBY.dynamic_agents]
    assert "visitor" in roles


def test_all_agent_types_are_human_or_robot():
    for scene in HOSPITAL_SCENES.values():
        for a in scene.dynamic_agents:
            assert a.agent_type in ("human", "robot", "unknown"), (
                f"Unexpected agent_type {a.agent_type!r} in {scene.name}"
            )


# ── ZoneMap + SocialRiskFilter integration ────────────────────────────────────

def test_social_filter_uses_icu_profile_inside_icu_zone():
    """SocialRiskFilter with zone_map returns ICU profile when robot is in ICU."""
    from fleet_safe_vla.social_awareness.social_risk_filter import SocialRiskFilter
    from fleet_safe_vla.social_awareness.dynamic_agent_tracker import AgentType, Detection
    from fleet_safe_vla.social_awareness.environment_profiles import EMERGENCY_CORRIDOR_PROFILE

    zm = HOSPITAL_ZONE_MAPS["hospital_icu_approach"]
    filt = SocialRiskFilter(profile=EMERGENCY_CORRIDOR_PROFILE, zone_map=zm)

    # Position inside ICU zone (x=-5, y=4)
    output = filt.compute(
        timestamp=0.0,
        robot_xy=(-5.0, 4.0),
        robot_speed_ms=0.1,
        robot_yaw=0.0,
        detections=[],
        obstacle_positions=[],
    )
    assert output.current_zone_name == "icu"
    assert output.current_profile_name == "icu"


def test_social_filter_uses_corridor_profile_in_corridor():
    """SocialRiskFilter switches to emergency_corridor profile in corridor zone."""
    from fleet_safe_vla.social_awareness.social_risk_filter import SocialRiskFilter
    from fleet_safe_vla.social_awareness.environment_profiles import HOSPITAL_PROFILE

    zm = HOSPITAL_ZONE_MAPS["hospital_corridor"]
    filt = SocialRiskFilter(profile=HOSPITAL_PROFILE, zone_map=zm)

    output = filt.compute(
        timestamp=0.0,
        robot_xy=(0.0, 0.0),
        robot_speed_ms=0.2,
        robot_yaw=0.0,
        detections=[],
        obstacle_positions=[],
    )
    assert output.current_zone_name == "emergency_corridor"
    assert output.current_profile_name == "emergency_corridor"


def test_social_filter_falls_back_to_default_outside_all_zones():
    """Robot outside all defined zones uses the constructor profile."""
    from fleet_safe_vla.social_awareness.social_risk_filter import SocialRiskFilter
    from fleet_safe_vla.social_awareness.environment_profiles import HOSPITAL_PROFILE

    zm = HOSPITAL_ZONE_MAPS["hospital_corridor"]
    filt = SocialRiskFilter(profile=HOSPITAL_PROFILE, zone_map=zm)

    output = filt.compute(
        timestamp=0.0,
        robot_xy=(50.0, 50.0),   # far outside any zone polygon
        robot_speed_ms=0.2,
        robot_yaw=0.0,
        detections=[],
        obstacle_positions=[],
    )
    assert output.current_zone_name == "default"
    assert output.current_profile_name == "hospital"


def test_social_filter_zone_output_in_state():
    """SocialRiskState carries current_zone_name and current_profile_name."""
    from fleet_safe_vla.social_awareness.social_risk_filter import SocialRiskFilter
    from fleet_safe_vla.social_awareness.environment_profiles import HOSPITAL_PROFILE

    zm = HOSPITAL_ZONE_MAPS["hospital_elevator_lobby"]
    filt = SocialRiskFilter(profile=HOSPITAL_PROFILE, zone_map=zm)

    output = filt.compute(
        timestamp=0.0,
        robot_xy=(0.0, -4.0),
        robot_speed_ms=0.1,
        robot_yaw=0.0,
        detections=[],
        obstacle_positions=[],
    )
    assert output.state.current_zone_name == "waiting_room"
    assert output.state.current_profile_name == "waiting_room"


# ── ALL_SCENES registration ───────────────────────────────────────────────────

def test_hospital_scenes_in_all_scenes():
    from fleet_safe_vla.benchmarks.visualnav_scenarios import ALL_SCENES
    for name in HOSPITAL_SCENES:
        assert name in ALL_SCENES, f"{name!r} missing from ALL_SCENES"


def test_all_scenes_minimum_count():
    from fleet_safe_vla.benchmarks.visualnav_scenarios import ALL_SCENES
    n = len(ALL_SCENES)
    assert n >= 14, (
        f"Expected at least 14 scenes (11 base + 3 hospital), got {n}: "
        f"{list(ALL_SCENES.keys())}"
    )


def test_get_scenes_hospital_corridor():
    from fleet_safe_vla.benchmarks.visualnav_scenarios import get_scenes
    scenes = get_scenes("hospital_corridor")
    assert len(scenes) == 1
    assert scenes[0].name == "hospital_corridor"


def test_get_scenes_all_hospital_names():
    from fleet_safe_vla.benchmarks.visualnav_scenarios import get_scenes
    result = get_scenes("hospital_corridor,hospital_icu_approach,hospital_elevator_lobby")
    names = [s.name for s in result]
    assert names == ["hospital_corridor", "hospital_icu_approach", "hospital_elevator_lobby"]


def test_get_scenes_all_includes_hospital():
    from fleet_safe_vla.benchmarks.visualnav_scenarios import get_scenes
    all_scenes = get_scenes("all")
    names = {s.name for s in all_scenes}
    assert "hospital_corridor"       in names
    assert "hospital_icu_approach"   in names
    assert "hospital_elevator_lobby" in names


def test_get_scenes_unknown_raises():
    from fleet_safe_vla.benchmarks.visualnav_scenarios import get_scenes
    with pytest.raises(ValueError, match="Unknown scene"):
        get_scenes("nonexistent_scene")
