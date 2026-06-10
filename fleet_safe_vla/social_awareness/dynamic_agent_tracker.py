"""
dynamic_agent_tracker.py — lightweight track-by-detection for dynamic agents.

Maintains persistent tracks across timesteps using nearest-neighbor association.
Estimates velocity by finite difference of recent positions.  Predicts short-horizon
crossing risk for each tracked agent relative to the robot.

Design constraints
──────────────────
- No Kalman filter, no deep learning.  Pure geometry + finite differences.
- Deterministic and unit-testable without sensor hardware.
- Accepts (position_xy, agent_type, timestamp) tuples as "detections".
  In benchmark context these come from DynamicAgentSpec.position_at(t).
  In real deployment they come from YOLO + LiDAR fusion.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence


class AgentType(str, Enum):
    HUMAN   = "human"
    ROBOT   = "robot"
    UNKNOWN = "unknown"


@dataclass
class Detection:
    """One sensor observation of a dynamic agent."""
    position_xy:   tuple[float, float]
    agent_type:    AgentType = AgentType.UNKNOWN
    timestamp:     float     = 0.0
    confidence:    float     = 1.0
    semantic_role: str       = "unknown"


@dataclass
class DynamicAgent:
    """A persistent track: maintained state of one detected dynamic agent."""
    agent_id:      str
    agent_type:    AgentType
    position_xy:   tuple[float, float]
    velocity_xy:   tuple[float, float]  # estimated m/s, (0,0) if too few samples
    speed_ms:      float
    timestamp:     float
    confidence:    float
    age_steps:     int = 0             # number of updates since first seen
    semantic_role: str = "unknown"


class DynamicAgentTracker:
    """
    Track dynamic agents across timesteps.

    Usage::

        tracker = DynamicAgentTracker()
        agents = tracker.update(detections, timestamp=t)
        risk = tracker.get_crossing_risk(robot_xy, (0.3, 0.0), agents[0], horizon_s=2.0)
    """

    def __init__(
        self,
        max_association_dist_m: float = 0.80,
        max_track_age_s: float = 2.0,
        velocity_history: int = 3,
    ) -> None:
        self._max_assoc = max_association_dist_m
        self._max_age   = max_track_age_s
        self._vel_hist  = velocity_history
        self._tracks: dict[str, _Track] = {}
        self._next_id = 0

    # ── Public API ────────────────────────────────────────────────────────────

    def update(
        self,
        detections: Sequence[Detection],
        timestamp: float,
    ) -> list[DynamicAgent]:
        """
        Associate detections to existing tracks and return updated agent list.

        New detections that don't match any track start a new track.
        Tracks with no recent detection are pruned after max_track_age_s.
        """
        self._prune_stale(timestamp)
        matched_track_ids: set[str] = set()

        for det in detections:
            best_id, best_dist = self._find_closest_track(det.position_xy)
            if best_id is not None and best_dist <= self._max_assoc:
                self._tracks[best_id].update(det, timestamp)
                matched_track_ids.add(best_id)
            else:
                new_id = f"agent_{self._next_id}"
                self._next_id += 1
                trk = _Track(
                    track_id=new_id,
                    agent_type=det.agent_type,
                    max_vel_hist=self._vel_hist,
                )
                trk.update(det, timestamp)
                self._tracks[new_id] = trk
                matched_track_ids.add(new_id)

        return [t.to_agent() for t in self._tracks.values()]

    def get_tracked_agents(self) -> list[DynamicAgent]:
        """Return current track list without updating."""
        return [t.to_agent() for t in self._tracks.values()]

    def predict_position(
        self,
        agent_id: str,
        dt: float,
    ) -> tuple[float, float] | None:
        """Linear position prediction dt seconds ahead. None if track unknown."""
        trk = self._tracks.get(agent_id)
        if trk is None:
            return None
        x, y = trk.position_xy
        vx, vy = trk.velocity_xy
        return (x + vx * dt, y + vy * dt)

    def get_crossing_risk(
        self,
        robot_xy: tuple[float, float],
        robot_vel_xy: tuple[float, float],
        agent: DynamicAgent,
        horizon_s: float = 2.0,
        collision_radius_m: float = 0.50,
    ) -> float:
        """
        Estimate path-crossing risk in [0, 1].

        Linearly predicts both robot and agent positions over horizon_s and
        checks minimum separation.  Risk = 1 if minimum separation < collision_radius_m.
        """
        n_steps = max(int(horizon_s / 0.25), 1)
        dt = horizon_s / n_steps
        rx, ry = robot_xy
        rvx, rvy = robot_vel_xy
        ax, ay = agent.position_xy
        avx, avy = agent.velocity_xy

        min_sep_sq = float("inf")
        for i in range(1, n_steps + 1):
            t = i * dt
            rx_t = rx + rvx * t
            ry_t = ry + rvy * t
            ax_t = ax + avx * t
            ay_t = ay + avy * t
            sep_sq = (rx_t - ax_t) ** 2 + (ry_t - ay_t) ** 2
            if sep_sq < min_sep_sq:
                min_sep_sq = sep_sq

        min_sep = math.sqrt(min_sep_sq)
        if min_sep >= collision_radius_m:
            return 0.0
        return 1.0 - min_sep / collision_radius_m

    def reset(self) -> None:
        self._tracks.clear()
        self._next_id = 0

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _prune_stale(self, now: float) -> None:
        stale = [k for k, t in self._tracks.items()
                 if (now - t.last_seen) > self._max_age]
        for k in stale:
            del self._tracks[k]

    def _find_closest_track(
        self,
        pos: tuple[float, float],
    ) -> tuple[str | None, float]:
        best_id: str | None = None
        best_dist = float("inf")
        for tid, trk in self._tracks.items():
            d = math.hypot(trk.position_xy[0] - pos[0],
                           trk.position_xy[1] - pos[1])
            if d < best_dist:
                best_dist = d
                best_id = tid
        return best_id, best_dist


# ── Internal track state ──────────────────────────────────────────────────────

class _Track:
    """Mutable internal track state (not exposed publicly)."""

    def __init__(self, track_id: str, agent_type: AgentType, max_vel_hist: int) -> None:
        self.track_id      = track_id
        self.agent_type    = agent_type
        self.position_xy: tuple[float, float] = (0.0, 0.0)
        self.velocity_xy: tuple[float, float] = (0.0, 0.0)
        self.confidence    = 1.0
        self.last_seen     = 0.0
        self.age_steps     = 0
        self.semantic_role = "unknown"
        self._pos_hist: deque[tuple[float, float, float]] = deque(maxlen=max_vel_hist)

    def update(self, det: Detection, timestamp: float) -> None:
        self.position_xy   = det.position_xy
        self.confidence    = det.confidence
        self.last_seen     = timestamp
        self.age_steps    += 1
        if det.semantic_role != "unknown":
            self.semantic_role = det.semantic_role
        self._pos_hist.append((det.position_xy[0], det.position_xy[1], timestamp))
        self.velocity_xy = self._estimate_velocity()

    def _estimate_velocity(self) -> tuple[float, float]:
        if len(self._pos_hist) < 2:
            return (0.0, 0.0)
        x0, y0, t0 = self._pos_hist[0]
        x1, y1, t1 = self._pos_hist[-1]
        dt = t1 - t0
        if dt < 1e-6:
            return (0.0, 0.0)
        return ((x1 - x0) / dt, (y1 - y0) / dt)

    def to_agent(self) -> DynamicAgent:
        vx, vy = self.velocity_xy
        return DynamicAgent(
            agent_id      = self.track_id,
            agent_type    = self.agent_type,
            position_xy   = self.position_xy,
            velocity_xy   = self.velocity_xy,
            speed_ms      = math.hypot(vx, vy),
            timestamp     = self.last_seen,
            confidence    = self.confidence,
            age_steps     = self.age_steps,
            semantic_role = self.semantic_role,
        )
