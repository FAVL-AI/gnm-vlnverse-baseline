"""
fleet_safe_vla/envs/isaaclab/yahboom_m3pro/scene_cfg.py

Isaac Sim scene configurations for the four canonical FleetSafe VisualNav
benchmark scenes. Scene names match benchmarks/scenes/canonical/SCENESET_v0.1.yaml
exactly — do not rename them.

All Isaac Lab imports are guarded so this module is importable without the
isaac conda environment (CI compatibility).

Scenes:
  straight_corridor  — 10 m corridor, no obstacles
  cluttered_static   — 8 static cylinder obstacles (exact canonical positions)
  narrow_passage     — 8 pillars leaving 0.65 m gap (exact canonical positions)
  dynamic_obstacle   — one dynamic crossing agent
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[4]

# ── Scene data structures (no Isaac dependency) ───────────────────────────────

@dataclass
class IsaacObstacleCfg:
    """A single static cylinder obstacle in the Isaac scene."""
    name: str
    pos_xyz: tuple[float, float, float]   # world position
    radius_m: float = 0.15
    height_m: float = 0.60
    color_rgba: tuple[float, float, float, float] = (0.85, 0.20, 0.10, 1.0)


@dataclass
class IsaacDynamicAgentCfg:
    """A dynamic agent (constant velocity, straight-line crossing)."""
    name: str
    start_xyz: tuple[float, float, float]
    velocity_xyz: tuple[float, float, float]    # constant velocity (m/s)
    radius_m: float = 0.15
    height_m: float = 0.60
    crossing_time_s: float = 10.0
    color_rgba: tuple[float, float, float, float] = (0.10, 0.40, 0.85, 1.0)


@dataclass
class IsaacSceneCfg:
    """
    Full Isaac scene configuration for one canonical benchmark scene.
    Matches SCENESET_v0.1.yaml geometry exactly.
    """
    scene_id: str
    scene_version: str
    description: str
    arena_length_m: float
    arena_width_m: float
    start_xyz: tuple[float, float, float]
    goal_xyz: tuple[float, float, float]
    optimal_path_m: float
    obstacles: list[IsaacObstacleCfg] = field(default_factory=list)
    dynamic_agents: list[IsaacDynamicAgentCfg] = field(default_factory=list)
    # Wall half-extents: [(x_centre, y_centre, z_centre, half_x, half_y, half_z)]
    walls: list[tuple[float, float, float, float, float, float]] = field(default_factory=list)
    goal_marker_radius_m: float = 0.20
    goal_marker_color: tuple[float, float, float, float] = (0.10, 0.85, 0.10, 0.7)


# ── Canonical scenes (geometry from SCENESET_v0.1.yaml) ───────────────────────

SCENE_STRAIGHT_CORRIDOR = IsaacSceneCfg(
    scene_id="straight_corridor",
    scene_version="0.1.0",
    description="10 m straight corridor, no obstacles. Tests baseline navigation quality.",
    arena_length_m=10.0,
    arena_width_m=3.0,
    start_xyz=(0.0, 0.0, 0.055),
    goal_xyz=(8.0, 0.0, 0.0),
    optimal_path_m=8.0,
    obstacles=[],
    dynamic_agents=[],
    walls=[
        # (cx, cy, cz, half_x, half_y, half_z)  — box walls along corridor
        (5.0,  1.5, 0.30, 5.0, 0.05, 0.30),   # left wall
        (5.0, -1.5, 0.30, 5.0, 0.05, 0.30),   # right wall
    ],
)

SCENE_CLUTTERED_STATIC = IsaacSceneCfg(
    scene_id="cluttered_static",
    scene_version="0.1.0",
    description="8 static cylindrical obstacles in an 8×8 m arena. Tests CBF intervention frequency.",
    arena_length_m=8.0,
    arena_width_m=8.0,
    start_xyz=(-3.0, -3.0, 0.055),
    goal_xyz=(3.0, 3.0, 0.0),
    optimal_path_m=8.49,
    obstacles=[
        # Exact positions from canonical SCENESET_v0.1.yaml (SceneSpec.obstacles)
        IsaacObstacleCfg("obstacle_0", ( 0.5,  1.0, 0.30), radius_m=0.15, height_m=0.60),
        IsaacObstacleCfg("obstacle_1", (-1.0,  2.0, 0.30), radius_m=0.15, height_m=0.60),
        IsaacObstacleCfg("obstacle_2", ( 1.5,  0.0, 0.30), radius_m=0.15, height_m=0.60),
        IsaacObstacleCfg("obstacle_3", (-0.5, -1.0, 0.30), radius_m=0.15, height_m=0.60),
        IsaacObstacleCfg("obstacle_4", ( 2.0,  1.5, 0.30), radius_m=0.15, height_m=0.60),
        IsaacObstacleCfg("obstacle_5", (-2.0, -0.5, 0.30), radius_m=0.15, height_m=0.60),
        IsaacObstacleCfg("obstacle_6", ( 0.0,  2.5, 0.30), radius_m=0.15, height_m=0.60),
        IsaacObstacleCfg("obstacle_7", ( 1.0, -1.5, 0.30), radius_m=0.15, height_m=0.60),
    ],
    dynamic_agents=[],
    walls=[],
)

SCENE_NARROW_PASSAGE = IsaacSceneCfg(
    scene_id="narrow_passage",
    scene_version="0.1.0",
    description="Two wall-like obstacle rows leaving a 0.65 m gap. Tests CBF-QP in high-constraint geometry.",
    arena_length_m=6.0,
    arena_width_m=6.0,
    start_xyz=(0.0, -2.5, 0.055),
    goal_xyz=(0.0, 2.5, 0.0),
    optimal_path_m=5.0,
    obstacles=[
        # Exact positions from canonical SCENESET_v0.1.yaml (SceneSpec.obstacles)
        # Left wall (3 pillars)
        IsaacObstacleCfg("obstacle_0", (-1.5,  0.0, 0.30), radius_m=0.20, height_m=0.60,
                         color_rgba=(0.70, 0.20, 0.10, 1.0)),
        IsaacObstacleCfg("obstacle_1", (-1.5,  0.6, 0.30), radius_m=0.20, height_m=0.60,
                         color_rgba=(0.70, 0.20, 0.10, 1.0)),
        IsaacObstacleCfg("obstacle_2", (-1.5, -0.6, 0.30), radius_m=0.20, height_m=0.60,
                         color_rgba=(0.70, 0.20, 0.10, 1.0)),
        # Right wall (3 pillars)
        IsaacObstacleCfg("obstacle_3", (1.5,  0.0, 0.30), radius_m=0.20, height_m=0.60,
                         color_rgba=(0.70, 0.20, 0.10, 1.0)),
        IsaacObstacleCfg("obstacle_4", (1.5,  0.6, 0.30), radius_m=0.20, height_m=0.60,
                         color_rgba=(0.70, 0.20, 0.10, 1.0)),
        IsaacObstacleCfg("obstacle_5", (1.5, -0.6, 0.30), radius_m=0.20, height_m=0.60,
                         color_rgba=(0.70, 0.20, 0.10, 1.0)),
        # Gap flanking obstacles
        IsaacObstacleCfg("obstacle_6", (-0.4, 0.0, 0.30), radius_m=0.20, height_m=0.60,
                         color_rgba=(0.70, 0.20, 0.10, 1.0)),
        IsaacObstacleCfg("obstacle_7", ( 0.4, 0.0, 0.30), radius_m=0.20, height_m=0.60,
                         color_rgba=(0.70, 0.20, 0.10, 1.0)),
    ],
    dynamic_agents=[],
    walls=[],
)

SCENE_DYNAMIC_OBSTACLE = IsaacSceneCfg(
    scene_id="dynamic_obstacle",
    scene_version="0.1.0",
    description="Single dynamic agent crossing perpendicular at midpoint. Tests temporal CBF.",
    arena_length_m=10.0,
    arena_width_m=3.0,
    start_xyz=(0.0, 0.0, 0.055),
    goal_xyz=(8.0, 0.0, 0.0),
    optimal_path_m=8.0,
    obstacles=[],
    dynamic_agents=[
        IsaacDynamicAgentCfg(
            name="dynamic_agent_0",
            start_xyz=(4.0, -1.5, 0.30),
            velocity_xyz=(0.0, 0.3, 0.0),
            radius_m=0.15,
            height_m=0.60,
            crossing_time_s=10.0,
        ),
    ],
    walls=[
        (5.0,  1.5, 0.30, 5.0, 0.05, 0.30),
        (5.0, -1.5, 0.30, 5.0, 0.05, 0.30),
    ],
)

# ── Scene registry ────────────────────────────────────────────────────────────

CANONICAL_SCENES: dict[str, IsaacSceneCfg] = {
    "straight_corridor": SCENE_STRAIGHT_CORRIDOR,
    "cluttered_static":  SCENE_CLUTTERED_STATIC,
    "narrow_passage":    SCENE_NARROW_PASSAGE,
    "dynamic_obstacle":  SCENE_DYNAMIC_OBSTACLE,
}


def get_scene(scene_id: str) -> IsaacSceneCfg:
    """Return IsaacSceneCfg by scene_id. Raises KeyError if unknown."""
    if scene_id not in CANONICAL_SCENES:
        raise KeyError(
            f"Unknown scene: {scene_id!r}. "
            f"Available: {sorted(CANONICAL_SCENES.keys())}"
        )
    return CANONICAL_SCENES[scene_id]


# ── Isaac spawner helpers (guarded) ───────────────────────────────────────────

try:
    import isaaclab.sim as sim_utils
    _ISAACLAB_AVAILABLE = True
except ImportError:
    _ISAACLAB_AVAILABLE = False


def spawn_scene_obstacles(scene: IsaacSceneCfg) -> None:
    """
    Spawn all static obstacles and walls for the given scene into /World.
    Must be called after AppLauncher and inside a scene design function.

    Raises ImportError if isaaclab is not installed.
    """
    if not _ISAACLAB_AVAILABLE:
        raise ImportError("isaaclab is not installed — cannot spawn scene.")

    # Static obstacles (cylinders)
    for obs in scene.obstacles:
        cfg = sim_utils.CylinderCfg(
            radius=obs.radius_m,
            height=obs.height_m,
            rigid_props=sim_utils.RigidBodyPropertiesCfg(kinematic_enabled=True),
            mass_props=sim_utils.MassPropertiesCfg(mass=10.0),
            collision_props=sim_utils.CollisionPropertiesCfg(),
            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=obs.color_rgba[:3]),
        )
        cfg.func(f"/World/Obstacles/{obs.name}", cfg, translation=obs.pos_xyz)

    # Walls (thin boxes)
    for i, (cx, cy, cz, hx, hy, hz) in enumerate(scene.walls):
        cfg = sim_utils.CuboidCfg(
            size=(hx * 2, hy * 2, hz * 2),
            rigid_props=sim_utils.RigidBodyPropertiesCfg(kinematic_enabled=True),
            mass_props=sim_utils.MassPropertiesCfg(mass=100.0),
            collision_props=sim_utils.CollisionPropertiesCfg(),
            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(0.5, 0.5, 0.5)),
        )
        cfg.func(f"/World/Walls/wall_{i}", cfg, translation=(cx, cy, cz))

    # Goal marker (flat cylinder)
    goal_cfg = sim_utils.CylinderCfg(
        radius=scene.goal_marker_radius_m,
        height=0.02,
        rigid_props=sim_utils.RigidBodyPropertiesCfg(kinematic_enabled=True),
        mass_props=sim_utils.MassPropertiesCfg(mass=0.0),
        collision_props=sim_utils.CollisionPropertiesCfg(),
        visual_material=sim_utils.PreviewSurfaceCfg(
            diffuse_color=scene.goal_marker_color[:3],
            opacity=scene.goal_marker_color[3],
        ),
    )
    gx, gy, _ = scene.goal_xyz
    goal_cfg.func("/World/GoalMarker", goal_cfg, translation=(gx, gy, 0.01))
