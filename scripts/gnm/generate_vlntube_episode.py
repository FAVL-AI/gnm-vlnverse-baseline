"""Generate one VLNTube-format training episode from a composed USD scene.

Plans an A* route on the scene's occupancy map (calibrated transform:
col = (x_max - x)/scale, row = (y - y_min)/scale — verified by projecting
all 66 existing kujiale_0092 episodes onto free space at fraction 1.000),
renders 224x224 RGB frames along the route in headless Isaac, and packages
frames + traj_data.pkl in the exact format of the existing dataset loader.

Train scenes only — the frozen test scene kujiale_0271 is refused.

Run with the isaac env python from the repo root.
"""

import heapq
import json
import pickle
import sys
from pathlib import Path

SCENE = "kujiale_0092"
assert SCENE != "kujiale_0271", "test scene is frozen"
OUT_ROOT = Path("datasets/vlntube_generated/train")
EP_NAME = f"gen_{SCENE}_0000"
EVIDENCE = Path("assets/experiments/data_expansion/"
                "generated_episode_smoke_20260708")
CAM_HEIGHT = 1.2
STEP_M = 0.10

from isaacsim import SimulationApp
app = SimulationApp({"headless": True})
import numpy as np
import omni.replicator.core as rep
import omni.usd
from PIL import Image
from pxr import Gf, UsdGeom, UsdLux
from scipy.ndimage import binary_erosion

env = Path(f"datasets/vlntube/envs/{SCENE}")
occ = json.loads((env / "occupancy.json").read_text())
om = np.array(Image.open(env / "occupancy.png").convert("L"))
lo, hi, s = occ["lower"], occ["upper"], occ["scale"]
H, W = om.shape
free = binary_erosion(om > 128, iterations=3)  # ~15 cm safety margin


def to_world(row, col):
    return hi[0] - col * s, lo[1] + row * s


def to_px(x, y):
    return int(round((y - lo[1]) / s)), int(round((hi[0] - x) / s))


def astar(start, goal):
    op = [(0, start)]
    g = {start: 0.0}
    came = {}
    while op:
        _, cur = heapq.heappop(op)
        if cur == goal:
            path = [cur]
            while cur in came:
                cur = came[cur]
                path.append(cur)
            return path[::-1]
        for dr, dc in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
            nxt = (cur[0]+dr, cur[1]+dc)
            if not (0 <= nxt[0] < H and 0 <= nxt[1] < W) or not free[nxt]:
                continue
            ng = g[cur] + (1.414 if dr and dc else 1.0)
            if ng < g.get(nxt, 1e18):
                g[nxt] = ng
                came[nxt] = cur
                heapq.heappush(op, (ng + abs(goal[0]-nxt[0])
                                    + abs(goal[1]-nxt[1]), nxt))
    raise RuntimeError("no path")


# route: pick a free start/goal pair ~3 m apart automatically
rng = np.random.default_rng(42)
free_px = np.argwhere(free)
path_px = None
for _ in range(200):
    a, b = free_px[rng.integers(len(free_px), size=2)]
    dist_px = np.hypot(*(a - b))
    if not (25 <= dist_px <= 45):
        continue
    try:
        cand = astar(tuple(a), tuple(b))
    except RuntimeError:
        continue
    if len(cand) <= dist_px * 1.6:   # low-curvature: near-straight route
        p0, p1 = tuple(a), tuple(b)
        path_px = cand
        break
assert path_px, "no low-curvature free pair found"
start_w, goal_w = to_world(*p0), to_world(*p1)
pts = np.array([to_world(r, c) for r, c in path_px])
# resample at STEP_M spacing
seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
cum = np.concatenate([[0], np.cumsum(seg)])
n_steps = max(int(cum[-1] / STEP_M), 8)
si = np.linspace(0, cum[-1], n_steps)
xs = np.interp(si, cum, pts[:, 0])
ys = np.interp(si, cum, pts[:, 1])
pos = np.stack([xs, ys], axis=1).astype(np.float32)
d = np.diff(pos, axis=0)
yaw = np.arctan2(d[:, 1], d[:, 0])
yaw = np.append(yaw, yaw[-1]).astype(np.float32)

ctx = omni.usd.get_context()
ctx.open_stage(str(env / "start_result_navigation.usd"))
stage = ctx.get_stage()
UsdLux.DomeLight.Define(stage, "/World_extra/dome").CreateIntensityAttr(1200)
cam = UsdGeom.Camera.Define(stage, "/World_extra/cam")
t_op = cam.AddTranslateOp()
r_op = cam.AddRotateXYZOp()
cam.CreateClippingRangeAttr(Gf.Vec2f(0.05, 10000))
rp = rep.create.render_product("/World_extra/cam", (224, 224))
annot = rep.AnnotatorRegistry.get_annotator("rgb")
annot.attach(rp)

ep_dir = OUT_ROOT / EP_NAME
ep_dir.mkdir(parents=True, exist_ok=True)
EVIDENCE.mkdir(parents=True, exist_ok=True)
frames = []
for i, ((x, y), th) in enumerate(zip(pos, yaw)):
    t_op.Set(Gf.Vec3d(float(x), float(y), CAM_HEIGHT))
    r_op.Set(Gf.Vec3f(90.0, 0.0, float(np.degrees(th)) - 90.0))
    arr = np.zeros(())
    for _ in range(12):
        rep.orchestrator.step(rt_subframes=3)
        arr = np.array(annot.get_data())
        if arr.ndim == 3 and arr.size and float(arr[..., :3].mean()) > 1.0:
            break
    rgb = arr[..., :3].astype("uint8")
    Image.fromarray(rgb).save(ep_dir / f"{i}.jpg", quality=92)
    frames.append(rgb)

pickle.dump({"position": pos, "yaw": yaw},
            open(ep_dir / "traj_data.pkl", "wb"))
meta = {
    "generator": "scripts/gnm/generate_vlntube_episode.py",
    "scene": SCENE, "episode": EP_NAME,
    "start_world": list(map(float, start_w)),
    "goal_world": list(map(float, goal_w)),
    "n_frames": len(frames),
    "path_length_m": float(cum[-1]),
    "camera_height_m": CAM_HEIGHT,
    "image_size": [224, 224],
    "calibration": "col=(x_max-x)/scale, row=(y-y_min)/scale; verified "
                   "1.000 free-fraction on all 66 existing kujiale_0092 "
                   "episodes",
    "safety_margin": "occupancy eroded 3 px (~0.15 m)",
    "mean_frame_intensity": float(np.mean([f.mean() for f in frames])),
}
(ep_dir / "metadata.json").write_text(json.dumps(meta, indent=2))

# contact sheet: every 6th frame in a row
sel = frames[::max(1, len(frames)//8)][:8]
sheet = np.concatenate(sel, axis=1)
with open(EVIDENCE / "render_contact_sheet.ppm", "wb") as f:
    f.write(f"P6\n{sheet.shape[1]} {sheet.shape[0]}\n255\n".encode())
    f.write(sheet.tobytes())
json.dump(meta, open(EVIDENCE / "first_generated_episode_manifest.json",
                     "w"), indent=2)
app.close()
