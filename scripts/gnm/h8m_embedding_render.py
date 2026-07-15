"""H8-M Step B — validation-only RENDER of candidate views in the verified hospital.usd.

Renders, for each in-envelope Step-A zone, three static free-camera views:
  decision frame (o_d, along approach yaw), goal A, goal B (each at the goal position, facing
  the o_d->goal bearing). Raised mount height (~0.12 above a 0.35 m base = 0.47 m), level horizon.
Fail-closed on the hospital scene-identity gate. NO robot spawn, NO drive, NO rosbag, NO
trajectory, NO training. Saves raw uint8 arrays (.npy) + a poses manifest to a scratchpad handoff
dir; PNG/contact-sheet/embedding analysis happens in the gnm_train stage (isaac-env PIL crashes
on PNG save). Run with: ~/miniforge3/envs/isaac/bin/python -u scripts/gnm/h8m_embedding_render.py
"""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 640, "height": 480})

import math, json, sys, os                # noqa: E402
from pathlib import Path                   # noqa: E402
import numpy as np                         # noqa: E402
import omni.usd                            # noqa: E402
import carb.settings                       # noqa: E402
import omni.replicator.core as rep         # noqa: E402
from pxr import UsdGeom, UsdLux, Gf         # noqa: E402

REPO = Path("/home/favl/robotics/gnm-vlnverse-baseline")
sys.path.insert(0, str(REPO / "scripts/gnm"))
from hospital_scene_identity_gate import verify_hospital_scene   # noqa: E402

ZONES_JSON = REPO / "assets/experiments/hospital_h8_m_route_zone_design/h8m_zone_candidates.json"
HANDOFF = Path(os.environ.get("H8M_RENDER_HANDOFF", "/tmp/h8m_render_npy"))  # raw .npy handoff (not committed)
HANDOFF.mkdir(parents=True, exist_ok=True)
HOSPITAL_USD = ("https://omniverse-content-production.s3-us-west-2.amazonaws.com"
                "/Assets/Isaac/5.1/Isaac/Environments/Hospital/hospital.usd")
HOSP_ROOT = "/World/Hospital"
W, H = 640, 480
Z_CAM = 0.47   # raised mount: ~0.35 m base eye + 0.12 m raise; level horizon
AIM = 2.0      # look-ahead distance for the level target point

# ── boot + load hospital.usd (fail-closed) ───────────────────────────────────
ctx = omni.usd.get_context(); ctx.new_stage(); app.update()
stage = ctx.get_stage()
world = UsdGeom.Xform.Define(stage, "/World"); stage.SetDefaultPrim(world.GetPrim())
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z); UsdGeom.SetStageMetersPerUnit(stage, 1.0)
UsdLux.DomeLight.Define(stage, "/World/DomeLight").CreateIntensityAttr(1000.0)  # no-black fix
print(f"[h8m-render] referencing {HOSPITAL_USD}", flush=True)
env = stage.DefinePrim(HOSP_ROOT)
if not env.GetReferences().AddReference(HOSPITAL_USD):
    print("[h8m-render] ERROR: could not author hospital reference", flush=True)
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
n_hosp = sum(1 for p in stage.Traverse() if str(p.GetPath()).startswith(HOSP_ROOT + "/"))
print(f"[h8m-render] hospital prims={n_hosp}", flush=True)
carb.settings.get_settings().set("/app/viewport/grid/enabled", False)


def aim_at(cam, tgt):
    dx, dy, dz = (t - c for c, t in zip(cam, tgt))
    yaw = math.degrees(math.atan2(dy, dx)) - 90.0
    pitch = 90.0 - math.degrees(math.atan2(-dz, math.hypot(dx, dy)))
    return Gf.Vec3f(pitch, 0.0, yaw)


def render_view(name, eye, tgt):
    cp = f"/World/Cam_{name}"
    cam = UsdGeom.Camera.Define(stage, cp)
    cam.CreateFocalLengthAttr(18.0)
    cam.CreateClippingRangeAttr(Gf.Vec2f(0.02, 1000.0))  # 2 cm near plane, no <1 m culling
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
        annot.detach(); rp.destroy()
    except Exception:
        pass
    if data.size == 0 or data.ndim < 2:
        print(f"[h8m-render] {name}: EMPTY", flush=True); return None, cp
    if data.dtype != np.uint8:
        data = (data * 255).clip(0, 255).astype(np.uint8)
    rgb = np.ascontiguousarray(data[..., :3])
    np.save(HANDOFF / f"{name}.npy", rgb)
    return rgb, cp


# ── scene gate (fail-closed) on a first rendered view ────────────────────────
gate_rgb, gate_cam = render_view("scene_gate_probe", (0.0, 0.0, Z_CAM), (AIM, 0.0, Z_CAM))
gate = verify_hospital_scene(stage, scene_mode="hospital", hospital_root=HOSP_ROOT,
                             front_cam_path=gate_cam, resolution=[W, H], front_rgb=gate_rgb)
print(f"[h8m-render] scene_gate pass={gate['pass']} reasons={gate.get('reasons')}", flush=True)
if not gate["pass"]:
    print("[h8m-render] SCENE GATE FAILED — refusing to render candidates.", flush=True)
    (HANDOFF / "render_manifest.json").write_text(json.dumps(
        {"scene_gate": gate, "aborted": True}, indent=2))
    app.close(); raise SystemExit(5)

# ── build view list from committed Step-A zones ──────────────────────────────
zones = json.loads(ZONES_JSON.read_text())["zones"]
views = []   # (view_id, zone_id, role, eye, tgt, heading_deg)
for z in zones:
    if not z.get("o_d") or not z.get("within_envelope", True):
        continue
    od = z["o_d"]; yaw = z["spawn"][2] if z.get("spawn") else 0.0
    # decision frame: at o_d, along approach yaw
    tgt = (od[0] + AIM * math.cos(yaw), od[1] + AIM * math.sin(yaw), Z_CAM)
    views.append((f"{z['zone_id']}__decision", z["zone_id"], "decision",
                  (od[0], od[1], Z_CAM), tgt, math.degrees(yaw)))
    # goals: at the goal, facing the o_d->goal bearing
    for role, g in (("goalA", z["goalA"]), ("goalB", z["goalB"])):
        br = math.atan2(g[1] - od[1], g[0] - od[0])
        tgt = (g[0] + AIM * math.cos(br), g[1] + AIM * math.sin(br), Z_CAM)
        views.append((f"{z['zone_id']}__{role}", z["zone_id"], role,
                      (g[0], g[1], Z_CAM), tgt, math.degrees(br)))

meta = []
for vid, zid, role, eye, tgt, hdg in views:
    rgb, cp = render_view(vid, eye, tgt)
    if rgb is None:
        meta.append({"view_id": vid, "zone_id": zid, "role": role, "eye": list(eye),
                     "target": list(tgt), "heading_deg": round(hdg, 1), "empty": True})
        continue
    # lower-frame black fraction (bottom third) — occlusion proxy (free cam: geometry only)
    lower = rgb[int(H * 2 / 3):, :, :]
    black = float((lower.max(axis=2) < 12).mean())
    meta.append({"view_id": vid, "zone_id": zid, "role": role, "eye": list(eye),
                 "target": list(tgt), "heading_deg": round(hdg, 1),
                 "mean_luma": round(float(rgb.mean()), 1),
                 "lower_frame_black_frac": round(black, 4), "empty": False})
    print(f"[h8m-render] {vid}: luma={rgb.mean():.1f} lower_black={black:.3f}", flush=True)

(HANDOFF / "render_manifest.json").write_text(json.dumps({
    "asset_path": HOSPITAL_USD, "isaac_sim_version": "5.1.0.0", "resolution": [W, H],
    "camera_height_m": Z_CAM, "camera_raise_note": "~0.12 m above 0.35 m base; level horizon",
    "focal_length_mm": 18.0, "free_camera_no_robot_body": True,
    "occlusion_note": "free camera has NO robot chassis; lower_frame_black reflects scene "
                      "geometry only. Chassis lower-frame occlusion is a Step-C drive check.",
    "hospital_prim_count": n_hosp, "scene_gate": gate, "synthetic": False,
    "n_views": len(meta), "views": meta}, indent=2))
print(f"[h8m-render] DONE {len(meta)} views -> {HANDOFF}", flush=True)
app.close()
