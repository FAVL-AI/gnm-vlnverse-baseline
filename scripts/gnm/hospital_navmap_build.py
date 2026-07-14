"""Build a robot-height navigability (occupancy) map of the real Isaac hospital.usd
by computing world-space AABBs of leaf geometry that intersect the robot slab.
Runs the scene-identity gate first (fail-closed). Saves a raw occupancy grid (.npy)
+ metadata so hospital driving routes can be authored on MEASURED free floor, not
guesses. PNG visualization + route authoring happen post-run in the gnm_train env.
"""
from isaacsim import SimulationApp
app = SimulationApp({"headless": True, "width": 640, "height": 480})

import sys, json                              # noqa: E402
from pathlib import Path                       # noqa: E402
import numpy as np                             # noqa: E402
import omni.usd                                # noqa: E402
from pxr import UsdGeom, UsdLux, Usd, Gf        # noqa: E402

REPO = Path("/home/favl/robotics/gnm-vlnverse-baseline")
sys.path.insert(0, str(REPO / "scripts/gnm"))
from hospital_scene_identity_gate import (      # noqa: E402
    verify_hospital_scene, write_scene_identity_manifest, HOSPITAL_USD, HOSPITAL_ROOT)

OUT = REPO / "assets/experiments/hospital_h7_collection/navmap"
OUT.mkdir(parents=True, exist_ok=True)

# grid over the lobby region; z-slab picks obstacles a 0.35 m robot would hit
X_MIN, X_MAX, Y_MIN, Y_MAX, RES = -7.0, 7.0, -7.0, 7.0, 0.05
Z_LO, Z_HI = 0.08, 0.55
NX = int(round((X_MAX - X_MIN) / RES))
NY = int(round((Y_MAX - Y_MIN) / RES))

ctx = omni.usd.get_context(); ctx.new_stage(); app.update()
stage = ctx.get_stage()
UsdGeom.Xform.Define(stage, "/World"); stage.SetDefaultPrim(stage.GetPrimAtPath("/World"))
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z); UsdGeom.SetStageMetersPerUnit(stage, 1.0)
UsdLux.DomeLight.Define(stage, "/World/DomeLight").CreateIntensityAttr(1000.0)

prim = stage.DefinePrim(HOSPITAL_ROOT)
if not prim.GetReferences().AddReference(HOSPITAL_USD):
    print("[navmap] ERROR: could not author hospital reference"); app.close(); raise SystemExit(3)
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
write_scene_identity_manifest(OUT / "navmap_scene_identity.json", gate, run_kind="hospital_navmap_build")
print(f"[navmap] gate PASS={gate['pass']} prims={gate['observed']['hospital_prim_count']}", flush=True)
if not gate["pass"]:
    print("[navmap] gate failed — refusing to map.", gate["reasons"]); app.close(); raise SystemExit(5)

occ = np.zeros((NY, NX), dtype=np.uint8)
bbc = UsdGeom.BBoxCache(Usd.TimeCode.Default(),
                       [UsdGeom.Tokens.default_, UsdGeom.Tokens.render],
                       useExtentsHint=True)
n_geo = n_hit = 0
# hospital.usd uses scenegraph instancing — descend into instance proxies, and take
# all Boundable geometry (Mesh etc.), not just non-instanced Gprims.
rng_it = Usd.PrimRange(stage.GetPrimAtPath(HOSPITAL_ROOT), Usd.TraverseInstanceProxies())
for p in rng_it:
    if not p.IsA(UsdGeom.Boundable):
        continue
    n_geo += 1
    try:
        rng = bbc.ComputeWorldBound(p).ComputeAlignedRange()
    except Exception:
        continue
    if rng.IsEmpty():
        continue
    mn, mx = rng.GetMin(), rng.GetMax()
    if mx[2] < Z_LO or mn[2] > Z_HI:          # no overlap with the robot slab
        continue
    ix0 = max(0, int((mn[0] - X_MIN) / RES)); ix1 = min(NX, int((mx[0] - X_MIN) / RES) + 1)
    iy0 = max(0, int((mn[1] - Y_MIN) / RES)); iy1 = min(NY, int((mx[1] - Y_MIN) / RES) + 1)
    if ix1 <= ix0 or iy1 <= iy0:
        continue
    occ[iy0:iy1, ix0:ix1] = 1
    n_hit += 1

np.save(OUT / "occupancy_raw.npy", occ)
(OUT / "navmap_meta.json").write_text(json.dumps({
    "asset_path": HOSPITAL_USD, "scene_identity_pass": gate["pass"],
    "x_min": X_MIN, "x_max": X_MAX, "y_min": Y_MIN, "y_max": Y_MAX, "res_m": RES,
    "nx": NX, "ny": NY, "z_slab": [Z_LO, Z_HI], "robot_camera_height_m": 0.35,
    "gprim_total": n_geo, "gprim_in_slab": n_hit,
    "occupied_cells": int(occ.sum()), "free_cells": int((occ == 0).sum()),
    "note": "occupancy_raw.npy: 1=occupied by hospital geometry in robot slab, 0=free. "
            "Inflate by robot radius before authoring routes."}, indent=2))
print(f"[navmap] gprim={n_geo} in-slab={n_hit} occupied_cells={int(occ.sum())} -> {OUT}", flush=True)
app.close()
