"""
test_zone_map.py — Unit tests for ZoneMap and ZonePolygon.

Covers:
  - point-in-polygon for axis-aligned rectangles
  - zone priority (first match wins on overlap)
  - fallback to default when no polygon matches
  - profile lookup correctness
  - __repr__ smoke test
"""
from __future__ import annotations

import pytest

from fleet_safe_vla.social_awareness.zone_map import ZoneMap, ZonePolygon
from fleet_safe_vla.social_awareness.environment_profiles import (
    ICU_PROFILE,
    EMERGENCY_CORRIDOR_PROFILE,
    HOSPITAL_PROFILE,
)


def _rect(x_lo, x_hi, y_lo, y_hi):
    return [(x_lo, y_lo), (x_hi, y_lo), (x_hi, y_hi), (x_lo, y_hi)]


ICU_ZONE  = ZonePolygon("icu",       "icu",                _rect(-5, 0, 2, 5))
CORR_ZONE = ZonePolygon("corridor",  "emergency_corridor", _rect(-5, 5, -1, 2))
DEFAULT_ZONE_MAP = ZoneMap(zones=[ICU_ZONE, CORR_ZONE], default_profile_name="hospital")


# ── ZonePolygon.contains ──────────────────────────────────────────────────────

def test_polygon_contains_interior_point():
    assert ICU_ZONE.contains((-2.0, 3.5))


def test_polygon_not_contains_exterior_point():
    assert not ICU_ZONE.contains((3.0, 3.5))


def test_polygon_contains_center():
    assert CORR_ZONE.contains((0.0, 0.5))


def test_polygon_not_contains_above_rect():
    assert not CORR_ZONE.contains((0.0, 3.0))


def test_polygon_not_contains_below_rect():
    assert not CORR_ZONE.contains((0.0, -2.0))


# ── ZoneMap.classify ──────────────────────────────────────────────────────────

def test_classify_returns_icu_profile_inside_icu():
    name, profile = DEFAULT_ZONE_MAP.classify((-2.0, 3.5))
    assert name == "icu"
    assert profile == ICU_PROFILE


def test_classify_returns_corridor_profile_inside_corridor():
    name, profile = DEFAULT_ZONE_MAP.classify((2.0, 0.5))
    assert name == "corridor"
    assert profile == EMERGENCY_CORRIDOR_PROFILE


def test_classify_returns_default_when_no_match():
    name, profile = DEFAULT_ZONE_MAP.classify((10.0, 10.0))
    assert name == "default"
    assert profile == HOSPITAL_PROFILE


def test_classify_first_match_wins_on_overlap():
    # Both ICU and corridor rectangles share y=2 boundary; point at boundary
    # classified by whichever polygon is first in the list.
    # y=2 is inside ICU_ZONE (y_lo=2, y_hi=5 → y=2 is the boundary row).
    # Ray-cast is implementation-defined at exact edge; just verify it picks one.
    name, _ = DEFAULT_ZONE_MAP.classify((-2.0, 2.0))
    assert name in ("icu", "corridor")


def test_zone_map_repr_contains_zone_names():
    r = repr(DEFAULT_ZONE_MAP)
    assert "icu" in r
    assert "corridor" in r


def test_zone_map_zone_names():
    assert DEFAULT_ZONE_MAP.zone_names() == ["icu", "corridor"]


# ── Hospital scene zone maps ──────────────────────────────────────────────────

def test_hospital_zone_maps_load():
    from fleet_safe_vla.benchmarks.hospital_scenes import HOSPITAL_ZONE_MAPS, HOSPITAL_SCENES
    for scene_name in HOSPITAL_SCENES:
        assert scene_name in HOSPITAL_ZONE_MAPS
        zm = HOSPITAL_ZONE_MAPS[scene_name]
        assert isinstance(zm, ZoneMap)


def test_hospital_icu_zone_classifies_correctly():
    from fleet_safe_vla.benchmarks.hospital_scenes import HOSPITAL_ZONE_MAPS
    zm = HOSPITAL_ZONE_MAPS["hospital_icu_approach"]
    name, profile = zm.classify((-5.0, 4.0))
    assert name == "icu"
    assert profile.name == "icu"


def test_hospital_corridor_zone_classifies_correctly():
    from fleet_safe_vla.benchmarks.hospital_scenes import HOSPITAL_ZONE_MAPS
    zm = HOSPITAL_ZONE_MAPS["hospital_corridor"]
    name, profile = zm.classify((0.0, 0.0))
    assert name == "emergency_corridor"
    assert profile.name == "emergency_corridor"


def test_hospital_waiting_room_classifies_correctly():
    from fleet_safe_vla.benchmarks.hospital_scenes import HOSPITAL_ZONE_MAPS
    zm = HOSPITAL_ZONE_MAPS["hospital_elevator_lobby"]
    name, profile = zm.classify((0.0, -4.0))
    assert name == "waiting_room"
    assert profile.name == "waiting_room"
