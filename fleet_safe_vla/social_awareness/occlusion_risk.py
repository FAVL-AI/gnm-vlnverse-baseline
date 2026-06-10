"""
occlusion_risk.py — geometric occlusion risk from static obstacles and scene geometry.

For each obstacle in the robot's field of view, estimates the "shadow zone" — the
uncertain region behind the obstacle that cannot be observed from the robot's current
position.  Risk increases when the robot approaches at speed toward such zones.

This is a conservative geometric model: it does not know what is actually in the
shadow zone, so it treats it as potentially occupied.  This is appropriate for
curse-of-rarity scenarios where unseen hazards must be assumed possible.

Reviewer note
─────────────
Occlusion risk is about epistemic uncertainty — the robot cannot see behind the
obstacle, not that something is definitely there.  The AMBER zone response (slow
down, widen margin) is proportional to this uncertainty, not to a belief about
occupancy.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class OcclusionZone:
    """A region of spatial uncertainty caused by an occluding obstacle."""
    center_xy:  tuple[float, float]   # approximate centre of the shadow
    radius_m:   float                  # approximate extent
    risk_score: float                  # in [0, 1]; higher = more uncertain/dangerous
    cause:      str                    # human-readable: e.g. "obstacle_at_(1.0,0.0)"
    angular_half_width_rad: float = 0.0  # half-angle subtended by occluder


class OcclusionRisk:
    """
    Estimate occlusion zones and their associated risk score.

    Usage::

        oc = OcclusionRisk(scan_range_m=5.0)
        zones = oc.estimate_occlusion_zones(
            robot_xy=(0.0, 0.0),
            obstacle_positions=[(1.0, 0.0)],
            obstacle_radii=[0.15],
        )
        risk = oc.compute_risk_score(zones, robot_speed_ms=0.3)
    """

    def __init__(
        self,
        scan_range_m: float = 5.0,
        shadow_depth_m: float = 1.5,
        min_subtend_rad: float = 0.05,  # ignore very distant, thin occluders
    ) -> None:
        self._scan_range = scan_range_m
        self._shadow_depth = shadow_depth_m
        self._min_subtend = min_subtend_rad

    # ── Main API ──────────────────────────────────────────────────────────────

    def estimate_occlusion_zones(
        self,
        robot_xy: tuple[float, float],
        obstacle_positions: list[tuple[float, float]],
        obstacle_radii: list[float] | None = None,
    ) -> list[OcclusionZone]:
        """
        Return list of OcclusionZone objects, one per significant occluder.

        Obstacles beyond scan_range_m are ignored.
        Obstacles that subtend less than min_subtend_rad are ignored.
        """
        if obstacle_radii is None:
            obstacle_radii = [0.15] * len(obstacle_positions)

        zones: list[OcclusionZone] = []
        rx, ry = robot_xy
        for (ox, oy), obs_r in zip(obstacle_positions, obstacle_radii):
            dx = ox - rx
            dy = oy - ry
            dist = math.hypot(dx, dy)
            if dist < 1e-6 or dist > self._scan_range:
                continue

            half_angle = math.asin(min(obs_r / dist, 1.0))
            if half_angle < self._min_subtend:
                continue

            zone = self._shadow_zone(rx, ry, ox, oy, dist, obs_r, half_angle)
            zones.append(zone)

        return zones

    def compute_risk_score(
        self,
        zones: list[OcclusionZone],
        robot_speed_ms: float = 0.0,
        speed_weight: float = 0.5,
    ) -> float:
        """
        Aggregate risk in [0, 1].

        Combines: max zone risk score + speed penalty (fast approach to unknown = more risk).
        """
        if not zones:
            return 0.0
        base_risk = max(z.risk_score for z in zones)
        speed_penalty = min(robot_speed_ms / 0.5, 1.0) * speed_weight
        return min(base_risk * (1.0 - speed_weight) + speed_penalty, 1.0)

    def is_approaching_blind_corner(
        self,
        robot_xy: tuple[float, float],
        robot_yaw: float,
        obstacle_positions: list[tuple[float, float]],
        obstacle_radii: list[float] | None = None,
        corner_threshold_m: float = 1.20,
        angle_threshold_rad: float = 0.40,
    ) -> bool:
        """
        Return True if the robot is heading toward an occlusion zone ahead.

        A "blind corner" is an occlusion zone whose centre falls within
        angle_threshold_rad of the robot's heading and within corner_threshold_m.
        """
        zones = self.estimate_occlusion_zones(robot_xy, obstacle_positions, obstacle_radii)
        rx, ry = robot_xy
        heading_dx = math.cos(robot_yaw)
        heading_dy = math.sin(robot_yaw)

        for z in zones:
            zx, zy = z.center_xy
            dz = math.hypot(zx - rx, zy - ry)
            if dz > corner_threshold_m:
                continue
            # Angle between heading and direction to zone centre
            dot = ((zx - rx) * heading_dx + (zy - ry) * heading_dy) / (dz + 1e-9)
            dot = max(-1.0, min(1.0, dot))
            angle = math.acos(dot)
            if angle < angle_threshold_rad:
                return True
        return False

    def nearest_occlusion_zone_dist_m(
        self,
        robot_xy: tuple[float, float],
        zones: list[OcclusionZone],
    ) -> float:
        """Distance from robot_xy to nearest occlusion zone centre."""
        if not zones:
            return float("inf")
        rx, ry = robot_xy
        return min(math.hypot(z.center_xy[0] - rx, z.center_xy[1] - ry)
                   for z in zones)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _shadow_zone(
        self,
        rx: float, ry: float,
        ox: float, oy: float,
        dist: float,
        obs_r: float,
        half_angle: float,
    ) -> OcclusionZone:
        """Compute the shadow OcclusionZone behind an obstacle."""
        # Unit vector from robot toward obstacle
        ux = (ox - rx) / dist
        uy = (oy - ry) / dist
        # Zone centre: just beyond the obstacle along the robot→obstacle ray
        depth = self._shadow_depth
        cx = ox + ux * depth / 2.0
        cy = oy + uy * depth / 2.0
        # Zone radius scales with shadow width
        zone_r = obs_r + depth * math.tan(half_angle)
        # Risk score: closer obstacle = larger angular uncertainty = higher risk
        risk = min(half_angle / (math.pi / 2.0), 1.0)
        return OcclusionZone(
            center_xy=(cx, cy),
            radius_m=zone_r,
            risk_score=risk,
            cause=f"obstacle_at_({ox:.2f},{oy:.2f})",
            angular_half_width_rad=half_angle,
        )
