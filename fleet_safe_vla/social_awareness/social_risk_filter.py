"""
social_risk_filter.py — integration hub for the social-risk and rare-event layer.

SocialRiskFilter wraps the individual estimators and classifiers into one call.
Given a robot state + agent list + scene geometry it returns a SocialRiskOutput
that tells the caller:

  - What safety zone (GREEN/AMBER/RED) the robot is in.
  - What the recommended speed cap and margin are.
  - Whether the nominal action should be vetoed (RED zone) or modified (AMBER).
  - What rare events fired this step.
  - A concise audit trail (reasons list) for downstream logging.

Design note
───────────
This is a *supervisory* filter, not a planner.  It does not compute a new
trajectory.  It caps speed, expands margin, and asserts veto when required.
The VLA or planner upstream is responsible for actual path computation.

All inputs are geometric.  No learned model is used here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from fleet_safe_vla.social_awareness.crowding_estimator import CrowdingEstimator
from fleet_safe_vla.social_awareness.dynamic_agent_tracker import (
    DynamicAgent,
    DynamicAgentTracker,
    Detection,
)
from fleet_safe_vla.social_awareness.environment_profiles import (
    EnvironmentProfile,
    DEFAULT_PROFILE,
)
from fleet_safe_vla.social_awareness.occlusion_risk import OcclusionRisk
from fleet_safe_vla.social_awareness.rare_event_monitor import (
    RareEvent,
    RareEventMonitor,
)
from fleet_safe_vla.social_awareness.safety_zones import (
    SafetyZone,
    SafetyZoneClassifier,
    ZoneClassification,
)
from fleet_safe_vla.social_awareness.zone_map import ZoneMap


@dataclass
class SocialRiskState:
    """Snapshot of all social-risk signals for one timestep."""
    timestamp:           float
    robot_xy:            tuple[float, float]
    robot_speed_ms:      float
    crowding_score:      float
    occlusion_risk:      float
    min_human_dist_m:    float
    agents:              list[DynamicAgent]
    zone_result:         ZoneClassification
    rare_events:         list[RareEvent]
    current_zone_name:   str = "default"
    current_profile_name: str = "default"


@dataclass
class SocialRiskOutput:
    """
    The filter's decision for this timestep.

    Fields
    ------
    veto : bool
        True when the zone is RED — nominal action must be suppressed.
    speed_cap_ms : float
        Maximum allowed speed (0.0 in RED; amber speed in AMBER; nominal in GREEN).
    margin_m : float
        Recommended safety margin for the CBF or planner.
    zone : SafetyZone
        GREEN / AMBER / RED.
    reasons : list[str]
        Audit trail — why this zone was assigned.
    rare_events : list[RareEvent]
        Any rare events detected this step.
    state : SocialRiskState
        Full snapshot (for logging / replay).
    current_zone_name : str
        Name of the spatial zone the robot is currently in (from ZoneMap).
    current_profile_name : str
        Name of the EnvironmentProfile used for this step.
    """
    veto:                bool
    speed_cap_ms:        float
    margin_m:            float
    zone:                SafetyZone
    reasons:             list[str]
    rare_events:         list[RareEvent]
    state:               SocialRiskState
    current_zone_name:   str = "default"
    current_profile_name: str = "default"


class SocialRiskFilter:
    """
    Integrate crowding, occlusion, zone classification, and rare-event detection.

    Usage::

        filt = SocialRiskFilter(profile=HOSPITAL_PROFILE)
        # each timestep:
        output = filt.compute(
            timestamp=t,
            robot_xy=(x, y),
            robot_speed_ms=0.3,
            robot_yaw=0.0,
            detections=[Detection(position_xy=(1.0, 0.5), agent_type=AgentType.HUMAN)],
            obstacle_positions=[(2.0, 0.0)],
            obstacle_radii=[0.15],
            path_blocked=False,
        )
        if output.veto:
            robot.stop()
        else:
            robot.set_speed(output.speed_cap_ms)
    """

    def __init__(
        self,
        profile: EnvironmentProfile = DEFAULT_PROFILE,
        crowding_radius_m: float | None = None,
        zone_map: ZoneMap | None = None,
    ) -> None:
        self._profile = profile
        self._tracker   = DynamicAgentTracker()
        self._crowding  = CrowdingEstimator()
        self._occlusion = OcclusionRisk()
        self._rare      = RareEventMonitor()
        self._zone_clf  = SafetyZoneClassifier(profile)
        self._crowding_radius = crowding_radius_m or profile.crowding_radius_m
        self._zone_map  = zone_map
        self._prev_agent_ids: set[str] = set()

    # ── Main API ──────────────────────────────────────────────────────────────

    def compute(
        self,
        timestamp: float,
        robot_xy: tuple[float, float],
        robot_speed_ms: float,
        robot_yaw: float,
        detections: Sequence[Detection],
        obstacle_positions: list[tuple[float, float]],
        obstacle_radii: list[float] | None = None,
        path_blocked: bool = False,
    ) -> SocialRiskOutput:
        """
        Run all social-risk estimators and return a unified output.

        Parameters
        ----------
        timestamp : float
            Current simulation/wall time in seconds.
        robot_xy : (x, y) metres
        robot_speed_ms : float
        robot_yaw : float — radians, used for blind-corner check
        detections : list of Detection objects from perception pipeline
        obstacle_positions : static obstacle (x, y) list
        obstacle_radii : optional per-obstacle radii (default 0.15m each)
        path_blocked : bool — set by planner when forward path is obstructed
        """
        # 1. Track dynamic agents
        agents = self._tracker.update(detections, timestamp)
        current_ids = {a.agent_id for a in agents}

        # 2. Crowding score
        crowding_score = self._crowding.compute_crowding_score(
            agents, robot_xy, radius_m=self._crowding_radius
        )

        # 3. Occlusion risk
        occ_zones = self._occlusion.estimate_occlusion_zones(
            robot_xy, obstacle_positions, obstacle_radii
        )
        occlusion_risk = self._occlusion.compute_risk_score(
            occ_zones, robot_speed_ms=robot_speed_ms
        )

        # 4. Minimum human distance (for rare-event + zone classifier)
        from fleet_safe_vla.social_awareness.dynamic_agent_tracker import AgentType
        import math
        rx, ry = robot_xy
        human_dists = [
            math.hypot(a.position_xy[0] - rx, a.position_xy[1] - ry)
            for a in agents
            if a.agent_type == AgentType.HUMAN
        ]
        min_human_dist = min(human_dists, default=float("inf"))

        # 4b. Per-step profile from ZoneMap (overrides constructor profile if present)
        current_zone_name   = "default"
        current_profile     = self._profile
        current_profile_name = self._profile.name
        if self._zone_map is not None:
            current_zone_name, current_profile = self._zone_map.classify(robot_xy)
            current_profile_name = current_profile.name

        # 5. Zone classification (with optional per-zone profile override)
        zone_result = self._zone_clf.classify(
            agents=agents,
            robot_xy=robot_xy,
            crowding_score=crowding_score,
            occlusion_risk=occlusion_risk,
            path_blocked=path_blocked,
            profile=current_profile,
        )

        # 6. Rare events
        rare_events = self._rare.check(
            timestamp=timestamp,
            robot_xy=robot_xy,
            agents=agents,
            crowding_score=crowding_score,
            occlusion_risk=occlusion_risk,
            min_human_dist_m=min_human_dist,
            human_red_dist_m=current_profile.stop_distance_red_m,
            known_agent_ids=self._prev_agent_ids,
            path_blocked=path_blocked,
        )

        self._prev_agent_ids = current_ids

        # 7. Build output
        state = SocialRiskState(
            timestamp=timestamp,
            robot_xy=robot_xy,
            robot_speed_ms=robot_speed_ms,
            crowding_score=crowding_score,
            occlusion_risk=occlusion_risk,
            min_human_dist_m=min_human_dist,
            agents=agents,
            zone_result=zone_result,
            rare_events=rare_events,
            current_zone_name=current_zone_name,
            current_profile_name=current_profile_name,
        )

        return SocialRiskOutput(
            veto=zone_result.zone == SafetyZone.RED,
            speed_cap_ms=zone_result.recommended_speed_ms,
            margin_m=zone_result.recommended_margin_m,
            zone=zone_result.zone,
            reasons=zone_result.reasons,
            rare_events=rare_events,
            state=state,
            current_zone_name=current_zone_name,
            current_profile_name=current_profile_name,
        )

    def filter_action(
        self,
        output: SocialRiskOutput,
        nominal_action: tuple[float, float],
    ) -> tuple[float, float]:
        """
        Apply zone-based action modification.

        Returns (linear_speed_ms, angular_speed_rads) clipped to zone limits.
        In RED zone: (0.0, 0.0).
        In AMBER zone: linear speed capped to profile.max_speed_amber_ms.
        In GREEN zone: linear speed capped to profile.max_speed_nominal_ms.
        """
        vx, wz = nominal_action
        if output.veto:
            return (0.0, 0.0)
        capped_vx = min(abs(vx), output.speed_cap_ms) * (1 if vx >= 0 else -1)
        return (capped_vx, wz)

    # ── Accessors ─────────────────────────────────────────────────────────────

    def get_all_rare_events(self) -> list[RareEvent]:
        return self._rare.get_events()

    def get_rare_event_count(self) -> int:
        return self._rare.get_trigger_count()

    def reset(self) -> None:
        self._tracker.reset()
        self._rare.reset()
        self._prev_agent_ids = set()
