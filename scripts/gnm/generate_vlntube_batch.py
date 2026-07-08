"""Route-quality-controlled batch generation of VLNTube-format episodes.

Camera model verified against original frames (see
camera_model_verification.md): TOP-DOWN camera, z=2.4 m, focal 16 mm,
224x224, image orientation rotateXYZ(0,0,deg(yaw)) — the original
dataset is bird's-eye, so route quality is clearance/length/curvature/
goal-content, not first-person wall-facing.

Calibration (verified free-fraction 1.000 on every train scene):
col = (x_max - x)/scale, row = (y - y_min)/scale.

Usage (isaac env, repo root):
    python scripts/gnm/generate_vlntube_batch.py <scene> <n_episodes> <seed>
"""

import heapq
import json
import pickle
import sys
from pathlib import Path

SCENE, N_EP, SEED = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
assert SCENE != "kujiale_0271", "test scene is frozen"
POLICY = {"min_path_m": 2.0, "max_path_m": 6.0,
          "max_curvature_ratio": 1.5, "safety_erosion_px": 3,
          "min_clearance_m": 0.25, "min_goal_frame_std": 15.0,
          "camera": {"z_m": 2.4, "focal_mm": 16.0,
                     "rotation": "rotateXYZ(0,0,deg(yaw))",
                     "image": [224, 224]},
          "step_m": 0.10, "dedup_cell_px": 6}

from isaacsim import SimulationApp
app = SimulationApp({"headless": True})
import numpy as np
import omni.replicator.core as rep
import omni.usd
from PIL import Image
from pxr import Gf, UsdGeom, UsdLux
from scipy.ndimage import binary_erosion, distance_transform_edt

env = Path(f"datasets/vlntube/envs/{SCENE}")
occ = json.loads((env / "occupancy.json").read_text())
om = np.array(Image.open(env / "occupancy.png").convert("L"))
lo, hi, s = occ["lower"], occ["upper"], occ["scale"]
H, W = om.shape
free = binary_erosion(om > 128, iterations=POLICY["safety_erosion_px"])
clear_px = distance_transform_edt(om > 128)


def to_world(row, col):
    return hi[0] - col * s, lo[1] + row * s


def astar(start, goal):
    op = [(0, start)]; g = {start: 0.0}; came = {}
    while op:
        _, cur = heapq.heappop(op)
        if cur == goal:
            path = [cur]
            while cur in came:
                cur = came[cur]; path.append(cur)
            return path[::-1]
        for dr, dc in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
            nxt = (cur[0]+dr, cur[1]+dc)
            if not (0 <= nxt[0] < H and 0 <= nxt[1] < W) or not free[nxt]:
                continue
            ng = g[cur] + (1.414 if dr and dc else 1.0)
            if ng < g.get(nxt, 1e18):
                g[nxt] = ng; came[nxt] = cur
                heapq.heappush(op, (ng + abs(goal[0]-nxt[0])
                                    + abs(goal[1]-nxt[1]), nxt))
    raise RuntimeError("no path")


rng = np.random.default_rng(SEED)
free_px = np.argwhere(free)
lo_px = POLICY["min_path_m"] / s
hi_px = POLICY["max_path_m"] / s
routes, used_cells = [], set()
import pickle as _pk
def _cell_of(pos_xy):
    col = (hi[0]-pos_xy[0])/s; row = (pos_xy[1]-lo[1])/s
    return (int(row)//POLICY["dedup_cell_px"], int(col)//POLICY["dedup_cell_px"])
for _old in Path("datasets/vlntube_generated/train").glob("*/metadata.json"):
    _m = json.loads(_old.read_text())
    if _m.get("scene") != SCENE: continue
    _t = _pk.loads((_old.parent/"traj_data.pkl").read_bytes())
    used_cells.add((_cell_of(_t["position"][0]), _cell_of(_t["position"][-1])))
tries = 0
while len(routes) < N_EP * 2 and tries < 6000:
    tries += 1
    a, b = free_px[rng.integers(len(free_px), size=2)]
    d = np.hypot(*(a - b))
    if not (lo_px <= d <= hi_px):
        continue
    cell = (tuple(int(v) // POLICY["dedup_cell_px"] for v in a),
            tuple(int(v) // POLICY["dedup_cell_px"] for v in b))
    if cell in used_cells:
        continue
    try:
        path = astar(tuple(a), tuple(b))
    except RuntimeError:
        continue
    if len(path) > d * POLICY["max_curvature_ratio"]:
        continue
    clearances = np.array([clear_px[p] * s for p in path])
    if clearances.min() < POLICY["min_clearance_m"]:
        continue
    used_cells.add(cell)
    routes.append({"path": path, "clearance_min": float(clearances.min()),
                   "clearance_median": float(np.median(clearances))})
assert len(routes) >= N_EP, f"only {len(routes)} routes after {tries} tries"

ctx = omni.usd.get_context()
ctx.open_stage(str(env / "start_result_navigation.usd"))
stage = ctx.get_stage()
UsdLux.DomeLight.Define(stage, "/World_extra/dome").CreateIntensityAttr(1200)
cam = UsdGeom.Camera.Define(stage, "/World_extra/cam")
t_op = cam.AddTranslateOp(); r_op = cam.AddRotateXYZOp()
cam.CreateClippingRangeAttr(Gf.Vec2f(0.05, 10000))
cam.CreateFocalLengthAttr(POLICY["camera"]["focal_mm"])
rp = rep.create.render_product("/World_extra/cam", tuple(POLICY["camera"]["image"]))
annot = rep.AnnotatorRegistry.get_annotator("rgb"); annot.attach(rp)

def render_at(x, y, th):
    t_op.Set(Gf.Vec3d(float(x), float(y), POLICY["camera"]["z_m"]))
    r_op.Set(Gf.Vec3f(0.0, 0.0, float(np.degrees(th))))
    arr = np.zeros(())
    for _ in range(12):
        rep.orchestrator.step(rt_subframes=3)
        arr = np.array(annot.get_data())
        if arr.ndim == 3 and arr.size and float(arr[..., :3].mean()) > 1.0:
            break
    return arr[..., :3].astype("uint8")


# goal-content precheck: reject routes whose goal frame is featureless
strong_routes = []
for route in routes:
    gr, gc = route["path"][-1]
    gx, gy = to_world(gr, gc)
    prev = route["path"][-2] if len(route["path"]) > 1 else route["path"][-1]
    px, py = to_world(*prev)
    th = np.arctan2(gy - py, gx - px)
    gframe = render_at(gx, gy, th)
    route["goal_precheck_std"] = float(gframe.std())
    if route["goal_precheck_std"] >= POLICY["min_goal_frame_std"]:
        strong_routes.append(route)
print(f"[batch] goal precheck: {len(strong_routes)}/{len(routes)} strong",
      flush=True)
routes = strong_routes[:N_EP]

results = []
for ep_i, route in enumerate(routes):
    pts = np.array([to_world(r, c) for r, c in route["path"]])
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)])
    n_steps = max(int(cum[-1] / POLICY["step_m"]), 8)
    si = np.linspace(0, cum[-1], n_steps)
    pos = np.stack([np.interp(si, cum, pts[:, 0]),
                    np.interp(si, cum, pts[:, 1])], 1).astype(np.float32)
    d = np.diff(pos, axis=0)
    yaw = np.append(np.arctan2(d[:, 1], d[:, 0]),
                    np.arctan2(d[-1, 1], d[-1, 0])).astype(np.float32)
    ep_name = f"gen_{SCENE}_{SEED:02d}{ep_i:02d}"
    ep_dir = Path("datasets/vlntube_generated/train") / ep_name
    ep_dir.mkdir(parents=True, exist_ok=True)
    stds = []
    for i, ((x, y), th) in enumerate(zip(pos, yaw)):
        t_op.Set(Gf.Vec3d(float(x), float(y), POLICY["camera"]["z_m"]))
        r_op.Set(Gf.Vec3f(0.0, 0.0, float(np.degrees(th))))
        arr = np.zeros(())
        for _ in range(12):
            rep.orchestrator.step(rt_subframes=3)
            arr = np.array(annot.get_data())
            if arr.ndim == 3 and arr.size and float(arr[..., :3].mean()) > 1.0:
                break
        rgb = arr[..., :3].astype("uint8")
        Image.fromarray(rgb).save(ep_dir / f"{i}.jpg", quality=92)
        stds.append(float(rgb.std()))
    goal_ok = stds[-1] >= POLICY["min_goal_frame_std"]
    pickle.dump({"position": pos, "yaw": yaw}, open(ep_dir/"traj_data.pkl", "wb"))
    meta = {"generator": "scripts/gnm/generate_vlntube_batch.py",
            "scene": SCENE, "episode": ep_name, "seed": SEED,
            "n_frames": len(pos), "path_length_m": float(cum[-1]),
            "route_quality": {"clearance_min_m": route["clearance_min"],
                              "clearance_median_m": route["clearance_median"],
                              "goal_frame_std": stds[-1],
                              "goal_frame_ok": bool(goal_ok)},
            "camera": POLICY["camera"], "policy": {k: v for k, v in
                                                   POLICY.items()
                                                   if k != "camera"}}
    (ep_dir / "metadata.json").write_text(json.dumps(meta, indent=2))
    results.append(meta)
    print(f"[batch] {ep_name}: {len(pos)} frames, {cum[-1]:.2f} m, "
          f"clear {route['clearance_min']:.2f}/{route['clearance_median']:.2f}, "
          f"goal_std {stds[-1]:.1f}", flush=True)

out = Path("assets/experiments/data_expansion/generated_train_batch_20260708")
out.mkdir(parents=True, exist_ok=True)
(out / f"batch_{SCENE}_seed{SEED}.json").write_text(json.dumps(results, indent=2))
app.close()
