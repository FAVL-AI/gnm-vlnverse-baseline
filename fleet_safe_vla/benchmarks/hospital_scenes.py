"""
hospital_scenes.py — Named scene definitions for the FleetSafe demo and benchmark.

Each SceneSpec carries the obstacle layout, start/goal positions, and episode
parameters for one named scenario.  The IsaacNavBenchmarkEnv accepts
fixed_positions and obstacle_radii directly from a SceneSpec.

Coordinate convention: x = forward along corridor, y = lateral.
Hospital corridor zone: y ∈ [-1.5, 2.0], x ∈ [-10, 10].
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple, List, Tuple

from fleet_safe_vla.social_awareness.zone_map import ZoneMap, ZonePolygon


# ── Minimal start/goal pair (mirrors visualnav_scenarios.StartGoalPair) ────────

class _StartGoalPair(NamedTuple):
    start_xy: Tuple[float, float]
    goal_xy:  Tuple[float, float]
    label:    str = ""


# ── Dynamic agent spec ────────────────────────────────────────────────────────

@dataclass
class DynamicAgentSpec:
    """Minimal spec for a semantic agent within a hospital scene."""
    x: float = 0.0
    y: float = 0.0
    semantic_role: str = "unknown"     # "nurse", "patient", "visitor", "gurney", …
    agent_type: str = "human"          # "human", "robot", or "unknown"
    obstacle_radius_m: float = 0.30

    def position_at(self, t: float) -> Tuple[float, float]:
        """Return (x, y) at time t — static agents return fixed position."""
        return (self.x, self.y)


# ── Scene spec ────────────────────────────────────────────────────────────────

@dataclass
class SceneSpec:
    name:               str
    obstacle_positions: List[Tuple[float, float]] = field(default_factory=list)
    obstacle_radii:     List[float]               = field(default_factory=list)
    start_xy:           Tuple[float, float]        = (0.0, 0.0)
    goal_xy:            Tuple[float, float]        = (5.0, 0.0)
    max_steps:          int                        = 300
    dynamic_agents:     Tuple[DynamicAgentSpec, ...] = field(default_factory=tuple)

    @property
    def start_goal_pairs(self) -> Tuple[_StartGoalPair, ...]:
        """Single canonical start/goal pair derived from start_xy and goal_xy."""
        return (_StartGoalPair(self.start_xy, self.goal_xy, self.name),)


# ── Legacy SCENES dict (kept for backward compatibility) ──────────────────────

SCENES: dict[str, SceneSpec] = {
    # One obstacle directly ahead + one offset — clean CBF demo
    "hospital_corridor": SceneSpec(
        name               = "hospital_corridor",
        obstacle_positions = [(1.5, 0.1), (3.0, -0.2)],
        obstacle_radii     = [0.20, 0.20],
        start_xy           = (-2.5, 0.0),
        goal_xy            = (4.5, 0.0),
        max_steps          = 300,
    ),
    # Single central obstacle — simplest possible demo
    "straight_corridor": SceneSpec(
        name               = "straight_corridor",
        obstacle_positions = [(2.0, 0.0)],
        obstacle_radii     = [0.20],
        start_xy           = (0.0, 0.0),
        goal_xy            = (5.0, 0.0),
        max_steps          = 200,
    ),
    # Three obstacles — more challenging, shows multiple interventions
    "cluttered_navigation": SceneSpec(
        name               = "cluttered_navigation",
        obstacle_positions = [(1.0, 0.3), (2.5, -0.3), (4.0, 0.2)],
        obstacle_radii     = [0.20, 0.20, 0.20],
        start_xy           = (-1.0, 0.0),
        goal_xy            = (5.5, 0.0),
        max_steps          = 400,
    ),
}


def get_scene_config(scene_name: str) -> SceneSpec:
    """Return SceneSpec by name, defaulting to hospital_corridor."""
    return SCENES.get(scene_name, SCENES["hospital_corridor"])


# ── Hospital benchmark scenes (semantic, with dynamic agents) ─────────────────

SCENE_HOSPITAL_CORRIDOR = SceneSpec(
    name               = "hospital_corridor",
    obstacle_positions = [(1.5, 0.1), (3.0, -0.2)],
    obstacle_radii     = [0.20, 0.20],
    start_xy           = (-2.5, 0.0),
    goal_xy            = (4.5, 0.0),
    max_steps          = 300,
    dynamic_agents     = (
        DynamicAgentSpec(x=1.0,  y= 0.3, semantic_role="nurse",  agent_type="human", obstacle_radius_m=0.30),
        DynamicAgentSpec(x=2.5,  y=-0.2, semantic_role="gurney", agent_type="robot", obstacle_radius_m=0.40),
    ),
)

SCENE_HOSPITAL_ICU_APPROACH = SceneSpec(
    name               = "hospital_icu_approach",
    obstacle_positions = [(1.0, 0.2), (2.5, -0.1)],
    obstacle_radii     = [0.25, 0.25],
    start_xy           = (-3.0, 0.0),
    goal_xy            = (4.0, 0.0),
    max_steps          = 300,
    dynamic_agents     = (
        DynamicAgentSpec(x=1.5,  y= 0.5, semantic_role="wheelchair_user", agent_type="human", obstacle_radius_m=0.45),
        DynamicAgentSpec(x=2.8,  y=-0.3, semantic_role="patient",         agent_type="human", obstacle_radius_m=0.30),
    ),
)

SCENE_HOSPITAL_ELEVATOR_LOBBY = SceneSpec(
    name               = "hospital_elevator_lobby",
    obstacle_positions = [(0.5, 0.5), (0.5, -0.5)],
    obstacle_radii     = [0.20, 0.20],
    start_xy           = (-2.0, 0.0),
    goal_xy            = (3.0, 0.0),
    max_steps          = 250,
    dynamic_agents     = (
        DynamicAgentSpec(x=0.5,  y= 0.8, semantic_role="visitor", agent_type="human", obstacle_radius_m=0.30),
    ),
)

# Canonical three-scene hospital benchmark dict
HOSPITAL_SCENES: dict[str, SceneSpec] = {
    "hospital_corridor":       SCENE_HOSPITAL_CORRIDOR,
    "hospital_icu_approach":   SCENE_HOSPITAL_ICU_APPROACH,
    "hospital_elevator_lobby": SCENE_HOSPITAL_ELEVATOR_LOBBY,
}


# ── Zone maps (per-scene spatial profile switching) ───────────────────────────
# Each ZoneMap is keyed to one hospital scene and contains the polygon zones
# that a SocialRiskFilter uses to select an EnvironmentProfile by robot position.
# profile_name values must match keys in environment_profiles.py.

HOSPITAL_ZONE_MAPS: dict[str, ZoneMap] = {

    # hospital_corridor: main corridor is emergency_corridor profile
    # Robot at (0, 0) → "emergency_corridor"; outside all zones → "hospital"
    "hospital_corridor": ZoneMap(
        zones=[
            ZonePolygon(
                "emergency_corridor",
                "emergency_corridor",
                [(-10.0, -1.5), (-10.0, 1.5), (10.0, 1.5), (10.0, -1.5)],
            ),
        ],
        default_profile_name="hospital",
    ),

    # hospital_icu_approach: ICU zone in upper half (y > 2)
    # Robot at (-5, 4) → "icu"; default → "hospital"
    "hospital_icu_approach": ZoneMap(
        zones=[
            ZonePolygon(
                "icu",
                "icu",
                [(-10.0, 2.0), (-10.0, 8.0), (10.0, 8.0), (10.0, 2.0)],
            ),
        ],
        default_profile_name="hospital",
    ),

    # hospital_elevator_lobby: waiting room in lower half (y < -2)
    # Robot at (0, -4) → "waiting_room"; default → "hospital"
    "hospital_elevator_lobby": ZoneMap(
        zones=[
            ZonePolygon(
                "waiting_room",
                "waiting_room",
                [(-5.0, -2.0), (-5.0, -8.0), (5.0, -8.0), (5.0, -2.0)],
            ),
        ],
        default_profile_name="hospital",
    ),
}


# ── Legacy zone polygon list (used by HospitalWorldLoader) ────────────────────

_HOSPITAL_ZONES: list[ZonePolygon] = [
    ZonePolygon(
        "main_corridor",
        "hospital",
        [(-10.0, -1.5), (-10.0, 2.0), (10.0, 2.0), (10.0, -1.5)],
    ),
    ZonePolygon(
        "icu_zone",
        "hospital",
        [(0.0, 2.0), (0.0, 5.0), (10.0, 5.0), (10.0, 2.0)],
    ),
    ZonePolygon(
        "nurse_station",
        "hospital",
        [(-2.0, -1.5), (-2.0, -4.0), (2.0, -4.0), (2.0, -1.5)],
    ),
    ZonePolygon(
        "emergency_entrance",
        "emergency_corridor",
        [(-10.0, -4.0), (-10.0, -1.5), (-2.0, -1.5), (-2.0, -4.0)],
    ),
    ZonePolygon(
        "storage_wing",
        "hospital",
        [(5.0, -4.0), (5.0, -1.5), (10.0, -1.5), (10.0, -4.0)],
    ),
]
