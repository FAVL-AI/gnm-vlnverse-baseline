"""Render candidate front-camera views inside the REAL Isaac 5.1 hospital.usd
(fail-closed on asset identity). Robot-height (0.35 m) front-facing cameras plus a
few clearly-separate higher context cameras. Saves raw uint8 arrays (.npy) + a
poses manifest; PNG conversion + montage happen post-run with the gnm_train PIL
(the isaac-env PIL crashes on PNG save).

These are TARGET-SCENE renders for the corrected deck / next hospital run — they
are NOT the original H6 training frames (H6 ran in the procedural --scene stage).
"""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 1280, "height": 720})

import math, json                       # noqa: E402
from pathlib import Path                # noqa: E402
import numpy as np                      # noqa: E402
import omni.usd                         # noqa: E402
import carb.settings                    # noqa: E402
import omni.replicator.core as rep      # noqa: E402
from pxr import UsdGeom, UsdLux, Gf      # noqa: E402

REPO = Path("/home/favl/robotics/gnm-vlnverse-baseline")
OUT = REPO / "assets/experiments/hospital_h2_collection_20260709/hospital_render_candidates"
OUT.mkdir(parents=True, exist_ok=True)
HOSPITAL_USD = ("https://omniverse-content-production.s3-us-west-2.amazonaws.com"
                "/Assets/Isaac/5.1/Isaac/Environments/Hospital/hospital.usd")
W, H = 1280, 720
ROBOT_H = 0.35

ctx = omni.usd.get_context(); ctx.new_stage(); app.update()
stage = ctx.get_stage()
world = UsdGeom.Xform.Define(stage, "/World"); stage.SetDefaultPrim(world.GetPrim())
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z); UsdGeom.SetStageMetersPerUnit(stage, 1.0)
UsdLux.DomeLight.Define(stage, "/World/DomeLight").CreateIntensityAttr(1000.0)

print(f"[hosp-render] referencing {HOSPITAL_USD}", flush=True)
env = stage.DefinePrim("/World/Hospital")
if not env.GetReferences().AddReference(HOSPITAL_USD):
    print("[hosp-render] ERROR: could not author hospital reference", flush=True)
    app.close(); raise SystemExit(3)
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
n_hosp = sum(1 for p in stage.Traverse() if str(p.GetPath()).startswith("/World/Hospital/"))
print(f"[hosp-render] hospital prims={n_hosp}", flush=True)
if n_hosp < 50:
    print("[hosp-render] ERROR: hospital did not populate; refusing to render.", flush=True)
    app.close(); raise SystemExit(4)

s = carb.settings.get_settings()
try:
    s.set("/app/viewport/grid/enabled", False)
except Exception:
    pass


def aim_at(cam, tgt):
    dx, dy, dz = (t - c for c, t in zip(cam, tgt))
    yaw = math.degrees(math.atan2(dy, dx)) - 90.0
    pitch = 90.0 - math.degrees(math.atan2(-dz, math.hypot(dx, dy)))
    return Gf.Vec3f(pitch, 0.0, yaw)


# robot-height front cams (eye z=0.35), aimed at furniture height (z~0.6) to keep
# hospital features in frame without raising the eye; + 2 higher CONTEXT cams.
Z, ZT = ROBOT_H, 0.6
CANDS = [
    ("r01", (0.0, 1.2, Z), (3.2, -1.6, ZT)), ("r02", (-1.0, 1.5, Z), (2.5, -1.5, ZT)),
    ("r03", (1.0, 1.0, Z), (3.5, -1.2, ZT)), ("r04", (-2.5, 0.5, Z), (3.0, 1.0, ZT)),
    ("r05", (-2.5, -0.5, Z), (3.0, -1.0, ZT)), ("r06", (-1.5, 0.0, Z), (3.5, 0.0, ZT)),
    ("r07", (0.5, -0.5, Z), (3.5, -2.5, ZT)), ("r08", (-2.0, 1.0, Z), (1.0, -1.0, ZT)),
    ("r09", (1.5, 1.2, Z), (1.5, -1.5, ZT)), ("r10", (-2.5, 1.5, Z), (2.0, -1.0, ZT)),
    ("r11", (0.0, -1.0, Z), (3.0, -3.0, ZT)), ("r12", (-1.0, -1.5, Z), (2.5, 0.5, ZT)),
    ("r13", (2.0, 1.0, Z), (4.0, -1.0, ZT)), ("r14", (-3.0, 0.0, Z), (2.0, 0.0, ZT)),
    ("r15", (0.0, 2.0, Z), (2.0, -1.0, ZT)), ("r16", (1.0, -0.5, Z), (4.0, -2.0, ZT)),
    ("ctx1", (-3.0, 2.0, 1.4), (1.0, -0.5, 0.4)), ("ctx2", (-3.0, -1.5, 1.5), (2.0, 0.5, 0.4)),
]

poses = []
for name, eye, tgt in CANDS:
    cp = f"/World/Cam_{name}"
    cam = UsdGeom.Camera.Define(stage, cp)
    cam.CreateFocalLengthAttr(18.0)
    cam.CreateClippingRangeAttr(Gf.Vec2f(0.02, 1000.0))
    UsdGeom.XformCommonAPI(cam).SetTranslate(Gf.Vec3d(*eye))
    UsdGeom.XformCommonAPI(cam).SetRotate(aim_at(eye, tgt))
    rp = rep.create.render_product(cp, (W, H))
    annot = rep.AnnotatorRegistry.get_annotator("rgb")
    try:
        annot.attach([rp])
    except Exception:
        annot.attach(rp)
    data = np.zeros((0,))
    for _ in range(12):
        try:
            rep.orchestrator.step(rt_subframes=16)
        except Exception:
            for _ in range(20):
                app.update()
        arr = np.asarray(annot.get_data())
        if arr.size and arr.ndim >= 2:
            data = arr; break
    try:
        annot.detach()
    except Exception:
        pass
    try:
        rp.destroy()
    except Exception:
        pass
    if data.size == 0 or data.ndim < 2:
        print(f"[hosp-render] {name}: EMPTY", flush=True); continue
    if data.dtype != np.uint8:
        data = (data * 255).clip(0, 255).astype(np.uint8)
    rgb = np.ascontiguousarray(data[..., :3])
    np.save(OUT / f"cand_{name}.npy", rgb)
    poses.append({"name": name, "eye": list(eye), "target": list(tgt),
                  "is_context": eye[2] > 1.0, "mean_luma": round(float(rgb.mean()), 1)})
    print(f"[hosp-render] {name}: {rgb.shape} luma={rgb.mean():.1f}", flush=True)

(OUT / "candidate_poses.json").write_text(json.dumps(
    {"asset_path": HOSPITAL_USD, "isaac_sim_version": "5.1.0.0",
     "resolution": [W, H], "robot_camera_height_m": ROBOT_H,
     "focal_length_mm": 18.0, "render_mode": str(s.get("/rtx/rendermode")),
     "hospital_prim_count": n_hosp, "synthetic": False, "candidates": poses}, indent=2))
print(f"[hosp-render] DONE {len(poses)} candidates -> {OUT}", flush=True)
app.close()
