from isaacsim import SimulationApp

app = SimulationApp({
    "headless": False,
    "width": 1280,
    "height": 720,
})

import math
import time
import pickle
from pathlib import Path

import omni.usd
from pxr import UsdGeom, UsdLux, Gf


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

# The hospital environment ships its own light rig; this low-intensity
# dome is a safety net so markers never render black if that rig changes.
dome = UsdLux.DomeLight.Define(stage, "/World/DomeLight")
dome.CreateIntensityAttr(1000.0)

traj_path, positions = find_trajectory()
positions = list(positions)

print(f"GNM LIVE ISAAC TRAJECTORY")
print(f"Trajectory: {traj_path}")
print(f"Frames: {len(positions)}")

# Isaac 5.1 Hospital environment, streamed from the official asset bucket
# (cached locally by omni.client after the first download).
HOSPITAL_USD = (
    "https://omniverse-content-production.s3-us-west-2.amazonaws.com"
    "/Assets/Isaac/5.1/Isaac/Environments/Hospital/hospital.usd"
)
env = stage.DefinePrim("/World/Hospital")
env.GetReferences().AddReference(HOSPITAL_USD)
print(f"Loading hospital environment (first run downloads assets): {HOSPITAL_USD}")
for _ in range(60):
    app.update()
for _ in range(3000):
    app.update()
    try:
        _, loading, total = ctx.get_stage_loading_status()
    except Exception:
        break
    if loading == 0 and total == 0:
        break
print("Hospital environment loaded.")

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

def aim_at(cam_xyz, target_xyz):
    """rotateXYZ (deg) that points a camera at target: X pitches down from
    horizontal, Z yaws it (a zero-yaw camera in this Z-up stage looks
    along +Y)."""
    dx, dy, dz = (t - c for c, t in zip(cam_xyz, target_xyz))
    yaw = math.degrees(math.atan2(dy, dx)) - 90.0
    pitch = 90.0 - math.degrees(math.atan2(-dz, math.hypot(dx, dy)))
    return Gf.Vec3f(pitch, 0.0, yaw)


# Elevated over-the-shoulder camera behind the start marker, aimed at the
# goal so the whole start-to-goal line of sight is in frame.
dx, dy = gx - sx, gy - sy
dist = math.hypot(dx, dy) or 1.0
ux, uy = dx / dist, dy / dist
start_eye = (sx - 2.8 * ux + 1.2 * uy, sy - 2.8 * uy - 1.2 * ux, 2.4)
start_cam = UsdGeom.Camera.Define(stage, "/World/StartViewCamera")
start_cam.CreateFocalLengthAttr(18.0)
UsdGeom.XformCommonAPI(start_cam).SetTranslate(Gf.Vec3d(*start_eye))
UsdGeom.XformCommonAPI(start_cam).SetRotate(aim_at(start_eye, (gx, gy, 0.25)))

# Overview camera for the replay. The reception lobby is small and its
# south-east wall sits just behind the start-view camera, so both the
# entrance vestibule at (0, -6.5) and (5.5, -4.8) are outside the room.
# Stay on the start-to-goal sight line (known-open interior), slightly
# forward of the start-view eye and just below the ~3 m ceiling.
over_eye = (sx - 1.6 * ux + 1.2 * uy, sy - 1.6 * uy - 1.2 * ux, 2.65)
camera = UsdGeom.Camera.Define(stage, "/World/Camera")
camera.CreateFocalLengthAttr(18.0)
UsdGeom.XformCommonAPI(camera).SetTranslate(Gf.Vec3d(*over_eye))
# Aim midway between the trajectory centre (origin) and the goal so the
# whole breadcrumb trail plus the goal sit comfortably in frame.
UsdGeom.XformCommonAPI(camera).SetRotate(
    aim_at(over_eye, (gx / 2, gy / 2, 0.3)))

try:
    import carb.settings
    _settings = carb.settings.get_settings()
    _settings.set("/app/viewport/grid/enabled", False)
    _settings.set("/persistent/app/viewport/displayOptions", 0)
except Exception as e:
    print("Grid overlay disable skipped:", e)

try:
    import omni.kit.viewport.utility as vp_utils
    viewport = vp_utils.get_active_viewport()
    if viewport:
        viewport.camera_path = "/World/Camera"
except Exception as e:
    print("Viewport camera set skipped:", e)

def capture_deck_screenshot(output_path, camera_path=None, settle_frames=60):
    from omni.kit.viewport.utility import get_active_viewport, capture_viewport_to_file

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    viewport = get_active_viewport()
    if camera_path:
        viewport.camera_path = camera_path
        # Let the RTX renderer converge on the new view before capturing.
        for _ in range(settle_frames):
            app.update()
    capture_viewport_to_file(viewport, str(output_path))

    # Allow Isaac / Omniverse enough rendered frames to complete the capture.
    for _ in range(60):
        app.update()

    print(f"[deck] Isaac Sim screenshot saved to: {output_path}")


# Persist the composed experiment scene (hospital reference + trajectory
# markers + cameras) so every run leaves a reopenable stage in the repo.
SCENE_EXPORT = Path("assets/isaac/tracka_hospital_replay_stage.usda")
SCENE_EXPORT.parent.mkdir(parents=True, exist_ok=True)
stage.GetRootLayer().Export(str(SCENE_EXPORT))
print(f"[scene] Stage saved to: {SCENE_EXPORT}")

capture_deck_screenshot(
    "assets/deck/isaac_sim_tracka_start_view_toward_goal.png",
    camera_path="/World/StartViewCamera",
)

try:
    vp_utils.get_active_viewport().camera_path = "/World/Camera"
    for _ in range(20):
        app.update()
except Exception as e:
    print("Viewport camera restore skipped:", e)

print("Starting live replay...")
for i, (x, y) in enumerate(mapped):
    UsdGeom.XformCommonAPI(robot).SetTranslate(Gf.Vec3d(x, y, 0.35))
    app.update()
    if i % 10 == 0:
        print(f"frame {i:03d}/{len(mapped)-1}  x={x:.2f} y={y:.2f}")
    time.sleep(0.07)

capture_deck_screenshot(
    "assets/deck/isaac_sim_tracka_trajectory_replay.png",
    camera_path="/World/Camera",
    settle_frames=20,
)

print("Replay complete. Holding Isaac window open. Press Ctrl+C in terminal to close.")

try:
    while True:
        app.update()
        time.sleep(1 / 60)
except KeyboardInterrupt:
    print("Closing Isaac live demo.")

app.close()
