"""H8-M Track B — SYNTHETIC_DIAGNOSTIC_ONLY fork RENDER SCAN (validation-only; gates 1-7 input).

Renders the authored 4-way cross junction
`assets/scenes/synthetic_diagnostic_fork/synthetic_diagnostic_fork.usda` to test whether it actually
satisfies the render-valid angular branch-choice requirements (render-validity + depth-openness +
open-floor/collinear guards + embedding distinctness + action-angle) — i.e. whether the EXPECTED
design property holds once pixels + depth are captured. Nothing is proven until the analyze stage
runs; this stage only captures RGB + distance_to_image_plane.

Probes (fixed, known geometry — no interior grid needed):
  * center      @ (0,0,0.47): 4 cardinal views E/N/W/S (junction classification probe).
                              N=branch A (blue), W=branch B (green), E=distractor (orange),
                              S=approach (red).
  * decision    @ (0,-1.2,0.47) facing N: the approach-into-junction decision frame.
  * goalA_img   @ (0,2.2,0.47)  facing N: close goal image of branch A (blue wall + circle).
  * goalB_img   @ (-2.2,0,0.47) facing W: close goal image of branch B (green wall + triangle).

SYNTHETIC_DIAGNOSTIC_ONLY. NO robot spawn, NO drive, NO rosbag, NO trajectory, NO recording, NO
training, NO collection. Free camera only. `CL_BOUND_XY` (the hospital drive watchdog) is unrelated
to this free-camera render and is NOT touched. Raw .npy -> handoff; PNG/contact-sheets/DINO in the
gnm_train analyze stage.

Run: ~/miniforge3/envs/isaac/bin/python -u scripts/gnm/h8_track_b_synthetic_fork_render.py
"""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 640, "height": 480})

import math, json, os                            # noqa: E402
from pathlib import Path                          # noqa: E402
import numpy as np                                # noqa: E402
import omni.usd                                   # noqa: E402
import carb.settings                              # noqa: E402
import omni.replicator.core as rep                # noqa: E402
from pxr import Usd, UsdGeom, UsdLux, Gf          # noqa: E402

HANDOFF = Path(os.environ.get("H8_SFORK_HANDOFF", "/tmp/h8_sfork_npy"))
HANDOFF.mkdir(parents=True, exist_ok=True)
REPO = Path("/home/favl/robotics/gnm-vlnverse-baseline")
USDA = REPO / "assets/scenes/synthetic_diagnostic_fork/synthetic_diagnostic_fork.usda"
SID = "synthetic_diagnostic_fork"
W, H = 640, 480
Z_CAM = 0.47
AIM = 2.0
DIRS = [("E", 0.0), ("N", 90.0), ("W", 180.0), ("S", 270.0)]
def _gy(so):
    return round(3.5 - so, 3)   # end wall inner face at 3.5 m -> goal-cam coord at standoff `so`
# R4: capture goal images at TWO standoffs (1.5 m primary, 2.0 m secondary); analyze picks the
# standoff that best includes branch-specific structure (lower embedding similarity).
NAMED = [("decision", (0.0, -1.2, Z_CAM), 90.0),
         ("goalA_img",    (0.0,  _gy(1.5), Z_CAM), 90.0),    # north branch A, standoff 1.5 m
         ("goalB_img",    (-_gy(1.5), 0.0, Z_CAM), 180.0),   # west  branch B, standoff 1.5 m
         ("goalA_img_20", (0.0,  _gy(2.0), Z_CAM), 90.0),    # north branch A, standoff 2.0 m
         ("goalB_img_20", (-_gy(2.0), 0.0, Z_CAM), 180.0)]   # west  branch B, standoff 2.0 m


def aim_at(cam, tgt):
    dx, dy, dz = (t - c for c, t in zip(cam, tgt))
    yaw = math.degrees(math.atan2(dy, dx)) - 90.0
    pitch = 90.0 - math.degrees(math.atan2(-dz, math.hypot(dx, dy)))
    return Gf.Vec3f(pitch, 0.0, yaw)


def central_median_depth(depth):
    d = np.asarray(depth, dtype=np.float32)
    if d.ndim < 2 or d.size == 0:
        return None
    h, w = d.shape[:2]
    c = d[int(h * 0.3):int(h * 0.7), int(w * 0.3):int(w * 0.7)].ravel()
    c = c[np.isfinite(c)]
    c = c[(c > 0.05) & (c < 500.0)]
    return round(float(np.median(c)), 3) if c.size else None


def blackfrac(rgb):
    lower = rgb[int(H * 2 / 3):, :, :]
    return float((lower.max(axis=2) < 12).mean())


def load_scene(usd):
    """Reference the local authored USDA under /World/Scene (references remap internal material
    bindings, so the coloured end panels stay bound). Adds a DomeLight for parity with the scans."""
    ctx = omni.usd.get_context(); ctx.new_stage(); app.update()
    stage = ctx.get_stage()
    world = UsdGeom.Xform.Define(stage, "/World"); stage.SetDefaultPrim(world.GetPrim())
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z); UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdLux.DomeLight.Define(stage, "/World/DomeLight").CreateIntensityAttr(1000.0)
    root = "/World/Scene"
    env = stage.DefinePrim(root)
    ok = env.GetReferences().AddReference(usd)
    for _ in range(60):
        app.update()
    for _ in range(8000):
        app.update()
        try:
            _, loading, total = ctx.get_stage_loading_status()
        except Exception:
            break
        if loading == 0 and total == 0:
            break
    n = sum(1 for p in stage.Traverse() if str(p.GetPath()).startswith(root + "/"))
    carb.settings.get_settings().set("/app/viewport/grid/enabled", False)
    return stage, ctx, root, bool(ok), n


def world_bbox(stage, root):
    try:
        cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(),
                                  [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
        rng = cache.ComputeWorldBound(stage.GetPrimAtPath(root)).ComputeAlignedRange()
        mn, mx = rng.GetMin(), rng.GetMax()
        bb = [float(mn[0]), float(mn[1]), float(mn[2]), float(mx[0]), float(mx[1]), float(mx[2])]
        if not all(math.isfinite(v) for v in bb):
            return None
        return [round(v, 3) for v in bb]
    except Exception as e:
        print(f"[sfork] bbox error: {e}", flush=True)
        return None


def make_cam(stage):
    cp = "/World/ScanCam"
    cam = UsdGeom.Camera.Define(stage, cp)
    cam.CreateFocalLengthAttr(18.0)
    cam.CreateClippingRangeAttr(Gf.Vec2f(0.02, 1000.0))
    rp = rep.create.render_product(cp, (W, H))
    a_rgb = rep.AnnotatorRegistry.get_annotator("rgb")
    a_dep = rep.AnnotatorRegistry.get_annotator("distance_to_image_plane")
    for a in (a_rgb, a_dep):
        try:
            a.attach([rp])
        except Exception:
            a.attach(rp)
    return cp, rp, a_rgb, a_dep


def shoot(stage, cp, a_rgb, a_dep, name, eye, yaw_deg):
    tgt = (eye[0] + AIM * math.cos(math.radians(yaw_deg)),
           eye[1] + AIM * math.sin(math.radians(yaw_deg)), eye[2])
    prim = stage.GetPrimAtPath(cp)
    UsdGeom.XformCommonAPI(prim).SetTranslate(Gf.Vec3d(*eye))
    UsdGeom.XformCommonAPI(prim).SetRotate(aim_at(eye, tgt))
    data = np.zeros((0,)); dep = None
    for _ in range(12):
        try:
            rep.orchestrator.step(rt_subframes=16)
        except Exception:
            for _ in range(20):
                app.update()
        arr = np.asarray(a_rgb.get_data())
        if arr.size and arr.ndim >= 2:
            data = arr
            try:
                dep = np.asarray(a_dep.get_data())
            except Exception:
                dep = None
            break
    if data.size == 0 or data.ndim < 2:
        return None
    if data.dtype != np.uint8:
        data = (data * 255).clip(0, 255).astype(np.uint8)
    rgb = np.ascontiguousarray(data[..., :3])
    np.save(HANDOFF / f"{name}.npy", rgb)
    return {"mean_luma": round(float(rgb.mean()), 1),
            "lower_frame_black_frac": round(blackfrac(rgb), 4),
            "median_depth_central_m": (central_median_depth(dep) if dep is not None else None),
            "eye": list(eye), "yaw_deg": yaw_deg}


scan = {"label": "SYNTHETIC_DIAGNOSTIC_ONLY", "scene_id": SID, "asset_path": str(USDA),
        "isaac_sim_version": "5.1.0.0", "resolution": [W, H], "camera_height_m": Z_CAM,
        "directions": [d for d, _ in DIRS], "free_camera_no_robot_body": True,
        "cl_bound_xy_touched": False, "scenes": []}

print(f"[sfork] === {SID}: {USDA}", flush=True)
stage, ctx, root, ok, n = load_scene(str(USDA))
print(f"[sfork] ref_authored={ok} prims={n}", flush=True)
cp, rp, a_rgb, a_dep = make_cam(stage)
bb = world_bbox(stage, root)

probe0 = shoot(stage, cp, a_rgb, a_dep, f"{SID}__loadprobe", (0.0, 0.0, Z_CAM), 90.0)
load_ok = bool(ok and n >= 15)
print(f"[sfork] bbox={bb} load_ok={load_ok} loadprobe={probe0}", flush=True)

sc = {"scene_id": SID, "asset_path": str(USDA), "ref_authored": ok, "prim_count": n,
      "world_bbox": bb, "scene_load_ok": load_ok, "load_probe": probe0, "probes": [],
      "named_frames": {}}

# center probe — 4 cardinal views (junction classification probe)
eye = (0.0, 0.0, Z_CAM)
views = {}
for dname, dyaw in DIRS:
    r = shoot(stage, cp, a_rgb, a_dep, f"{SID}__center__{dname}", eye, dyaw)
    views[dname] = r if r else {"empty": True}
    print(f"[sfork] center {dname} -> {views[dname]}", flush=True)
sc["probes"].append({"probe_id": "center", "eye": list(eye), "views": views})

# named frames — decision + close goal images
for nm, ep, yw in NAMED:
    r = shoot(stage, cp, a_rgb, a_dep, f"{SID}__{nm}", ep, yw)
    sc["named_frames"][nm] = r if r else {"empty": True}
    print(f"[sfork] {nm} -> {sc['named_frames'][nm]}", flush=True)

scan["scenes"].append(sc)
(HANDOFF / "sfork_scan_manifest.json").write_text(json.dumps(scan, indent=2))
print(f"[sfork] DONE -> {HANDOFF}", flush=True)
app.close()
