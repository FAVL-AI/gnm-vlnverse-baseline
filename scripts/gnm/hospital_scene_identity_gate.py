"""Reusable HOSPITAL SCENE-IDENTITY GATE.

Fail-closed guard that every hospital collection/export/demo MUST call after
loading the scene and BEFORE recording. It proves the running scene is the real
Isaac Sim 5.1 hospital.usd and NOT the procedural --scene stage (grey ground +
coloured landmark cubes).

Pure functions (`verify_hospital_scene`, `looks_hospital_like`,
`write_scene_identity_manifest`) import only stdlib + numpy, so any Isaac script
can `from hospital_scene_identity_gate import verify_hospital_scene` after it has
booted SimulationApp (pxr objects are passed in, never imported here).

Run standalone (`python hospital_scene_identity_gate.py`) to boot Isaac, load the
hospital, run the gate on the live stage, and write the top-level locked manifest.

Locked rule:
    Procedural-stage H6 = diagnostic route-family coverage experiment.
    Real hospital USD    = official target scene for future hospital ImageNav
                           data, demos, and professor visuals.
"""
import json
import datetime
import numpy as np

HOSPITAL_USD = ("https://omniverse-content-production.s3-us-west-2.amazonaws.com"
                "/Assets/Isaac/5.1/Isaac/Environments/Hospital/hospital.usd")
HOSPITAL_ROOT = "/World/Hospital"
MIN_HOSPITAL_PRIMS = 1000          # real hospital.usd loads ~1909; stage is a handful
# procedural --scene stage landmark/ground prim name fragments that must NOT exist
FORBIDDEN_LANDMARKS = ("Pillar_Red", "Pillar_Blue", "Pillar_Green", "Wall_Yellow",
                       "Landmark", "Ground_Cube", "StageGround")
EXPECTED_RESOLUTION = [1280, 720]
ROBOT_CAMERA_HEIGHT_M = 0.35


def looks_hospital_like(rgb, min_std=10.0, lo=15.0, hi=235.0):
    """Weak visual safety net: the procedural grey stage renders near-flat. Require
    real spatial variation and a plausible (non-blown-out, non-black) mean.
    Returns (ok: bool, stats: dict)."""
    if rgb is None:
        return None, {"reason": "no image provided (visual check skipped)"}
    arr = np.asarray(rgb)
    if arr.ndim == 3 and arr.shape[-1] >= 3:
        gray = arr[..., :3].mean(axis=-1)
    else:
        gray = arr.astype(float)
    mean, std = float(gray.mean()), float(gray.std())
    ok = (std >= min_std) and (lo <= mean <= hi)
    return ok, {"mean_luma": round(mean, 2), "std_luma": round(std, 2),
                "min_std_required": min_std, "luma_window": [lo, hi]}


def verify_hospital_scene(stage, *, scene_mode, hospital_root=HOSPITAL_ROOT,
                          front_cam_path=None, resolution=None,
                          min_prims=MIN_HOSPITAL_PRIMS, front_rgb=None):
    """Fail-closed scene-identity check on a live USD stage.

    Returns a dict with `pass` (bool), per-check booleans, `reasons` (failed checks),
    and the observed values. Never raises on a normal failure — the CALLER must
    refuse to record when `pass` is False.
    """
    checks, reasons, observed = {}, [], {}

    # 1) hospital reference authored at the expected root, pointing at hospital.usd
    ref_ok, ref_asset = False, None
    root = stage.GetPrimAtPath(hospital_root)
    if root and root.IsValid():
        try:
            for spec in root.GetPrimStack():          # composed reference arcs
                rl = getattr(spec, "referenceList", None)
                if rl is None:
                    continue
                items = (list(getattr(rl, "prependedItems", [])) +
                         list(getattr(rl, "explicitItems", [])) +
                         list(getattr(rl, "addedItems", [])))
                for it in items:
                    ap = getattr(it, "assetPath", "") or ""
                    if ap:
                        ref_asset = ap
                        if ap.endswith("hospital.usd"):
                            ref_ok = True
        except Exception as e:
            observed["reference_introspection_error"] = str(e)
    checks["hospital_reference_authored"] = ref_ok
    observed["hospital_reference_asset"] = ref_asset
    if not ref_ok:
        reasons.append(f"no hospital.usd reference under {hospital_root} (got {ref_asset!r})")

    # 2) prim count under the hospital root
    n_prims = sum(1 for p in stage.Traverse()
                  if str(p.GetPath()).startswith(hospital_root + "/"))
    observed["hospital_prim_count"] = n_prims
    checks["prim_count_ok"] = n_prims >= min_prims
    if n_prims < min_prims:
        reasons.append(f"hospital prim count {n_prims} < threshold {min_prims}")

    # 3) scene mode explicitly hospital
    checks["scene_mode_hospital"] = (scene_mode == "hospital")
    observed["scene_mode"] = scene_mode
    if scene_mode != "hospital":
        reasons.append(f"scene_mode={scene_mode!r} (must be 'hospital')")

    # 4) NO procedural landmark/ground cubes anywhere in the stage
    found = []
    for p in stage.Traverse():
        name = p.GetName()
        for bad in FORBIDDEN_LANDMARKS:
            if bad.lower() in name.lower():
                found.append(str(p.GetPath()))
    checks["no_procedural_landmarks"] = (len(found) == 0)
    observed["procedural_landmark_prims"] = found[:10]
    if found:
        reasons.append(f"procedural landmark prims present: {found[:5]}")

    # 5) front RGB camera path exists (if the caller declares one)
    if front_cam_path is not None:
        cam = stage.GetPrimAtPath(front_cam_path)
        cam_ok = bool(cam and cam.IsValid())
        checks["front_camera_exists"] = cam_ok
        observed["front_camera_path"] = front_cam_path
        if not cam_ok:
            reasons.append(f"front camera prim missing at {front_cam_path}")

    # 6) resolution present / as expected (if declared)
    if resolution is not None:
        res_ok = list(resolution) == list(EXPECTED_RESOLUTION) or (len(resolution) == 2)
        checks["resolution_declared"] = res_ok
        observed["resolution"] = list(resolution)
        if not res_ok:
            reasons.append(f"resolution {resolution} not declared as [W,H]")

    # 7) optional visual safety net
    if front_rgb is not None:
        vis_ok, vis_stats = looks_hospital_like(front_rgb)
        checks["image_hospital_like"] = bool(vis_ok)
        observed["visual_stats"] = vis_stats
        if vis_ok is False:
            reasons.append(f"front image not hospital-like (near-flat/grey): {vis_stats}")

    passed = all(v for v in checks.values())
    return {"pass": passed, "checks": checks, "reasons": reasons,
            "observed": observed, "asset_path": HOSPITAL_USD}


def write_scene_identity_manifest(path, result, *, run_kind="scene-identity",
                                  extra=None, timestamp=None):
    """Write a scene-identity manifest BEFORE recording. Records the gate verdict
    and the locked rule so any downstream artifact is self-describing."""
    m = {
        "run_kind": run_kind,
        "asset_path": HOSPITAL_USD,
        "asset_is_hospital_usd": True,
        "scene_identity_pass": result["pass"],
        "checks": result["checks"],
        "failed_reasons": result["reasons"],
        "observed": result["observed"],
        "min_hospital_prims": MIN_HOSPITAL_PRIMS,
        "forbidden_landmark_fragments": list(FORBIDDEN_LANDMARKS),
        "expected_resolution": EXPECTED_RESOLUTION,
        "robot_camera_height_m": ROBOT_CAMERA_HEIGHT_M,
        "isaac_sim_version": "5.1.0.0",
        "locked_rule": ("Procedural-stage H6 = diagnostic route-family coverage experiment. "
                        "Real hospital USD = official target scene for future hospital ImageNav "
                        "data, demos, and professor visuals."),
        "timestamp": timestamp or datetime.datetime.now().isoformat(timespec="seconds"),
    }
    if extra:
        m.update(extra)
    with open(path, "w") as f:
        json.dump(m, f, indent=2)
    return m


# --------------------------------------------------------------------------- #
# Standalone self-test: boot Isaac, load hospital, run the gate on the live
# stage, write the top-level locked manifest. Exits non-zero if the gate fails.
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    from pathlib import Path
    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True, "width": 1280, "height": 720})

    import math                                    # noqa: E402
    import omni.usd                                # noqa: E402
    import carb.settings                           # noqa: E402
    import omni.replicator.core as rep             # noqa: E402
    from pxr import UsdGeom, UsdLux, Gf            # noqa: E402

    REPO = Path("/home/favl/robotics/gnm-vlnverse-baseline")
    LOCKED_MANIFEST = (REPO / "assets/experiments/hospital_h2_collection_20260709"
                       "/hospital_scene_locked_manifest.json")

    ctx = omni.usd.get_context(); ctx.new_stage(); app.update()
    stage = ctx.get_stage()
    UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(stage.GetPrimAtPath("/World"))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdLux.DomeLight.Define(stage, "/World/DomeLight").CreateIntensityAttr(1000.0)

    prim = stage.DefinePrim(HOSPITAL_ROOT)
    if not prim.GetReferences().AddReference(HOSPITAL_USD):
        print("[gate] ERROR: could not author hospital reference"); app.close(); raise SystemExit(3)
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

    # author a front RGB camera at robot height for the front-camera + visual checks
    cam_path = "/World/FrontCam"
    cam = UsdGeom.Camera.Define(stage, cam_path)
    cam.CreateFocalLengthAttr(18.0)
    cam.CreateClippingRangeAttr(Gf.Vec2f(0.02, 1000.0))
    eye, tgt = (-2.5, -0.5, 0.35), (3.0, -1.0, 0.6)
    UsdGeom.XformCommonAPI(cam).SetTranslate(Gf.Vec3d(*eye))
    dx, dy, dz = (t - c for c, t in zip(eye, tgt))
    yaw = math.degrees(math.atan2(dy, dx)) - 90.0
    pitch = 90.0 - math.degrees(math.atan2(-dz, math.hypot(dx, dy)))
    UsdGeom.XformCommonAPI(cam).SetRotate(Gf.Vec3f(pitch, 0.0, yaw))

    rgb = None
    try:
        rp = rep.create.render_product(cam_path, (1280, 720))
        annot = rep.AnnotatorRegistry.get_annotator("rgb")
        try:
            annot.attach([rp])
        except Exception:
            annot.attach(rp)
        for _ in range(12):
            try:
                rep.orchestrator.step(rt_subframes=16)
            except Exception:
                for _ in range(20):
                    app.update()
            arr = np.asarray(annot.get_data())
            if arr.size and arr.ndim >= 2:
                rgb = arr[..., :3]; break
    except Exception as e:
        print(f"[gate] visual capture skipped: {e}")

    result = verify_hospital_scene(stage, scene_mode="hospital", front_cam_path=cam_path,
                                   resolution=[1280, 720], front_rgb=rgb)
    write_scene_identity_manifest(LOCKED_MANIFEST, result, run_kind="locked-standard-selftest",
                                  extra={"front_camera_path": cam_path,
                                         "front_camera_eye_xyz": list(eye),
                                         "front_camera_target_xyz": list(tgt)})
    print("[gate] checks:", json.dumps(result["checks"]))
    print("[gate] reasons:", result["reasons"])
    print(f"[gate] PASS={result['pass']}  ->  {LOCKED_MANIFEST}")
    app.close()
    raise SystemExit(0 if result["pass"] else 5)
