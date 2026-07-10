"""H2.3 Workstream B: physics-derived occupancy map of the hospital.

PhysX overlap-box queries at robot body height over a 0.05 m grid inside
the +/-5.5 m workspace — measured collision geometry, replacing the
hand-authored semantic polygons that H2.2 proved incorrect.

Run with the isaac env python from the repo root.
"""

import json
from pathlib import Path

from isaacsim import SimulationApp
app = SimulationApp({"headless": True})
import numpy as np
import omni.usd
from omni.physx import get_physx_scene_query_interface
import carb
from pxr import UsdPhysics

HOSPITAL = ("https://omniverse-content-production.s3-us-west-2.amazonaws.com"
            "/Assets/Isaac/5.1/Isaac/Environments/Hospital/hospital.usd")
RES = 0.05
XMIN = YMIN = -5.5
N = int(11.0 / RES)
Z_LO, Z_HI = 0.06, 0.40          # robot body band; excludes floor

ctx = omni.usd.get_context()
ctx.open_stage(HOSPITAL)
stage = ctx.get_stage()
UsdPhysics.Scene.Define(stage, "/physicsScene")

import omni.timeline
omni.timeline.get_timeline_interface().play()
for _ in range(20):
    app.update()

qi = get_physx_scene_query_interface()
occ = np.zeros((N, N), dtype=np.uint8)
half = carb.Float3(RES / 2, RES / 2, (Z_HI - Z_LO) / 2)
zc = (Z_LO + Z_HI) / 2
hit_flag = {"v": False}


def on_hit(hit):
    hit_flag["v"] = True
    return False          # stop after first hit


for r in range(N):
    y = YMIN + r * RES
    for c in range(N):
        x = XMIN + c * RES
        hit_flag["v"] = False
        qi.overlap_box(half, carb.Float3(x, y, zc),
                       carb.Float4(0, 0, 0, 1), on_hit, False)
        if hit_flag["v"]:
            occ[r, c] = 1
    if r % 40 == 0:
        print(f"row {r}/{N}", flush=True)

out = Path("assets/datasets/isaac_hospital_navgen_v0")
np.save(out / "measured_occupancy.npy", occ)
from PIL import Image
img = ((1 - occ) * 255).astype(np.uint8)     # white = free
Image.fromarray(img).save(out / "measured_occupancy.png")
meta = {"resolution_m": RES, "origin_xy": [XMIN, YMIN], "size": [N, N],
        "z_band_m": [Z_LO, Z_HI],
        "method": "PhysX overlap_box per cell on the composed hospital "
                  "stage (measured collision geometry)",
        "occupied_fraction": round(float(occ.mean()), 4),
        "convention": "row = (y - YMIN)/RES, col = (x - XMIN)/RES; "
                      "white=free in PNG"}
(out / "measured_occupancy.json").write_text(json.dumps(meta, indent=2))
# K/M grind-zone check: x in [0,2], y in [-3.5,-2.5]
r0, r1 = int((-3.5 - YMIN)/RES), int((-2.5 - YMIN)/RES)
c0, c1 = int((0 - XMIN)/RES), int((2 - XMIN)/RES)
zone = occ[r0:r1, c0:c1]
print(f"RESULT occupied_fraction={occ.mean():.3f} "
      f"km_zone_occupied_fraction={zone.mean():.3f}")
app.close()
