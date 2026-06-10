"""
rare_event_monitor.py — detect and log rare or unexpected navigation hazards.

A "rare event" is a situation that falls outside the robot's normal operating
distribution: a suddenly appearing agent, an unexpected path blockage, crowding
that exceeds the expected density, or a near-miss with a human.

These events are logged with timestamps, positions, and severity scores.
The trigger count is a benchmark metric that captures how often FleetSafe had
to respond to something unusual — supporting the "curse of rarity" argument.

All detection logic is purely geometric; no learned anomaly model is used.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence


class RareEventType(str, Enum):
    UNKNOWN_DYNAMIC_AGENT   = "unknown_dynamic_agent"    # new agent detected
    SUDDEN_VELOCITY_CHANGE  = "sudden_velocity_change"   # agent decelerated sharply
    PATH_BLOCKED            = "path_blocked"             # forward path obstructed
    UNEXPECTED_CROWDING     = "unexpected_crowding"      # density spike
    NEAR_MISS_HUMAN         = "near_miss_human"          # human closer than red threshold
    OCCLUSION_SURPRISE      = "occlusion_surprise"       # entered zone; new agent appeared
    CORRIDOR_BLOCKED        = "corridor_blocked"         # bottleneck with no clear path


@dataclass
class RareEvent:
    """One logged rare-event occurrence."""
    event_type:  RareEventType
    timestamp:   float
    position_xy: tuple[float, float]     # robot position at time of event
    description: str                     # human-readable
    severity:    float                   # in [0, 1]; 1 = most severe


class RareEventMonitor:
    """
    Scan current state for rare events and maintain an event log.

    Usage::

        monitor = RareEventMonitor()
        events = monitor.check(
            timestamp=t,
            robot_xy=(x, y),
            agents=tracker.get_tracked_agents(),
            crowding_score=0.8,
            occlusion_risk=0.6,
            min_human_dist_m=0.45,
            human_red_dist_m=0.60,
            known_agent_ids=prev_agent_ids,
        )
    """

    def __init__(
        self,
        crowding_spike_threshold: float = 0.70,
        velocity_change_threshold_ms: float = 0.30,
    ) -> None:
        self._crowding_thresh   = crowding_spike_threshold
        self._vel_thresh        = velocity_change_threshold_ms
        self._events: list[RareEvent] = []
        self._prev_crowding: float = 0.0
        self._prev_agent_speeds: dict[str, float] = {}

    def check(
        self,
        timestamp: float,
        robot_xy: tuple[float, float],
        agents: Sequence,          # list[DynamicAgent]
        crowding_score: float,
        occlusion_risk: float,
        min_human_dist_m: float,
        human_red_dist_m: float,
        known_agent_ids: set[str] | None = None,
        path_blocked: bool = False,
    ) -> list[RareEvent]:
        """
        Return any newly-detected rare events.  Side-effects: logs them internally.
        """
        new_events: list[RareEvent] = []

        # Unknown new dynamic agents
        if known_agent_ids is not None:
            for agent in agents:
                if agent.agent_id not in known_agent_ids:
                    new_events.append(RareEvent(
                        event_type=RareEventType.UNKNOWN_DYNAMIC_AGENT,
                        timestamp=timestamp,
                        position_xy=robot_xy,
                        description=f"New {agent.agent_type.value} agent appeared"
                                    f" at {agent.position_xy}",
                        severity=0.6,
                    ))

        # Sudden velocity change (agent decelerated sharply)
        for agent in agents:
            prev_speed = self._prev_agent_speeds.get(agent.agent_id, agent.speed_ms)
            delta = abs(agent.speed_ms - prev_speed)
            if delta >= self._vel_thresh:
                new_events.append(RareEvent(
                    event_type=RareEventType.SUDDEN_VELOCITY_CHANGE,
                    timestamp=timestamp,
                    position_xy=robot_xy,
                    description=f"Agent {agent.agent_id} speed changed"
                                f" {prev_speed:.2f}→{agent.speed_ms:.2f} m/s",
                    severity=min(delta / 1.0, 1.0),
                ))
            self._prev_agent_speeds[agent.agent_id] = agent.speed_ms

        # Unexpected crowding spike
        if (crowding_score >= self._crowding_thresh
                and self._prev_crowding < self._crowding_thresh):
            new_events.append(RareEvent(
                event_type=RareEventType.UNEXPECTED_CROWDING,
                timestamp=timestamp,
                position_xy=robot_xy,
                description=f"Crowding spike: score={crowding_score:.2f}",
                severity=crowding_score,
            ))

        # Near miss with human
        if min_human_dist_m < human_red_dist_m:
            new_events.append(RareEvent(
                event_type=RareEventType.NEAR_MISS_HUMAN,
                timestamp=timestamp,
                position_xy=robot_xy,
                description=f"Human within red zone: {min_human_dist_m:.2f} m"
                            f" < threshold {human_red_dist_m:.2f} m",
                severity=max(0.0, 1.0 - min_human_dist_m / human_red_dist_m),
            ))

        # Path blocked
        if path_blocked:
            new_events.append(RareEvent(
                event_type=RareEventType.PATH_BLOCKED,
                timestamp=timestamp,
                position_xy=robot_xy,
                description="Forward path blocked by agents",
                severity=0.8,
            ))

        # High occlusion risk (potential surprise)
        if occlusion_risk > 0.75:
            new_events.append(RareEvent(
                event_type=RareEventType.OCCLUSION_SURPRISE,
                timestamp=timestamp,
                position_xy=robot_xy,
                description=f"High occlusion risk: {occlusion_risk:.2f}"
                            f" — unknown hazard possible",
                severity=occlusion_risk,
            ))

        self._prev_crowding = crowding_score
        self._events.extend(new_events)
        return new_events

    def get_events(self) -> list[RareEvent]:
        return list(self._events)

    def get_trigger_count(self) -> int:
        return len(self._events)

    def get_events_by_type(self, event_type: RareEventType) -> list[RareEvent]:
        return [e for e in self._events if e.event_type == event_type]

    def reset(self) -> None:
        self._events.clear()
        self._prev_crowding = 0.0
        self._prev_agent_speeds.clear()
