"""
safety_zones.py — Traffic-Light Safety Zone classifier for the social-risk layer.

Risk zones:
  GREEN  — nominal; no intervention required.
  AMBER  — caution; reduce speed, increase safety margin, log warning.
  RED    — danger; stop or reroute, force FleetSafe intervention.

Classification is deterministic and geometry-based.  The same inputs always
produce the same zone.  This makes the safety layer inspectable and reproducible
across benchmark runs.

Zone precedence (highest wins):
    RED > AMBER > GREEN

Inputs come from CrowdingEstimator, OcclusionRisk, DynamicAgentTracker, and the
EnvironmentProfile for the current deployment context.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence

from fleet_safe_vla.social_awareness.environment_profiles import EnvironmentProfile
from fleet_safe_vla.social_awareness.dynamic_agent_tracker import DynamicAgent, AgentType


class SafetyZone(str, Enum):
    GREEN = "GREEN"
    AMBER = "AMBER"
    RED   = "RED"


@dataclass
class ZoneClassification:
    """Full classification result for one timestep."""
    zone:              SafetyZone
    reasons:           list[str]             # human-readable trigger list
    crowding_score:    float                 # [0, 1]
    occlusion_risk:    float                 # [0, 1]
    min_human_dist_m:  float                 # inf if no humans
    min_agent_dist_m:  float                 # inf if no agents
    agents_in_radius:  int
    recommended_speed_ms: float
    recommended_margin_m: float


class SafetyZoneClassifier:
    """
    Classify the robot's current situation as GREEN, AMBER, or RED.

    Usage::

        clf = SafetyZoneClassifier(profile)
        result = clf.classify(
            agents=tracker.get_tracked_agents(),
            robot_xy=(x, y),
            crowding_score=0.6,
            occlusion_risk=0.4,
            path_blocked=False,
        )
        if result.zone == SafetyZone.RED:
            robot.stop()
    """

    def __init__(self, profile: EnvironmentProfile) -> None:
        self._p = profile

    def classify(
        self,
        agents: Sequence[DynamicAgent],
        robot_xy: tuple[float, float],
        crowding_score: float,
        occlusion_risk: float,
        path_blocked: bool = False,
        profile: EnvironmentProfile | None = None,
    ) -> ZoneClassification:
        """
        Return a ZoneClassification for the current robot state.

        Parameters
        ----------
        profile : optional per-step profile override (from ZoneMap).
                  When provided it takes precedence over the classifier's
                  constructor profile for this call only.

        RED wins over AMBER; AMBER wins over GREEN.
        """
        p = profile if profile is not None else self._p
        reasons: list[str] = []
        zone = SafetyZone.GREEN

        # ── Distances ─────────────────────────────────────────────────────────
        rx, ry = robot_xy
        human_agents = [a for a in agents if a.agent_type == AgentType.HUMAN]
        all_dists = [
            ((a.position_xy[0] - rx) ** 2 + (a.position_xy[1] - ry) ** 2) ** 0.5
            for a in agents
        ]
        human_dists = [
            ((a.position_xy[0] - rx) ** 2 + (a.position_xy[1] - ry) ** 2) ** 0.5
            for a in human_agents
        ]
        min_agent_dist = min(all_dists, default=float("inf"))
        min_human_dist = min(human_dists, default=float("inf"))

        # Count agents in crowding radius (passed in as crowding_score, but recount
        # for reporting)
        agents_in_r = sum(
            1 for d in all_dists if d <= p.crowding_radius_m
        )

        # ── RED checks ────────────────────────────────────────────────────────
        if min_human_dist < p.stop_distance_red_m:
            zone = SafetyZone.RED
            reasons.append(
                f"human_too_close: {min_human_dist:.2f}m < red_dist {p.stop_distance_red_m:.2f}m"
            )

        if agents_in_r >= p.red_crowding_agents:
            zone = SafetyZone.RED
            reasons.append(
                f"crowd_red: {agents_in_r} agents in {p.crowding_radius_m:.1f}m radius"
            )

        if path_blocked:
            zone = SafetyZone.RED
            reasons.append("path_blocked")

        # ── AMBER checks (only if not already RED) ────────────────────────────
        if zone != SafetyZone.RED:
            if min_human_dist < p.human_amber_dist_m:
                zone = SafetyZone.AMBER
                reasons.append(
                    f"human_amber: {min_human_dist:.2f}m < amber_dist {p.human_amber_dist_m:.2f}m"
                )

            if agents_in_r >= p.amber_crowding_agents:
                zone = SafetyZone.AMBER
                reasons.append(
                    f"crowd_amber: {agents_in_r} agents in {p.crowding_radius_m:.1f}m radius"
                )

            if occlusion_risk > 0.3:
                zone = SafetyZone.AMBER
                reasons.append(f"occlusion_risk: {occlusion_risk:.2f}")

            if crowding_score >= 0.5:
                zone = SafetyZone.AMBER
                reasons.append(f"crowding_score: {crowding_score:.2f}")

        # ── Recommended speed / margin ─────────────────────────────────────────
        if zone == SafetyZone.RED:
            recommended_speed = 0.0
            recommended_margin = p.human_margin_m
        elif zone == SafetyZone.AMBER:
            recommended_speed = p.max_speed_amber_ms
            recommended_margin = p.default_safety_margin_m + 0.15
        else:
            recommended_speed = p.max_speed_nominal_ms
            recommended_margin = p.default_safety_margin_m

        return ZoneClassification(
            zone=zone,
            reasons=reasons if reasons else ["all_clear"],
            crowding_score=crowding_score,
            occlusion_risk=occlusion_risk,
            min_human_dist_m=min_human_dist,
            min_agent_dist_m=min_agent_dist,
            agents_in_radius=agents_in_r,
            recommended_speed_ms=recommended_speed,
            recommended_margin_m=recommended_margin,
        )
