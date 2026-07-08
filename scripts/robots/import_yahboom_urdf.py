"""Headless URDF -> USD import for the Yahboom ROSMASTER M3 Pro.

Converts assets/robots/yahboom_m3_pro/yahboom_m3pro.urdf (spec-derived,
primitive geometry, 4 continuous mecanum wheel joints) into an articulated
USD at the canonical path the project accepts:

    assets/robots/yahboom_m3_pro/yahboom_m3pro.usd

Any existing file at that path is backed up first. Import settings follow
docs/YAHBOOM_URDF_TO_USD_IMPORT.md: merge fixed joints OFF, fix base OFF,
inertia tensors ON.

Run:
    ~/miniforge3/envs/isaac/bin/python -u scripts/robots/import_yahboom_urdf.py
"""

from isaacsim import SimulationApp

app = SimulationApp({"headless": True})

import shutil
from datetime import datetime
from pathlib import Path

from isaacsim.core.utils.extensions import enable_extension

enable_extension("isaacsim.asset.importer.urdf")
app.update()

import omni.kit.commands

REPO = Path(__file__).resolve().parents[2]
URDF = REPO / "assets/robots/yahboom_m3_pro/yahboom_m3pro.urdf"
DEST = REPO / "assets/robots/yahboom_m3_pro/yahboom_m3pro.usd"

if DEST.exists():
    backup = DEST.with_name(
        DEST.stem + f".bak-{datetime.now():%Y%m%d-%H%M}" + DEST.suffix)
    shutil.move(DEST, backup)
    print(f"[backup] previous file moved to {backup.name}")

status, import_config = omni.kit.commands.execute("URDFCreateImportConfig")
import_config.merge_fixed_joints = False
import_config.fix_base = False
import_config.import_inertia_tensor = True
import_config.distance_scale = 1.0
import_config.self_collision = False

status, stage_path = omni.kit.commands.execute(
    "URDFParseAndImportFile",
    urdf_path=str(URDF),
    import_config=import_config,
    dest_path=str(DEST),
)
for _ in range(60):
    app.update()

print(f"[import] status={status} prim={stage_path}")
print(f"[import] wrote {DEST} ({DEST.stat().st_size} bytes)"
      if DEST.exists() else "[import] FAILED: no output file")

# ---------------------------------------------------------------------------
# Post-process: the Isaac 5.1 modular URDF importer only materialises mesh
# visuals; primitive <box>/<cylinder>/<sphere> visuals end up as unresolved
# references. Author them directly from the URDF into the imported stage so
# the robot is visible (dimensions stay traceable to the spec-derived URDF).
# ---------------------------------------------------------------------------
import math
import xml.etree.ElementTree as ET

from pxr import Usd, UsdGeom, Gf

tree = ET.parse(URDF)
root = tree.getroot()

materials = {}
for mat in root.findall("material"):
    color = mat.find("color")
    if color is not None:
        rgba = [float(v) for v in color.get("rgba", "0.5 0.5 0.5 1").split()]
        materials[mat.get("name")] = rgba[:3]

stage = Usd.Stage.Open(str(DEST))
if not stage.GetDefaultPrim():
    root_prim = stage.GetPrimAtPath("/yahboom_m3pro")
    if root_prim:
        stage.SetDefaultPrim(root_prim)
        print("[fix] set defaultPrim=/yahboom_m3pro (importer left it unset, "
              "which makes plain references compose empty)")
robot_root = stage.GetDefaultPrim().GetPath() if stage.GetDefaultPrim() \
    else "/yahboom_m3pro"

from pxr import UsdPhysics as _UsdPhysics

authored = 0
collisions = 0
for link in root.findall("link"):
    lname = link.get("name")
    link_path = f"{robot_root}/{lname}"
    if not stage.GetPrimAtPath(link_path):
        continue
    elements = ([("viz", v) for v in link.findall("visual")]
                + [("col", c) for c in link.findall("collision")])
    for vi, (kind, visual) in enumerate(elements):
        geo = visual.find("geometry")
        if geo is None:
            continue
        origin = visual.find("origin")
        xyz = [float(v) for v in (origin.get("xyz", "0 0 0") if origin is not None else "0 0 0").split()]
        rpy = [math.degrees(float(v)) for v in (origin.get("rpy", "0 0 0") if origin is not None else "0 0 0").split()]
        color = (0.55, 0.55, 0.58)
        mat = visual.find("material")
        if mat is not None:
            inline = mat.find("color")
            if inline is not None:
                color = tuple(float(v) for v in inline.get("rgba").split()[:3])
            elif mat.get("name") in materials:
                color = tuple(materials[mat.get("name")])

        path = f"{link_path}/{kind}_{vi}"
        box = geo.find("box")
        cyl = geo.find("cylinder")
        sph = geo.find("sphere")
        if kind == "col" and cyl is not None and lname.endswith("_wheel"):
            # Sphere collider for wheels: native PhysX shape (cylinder
            # gprims cook to degenerate convexes at this size and the
            # robot sinks to axle depth and beaches).
            prim = UsdGeom.Sphere.Define(stage, path)
            prim.CreateRadiusAttr(float(cyl.get("radius")))
            api = UsdGeom.XformCommonAPI(prim)
        elif box is not None:
            size = [float(v) for v in box.get("size").split()]
            prim = UsdGeom.Cube.Define(stage, path)
            prim.CreateSizeAttr(1.0)
            api = UsdGeom.XformCommonAPI(prim)
            api.SetScale(Gf.Vec3f(*size))
        elif cyl is not None:
            prim = UsdGeom.Cylinder.Define(stage, path)
            prim.CreateRadiusAttr(float(cyl.get("radius")))
            prim.CreateHeightAttr(float(cyl.get("length")))
            prim.CreateAxisAttr("Z")
            api = UsdGeom.XformCommonAPI(prim)
        elif sph is not None:
            prim = UsdGeom.Sphere.Define(stage, path)
            prim.CreateRadiusAttr(float(sph.get("radius")))
            api = UsdGeom.XformCommonAPI(prim)
        else:
            continue
        api.SetTranslate(Gf.Vec3d(*xyz))
        api.SetRotate(Gf.Vec3f(*rpy))
        if kind == "col":
            # Invisible physics collider (importer drops primitive
            # collisions the same way it drops primitive visuals).
            _UsdPhysics.CollisionAPI.Apply(prim.GetPrim())
            from pxr import PhysxSchema
            pc = PhysxSchema.PhysxCollisionAPI.Apply(prim.GetPrim())
            pc.CreateContactOffsetAttr(0.005)
            pc.CreateRestOffsetAttr(0.0)
            prim.CreateVisibilityAttr(UsdGeom.Tokens.invisible)
            collisions += 1
        else:
            prim.CreateDisplayColorAttr().Set([Gf.Vec3f(*color)])
            authored += 1

# Wheel joints need an angular drive for velocity control (stiffness 0,
# damping > 0); the importer leaves continuous joints passive, so
# ArticulationController velocity commands would apply zero torque.
from pxr import UsdPhysics

drives = 0
for prim in stage.Traverse():
    if prim.GetTypeName() == "PhysicsRevoluteJoint" \
            and "wheel_joint" in prim.GetName():
        drive = UsdPhysics.DriveAPI.Apply(prim, "angular")
        drive.CreateTypeAttr("force")
        drive.CreateStiffnessAttr(0.0)
        drive.CreateDampingAttr(15.0)
        drive.CreateMaxForceAttr(20.0)
        drives += 1

# Low-friction wheel material: the real M3Pro has mecanum rollers that
# shed lateral load; with plain sphere colliders the wheelbase/track
# ratio makes lateral grip cancel the skid-steer yaw moment (measured
# yaw_tracking_ratio 0.03-0.23 at default friction). Reducing wheel
# friction approximates the rollers' lateral compliance.
from pxr import UsdShade
wheel_mat = UsdShade.Material.Define(stage, f"{robot_root}/Materials/WheelMat")
mat_api = _UsdPhysics.MaterialAPI.Apply(wheel_mat.GetPrim())
mat_api.CreateStaticFrictionAttr(0.35)
mat_api.CreateDynamicFrictionAttr(0.35)
mat_api.CreateRestitutionAttr(0.0)
bound = 0
for prim in stage.Traverse():
    if prim.GetName().startswith("col_") and "_wheel/" in str(prim.GetPath()):
        UsdShade.MaterialBindingAPI.Apply(prim).Bind(
            wheel_mat, materialPurpose="physics")
        bound += 1
print(f"[material] low-friction wheel material bound to {bound} colliders")

from pxr import PhysxSchema
root_link = stage.GetPrimAtPath(f"{robot_root}/base_footprint")
if root_link:
    pa = PhysxSchema.PhysxArticulationAPI.Apply(root_link)
    pa.CreateSolverPositionIterationCountAttr(32)
    pa.CreateSolverVelocityIterationCountAttr(4)
    print("[physx] solver iterations raised on articulation root")

stage.Save()
print(f"[visuals] authored {authored} primitive visuals from URDF")
print(f"[collisions] authored {collisions} primitive colliders from URDF")
print(f"[drives] applied angular velocity drives to {drives} wheel joints")
app.close()
