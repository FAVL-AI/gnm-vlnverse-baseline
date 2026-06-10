"""
zone_map.py — Spatial zone partitioning for per-zone EnvironmentProfile switching.

A ZoneMap partitions a 2-D arena into named polygon regions, each associated with
an EnvironmentProfile.  At each step the robot's xy position is classified to a
zone, and the matching profile is forwarded to SafetyZoneClassifier.

Point-in-polygon uses ray-casting (O(n) per polygon, n=vertices).  No external
geometry library required.

Usage::

    from fleet_safe_vla.social_awareness.zone_map import ZoneMap, ZonePolygon

    zm = ZoneMap(
        zones=[
            ZonePolygon("icu", "icu", [(-5,0),(-5,4),(0,4),(0,0)]),
            ZonePolygon("corridor", "emergency_corridor", [(-5,-1.5),(-5,0),(5,0),(5,-1.5)]),
        ],
        default_profile_name="hospital",
    )
    zone_name, profile = zm.classify((x, y))
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from fleet_safe_vla.social_awareness.environment_profiles import (
    EnvironmentProfile,
    get_profile,
    DEFAULT_PROFILE,
)


@dataclass(frozen=True)
class ZonePolygon:
    """One named polygon zone within the arena."""
    name:         str                          # zone identifier (e.g. "icu")
    profile_name: str                          # environment profile key
    vertices:     tuple[tuple[float, float], ...]  # polygon vertices in order

    def __init__(
        self,
        name: str,
        profile_name: str,
        vertices: Sequence[tuple[float, float]],
    ) -> None:
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "profile_name", profile_name)
        object.__setattr__(self, "vertices", tuple(vertices))

    def contains(self, point: tuple[float, float]) -> bool:
        """
        Ray-casting point-in-polygon test.

        Returns True if point is inside (or on the boundary of) this polygon.
        Handles non-convex polygons correctly.
        """
        px, py = point
        verts = self.vertices
        n = len(verts)
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = verts[i]
            xj, yj = verts[j]
            if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        return inside


class ZoneMap:
    """
    Map from robot xy → (zone_name, EnvironmentProfile).

    Zones are checked in list order; the first matching polygon wins.
    If no polygon matches, the default_profile_name profile is returned with
    zone_name = "default".

    Parameters
    ----------
    zones : list of ZonePolygon
        Ordered list of zones.  Earlier entries take priority on overlap.
    default_profile_name : str
        Profile name used when no polygon matches.  Must be in ALL_PROFILES or
        a custom profile registered via register_profile().
    """

    def __init__(
        self,
        zones: list[ZonePolygon],
        default_profile_name: str = "default",
    ) -> None:
        self._zones = zones
        self._default_profile_name = default_profile_name
        self._default_profile = get_profile(default_profile_name)
        # Pre-load profiles (raises ValueError early on bad name)
        self._profiles: dict[str, EnvironmentProfile] = {
            z.profile_name: get_profile(z.profile_name) for z in zones
        }
        self._profiles[default_profile_name] = self._default_profile

    def classify(
        self,
        robot_xy: tuple[float, float],
    ) -> tuple[str, EnvironmentProfile]:
        """
        Return (zone_name, EnvironmentProfile) for the given robot position.

        Falls back to ("default", default_profile) if no zone matches.
        """
        for zone in self._zones:
            if zone.contains(robot_xy):
                return zone.name, self._profiles[zone.profile_name]
        return "default", self._default_profile

    def zone_names(self) -> list[str]:
        return [z.name for z in self._zones]

    def __repr__(self) -> str:
        names = [z.name for z in self._zones]
        return f"ZoneMap(zones={names!r}, default={self._default_profile_name!r})"
