"""Visualise real Track A stop-policy decisions in the Isaac Hospital scene.

For each requested validation episode this renders the dataset's recorded
demonstration trajectory plus, for each evaluated stop policy, a dotted
circle around the goal at that policy's recorded termination distance
(final_dist_m from the per-episode results CSVs — nothing is re-simulated).

The evaluation rolled out the GNM agent, whose path differs from the
demonstration and was not persisted, so termination *positions* are
unknowable after the fact; termination *distance to goal* is exact.
A policy circle inside the red 3 m success ring reads as success, outside
as failure.

Outputs per episode under assets/experiments/<episode_id>/:
    start_view.png     first-person view from the start pose toward the goal
    overview.png       lobby overview: demo path, success ring, distance circles
    replay.mp4         robot replaying the demonstration path (overview camera)
    keyframe_start.png robot at the start pose
    keyframe_mid.png   robot mid-path
    keyframe_end.png   robot at the demonstration path end
    metrics.json       the real per-policy rows from the results CSVs
    scene.usda         reopenable composed stage (standing save rule)

A campaign-level run manifest (environment, data provenance, outputs) is
written to assets/experiments/run_manifest_<timestamp>.json.

Marker legend: green = start, red = goal (translucent disk = 3 m success
radius), purple = temporal stop head termination, orange = deployable
baseline termination (end of episode if its stop never fired).

Run:
    ~/miniforge3/envs/isaac/bin/python -u scripts/gnm/isaac_stop_decision_replay.py \
        [episode_id ...]
"""

import sys

EPISODES = sys.argv[1:] or [
    "kujiale_0203_kujiale_0203_25_0",
    "kujiale_0203_kujiale_0203_16_3",
    "kujiale_0092_kujiale_0092_91_1",
]

from isaacsim import SimulationApp

app = SimulationApp({
    "headless": True,
    "width": 1280,
    "height": 720,
})

import csv
import hashlib
import json
import math
import pickle
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import omni.usd
from pxr import Usd, UsdGeom, UsdLux, Gf

REPO = Path(__file__).resolve().parents[2]
VAL = REPO / "datasets/vlntube/val"
ROBOT_USD = REPO / "assets/robots/yahboom_m3_pro/yahboom_m3pro_visible_placeholder.usda"
ROBOT_PRIM_IN_FILE = "/World/YahboomM3Pro"
# The placeholder M3Pro is true physical size (~0.3 m); scale it up so it
# reads clearly at overview-camera distance. Recorded in the manifest.
ROBOT_DISPLAY_SCALE = 1.5
VIDEO_FPS = 8
POLICIES = {
    "temporal_stop_head": {
        "csv": REPO / "results/bo_reviewer_packet/temporal_stop_head/22_temporal_stop_head_details.csv",
        "color": (0.55, 0.15, 0.75),  # purple
    },
    "deployable_stop_policy": {
        "csv": REPO / "results/bo_reviewer_packet/deployable_stop_policy/17_deployable_stop_policy_details.csv",
        "color": (0.95, 0.55, 0.10),  # orange
    },
}
SUCCESS_RADIUS_M = 3.0
HOSPITAL_USD = (
    "https://omniverse-content-production.s3-us-west-2.amazonaws.com"
    "/Assets/Isaac/5.1/Isaac/Environments/Hospital/hospital.usd"
)
# Keep scaled trajectories inside the reception lobby (see
# docs/ISAAC_HOSPITAL_ENVIRONMENT.md for the layout constraints).
LOBBY_FIT_M = 8.0


def load_policy_rows(episode_id):
    rows = {}
    for name, spec in POLICIES.items():
        with open(spec["csv"]) as f:
            for row in csv.DictReader(f):
                if row["episode_id"] == episode_id:
                    rows[name] = row
                    break
    return rows


def set_color(geom, rgb, opacity=None):
    geom.CreateDisplayColorAttr().Set([Gf.Vec3f(*rgb)])
    if opacity is not None:
        geom.CreateDisplayOpacityAttr().Set([opacity])


def sphere(stage, path, translate, radius, color):
    s = UsdGeom.Sphere.Define(stage, path)
    s.CreateRadiusAttr(radius)
    UsdGeom.XformCommonAPI(s).SetTranslate(Gf.Vec3d(*translate))
    set_color(s, color)
    return s


def aim_at(cam_xyz, target_xyz):
    dx, dy, dz = (t - c for c, t in zip(cam_xyz, target_xyz))
    yaw = math.degrees(math.atan2(dy, dx)) - 90.0
    pitch = 90.0 - math.degrees(math.atan2(-dz, math.hypot(dx, dy)))
    return Gf.Vec3f(pitch, 0.0, yaw)


def capture(viewport, output_path, camera_path, settle=60):
    from omni.kit.viewport.utility import capture_viewport_to_file

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    viewport.camera_path = camera_path
    for _ in range(settle):
        app.update()
    capture_viewport_to_file(viewport, str(output_path))
    for _ in range(60):
        app.update()
    print(f"[capture] {output_path}")


ctx = omni.usd.get_context()
ctx.new_stage()
app.update()
stage = ctx.get_stage()
world = UsdGeom.Xform.Define(stage, "/World")
stage.SetDefaultPrim(world.GetPrim())
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
UsdGeom.SetStageMetersPerUnit(stage, 1.0)

dome = UsdLux.DomeLight.Define(stage, "/World/DomeLight")
dome.CreateIntensityAttr(1000.0)

env = stage.DefinePrim("/World/Hospital")
env.GetReferences().AddReference(HOSPITAL_USD)
print(f"Loading hospital environment: {HOSPITAL_USD}")
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

try:
    import carb.settings
    _settings = carb.settings.get_settings()
    _settings.set("/app/viewport/grid/enabled", False)
    _settings.set("/persistent/app/viewport/displayOptions", 0)
except Exception as e:
    print("Grid overlay disable skipped:", e)

from omni.kit.viewport.utility import get_active_viewport

viewport = get_active_viewport()

for episode_id in EPISODES:
    traj_pkl = VAL / episode_id / "traj_data.pkl"
    if not traj_pkl.exists():
        print(f"[skip] {episode_id}: no {traj_pkl}")
        continue
    rows = load_policy_rows(episode_id)
    if not rows:
        print(f"[skip] {episode_id}: not in any policy details CSV")
        continue

    with traj_pkl.open("rb") as f:
        data = pickle.load(f)
    xy = [(float(p[0]), float(p[1])) for p in data["position"]]

    xs, ys = [p[0] for p in xy], [p[1] for p in xy]
    cx, cy = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
    span = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
    scale = min(LOBBY_FIT_M / span, 1.0)
    mapped = [((x - cx) * scale, (y - cy) * scale) for x, y in xy]
    sx, sy = mapped[0]
    gx, gy = mapped[-1]

    stage.RemovePrim("/World/Viz")
    viz = UsdGeom.Xform.Define(stage, "/World/Viz")

    sphere(stage, "/World/Viz/Start", (sx, sy, 0.25), 0.22, (0.1, 0.8, 0.1))
    sphere(stage, "/World/Viz/Goal", (gx, gy, 0.25), 0.28, (0.9, 0.1, 0.1))
    # Circles are dotted: RTX renders displayOpacity on a filled disk as
    # opaque, which floods the floor.
    def dotted_circle(tag, radius, z, dot_r, color, n=64):
        for i in range(n):
            a = 2 * math.pi * i / n
            sphere(stage, f"/World/Viz/{tag}_{i:02d}",
                   (gx + radius * math.cos(a), gy + radius * math.sin(a), z),
                   dot_r, color)

    dotted_circle("Ring", SUCCESS_RADIUS_M * scale, 0.03, 0.045,
                  (0.9, 0.2, 0.2))

    for i, (x, y) in enumerate(mapped[::3]):
        sphere(stage, f"/World/Viz/Path_{i:03d}", (x, y, 0.06), 0.06,
               (0.1, 0.45, 0.9))

    metrics = {
        "episode_id": episode_id,
        "success_radius_m": SUCCESS_RADIUS_M,
        "display_scale": scale,
        "visualization_note": (
            "policy circles show recorded termination DISTANCE to goal "
            "(final_dist_m); agent rollout paths were not persisted by the "
            "evaluation, so termination positions are not shown. The blue "
            "path is the dataset demonstration trajectory."
        ),
        "policies": {},
    }
    for name, spec in POLICIES.items():
        row = rows.get(name)
        if row is None:
            continue
        final_dist = float(row["final_dist_m"])
        dotted_circle(f"Dist_{name}", final_dist * scale, 0.06, 0.055,
                      spec["color"], n=48)
        metrics["policies"][name] = {
            "stop_fired": row["stop_fired"] == "True",
            "stop_step": int(row["stop_step"]) if row["stop_step"] else None,
            "n_steps": int(row["n_steps"]),
            "final_dist_m": final_dist,
            "success": row["success"] == "True",
        }

    dx, dy = gx - sx, gy - sy
    dist = math.hypot(dx, dy) or 1.0
    ux, uy = dx / dist, dy / dist
    start_eye = (sx - 2.8 * ux + 1.2 * uy, sy - 2.8 * uy - 1.2 * ux, 2.4)
    start_cam = UsdGeom.Camera.Define(stage, "/World/Viz/StartViewCamera")
    start_cam.CreateFocalLengthAttr(18.0)
    UsdGeom.XformCommonAPI(start_cam).SetTranslate(Gf.Vec3d(*start_eye))
    UsdGeom.XformCommonAPI(start_cam).SetRotate(aim_at(start_eye, (gx, gy, 0.25)))

    # Slightly ahead of the start-view eye so lobby furniture behind the
    # start (e.g. the reception desk) cannot fill the foreground.
    cxm = sum(x for x, _ in mapped) / len(mapped)
    cym = sum(y for _, y in mapped) / len(mapped)
    over_eye = (sx - 0.8 * ux + 1.4 * uy, sy - 0.8 * uy - 1.4 * ux, 2.75)
    over_cam = UsdGeom.Camera.Define(stage, "/World/Viz/OverviewCamera")
    over_cam.CreateFocalLengthAttr(18.0)
    UsdGeom.XformCommonAPI(over_cam).SetTranslate(Gf.Vec3d(*over_eye))
    UsdGeom.XformCommonAPI(over_cam).SetRotate(
        aim_at(over_eye, (cxm, cym, 0.2)))

    # Yahboom M3Pro placeholder as the replayed robot, posed with the
    # recorded per-step yaw.
    yaws = [math.degrees(float(a)) for a in data.get("yaw", [0.0] * len(mapped))]
    robot_prim = stage.DefinePrim("/World/Viz/Robot")
    robot_prim.GetReferences().AddReference(str(ROBOT_USD), ROBOT_PRIM_IN_FILE)
    robot_api = UsdGeom.XformCommonAPI(UsdGeom.Xformable(robot_prim))
    # The placeholder is not modelled at physical scale; normalise its
    # footprint to the real M3Pro length (~0.45 m) times the display factor.
    bbox = UsdGeom.BBoxCache(
        Usd.TimeCode.Default(), [UsdGeom.Tokens.default_]
    ).ComputeWorldBound(robot_prim).ComputeAlignedRange().GetSize()
    max_xy = max(bbox[0], bbox[1], 1e-6)
    robot_scale = 0.45 * ROBOT_DISPLAY_SCALE / max_xy
    robot_api.SetScale(Gf.Vec3f(robot_scale))

    def pose_robot(i):
        x, y = mapped[i]
        robot_api.SetTranslate(Gf.Vec3d(x, y, 0.02))
        robot_api.SetRotate(Gf.Vec3f(0.0, 0.0, yaws[min(i, len(yaws) - 1)]))

    pose_robot(0)

    out = REPO / "assets/experiments" / episode_id
    out.mkdir(parents=True, exist_ok=True)

    stage.GetRootLayer().Export(str(out / "scene.usda"))
    with open(out / "metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    capture(viewport, out / "start_view.png", "/World/Viz/StartViewCamera")
    capture(viewport, out / "overview.png", "/World/Viz/OverviewCamera")

    # Replay video: robot follows the full recorded path (overview camera).
    from omni.kit.viewport.utility import capture_viewport_to_file

    frames_dir = out / "frames"
    frames_dir.mkdir(exist_ok=True)
    viewport.camera_path = "/World/Viz/OverviewCamera"
    for _ in range(30):
        app.update()
    for i in range(len(mapped)):
        pose_robot(i)
        for _ in range(2):
            app.update()
        capture_viewport_to_file(viewport, str(frames_dir / f"frame_{i:04d}.png"))
        for _ in range(4):
            app.update()
    for _ in range(90):
        app.update()

    keyframes = {
        "keyframe_start.png": 0,
        "keyframe_mid.png": len(mapped) // 2,
        "keyframe_end.png": len(mapped) - 1,
    }
    for name, idx in keyframes.items():
        src = frames_dir / f"frame_{idx:04d}.png"
        if src.exists():
            shutil.copy2(src, out / name)

    try:
        from imageio_ffmpeg import get_ffmpeg_exe

        def encode(codec):
            subprocess.run(
                [get_ffmpeg_exe(), "-y", "-framerate", str(VIDEO_FPS),
                 "-i", str(frames_dir / "frame_%04d.png"),
                 "-c:v", codec, "-pix_fmt", "yuv420p",
                 str(out / "replay.mp4")],
                check=True, capture_output=True)

        try:
            encode("libx264")
        except subprocess.CalledProcessError:
            encode("mpeg4")
        shutil.rmtree(frames_dir)
        print(f"[video] {out / 'replay.mp4'}")
    except Exception as e:
        print(f"[video] assembly failed, raw frames kept: {e}")

    print(f"[episode done] {episode_id}: {metrics['policies']}")


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


def cmd_out(args):
    try:
        return subprocess.run(args, capture_output=True, text=True,
                              timeout=20).stdout.strip()
    except Exception as e:
        return f"unavailable: {e}"


manifest = {
    "campaign": "isaac_hospital_stop_decision_replay",
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "hypothesis": (
        "The temporal stop head terminates within the 3 m success radius on "
        "episodes where the deployable baseline stop rule fails to fire or "
        "fires outside it; drawing each policy's recorded termination "
        "distance as a circle against the success ring makes those failure "
        "modes legible."
    ),
    "known_limitation": (
        "the evaluation did not persist agent rollout paths, so policy "
        "termination positions cannot be rendered — only exact distances; "
        "Phase 2 must log agent trajectories per episode"
    ),
    "environment": {
        "scene": HOSPITAL_USD,
        "gpu": cmd_out(["nvidia-smi", "--query-gpu=name,driver_version",
                        "--format=csv,noheader"]),
        "isaac_sim": "isaacsim 5.1.0 (pip, conda env 'isaac')",
        "headless": True,
        "resolution": "1280x720",
    },
    "robot": {
        "platform": "Yahboom ROSMASTER M3 Pro",
        "asset": str(ROBOT_USD.relative_to(REPO)),
        "note": ("primitive visible-placeholder model (see "
                 "docs/YAHBOOM_URDF_TO_USD_IMPORT.md); footprint normalised "
                 f"to 0.45 m x {ROBOT_DISPLAY_SCALE} display factor "
                 "(placeholder is not modelled at physical scale)"),
    },
    "models_evaluated": {
        name: {
            "details_csv": str(spec["csv"].relative_to(REPO)),
            "sha256_12": file_digest(spec["csv"]),
        } for name, spec in POLICIES.items()
    },
    "data": {
        "trajectories": "datasets/vlntube/val/<episode_id>/traj_data.pkl",
        "provenance": ("stop decisions taken verbatim from the Track A "
                       "per-episode results; nothing re-simulated"),
        "success_radius_m": SUCCESS_RADIUS_M,
        "display_note": ("trajectories uniformly scaled to fit the lobby "
                         f"(max span {LOBBY_FIT_M} m); scale recorded per "
                         "episode in metrics.json"),
    },
    "git_head": cmd_out(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"]),
    "episodes": EPISODES,
    "outputs_per_episode": [
        "start_view.png", "overview.png", "replay.mp4",
        "keyframe_start.png", "keyframe_mid.png", "keyframe_end.png",
        "metrics.json", "scene.usda",
    ],
}
manifest_path = (REPO / "assets/experiments" /
                 f"run_manifest_{datetime.now():%Y%m%d-%H%M%S}.json")
manifest_path.parent.mkdir(parents=True, exist_ok=True)
with open(manifest_path, "w") as f:
    json.dump(manifest, f, indent=2)
print(f"[manifest] {manifest_path}")

print("All episodes done.")
app.close()
