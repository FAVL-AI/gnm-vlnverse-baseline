"""H8-M — bounded real-junction RENDER SCAN in the verified hospital.usd (validation-only).

Renders candidate T-junction/fork probes inside the safe +/-6 m envelope to determine whether
any render-valid junction exists (goal A and goal B along divergent branches that are actually
open, not walls/void). For each candidate: decision frame (o_d, along approach yaw) + goalA +
goalB (each 2 m along its branch direction). Scene gate fail-closed, raised (~0.12) mount, level
horizon. NO robot spawn, NO drive, NO rosbag, NO trajectory, NO training. Raw .npy -> handoff;
classification/contact-sheets in the gnm_train analysis stage.

Candidates are grounded in the KNOWN reachable geometry (H8 drivable corridor y~-0.2,
x in [-3.4,3.5], reception near origin, corridor ends) — a BOUNDED scan, not an exhaustive
floor-plan search. Run: ~/miniforge3/envs/isaac/bin/python -u scripts/gnm/h8m_junction_scan_render.py
"""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 640, "height": 480})

import math, json, sys, os                 # noqa: E402
from pathlib import Path                    # noqa: E402
import numpy as np                          # noqa: E402
import omni.usd                             # noqa: E402
import carb.settings                        # noqa: E402
import omni.replicator.core as rep          # noqa: E402
from pxr import UsdGeom, UsdLux, Gf          # noqa: E402

REPO = Path("/home/favl/robotics/gnm-vlnverse-baseline")
sys.path.insert(0, str(REPO / "scripts/gnm"))
from hospital_scene_identity_gate import verify_hospital_scene   # noqa: E402

HANDOFF = Path(os.environ.get("H8M_JSCAN_HANDOFF", "/tmp/h8m_junction_npy"))
HANDOFF.mkdir(parents=True, exist_ok=True)
HOSPITAL_USD = ("https://omniverse-content-production.s3-us-west-2.amazonaws.com"
                "/Assets/Isaac/5.1/Isaac/Environments/Hospital/hospital.usd")
HOSP_ROOT = "/World/Hospital"
W, H = 640, 480
Z_CAM = 0.47
AIM = 2.0
BR = 2.0   # branch reach (m) from the junction center to each goal

# ── candidate junctions: (id, o_d[x,y], approach_yaw_rad, branchA_deg, branchB_deg, kind) ──
# branch angles are RELATIVE to the approach heading. Goal = o_d + BR*(unit at yaw+branch).
CANDS = [
    ("jc_corr_wmid_T", [-2.5, -0.2], 0.0, 90, -90, "corridor T (+/-y)"),
    ("jc_corr_mid_T",  [-1.0, -0.2], 0.0, 90, -90, "corridor T (+/-y)"),
    ("jc_corr_c_T",    [0.5, -0.2],  0.0, 90, -90, "corridor T (+/-y)"),
    ("jc_corr_e_T",    [2.0, -0.2],  0.0, 90, -90, "corridor T (+/-y)"),
    ("jc_recep_fork",  [-0.5, -0.2], 0.0, 45, -45, "reception fork (+/-45)"),
    ("jc_corr_end_e",  [3.0, -0.2],  0.0, 40, -40, "east corridor-end fan"),
    ("jc_corr_end_w",  [-3.0, -0.2], math.pi, 40, -40, "west corridor-end fan"),
    ("jc_recep_cross", [0.0, -1.5],  math.pi / 2, 60, -60, "reception cross (perp approach)"),
]


ctx = omni.usd.get_context(); ctx.new_stage(); app.update()
stage = ctx.get_stage()
world = UsdGeom.Xform.Define(stage, "/World"); stage.SetDefaultPrim(world.GetPrim())
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z); UsdGeom.SetStageMetersPerUnit(stage, 1.0)
UsdLux.DomeLight.Define(stage, "/World/DomeLight").CreateIntensityAttr(1000.0)
print(f"[jscan] referencing {HOSPITAL_USD}", flush=True)
env = stage.DefinePrim(HOSP_ROOT)
if not env.GetReferences().AddReference(HOSPITAL_USD):
    print("[jscan] ERROR: could not author hospital reference", flush=True)
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
print(f"[jscan] hospital prims={n_hosp}", flush=True)
carb.settings.get_settings().set("/app/viewport/grid/enabled", False)


def aim_at(cam, tgt):
    dx, dy, dz = (t - c for c, t in zip(cam, tgt))
    yaw = math.degrees(math.atan2(dy, dx)) - 90.0
    pitch = 90.0 - math.degrees(math.atan2(-dz, math.hypot(dx, dy)))
    return Gf.Vec3f(pitch, 0.0, yaw)


def _central_median_depth(depth):
    """Median depth (m) over the central region — an openness proxy: a wall in front gives a
    small value; an open corridor extending ahead gives a large value."""
    d = np.asarray(depth, dtype=np.float32)
    if d.ndim < 2 or d.size == 0:
        return None
    h, w = d.shape[:2]
    c = d[int(h * 0.3):int(h * 0.7), int(w * 0.3):int(w * 0.7)].ravel()
    c = c[np.isfinite(c)]
    c = c[(c > 0.05) & (c < 500.0)]   # drop void/sky/degenerate
    return round(float(np.median(c)), 3) if c.size else None


def render_view(name, eye, tgt):
    cp = f"/World/JCam_{name}"
    cam = UsdGeom.Camera.Define(stage, cp)
    cam.CreateFocalLengthAttr(18.0)
    cam.CreateClippingRangeAttr(Gf.Vec2f(0.02, 1000.0))
    UsdGeom.XformCommonAPI(cam).SetTranslate(Gf.Vec3d(*eye))
    UsdGeom.XformCommonAPI(cam).SetRotate(aim_at(eye, tgt))
    rp = rep.create.render_product(cp, (W, H))
    a_rgb = rep.AnnotatorRegistry.get_annotator("rgb")
    a_dep = rep.AnnotatorRegistry.get_annotator("distance_to_image_plane")
    for a in (a_rgb, a_dep):
        try:
            a.attach([rp])
        except Exception:
            a.attach(rp)
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
    for a in (a_rgb, a_dep):
        try:
            a.detach()
        except Exception:
            pass
    try:
        rp.destroy()
    except Exception:
        pass
    if data.size == 0 or data.ndim < 2:
        return None, cp, None
    if data.dtype != np.uint8:
        data = (data * 255).clip(0, 255).astype(np.uint8)
    rgb = np.ascontiguousarray(data[..., :3])
    np.save(HANDOFF / f"{name}.npy", rgb)
    return rgb, cp, (_central_median_depth(dep) if dep is not None else None)


def blackfrac(rgb):
    lower = rgb[int(H * 2 / 3):, :, :]
    return float((lower.max(axis=2) < 12).mean())


# scene gate on a first render
gate_rgb, gate_cam, _ = render_view("scene_gate_probe", (0.0, 0.0, Z_CAM), (AIM, 0.0, Z_CAM))
gate = verify_hospital_scene(stage, scene_mode="hospital", hospital_root=HOSP_ROOT,
                             front_cam_path=gate_cam, resolution=[W, H], front_rgb=gate_rgb)
print(f"[jscan] scene_gate pass={gate['pass']} reasons={gate.get('reasons')}", flush=True)
if not gate["pass"]:
    (HANDOFF / "jscan_manifest.json").write_text(json.dumps({"scene_gate": gate, "aborted": True}, indent=2))
    app.close(); raise SystemExit(5)


def unit(a):
    return (math.cos(a), math.sin(a))


cands = []
for cid, od, yaw, ba, bb, kind in CANDS:
    within = all(abs(v) <= 6.0 for v in od)
    gA = [od[0] + BR * unit(yaw + math.radians(ba))[0], od[1] + BR * unit(yaw + math.radians(ba))[1]]
    gB = [od[0] + BR * unit(yaw + math.radians(bb))[0], od[1] + BR * unit(yaw + math.radians(bb))[1]]
    within = within and all(abs(v) <= 6.0 for v in gA + gB)
    entry = {"cand_id": cid, "kind": kind, "o_d": od, "approach_yaw_deg": round(math.degrees(yaw), 1),
             "goalA": gA, "goalB": gB, "branchA_rel_deg": ba, "branchB_rel_deg": bb,
             "expected_action_angle_sep_deg": abs(ba - bb), "within_envelope": within, "views": {}}
    if not within:
        entry["classification_prelim"] = "OUT_OF_ENVELOPE"
        cands.append(entry); continue
    # decision: at o_d along approach yaw; goals: at goal, facing o_d->goal bearing
    specs = {"decision": (tuple(od) + (Z_CAM,),
                          (od[0] + AIM * math.cos(yaw), od[1] + AIM * math.sin(yaw), Z_CAM))}
    for role, g in (("goalA", gA), ("goalB", gB)):
        br = math.atan2(g[1] - od[1], g[0] - od[0])
        specs[role] = ((g[0], g[1], Z_CAM), (g[0] + AIM * math.cos(br), g[1] + AIM * math.sin(br), Z_CAM))
    for role, (eye, tgt) in specs.items():
        rgb, _, depth_med = render_view(f"{cid}__{role}", eye, tgt)
        if rgb is None:
            entry["views"][role] = {"empty": True}
        else:
            entry["views"][role] = {"mean_luma": round(float(rgb.mean()), 1),
                                    "lower_frame_black_frac": round(blackfrac(rgb), 4),
                                    "median_depth_central_m": depth_med}
    print(f"[jscan] {cid}: " + ", ".join(
        f"{r}=L{v.get('mean_luma','X')}/D{v.get('median_depth_central_m','X')}"
        for r, v in entry["views"].items()), flush=True)
    cands.append(entry)

(HANDOFF / "jscan_manifest.json").write_text(json.dumps({
    "asset_path": HOSPITAL_USD, "isaac_sim_version": "5.1.0.0", "resolution": [W, H],
    "camera_height_m": Z_CAM, "camera_raise_note": "~0.12 m above 0.35 m base; level horizon",
    "branch_reach_m": BR, "free_camera_no_robot_body": True, "hospital_prim_count": n_hosp,
    "scene_gate": gate, "n_candidates": len(cands), "candidates": cands}, indent=2))
print(f"[jscan] DONE {len(cands)} candidates -> {HANDOFF}", flush=True)
app.close()
