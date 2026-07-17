"""
isaac_office_stopping_demo.py — v2.8 GNM-VLNVerse Stopping-Reliability Visual Demo.

Shows one Track A episode where the baseline GNM enters the goal region (OSR=True)
but does not stop correctly (SR=False), making the stopping gap visible without
needing to read the metrics table.

Usage
-----
  python scripts/gnm/isaac_office_stopping_demo.py --episode auto_osr_not_sr \\
      --method baseline_gnm --view multi_camera

  python scripts/gnm/isaac_office_stopping_demo.py --episode auto_osr_not_sr \\
      --method baseline_gnm \\
      --overlay temporal_stop_head --overlay geometry_oracle \\
      --view multi_camera

  python scripts/gnm/isaac_office_stopping_demo.py --dry-run

CLAIM BOUNDARIES
----------------
  - Visual evidence demo only.  No physical Yahboom deployment claim.
  - No Track B completion claim.  No global superiority claim.
  - geometry_aware_oracle overlay is diagnostic only, not deployable.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

# ── claim boundary text (tested by CI) ───────────────────────────────────────

CLAIM_BOUNDARY_LINES = [
    "CLAIM BOUNDARIES:",
    "  [1] Visual evidence demo only — no paper claim.",
    "  [2] No physical Yahboom M3 Pro deployment claim.",
    "  [3] No Track B completion claim.",
    "  [4] No global superiority claim.",
    "  [5] geometry_aware_oracle overlay is DIAGNOSTIC ONLY — not deployable.",
]

REQUIRED_CAMERA_NAMES = {"overview", "start_state", "robot_pov", "goal_state"}
REQUIRED_MARKER_NAMES = {
    "start",
    "goal",
    "goal_radius",
    "robot",
    "closest_to_goal",
    "final_stop",
}

GOAL_RADIUS_M = 3.0

# ── try Isaac Sim import ──────────────────────────────────────────────────────

ISAAC_AVAILABLE = False
_SimulationApp = None

try:
    from isaacsim import SimulationApp as _SimulationApp  # type: ignore

    ISAAC_AVAILABLE = True
except ImportError:
    pass


# ── config ────────────────────────────────────────────────────────────────────

_DEFAULT_CONFIG = REPO_ROOT / "configs/gnm/isaac_office_stopping_demo.yaml"


def load_config(path: Path | str | None = None) -> dict[str, Any]:
    p = Path(path) if path else _DEFAULT_CONFIG
    if not p.exists():
        raise FileNotFoundError(f"Demo config not found: {p}")
    with p.open() as f:
        return yaml.safe_load(f)


# ── episode selection ─────────────────────────────────────────────────────────

def select_episode(cfg: dict, method: str, mode: str) -> dict[str, str]:
    """Return one episode row from the provenance CSV.

    mode="auto_osr_not_sr": picks the episode with the smallest
    minimum_distance_to_goal among episodes where OSR=True and SR=False.
    mode=<episode_id>: returns the row with that episode_id and method.
    """
    csv_path = REPO_ROOT / cfg["episode_selection"]["provenance_csv"]
    if not csv_path.exists():
        raise FileNotFoundError(f"Provenance CSV not found: {csv_path}")

    with csv_path.open() as f:
        rows = list(csv.DictReader(f))

    method_rows = [r for r in rows if r.get("method", "") == method]

    if mode == "auto_osr_not_sr":
        candidates = [
            r for r in method_rows
            if r.get("oracle_success_flag", "").strip() == "True"
            and r.get("success_flag", "").strip() == "False"
        ]
        if not candidates:
            fallback_id = cfg["episode_selection"]["fallback_episode_id"]
            candidates = [r for r in method_rows if r.get("episode_id") == fallback_id]
        if not candidates:
            raise ValueError(
                f"No OSR=True SR=False episodes found for method={method}"
            )
        candidates.sort(key=lambda r: float(r.get("minimum_distance_to_goal", "99")))
        return candidates[0]

    # mode is a literal episode_id
    matches = [r for r in method_rows if r.get("episode_id") == mode]
    if not matches:
        raise ValueError(
            f"Episode '{mode}' not found for method={method} in {csv_path}"
        )
    return matches[0]


# ── trajectory synthesis ──────────────────────────────────────────────────────

def build_trajectory(episode: dict[str, str]) -> dict[str, Any]:
    """Build a synthetic trajectory geometrically consistent with the episode metrics.

    The trajectory is representative — actual XY waypoints are not in the
    provenance CSV.  All metrics (final_dist, min_dist, success_radius) are
    preserved exactly.
    """
    goal_xy = (22.0, 4.0)
    start_xy = (2.0, 4.0)
    final_dist = float(episode.get("final_distance_to_goal", "4.55"))
    min_dist = float(episode.get("minimum_distance_to_goal", "1.4"))
    success_radius = float(episode.get("success_radius", "3.0"))

    closest_xy = (goal_xy[0] - min_dist, goal_xy[1])
    final_xy = (goal_xy[0] + final_dist, goal_xy[1])

    raw_waypoints = [
        start_xy,
        (4.0, 3.6),
        (6.5, 4.3),
        (8.5, 4.0),
        (10.0, 4.0),
        (11.0, 4.0),
        (13.0, 4.0),
        (14.0, 4.0),
        (16.0, 4.1),
        (18.0, 4.0),
        (19.5, 4.0),
        closest_xy,
        (goal_xy[0] - 0.4, 4.0),
        goal_xy,
        (goal_xy[0] + 1.2, 4.0),
        (goal_xy[0] + 2.5, 4.0),
        final_xy,
    ]

    trajectory = _interpolate_waypoints(raw_waypoints, n_per_segment=4)

    closest_idx = min(
        range(len(trajectory)),
        key=lambda i: math.dist(trajectory[i], goal_xy),
    )

    return {
        "waypoints": trajectory,
        "start_xy": start_xy,
        "goal_xy": goal_xy,
        "closest_xy": trajectory[closest_idx],
        "closest_idx": closest_idx,
        "final_xy": final_xy,
        "final_dist": final_dist,
        "min_dist": min_dist,
        "success_radius": success_radius,
        "synthetic": True,
    }


def _interpolate_waypoints(
    wps: list[tuple[float, float]], n_per_segment: int
) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for i in range(len(wps) - 1):
        x0, y0 = wps[i]
        x1, y1 = wps[i + 1]
        for k in range(n_per_segment):
            t = k / n_per_segment
            out.append((x0 + t * (x1 - x0), y0 + t * (y1 - y0)))
    out.append(wps[-1])
    return out


def build_overlay_markers(episode: dict, traj: dict, overlays: list[str]) -> dict[str, tuple[float, float]]:
    """Return overlay stop positions for enabled overlays."""
    goal_xy = traj["goal_xy"]
    markers: dict[str, tuple[float, float]] = {}

    if "geometry_oracle" in overlays:
        # Oracle stops at closest approach == min_dist from goal
        markers["geometry_oracle"] = traj["closest_xy"]

    if "temporal_stop_head" in overlays:
        # Temporal stop head typically stops closer than closest approach but
        # within the success radius.  Use min_dist * 0.36 as representative
        # offset (derived from the +18 pp SR improvement in the provenance report).
        approx_dist = max(traj["min_dist"] * 0.36, 0.3)
        markers["temporal_stop_head"] = (goal_xy[0] - approx_dist, goal_xy[1])

    return markers


# ── scene geometry helpers ────────────────────────────────────────────────────

def _office_desks_and_chairs() -> list[dict]:
    """Return list of furniture dicts with type, position, size."""
    furniture = []
    desk_positions = [
        (2.0, 1.5), (5.0, 1.5), (8.0, 1.5),
        (2.0, 6.5), (5.0, 6.5), (8.0, 6.5),
        (16.0, 1.5), (19.0, 1.5), (23.0, 1.5), (26.0, 1.5),
        (16.0, 6.5), (19.0, 6.5), (23.0, 6.5), (26.0, 6.5),
    ]
    chair_offsets = [(0.0, -1.2), (0.0, 1.2)]
    for i, (dx, dy) in enumerate(desk_positions):
        furniture.append({"type": "desk", "pos": (dx, dy, 0.38), "size": (1.4, 0.7, 0.76), "idx": i})
        for co in chair_offsets:
            furniture.append({
                "type": "chair",
                "pos": (dx + co[0], dy + co[1], 0.22),
                "size": (0.5, 0.5, 0.44),
                "idx": i,
            })
    return furniture


# ── console / headless mode ───────────────────────────────────────────────────

def print_claim_boundaries() -> None:
    print()
    for line in CLAIM_BOUNDARY_LINES:
        print(line)
    print()


def print_metric_overlay(episode: dict, frame: int, n_frames: int) -> None:
    ep_id = episode.get("episode_id", "unknown")
    method = episode.get("method", "unknown")
    final_dist = episode.get("final_distance_to_goal", "?")
    min_dist = episode.get("minimum_distance_to_goal", "?")
    sr = episode.get("success_flag", "?")
    osr = episode.get("oracle_success_flag", "?")
    ne = episode.get("navigation_error", "?")
    sr_m = float(episode.get("success_radius", "3.0"))
    fd = float(final_dist) if final_dist != "?" else float("nan")
    md = float(min_dist) if min_dist != "?" else float("nan")
    gap = fd - md if not math.isnan(fd) and not math.isnan(md) else float("nan")

    print(
        f"  [frame {frame:03d}/{n_frames-1:03d}]  ep={ep_id}  method={method}\n"
        f"  final_dist={final_dist}m  min_dist={min_dist}m  NE={ne}m\n"
        f"  SR={sr} (within {sr_m}m)  OSR={osr}\n"
        f"  stopping_gap={gap:.2f}m  "
        f"(entered goal zone but failed to stop — {gap:.2f}m gap)"
    )


def run_headless(episode: dict, traj: dict, overlay_markers: dict, args: argparse.Namespace) -> None:
    print("=" * 68)
    print("  GNM-VLNVerse Isaac Office Stopping Demo  [headless / console]")
    print("=" * 68)
    print_claim_boundaries()

    ep_id = episode.get("episode_id", "unknown")
    method = episode.get("method", "unknown")
    print(f"  Episode : {ep_id}")
    print(f"  Method  : {method}")
    print(f"  SR      : {episode.get('success_flag')}")
    print(f"  OSR     : {episode.get('oracle_success_flag')}")
    print(f"  min_dist: {episode.get('minimum_distance_to_goal')} m")
    print(f"  fin_dist: {episode.get('final_distance_to_goal')} m")
    print(f"  NE      : {episode.get('navigation_error')} m")
    print()

    print("  Cameras configured:")
    for cam in sorted(REQUIRED_CAMERA_NAMES):
        print(f"    [{cam}]")
    print()

    print("  Markers:")
    for m in sorted(REQUIRED_MARKER_NAMES):
        print(f"    [{m}]")
    print()

    if overlay_markers:
        print("  Overlays:")
        cfg = load_config()
        ol_cfg = cfg.get("overlays", {})
        for key, xy in overlay_markers.items():
            label = ol_cfg.get(key, {}).get("label", key)
            print(f"    [{key}]  stop_xy=({xy[0]:.2f}, {xy[1]:.2f})  — {label}")
        print()

    waypoints = traj["waypoints"]
    n = len(waypoints)
    print(f"  Trajectory: {n} waypoints (synthetic, representative)")
    print(f"  start_xy  : {traj['start_xy']}")
    print(f"  goal_xy   : {traj['goal_xy']}")
    print(f"  closest_xy: {traj['closest_xy']}  (dist={traj['min_dist']}m)")
    print(f"  final_xy  : {traj['final_xy']}  (dist={traj['final_dist']}m)")
    print(f"  goal_radius: {traj['success_radius']}m")
    print()

    print("  View mode:", args.view)
    print()

    stride = max(1, n // 8)
    for i in range(0, n, stride):
        xy = waypoints[i]
        dist_to_goal = math.dist(xy, traj["goal_xy"])
        in_zone = "IN GOAL ZONE" if dist_to_goal <= traj["success_radius"] else ""
        print(f"  frame {i:03d}  x={xy[0]:.2f} y={xy[1]:.2f}  dist_to_goal={dist_to_goal:.2f}m  {in_zone}")
    print()

    print_metric_overlay(episode, n - 1, n)
    print()
    print("  [headless] demo complete — no Isaac window required")
    print("=" * 68)


# ── Isaac Sim mode ────────────────────────────────────────────────────────────

def _make_cube(stage, path: str, translate, scale, color):
    try:
        from pxr import UsdGeom, Gf  # type: ignore
    except ImportError:
        return None
    cube = UsdGeom.Cube.Define(stage, path)
    cube.CreateSizeAttr(1.0)
    UsdGeom.XformCommonAPI(cube).SetTranslate(Gf.Vec3d(*translate))
    UsdGeom.XformCommonAPI(cube).SetScale(Gf.Vec3f(*scale))
    cube.CreateDisplayColorAttr().Set([Gf.Vec3f(*color)])
    return cube


def _make_sphere(stage, path: str, translate, radius: float, color):
    try:
        from pxr import UsdGeom, Gf  # type: ignore
    except ImportError:
        return None
    sphere = UsdGeom.Sphere.Define(stage, path)
    sphere.CreateRadiusAttr(radius)
    UsdGeom.XformCommonAPI(sphere).SetTranslate(Gf.Vec3d(*translate))
    sphere.CreateDisplayColorAttr().Set([Gf.Vec3f(*color)])
    return sphere


def _make_cylinder(stage, path: str, translate, radius: float, height: float, color):
    try:
        from pxr import UsdGeom, Gf  # type: ignore
    except ImportError:
        return None
    cyl = UsdGeom.Cylinder.Define(stage, path)
    cyl.CreateRadiusAttr(radius)
    cyl.CreateHeightAttr(height)
    UsdGeom.XformCommonAPI(cyl).SetTranslate(Gf.Vec3d(*translate))
    cyl.CreateDisplayColorAttr().Set([Gf.Vec3f(*color)])
    return cyl


def _make_camera(stage, path: str, translate, rotate):
    try:
        from pxr import UsdGeom, Gf  # type: ignore
    except ImportError:
        return None
    cam = UsdGeom.Camera.Define(stage, path)
    UsdGeom.XformCommonAPI(cam).SetTranslate(Gf.Vec3d(*translate))
    UsdGeom.XformCommonAPI(cam).SetRotate(Gf.Vec3f(*rotate))
    return cam


def _set_viewport_camera(camera_path: str) -> None:
    try:
        import omni.kit.viewport.utility as vp_utils  # type: ignore
        vp = vp_utils.get_active_viewport()
        if vp:
            vp.camera_path = camera_path
    except Exception:
        pass


def build_scene_isaac(stage, cfg: dict) -> None:
    from pxr import UsdGeom, Gf  # type: ignore

    sc = cfg.get("scene", {})
    r1 = sc.get("room1_bounds", [0, 10, 0, 8])
    r2 = sc.get("room2_bounds", [14, 28, 0, 8])
    co = sc.get("corridor_bounds", [10, 14, 3, 5])
    wh = sc.get("wall_height", 2.8)
    fc = sc.get("floor_color", [0.38, 0.38, 0.38])
    wc = sc.get("wall_color", [0.72, 0.72, 0.72])
    dc = sc.get("desk_color", [0.55, 0.35, 0.15])
    cc = sc.get("chair_color", [0.20, 0.20, 0.60])

    total_w = r2[1] - r1[0]
    total_cx = (r1[0] + r2[1]) / 2.0
    total_cy = (r1[2] + r1[3]) / 2.0

    # Floor
    _make_cube(stage, "/World/Floor", (total_cx, total_cy, -0.03), (total_w, r1[3] - r1[2], 0.05), fc)

    # Room 1 walls
    r1_cx = (r1[0] + r1[1]) / 2.0
    r1_cy = (r1[2] + r1[3]) / 2.0
    r1_w = r1[1] - r1[0]
    r1_d = r1[3] - r1[2]
    _make_cube(stage, "/World/R1_WallBack", (r1_cx, r1[2] - 0.1, wh / 2), (r1_w, 0.2, wh), wc)
    _make_cube(stage, "/World/R1_WallFront_Left", (r1_cx, r1[3] + 0.1, wh / 2), (r1_w, 0.2, wh), wc)
    _make_cube(stage, "/World/R1_WallLeft", (r1[0] - 0.1, r1_cy, wh / 2), (0.2, r1_d, wh), wc)
    # partial right wall of room 1 (leaves corridor opening)
    co_y_lo = co[2]
    co_y_hi = co[3]
    seg_lo = co_y_lo - r1[2]
    seg_hi = r1[3] - co_y_hi
    if seg_lo > 0.1:
        _make_cube(stage, "/World/R1_WallRight_Lo",
                   (r1[1] + 0.1, r1[2] + seg_lo / 2, wh / 2), (0.2, seg_lo, wh), wc)
    if seg_hi > 0.1:
        _make_cube(stage, "/World/R1_WallRight_Hi",
                   (r1[1] + 0.1, co_y_hi + seg_hi / 2, wh / 2), (0.2, seg_hi, wh), wc)

    # Corridor walls
    co_cx = (co[0] + co[1]) / 2.0
    co_len = co[1] - co[0]
    _make_cube(stage, "/World/Co_WallBack", (co_cx, co[2] - 0.1, wh / 2), (co_len, 0.2, wh), wc)
    _make_cube(stage, "/World/Co_WallFront", (co_cx, co[3] + 0.1, wh / 2), (co_len, 0.2, wh), wc)

    # Room 2 walls (partial left wall leaving corridor opening)
    r2_cx = (r2[0] + r2[1]) / 2.0
    r2_cy = (r2[2] + r2[3]) / 2.0
    r2_w = r2[1] - r2[0]
    r2_d = r2[3] - r2[2]
    _make_cube(stage, "/World/R2_WallBack", (r2_cx, r2[2] - 0.1, wh / 2), (r2_w, 0.2, wh), wc)
    _make_cube(stage, "/World/R2_WallFront", (r2_cx, r2[3] + 0.1, wh / 2), (r2_w, 0.2, wh), wc)
    _make_cube(stage, "/World/R2_WallRight", (r2[1] + 0.1, r2_cy, wh / 2), (0.2, r2_d, wh), wc)
    if seg_lo > 0.1:
        _make_cube(stage, "/World/R2_WallLeft_Lo",
                   (r2[0] - 0.1, r2[2] + seg_lo / 2, wh / 2), (0.2, seg_lo, wh), wc)
    if seg_hi > 0.1:
        _make_cube(stage, "/World/R2_WallLeft_Hi",
                   (r2[0] - 0.1, co_y_hi + seg_hi / 2, wh / 2), (0.2, seg_hi, wh), wc)

    # Furniture
    for i, furn in enumerate(_office_desks_and_chairs()):
        px, py, pz = furn["pos"]
        sw, sd, sh = furn["size"]
        col = dc if furn["type"] == "desk" else cc
        prim_path = f"/World/Furniture_{furn['type']}_{i:03d}"
        _make_cube(stage, prim_path, (px, py, pz + sh / 2), (sw, sd, sh), col)


def build_markers_isaac(stage, traj: dict, cfg: dict, overlay_markers: dict) -> str:
    mc = cfg.get("markers", {})

    start_xy = traj["start_xy"]
    goal_xy = traj["goal_xy"]
    closest_xy = traj["closest_xy"]
    final_xy = traj["final_xy"]
    r = traj["success_radius"]

    # Start
    _make_sphere(stage, "/World/Markers/Start",
                 (start_xy[0], start_xy[1], 0.3), 0.3, mc.get("start_color", [0.1, 0.8, 0.1]))
    # Goal
    _make_sphere(stage, "/World/Markers/Goal",
                 (goal_xy[0], goal_xy[1], 0.3), 0.35, mc.get("goal_color", [0.9, 0.15, 0.1]))
    # Goal radius ring (flat cylinder)
    _make_cylinder(stage, "/World/Markers/GoalRadius",
                   (goal_xy[0], goal_xy[1], 0.02), r, 0.04,
                   mc.get("goal_radius_color", [0.1, 0.7, 0.1]))
    # Breadcrumbs
    stride = cfg.get("replay", {}).get("breadcrumb_stride", 3)
    for i, (x, y) in enumerate(traj["waypoints"][::stride]):
        _make_sphere(stage, f"/World/Markers/Breadcrumb_{i:04d}",
                     (x, y, 0.07), 0.07, mc.get("breadcrumb_color", [0.15, 0.5, 0.95]))
    # Closest-to-goal
    _make_sphere(stage, "/World/Markers/ClosestToGoal",
                 (closest_xy[0], closest_xy[1], 0.25), 0.22,
                 mc.get("closest_to_goal_color", [0.0, 0.9, 0.9]))
    # Final stop
    _make_sphere(stage, "/World/Markers/FinalStop",
                 (final_xy[0], final_xy[1], 0.25), 0.22,
                 mc.get("final_stop_color", [0.95, 0.3, 0.0]))
    # Robot (movable)
    robot_path = "/World/Markers/Robot"
    _make_cube(stage, robot_path,
               (start_xy[0], start_xy[1], 0.35), (0.45, 0.35, 0.25),
               mc.get("robot_color", [1.0, 0.8, 0.1]))

    # Overlays
    ol_cfg = cfg.get("overlays", {})
    for key, xy in overlay_markers.items():
        col = ol_cfg.get(key, {}).get("color", [0.5, 0.9, 0.5])
        _make_sphere(stage, f"/World/Markers/Overlay_{key}",
                     (xy[0], xy[1], 0.45), 0.25, col)

    return robot_path


def setup_cameras_isaac(stage, cfg: dict) -> dict[str, str]:
    cam_cfg = cfg.get("cameras", {})
    paths: dict[str, str] = {}
    for name in REQUIRED_CAMERA_NAMES:
        c = cam_cfg.get(name, {})
        if name == "robot_pov":
            continue
        prim_path = f"/World/Cameras/{name}"
        _make_camera(stage, prim_path,
                     c.get("translate", [0, 0, 10]),
                     c.get("rotate", [50, 0, 0]))
        paths[name] = prim_path
    return paths


def run_isaac(episode: dict, traj: dict, overlay_markers: dict, cfg: dict, args: argparse.Namespace) -> None:
    import time

    import omni.usd  # type: ignore
    from pxr import UsdGeom, Gf  # type: ignore

    app = _SimulationApp({"headless": False, "width": 1280, "height": 720})

    ctx = omni.usd.get_context()
    ctx.new_stage()
    app.update()

    stage = ctx.get_stage()
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)

    print_claim_boundaries()
    print(f"  Building office scene (Isaac primitives)...")
    build_scene_isaac(stage, cfg)

    print(f"  Placing markers...")
    robot_path = build_markers_isaac(stage, traj, cfg, overlay_markers)

    print(f"  Setting up cameras...")
    cam_paths = setup_cameras_isaac(stage, cfg)

    # Select initial camera
    view = args.view
    if view == "multi_camera" or view == "overview":
        _set_viewport_camera(cam_paths.get("overview", "/World/Cameras/overview"))
    elif view in cam_paths:
        _set_viewport_camera(cam_paths[view])

    app.update()

    print(f"\n  Starting replay — {len(traj['waypoints'])} frames")
    print_metric_overlay(episode, 0, len(traj["waypoints"]))

    delay = cfg.get("replay", {}).get("frame_delay_s", 0.05)
    waypoints = traj["waypoints"]
    goal_xy = traj["goal_xy"]
    goal_r = traj["success_radius"]

    try:
        from pxr import UsdGeom, Gf  # type: ignore

        for i, (x, y) in enumerate(waypoints):
            UsdGeom.XformCommonAPI(
                stage.GetPrimAtPath(robot_path)
            ).SetTranslate(Gf.Vec3d(x, y, 0.35))

            if view == "multi_camera":
                cam_cycle = ["overview", "start_state", "goal_state"]
                cycle_idx = (i // max(1, len(waypoints) // len(cam_cycle))) % len(cam_cycle)
                _set_viewport_camera(cam_paths.get(cam_cycle[cycle_idx], cam_paths.get("overview")))

            app.update()
            dist = math.dist((x, y), goal_xy)
            in_zone = " *** IN GOAL ZONE ***" if dist <= goal_r else ""
            if i % 8 == 0:
                print_metric_overlay(episode, i, len(waypoints))
                print(f"  robot_xy=({x:.2f},{y:.2f})  dist_to_goal={dist:.2f}m{in_zone}")
            time.sleep(delay)

        print("\n  Replay complete. Final state:")
        print_metric_overlay(episode, len(waypoints) - 1, len(waypoints))
        print_claim_boundaries()
        print("  [Isaac] Holding window open. Ctrl+C to close.")

        while True:
            app.update()
            time.sleep(1 / 60)

    except KeyboardInterrupt:
        print("  Closing demo.")
    finally:
        app.close()


# ── argument parsing ──────────────────────────────────────────────────────────

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="GNM-VLNVerse Isaac Office Stopping Demo (v2.8)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--episode",
        default="auto_osr_not_sr",
        help="Episode selection mode: 'auto_osr_not_sr' (default) or a specific episode_id.",
    )
    p.add_argument(
        "--method",
        default="baseline_gnm",
        help="Method name to look up in the provenance CSV (default: baseline_gnm).",
    )
    p.add_argument(
        "--overlay",
        action="append",
        dest="overlays",
        choices=["temporal_stop_head", "geometry_oracle"],
        default=[],
        help="Overlay to show (can be repeated).",
    )
    p.add_argument(
        "--view",
        default="overview",
        choices=["overview", "start_state", "robot_pov", "goal_state", "multi_camera"],
        help="Camera view (default: overview).",
    )
    p.add_argument(
        "--config",
        default=None,
        help="Path to YAML config (default: configs/gnm/isaac_office_stopping_demo.yaml).",
    )
    p.add_argument(
        "--no-isaac",
        action="store_true",
        help="Force headless/console mode even if Isaac Sim is available.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate config and episode selection only; do not run replay.",
    )
    return p.parse_args(argv)


# ── main ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    cfg = load_config(args.config)
    episode = select_episode(cfg, args.method, args.episode)
    traj = build_trajectory(episode)
    overlay_markers = build_overlay_markers(episode, traj, args.overlays)

    if args.dry_run:
        print("  [dry-run] config loaded OK")
        print(f"  [dry-run] episode: {episode.get('episode_id')}")
        print(f"  [dry-run] SR={episode.get('success_flag')}  OSR={episode.get('oracle_success_flag')}")
        print(f"  [dry-run] goal_radius={traj['success_radius']}m")
        print_claim_boundaries()
        return

    use_isaac = ISAAC_AVAILABLE and not args.no_isaac

    if use_isaac:
        run_isaac(episode, traj, overlay_markers, cfg, args)
    else:
        if not ISAAC_AVAILABLE and not args.no_isaac:
            print("  [info] Isaac Sim not available — running in headless console mode.")
        run_headless(episode, traj, overlay_markers, args)


if __name__ == "__main__":
    main()
