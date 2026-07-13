"""Live Isaac Sim hospital front-camera demo + gated pilot capture.

Flow: open Isaac -> load the verified hospital.usd -> run the scene-identity gate
(FAIL-CLOSED: refuses to record if the scene is not the hospital) -> place a front
RGB camera at robot height -> move it through one short route -> capture
start/current/goal frames -> write a scene-identity manifest proving the scene.

Usage:
  # headless pilot pack (all 4 routes) -> npy + manifests (default):
  ~/miniforge3/envs/isaac/bin/python scripts/gnm/hospital_front_camera_demo.py --route all
  # live viewport demo of one short route on a desktop with a display:
  ~/miniforge3/envs/isaac/bin/python scripts/gnm/hospital_front_camera_demo.py --gui \
        --route reception_to_corridor

PNG contact sheets are built afterwards with the gnm_train PIL (the isaac-env PIL
crashes on PNG save):
  ~/miniforge3/envs/gnm_train/bin/python scripts/gnm/hospital_scene_locked_build.py
"""
import sys
import math
import json
from pathlib import Path

REPO = Path("/home/favl/robotics/gnm-vlnverse-baseline")
sys.path.insert(0, str(REPO / "scripts/gnm"))


def _arg(flag, default=None):
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if flag in ("--gui",):
            return True
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


GUI = "--gui" in sys.argv
ROUTE = _arg("--route", "all")
OUT = Path(_arg("--out", REPO / "assets/experiments/hospital_h2_collection_20260709"
                "/hospital_scene_locked_exports"))
(OUT / "npy").mkdir(parents=True, exist_ok=True)
W, H = 1280, 720
ROBOT_H = 0.35

# 4 pilot route types; each start/mid/goal as (eye_xyz, target_xyz). Robot-height
# front camera (eye z = 0.35). Poses chosen on verified feature-rich hospital sight-lines.
ROUTES = {
    "reception_to_corridor": {
        "label": "reception → corridor", "use": "pilot sample — proposed: train",
        "frames": {"start": ((-2.6, -0.8, ROBOT_H), (2.2, 0.4, 0.6)),
                   "mid":   ((-0.8, -0.2, ROBOT_H), (3.4, 0.2, 0.6)),
                   "goal":  ((1.2, 0.0, ROBOT_H),  (4.2, 0.4, 0.5))}},
    "corridor_straight": {
        "label": "corridor straight", "use": "pilot sample — proposed: train",
        "frames": {"start": ((-1.5, 0.0, ROBOT_H), (3.5, 0.0, 0.5)),
                   "mid":   ((0.2, 0.0, ROBOT_H),  (4.2, 0.0, 0.5)),
                   "goal":  ((2.0, 0.0, ROBOT_H),  (5.5, 0.0, 0.5))}},
    "turn_t_junction": {
        "label": "left/right turn or T-junction", "use": "pilot sample — proposed: val",
        "frames": {"start": ((0.0, 1.0, ROBOT_H),  (3.0, 0.5, 0.6)),
                   "mid":   ((1.2, 0.4, ROBOT_H),  (2.0, -1.6, 0.5)),
                   "goal":  ((1.4, -0.6, ROBOT_H), (3.6, -2.6, 0.5))}},
    "waiting_to_doorway": {
        "label": "waiting area → doorway / goal", "use": "pilot sample — proposed: test/goal-approach",
        "frames": {"start": ((-2.2, 1.4, ROBOT_H), (1.8, -0.8, 0.6)),
                   "mid":   ((0.0, 0.6, ROBOT_H),  (2.8, -1.6, 0.5)),
                   "goal":  ((1.6, -0.2, ROBOT_H), (3.8, -2.4, 0.5))}},
}
if ROUTE != "all":
    if ROUTE not in ROUTES:
        print(f"[demo] unknown route {ROUTE!r}; choices: {list(ROUTES)} or 'all'")
        raise SystemExit(2)
    ROUTES = {ROUTE: ROUTES[ROUTE]}

from isaacsim import SimulationApp                       # noqa: E402
app = SimulationApp({"headless": not GUI, "width": W, "height": H})

import numpy as np                                       # noqa: E402
import omni.usd                                          # noqa: E402
import omni.replicator.core as rep                       # noqa: E402
from pxr import UsdGeom, UsdLux, Gf                       # noqa: E402
from hospital_scene_identity_gate import (                # noqa: E402
    verify_hospital_scene, write_scene_identity_manifest, HOSPITAL_USD, HOSPITAL_ROOT)

ctx = omni.usd.get_context(); ctx.new_stage(); app.update()
stage = ctx.get_stage()
UsdGeom.Xform.Define(stage, "/World")
stage.SetDefaultPrim(stage.GetPrimAtPath("/World"))
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
UsdGeom.SetStageMetersPerUnit(stage, 1.0)
UsdLux.DomeLight.Define(stage, "/World/DomeLight").CreateIntensityAttr(1000.0)

print(f"[demo] loading hospital: {HOSPITAL_USD}", flush=True)
prim = stage.DefinePrim(HOSPITAL_ROOT)
if not prim.GetReferences().AddReference(HOSPITAL_USD):
    print("[demo] ERROR: could not author hospital reference"); app.close(); raise SystemExit(3)
for _ in range(60):
    app.update()
for _ in range(6000):
    app.update()
    try:
        _, loading, total = ctx.get_stage_loading_status()
    except Exception:
        break
    if loading == 0 and total == 0:
        break

CAM_PATH = "/World/FrontCam"
cam = UsdGeom.Camera.Define(stage, CAM_PATH)
cam.CreateFocalLengthAttr(18.0)
cam.CreateClippingRangeAttr(Gf.Vec2f(0.02, 1000.0))


def aim(eye, tgt):
    dx, dy, dz = (t - c for c, t in zip(eye, tgt))
    yaw = math.degrees(math.atan2(dy, dx)) - 90.0
    pitch = 90.0 - math.degrees(math.atan2(-dz, math.hypot(dx, dy)))
    return yaw, pitch


def place(eye, tgt):
    yaw, pitch = aim(eye, tgt)
    UsdGeom.XformCommonAPI(cam).SetTranslate(Gf.Vec3d(*eye))
    UsdGeom.XformCommonAPI(cam).SetRotate(Gf.Vec3f(pitch, 0.0, yaw))
    return yaw


rp = rep.create.render_product(CAM_PATH, (W, H))
annot = rep.AnnotatorRegistry.get_annotator("rgb")
try:
    annot.attach([rp])
except Exception:
    annot.attach(rp)


def capture():
    for _ in range(12):
        try:
            rep.orchestrator.step(rt_subframes=16)
        except Exception:
            for _ in range(20):
                app.update()
        arr = np.asarray(annot.get_data())
        if arr.size and arr.ndim >= 2:
            return np.ascontiguousarray(arr[..., :3])
    return None


# --- SCENE-IDENTITY GATE (fail closed BEFORE recording) ---
probe = place((-2.5, -0.5, ROBOT_H), (3.0, -1.0, 0.6))
first_rgb = capture()
gate = verify_hospital_scene(stage, scene_mode="hospital", front_cam_path=CAM_PATH,
                             resolution=[W, H], front_rgb=first_rgb)
write_scene_identity_manifest(OUT / "scene_identity_manifest.json", gate,
                              run_kind="hospital_front_camera_demo",
                              extra={"gui": GUI, "routes_requested": list(ROUTES),
                                     "front_camera_path": CAM_PATH})
print("[demo] gate checks:", json.dumps(gate["checks"]), flush=True)
if not gate["pass"]:
    print("[demo] SCENE-IDENTITY GATE FAILED — refusing to record.", gate["reasons"], flush=True)
    app.close(); raise SystemExit(5)
print("[demo] gate PASS — scene is the real hospital. Capturing.", flush=True)

pack = {"asset_path": HOSPITAL_USD, "scene_identity_pass": True, "resolution": [W, H],
        "robot_camera_height_m": ROBOT_H, "focal_length_mm": 18.0, "routes": {}}
for rname, rdef in ROUTES.items():
    frames = {}
    for fname, (eye, tgt) in rdef["frames"].items():
        yaw = place(eye, tgt)
        if GUI:
            for _ in range(30):
                app.update()
        rgb = capture()
        if rgb is None:
            print(f"[demo] {rname}/{fname}: EMPTY capture", flush=True); continue
        npy = OUT / "npy" / f"{rname}_{fname}.npy"
        np.save(npy, rgb)
        frames[fname] = {
            "array_file": f"npy/{npy.name}",
            "camera_pose": {"x": eye[0], "y": eye[1], "z": eye[2], "target": list(tgt),
                            "focal_length_mm": 18.0, "yaw_deg": round(yaw, 1)},
            "robot_pose": {"x": eye[0], "y": eye[1], "z": 0.0, "yaw_deg": round(yaw, 1)},
            "mean_luma": round(float(rgb.mean()), 1)}
        print(f"[demo] {rname}/{fname}: {rgb.shape} luma={rgb.mean():.1f}", flush=True)
    pack["routes"][rname] = {"label": rdef["label"], "use": rdef["use"], "frames": frames}

(OUT / "pilot_capture_poses.json").write_text(json.dumps(pack, indent=2))
print(f"[demo] DONE -> {OUT}  (run hospital_scene_locked_build.py to build PNG contact sheets)", flush=True)
app.close()
