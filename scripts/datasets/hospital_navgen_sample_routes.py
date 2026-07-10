"""Isaac-Hospital-NavGen route sampler (Stage 2).

Zone-aware A* over a coarse v0 occupancy grid rasterised from the
hand-authored scene semantics and safety zones (red = blocked,
amber = high cost, green = low cost). Emits route plans with length/turn
bins, zone traces and instruction grounding — rendering happens
separately (Stage 3).

Usage: python3 scripts/datasets/hospital_navgen_sample_routes.py <n> <seed> <out.json>
"""

import heapq
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
D = REPO / "assets/datasets/isaac_hospital_navgen_v0"
RES = 0.05
XMIN = YMIN = -5.5
W = H = int(11.0 / RES)
AMBER_COST = 3.0


def _in_poly(px, py, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]; x2, y2 = poly[(i + 1) % n]
        if (y1 > py) != (y2 > py):
            if px < (x2 - x1) * (py - y1) / (y2 - y1) + x1:
                inside = not inside
    return inside


def poly_mask(poly):
    ys, xs = np.mgrid[0:H, 0:W]
    wx = XMIN + xs * RES; wy = YMIN + ys * RES
    mask = np.zeros((H, W), bool)
    it = np.nditer(mask, flags=["multi_index"])
    xs_min = min(p[0] for p in poly); xs_max = max(p[0] for p in poly)
    ys_min = min(p[1] for p in poly); ys_max = max(p[1] for p in poly)
    box = (wx >= xs_min) & (wx <= xs_max) & (wy >= ys_min) & (wy <= ys_max)
    for r, c in np.argwhere(box):
        mask[r, c] = _in_poly(wx[r, c], wy[r, c], poly)
    return mask


def build_grids():
    sem = json.loads((D / "scene_semantics.json").read_text())
    zon = json.loads((D / "safety_zones.json").read_text())
    obstacle = np.zeros((H, W), bool)
    for lm in sem["landmarks"]:
        if lm["kind"] == "furniture":
            obstacle |= poly_mask(lm["polygon"])
    obstacle[:2] = obstacle[-2:] = True
    obstacle[:, :2] = obstacle[:, -2:] = True
    zone = np.full((H, W), "green", dtype=object)
    for z in reversed(zon["zones"]):          # green first, red last wins
        zone[poly_mask(z["polygon"])] = z["zone"]
    cost = np.where(zone == "amber", AMBER_COST, 1.0)
    blocked = obstacle | (zone == "red")
    for _ in range(4):                                 # 0.2 m safety margin
        b = blocked.copy()
        b[1:] |= blocked[:-1]; b[:-1] |= blocked[1:]
        b[:, 1:] |= blocked[:, :-1]; b[:, :-1] |= blocked[:, 1:]
        blocked = b
    return sem, zon, blocked, cost, zone


def to_world(r, c):
    return XMIN + c * RES, YMIN + r * RES


def astar(blocked, cost, a, b):
    op = [(0.0, a)]; g = {a: 0.0}; came = {}
    while op:
        _, cur = heapq.heappop(op)
        if cur == b:
            path = [cur]
            while cur in came:
                cur = came[cur]; path.append(cur)
            return path[::-1]
        for dr, dc in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
            nxt = (cur[0]+dr, cur[1]+dc)
            if not (0 <= nxt[0] < H and 0 <= nxt[1] < W) or blocked[nxt]:
                continue
            step = (1.414 if dr and dc else 1.0) * cost[nxt]
            ng = g[cur] + step
            if ng < g.get(nxt, 1e18):
                g[nxt] = ng; came[nxt] = cur
                heapq.heappush(op, (ng + abs(b[0]-nxt[0]) + abs(b[1]-nxt[1]), nxt))
    raise RuntimeError("no path")


def landmark_at(sem, x, y):
    for lm in sem["landmarks"]:
        if _in_poly(x, y, lm["polygon"]):
            return lm["name"]
    return "main lobby"


def main():
    n, seed, out = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    sem, zon, blocked, cost, zone = build_grids()
    free = np.argwhere(~blocked)
    rng = np.random.default_rng(seed)
    bins = {"short": (2.0, 4.0), "medium": (4.0, 7.0), "long": (7.0, 11.0)}
    routes, used = [], set()
    tries = 0
    while len(routes) < n and tries < 8000:
        tries += 1
        a, b = free[rng.integers(len(free), size=2)]
        d = np.hypot(*(a - b)) * RES
        blabel = next((k for k, (lo, hi) in bins.items() if lo <= d <= hi), None)
        if blabel is None:
            continue
        key = (tuple(a // 8), tuple(b // 8))
        if key in used:
            continue
        try:
            path = astar(blocked, cost, tuple(a), tuple(b))
        except RuntimeError:
            continue
        used.add(key)
        pts = np.array([to_world(r, c) for r, c in path])
        seg = np.diff(pts, axis=0)
        yaws = np.arctan2(seg[:, 1], seg[:, 0])
        turns = int((np.abs(np.diff(np.unwrap(yaws))) > 0.6).sum())
        ztrace = [str(zone[p]) for p in path]
        amber_frac = ztrace.count("amber") / len(ztrace)
        sx, sy = to_world(*path[0]); gx, gy = to_world(*path[-1])
        routes.append({
            "route_id": f"navgen_{seed:02d}_{len(routes):03d}",
            "start_world": [round(sx, 2), round(sy, 2)],
            "goal_world": [round(gx, 2), round(gy, 2)],
            "path_px": [list(map(int, p)) for p in path],
            "length_m": round(float(np.linalg.norm(seg, axis=1).sum()), 2),
            "length_bin": blabel, "turn_count": turns,
            "turn_bin": "multi" if turns >= 2 else ("single" if turns else "straight"),
            "zone_profile": {"amber_fraction": round(amber_frac, 3),
                             "red_fraction": 0.0,
                             "class": "amber_required" if amber_frac > 0.05
                                      else "green_only"},
            "start_landmark": landmark_at(sem, sx, sy),
            "goal_landmark": landmark_at(sem, gx, gy),
            "camera_convention": "Yahboom front-facing RGB",
        })
    json.dump({"routes": routes, "grid": {"res_m": RES, "origin": [XMIN, YMIN],
               "size": [H, W]},
               "policy": "red blocked at planning time; amber cost x3; "
                         "0.2 m dilation; dedup 8px cells"},
              open(out, "w"), indent=2)
    print(f"{len(routes)} routes | bins:",
          {b: sum(1 for r in routes if r['length_bin'] == b) for b in bins},
          "| zone classes:",
          {c: sum(1 for r in routes if r['zone_profile']['class'] == c)
           for c in ('green_only', 'amber_required')})


if __name__ == "__main__":
    main()
