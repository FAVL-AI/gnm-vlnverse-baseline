"""Camera-view comparison for H7: load the REAL hospital.usd + the Yahboom robot
(so the robot-body occlusion is reproduced), pose the robot at start/mid/goal of 2
representative routes, and render several front-camera variants (current mount vs
upward pitch vs raised mount). Saves .npy per (route,pose,variant); PNG + contact
sheets + black% metrics built post-run. NO driving, NO recording, NO training.
"""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 640, "height": 480})

import math, json                              # noqa: E402
from pathlib import Path                        # noqa: E402
import numpy as np                              # noqa: E402
import omni.usd                                 # noqa: E402
import omni.replicator.core as rep             # noqa: E402
from pxr import UsdGeom, UsdLux, Gf             # noqa: E402

REPO = Path("/home/favl/robotics/gnm-vlnverse-baseline")
import sys                                      # noqa: E402
sys.path.insert(0, str(REPO / "scripts/gnm"))
from hospital_scene_identity_gate import verify_hospital_scene, HOSPITAL_USD, HOSPITAL_ROOT  # noqa: E402
ROBOT_USD = REPO / "assets/robots/yahboom_m3_pro/yahboom_m3pro.usd"
OUT = REPO / "assets/experiments/hospital_h7_collection/camera_review_npy"
OUT.mkdir(parents=True, exist_ok=True)
W, H = 640, 480

# camera variants authored under camera_link (same convention as the bringup:
# SetRotate(90,0,-90) = level forward). pitch via X-euler; raise via local translate.
VARIANTS = {
    "current":  {"rot": (90.0, 0.0, -90.0), "tr": (0.0, 0.0, 0.0)},
    "pitch_up": {"rot": (75.0, 0.0, -90.0), "tr": (0.0, 0.0, 0.0)},
    "pitch_dn": {"rot": (105.0, 0.0, -90.0), "tr": (0.0, 0.0, 0.0)},
    "raise_z":  {"rot": (90.0, 0.0, -90.0), "tr": (0.0, 0.0, 0.12)},
    "raise_y":  {"rot": (90.0, 0.0, -90.0), "tr": (0.0, 0.12, 0.0)},
}
ROUTES = {
    "reception_01": [(-2.6, -0.8), (-0.8, -0.2), (1.2, 0.0)],
    "turn_01":      [(-1.0, 0.8), (0.2, 0.8), (0.2, -0.2)],
}


def poses(wps):
    out = []
    for i, (fr) in enumerate(("start", "mid", "goal")):
        p = wps[i]
        j = min(i + 1, len(wps) - 1)
        a = wps[i] if i < len(wps) - 1 else wps[i - 1]
        b = wps[i + 1] if i < len(wps) - 1 else wps[i]
        yaw = math.atan2(b[1] - a[1], b[0] - a[0])
        out.append((fr, p[0], p[1], yaw))
    return out


ctx = omni.usd.get_context(); ctx.new_stage(); app.update()
stage = ctx.get_stage()
UsdGeom.Xform.Define(stage, "/World"); stage.SetDefaultPrim(stage.GetPrimAtPath("/World"))
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z); UsdGeom.SetStageMetersPerUnit(stage, 1.0)
UsdLux.DomeLight.Define(stage, "/World/DomeLight").CreateIntensityAttr(1000.0)

prim = stage.DefinePrim(HOSPITAL_ROOT)
prim.GetReferences().AddReference(HOSPITAL_USD)
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
gate = verify_hospital_scene(stage, scene_mode="hospital")
print(f"[cam-review] gate PASS={gate['pass']} prims={gate['observed']['hospital_prim_count']}", flush=True)
if not gate["pass"]:
    app.close(); raise SystemExit(5)

ROBOT = "/World/M3Pro"
rob = stage.DefinePrim(ROBOT)
rob.GetReferences().AddReference(str(ROBOT_USD))
for _ in range(120):
    app.update()

# author camera variants under camera_link
CAMB = f"{ROBOT}/camera_link"
cams = {}
for name, v in VARIANTS.items():
    cp = f"{CAMB}/rev_{name}"
    c = UsdGeom.Camera.Define(stage, cp)
    c.CreateFocalLengthAttr(18.0)
    c.CreateClippingRangeAttr(Gf.Vec2f(0.02, 10000.0))
    api = UsdGeom.XformCommonAPI(c)
    api.SetTranslate(Gf.Vec3d(*v["tr"]))
    api.SetRotate(Gf.Vec3f(*v["rot"]))
    rp = rep.create.render_product(cp, (W, H))
    annot = rep.AnnotatorRegistry.get_annotator("rgb")
    try:
        annot.attach([rp])
    except Exception:
        annot.attach(rp)
    cams[name] = annot

manifest = {"asset": HOSPITAL_USD, "variants": {k: v for k, v in VARIANTS.items()},
            "routes": list(ROUTES), "renders": []}
for rname, wps in ROUTES.items():
    for fr, x, y, yaw in poses(wps):
        UsdGeom.XformCommonAPI(UsdGeom.Xformable(rob)).SetTranslate(Gf.Vec3d(x, y, 0.005))
        UsdGeom.XformCommonAPI(UsdGeom.Xformable(rob)).SetRotate(Gf.Vec3f(0, 0, math.degrees(yaw)))
        for _ in range(15):
            app.update()
        for name, annot in cams.items():
            data = np.zeros((0,))
            for _ in range(10):
                try:
                    rep.orchestrator.step(rt_subframes=16)
                except Exception:
                    for _ in range(20):
                        app.update()
                arr = np.asarray(annot.get_data())
                if arr.size and arr.ndim >= 2:
                    data = arr; break
            if data.size == 0:
                print(f"[cam-review] {rname}/{fr}/{name}: EMPTY", flush=True); continue
            if data.dtype != np.uint8:
                data = (data * 255).clip(0, 255).astype(np.uint8)
            rgb = np.ascontiguousarray(data[..., :3])
            fn = f"{rname}__{fr}__{name}.npy"
            np.save(OUT / fn, rgb)
            manifest["renders"].append({"route": rname, "frame": fr, "variant": name,
                                        "file": fn, "mean_luma": round(float(rgb.mean()), 1)})
        print(f"[cam-review] {rname}/{fr}: rendered {len(cams)} variants", flush=True)

(OUT / "camera_review_manifest.json").write_text(json.dumps(manifest, indent=2))
print(f"[cam-review] DONE {len(manifest['renders'])} renders -> {OUT}", flush=True)
app.close()
