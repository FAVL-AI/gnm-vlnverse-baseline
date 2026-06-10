"""
visualnav_scenarios.py — Scene and seed-mode definitions for the VisualNav benchmark.

Eleven canonical scenes:
  straight_corridor  — open lane, no obstacles, speed benchmark.
  cluttered_static   — 8 randomly-placed static obstacles.
  narrow_passage     — two wall segments leaving a 0.65 m gap.
  dynamic_obstacle   — one moving obstacle (MuJoCo/mock) + static clutter.

Social-awareness scenes (require social_awareness layer):
  crowded_corridor       — 4 human agents within 1.5 m of robot start; triggers RED.
  crossing_pedestrian    — human 0.58 m from robot start; triggers RED immediately.
  blind_corner           — large pillar creates AMBER occlusion as robot approaches.
  doorway_bottleneck     — 0.9 m doorway with 3 humans and 1 robot waiting.
  multi_robot_corridor   — 2 peer robots + static clutter; yield logic required.
  occluded_obstacle_reveal — large occluder hiding a human until robot is close.
  social_red_zone_smoke  — deterministic RED trigger: human 0.35 m from robot start.

Three seed modes:
  smoke  — 1  seed  (fast pipeline sanity check)
  dev    — 10 seeds (development / regression)
  paper  — 50 seeds (publication-grade statistics)

Each scene defines:
  - fixed obstacle positions (relative to arena centre)
  - a canonical set of start/goal pairs with optimal path lengths
  - arena_size_m for visualization
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np


# ── Obstacle specification ────────────────────────────────────────────────────

@dataclass(frozen=True)
class ObstacleSpec:
    """A single circular obstacle."""
    x: float          # centre x (m), arena-frame
    y: float          # centre y (m), arena-frame
    radius_m: float = 0.15

    @property
    def position_xy(self) -> tuple[float, float]:
        return (self.x, self.y)


@dataclass(frozen=True)
class DynamicAgentSpec:
    """A dynamic obstacle that follows a circular path."""
    cx: float          # circle centre x (m)
    cy: float          # circle centre y (m)
    radius_m: float    # orbit radius (m)
    angular_speed_rad_per_s: float = 0.5
    obstacle_radius_m: float = 0.15
    agent_type: str = "unknown"   # "human", "robot", or "unknown"
    semantic_role: str = "unknown"  # SemanticRole label (e.g. "nurse", "patient")

    def position_at(self, t: float) -> tuple[float, float]:
        """Position at time t (seconds)."""
        angle = self.angular_speed_rad_per_s * t
        return (
            self.cx + self.radius_m * np.cos(angle),
            self.cy + self.radius_m * np.sin(angle),
        )


@dataclass(frozen=True)
class LinearAgentSpec:
    """
    A pedestrian / agent that walks in a straight line at constant velocity,
    with an optional start delay (the agent is stationary at start_xy until
    start_delay_s has elapsed, then moves at (vel_x, vel_y) m/s).

    Duck-typed with DynamicAgentSpec: provides position_at(), obstacle_radius_m,
    agent_type, and semantic_role so the runner needs no modification.
    """
    start_x: float
    start_y: float
    vel_x: float            # m/s
    vel_y: float            # m/s
    start_delay_s: float = 0.0
    obstacle_radius_m: float = 0.18
    agent_type: str = "human"
    semantic_role: str = "pedestrian"

    def position_at(self, t: float) -> tuple[float, float]:
        dt = max(0.0, t - self.start_delay_s)
        return (self.start_x + self.vel_x * dt, self.start_y + self.vel_y * dt)


@dataclass(frozen=True)
class PopupObstacleSpec:
    """
    A static obstacle that materialises at appear_s seconds into the episode and
    optionally vanishes at vanish_s.  Before appear_s (or after vanish_s) the
    spec reports position (1000, 1000) so the CBF and sim treat it as absent.

    Duck-typed with DynamicAgentSpec: provides position_at(), obstacle_radius_m,
    agent_type, semantic_role.  Works with the runner without modification.
    """
    x:                  float
    y:                  float
    appear_s:           float = 0.0
    vanish_s:           float = float("inf")
    obstacle_radius_m:  float = 0.50
    agent_type:         str   = "obstacle"
    semantic_role:      str   = "popup_block"

    def position_at(self, t: float) -> tuple[float, float]:
        if self.appear_s <= t < self.vanish_s:
            return (self.x, self.y)
        return (1000.0, 1000.0)  # far away — invisible to CBF and sim


# ── Start/goal pair ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class StartGoalPair:
    """One start/goal configuration within a scene."""
    start_xy:       tuple[float, float]
    goal_xy:        tuple[float, float]
    label:          str   = ""

    @property
    def optimal_path_m(self) -> float:
        """Euclidean straight-line distance from start to goal."""
        dx = self.goal_xy[0] - self.start_xy[0]
        dy = self.goal_xy[1] - self.start_xy[1]
        return float(np.hypot(dx, dy))


# ── Scene specification ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class SceneSpec:
    """
    Complete specification for one benchmark scene.

    Attributes
    ----------
    name            : Unique scene identifier (used as directory name in output).
    description     : One-sentence human-readable description.
    arena_size_m    : Side length of the square evaluation arena.
    obstacles       : Static obstacle list.
    dynamic_agents  : Moving obstacles (empty for static scenes).
    start_goal_pairs: Canonical navigation tasks in this scene.
    """
    name:             str
    description:      str
    arena_size_m:     float
    obstacles:        tuple[ObstacleSpec, ...]         = field(default=())
    dynamic_agents:   tuple[DynamicAgentSpec, ...]     = field(default=())
    start_goal_pairs: tuple[StartGoalPair, ...]        = field(default=())


# ── Canonical scenes ──────────────────────────────────────────────────────────

SCENE_STRAIGHT_CORRIDOR = SceneSpec(
    name        = "straight_corridor",
    description = "Open 8×8 m arena with no obstacles. Tests forward navigation efficiency.",
    arena_size_m = 8.0,
    obstacles    = (),
    dynamic_agents = (),
    start_goal_pairs = (
        StartGoalPair((0.0, -3.0), (0.0, 3.0),  "corridor_forward_6m"),
        StartGoalPair((-1.0, -3.0), (1.0, 3.0), "corridor_diagonal"),
        StartGoalPair((0.0, -3.0), (0.0, 1.5),  "corridor_short"),
        StartGoalPair((-2.0, 0.0), (2.0, 0.0),  "corridor_lateral_4m"),
    ),
)

SCENE_CLUTTERED_STATIC = SceneSpec(
    name        = "cluttered_static",
    description = "8 static cylindrical obstacles (~0.15 m radius) in an 8×8 m arena.",
    arena_size_m = 8.0,
    obstacles    = (
        ObstacleSpec( 0.5,  1.0),
        ObstacleSpec(-1.0,  2.0),
        ObstacleSpec( 1.5,  0.0),
        ObstacleSpec(-0.5, -1.0),
        ObstacleSpec( 2.0,  1.5),
        ObstacleSpec(-2.0, -0.5),
        ObstacleSpec( 0.0,  2.5),
        ObstacleSpec( 1.0, -1.5),
    ),
    start_goal_pairs = (
        StartGoalPair((-3.0, -3.0), (3.0, 3.0),  "clutter_diagonal"),
        StartGoalPair((-3.0,  0.0), (3.0, 0.0),  "clutter_forward"),
        StartGoalPair(( 0.0, -3.0), (0.0, 3.0),  "clutter_lateral"),
        StartGoalPair((-2.5, -2.5), (2.5, 2.5),  "clutter_short_diag"),
    ),
)

SCENE_NARROW_PASSAGE = SceneSpec(
    name        = "narrow_passage",
    description = "Two wall-like obstacle rows leaving a 0.65 m gap. Tests precise navigation.",
    arena_size_m = 6.0,
    obstacles    = (
        # Left wall (3 pillars)
        ObstacleSpec(-1.50, 0.0, radius_m=0.20),
        ObstacleSpec(-1.50, 0.6, radius_m=0.20),
        ObstacleSpec(-1.50,-0.6, radius_m=0.20),
        # Right wall (3 pillars)
        ObstacleSpec( 1.50, 0.0, radius_m=0.20),
        ObstacleSpec( 1.50, 0.6, radius_m=0.20),
        ObstacleSpec( 1.50,-0.6, radius_m=0.20),
        # Gap: [-0.65/2, +0.65/2] at x ≈ 0
        # Flanking obstacles to force through the gap
        ObstacleSpec(-0.40, 0.0, radius_m=0.20),
        ObstacleSpec( 0.40, 0.0, radius_m=0.20),
    ),
    start_goal_pairs = (
        StartGoalPair((0.0, -2.5), (0.0, 2.5), "passage_through"),
        StartGoalPair((-0.2,-2.5), (0.2, 2.5), "passage_offset_start"),
        StartGoalPair((0.0, -2.5), (0.5, 2.5), "passage_offset_goal"),
    ),
)

SCENE_DYNAMIC_OBSTACLE = SceneSpec(
    name        = "dynamic_obstacle",
    description = "One robot-sized agent on a circular path + light static clutter.",
    arena_size_m = 8.0,
    obstacles    = (
        ObstacleSpec(-2.5, -1.0),
        ObstacleSpec( 2.5,  1.0),
        ObstacleSpec( 0.0, -2.0),
    ),
    dynamic_agents = (
        DynamicAgentSpec(cx=0.0, cy=0.5, radius_m=1.2,
                         angular_speed_rad_per_s=0.6,
                         obstacle_radius_m=0.18),
    ),
    start_goal_pairs = (
        StartGoalPair((-3.0, -3.0), (3.0, 3.0),  "dynamic_diagonal"),
        StartGoalPair((-3.0,  0.0), (3.0, 0.0),  "dynamic_straight"),
        StartGoalPair(( 0.0, -3.0), (0.0, 3.0),  "dynamic_lateral"),
    ),
)

SCENE_CROWDED_CORRIDOR = SceneSpec(
    name        = "crowded_corridor",
    description = "4 humans within 1.5 m of robot start; 4 agents in radius → RED (hospital).",
    arena_size_m = 6.0,
    obstacles    = (),
    dynamic_agents = (
        # All 4 agents are within hospital crowding_radius_m (2.5 m) of robot start
        # (0, -2.5) at t=0.  position_at(0) = (cx + radius_m, cy).
        DynamicAgentSpec(cx=0.0,  cy=-2.5, radius_m=0.40, angular_speed_rad_per_s= 0.4,
                         obstacle_radius_m=0.20, agent_type="human"),  # → (0.40,-2.5) 0.40 m
        DynamicAgentSpec(cx=-0.3, cy=-2.0, radius_m=0.40, angular_speed_rad_per_s=-0.5,
                         obstacle_radius_m=0.20, agent_type="human"),  # → (0.10,-2.0) 0.51 m
        DynamicAgentSpec(cx=0.2,  cy=-1.8, radius_m=0.35, angular_speed_rad_per_s= 0.3,
                         obstacle_radius_m=0.20, agent_type="human"),  # → (0.55,-1.8) 0.89 m
        DynamicAgentSpec(cx=0.0,  cy=-2.0, radius_m=0.50, angular_speed_rad_per_s=-0.4,
                         obstacle_radius_m=0.20, agent_type="human"),  # → (0.50,-2.0) 0.71 m
    ),
    start_goal_pairs = (
        StartGoalPair((0.0, -2.5), (0.0, 2.5), "crowd_straight"),
        StartGoalPair((-1.0, -2.5), (1.0, 2.5), "crowd_diagonal"),
    ),
)

SCENE_CROSSING_PEDESTRIAN = SceneSpec(
    name        = "crossing_pedestrian",
    description = "Human 0.58 m from robot start; crosses path at speed. RED zone immediately.",
    arena_size_m = 8.0,
    obstacles    = (
        ObstacleSpec(-2.0, 0.5),
        ObstacleSpec( 2.0, 0.5),
    ),
    dynamic_agents = (
        # position_at(0) = (0.0+0.30, -2.5) = (0.30, -2.5)
        # dist from robot start (0,-3.0) = sqrt(0.09+0.25) = 0.583 m
        # hospital stop_distance_red_m = 0.60 m → RED at t=0
        DynamicAgentSpec(cx=0.0, cy=-2.5, radius_m=0.30,
                         angular_speed_rad_per_s=1.0,
                         obstacle_radius_m=0.18, agent_type="human"),
    ),
    start_goal_pairs = (
        StartGoalPair((0.0, -3.0), (0.0, 3.0), "cross_head_on"),
        StartGoalPair((-1.0, -3.0), (1.0, 3.0), "cross_offset"),
    ),
)

SCENE_BLIND_CORNER = SceneSpec(
    name        = "blind_corner",
    description = "Large pillar at intersection; human emerges unexpectedly from occlusion zone.",
    arena_size_m = 8.0,
    obstacles    = (
        ObstacleSpec( 0.0, 0.0, radius_m=0.50),   # large occluding pillar
        ObstacleSpec(-2.0, 0.0, radius_m=0.15),
        ObstacleSpec( 2.5, 1.5, radius_m=0.15),
    ),
    dynamic_agents = (
        DynamicAgentSpec(cx=0.0, cy=0.0, radius_m=0.9,
                         angular_speed_rad_per_s=0.8,
                         obstacle_radius_m=0.18, agent_type="human"),
    ),
    start_goal_pairs = (
        StartGoalPair((-3.0, -3.0), (3.0, 3.0), "corner_diagonal"),
        StartGoalPair(( 0.0, -3.0), (0.0, 3.0), "corner_direct"),
    ),
)

SCENE_DOORWAY_BOTTLENECK = SceneSpec(
    name        = "doorway_bottleneck",
    description = "0.9 m doorway with 3 humans + 1 robot waiting; tests bottleneck yield.",
    arena_size_m = 6.0,
    obstacles    = (
        # Door frame: two pillars leaving 0.90 m gap
        ObstacleSpec(-0.65, 0.0, radius_m=0.20),
        ObstacleSpec( 0.65, 0.0, radius_m=0.20),
        # Wall segments
        ObstacleSpec(-1.50, 0.0, radius_m=0.20),
        ObstacleSpec( 1.50, 0.0, radius_m=0.20),
    ),
    dynamic_agents = (
        DynamicAgentSpec(cx=0.0, cy=1.2,  radius_m=0.4, angular_speed_rad_per_s=0.3,
                         obstacle_radius_m=0.18, agent_type="human"),
        DynamicAgentSpec(cx=0.0, cy=-1.2, radius_m=0.4, angular_speed_rad_per_s=-0.3,
                         obstacle_radius_m=0.18, agent_type="human"),
        DynamicAgentSpec(cx=0.5, cy=1.0,  radius_m=0.3, angular_speed_rad_per_s=0.4,
                         obstacle_radius_m=0.18, agent_type="human"),
        DynamicAgentSpec(cx=-0.5, cy=-1.0, radius_m=0.3, angular_speed_rad_per_s=-0.2,
                         obstacle_radius_m=0.20, agent_type="robot"),
    ),
    start_goal_pairs = (
        StartGoalPair((0.0, -2.5), (0.0, 2.5), "doorway_through"),
        StartGoalPair((-0.2, -2.5), (0.2, 2.5), "doorway_offset"),
    ),
)

SCENE_MULTI_ROBOT_CORRIDOR = SceneSpec(
    name        = "multi_robot_corridor",
    description = "2 peer robots + static clutter in 8×8 m corridor. Tests robot-robot yield.",
    arena_size_m = 8.0,
    obstacles    = (
        ObstacleSpec( 1.0,  0.5),
        ObstacleSpec(-1.0, -0.5),
        ObstacleSpec( 0.0,  2.0),
    ),
    dynamic_agents = (
        DynamicAgentSpec(cx=1.0, cy=0.0,  radius_m=1.0, angular_speed_rad_per_s=0.5,
                         obstacle_radius_m=0.22, agent_type="robot"),
        DynamicAgentSpec(cx=-1.0, cy=0.5, radius_m=1.0, angular_speed_rad_per_s=-0.4,
                         obstacle_radius_m=0.22, agent_type="robot"),
    ),
    start_goal_pairs = (
        StartGoalPair((-3.0, -3.0), (3.0, 3.0), "multi_robot_diagonal"),
        StartGoalPair((-3.0,  0.0), (3.0, 0.0), "multi_robot_straight"),
        StartGoalPair(( 0.0, -3.0), (0.0, 3.0), "multi_robot_lateral"),
    ),
)

SCENE_OCCLUDED_OBSTACLE_REVEAL = SceneSpec(
    name        = "occluded_obstacle_reveal",
    description = "Large box hides a human until robot rounds the corner at close range.",
    arena_size_m = 8.0,
    obstacles    = (
        ObstacleSpec( 0.0,  0.5, radius_m=0.60),   # large occluder (box/column)
        ObstacleSpec(-2.0,  1.5, radius_m=0.15),
        ObstacleSpec( 2.5, -1.0, radius_m=0.15),
    ),
    dynamic_agents = (
        DynamicAgentSpec(cx=0.0, cy=0.5, radius_m=0.80,
                         angular_speed_rad_per_s=0.5,
                         obstacle_radius_m=0.18, agent_type="human"),
    ),
    start_goal_pairs = (
        StartGoalPair((-3.0, -2.0), (3.0, 2.0), "reveal_diagonal"),
        StartGoalPair(( 0.0, -3.0), (0.0, 3.0), "reveal_direct"),
    ),
)

SCENE_SOCIAL_RED_ZONE_SMOKE = SceneSpec(
    name        = "social_red_zone_smoke",
    description = "Deterministic RED-zone smoke test: human 0.35 m from robot start.",
    arena_size_m = 6.0,
    obstacles    = (
        ObstacleSpec(1.0, 0.0, radius_m=0.40),
    ),
    dynamic_agents = (
        # Agent 0: orbit centre = robot start; at t=0 → (0.35, -2.5), dist=0.35m
        # hospital stop_distance_red_m = 0.60 m → RED immediately
        DynamicAgentSpec(cx=0.0, cy=-2.5, radius_m=0.35,
                         angular_speed_rad_per_s=0.5,
                         obstacle_radius_m=0.18, agent_type="human"),
        DynamicAgentSpec(cx=0.0, cy=-1.5, radius_m=0.50,
                         angular_speed_rad_per_s=0.8,
                         obstacle_radius_m=0.18, agent_type="human"),
    ),
    start_goal_pairs = (
        StartGoalPair((0.0, -2.5), (0.0, 2.5), "red_zone_straight"),
    ),
)

# ── Scenario 1: Mid-navigation crossing interruption ─────────────────────────

SCENE_MID_CROSSING = SceneSpec(
    name        = "mid_crossing",
    description = (
        "Pedestrian enters path from the side after the robot has travelled ~40% "
        "of route (delay 3 s). Crossing point at arena centre; robot must slow / "
        "stop / reroute. Verifies FleetSafe responds mid-navigation, not only at t=0."
    ),
    arena_size_m = 12.0,
    obstacles    = (
        # Off-axis clutter — does NOT block the y=0 corridor axis
        ObstacleSpec(-2.0,  1.2, radius_m=0.12),
        ObstacleSpec( 2.0, -1.2, radius_m=0.12),
    ),
    dynamic_agents = (
        # Main crossing agent: waits 3 s at (-3, 0.5) south of crossing, then
        # walks north at 0.7 m/s. At the robot's cruise speed (~0.6 m/s from
        # (-5,0)), the robot will be near x=0 around t=8 s, when the agent
        # is at (0, 0.5 + 0.7*(8-3)≈4.0 m) — the paths intersect in the
        # robot's future cone ~3 s before reaching goal.
        LinearAgentSpec(
            start_x=-0.3, start_y=-3.5,
            vel_x=0.0, vel_y=0.75,
            start_delay_s=3.0,
            obstacle_radius_m=0.22,
            agent_type="human",
            semantic_role="crossing_pedestrian",
        ),
        # Second agent: slower crosser from the opposite side, 1 s later.
        LinearAgentSpec(
            start_x=0.4, start_y=3.5,
            vel_x=0.0, vel_y=-0.55,
            start_delay_s=4.0,
            obstacle_radius_m=0.20,
            agent_type="human",
            semantic_role="crossing_pedestrian",
        ),
    ),
    start_goal_pairs = (
        StartGoalPair((-5.0, 0.0), (5.0, 0.0), "corridor_crossing_head_on"),
        StartGoalPair((-5.0, 0.5), (5.0, -0.5), "corridor_crossing_offset"),
    ),
)


# ── Scenario 2: Congestion stress (8 agents) ──────────────────────────────────

SCENE_CONGESTION_STRESS_8 = SceneSpec(
    name        = "congestion_stress_8",
    description = (
        "Eight human agents in a 10 m corridor; robot must navigate from end to "
        "end. Measures hesitation latency, TTC, SPL degradation, and zone-RED "
        "frequency under sustained congestion."
    ),
    arena_size_m = 10.0,
    obstacles    = (
        ObstacleSpec( 0.5, 0.3, radius_m=0.12),
        ObstacleSpec(-0.5, -0.3, radius_m=0.12),
    ),
    dynamic_agents = (
        # Mix of speeds and orbit radii to create varied congestion patterns.
        # Arranged so at least 4 are within the hospital crowding_radius (2.5 m)
        # of the midpoint at various times → sustained AMBER/RED.
        DynamicAgentSpec(cx= 0.0, cy= 0.0, radius_m=0.50, angular_speed_rad_per_s= 0.60,
                         obstacle_radius_m=0.20, agent_type="human", semantic_role="staff"),
        DynamicAgentSpec(cx= 1.0, cy= 0.5, radius_m=0.45, angular_speed_rad_per_s=-0.55,
                         obstacle_radius_m=0.20, agent_type="human", semantic_role="visitor"),
        DynamicAgentSpec(cx=-1.0, cy=-0.5, radius_m=0.55, angular_speed_rad_per_s= 0.50,
                         obstacle_radius_m=0.20, agent_type="human", semantic_role="patient"),
        DynamicAgentSpec(cx= 0.5, cy=-1.0, radius_m=0.40, angular_speed_rad_per_s=-0.70,
                         obstacle_radius_m=0.20, agent_type="human", semantic_role="visitor"),
        DynamicAgentSpec(cx=-0.5, cy= 1.0, radius_m=0.60, angular_speed_rad_per_s= 0.45,
                         obstacle_radius_m=0.22, agent_type="human", semantic_role="wheelchair_user"),
        DynamicAgentSpec(cx= 1.5, cy=-0.5, radius_m=0.35, angular_speed_rad_per_s=-0.65,
                         obstacle_radius_m=0.20, agent_type="human", semantic_role="staff"),
        DynamicAgentSpec(cx=-1.5, cy= 0.5, radius_m=0.50, angular_speed_rad_per_s= 0.55,
                         obstacle_radius_m=0.20, agent_type="human", semantic_role="visitor"),
        DynamicAgentSpec(cx= 0.0, cy=-1.5, radius_m=0.45, angular_speed_rad_per_s=-0.50,
                         obstacle_radius_m=0.20, agent_type="human", semantic_role="patient"),
    ),
    start_goal_pairs = (
        StartGoalPair((-4.0, 0.0), (4.0, 0.0), "congestion_straight"),
        StartGoalPair((-4.0, -0.5), (4.0, 0.5), "congestion_offset"),
    ),
)


# ── Scenario 4a: E-stop resume ────────────────────────────────────────────────

SCENE_ESTOP_RESUME = SceneSpec(
    name        = "estop_resume",
    description = (
        "Straight corridor.  An e-stop is injected via the _EstopAdapter wrapper "
        "(zero cmd_vel at steps 20–60), then control resumes.  No popup obstacles "
        "needed: the adapter-level injection proves the control-layer stop/resume "
        "behaviour independently of obstacle geometry."
    ),
    arena_size_m = 10.0,
    obstacles    = (
        ObstacleSpec(x= 0.0, y= 2.5, radius_m=0.20),
        ObstacleSpec(x= 0.0, y=-2.5, radius_m=0.20),
        # Mid-corridor pole: robot must resume AND avoid it after e-stop
        ObstacleSpec(x= 1.5, y= 0.0, radius_m=0.15),
    ),
    dynamic_agents = (),   # stop/resume injected at adapter level
    start_goal_pairs = (
        StartGoalPair((-4.0,  0.0), (4.0,  0.0), "estop_straight"),
        StartGoalPair((-4.0,  0.3), (4.0, -0.3), "estop_offset"),
    ),
)


# ── Scenario 4b: Blocked corridor reroute ─────────────────────────────────────

SCENE_BLOCKED_CORRIDOR = SceneSpec(
    name        = "blocked_corridor",
    description = (
        "Three popup pillars (radius=0.18 m, appear at 3 s) form a partial barrier "
        "across the corridor axis.  radius=0.18 m keeps obstacle surfaces within the "
        "CBF's 0.45 m detection range so the safety filter can prevent collision. "
        "Robot must deflect and reroute around the cluster."
    ),
    arena_size_m = 10.0,
    obstacles    = (
        ObstacleSpec(x= 0.0, y= 2.5, radius_m=0.20),
        ObstacleSpec(x= 0.0, y=-2.5, radius_m=0.20),
    ),
    dynamic_agents = (
        # Three pillars 0.4 m apart covering ±0.4 m laterally.
        # radius=0.18 m: CBF stops at centre_dist=0.45 m, collision at 0.28 m → 0.17 m margin.
        PopupObstacleSpec(x=0.0, y= 0.0, appear_s=3.0, obstacle_radius_m=0.18,
                          agent_type="obstacle", semantic_role="corridor_block"),
        PopupObstacleSpec(x=0.0, y= 0.4, appear_s=3.0, obstacle_radius_m=0.18,
                          agent_type="obstacle", semantic_role="corridor_block"),
        PopupObstacleSpec(x=0.0, y=-0.4, appear_s=3.0, obstacle_radius_m=0.18,
                          agent_type="obstacle", semantic_role="corridor_block"),
    ),
    start_goal_pairs = (
        StartGoalPair((-4.0,  0.0), (4.0,  0.0), "block_straight"),
        StartGoalPair((-4.0,  0.5), (4.0, -0.5), "block_offset"),
    ),
)


# ── Scenario 4c: Relay interruption recovery ──────────────────────────────────

SCENE_RELAY_INTERRUPTION = SceneSpec(
    name        = "relay_interruption",
    description = (
        "Straight corridor with a static mid-corridor obstacle.  A relay blackout "
        "is injected at step 20–50 (t=2–5 s) via the adapter wrapper: zero cmd_vel "
        "for 30 steps, then normal navigation resumes.  Robot must coast to a safe "
        "stop and re-engage after the relay is restored."
    ),
    arena_size_m = 10.0,
    obstacles    = (
        ObstacleSpec(x= 0.0, y= 2.5, radius_m=0.20),   # corridor walls
        ObstacleSpec(x= 0.0, y=-2.5, radius_m=0.20),
        ObstacleSpec(x= 2.0, y= 0.0, radius_m=0.15),   # mid-path obstacle to test post-relay CBF
    ),
    dynamic_agents = (),   # relay blackout injected at adapter level, not scene level
    start_goal_pairs = (
        StartGoalPair((-4.0,  0.0), (4.0,  0.0), "relay_straight"),
        StartGoalPair((-4.0,  0.3), (4.0, -0.3), "relay_offset"),
    ),
)


# ── Registry — all canonical scenes in evaluation order. ─────────────────────
# Hospital semantic scenes are imported lazily to avoid a circular import
# (hospital_scenes.py imports from this module).
def _build_all_scenes() -> dict[str, "SceneSpec"]:
    base: dict[str, SceneSpec] = {
        "straight_corridor":        SCENE_STRAIGHT_CORRIDOR,
        "cluttered_static":         SCENE_CLUTTERED_STATIC,
        "narrow_passage":           SCENE_NARROW_PASSAGE,
        "dynamic_obstacle":         SCENE_DYNAMIC_OBSTACLE,
        "crowded_corridor":         SCENE_CROWDED_CORRIDOR,
        "crossing_pedestrian":      SCENE_CROSSING_PEDESTRIAN,
        "mid_crossing":             SCENE_MID_CROSSING,
        "congestion_stress_8":      SCENE_CONGESTION_STRESS_8,
        "estop_resume":             SCENE_ESTOP_RESUME,
        "blocked_corridor":         SCENE_BLOCKED_CORRIDOR,
        "relay_interruption":       SCENE_RELAY_INTERRUPTION,
        "blind_corner":             SCENE_BLIND_CORNER,
        "doorway_bottleneck":       SCENE_DOORWAY_BOTTLENECK,
        "multi_robot_corridor":     SCENE_MULTI_ROBOT_CORRIDOR,
        "occluded_obstacle_reveal": SCENE_OCCLUDED_OBSTACLE_REVEAL,
        "social_red_zone_smoke":    SCENE_SOCIAL_RED_ZONE_SMOKE,
    }
    try:
        from fleet_safe_vla.benchmarks.hospital_scenes import HOSPITAL_SCENES
        base.update(HOSPITAL_SCENES)
    except Exception:
        pass
    return base


ALL_SCENES: dict[str, SceneSpec] = _build_all_scenes()


# ── Seed modes ────────────────────────────────────────────────────────────────

SEED_MODES: dict[str, list[int]] = {
    "smoke": [0],
    "dev":   list(range(10)),
    "paper": list(range(50)),
}


def get_seeds(mode_or_count: str | int) -> list[int]:
    """
    Parse seed specification.

    Accepts:
      "smoke"       → [0]
      "dev"         → [0, 1, ..., 9]
      "paper"       → [0, 1, ..., 49]
      "0,1,5"       → [0, 1, 5]
      10            → [0, 1, ..., 9]
    """
    if isinstance(mode_or_count, int):
        return list(range(mode_or_count))
    if mode_or_count in SEED_MODES:
        return SEED_MODES[mode_or_count]
    # "0,1,2" format
    parts = [p.strip() for p in mode_or_count.split(",") if p.strip()]
    return [int(p) for p in parts]


def get_scenes(scene_spec: str | Sequence[str] | None = None) -> list[SceneSpec]:
    """
    Parse scene specification.

    Accepts:
      None / "all"         → all ten canonical scenes
      "straight_corridor"  → one scene
      ["cluttered_static", "narrow_passage"] → two scenes
      "cluttered_static,narrow_passage"      → two scenes (comma-separated)
    """
    if scene_spec is None or scene_spec == "all":
        return list(ALL_SCENES.values())

    if isinstance(scene_spec, str):
        keys = [k.strip() for k in scene_spec.split(",") if k.strip()]
    else:
        keys = list(scene_spec)

    scenes = []
    for k in keys:
        if k not in ALL_SCENES:
            raise ValueError(
                f"Unknown scene: {k!r}. Available: {list(ALL_SCENES.keys())}"
            )
        scenes.append(ALL_SCENES[k])
    return scenes
