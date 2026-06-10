"""
test_hospital_scene_builder.py — CI-safe tests for hospital scene geometry.

All tests import only pure-Python parts of hospital_scene_builder.py.
No Isaac Sim / omni.* imports are used so this runs in the standard pytest env.
"""
from __future__ import annotations

import pytest

# ── Pure-Python internals accessible without Isaac ────────────────────────────

from fleet_safe_vla.envs.isaaclab.hospital.hospital_scene_builder import (
    _ZONE_COLORS,
    _ROLE_COLORS,
    _floor_panel,
    _wall,
    _hospital_geometry,
    _Box,
    WALL_HEIGHT,
    WALL_THICKNESS,
    X_MIN, X_MAX, Y_MIN, Y_MAX,
    Y_ICU_LO, Y_CORR_LO, Y_WAIT_LO,
    X_ICU_HI, X_PHARMACY_LO,
)
from fleet_safe_vla.envs.isaaclab.hospital.hospital_world_loader import (
    HospitalWorldLoader,
    FALLBACK_ZONE_MAP,
    HOSPITAL_USD_PATH,
)
from fleet_safe_vla.envs.isaaclab.hospital import HOSPITAL_ZONES_YAML


# ── Zone colour palette ────────────────────────────────────────────────────────

def test_all_zone_colors_defined():
    for zone in ("icu", "nurse_station", "pharmacy", "emergency_corridor", "waiting_room"):
        assert zone in _ZONE_COLORS, f"Missing color for {zone}"


def test_all_zone_colors_are_rgb_triples():
    for name, color in _ZONE_COLORS.items():
        assert len(color) == 3, f"{name}: expected 3-tuple, got {color!r}"
        assert all(0.0 <= c <= 1.0 for c in color), f"{name}: color out of [0,1] range"


def test_all_role_colors_defined():
    from fleet_safe_vla.social_awareness.semantic_agents import SemanticRole
    for role in SemanticRole:
        assert role.value in _ROLE_COLORS, f"Missing role color for {role}"


def test_icu_color_is_blue():
    r, g, b = _ZONE_COLORS["icu"]
    assert b > r and b > g, "ICU should have a blue-dominant color"


def test_emergency_corridor_is_warm():
    r, g, b = _ZONE_COLORS["emergency_corridor"]
    assert r > b, "Emergency corridor should have a warm (red > blue) color"


# ── Geometry helpers ───────────────────────────────────────────────────────────

def test_floor_panel_center_is_midpoint():
    box = _floor_panel("test", -4.0, 0.0, -2.0, 2.0, (1, 0, 0))
    assert abs(box.cx - (-2.0)) < 1e-9
    assert abs(box.cy - 0.0)    < 1e-9


def test_floor_panel_half_extents():
    box = _floor_panel("test", 0.0, 6.0, 0.0, 4.0, (1, 0, 0))
    assert abs(box.hx - 3.0) < 1e-9
    assert abs(box.hy - 2.0) < 1e-9


def test_wall_height():
    box = _wall("w", 0.0, 0.0, 5.0, 0.15)
    assert abs(box.cz - WALL_HEIGHT / 2.0) < 1e-9
    assert abs(box.hz - WALL_HEIGHT / 2.0) < 1e-9


# ── Full hospital geometry ─────────────────────────────────────────────────────

def test_hospital_geometry_returns_boxes():
    boxes = _hospital_geometry()
    assert len(boxes) > 0
    assert all(isinstance(b, _Box) for b in boxes)


def test_five_floor_panels_present():
    boxes = _hospital_geometry()
    floors = [b for b in boxes if b.label.startswith("floor_")]
    assert len(floors) == 5, f"Expected 5 floor panels, got {len(floors)}"


def test_perimeter_walls_present():
    boxes = _hospital_geometry()
    labels = {b.label for b in boxes}
    for wall_name in ("wall_north", "wall_south", "wall_east", "wall_west"):
        assert wall_name in labels, f"Missing perimeter wall: {wall_name}"


def test_partition_walls_present():
    boxes = _hospital_geometry()
    labels = {b.label for b in boxes}
    assert "wall_icu_nurse" in labels
    assert "wall_nurse_pharm" in labels


def test_floor_panels_cover_correct_zones():
    boxes = _hospital_geometry()
    floor_map = {b.label: b for b in boxes if b.label.startswith("floor_")}
    # ICU floor should be in x ∈ [X_MIN, X_ICU_HI], y ∈ [Y_ICU_LO, Y_MAX]
    icu = floor_map["floor_icu"]
    assert abs(icu.cx - (X_MIN + X_ICU_HI) / 2.0) < 1e-9
    assert abs(icu.cy - (Y_ICU_LO + Y_MAX) / 2.0) < 1e-9


def test_walls_are_tall_enough():
    boxes = _hospital_geometry()
    walls = [b for b in boxes if "wall" in b.label]
    for w in walls:
        full_h = w.hz * 2.0
        assert full_h >= WALL_HEIGHT - 1e-9, f"{w.label}: wall too short ({full_h:.2f}m)"


def test_zone_pillars_present():
    boxes = _hospital_geometry()
    pillars = [b for b in boxes if b.label.startswith("pillar_")]
    assert len(pillars) == 5, f"Expected 5 zone pillars, got {len(pillars)}"


def test_pillar_colors_match_zone_colors():
    boxes = _hospital_geometry()
    for b in boxes:
        if not b.label.startswith("pillar_"):
            continue
        zone = b.label[len("pillar_"):]
        assert b.color == _ZONE_COLORS[zone], (
            f"{b.label}: color mismatch: {b.color!r} != {_ZONE_COLORS[zone]!r}"
        )


# ── HospitalWorldLoader (pure-Python API, no Isaac needed) ────────────────────

def test_fallback_zone_map_is_zone_map():
    from fleet_safe_vla.social_awareness.zone_map import ZoneMap
    assert isinstance(FALLBACK_ZONE_MAP, ZoneMap)


def test_fallback_synthetic_zones():
    loader = HospitalWorldLoader()
    zm = loader.fallback_synthetic_zones()
    from fleet_safe_vla.social_awareness.zone_map import ZoneMap
    assert isinstance(zm, ZoneMap)
    assert zm is FALLBACK_ZONE_MAP


def test_load_from_usd_raises_when_file_missing():
    loader = HospitalWorldLoader()
    with pytest.raises(FileNotFoundError):
        loader.load_from_usd("/nonexistent/path/hospital.usd")


def test_hospital_usd_path_is_path_object():
    from pathlib import Path
    assert isinstance(HOSPITAL_USD_PATH, Path)


def test_hospital_zones_yaml_exists():
    assert HOSPITAL_ZONES_YAML.exists(), f"YAML sidecar missing: {HOSPITAL_ZONES_YAML}"


def test_load_zones_from_yaml():
    loader = HospitalWorldLoader()
    zm = loader.load_zones_from_yaml(HOSPITAL_ZONES_YAML)
    from fleet_safe_vla.social_awareness.zone_map import ZoneMap
    assert isinstance(zm, ZoneMap)
    assert "icu" in zm.zone_names()
    assert "emergency_corridor" in zm.zone_names()
    assert "waiting_room" in zm.zone_names()


def test_yaml_icu_profile():
    loader = HospitalWorldLoader()
    zm = loader.load_zones_from_yaml(HOSPITAL_ZONES_YAML)
    name, profile = zm.classify((-5.0, 5.0))
    assert name == "icu"
    assert profile.name == "icu"


def test_yaml_corridor_profile():
    loader = HospitalWorldLoader()
    zm = loader.load_zones_from_yaml(HOSPITAL_ZONES_YAML)
    name, profile = zm.classify((0.0, 0.0))
    assert name == "emergency_corridor"
    assert profile.name == "emergency_corridor"


def test_yaml_waiting_room_profile():
    loader = HospitalWorldLoader()
    zm = loader.load_zones_from_yaml(HOSPITAL_ZONES_YAML)
    name, profile = zm.classify((3.0, -5.0))
    assert name == "waiting_room"
    assert profile.name == "waiting_room"
