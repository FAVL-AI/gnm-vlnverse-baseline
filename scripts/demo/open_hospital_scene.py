#!/usr/bin/env python3
"""
open_hospital_scene.py — FleetSafe photorealistic hospital scene viewer.

Opens Isaac Sim GUI with:
  • Full 20 m × 16 m hospital floor plan (5 clinical zones)
  • Zone-coloured floor panels: ICU / Nurse Station / Pharmacy /
    Emergency Corridor / Waiting Room
  • Upright zone signs at every doorway with clinical colours
  • Floor boundary tape lines between zones
  • Yahboom M3Pro robot (URDF auto-converted on first run)
  • RTX Path Tracing (--raytraced for faster ray-traced lighting)
  • PBR materials: zone-appropriate roughness and sheen
  • Clinical fluorescent ceiling + room overhead lights

Usage:
  conda activate isaac
  cd ~/robotics/FleetSafe-VisualNav-Benchmark
  python scripts/demo/open_hospital_scene.py
  python scripts/demo/open_hospital_scene.py --raytraced   # faster
  python scripts/demo/open_hospital_scene.py --stream      # + WebRTC

AppLauncher must be initialised BEFORE any isaaclab/omni import.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# ── Args (before AppLauncher) ─────────────────────────────────────────────────
_p = argparse.ArgumentParser(add_help=False)
_p.add_argument("--stream",    action="store_true")
_p.add_argument("--raytraced", action="store_true",
                help="Ray-traced lighting (faster than full path tracing)")
_p.add_argument("--spawn-x",  type=float, default=-2.0)
_p.add_argument("--spawn-y",  type=float, default=0.25)
_p.add_argument("--nucleus",   action="store_true",
                help="Attempt to load NVIDIA hospital USD from Nucleus before procedural fallback")
_args, _extra = _p.parse_known_args()

# ── AppLauncher — MUST precede every isaaclab/omni import ─────────────────────
try:
    from isaaclab.app import AppLauncher
except ImportError:
    print("[ERROR] isaaclab not found.  Run:  conda activate isaac")
    sys.exit(1)

_orig_argv = sys.argv[:]
sys.argv   = [sys.argv[0]] + _extra
print("[FleetSafe] Starting Isaac Sim GUI (~60 s on first boot)…")
_launcher  = AppLauncher({"headless": False, "livestream": 1 if _args.stream else 0})
_app       = _launcher.app
sys.argv   = _orig_argv

# ── Post-AppLauncher imports ──────────────────────────────────────────────────
import carb
import carb.settings
from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdShade

# ── Repo paths ────────────────────────────────────────────────────────────────
M3PRO_URDF    = _REPO / "fleet_safe_vla/robots/yahboom/m3pro/urdf/yahboom_m3pro.urdf"
M3PRO_USD_DIR = _REPO / "fleet_safe_vla/robots/yahboom/m3pro/usd"
M3PRO_USD_DIR.mkdir(parents=True, exist_ok=True)

_RENDER_MODE = "RaytracedLighting" if _args.raytraced else "PathTracing"

# Zone colour palette (matches hospital_scene_builder.py)
_ZONE_COLORS = {
    "icu":                (0.20, 0.40, 0.80),
    "nurse_station":      (0.55, 0.55, 0.60),
    "pharmacy":           (0.20, 0.65, 0.65),
    "emergency_corridor": (0.95, 0.92, 0.82),
    "waiting_room":       (0.40, 0.65, 0.45),
}

_ZONE_LABELS = {
    "icu":                "ICU",
    "nurse_station":      "NURSE STATION",
    "pharmacy":           "PHARMACY",
    "emergency_corridor": "EMERGENCY CORRIDOR",
    "waiting_room":       "WAITING ROOM",
}

# ─────────────────────────────────────────────────────────────────────────────
# RTX configuration
# ─────────────────────────────────────────────────────────────────────────────

def _configure_rtx() -> None:
    s = carb.settings.get_settings()
    s.set("/rtx/rendermode", _RENDER_MODE)
    if _RENDER_MODE == "PathTracing":
        s.set("/rtx/pathtracing/spp",          64)
        s.set("/rtx/pathtracing/totalSpp",      512)
        s.set("/rtx/pathtracing/optixDenoiser/enabled", True)
    s.set("/rtx/shadows/enabled",          True)
    s.set("/rtx/ambientOcclusion/enabled", _RENDER_MODE != "PathTracing")
    print(f"[render] {_RENDER_MODE}")


# ─────────────────────────────────────────────────────────────────────────────
# PBR material helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_material(
    stage: Usd.Stage, path: str,
    diffuse: tuple, roughness: float, metallic: float = 0.0,
) -> UsdShade.Material:
    mat = UsdShade.Material.Define(stage, path)
    sh  = UsdShade.Shader.Define(stage, f"{path}/S")
    sh.CreateIdAttr("UsdPreviewSurface")
    sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*diffuse))
    sh.CreateInput("roughness",    Sdf.ValueTypeNames.Float).Set(roughness)
    sh.CreateInput("metallic",     Sdf.ValueTypeNames.Float).Set(metallic)
    mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
    return mat


def _bind(stage: Usd.Stage, prim_path: str, mat: UsdShade.Material) -> None:
    prim = stage.GetPrimAtPath(prim_path)
    if prim and prim.IsValid():
        UsdShade.MaterialBindingAPI(prim).Bind(mat)


def _setup_zone_materials(stage: Usd.Stage) -> dict[str, UsdShade.Material]:
    """Create PBR materials for each hospital zone (applied after scene_builder spawns)."""
    base = "/World/Materials"
    mats: dict[str, UsdShade.Material] = {}

    # Corridor — shiny vinyl tile, slightly warm cream
    mats["emergency_corridor"] = _make_material(
        stage, f"{base}/VinylCorr",
        diffuse=(0.95, 0.92, 0.82), roughness=0.08,
    )
    # ICU — matte clinical blue epoxy
    mats["icu"] = _make_material(
        stage, f"{base}/IcuFloor",
        diffuse=(0.18, 0.35, 0.72), roughness=0.35,
    )
    # Nurse station — polished grey linoleum
    mats["nurse_station"] = _make_material(
        stage, f"{base}/NurseFloor",
        diffuse=(0.52, 0.52, 0.56), roughness=0.20,
    )
    # Pharmacy — semi-gloss teal
    mats["pharmacy"] = _make_material(
        stage, f"{base}/PharmacyFloor",
        diffuse=(0.18, 0.60, 0.62), roughness=0.18,
    )
    # Waiting room — matte soft green carpet
    mats["waiting_room"] = _make_material(
        stage, f"{base}/WaitingFloor",
        diffuse=(0.38, 0.60, 0.42), roughness=0.75,
    )
    # Walls — matte hospital white
    mats["wall"] = _make_material(
        stage, f"{base}/HospWall",
        diffuse=(0.96, 0.96, 0.94), roughness=0.60,
    )
    # Ceiling tiles — flat white
    mats["ceiling"] = _make_material(
        stage, f"{base}/HospCeiling",
        diffuse=(0.98, 0.98, 0.98), roughness=0.85,
    )
    # Robot chassis — dark metallic carbon
    mats["robot"] = _make_material(
        stage, f"{base}/RobotChassis",
        diffuse=(0.08, 0.08, 0.10), roughness=0.22, metallic=0.88,
    )
    # Robot wheels — matte black rubber
    mats["wheel"] = _make_material(
        stage, f"{base}/RobotWheel",
        diffuse=(0.05, 0.05, 0.05), roughness=0.80,
    )
    return mats


def _apply_zone_materials(stage: Usd.Stage, mats: dict) -> None:
    """Walk all hospital geometry prims and bind zone-appropriate PBR materials."""
    for prim in stage.Traverse():
        if not (prim.IsA(UsdGeom.Gprim) or prim.IsA(UsdGeom.Mesh)):
            continue
        name = prim.GetName().lower()
        path = str(prim.GetPath())
        if "hospital" not in path.lower() and "world" not in path.lower():
            continue

        if "floor_corridor" in name or "floor_corridor" in path:
            UsdShade.MaterialBindingAPI(prim).Bind(mats["emergency_corridor"])
        elif "floor_icu" in name or "floor_icu" in path:
            UsdShade.MaterialBindingAPI(prim).Bind(mats["icu"])
        elif "floor_nurse" in name or "floor_nurse" in path:
            UsdShade.MaterialBindingAPI(prim).Bind(mats["nurse_station"])
        elif "floor_pharmacy" in name or "floor_pharmacy" in path:
            UsdShade.MaterialBindingAPI(prim).Bind(mats["pharmacy"])
        elif "floor_waiting" in name or "floor_waiting" in path:
            UsdShade.MaterialBindingAPI(prim).Bind(mats["waiting_room"])
        elif any(w in name for w in ("wall", "partition", "pillar")):
            UsdShade.MaterialBindingAPI(prim).Bind(mats["wall"])
        elif "ceiling" in name:
            UsdShade.MaterialBindingAPI(prim).Bind(mats["ceiling"])


# ─────────────────────────────────────────────────────────────────────────────
# Zone signs (upright coloured boards at every doorway + zone centres)
# ─────────────────────────────────────────────────────────────────────────────

# (x, y, z_centre, rot_z_deg, zone_key)
_SIGN_DEFS = [
    # Doorway signs at corridor/upper-room partition (y ≈ 2 m), face south
    (-7.0,  2.15, 2.10, 0.0,  "icu"),
    ( 0.0,  2.15, 2.10, 0.0,  "nurse_station"),
    ( 7.0,  2.15, 2.10, 0.0,  "pharmacy"),
    # Corridor / Waiting Room boundary (y ≈ -1.5 m), face south
    (-5.0, -1.65, 2.10, 0.0,  "emergency_corridor"),
    ( 5.0, -1.65, 2.10, 0.0,  "emergency_corridor"),
    # Waiting room far-wall sign (y ≈ -7.8 m), face north (rot 180°)
    ( 0.0, -7.85, 1.80, 180.0, "waiting_room"),
    # ICU far wall (y ≈ 7.8 m), face south (rot 0°)
    (-6.0,  7.85, 1.80, 180.0, "icu"),
    # Pharmacy far wall
    ( 7.0,  7.85, 1.80, 180.0, "pharmacy"),
]

# Floor tape boundary strips
_TAPE_DEFS = [
    # Zone y = 2.0 boundary (corridor ↔ upper rooms)
    dict(cx=0.0, cy=2.0, w=20.0, d=0.08, zone="emergency_corridor"),
    # Zone y = -1.5 boundary (corridor ↔ waiting room)
    dict(cx=0.0, cy=-1.5, w=20.0, d=0.08, zone="waiting_room"),
    # ICU ↔ Nurse Station (x = -2.0)
    dict(cx=-2.0, cy=5.0, w=0.08, d=6.0, zone="icu"),
    # Nurse Station ↔ Pharmacy (x = 2.0)
    dict(cx=2.0, cy=5.0, w=0.08, d=6.0, zone="pharmacy"),
]


def _spawn_zone_signs(stage: Usd.Stage, base: str = "/World/ZoneSigns") -> None:
    """Spawn upright coloured sign boards at zone entrances."""
    for i, (sx, sy, sz, rot, zone) in enumerate(_SIGN_DEFS):
        color = _ZONE_COLORS[zone]
        label = _ZONE_LABELS[zone]
        path  = f"{base}/Sign_{i:02d}"

        # Sign board (0.6 m wide, 0.28 m tall, 0.04 m thick)
        board = UsdGeom.Cube.Define(stage, f"{path}/Board")
        board.GetSizeAttr().Set(1.0)
        board.GetDisplayColorAttr().Set([Gf.Vec3f(*color)])
        xf = UsdGeom.Xformable(board.GetPrim())
        xf.ClearXformOpOrder()
        xf.AddTranslateOp().Set(Gf.Vec3d(sx, sy, sz))
        xf.AddRotateZOp().Set(rot)
        xf.AddScaleOp().Set(Gf.Vec3f(0.60, 0.04, 0.28))

        # White border frame
        border = UsdGeom.Cube.Define(stage, f"{path}/Border")
        border.GetSizeAttr().Set(1.0)
        border.GetDisplayColorAttr().Set([Gf.Vec3f(1.0, 1.0, 1.0)])
        xf2 = UsdGeom.Xformable(border.GetPrim())
        xf2.ClearXformOpOrder()
        xf2.AddTranslateOp().Set(Gf.Vec3d(sx, sy - 0.022, sz))
        xf2.AddRotateZOp().Set(rot)
        xf2.AddScaleOp().Set(Gf.Vec3f(0.64, 0.04, 0.32))

        # Apply zone PBR material to board
        mat_path = f"/World/Materials/Sign_{zone}"
        if not stage.GetPrimAtPath(mat_path).IsValid():
            _make_material(stage, mat_path, color, roughness=0.40)
        mat = UsdShade.Material(stage.GetPrimAtPath(mat_path))
        UsdShade.MaterialBindingAPI(board.GetPrim()).Bind(mat)

        # Tag with zone label metadata for Isaac Sim Stage inspector
        board.GetPrim().SetCustomDataByKey("zone_label", label)
        board.GetPrim().SetCustomDataByKey("zone_key",   zone)

    print(f"[signs] {len(_SIGN_DEFS)} zone signs placed")


def _spawn_floor_tape(stage: Usd.Stage, base: str = "/World/FloorTape") -> None:
    """Spawn thin coloured floor tape strips at zone boundaries."""
    for i, td in enumerate(_TAPE_DEFS):
        color = _ZONE_COLORS[td["zone"]]
        path  = f"{base}/Tape_{i:02d}"
        tape  = UsdGeom.Cube.Define(stage, path)
        tape.GetSizeAttr().Set(1.0)
        tape.GetDisplayColorAttr().Set([Gf.Vec3f(*color)])
        xf = UsdGeom.Xformable(tape.GetPrim())
        xf.ClearXformOpOrder()
        xf.AddTranslateOp().Set(Gf.Vec3d(td["cx"], td["cy"], 0.006))
        xf.AddScaleOp().Set(Gf.Vec3f(td["w"], td["d"], 0.004))
    print(f"[tape] {len(_TAPE_DEFS)} zone boundary strips placed")


# ─────────────────────────────────────────────────────────────────────────────
# Robot: URDF → USD + spawn
# ─────────────────────────────────────────────────────────────────────────────

def _get_m3pro_usd() -> str | None:
    candidate = M3PRO_USD_DIR / "yahboom_m3pro" / "yahboom_m3pro.usd"
    if candidate.exists():
        print(f"[M3Pro] USD cache: {candidate.relative_to(_REPO)}")
        return str(candidate)
    print("[M3Pro] Converting URDF → USD (~20 s)…")
    try:
        import omni.kit.commands
        import isaacsim.asset.importer.urdf._urdf as _urdf_b
        cfg = _urdf_b.ImportConfig()
        cfg.merge_fixed_joints    = True
        cfg.fix_base              = False
        cfg.self_collision        = False
        cfg.import_inertia_tensor = True
        cfg.distance_scale        = 1.0
        _, usd = omni.kit.commands.execute(
            "URDFParseAndImportFile",
            urdf_path=str(M3PRO_URDF),
            import_config=cfg,
            dest_path=str(M3PRO_USD_DIR),
        )
        if usd:
            print(f"[M3Pro] USD: {usd}")
            return usd
    except Exception as e:
        print(f"[M3Pro] URDF importer: {e}; trying IsaacLab converter…")
    try:
        from isaaclab.sim.converters import UrdfConverter, UrdfConverterCfg
        cfg2 = UrdfConverterCfg(
            asset_path=str(M3PRO_URDF), usd_dir=str(M3PRO_USD_DIR),
            fix_base=False, merge_fixed_joints=True, self_collision=False,
            force_usd_conversion=True,
        )
        c = UrdfConverter(cfg2)
        print(f"[M3Pro] USD via IsaacLab: {c.usd_path}")
        return c.usd_path
    except Exception as e2:
        print(f"[M3Pro] Both converters failed: {e2}")
        return None


def _try_load_nucleus_hospital(stage: Usd.Stage, prim_path: str = "/World/Hospital") -> bool:
    """
    Attempt to load the NVIDIA hospital USD from Nucleus.

    Resolution order (matches hospital_asset_library.py 3-tier policy):
      1. omniverse://localhost/NVIDIA/Assets/Isaac/5.1/Isaac/Environments/Hospital/hospital.usd
      2. omniverse://localhost/NVIDIA/Assets/Isaac/5.0/...  (Isaac 5.0)
      3. omniverse://localhost/NVIDIA/Assets/Isaac/4.5.0/... (Isaac 4.x)

    Returns True if a USD reference was successfully added to the stage.
    Callers must fall back to spawn_hospital_scene() if this returns False.
    """
    _CANDIDATE_URLS = [
        "omniverse://localhost/NVIDIA/Assets/Isaac/5.1/Isaac/Environments/Hospital/hospital.usd",
        "omniverse://localhost/NVIDIA/Assets/Isaac/5.0/Isaac/Environments/Hospital/hospital.usd",
        "omniverse://localhost/NVIDIA/Assets/Isaac/4.5.0/Isaac/Environments/Hospital/hospital.usd",
    ]

    try:
        from isaacsim.core.utils.stage import add_reference_to_stage
        import omni.usd
    except ImportError as exc:
        print(f"[hospital/nucleus] isaacsim not importable: {exc}")
        return False

    for url in _CANDIDATE_URLS:
        try:
            add_reference_to_stage(url, prim_path)
            prim = stage.GetPrimAtPath(prim_path)
            if prim and prim.IsValid():
                # Position root at world origin
                xf = UsdGeom.Xformable(prim)
                xf.ClearXformOpOrder()
                xf.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, 0.0))
                print(f"[hospital/nucleus] Loaded: {url}")
                return True
        except Exception as exc:
            print(f"[hospital/nucleus] {url} failed: {exc}")

    print("[hospital/nucleus] No Nucleus hospital USD reachable — falling back to procedural scene")
    return False


def _spawn_robot(stage: Usd.Stage, spawn_xy: tuple, mats: dict) -> str:
    """Spawn M3Pro from USD or fall back to geometry box."""
    from isaacsim.core.utils.stage import add_reference_to_stage
    root = "/World/Robot/Yahboom_M3Pro"
    usd  = _get_m3pro_usd()
    if usd:
        add_reference_to_stage(usd, root)
        prim = stage.GetPrimAtPath(root)
        if prim and prim.IsValid():
            xf = UsdGeom.Xformable(prim)
            xf.ClearXformOpOrder()
            xf.AddTranslateOp().Set(Gf.Vec3d(spawn_xy[0], spawn_xy[1], 0.055))
            xf.AddOrientOp().Set(Gf.Quatd(1, 0, 0, 0))
        print(f"[M3Pro] Spawned (URDF) at {spawn_xy}")
    else:
        # Geometry fallback
        root = "/World/Robot/M3Pro_Geo"
        ch = UsdGeom.Cube.Define(stage, f"{root}/Chassis")
        ch.GetSizeAttr().Set(1.0)
        ch.GetDisplayColorAttr().Set([Gf.Vec3f(0.08, 0.08, 0.10)])
        xf = UsdGeom.Xformable(ch.GetPrim())
        xf.ClearXformOpOrder()
        xf.AddTranslateOp().Set(Gf.Vec3d(spawn_xy[0], spawn_xy[1], 0.095))
        xf.AddScaleOp().Set(Gf.Vec3f(0.29, 0.235, 0.08))
        for (ox, oy, label) in [(0.0775, 0.0925, "FL"), (0.0775, -0.0925, "FR"),
                                  (-0.0775, 0.0925, "RL"), (-0.0775, -0.0925, "RR")]:
            wh = UsdGeom.Cylinder.Define(stage, f"{root}/Wheel_{label}")
            wh.GetRadiusAttr().Set(0.048); wh.GetHeightAttr().Set(0.025)
            wh.GetAxisAttr().Set("Y")
            wh.GetDisplayColorAttr().Set([Gf.Vec3f(0.05, 0.05, 0.05)])
            wxf = UsdGeom.Xformable(wh.GetPrim())
            wxf.ClearXformOpOrder()
            wxf.AddTranslateOp().Set(Gf.Vec3d(spawn_xy[0]+ox, spawn_xy[1]+oy, 0.048))
        print(f"[M3Pro] Spawned (geometry fallback) at {spawn_xy}")

    # Apply robot materials
    for prim in stage.Traverse():
        if not str(prim.GetPath()).startswith("/World/Robot"):
            continue
        if not (prim.IsA(UsdGeom.Gprim) or prim.IsA(UsdGeom.Mesh)):
            continue
        n = prim.GetName().lower()
        if "wheel" in n:
            UsdShade.MaterialBindingAPI(prim).Bind(mats["wheel"])
        else:
            UsdShade.MaterialBindingAPI(prim).Bind(mats["robot"])

    return root


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    from isaacsim.core.api import World
    from isaacsim.core.utils.stage import get_current_stage

    # Import scene builder AFTER AppLauncher
    from fleet_safe_vla.envs.isaaclab.hospital.hospital_scene_builder import (
        spawn_hospital_scene,
        spawn_hospital_lights,
    )

    print("[FleetSafe] Configuring RTX photorealistic rendering…")
    _configure_rtx()

    world = World(stage_units_in_meters=1.0, physics_dt=1/60, rendering_dt=1/30)
    stage = get_current_stage()

    # ── Hospital geometry: Nucleus USD (photoreal) or procedural fallback ────
    nucleus_loaded = False
    if _args.nucleus:
        print("[hospital] Attempting Nucleus photorealistic hospital USD…")
        nucleus_loaded = _try_load_nucleus_hospital(stage, "/World/Hospital")

    if not nucleus_loaded:
        print("[hospital] Building procedural hospital floor plan…")
        spawn_hospital_scene("/World/Hospital")

    # ── Clinical lighting ─────────────────────────────────────────────────────
    spawn_hospital_lights("/World")

    # ── PBR materials ─────────────────────────────────────────────────────────
    mats = _setup_zone_materials(stage)
    _apply_zone_materials(stage, mats)

    # ── Zone signs at every doorway ───────────────────────────────────────────
    _spawn_zone_signs(stage)

    # ── Floor boundary tape ───────────────────────────────────────────────────
    _spawn_floor_tape(stage)

    # ── Yahboom M3Pro robot (starts in Emergency Corridor) ────────────────────
    spawn_xy = (_args.spawn_x, _args.spawn_y)
    _spawn_robot(stage, spawn_xy, mats)

    # ── Sample agents (nurses, patients, wheelchair users) ────────────────────
    from fleet_safe_vla.envs.isaaclab.hospital.hospital_scene_builder import (
        spawn_semantic_agents,
    )
    spawn_semantic_agents([
        {"position_xy": (-7.0,  5.5), "semantic_role": "doctor",           "agent_id": "doctor_00"},
        {"position_xy": ( 0.0,  4.5), "semantic_role": "nurse",            "agent_id": "nurse_00"},
        {"position_xy": ( 7.0,  5.0), "semantic_role": "patient",          "agent_id": "patient_00"},
        {"position_xy": (-3.0,  0.25),"semantic_role": "nurse",            "agent_id": "nurse_01"},
        {"position_xy": ( 4.0,  0.25),"semantic_role": "wheelchair_user",  "agent_id": "wc_user_00"},
        {"position_xy": (-5.0,  0.25),"semantic_role": "gurney",           "agent_id": "gurney_00"},
        {"position_xy": ( 0.0, -4.5), "semantic_role": "visitor",          "agent_id": "visitor_00"},
        {"position_xy": (-3.0, -5.0), "semantic_role": "visitor",          "agent_id": "visitor_01"},
        {"position_xy": ( 3.0, -3.5), "semantic_role": "patient",          "agent_id": "patient_01"},
    ], base_prim="/World/Agents")
    print("[agents] 9 semantic agents spawned (nurses, patients, visitors)")

    world.reset()

    print("")
    print("=" * 62)
    print("  FleetSafe Hospital Scene — Isaac Sim GUI")
    print(f"  Render   : {_RENDER_MODE}")
    print(f"  Scene    : {'NVIDIA Nucleus USD (photorealistic)' if nucleus_loaded else 'Procedural (5 clinical zones)'}")
    print(f"  Layout   : 20 m × 16 m  |  5 clinical zones")
    print(f"  Robot    : Yahboom M3Pro at ({spawn_xy[0]:.1f}, {spawn_xy[1]:.1f})")
    print("  Zones    : ICU · Nurse Station · Pharmacy ·")
    print("             Emergency Corridor · Waiting Room")
    if _args.stream:
        print("  WebRTC   : http://localhost:49100")
    print("  Close window or Ctrl+C to exit")
    print("=" * 62)
    print("")

    frame = 0
    try:
        while _app.is_running():
            world.step(render=True)
            frame += 1
            if frame % 600 == 0:
                print(f"  [{frame/30:5.0f}s] {frame} frames rendered — scene running")
    except KeyboardInterrupt:
        pass

    print("[FleetSafe] Shutting down…")
    world.close()


if __name__ == "__main__":
    main()
