from isaacsim import SimulationApp

app = SimulationApp({
    "headless": False,
    "width": 1280,
    "height": 720,
})

import time
import pickle
from pathlib import Path

import omni.usd
from pxr import UsdGeom, Gf


def find_trajectory():
    candidates = sorted(Path("datasets/vlntube/train").glob("*/traj_data.pkl"))
    if not candidates:
        raise FileNotFoundError("No traj_data.pkl found under datasets/vlntube/train")

    path = candidates[0]
    with path.open("rb") as f:
        data = pickle.load(f)

    for key in ["position", "positions", "pos", "xy"]:
        if isinstance(data, dict) and key in data:
            return path, data[key]

    if isinstance(data, dict):
        for key, value in data.items():
            if hasattr(value, "shape") and len(value.shape) >= 2 and value.shape[1] >= 2:
                return path, value

    raise KeyError(f"Could not find position array in {path}. Keys: {list(data.keys())}")


def set_color(geom, rgb):
    geom.CreateDisplayColorAttr().Set([Gf.Vec3f(*rgb)])


def make_cube(stage, path, translate, scale, color):
    cube = UsdGeom.Cube.Define(stage, path)
    cube.CreateSizeAttr(1.0)
    UsdGeom.XformCommonAPI(cube).SetTranslate(Gf.Vec3d(*translate))
    UsdGeom.XformCommonAPI(cube).SetScale(Gf.Vec3f(*scale))
    set_color(cube, color)
    return cube


def make_sphere(stage, path, translate, radius, color):
    sphere = UsdGeom.Sphere.Define(stage, path)
    sphere.CreateRadiusAttr(radius)
    UsdGeom.XformCommonAPI(sphere).SetTranslate(Gf.Vec3d(*translate))
    set_color(sphere, color)
    return sphere


ctx = omni.usd.get_context()
ctx.new_stage()
app.update()

stage = ctx.get_stage()
world = UsdGeom.Xform.Define(stage, "/World")
stage.SetDefaultPrim(world.GetPrim())

UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
UsdGeom.SetStageMetersPerUnit(stage, 1.0)

traj_path, positions = find_trajectory()
positions = list(positions)

print(f"GNM LIVE ISAAC TRAJECTORY")
print(f"Trajectory: {traj_path}")
print(f"Frames: {len(positions)}")

# Floor and simple environment
make_cube(stage, "/World/Floor", (0, 0, -0.03), (25, 25, 0.04), (0.35, 0.35, 0.35))
make_cube(stage, "/World/Wall_Back", (0, 10, 1.0), (25, 0.2, 2.0), (0.55, 0.55, 0.55))
make_cube(stage, "/World/Wall_Left", (-10, 0, 1.0), (0.2, 25, 2.0), (0.55, 0.55, 0.55))
make_cube(stage, "/World/Obstacle_1", (2, -1, 0.5), (1.0, 1.0, 1.0), (0.6, 0.25, 0.25))
make_cube(stage, "/World/Obstacle_2", (-2, 2, 0.5), (1.2, 0.8, 1.0), (0.25, 0.25, 0.6))

# Scale path into view if needed
xy = [(float(p[0]), float(p[1])) for p in positions]
xs = [p[0] for p in xy]
ys = [p[1] for p in xy]
cx = (min(xs) + max(xs)) / 2.0
cy = (min(ys) + max(ys)) / 2.0
span = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
scale = min(14.0 / span, 1.0)

def map_xy(x, y):
    return ((x - cx) * scale, (y - cy) * scale)

mapped = [map_xy(x, y) for x, y in xy]

# Start, goal, trajectory breadcrumbs
sx, sy = mapped[0]
gx, gy = mapped[-1]
make_sphere(stage, "/World/Start", (sx, sy, 0.25), 0.28, (0.1, 0.8, 0.1))
make_sphere(stage, "/World/Goal", (gx, gy, 0.25), 0.35, (0.9, 0.1, 0.1))

for i, (x, y) in enumerate(mapped[::5]):
    make_sphere(stage, f"/World/Path_{i:03d}", (x, y, 0.08), 0.08, (0.1, 0.45, 0.9))

robot = make_cube(stage, "/World/GNM_Robot", (sx, sy, 0.35), (0.45, 0.35, 0.25), (1.0, 0.8, 0.1))

# Camera
camera = UsdGeom.Camera.Define(stage, "/World/Camera")
UsdGeom.XformCommonAPI(camera).SetTranslate(Gf.Vec3d(0, -14, 11))
UsdGeom.XformCommonAPI(camera).SetRotate(Gf.Vec3f(55, 0, 0))

try:
    import omni.kit.viewport.utility as vp_utils
    viewport = vp_utils.get_active_viewport()
    if viewport:
        viewport.camera_path = "/World/Camera"
except Exception as e:
    print("Viewport camera set skipped:", e)

print("Starting live replay...")
for i, (x, y) in enumerate(mapped):
    UsdGeom.XformCommonAPI(robot).SetTranslate(Gf.Vec3d(x, y, 0.35))
    app.update()
    if i % 10 == 0:
        print(f"frame {i:03d}/{len(mapped)-1}  x={x:.2f} y={y:.2f}")
    time.sleep(0.07)

print("Replay complete. Holding Isaac window open. Press Ctrl+C in terminal to close.")

try:
    while True:
        app.update()
        time.sleep(1 / 60)
except KeyboardInterrupt:
    print("Closing Isaac live demo.")

app.close()
