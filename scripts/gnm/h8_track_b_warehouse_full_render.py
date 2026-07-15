"""H8-M Track B — bounded junction RENDER SCAN for candidate scenes (validation-only).

Scans two reachable Isaac stock environments for a render-valid, depth-open fork/T-junction that
could host Track-B angular branch-choice:
  * office_isaac      -> .../Environments/Office/office.usd
  * warehouse_simple  -> .../Environments/Simple_Warehouse/warehouse.usd

No prior map exists for these scenes, so this is a BOUNDED, geometry-grounded scan: compute the
scene's world bounding box, place an interior grid of probe points, and at each point render FOUR
cardinal directional views (E/N/W/S) with RGB + distance_to_image_plane depth. A point is a
junction only if >=2 divergent (perpendicular) directions are actually depth-open (>= 3 m) — the
openness test is applied in the gnm_train analysis stage; here we only capture pixels + depth.

NO robot spawn, NO drive, NO rosbag, NO trajectory, NO training, NO collection. Raw .npy -> handoff;
classification / contact-sheets / similarity matrix are produced by the analyze stage (isaac-env
PIL cannot save PNG). `CL_BOUND_XY` (the hospital drive watchdog) is unrelated to this free-camera
render and is NOT touched.

Run: ~/miniforge3/envs/isaac/bin/python -u scripts/gnm/h8_track_b_render_scan_render.py
"""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 640, "height": 480})

import math, json, os, sys                    # noqa: E402
from pathlib import Path                       # noqa: E402
import numpy as np                             # noqa: E402
import omni.usd                                # noqa: E402
import carb.settings                           # noqa: E402
import omni.replicator.core as rep             # noqa: E402
from pxr import Usd, UsdGeom, UsdLux, Gf        # noqa: E402

HANDOFF = Path(os.environ.get("H8_TRACKB_HANDOFF", "/tmp/h8_wfull_npy"))
HANDOFF.mkdir(parents=True, exist_ok=True)
S3 = ("https://omniverse-content-production.s3-us-west-2.amazonaws.com"
      "/Assets/Isaac/5.1/Isaac/Environments")
SCENES = [
    ("warehouse_full", f"{S3}/Simple_Warehouse/full_warehouse.usd"),
]
W, H = 640, 480
Z_CAM = 0.47          # robot-eye height (0.35 base + 0.12 raise), level horizon — parity w/ hospital
AIM = 2.0             # look-ahead for the level target point
GRID = (5, 5)         # interior probe grid (nx, ny) — denser for a larger, shelved warehouse
MARGIN_FRAC = 0.16    # shrink the scene bbox inward before gridding (avoid perimeter walls)
Z_FLOOR_MAX = 3.0     # ignore geometry above this when estimating the navigable footprint
DIRS = [("E", 0.0), ("N", 90.0), ("W", 180.0), ("S", 270.0)]


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
        if not all(math.isfinite(v) for v in bb) or (bb[3] - bb[0]) < 1 or (bb[4] - bb[1]) < 1:
            return None
        return bb
    except Exception as e:
        print(f"[trackb] bbox error: {e}", flush=True)
        return None


def interior_footprint(stage, root, cap_half=30.0):
    """Robust navigable footprint (x,y) from actual mesh positions, ignoring outlier skybox/
    backdrop/ground prims that blow up the raw world bbox (e.g. office.usd spans ~1000 m). Uses
    the 4th-96th percentile of mesh bbox centres, capped to +/-cap_half around the robust centre."""
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(),
                              [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
    meshes = [p for p in stage.Traverse()
              if str(p.GetPath()).startswith(root + "/") and p.IsA(UsdGeom.Mesh)]
    if not meshes:
        return None
    step = max(1, len(meshes) // 2000)
    xs, ys = [], []
    for p in meshes[::step]:
        try:
            r = cache.ComputeWorldBound(p).ComputeAlignedRange()
            mn, mx = r.GetMin(), r.GetMax()
            cx, cy = (mn[0] + mx[0]) / 2.0, (mn[1] + mx[1]) / 2.0
            if math.isfinite(cx) and math.isfinite(cy):
                xs.append(cx); ys.append(cy)
        except Exception:
            continue
    if len(xs) < 8:
        return None
    xs, ys = np.array(xs), np.array(ys)
    x0, x1 = np.percentile(xs, [4, 96]); y0, y1 = np.percentile(ys, [4, 96])
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    hx = min(max((x1 - x0) / 2.0, 3.0), cap_half)
    hy = min(max((y1 - y0) / 2.0, 3.0), cap_half)
    return [round(cx - hx, 3), round(cy - hy, 3), round(cx + hx, 3), round(cy + hy, 3)]


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
            "median_depth_central_m": (central_median_depth(dep) if dep is not None else None)}


scan = {"asset_root": S3, "isaac_sim_version": "5.1.0.0", "resolution": [W, H],
        "camera_height_m": Z_CAM, "grid": list(GRID), "margin_frac": MARGIN_FRAC,
        "directions": [d for d, _ in DIRS], "branch_open_depth_note": ">=3 m tested in analyze",
        "free_camera_no_robot_body": True, "scenes": []}

for sid, usd in SCENES:
    print(f"[trackb] === scene {sid}: {usd}", flush=True)
    stage, ctx, root, ok, n = load_scene(usd)
    print(f"[trackb] {sid}: ref_authored={ok} prims={n}", flush=True)
    cp, rp, a_rgb, a_dep = make_cam(stage)
    bb = world_bbox(stage, root)
    fp = interior_footprint(stage, root)   # robust navigable footprint (skybox-outlier-safe)
    region = fp if fp is not None else (
        [bb[0], bb[1], bb[3], bb[4]] if bb is not None else None)
    # scene-load check: a center render must be non-black
    if region is not None:
        cx, cy = (region[0] + region[2]) / 2.0, (region[1] + region[3]) / 2.0
    else:
        cx, cy = 0.0, 0.0
    probe0 = shoot(stage, cp, a_rgb, a_dep, f"{sid}__loadprobe", (cx, cy, Z_CAM), 0.0)
    # scene-load gate: the SCENE loaded (reference authored + populated). Do NOT gate on the single
    # centre probe — it may land inside a wall (black); per-probe validity is handled in analysis.
    load_ok = bool(ok and n >= 50 and region is not None)
    print(f"[trackb] {sid}: bbox={bb} footprint={fp} load_ok={load_ok} loadprobe={probe0}", flush=True)

    sc = {"scene_id": sid, "asset_path": usd, "ref_authored": ok, "prim_count": n,
          "world_bbox": bb, "interior_footprint": fp, "grid_region": region,
          "scene_load_ok": load_ok, "load_probe": probe0, "probes": []}
    if not load_ok or region is None:
        sc["aborted_reason"] = "scene did not load / no usable footprint"
        scan["scenes"].append(sc); continue

    mx0 = region[0] + MARGIN_FRAC * (region[2] - region[0])
    mx1 = region[2] - MARGIN_FRAC * (region[2] - region[0])
    my0 = region[1] + MARGIN_FRAC * (region[3] - region[1])
    my1 = region[3] - MARGIN_FRAC * (region[3] - region[1])
    nx, ny = GRID
    xs = [mx0 + (mx1 - mx0) * (i + 0.5) / nx for i in range(nx)]
    ys = [my0 + (my1 - my0) * (j + 0.5) / ny for j in range(ny)]
    for j, yv in enumerate(ys):
        for i, xv in enumerate(xs):
            pid = f"p{i}{j}"
            eye = (round(xv, 3), round(yv, 3), Z_CAM)
            views = {}
            for dname, dyaw in DIRS:
                r = shoot(stage, cp, a_rgb, a_dep, f"{sid}__{pid}__{dname}", eye, dyaw)
                views[dname] = r if r else {"empty": True}
            sc["probes"].append({"probe_id": pid, "eye": list(eye), "views": views})
            opens = [d for d, v in views.items()
                     if v and not v.get("empty") and (v.get("median_depth_central_m") or 0) >= 3.0]
            print(f"[trackb] {sid} {pid} @({eye[0]},{eye[1]}) open_dirs={opens}", flush=True)
    scan["scenes"].append(sc)

(HANDOFF / "trackb_scan_manifest.json").write_text(json.dumps(scan, indent=2))
print(f"[trackb] DONE -> {HANDOFF}", flush=True)
app.close()
