"""Isaac-Hospital-NavGen renderer (Stage 3).

Renders front-facing Yahboom-convention RGB frames along sampled routes
in the Isaac hospital stage. Camera: z=0.35 m (robot camera height),
horizontal, rotateXYZ(90, 0, deg(yaw)-90), 640x480 — matching the live
/camera/image_raw convention. Rendering warm-up before every capture.

Usage (isaac env, repo root):
    python scripts/datasets/hospital_navgen_render_episode.py <routes.json> <n_episodes>
"""

import hashlib
import json
import pickle
import sys
from pathlib import Path

ROUTES, N = sys.argv[1], int(sys.argv[2])
from isaacsim import SimulationApp
app = SimulationApp({"headless": True})
import numpy as np
import omni.replicator.core as rep
import omni.usd
from PIL import Image
from pxr import Gf, UsdGeom, UsdLux

REPO = Path(__file__).resolve().parents[2]
HOSPITAL = ("https://omniverse-content-production.s3-us-west-2.amazonaws.com"
            "/Assets/Isaac/5.1/Isaac/Environments/Hospital/hospital.usd")
STEP_M = 0.10
CAM = {"z_m": 0.35, "image": [640, 480],
       "rotation": "rotateXYZ(90,0,deg(yaw)-90)",
       "convention": "Yahboom front-facing RGB"}

routes = json.loads(Path(ROUTES).read_text())["routes"][:N]
zones = json.loads((REPO / "assets/datasets/isaac_hospital_navgen_v0/"
                    "safety_zones.json").read_text())


def _in_poly(px, py, poly):
    inside = False
    for i in range(len(poly)):
        x1, y1 = poly[i]; x2, y2 = poly[(i + 1) % len(poly)]
        if (y1 > py) != (y2 > py) and \
                px < (x2 - x1) * (py - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def zone_at(x, y):
    for z in zones["zones"]:
        if _in_poly(x, y, z["polygon"]):
            return z["zone"]
    return "green"


ctx = omni.usd.get_context()
ctx.open_stage(HOSPITAL)
stage = ctx.get_stage()
UsdLux.DomeLight.Define(stage, "/World_extra/dome").CreateIntensityAttr(800)
cam = UsdGeom.Camera.Define(stage, "/World_extra/cam")
t_op = cam.AddTranslateOp(); r_op = cam.AddRotateXYZOp()
cam.CreateClippingRangeAttr(Gf.Vec2f(0.02, 10000))
rp = rep.create.render_product("/World_extra/cam", tuple(CAM["image"]))
annot = rep.AnnotatorRegistry.get_annotator("rgb"); annot.attach(rp)


def render_at(x, y, th):
    t_op.Set(Gf.Vec3d(float(x), float(y), CAM["z_m"]))
    r_op.Set(Gf.Vec3f(90.0, 0.0, float(np.degrees(th)) - 90.0))
    arr = np.zeros(())
    for _ in range(14):                       # warm-up until content
        rep.orchestrator.step(rt_subframes=3)
        arr = np.array(annot.get_data())
        if arr.ndim == 3 and arr.size and float(arr[..., :3].mean()) > 1.0:
            break
    return arr[..., :3].astype("uint8")


RES = 0.05; XMIN = YMIN = -5.5
for route in routes:
    pts = np.array([[XMIN + c * RES, YMIN + r * RES]
                    for r, c in route["path_px"]])
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)])
    n_steps = max(int(cum[-1] / STEP_M), 10)
    si = np.linspace(0, cum[-1], n_steps)
    pos = np.stack([np.interp(si, cum, pts[:, 0]),
                    np.interp(si, cum, pts[:, 1])], 1).astype(np.float32)
    d = np.diff(pos, axis=0)
    yaw = np.append(np.arctan2(d[:, 1], d[:, 0]),
                    np.arctan2(d[-1, 1], d[-1, 0])).astype(np.float32)
    ep_dir = (REPO / "datasets/isaac_hospital_navgen_v0/unassigned"
              / route["route_id"])
    ep_dir.mkdir(parents=True, exist_ok=True)
    ztrace = []
    for i, ((x, y), th) in enumerate(zip(pos, yaw)):
        rgb = render_at(x, y, th)
        Image.fromarray(rgb).save(ep_dir / f"{i}.jpg", quality=90)
        ztrace.append({"step": i, "x": round(float(x), 3),
                       "y": round(float(y), 3), "zone": zone_at(x, y)})
    Image.fromarray(render_at(*pos[-1], yaw[-1])).save(ep_dir / "goal.png")
    pickle.dump({"position": pos, "yaw": yaw},
                open(ep_dir / "traj_data.pkl", "wb"))
    (ep_dir / "zone_trace.json").write_text(json.dumps(ztrace, indent=1))
    meta = dict(route)
    meta.update({"dataset": "Isaac-Hospital-NavGen-v0",
                 "camera": CAM, "n_frames": n_steps,
                 "amber_steps": sum(1 for z in ztrace if z["zone"] == "amber"),
                 "red_steps": sum(1 for z in ztrace if z["zone"] == "red"),
                 "claim": "synthetic internal hospital navigation data; "
                          "not real-robot evidence"})
    (ep_dir / "metadata.json").write_text(json.dumps(meta, indent=2))
    sha = "\n".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}"
                    for p in sorted(ep_dir.iterdir()))
    (ep_dir / "checksums.sha256").write_text(sha + "\n")
    print(f"[navgen] {route['route_id']}: {n_steps} frames "
          f"{route['length_m']}m {route['length_bin']}/{route['turn_bin']} "
          f"amber={meta['amber_steps']}", flush=True)
app.close()
