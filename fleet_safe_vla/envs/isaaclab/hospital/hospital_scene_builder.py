"""
hospital_scene_builder.py — Procedural USD hospital scene using Isaac Lab sim_utils.

Builds a 3-D hospital floor plan with actual room geometry (walls, corridor,
zone-coloured floor panels, lighting) entirely from Isaac Lab primitives —
no external USD asset required.

Floor plan (metres, arena centre at origin, all geometry at z=0):

                           y = +8
    ┌──────────┬──────────────┬──────────┐
    │   ICU    │ Nurse Station│ Pharmacy │
    │ x∈[-10,-2]│  x∈[-2, 2] │x∈[ 2,10]│  y ∈ [2, 8]
    ├──────────┴──────────────┴──────────┤
    │       Emergency Corridor            │  y ∈ [-1.5, 2.0]
    ├─────────────────────────────────── ┤
    │         Waiting Room               │  y ∈ [-8, -1.5]
    └────────────────────────────────────┘
                           y = -8

Zone colours (floor panels):
  ICU               → calm blue      (0.20, 0.40, 0.80)
  Nurse Station     → neutral grey   (0.55, 0.55, 0.60)
  Pharmacy          → teal           (0.20, 0.65, 0.65)
  Emergency Corridor→ warm cream     (0.95, 0.92, 0.82)
  Waiting Room      → soft green     (0.40, 0.65, 0.45)

Walls: white/off-white cuboids 0.25 m thick, 2.5 m tall.

Semantic agents (capsules with role-coded colours) are spawned separately
by HospitalAgentSpawner, which is called from HospitalWorldLoader.

All spawn functions return a list of created prim paths so the caller can
register them with IsaacNavBenchmarkEnv._owned_prim_paths for cleanup.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


# ── Zone colour palette ────────────────────────────────────────────────────────

_ZONE_COLORS: dict[str, tuple[float, float, float]] = {
    "icu":                (0.20, 0.40, 0.80),
    "nurse_station":      (0.55, 0.55, 0.60),
    "pharmacy":           (0.20, 0.65, 0.65),
    "emergency_corridor": (0.95, 0.92, 0.82),
    "waiting_room":       (0.40, 0.65, 0.45),
}

# Role → (R, G, B) for agent capsules
_ROLE_COLORS: dict[str, tuple[float, float, float]] = {
    "nurse":           (0.10, 0.60, 0.90),
    "doctor":          (0.15, 0.15, 0.70),
    "patient":         (0.90, 0.90, 0.70),
    "wheelchair_user": (0.70, 0.40, 0.10),
    "gurney":          (0.75, 0.75, 0.80),
    "cleaning_cart":   (0.80, 0.80, 0.20),
    "delivery_robot":  (0.30, 0.80, 0.30),
    "visitor":         (0.80, 0.50, 0.20),
    "unknown":         (0.60, 0.60, 0.60),
}

# ── Wall / zone geometry constants ─────────────────────────────────────────────

WALL_THICKNESS = 0.25
WALL_HEIGHT    = 2.50
FLOOR_THICKNESS = 0.05
CEILING_Z      = WALL_HEIGHT + 0.10   # used for dome light placement

# Zone floor Z offset so it's slightly above the ground plane (avoids z-fight)
FLOOR_PANEL_Z  = FLOOR_THICKNESS / 2.0

# Arena bounds
X_MIN, X_MAX = -10.0, 10.0
Y_MIN, Y_MAX = -8.0,   8.0

# Zone Y boundaries
Y_ICU_LO       =  2.0
Y_CORR_LO      = -1.5
Y_WAIT_LO      = -8.0

# Zone X boundaries (horizontal splits in the top half)
X_ICU_HI       = -2.0
X_PHARMACY_LO  =  2.0


# ── Internal dataclass ─────────────────────────────────────────────────────────

@dataclass
class _Box:
    """Centre + half-extents for a cuboid prim."""
    cx: float; cy: float; cz: float
    hx: float; hy: float; hz: float
    color: tuple[float, float, float]
    label: str


# ── Scene geometry builders ────────────────────────────────────────────────────

def _floor_panel(
    label: str,
    x_lo: float, x_hi: float,
    y_lo: float, y_hi: float,
    color: tuple[float, float, float],
) -> _Box:
    cx = (x_lo + x_hi) / 2.0
    cy = (y_lo + y_hi) / 2.0
    return _Box(cx=cx, cy=cy, cz=FLOOR_PANEL_Z,
                hx=(x_hi - x_lo) / 2.0, hy=(y_hi - y_lo) / 2.0, hz=FLOOR_THICKNESS / 2.0,
                color=color, label=label)


def _wall(
    label: str,
    cx: float, cy: float,
    hx: float, hy: float,
    color: tuple[float, float, float] = (0.95, 0.95, 0.95),
) -> _Box:
    return _Box(cx=cx, cy=cy, cz=WALL_HEIGHT / 2.0,
                hx=hx, hy=hy, hz=WALL_HEIGHT / 2.0,
                color=color, label=label)


def _hospital_geometry() -> list[_Box]:
    """Return all floor panels and walls for the hospital floor plan."""
    boxes: list[_Box] = []

    # ── Floor panels (zone-coloured) ─────────────────────────────────────────
    boxes.append(_floor_panel("floor_icu",       X_MIN, X_ICU_HI,      Y_ICU_LO, Y_MAX,
                               _ZONE_COLORS["icu"]))
    boxes.append(_floor_panel("floor_nurse",      X_ICU_HI, X_PHARMACY_LO, Y_ICU_LO, Y_MAX,
                               _ZONE_COLORS["nurse_station"]))
    boxes.append(_floor_panel("floor_pharmacy",   X_PHARMACY_LO, X_MAX,  Y_ICU_LO, Y_MAX,
                               _ZONE_COLORS["pharmacy"]))
    boxes.append(_floor_panel("floor_corridor",   X_MIN, X_MAX, Y_CORR_LO, Y_ICU_LO,
                               _ZONE_COLORS["emergency_corridor"]))
    boxes.append(_floor_panel("floor_waiting",    X_MIN, X_MAX, Y_WAIT_LO, Y_CORR_LO,
                               _ZONE_COLORS["waiting_room"]))

    # ── Perimeter walls ────────────────────────────────────────────────────────
    half_x = (X_MAX - X_MIN) / 2.0
    half_y = (Y_MAX - Y_MIN) / 2.0
    cx_mid = (X_MIN + X_MAX) / 2.0
    cy_mid = (Y_MIN + Y_MAX) / 2.0

    boxes.append(_wall("wall_north", cx_mid, Y_MAX, half_x + WALL_THICKNESS, WALL_THICKNESS / 2.0))
    boxes.append(_wall("wall_south", cx_mid, Y_MIN, half_x + WALL_THICKNESS, WALL_THICKNESS / 2.0))
    boxes.append(_wall("wall_east",  X_MAX, cy_mid, WALL_THICKNESS / 2.0, half_y + WALL_THICKNESS))
    boxes.append(_wall("wall_west",  X_MIN, cy_mid, WALL_THICKNESS / 2.0, half_y + WALL_THICKNESS))

    # ── Internal partition: corridor / upper rooms ─────────────────────────────
    # Horizontal wall at y = Y_ICU_LO with doorway gap at x ∈ [-1, 1]
    gap_x = 1.0
    left_wall_hx  = (X_ICU_HI + WALL_THICKNESS / 2.0 - X_MIN - gap_x) / 2.0
    left_wall_cx  = X_MIN + left_wall_hx
    right_wall_hx = (X_MAX - (X_PHARMACY_LO - WALL_THICKNESS / 2.0) - gap_x) / 2.0
    right_wall_cx = X_MAX - right_wall_hx

    if left_wall_hx > 0:
        boxes.append(_wall("wall_partition_left",  left_wall_cx,  Y_ICU_LO,
                            left_wall_hx, WALL_THICKNESS / 2.0))
    if right_wall_hx > 0:
        boxes.append(_wall("wall_partition_right", right_wall_cx, Y_ICU_LO,
                            right_wall_hx, WALL_THICKNESS / 2.0))

    # Internal vertical dividers between ICU / Nurse Station / Pharmacy
    top_half_y = (Y_MAX - Y_ICU_LO) / 2.0
    top_cy = Y_ICU_LO + top_half_y
    boxes.append(_wall("wall_icu_nurse",    X_ICU_HI,      top_cy, WALL_THICKNESS / 2.0, top_half_y))
    boxes.append(_wall("wall_nurse_pharm",  X_PHARMACY_LO, top_cy, WALL_THICKNESS / 2.0, top_half_y))

    # Horizontal wall at y = Y_CORR_LO (corridor / waiting room boundary)
    # Leave a doorway gap at x ∈ [-1, 1]
    left_w2_hx = (-gap_x - X_MIN - WALL_THICKNESS / 2.0) / 2.0
    left_w2_cx = X_MIN + left_w2_hx
    right_w2_hx = (X_MAX - gap_x - WALL_THICKNESS / 2.0) / 2.0
    right_w2_cx = X_MAX - right_w2_hx
    if left_w2_hx > 0:
        boxes.append(_wall("wall_corr_wait_left",  left_w2_cx,  Y_CORR_LO,
                            left_w2_hx, WALL_THICKNESS / 2.0))
    if right_w2_hx > 0:
        boxes.append(_wall("wall_corr_wait_right", right_w2_cx, Y_CORR_LO,
                            right_w2_hx, WALL_THICKNESS / 2.0))

    # ── Zone label pillars (thin coloured columns at corners) ──────────────────
    pillar_r = 0.10
    for px, py, zone in [
        (-8.0, 5.0, "icu"), (0.0, 5.0, "nurse_station"),
        (7.0, 5.0, "pharmacy"), (0.0, 0.0, "emergency_corridor"),
        (0.0, -5.0, "waiting_room"),
    ]:
        boxes.append(_Box(cx=px, cy=py, cz=WALL_HEIGHT / 2.0,
                           hx=pillar_r, hy=pillar_r, hz=WALL_HEIGHT / 2.0,
                           color=_ZONE_COLORS[zone], label=f"pillar_{zone}"))

    return boxes


# ── Isaac Sim spawn functions ──────────────────────────────────────────────────

def spawn_hospital_scene(base_prim: str = "/World/Hospital") -> list[str]:
    """
    Spawn the full procedural hospital scene into the current Isaac Sim stage.

    Must be called inside an active AppLauncher/SimulationContext.

    Parameters
    ----------
    base_prim : USD prim path prefix for all hospital geometry.

    Returns
    -------
    list of created prim paths (register with IsaacNavBenchmarkEnv._owned_prim_paths)
    """
    import isaaclab.sim as sim_utils

    created: list[str] = []
    boxes = _hospital_geometry()

    for box in boxes:
        prim_path = f"{base_prim}/{box.label}"
        cfg = sim_utils.CuboidCfg(
            size=(box.hx * 2.0, box.hy * 2.0, box.hz * 2.0),
            rigid_props=sim_utils.RigidBodyPropertiesCfg(kinematic_enabled=True),
            mass_props=sim_utils.MassPropertiesCfg(mass=1000.0),
            collision_props=sim_utils.CollisionPropertiesCfg(),
            visual_material=sim_utils.PreviewSurfaceCfg(
                diffuse_color=box.color,
                roughness=0.85,
                metallic=0.0,
            ),
        )
        cfg.func(prim_path, cfg, translation=(box.cx, box.cy, box.cz))
        created.append(prim_path)

    # Ceiling panels (thin, pale grey) — visual only, no collision needed
    created += _spawn_ceiling(base_prim)

    return created


def _spawn_ceiling(base_prim: str) -> list[str]:
    """Thin translucent ceiling panels (visual only, no rigid body)."""
    try:
        from pxr import UsdGeom, UsdPhysics, Gf
        import omni.usd
        stage = omni.usd.get_context().get_stage()
        created: list[str] = []
        color = Gf.Vec3f(0.98, 0.98, 0.98)
        for i, (x_lo, x_hi, y_lo, y_hi) in enumerate([
            (X_MIN, X_MAX, Y_WAIT_LO, Y_CORR_LO),
            (X_MIN, X_MAX, Y_CORR_LO, Y_ICU_LO),
            (X_MIN, X_MAX, Y_ICU_LO, Y_MAX),
        ]):
            cx = (x_lo + x_hi) / 2.0
            cy = (y_lo + y_hi) / 2.0
            prim_path = f"{base_prim}/ceiling_{i}"
            mesh = UsdGeom.Mesh.Define(stage, prim_path)
            hx = (x_hi - x_lo) / 2.0
            hy = (y_hi - y_lo) / 2.0
            z  = CEILING_Z
            mesh.CreatePointsAttr([
                Gf.Vec3f(cx - hx, cy - hy, z),
                Gf.Vec3f(cx + hx, cy - hy, z),
                Gf.Vec3f(cx + hx, cy + hy, z),
                Gf.Vec3f(cx - hx, cy + hy, z),
            ])
            mesh.CreateFaceVertexCountsAttr([4])
            mesh.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
            mesh.CreateNormalsAttr([Gf.Vec3f(0, 0, -1)] * 4)
            mesh.GetDisplayColorAttr().Set([color])
            created.append(prim_path)
        return created
    except Exception:
        return []


def spawn_semantic_agents(
    agents: list[dict],
    base_prim: str = "/World/Agents",
) -> list[str]:
    """
    Spawn colour-coded agent capsules for semantic roles.

    Parameters
    ----------
    agents : list of dicts with keys:
        position_xy : (x, y) tuple
        semantic_role : str
        agent_id : str
    base_prim : USD prim path prefix.

    Returns
    -------
    list of created prim paths
    """
    import isaaclab.sim as sim_utils
    created: list[str] = []
    for agent in agents:
        role = agent.get("semantic_role", "unknown")
        color = _ROLE_COLORS.get(role, _ROLE_COLORS["unknown"])
        ax, ay = agent["position_xy"]
        aid = agent.get("agent_id", f"agent_{len(created)}")
        prim_path = f"{base_prim}/{aid}"
        # Capsule: radius=0.20, height=1.70 (approximate human silhouette)
        cfg = sim_utils.CapsuleCfg(
            radius=0.20,
            height=1.30,
            axis="Z",
            rigid_props=sim_utils.RigidBodyPropertiesCfg(kinematic_enabled=True),
            mass_props=sim_utils.MassPropertiesCfg(mass=70.0),
            collision_props=sim_utils.CollisionPropertiesCfg(),
            visual_material=sim_utils.PreviewSurfaceCfg(
                diffuse_color=color,
                roughness=0.70,
                metallic=0.0,
            ),
        )
        cfg.func(prim_path, cfg, translation=(ax, ay, 0.85))
        created.append(prim_path)
    return created


def spawn_hospital_lights(base_prim: str = "/World") -> list[str]:
    """
    Spawn clinical overhead lighting: strip lights along corridor + room lights.

    Returns list of prim paths.
    """
    try:
        import isaaclab.sim as sim_utils
        created: list[str] = []

        # Dome light for ambient fill
        dome_cfg = sim_utils.DomeLightCfg(intensity=800.0, color=(0.96, 0.96, 1.00))
        dome_path = f"{base_prim}/DomeLight"
        dome_cfg.func(dome_path, dome_cfg)
        created.append(dome_path)

        # Corridor strip lights (disk lights at ceiling height pointing down)
        from pxr import UsdLux, Gf
        import omni.usd
        stage = omni.usd.get_context().get_stage()
        for i, (lx, ly) in enumerate([
            (-7.0, 5.0), (0.0, 5.0), (7.0, 5.0),  # room lights
            (-5.0, 0.25), (0.0, 0.25), (5.0, 0.25),  # corridor
            (-4.0, -4.5), (4.0, -4.5),               # waiting room
        ]):
            lpath = f"{base_prim}/Light_{i}"
            light = UsdLux.DiskLight.Define(stage, lpath)
            light.CreateIntensityAttr(3000.0)
            light.CreateColorAttr(Gf.Vec3f(0.98, 0.98, 1.00))
            light.CreateRadiusAttr(0.30)
            from pxr import UsdGeom
            xf = UsdGeom.Xformable(light.GetPrim())
            xf.AddTranslateOp().Set(Gf.Vec3d(lx, ly, CEILING_Z - 0.05))
            xf.AddRotateXOp().Set(180.0)  # point down
            created.append(lpath)
        return created
    except Exception:
        return []
