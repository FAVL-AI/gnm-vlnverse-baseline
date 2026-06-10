"""
mock_source.py — deterministic perception stub for testing without hardware.

MockPerceptionSource generates a reproducible stream of Detection objects
from a fixed scenario script, advancing by timestep on each call.

Usage in tests::

    source = MockPerceptionSource(scenario="hospital_corridor")
    detections = source.step(robot_xy=(1.0, 0.0))
    # → list[Detection] matching the scripted scenario at step 0

Usage in benchmark dry-runs::

    source = MockPerceptionSource(seed=42)
    pipeline = PerceptionPipeline.from_config(PerceptionConfig(model_path=None))
    # inject source detections into the tracker directly
    for t in range(100):
        dets = source.step(robot_xy=robot.position_xy, timestamp=t * 0.1)
        tracker.update(dets, timestamp=t * 0.1)

Built-in scenarios
------------------
"hospital_corridor"   — nurse approaches head-on, patient crosses laterally
"waiting_room"        — static cluster of visitors, one approaching wheelchair user
"empty"               — no agents (baseline)
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable, Sequence

from fleet_safe_vla.social_awareness.dynamic_agent_tracker import AgentType, Detection


# ── Agent track definition ─────────────────────────────────────────────────────

@dataclass
class MockAgentTrack:
    """
    A scripted agent path for MockPerceptionSource.

    Parameters
    ----------
    agent_id      : unique string identifier (not in Detection, but used for reproducibility)
    semantic_role : role string passed to Detection.semantic_role
    agent_type    : AgentType
    positions     : list of (x, y) waypoints visited at each timestep
    confidence    : fixed confidence value
    loop          : if True, waypoints repeat cyclically; else last position held
    """
    agent_id:     str
    semantic_role: str
    agent_type:   AgentType
    positions:    list[tuple[float, float]]
    confidence:   float = 0.85
    loop:         bool  = False

    def position_at(self, step: int) -> tuple[float, float]:
        if not self.positions:
            return (0.0, 0.0)
        if self.loop:
            return self.positions[step % len(self.positions)]
        return self.positions[min(step, len(self.positions) - 1)]


# ── Built-in scenarios ────────────────────────────────────────────────────────

def _make_corridor_scenario() -> list[MockAgentTrack]:
    """Nurse walks toward robot; patient crosses laterally."""
    nurse_path = [(5.0 - i * 0.3, 0.0) for i in range(40)]
    patient_path = [(-3.0, -4.0 + i * 0.25) for i in range(40)]
    return [
        MockAgentTrack("nurse_0",   "staff",   AgentType.HUMAN, nurse_path,   0.92),
        MockAgentTrack("patient_0", "patient", AgentType.HUMAN, patient_path, 0.78),
    ]


def _make_waiting_room_scenario() -> list[MockAgentTrack]:
    """Three static visitors + one wheelchair user drifting toward robot."""
    static_visitors = [
        MockAgentTrack(f"visitor_{i}", "visitor", AgentType.HUMAN,
                       [(2.0 + i * 0.6, 2.0)] * 60, 0.75)
        for i in range(3)
    ]
    wheelchair_path = [(4.0 - i * 0.15, 0.3) for i in range(60)]
    wc = MockAgentTrack("wheelchair_0", "wheelchair_user", AgentType.HUMAN,
                        wheelchair_path, 0.88)
    return static_visitors + [wc]


def _make_empty_scenario() -> list[MockAgentTrack]:
    return []


_SCENARIOS: dict[str, Callable[[], list[MockAgentTrack]]] = {
    "hospital_corridor": _make_corridor_scenario,
    "waiting_room":      _make_waiting_room_scenario,
    "empty":             _make_empty_scenario,
}


# ── Mock source ───────────────────────────────────────────────────────────────

class MockPerceptionSource:
    """
    Deterministic detection stub for testing without real sensors.

    Parameters
    ----------
    scenario : one of "hospital_corridor", "waiting_room", "empty", or None
               for a random walk of `n_random_agents` agents.
    n_random_agents : number of random-walk agents when scenario=None.
    seed     : RNG seed for reproducibility (random scenario only).
    conf_jitter : add uniform noise ±conf_jitter to confidence each step.
    drop_prob   : probability of dropping each detection (simulates occlusion).
    """

    def __init__(
        self,
        scenario: str | None = "hospital_corridor",
        n_random_agents: int = 3,
        seed: int = 42,
        conf_jitter: float = 0.05,
        drop_prob: float = 0.0,
    ) -> None:
        self._rng = random.Random(seed)
        self._conf_jitter = conf_jitter
        self._drop_prob   = drop_prob
        self._step        = 0

        if scenario is None:
            self._tracks = self._make_random_tracks(n_random_agents)
        elif scenario in _SCENARIOS:
            self._tracks = _SCENARIOS[scenario]()
        else:
            raise ValueError(
                f"Unknown scenario {scenario!r}. "
                f"Available: {sorted(_SCENARIOS)}"
            )

    def _make_random_tracks(self, n: int) -> list[MockAgentTrack]:
        roles  = ["staff", "patient", "visitor", "wheelchair_user"]
        tracks: list[MockAgentTrack] = []
        for i in range(n):
            role  = self._rng.choice(roles)
            atype = AgentType.HUMAN
            start = (self._rng.uniform(-5, 5), self._rng.uniform(-5, 5))
            dx    = self._rng.uniform(-0.2, 0.2)
            dy    = self._rng.uniform(-0.2, 0.2)
            path  = [(start[0] + dx * t, start[1] + dy * t) for t in range(80)]
            tracks.append(MockAgentTrack(f"agent_{i}", role, atype, path,
                                         self._rng.uniform(0.65, 0.95), loop=True))
        return tracks

    @property
    def current_step(self) -> int:
        return self._step

    def reset(self) -> None:
        self._step = 0

    def step_detections(
        self,
        robot_xy: tuple[float, float] = (0.0, 0.0),
        timestamp: float | None = None,
    ) -> list[Detection]:
        """Alias for step() — kept for backward compatibility."""
        return self.step_forward(robot_xy=robot_xy, timestamp=timestamp)

    def step_forward(
        self,
        robot_xy: tuple[float, float] = (0.0, 0.0),
        timestamp: float | None = None,
    ) -> list[Detection]:
        """
        Advance one timestep and return Detection list.

        Parameters
        ----------
        robot_xy  : robot global position; used to compute relative positions.
        timestamp : defaults to self._step * 0.1 (10 Hz).

        Returns
        -------
        list[Detection]
        """
        t = timestamp if timestamp is not None else self._step * 0.1
        detections: list[Detection] = []

        for track in self._tracks:
            if self._drop_prob > 0 and self._rng.random() < self._drop_prob:
                continue
            pos = track.position_at(self._step)
            conf = track.confidence
            if self._conf_jitter > 0:
                conf = min(1.0, max(0.0, conf + self._rng.uniform(
                    -self._conf_jitter, self._conf_jitter
                )))
            detections.append(Detection(
                position_xy=pos,
                agent_type=track.agent_type,
                timestamp=t,
                confidence=conf,
                semantic_role=track.semantic_role,
            ))

        self._step += 1
        return detections

    # Keep the old name working too
    def step(  # type: ignore[override]
        self,
        robot_xy: tuple[float, float] = (0.0, 0.0),
        timestamp: float | None = None,
    ) -> list[Detection]:
        return self.step_forward(robot_xy=robot_xy, timestamp=timestamp)

    @property
    def available_scenarios(self) -> list[str]:
        return sorted(_SCENARIOS.keys())
