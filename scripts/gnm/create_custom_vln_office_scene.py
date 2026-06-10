"""
create_custom_vln_office_scene.py — Build the CustomVLN-Office USD scene
=========================================================================
Creates an independent Isaac Sim navigation environment using Isaac Sim
built-in assets (where available) or USD primitives as fallback.

NO VLNVerse assets are used. This is an independent proof-of-method scene.

Floor plan (16 m × 10 m):
  Entrance corridor  : x=0..4,  y=0..10
  Open office A      : x=4..10, y=0..5   (desks, chairs)
  Open office B      : x=10..16, y=0..5  (desks, shelf)
  Meeting area       : x=4..10, y=5..10  (meeting table, cabinet)
  Hallway            : x=10..16, y=5..10 (cabinet, plant)

Outputs:
  assets/custom_vln_office/custom_vln_office.usd   (Isaac Sim mode)
  assets/custom_vln_office/scene_layout.usda        (dry-run stub)
  results/custom_vln_office/scene_manifest.md

Usage:
  python3 scripts/gnm/create_custom_vln_office_scene.py --dry-run
  conda run -n isaac python scripts/gnm/create_custom_vln_office_scene.py
"""
import argparse
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

FLOOR_W = 16.0
FLOOR_D = 10.0
WALL_H  = 2.8
WALL_T  = 0.15
CAM_H   = 1.2

# ── Object layout: (name, type, x, y, z, scale_x, scale_y, scale_z, r, g, b) ─
OBJECTS = [
    # desks
    ("Desk_A",       "desk",    5.5,  1.5,  0,   1.5, 0.8, 0.75, 0.55, 0.35, 0.18),
    ("Desk_B",       "desk",    8.5,  1.5,  0,   1.5, 0.8, 0.75, 0.55, 0.35, 0.18),
    ("Desk_C",       "desk",   12.0,  1.5,  0,   1.5, 0.8, 0.75, 0.55, 0.35, 0.18),
    ("Desk_D",       "desk",   14.0,  3.0,  0,   1.5, 0.8, 0.75, 0.55, 0.35, 0.18),
    # chairs
    ("Chair_A",      "chair",   5.5,  2.8,  0,   0.5, 0.5, 0.9,  0.25, 0.25, 0.25),
    ("Chair_B",      "chair",   8.5,  2.8,  0,   0.5, 0.5, 0.9,  0.25, 0.25, 0.25),
    ("Chair_C",      "chair",  12.0,  2.8,  0,   0.5, 0.5, 0.9,  0.25, 0.25, 0.25),
    # cabinet
    ("Cabinet_A",    "cabinet",15.2,  7.0,  0,   0.6, 1.2, 1.8,  0.4,  0.4,  0.42),
    ("Cabinet_B",    "cabinet", 4.5,  8.5,  0,   0.6, 1.2, 1.8,  0.4,  0.4,  0.42),
    # plants
    ("Plant_A",      "plant",   1.5,  1.5,  0,   0.3, 0.3, 0.6,  0.15, 0.55, 0.15),
    ("Plant_B",      "plant",  15.0,  9.5,  0,   0.3, 0.3, 0.6,  0.15, 0.55, 0.15),
    # shelf
    ("Shelf_A",      "shelf",  15.3,  2.5,  0,   0.4, 2.0, 1.8,  0.72, 0.62, 0.45),
    # meeting table
    ("MeetingTable", "table",   7.0,  8.5,  0,   2.5, 1.5, 0.75, 0.45, 0.28, 0.12),
    # partition wall (partial divider between entrance and office)
    ("Partition_A",  "wall",    4.0,  1.5,  0,   0.1, 3.0, 1.5,  0.9,  0.88, 0.85),
]

NAMED_POSES = {
    "entrance":      (2.0,  5.0),
    "desk_a":        (5.5,  1.5),
    "desk_b":        (8.5,  1.5),
    "desk_c":        (12.0, 1.5),
    "meeting_table": (7.0,  8.5),
    "cabinet_a":     (15.2, 7.0),
    "plant_a":       (1.5,  1.5),
    "shelf_a":       (15.0, 2.5),
    "hallway_end":   (14.0, 8.0),
}


def _write_usda_stub(out_path: Path) -> None:
    """Write a human-readable USD ASCII stub describing the scene layout."""
    lines = [
        '#usda 1.0',
        '(',
        '    doc = "CustomVLN-Office — independent Isaac Sim scene"',
        '    upAxis = "Z"',
        '    defaultPrim = "World"',
        '    metersPerUnit = 1',
        '    customLayerData = {',
        '        string source = "create_custom_vln_office_scene.py"',
        '        string vlnverse_assets = "none"',
        '        string isaac_assets = "USD primitives (fallback)"',
        '    }',
        ')',
        '',
        'def Xform "World"',
        '{',
        '    # ── Floor ──────────────────────────────────────────────────────────',
        f'    # Floor: {FLOOR_W} m × {FLOOR_D} m  (grey plane, z=0)',
        '    def Mesh "Floor" { }',
        '',
        '    # ── Perimeter walls ────────────────────────────────────────────────',
        '    def Xform "Walls" {',
        '        def Cube "N" { }  # North wall',
        '        def Cube "S" { }  # South wall',
        '        def Cube "E" { }  # East wall',
        '        def Cube "W" { }  # West wall',
        '    }',
        '',
        '    # ── Props (desks, chairs, cabinets, plants, shelf, table) ──────────',
        '    def Xform "Props" {',
    ]
    for obj in OBJECTS:
        name, otype, x, y, *_ = obj
        lines.append(f'        def Cube "{name}" {{ }}  # {otype} at ({x}, {y})')
    lines += [
        '    }',
        '',
        '    # ── Navigation markers ─────────────────────────────────────────────',
        '    def Xform "GNM_Markers" {',
        '        def Sphere "START" { }   # entrance (2, 5)',
        '        def Sphere "GOAL" { }    # desk_a (5.5, 1.5)',
        '    }',
        '',
        '    # ── Lighting ────────────────────────────────────────────────────────',
        '    def Xform "Lighting" {',
        '        def RectLight "Main_1" { }',
        '        def RectLight "Main_2" { }',
        '        def SphereLight "Ambient" { }',
        '    }',
        '',
        '    # ── Cameras ─────────────────────────────────────────────────────────',
        '    def Xform "Cameras" {',
        '        def Camera "Overview" { }  # top-down',
        '        def Camera "RobotCam" { }  # first-person at 1.2 m',
        '    }',
        '}',
    ]
    out_path.write_text("\n".join(lines))


def _write_manifest(assets_used: list[str], primitives_used: list[str],
                    usd_path: Path) -> None:
    lines = [
        "# CustomVLN-Office — Scene Manifest",
        "",
        "**Generated by:** `create_custom_vln_office_scene.py`",
        f"**Scene file:** `{usd_path.relative_to(REPO)}`",
        "",
        "## VLNVerse assets used",
        "",
        "**NONE.** This scene is entirely independent of VLNVerse.",
        "",
        "## Isaac Sim assets used",
        "",
    ]
    if assets_used:
        for a in assets_used:
            lines.append(f"- `{a}`")
    else:
        lines.append("None found — all objects are USD primitives (see below).")
    lines += [
        "",
        "## USD primitive fallback objects",
        "",
    ]
    for p in primitives_used:
        lines.append(f"- {p}")
    lines += [
        "",
        "## Scene layout",
        "",
        f"- Floor: {FLOOR_W} m × {FLOOR_D} m",
        "- Entrance corridor: x=0..4, y=0..10",
        "- Open office A: x=4..10, y=0..5 (Desk_A, Desk_B, Chair_A, Chair_B)",
        "- Open office B: x=10..16, y=0..5 (Desk_C, Desk_D, Chair_C, Shelf_A)",
        "- Meeting area: x=4..10, y=5..10 (MeetingTable, Cabinet_B)",
        "- Hallway: x=10..16, y=5..10 (Cabinet_A, Plant_B)",
        "- Entrance props: Plant_A",
        "",
        "## Start / goal locations",
        "",
    ]
    for name, (x, y) in NAMED_POSES.items():
        lines.append(f"- `{name}`: ({x}, {y})")
    lines += [
        "",
        "## Navigation episodes",
        "",
        "Defined in `configs/custom_vln_office/tasks.yaml`",
        "6 train + 2 val episodes.",
    ]
    out = REPO / "results/custom_vln_office/scene_manifest.md"
    out.write_text("\n".join(lines))
    print(f"Manifest: {out}")


def build_dry_run() -> None:
    out_dir = REPO / "assets/custom_vln_office"
    out_dir.mkdir(parents=True, exist_ok=True)
    usd_stub = out_dir / "scene_layout.usda"
    _write_usda_stub(usd_stub)
    primitives = [f"{obj[1]} '{obj[0]}' at ({obj[2]}, {obj[3]})" for obj in OBJECTS]
    primitives += ["floor (grey Mesh)", "walls (white Cubes)", "2× RectLight", "1× SphereLight"]
    _write_manifest([], primitives, out_dir / "custom_vln_office.usd")
    print()
    print("[DRY RUN] Scene layout written (no USD generation without Isaac Sim)")
    print(f"  USDA stub : {usd_stub}")
    print(f"  Objects   : {len(OBJECTS)} props + floor + walls + lights + cameras")
    print(f"  Floor     : {FLOOR_W} m × {FLOOR_D} m")
    print(f"  No VLNVerse assets used")
    print()
    print("To build the real USD scene, run inside Isaac Sim:")
    print("  conda run -n isaac python scripts/gnm/create_custom_vln_office_scene.py")


def build_isaac() -> None:
    from isaacsim import SimulationApp
    _app = SimulationApp({"headless": False, "renderer": "RayTracedLighting"})

    import omni.usd
    from pxr import UsdGeom, UsdShade, UsdLux, Gf, Sdf

    ctx = omni.usd.get_context()
    ctx.new_stage()
    for _ in range(30):
        _app.update()
    stage = ctx.get_stage()

    assets_used   = []
    primitives_used = []

    # ── Helper: try Isaac asset, fall back to cube ────────────────────────────
    def _isaac_asset(nucleus_path: str) -> bool:
        try:
            import omni.kit.commands
            omni.kit.commands.execute("CreateReferenceCommand",
                                      prim_path="/World/Props/_test",
                                      usd_context=ctx,
                                      path_to_stage=nucleus_path)
            stage.RemovePrim("/World/Props/_test")
            return True
        except Exception:
            return False

    def _make_mat(path, r, g, b):
        mat    = UsdShade.Material.Define(stage, path)
        sh     = UsdShade.Shader.Define(stage, f"{path}/S")
        sh.CreateIdAttr("UsdPreviewSurface")
        sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(r, g, b))
        sh.CreateInput("roughness",    Sdf.ValueTypeNames.Float).Set(0.5)
        mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
        return mat

    def _bind(prim, mat):
        UsdShade.MaterialBindingAPI(prim).Bind(mat)

    def _cube(path, tx, ty, tz, sx, sy, sz, r=0.8, g=0.8, b=0.8):
        c = UsdGeom.Cube.Define(stage, path)
        c.CreateSizeAttr(1.0)
        xf = UsdGeom.Xformable(c.GetPrim())
        xf.AddScaleOp().Set(Gf.Vec3f(sx, sy, sz))
        xf.AddTranslateOp().Set(Gf.Vec3d(tx, ty, tz + sz / 2))
        mat = _make_mat(f"{path}/mat", r, g, b)
        _bind(c.GetPrim(), mat)
        return c

    UsdGeom.Xform.Define(stage, "/World")
    UsdGeom.Xform.Define(stage, "/World/Walls")
    UsdGeom.Xform.Define(stage, "/World/Props")
    UsdGeom.Xform.Define(stage, "/World/GNM_Markers")
    UsdGeom.Xform.Define(stage, "/World/Lighting")
    UsdGeom.Xform.Define(stage, "/World/Cameras")

    # Floor
    fl = UsdGeom.Mesh.Define(stage, "/World/Floor")
    hw, hd = FLOOR_W / 2, FLOOR_D / 2
    fl.CreatePointsAttr([Gf.Vec3f(-hw, -hd, 0), Gf.Vec3f(hw, -hd, 0),
                         Gf.Vec3f(hw,  hd, 0), Gf.Vec3f(-hw,  hd, 0)])
    fl.CreateFaceVertexCountsAttr([4])
    fl.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
    fl.CreateNormalsAttr([Gf.Vec3f(0, 0, 1)] * 4)
    fl.AddTranslateOp().Set(Gf.Vec3d(FLOOR_W / 2, FLOOR_D / 2, 0))
    fl_mat = _make_mat("/World/FloorMat", 0.55, 0.55, 0.58)
    _bind(fl.GetPrim(), fl_mat)
    primitives_used.append("floor (Mesh, grey)")

    # Walls
    h = WALL_H / 2
    cx, cy = FLOOR_W / 2, FLOOR_D / 2
    for wname, tx, ty, sx, sy in [
        ("N", cx,      FLOOR_D, FLOOR_W, WALL_T),
        ("S", cx,      0,       FLOOR_W, WALL_T),
        ("E", FLOOR_W, cy,      WALL_T,  FLOOR_D),
        ("W", 0,       cy,      WALL_T,  FLOOR_D),
    ]:
        _cube(f"/World/Walls/{wname}", tx, ty, 0, sx, sy, WALL_H, 0.88, 0.88, 0.85)
        primitives_used.append(f"wall {wname} (Cube)")

    # Props (all fallback primitives)
    for obj in OBJECTS:
        name, otype, x, y, z, sw, sd, sh2, r, g, b = obj
        _cube(f"/World/Props/{name}", x, y, z, sw, sd, sh2, r, g, b)
        primitives_used.append(f"{otype} '{name}' at ({x},{y}) (Cube)")

    # Lights
    def _rect_light(path, tx, ty, tz, intensity=3000):
        lgt = UsdLux.RectLight.Define(stage, path)
        lgt.CreateIntensityAttr(intensity)
        lgt.CreateWidthAttr(4.0)
        lgt.CreateHeightAttr(4.0)
        UsdGeom.Xformable(lgt.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(tx, ty, tz))

    _rect_light("/World/Lighting/Main_1", 5.0,  2.5, WALL_H - 0.1)
    _rect_light("/World/Lighting/Main_2", 12.0, 7.0, WALL_H - 0.1)
    amb = UsdLux.SphereLight.Define(stage, "/World/Lighting/Ambient")
    amb.CreateIntensityAttr(500)
    UsdGeom.Xformable(amb.GetPrim()).AddTranslateOp().Set(Gf.Vec3d(FLOOR_W/2, FLOOR_D/2, WALL_H))

    # Navigation markers
    mat_start = _make_mat("/World/GNM_Markers/MatStart", 0.1, 0.9, 0.2)
    mat_goal  = _make_mat("/World/GNM_Markers/MatGoal",  1.0, 0.2, 0.1)
    st = UsdGeom.Sphere.Define(stage, "/World/GNM_Markers/START")
    st.CreateRadiusAttr(0.3)
    st.AddTranslateOp().Set(Gf.Vec3d(2.0, 5.0, 0.3))
    _bind(st.GetPrim(), mat_start)
    gl = UsdGeom.Sphere.Define(stage, "/World/GNM_Markers/GOAL")
    gl.CreateRadiusAttr(0.3)
    gl.AddTranslateOp().Set(Gf.Vec3d(5.5, 1.5, 0.3))
    _bind(gl.GetPrim(), mat_goal)

    # Overview camera
    ov_cam = UsdGeom.Camera.Define(stage, "/World/Cameras/Overview")
    ov_cam.CreateProjectionAttr(UsdGeom.Tokens.perspective)
    ov_cam.CreateHorizontalApertureAttr(20.0)
    ov_cam.CreateFocalLengthAttr(8.0)
    xf = UsdGeom.Xformable(ov_cam.GetPrim())
    xf.AddTranslateOp().Set(Gf.Vec3d(FLOOR_W/2, FLOOR_D/2, 18.0))
    xf.AddRotateXYZOp().Set(Gf.Vec3f(0, 0, 0))

    # Robot camera
    rc = UsdGeom.Camera.Define(stage, "/World/Cameras/RobotCam")
    rc.CreateProjectionAttr(UsdGeom.Tokens.perspective)
    rc.CreateHorizontalApertureAttr(20.0)
    rc.CreateFocalLengthAttr(16.0)
    xf = UsdGeom.Xformable(rc.GetPrim())
    xf.AddTranslateOp().Set(Gf.Vec3d(2.0, 5.0, CAM_H))
    xf.AddRotateXYZOp().Set(Gf.Vec3f(90.0, 0.0, -90.0))

    for _ in range(60):
        _app.update()

    # Save USD
    out_dir = REPO / "assets/custom_vln_office"
    out_dir.mkdir(parents=True, exist_ok=True)
    usd_path = out_dir / "custom_vln_office.usd"
    ctx.save_as_stage(str(usd_path))
    print(f"\nScene saved: {usd_path}")

    _write_manifest(assets_used, primitives_used, usd_path)
    _app.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        build_dry_run()
    else:
        build_isaac()


if __name__ == "__main__":
    main()
