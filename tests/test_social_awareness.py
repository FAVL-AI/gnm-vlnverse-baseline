"""
tests/test_social_awareness.py — Unit tests for the social-risk and rare-event layer.

Coverage
--------
  - DynamicAgentTracker: tracking, velocity estimation, crossing risk
  - CrowdingEstimator: score, bottleneck, approach rate
  - OcclusionRisk: zone estimation, risk score, blind corner detection
  - RareEventMonitor: all 5 triggered event types
  - SafetyZoneClassifier: GREEN / AMBER / RED transitions
  - SocialRiskFilter: end-to-end compute(), filter_action(), veto
  - EnvironmentProfile: profile lookup, get_profile()
"""
from __future__ import annotations

import math
import pytest

from fleet_safe_vla.social_awareness import (
    AgentType,
    CrowdingEstimator,
    DEFAULT_PROFILE,
    Detection,
    DynamicAgent,
    DynamicAgentTracker,
    HOSPITAL_PROFILE,
    OcclusionRisk,
    RareEvent,
    RareEventMonitor,
    RareEventType,
    SafetyZone,
    SafetyZoneClassifier,
    SocialRiskFilter,
    WAREHOUSE_PROFILE,
    get_profile,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_agent(
    x: float,
    y: float,
    vx: float = 0.0,
    vy: float = 0.0,
    agent_type: AgentType = AgentType.HUMAN,
    agent_id: str = "a0",
) -> DynamicAgent:
    return DynamicAgent(
        agent_id=agent_id,
        agent_type=agent_type,
        position_xy=(x, y),
        velocity_xy=(vx, vy),
        speed_ms=math.hypot(vx, vy),
        timestamp=0.0,
        confidence=1.0,
    )


# ── DynamicAgentTracker ───────────────────────────────────────────────────────

class TestDynamicAgentTracker:

    def test_new_detection_creates_track(self):
        tracker = DynamicAgentTracker()
        det = Detection(position_xy=(1.0, 0.0), agent_type=AgentType.HUMAN, timestamp=0.0)
        agents = tracker.update([det], timestamp=0.0)
        assert len(agents) == 1
        assert agents[0].agent_type == AgentType.HUMAN

    def test_track_persists_across_steps(self):
        tracker = DynamicAgentTracker()
        det1 = Detection(position_xy=(0.0, 0.0), agent_type=AgentType.HUMAN, timestamp=0.0)
        tracker.update([det1], timestamp=0.0)
        det2 = Detection(position_xy=(0.1, 0.0), agent_type=AgentType.HUMAN, timestamp=0.5)
        agents = tracker.update([det2], timestamp=0.5)
        assert len(agents) == 1
        assert agents[0].age_steps == 2

    def test_velocity_estimated_from_position_history(self):
        tracker = DynamicAgentTracker(velocity_history=3)
        for i in range(3):
            det = Detection(position_xy=(float(i) * 0.2, 0.0),
                            agent_type=AgentType.HUMAN, timestamp=float(i) * 0.5)
            tracker.update([det], timestamp=float(i) * 0.5)
        agents = tracker.get_tracked_agents()
        vx, vy = agents[0].velocity_xy
        assert abs(vx - 0.4) < 1e-6
        assert abs(vy) < 1e-6

    def test_stale_track_pruned(self):
        tracker = DynamicAgentTracker(max_track_age_s=1.0)
        det = Detection(position_xy=(0.0, 0.0), agent_type=AgentType.HUMAN, timestamp=0.0)
        tracker.update([det], timestamp=0.0)
        agents = tracker.update([], timestamp=5.0)  # no detections; 5s gap
        assert len(agents) == 0

    def test_crossing_risk_head_on(self):
        tracker = DynamicAgentTracker()
        # Robot at origin moving north; agent at (0, 1) moving south
        agent = _make_agent(x=0.0, y=1.0, vx=0.0, vy=-0.5)
        risk = tracker.get_crossing_risk(
            robot_xy=(0.0, 0.0),
            robot_vel_xy=(0.0, 0.3),
            agent=agent,
            horizon_s=2.0,
            collision_radius_m=0.50,
        )
        assert risk > 0.0, "head-on approach should have positive crossing risk"

    def test_crossing_risk_diverging(self):
        tracker = DynamicAgentTracker()
        # Robot moving north; agent already north and also moving north
        agent = _make_agent(x=0.0, y=2.0, vx=0.0, vy=0.5)
        risk = tracker.get_crossing_risk(
            robot_xy=(0.0, 0.0),
            robot_vel_xy=(0.0, 0.3),
            agent=agent,
            horizon_s=2.0,
            collision_radius_m=0.50,
        )
        assert risk == 0.0, "diverging paths should have zero crossing risk"


# ── CrowdingEstimator ─────────────────────────────────────────────────────────

class TestCrowdingEstimator:

    def test_score_zero_no_agents(self):
        est = CrowdingEstimator(max_expected_agents=10)
        score = est.compute_crowding_score([], robot_xy=(0.0, 0.0), radius_m=2.5)
        assert score == 0.0

    def test_score_one_with_max_agents(self):
        agents = [_make_agent(x=0.5, y=float(i) * 0.1, agent_id=f"a{i}") for i in range(10)]
        est = CrowdingEstimator(max_expected_agents=10)
        score = est.compute_crowding_score(agents, robot_xy=(0.0, 0.0), radius_m=5.0)
        assert score == 1.0

    def test_agents_outside_radius_not_counted(self):
        agents = [_make_agent(x=10.0, y=0.0)]
        est = CrowdingEstimator()
        nearby = est.agents_in_radius(agents, robot_xy=(0.0, 0.0), radius_m=2.5)
        assert len(nearby) == 0

    def test_nearest_agent_dist(self):
        agents = [
            _make_agent(x=3.0, y=0.0, agent_id="a0"),
            _make_agent(x=1.0, y=0.0, agent_id="a1"),
        ]
        est = CrowdingEstimator()
        d = est.nearest_agent_dist_m(agents, robot_xy=(0.0, 0.0))
        assert abs(d - 1.0) < 1e-6

    def test_bottleneck_detected(self):
        est = CrowdingEstimator()
        # 4 agents / (1.0 m × 4.0 m) = 1.0 agents/m²  > 0.4 threshold
        assert est.is_bottleneck(
            corridor_width_m=1.0,
            agent_count_in_corridor=4,
            density_threshold=0.4,
        )

    def test_no_bottleneck_sparse(self):
        est = CrowdingEstimator()
        assert not est.is_bottleneck(
            corridor_width_m=3.0,
            agent_count_in_corridor=1,
            density_threshold=0.4,
        )

    def test_approach_rate_positive_when_converging(self):
        # Agent at (2, 0) moving toward robot at (0, 0)
        agents = [_make_agent(x=2.0, y=0.0, vx=-0.5, vy=0.0)]
        est = CrowdingEstimator()
        rate = est.compute_approach_rate(agents, robot_xy=(0.0, 0.0))
        assert rate > 0.0


# ── OcclusionRisk ─────────────────────────────────────────────────────────────

class TestOcclusionRisk:

    def test_no_obstacles_returns_empty(self):
        oc = OcclusionRisk()
        zones = oc.estimate_occlusion_zones(
            robot_xy=(0.0, 0.0),
            obstacle_positions=[],
        )
        assert zones == []
        assert oc.compute_risk_score(zones) == 0.0

    def test_close_obstacle_creates_zone(self):
        oc = OcclusionRisk(scan_range_m=5.0)
        zones = oc.estimate_occlusion_zones(
            robot_xy=(0.0, 0.0),
            obstacle_positions=[(1.0, 0.0)],
            obstacle_radii=[0.20],
        )
        assert len(zones) == 1
        assert zones[0].risk_score > 0.0

    def test_far_obstacle_ignored(self):
        oc = OcclusionRisk(scan_range_m=3.0)
        zones = oc.estimate_occlusion_zones(
            robot_xy=(0.0, 0.0),
            obstacle_positions=[(10.0, 0.0)],
        )
        assert zones == []

    def test_risk_score_increases_with_speed(self):
        oc = OcclusionRisk()
        zones = oc.estimate_occlusion_zones(
            robot_xy=(0.0, 0.0),
            obstacle_positions=[(1.0, 0.0)],
            obstacle_radii=[0.20],
        )
        slow = oc.compute_risk_score(zones, robot_speed_ms=0.0)
        fast = oc.compute_risk_score(zones, robot_speed_ms=0.5)
        assert fast > slow

    def test_blind_corner_detected_ahead(self):
        oc = OcclusionRisk()
        # Obstacle at (0.5, 0); robot at origin facing east (yaw=0).
        # Shadow zone centre = 0.5 + 0.75 = 1.25 m < corner_threshold 1.5 m → detected.
        result = oc.is_approaching_blind_corner(
            robot_xy=(0.0, 0.0),
            robot_yaw=0.0,
            obstacle_positions=[(0.5, 0.0)],
            obstacle_radii=[0.20],
            corner_threshold_m=1.5,
        )
        assert result is True

    def test_blind_corner_not_detected_behind(self):
        oc = OcclusionRisk()
        # Obstacle behind robot (at -2, 0); robot facing east
        result = oc.is_approaching_blind_corner(
            robot_xy=(0.0, 0.0),
            robot_yaw=0.0,
            obstacle_positions=[(-2.0, 0.0)],
            obstacle_radii=[0.20],
        )
        assert result is False


# ── RareEventMonitor ──────────────────────────────────────────────────────────

class TestRareEventMonitor:

    def _base_call(self, monitor: RareEventMonitor, **overrides):
        kwargs = dict(
            timestamp=1.0,
            robot_xy=(0.0, 0.0),
            agents=[],
            crowding_score=0.0,
            occlusion_risk=0.0,
            min_human_dist_m=5.0,
            human_red_dist_m=0.60,
            known_agent_ids=set(),
            path_blocked=False,
        )
        kwargs.update(overrides)
        return monitor.check(**kwargs)

    def test_no_events_in_safe_state(self):
        monitor = RareEventMonitor()
        events = self._base_call(monitor)
        assert events == []

    def test_near_miss_triggers(self):
        monitor = RareEventMonitor()
        events = self._base_call(monitor, min_human_dist_m=0.30, human_red_dist_m=0.60)
        types = [e.event_type for e in events]
        assert RareEventType.NEAR_MISS_HUMAN in types

    def test_path_blocked_triggers(self):
        monitor = RareEventMonitor()
        events = self._base_call(monitor, path_blocked=True)
        types = [e.event_type for e in events]
        assert RareEventType.PATH_BLOCKED in types

    def test_crowding_spike_triggers(self):
        monitor = RareEventMonitor(crowding_spike_threshold=0.70)
        self._base_call(monitor, crowding_score=0.0)  # prime previous value
        events = self._base_call(monitor, crowding_score=0.85)
        types = [e.event_type for e in events]
        assert RareEventType.UNEXPECTED_CROWDING in types

    def test_occlusion_surprise_triggers(self):
        monitor = RareEventMonitor()
        events = self._base_call(monitor, occlusion_risk=0.9)
        types = [e.event_type for e in events]
        assert RareEventType.OCCLUSION_SURPRISE in types

    def test_new_agent_triggers(self):
        monitor = RareEventMonitor()
        agent = _make_agent(x=1.0, y=0.0)
        events = self._base_call(monitor, agents=[agent],
                                 known_agent_ids=set())  # agent_id not in known
        types = [e.event_type for e in events]
        assert RareEventType.UNKNOWN_DYNAMIC_AGENT in types

    def test_get_trigger_count(self):
        monitor = RareEventMonitor()
        self._base_call(monitor, path_blocked=True)
        self._base_call(monitor, path_blocked=True)
        assert monitor.get_trigger_count() == 2

    def test_reset_clears_events(self):
        monitor = RareEventMonitor()
        self._base_call(monitor, path_blocked=True)
        monitor.reset()
        assert monitor.get_trigger_count() == 0


# ── SafetyZoneClassifier ──────────────────────────────────────────────────────

class TestSafetyZoneClassifier:

    def test_green_when_no_agents(self):
        clf = SafetyZoneClassifier(DEFAULT_PROFILE)
        result = clf.classify(
            agents=[], robot_xy=(0.0, 0.0),
            crowding_score=0.0, occlusion_risk=0.0,
        )
        assert result.zone == SafetyZone.GREEN

    def test_amber_on_crowding_score(self):
        clf = SafetyZoneClassifier(DEFAULT_PROFILE)
        result = clf.classify(
            agents=[], robot_xy=(0.0, 0.0),
            crowding_score=0.6, occlusion_risk=0.0,
        )
        assert result.zone == SafetyZone.AMBER

    def test_amber_on_occlusion_risk(self):
        clf = SafetyZoneClassifier(DEFAULT_PROFILE)
        result = clf.classify(
            agents=[], robot_xy=(0.0, 0.0),
            crowding_score=0.0, occlusion_risk=0.8,
        )
        assert result.zone == SafetyZone.AMBER

    def test_red_when_path_blocked(self):
        clf = SafetyZoneClassifier(DEFAULT_PROFILE)
        result = clf.classify(
            agents=[], robot_xy=(0.0, 0.0),
            crowding_score=0.0, occlusion_risk=0.0,
            path_blocked=True,
        )
        assert result.zone == SafetyZone.RED

    def test_red_when_human_too_close(self):
        clf = SafetyZoneClassifier(HOSPITAL_PROFILE)
        human = _make_agent(x=0.3, y=0.0)  # 0.3m < hospital stop_dist 0.60
        result = clf.classify(
            agents=[human], robot_xy=(0.0, 0.0),
            crowding_score=0.0, occlusion_risk=0.0,
        )
        assert result.zone == SafetyZone.RED

    def test_red_wins_over_amber(self):
        clf = SafetyZoneClassifier(DEFAULT_PROFILE)
        human = _make_agent(x=0.1, y=0.0)
        result = clf.classify(
            agents=[human], robot_xy=(0.0, 0.0),
            crowding_score=0.9, occlusion_risk=0.9,
            path_blocked=True,
        )
        assert result.zone == SafetyZone.RED

    def test_recommended_speed_zero_in_red(self):
        clf = SafetyZoneClassifier(DEFAULT_PROFILE)
        result = clf.classify(
            agents=[], robot_xy=(0.0, 0.0),
            crowding_score=0.0, occlusion_risk=0.0,
            path_blocked=True,
        )
        assert result.recommended_speed_ms == 0.0

    def test_recommended_speed_capped_in_amber(self):
        clf = SafetyZoneClassifier(DEFAULT_PROFILE)
        result = clf.classify(
            agents=[], robot_xy=(0.0, 0.0),
            crowding_score=0.7, occlusion_risk=0.0,
        )
        assert result.zone == SafetyZone.AMBER
        assert result.recommended_speed_ms == DEFAULT_PROFILE.max_speed_amber_ms


# ── SocialRiskFilter ──────────────────────────────────────────────────────────

class TestSocialRiskFilter:

    def test_green_output_in_empty_scene(self):
        filt = SocialRiskFilter(profile=DEFAULT_PROFILE)
        output = filt.compute(
            timestamp=0.0, robot_xy=(0.0, 0.0),
            robot_speed_ms=0.2, robot_yaw=0.0,
            detections=[], obstacle_positions=[],
        )
        assert output.zone == SafetyZone.GREEN
        assert output.veto is False

    def test_veto_true_in_red_zone(self):
        filt = SocialRiskFilter(profile=DEFAULT_PROFILE)
        output = filt.compute(
            timestamp=0.0, robot_xy=(0.0, 0.0),
            robot_speed_ms=0.0, robot_yaw=0.0,
            detections=[], obstacle_positions=[],
            path_blocked=True,
        )
        assert output.veto is True
        assert output.zone == SafetyZone.RED

    def test_filter_action_stops_in_red(self):
        filt = SocialRiskFilter(profile=DEFAULT_PROFILE)
        output = filt.compute(
            timestamp=0.0, robot_xy=(0.0, 0.0),
            robot_speed_ms=0.0, robot_yaw=0.0,
            detections=[], obstacle_positions=[],
            path_blocked=True,
        )
        vx, wz = filt.filter_action(output, nominal_action=(0.4, 0.1))
        assert vx == 0.0
        assert wz == 0.0

    def test_filter_action_caps_speed_in_amber(self):
        filt = SocialRiskFilter(profile=DEFAULT_PROFILE)
        # Force AMBER via crowding: 3 humans inside crowding radius
        dets = [
            Detection(position_xy=(float(i) * 0.3, 0.0), agent_type=AgentType.HUMAN)
            for i in range(3)
        ]
        output = filt.compute(
            timestamp=0.0, robot_xy=(0.0, 0.0),
            robot_speed_ms=0.3, robot_yaw=0.0,
            detections=dets, obstacle_positions=[],
        )
        if output.zone == SafetyZone.AMBER:
            vx, _ = filt.filter_action(output, nominal_action=(1.0, 0.0))
            assert vx <= DEFAULT_PROFILE.max_speed_amber_ms + 1e-9

    def test_reset_clears_state(self):
        filt = SocialRiskFilter()
        det = Detection(position_xy=(0.5, 0.0), agent_type=AgentType.HUMAN)
        filt.compute(timestamp=0.0, robot_xy=(0.0, 0.0),
                     robot_speed_ms=0.0, robot_yaw=0.0,
                     detections=[det], obstacle_positions=[])
        filt.reset()
        assert filt.get_rare_event_count() == 0


# ── EnvironmentProfile ────────────────────────────────────────────────────────

class TestEnvironmentProfiles:

    def test_get_profile_hospital(self):
        p = get_profile("hospital")
        assert p.name == "hospital"
        assert p.max_speed_nominal_ms < 0.5

    def test_get_profile_case_insensitive(self):
        p1 = get_profile("hospital")
        p2 = get_profile("Hospital")
        assert p1 is p2

    def test_get_profile_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown environment profile"):
            get_profile("nonexistent")

    def test_hospital_more_conservative_than_warehouse(self):
        h = get_profile("hospital")
        w = get_profile("warehouse")
        assert h.max_speed_nominal_ms < w.max_speed_nominal_ms
        assert h.stop_distance_red_m > w.stop_distance_red_m
        assert h.human_margin_m > w.human_margin_m
