"""
replay_custom_gnm_scene.py — Replay the custom office GNM scene in Isaac Sim
=============================================================================
Opens the custom office scene (created by create_custom_gnm_scene.py)
and replays the planned trajectory with GNM overlay markers.

This scene is independent of VLNVerse assets — it demonstrates that the
GNM data pipeline works with any scene we build in Isaac Sim.

Usage:
  conda run -n isaac python scripts/gnm/replay_custom_gnm_scene.py
  SHOW_GNM_PANELS=1 conda run -n isaac python scripts/gnm/replay_custom_gnm_scene.py
"""
import json
import math
import os
import pickle
import sys
import time
from pathlib import Path

import numpy as np

REPO         = Path("/home/favl/robotics/FleetSafe-VisualNav-Benchmark")
SCENE_DIR    = REPO / "datasets/custom_gnm_scene/train/custom_office_0001"
SHOW_PANELS  = os.environ.get("SHOW_GNM_PANELS", "0") == "1"
SPEED        = float(os.environ.get("SPEED", "1.0"))

if not SCENE_DIR.exists():
    print("ERROR: custom scene not found. Run create_custom_gnm_scene.py first:")
    print("  conda run -n isaac python scripts/gnm/create_custom_gnm_scene.py")
    sys.exit(1)

data      = pickle.load(open(SCENE_DIR / "traj_data.pkl", "rb"))
positions = data["position"]
yaws      = data.get("yaw", np.zeros(len(positions)))
n_steps   = len(positions)
info_path = SCENE_DIR / "episode_info.json"
ep_info   = json.loads(info_path.read_text()) if info_path.exists() else {}

sx, sy    = float(positions[0][0]),  float(positions[0][1])
gx, gy    = float(positions[-1][0]), float(positions[-1][1])
path_len  = float(np.linalg.norm(np.diff(positions, axis=0), axis=1).sum())
goal_r    = float(ep_info.get("goal_radius", 3.0))

print(f"Custom scene  : {SCENE_DIR.parent.name}/{SCENE_DIR.name}")
print(f"Frames        : {n_steps}")
print(f"Path length   : {path_len:.3f} m")
print(f"Start         : ({sx:.3f}, {sy:.3f})")
print(f"Goal          : ({gx:.3f}, {gy:.3f})")

from isaacsim import SimulationApp
app = SimulationApp({"headless": False, "renderer": "RayTracedLighting"})

import omni.usd
from pxr import UsdGeom, UsdShade, Gf, Sdf, Usd

ctx = omni.usd.get_context()
ctx.new_stage()
for _ in range(30):
    app.update()

stage = ctx.get_stage()

# ── Rebuild scene geometry ────────────────────────────────────────────────────
FLOOR_SIZE  = 6.0
WALL_HEIGHT = 2.5
WALL_THICK  = 0.15

floor = UsdGeom.Cube.Define(stage, "/World/Floor")
floor.CreateSizeAttr(1.0)
UsdGeom.Xformable(floor.GetPrim()).AddScaleOp().Set(Gf.Vec3f(FLOOR_SIZE, FLOOR_SIZE, 0.05))
UsdGeom.Xformable(floor.GetPrim()).AddTranslateOp().Set(
    Gf.Vec3d(FLOOR_SIZE / 2, FLOOR_SIZE / 2, -0.025))

def _wall(name, tx, ty, tz, sx_, sy_, sz_):
    w = UsdGeom.Cube.Define(stage, f"/World/Walls/{name}")
    w.CreateSizeAttr(1.0)
    xf = UsdGeom.Xformable(w.GetPrim())
    xf.AddScaleOp().Set(Gf.Vec3f(sx_, sy_, sz_))
    xf.AddTranslateOp().Set(Gf.Vec3d(tx, ty, tz))

h = WALL_HEIGHT / 2
_wall("N", FLOOR_SIZE/2, FLOOR_SIZE, h, FLOOR_SIZE, WALL_THICK, WALL_HEIGHT)
_wall("S", FLOOR_SIZE/2, 0,          h, FLOOR_SIZE, WALL_THICK, WALL_HEIGHT)
_wall("E", FLOOR_SIZE,   FLOOR_SIZE/2, h, WALL_THICK, FLOOR_SIZE, WALL_HEIGHT)
_wall("W", 0,            FLOOR_SIZE/2, h, WALL_THICK, FLOOR_SIZE, WALL_HEIGHT)

tbl = UsdGeom.Cube.Define(stage, "/World/Table")
tbl.CreateSizeAttr(1.0)
xf = UsdGeom.Xformable(tbl.GetPrim())
xf.AddScaleOp().Set(Gf.Vec3f(1.0, 0.8, 0.75))
xf.AddTranslateOp().Set(Gf.Vec3d(2.0, 1.5, 0.375))

for _ in range(60):
    app.update()

# ── Materials ──────────────────────────────────────────────────────────────────
def make_mat(path, r, g, b):
    mat    = UsdShade.Material.Define(stage, path)
    shader = UsdShade.Shader.Define(stage, f"{path}/S")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(r, g, b))
    shader.CreateInput("roughness",    Sdf.ValueTypeNames.Float).Set(0.4)
    mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return mat

def bind(prim, mat):
    UsdShade.MaterialBindingAPI(prim).Bind(mat)

root      = "/World/GNM_Replay"
mats_root = f"{root}/Materials"
UsdGeom.Xform.Define(stage, root)
UsdGeom.Xform.Define(stage, mats_root)
mat_dot   = make_mat(f"{mats_root}/dot",   0.2, 0.6, 1.0)
mat_start = make_mat(f"{mats_root}/start", 0.1, 0.9, 0.2)
mat_goal  = make_mat(f"{mats_root}/goal",  1.0, 0.2, 0.1)
mat_robot = make_mat(f"{mats_root}/robot", 0.2, 0.4, 1.0)

Z_MARKER = 1.0

for i in range(n_steps):
    x, y = float(positions[i][0]), float(positions[i][1])
    s = UsdGeom.Sphere.Define(stage, f"{root}/path_{i:04d}")
    s.CreateRadiusAttr(0.06)
    s.AddTranslateOp().Set(Gf.Vec3d(x, y, Z_MARKER))
    bind(s.GetPrim(), mat_dot)

st = UsdGeom.Sphere.Define(stage, f"{root}/START")
st.CreateRadiusAttr(0.30)
st.AddTranslateOp().Set(Gf.Vec3d(sx, sy, Z_MARKER + 0.30))
bind(st.GetPrim(), mat_start)
# Custom attribute: mark as custom scene
st.GetPrim().CreateAttribute("gnm:source", Sdf.ValueTypeNames.String,
                             custom=True).Set("create_custom_gnm_scene.py")
st.GetPrim().CreateAttribute("gnm:scene_id", Sdf.ValueTypeNames.String,
                             custom=True).Set("custom_office")

gl = UsdGeom.Sphere.Define(stage, f"{root}/GOAL")
gl.CreateRadiusAttr(0.35)
gl.AddTranslateOp().Set(Gf.Vec3d(gx, gy, Z_MARKER + 0.35))
bind(gl.GetPrim(), mat_goal)
gl.GetPrim().CreateAttribute("gnm:goal_radius_m", Sdf.ValueTypeNames.Double,
                             custom=True).Set(goal_r)

# ── ROBOT_MARKER ──────────────────────────────────────────────────────────────
robot_xform = UsdGeom.Xform.Define(stage, f"{root}/ROBOT_MARKER")
robot_body  = UsdGeom.Cube.Define(stage, f"{root}/ROBOT_MARKER/body")
robot_body.CreateSizeAttr(0.4)
robot_body.AddTranslateOp().Set(Gf.Vec3d(0, 0, 0.4))
bind(robot_body.GetPrim(), mat_robot)

xformable    = UsdGeom.Xformable(robot_xform.GetPrim())
xformable.ClearXformOpOrder()
translate_op = xformable.AddTranslateOp()
rotate_op    = xformable.AddRotateZOp()
translate_op.Set(Gf.Vec3d(sx, sy, 0.0))
rotate_op.Set(math.degrees(float(yaws[0])))

print()
print("=" * 60)
print("Custom GNM scene loaded (no VLNVerse assets)")
print(f"  /World/GNM_Replay/START  green at ({sx:.2f}, {sy:.2f})")
print(f"  /World/GNM_Replay/GOAL   red   at ({gx:.2f}, {gy:.2f})")
print(f"  Path: {n_steps} waypoints  {path_len:.2f} m")
print(f"  gnm:source = create_custom_gnm_scene.py")
print()
print("Frame the replay: select /World/GNM_Replay → press F")
print("Press Ctrl-C to exit.")
print("=" * 60)

# ── Replay loop ────────────────────────────────────────────────────────────────
idx = 0
dt  = 0.05 / SPEED
while True:
    x  = float(positions[idx][0])
    y  = float(positions[idx][1])
    th = float(yaws[idx]) if idx < len(yaws) else 0.0
    translate_op.Set(Gf.Vec3d(x, y, 0.0))
    rotate_op.Set(math.degrees(th))
    app.update()
    time.sleep(dt)
    idx = (idx + 1) % n_steps
