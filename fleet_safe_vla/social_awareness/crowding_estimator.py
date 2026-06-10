"""
crowding_estimator.py — estimate crowding risk from nearby dynamic agents.

Computes a normalized crowding score in [0, 1] based on agent density within a
configurable radius of the robot.  Also detects bottleneck conditions (high density
relative to corridor width) and estimates pedestrian flow density.

The score is a transparent spatial density statistic — not a social prediction.
"""
from __future__ import annotations

import math
from typing import Sequence

from fleet_safe_vla.social_awareness.dynamic_agent_tracker import DynamicAgent


class CrowdingEstimator:
    """
    Estimate crowding severity from agent positions.

    Usage::

        est = CrowdingEstimator()
        score = est.compute_crowding_score(agents, robot_xy=(0.0, 0.0), radius_m=2.5)
    """

    def __init__(self, max_expected_agents: int = 10) -> None:
        self._max_agents = max(max_expected_agents, 1)

    # ── Main API ──────────────────────────────────────────────────────────────

    def compute_crowding_score(
        self,
        agents: Sequence[DynamicAgent],
        robot_xy: tuple[float, float],
        radius_m: float = 2.5,
    ) -> float:
        """
        Return crowding score in [0, 1].

        Score = (agents within radius) / max_expected_agents.
        Capped at 1.0.
        """
        nearby = self.agents_in_radius(agents, robot_xy, radius_m)
        return min(len(nearby) / self._max_agents, 1.0)

    def agents_in_radius(
        self,
        agents: Sequence[DynamicAgent],
        robot_xy: tuple[float, float],
        radius_m: float,
    ) -> list[DynamicAgent]:
        """Return agents whose position is within radius_m of robot_xy."""
        rx, ry = robot_xy
        return [
            a for a in agents
            if math.hypot(a.position_xy[0] - rx, a.position_xy[1] - ry) <= radius_m
        ]

    def nearest_agent_dist_m(
        self,
        agents: Sequence[DynamicAgent],
        robot_xy: tuple[float, float],
    ) -> float:
        """Euclidean distance to nearest agent.  Returns inf if no agents."""
        if not agents:
            return float("inf")
        rx, ry = robot_xy
        return min(
            math.hypot(a.position_xy[0] - rx, a.position_xy[1] - ry)
            for a in agents
        )

    def is_bottleneck(
        self,
        corridor_width_m: float,
        agent_count_in_corridor: int,
        corridor_length_m: float = 4.0,
        density_threshold: float = 0.4,
    ) -> bool:
        """
        Return True if the agent density in a corridor exceeds threshold.

        density_threshold is in agents/m².
        """
        area = max(corridor_width_m * corridor_length_m, 0.01)
        density = agent_count_in_corridor / area
        return density >= density_threshold

    def estimate_flow_density(
        self,
        agents: Sequence[DynamicAgent],
        area_m2: float,
    ) -> float:
        """Agents per square metre in the given area."""
        if area_m2 <= 0:
            return 0.0
        return len(agents) / area_m2

    def compute_approach_rate(
        self,
        agents: Sequence[DynamicAgent],
        robot_xy: tuple[float, float],
    ) -> float:
        """
        Mean approach speed of nearby agents (positive = approaching robot).

        Uses dot product of agent velocity with the agent→robot direction vector.
        """
        if not agents:
            return 0.0
        rx, ry = robot_xy
        total = 0.0
        for a in agents:
            dx = rx - a.position_xy[0]
            dy = ry - a.position_xy[1]
            dist = math.hypot(dx, dy)
            if dist < 1e-6:
                continue
            # Unit vector toward robot
            ux, uy = dx / dist, dy / dist
            approach = a.velocity_xy[0] * ux + a.velocity_xy[1] * uy
            total += approach
        return total / len(agents)
