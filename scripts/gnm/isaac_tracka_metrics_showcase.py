#!/usr/bin/env python3
"""
Track A Isaac Sim metrics showcase.

This script opens Isaac Sim, renders a moving Track A trajectory scene, and shows
validated Year 1 stopping-reliability metrics inside an Isaac UI panel. It is
intended for recording a 30--60 second research demonstration from the local
GNM-VLNVerse repository.

Scope:
- Uses project trajectory data when available under datasets/vlntube/train.
- Uses validated Track A aggregate metrics from the research audit CSV when
  available, with fixed fallbacks matching the current paper/report values.
- Visualises the baseline stopping failure and temporal stop-head improvement.
- Does not claim closed-loop Yahboom execution or full Track B completion.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import pickle
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# Isaac Sim must be started before importing most omni modules.
try:
    from isaacsim import SimulationApp
except Exception:  # Isaac 2023/2024 compatibility path
    from omni.isaac.kit import SimulationApp  # type: ignore


@dataclass
class MethodMetrics:
    sr: float
    osr: float
    ne: float


DEFAULT_METRICS: Dict[str, MethodMetrics] = {
    "Baseline GNM": MethodMetrics(sr=20.0, osr=46.7, ne=6.51),
    "Hand-tuned waypoint gate": MethodMetrics(sr=26.7, osr=26.7, ne=5.34),
    "Logistic stop head": MethodMetrics(sr=20.0, osr=46.7, ne=6.51),
    "Temporal neural stop head": MethodMetrics(sr=33.3, osr=33.3, ne=4.47),
    "Geometry-aware oracle": MethodMetrics(sr=46.7, osr=46.7, ne=3.79),
}

SUCCESS_RADIUS_M = 3.0
REQUIRED_TOPICS = ["/camera/image_raw", "/odom", "/tf", "/scan", "/cmd_vel"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Isaac Track A metrics showcase")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--duration", type=float, default=60.0, help="Target demo duration in seconds")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--speed", type=float, default=1.0, help="Animation speed multiplier")
    parser.add_argument("--trajectory", type=Path, default=None, help="Optional explicit traj_data.pkl path")
    parser.add_argument("--metric-csv", type=Path, default=None, help="Optional all-methods provenance CSV")
    parser.add_argument("--hold", action="store_true", help="Keep Isaac Sim open after the scripted demo ends.")
    parser.add_argument("--save-stage", action="store_true")
    parser.add_argument("--headless", action="store_true", help="Use only for automated smoke tests")
    parser.add_argument("--scene-usd", default="", help="Optional USD/USDA/USDC scene file or URL to load as the Isaac background.")
    return parser.parse_args()


def normalise_method_name(raw: str) -> str:
    key = raw.strip().lower().replace("_", " ").replace("-", " ")
    if "baseline" in key or key == "gnm":
        return "Baseline GNM"
    if "hand" in key or "waypoint" in key:
        return "Hand-tuned waypoint gate"
    if "logistic" in key:
        return "Logistic stop head"
    if "temporal" in key or "neural" in key:
        return "Temporal neural stop head"
    if "oracle" in key or "geometry" in key:
        return "Geometry-aware oracle"
    return raw.strip()


def _as_float(value: object) -> Optional[float]:
    try:
        if value is None:
            return None
        text = str(value).strip().replace("%", "")
        if text == "":
            return None
        return float(text)
    except Exception:
        return None


def load_metrics(repo_root: Path, metric_csv: Optional[Path]) -> Dict[str, MethodMetrics]:
    metrics = dict(DEFAULT_METRICS)
    candidates: List[Path] = []
    if metric_csv:
        candidates.append(metric_csv)
    candidates.extend([
        repo_root / "results/research_audit/tracka_all_methods_per_episode_metric_provenance.csv",
        repo_root / "results/bo_reviewer_packet/tracka_all_methods_per_episode_metric_provenance.csv",
    ])

    for path in candidates:
        if not path.exists():
            continue
        rows: Dict[str, List[Dict[str, str]]] = {}
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                method = normalise_method_name(
                    row.get("method")
                    or row.get("Method")
                    or row.get("policy")
                    or row.get("stop_policy")
                    or row.get("name")
                    or ""
                )
                if method:
                    rows.setdefault(method, []).append(row)

        for method, method_rows in rows.items():
            # Prefer per-episode columns if present.
            final_flags: List[float] = []
            oracle_flags: List[float] = []
            final_distances: List[float] = []
            for row in method_rows:
                final_success = row.get("final_success") or row.get("success") or row.get("sr_success")
                oracle_success = row.get("oracle_success") or row.get("osr_success")
                final_distance = (
                    row.get("final_distance_m")
                    or row.get("final_distance")
                    or row.get("navigation_error_m")
                    or row.get("ne")
                )
                fs = _as_float(final_success)
                os = _as_float(oracle_success)
                fd = _as_float(final_distance)
                if fs is not None:
                    final_flags.append(1.0 if fs >= 0.5 else 0.0)
                if os is not None:
                    oracle_flags.append(1.0 if os >= 0.5 else 0.0)
                if fd is not None:
                    final_distances.append(fd)

            if final_flags and oracle_flags and final_distances:
                metrics[method] = MethodMetrics(
                    sr=100.0 * sum(final_flags) / len(final_flags),
                    osr=100.0 * sum(oracle_flags) / len(oracle_flags),
                    ne=sum(final_distances) / len(final_distances),
                )
        return metrics
    return metrics


def find_trajectory(repo_root: Path, explicit: Optional[Path]) -> Tuple[Path, List[Tuple[float, float]]]:
    if explicit:
        candidates = [explicit]
    else:
        candidates = sorted((repo_root / "datasets/vlntube/train").glob("*/traj_data.pkl"))
        candidates += sorted((repo_root / "datasets/vlntube/val").glob("*/traj_data.pkl"))
        candidates += sorted((repo_root / "datasets/vlntube").glob("**/traj_data.pkl"))
    if not candidates:
        raise FileNotFoundError("No traj_data.pkl found under datasets/vlntube. Link VLNTube data first.")

    for path in candidates:
        try:
            with path.open("rb") as f:
                data = pickle.load(f)
            arrays: List[object] = []
            if isinstance(data, dict):
                for key in ["position", "positions", "pos", "xy", "trajectory", "poses"]:
                    if key in data:
                        arrays.append(data[key])
                arrays.extend(data.values())
            else:
                arrays.append(data)
            for arr in arrays:
                if hasattr(arr, "shape") and len(arr.shape) >= 2 and arr.shape[1] >= 2:
                    return path, [(float(p[0]), float(p[1])) for p in arr]
                if isinstance(arr, (list, tuple)) and arr and isinstance(arr[0], (list, tuple)) and len(arr[0]) >= 2:
                    return path, [(float(p[0]), float(p[1])) for p in arr]
        except Exception:
            continue
    raise KeyError("Could not extract an x/y trajectory from available traj_data.pkl files")


def resample_path(points: Sequence[Tuple[float, float]], n: int) -> List[Tuple[float, float]]:
    if len(points) <= 1:
        return list(points)
    distances = [0.0]
    for i in range(1, len(points)):
        dx = points[i][0] - points[i - 1][0]
        dy = points[i][1] - points[i - 1][1]
        distances.append(distances[-1] + math.hypot(dx, dy))
    total = distances[-1]
    if total <= 1e-9:
        return [points[0]] * n
    out: List[Tuple[float, float]] = []
    j = 1
    for k in range(n):
        target = total * k / max(n - 1, 1)
        while j < len(distances) - 1 and distances[j] < target:
            j += 1
        d0, d1 = distances[j - 1], distances[j]
        t = 0.0 if d1 == d0 else (target - d0) / (d1 - d0)
        x = points[j - 1][0] + t * (points[j][0] - points[j - 1][0])
        y = points[j - 1][1] + t * (points[j][1] - points[j - 1][1])
        out.append((x, y))
    return out


def map_path_into_stage(points: Sequence[Tuple[float, float]]) -> List[Tuple[float, float]]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    cx = (min(xs) + max(xs)) / 2.0
    cy = (min(ys) + max(ys)) / 2.0
    span = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
    scale = min(13.0 / span, 1.0)
    return [((x - cx) * scale, (y - cy) * scale) for x, y in points]



def add_showcase_cameras(stage):
    """Create camera views that show start, goal, path, and metric evidence clearly."""
    from pxr import UsdGeom, Gf

    cam_top = UsdGeom.Camera.Define(stage, "/World/Camera_Showcase_Top")
    cam_top.AddTranslateOp().Set(Gf.Vec3d(0.0, -1.5, 18.0))
    cam_top.AddRotateXYZOp().Set(Gf.Vec3f(0.0, 0.0, 0.0))
    cam_top.GetFocalLengthAttr().Set(18.0)
    cam_top.GetHorizontalApertureAttr().Set(34.0)

    cam_chase = UsdGeom.Camera.Define(stage, "/World/Camera_Showcase_Chase")
    cam_chase.AddTranslateOp().Set(Gf.Vec3d(4.0, -8.0, 5.0))
    cam_chase.AddRotateXYZOp().Set(Gf.Vec3f(60.0, 0.0, 28.0))
    cam_chase.GetFocalLengthAttr().Set(20.0)
    cam_chase.GetHorizontalApertureAttr().Set(34.0)

    print("[INFO] Added Camera_Showcase_Top and Camera_Showcase_Chase")



def add_scene_usd_reference(stage, scene_usd: str):
    """Reference a USD scene background while keeping the Track A evidence overlay."""
    if not scene_usd:
        print("[INFO] No external scene USD provided; using procedural Track A evidence stage.")
        return None

    try:
        from pxr import UsdGeom
        prim_path = "/World/SceneBackground"
        scene = UsdGeom.Xform.Define(stage, prim_path)
        scene.GetPrim().GetReferences().AddReference(scene_usd)
        print(f"[INFO] Referenced scene background: {scene_usd}")
        return prim_path
    except Exception as exc:
        print(f"[WARN] Could not reference scene USD: {scene_usd}")
        print(f"[WARN] Reason: {exc}")
        print("[WARN] Continuing with procedural Track A evidence stage.")
        return None


def main() -> None:
    args = parse_args()
    app = SimulationApp({"headless": args.headless, "width": args.width, "height": args.height})

    import omni.usd
    from pxr import Gf, Sdf, UsdGeom, UsdLux

    try:
        import omni.ui as ui
    except Exception:
        ui = None

    repo_root = args.repo_root.resolve()
    metrics = load_metrics(repo_root, args.metric_csv)
    trajectory_path, raw_points = find_trajectory(repo_root, args.trajectory)
    raw_points = resample_path(raw_points, max(80, int(args.duration * args.fps)))
    mapped = map_path_into_stage(raw_points)

    # Force a visual stopping-failure demonstration: the goal is placed at a point
    # the path enters before the final frame, so the baseline segment passes through
    # the success radius but does not terminate there. This visualises the validated
    # SR--OSR failure mode while preserving the real path geometry.
    goal_index = max(10, int(0.62 * len(mapped)))
    success_radius_stage = 1.15
    sx, sy = mapped[0]
    gx, gy = mapped[goal_index]
    fx, fy = mapped[-1]

    ctx = omni.usd.get_context()
    ctx.new_stage()
    app.update()
    stage = ctx.get_stage()
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)

    def set_color(geom, rgb):
        geom.CreateDisplayColorAttr().Set([Gf.Vec3f(*rgb)])

    def make_cube(path: str, translate, scale, color):
        cube = UsdGeom.Cube.Define(stage, path)
        cube.CreateSizeAttr(1.0)
        UsdGeom.XformCommonAPI(cube).SetTranslate(Gf.Vec3d(*translate))
        UsdGeom.XformCommonAPI(cube).SetScale(Gf.Vec3f(*scale))
        set_color(cube, color)
        return cube

    def make_sphere(path: str, translate, radius, color):
        sphere = UsdGeom.Sphere.Define(stage, path)
        sphere.CreateRadiusAttr(radius)
        UsdGeom.XformCommonAPI(sphere).SetTranslate(Gf.Vec3d(*translate))
        set_color(sphere, color)
        return sphere

    def make_text(path: str, text: str, translate, scale=0.35, color=(0.05, 0.05, 0.05)):
        # Omniverse Text prims vary by Isaac version. Keep this best-effort and
        # rely on the Isaac UI HUD plus 3D bars if the Text prim is unavailable.
        try:
            prim = stage.DefinePrim(path, "Text")
            prim.CreateAttribute("text", Sdf.ValueTypeNames.String).Set(text)
            prim.CreateAttribute("fontSize", Sdf.ValueTypeNames.Float).Set(24.0)
            prim.CreateAttribute("color", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
            UsdGeom.XformCommonAPI(prim).SetTranslate(Gf.Vec3d(*translate))
            UsdGeom.XformCommonAPI(prim).SetScale(Gf.Vec3f(scale, scale, scale))
            UsdGeom.XformCommonAPI(prim).SetRotate(Gf.Vec3f(70, 0, 0))
            return prim
        except Exception:
            return None

    # Stage environment.
    add_scene_usd_reference(stage, args.scene_usd)
    make_cube("/World/Floor", (0, 0, -0.03), (24, 18, 0.04), (0.78, 0.78, 0.78))
    make_cube("/World/Wall_Back", (0, 8.6, 1.05), (24, 0.18, 2.1), (0.64, 0.64, 0.66))
    make_cube("/World/Wall_Left", (-10.7, 0, 1.05), (0.18, 17, 2.1), (0.64, 0.64, 0.66))
    make_cube("/World/Obstacle_Block_A", (2.5, -1.2, 0.45), (1.1, 1.1, 0.9), (0.70, 0.24, 0.24))
    make_cube("/World/Obstacle_Block_B", (-2.4, 2.1, 0.45), (1.3, 0.8, 0.9), (0.27, 0.31, 0.72))

    # Start, goal, success radius ring, and trajectory breadcrumbs.
    make_sphere("/World/Start_Green", (sx, sy, 0.22), 0.32, (0.08, 0.70, 0.18))
    make_sphere("/World/Goal_Red", (gx, gy, 0.25), 0.34, (0.90, 0.08, 0.08))
    for j in range(48):
        theta = 2 * math.pi * j / 48
        make_sphere(
            f"/World/Goal_Radius_3m_{j:02d}",
            (gx + success_radius_stage * math.cos(theta), gy + success_radius_stage * math.sin(theta), 0.055),
            0.045,
            (1.0, 0.55, 0.05),
        )
    for i, (x, y) in enumerate(mapped[:: max(1, len(mapped) // 45)]):
        make_sphere(f"/World/TrackA_Path_{i:03d}", (x, y, 0.07), 0.075, (0.03, 0.45, 0.95))

    robot = make_cube("/World/GNM_Robot", (sx, sy, 0.32), (0.42, 0.32, 0.22), (1.0, 0.78, 0.08))
    stop_marker = make_sphere("/World/Temporal_Stop_Point", (gx, gy, 0.85), 0.18, (0.02, 0.80, 0.75))

    # 3D metric board. Values are intentionally encoded as geometry so they are
    # visible even if Text prim rendering is unavailable.
    board_x, board_y = -8.2, -6.7
    make_cube("/World/Metrics_Board", (board_x + 2.0, board_y, 1.25), (4.6, 0.08, 1.7), (0.10, 0.11, 0.13))
    make_text("/World/Metrics_Title", "Track A stopping reliability", (board_x, board_y - 0.1, 2.55), 0.25, (1, 1, 1))
    bar_specs = [
        ("Baseline_SR", metrics["Baseline GNM"].sr, (0.2, 0.8, 0.2)),
        ("Baseline_OSR", metrics["Baseline GNM"].osr, (0.1, 0.45, 0.95)),
        ("Temporal_SR", metrics["Temporal neural stop head"].sr, (0.9, 0.7, 0.1)),
        ("Oracle_UB", metrics["Geometry-aware oracle"].sr, (0.55, 0.25, 0.85)),
    ]
    for i, (name, value, color) in enumerate(bar_specs):
        h = max(0.05, value / 100.0 * 1.6)
        x = board_x + 0.5 + i * 0.95
        safe_value = str(f"{value:.1f}").replace(".", "p")
        make_cube(f"/World/Metric_Bar_{name}_{safe_value}pct", (x, board_y - 0.18, 0.30 + h / 2), (0.30, 0.12, h), color)
        make_text(f"/World/Metric_Label_{name}", f"{name.replace('_', ' ')} {value:.1f}%", (x - 0.38, board_y - 0.28, 2.08), 0.13, (1, 1, 1))
    make_text(
        "/World/NE_Label",
        f"NE: baseline {metrics['Baseline GNM'].ne:.2f} m | temporal {metrics['Temporal neural stop head'].ne:.2f} m",
        (board_x - 0.15, board_y - 0.30, 1.86),
        0.14,
        (1, 1, 1),
    )

    # Lighting and cameras.
    light = UsdLux.DistantLight.Define(stage, "/World/Sun")
    light.CreateIntensityAttr(4500)
    UsdGeom.XformCommonAPI(light).SetRotate(Gf.Vec3f(-45, 0, 35))

    top_camera = UsdGeom.Camera.Define(stage, "/World/Camera_Top")
    UsdGeom.XformCommonAPI(top_camera).SetTranslate(Gf.Vec3d(0, -11.5, 9.5))
    UsdGeom.XformCommonAPI(top_camera).SetRotate(Gf.Vec3f(55, 0, 0))
    chase_camera = UsdGeom.Camera.Define(stage, "/World/Camera_Chase")
    UsdGeom.XformCommonAPI(chase_camera).SetTranslate(Gf.Vec3d(sx, sy - 5.0, 2.4))
    UsdGeom.XformCommonAPI(chase_camera).SetRotate(Gf.Vec3f(66, 0, 0))

    try:
        import omni.kit.viewport.utility as vp_utils

        viewport = vp_utils.get_active_viewport()
        if viewport:
            viewport.camera_path = "/World/Camera_Top"
    except Exception as e:
        print(f"Viewport camera set skipped: {e}")

    # Isaac UI HUD. This is the main readable overlay for recording.
    labels = {}
    if ui is not None and not args.headless:
        try:
            win = ui.Window("Track A Metrics HUD", width=470, height=330, visible=True)
            with win.frame:
                with ui.VStack(spacing=6, height=0):
                    labels["title"] = ui.Label("Accurate and Safety-Aware Visual Navigation", height=24)
                    labels["phase"] = ui.Label("Initialising Track A showcase", word_wrap=True)
                    labels["metrics"] = ui.Label("", word_wrap=True)
                    labels["episode"] = ui.Label("", word_wrap=True)
                    labels["scope"] = ui.Label("", word_wrap=True)
                    labels["topics"] = ui.Label("", word_wrap=True)
        except Exception as e:
            print(f"HUD creation skipped: {e}")

    def update_hud(phase: str, frame_idx: int, xy: Tuple[float, float], status: str) -> None:
        d = math.hypot(xy[0] - gx, xy[1] - gy)
        if labels:
            labels["phase"].text = f"{phase} | frame {frame_idx:03d} | distance-to-goal proxy {d:.2f}"
            labels["metrics"].text = (
                f"Baseline GNM: SR {metrics['Baseline GNM'].sr:.1f}% | OSR {metrics['Baseline GNM'].osr:.1f}% | "
                f"NE {metrics['Baseline GNM'].ne:.2f} m\n"
                f"Temporal stop head: SR {metrics['Temporal neural stop head'].sr:.1f}% | "
                f"OSR {metrics['Temporal neural stop head'].osr:.1f}% | NE {metrics['Temporal neural stop head'].ne:.2f} m\n"
                f"Geometry-aware oracle upper bound: SR/OSR {metrics['Geometry-aware oracle'].sr:.1f}% | NE {metrics['Geometry-aware oracle'].ne:.2f} m"
            )
            labels["episode"].text = f"Demo status: {status}\nTrajectory source: {trajectory_path.relative_to(repo_root) if trajectory_path.is_relative_to(repo_root) else trajectory_path}"
            labels["scope"].text = "Track A camera-only image-goal navigation. Pose/goal geometry is used for evaluation, not runtime model input."
            labels["topics"].text = "Year 2 topic contract: " + ", ".join(REQUIRED_TOPICS)

    print("TRACK A ISAAC METRICS SHOWCASE")
    print(f"Repository root: {repo_root}")
    print(f"Trajectory: {trajectory_path}")
    print(f"Frames: {len(mapped)}")
    print(f"Baseline SR={metrics['Baseline GNM'].sr:.1f}% OSR={metrics['Baseline GNM'].osr:.1f}% NE={metrics['Baseline GNM'].ne:.2f}m")
    print(f"Temporal SR={metrics['Temporal neural stop head'].sr:.1f}% NE={metrics['Temporal neural stop head'].ne:.2f}m")
    print("Recording target: 30--60 seconds using OBS or the supplied ffmpeg helper.")

    phase_1 = int(0.45 * len(mapped))
    phase_2 = int(0.72 * len(mapped))
    sleep_dt = max(0.001, 1.0 / max(args.fps, 1.0) / max(args.speed, 0.1))

    for i, (x, y) in enumerate(mapped):
        if i < phase_1:
            phase = "Baseline GNM replay: approaching goal region"
            status = "path following"
            current = (x, y)
        elif i < phase_2:
            phase = "Baseline stopping failure: enters goal radius but continues"
            status = "OSR true, SR false visualisation"
            current = (x, y)
        else:
            # Second segment: reset as temporal stop-head view and hold near goal.
            phase = "Temporal stop-head view: deployable stop decision near goal"
            status = "stop accepted inside goal radius"
            blend = min(1.0, (i - phase_2) / max(1, len(mapped) - phase_2))
            start2 = mapped[max(0, goal_index - 15)]
            current = (start2[0] + blend * (gx - start2[0]), start2[1] + blend * (gy - start2[1]))

        UsdGeom.XformCommonAPI(robot).SetTranslate(Gf.Vec3d(current[0], current[1], 0.32))
        UsdGeom.XformCommonAPI(chase_camera).SetTranslate(Gf.Vec3d(current[0], current[1] - 4.8, 2.2))
        update_hud(phase, i, current, status)
        if i % 15 == 0:
            d = math.hypot(current[0] - gx, current[1] - gy)
            print(f"frame={i:03d} phase='{phase}' x={current[0]:.2f} y={current[1]:.2f} d_goal_proxy={d:.2f}")
        app.update()
        time.sleep(sleep_dt)

    # Final hold for recording and screenshots.
    update_hud("Final summary", len(mapped), (gx, gy), "ready for screenshot / recording end")
    summary = {
        "title": "Accurate and Safety-Aware Visual Navigation: Track A Isaac Metrics Showcase",
        "trajectory": str(trajectory_path),
        "success_radius_m": SUCCESS_RADIUS_M,
        "metrics": {k: vars(v) for k, v in metrics.items()},
        "claim_boundary": [
            "validated Track A stopping-reliability evidence",
            "camera-only image-goal navigation scope",
            "not a completed closed-loop Yahboom safety result",
            "not a global superiority claim over external navigation methods",
        ],
        "required_year2_topics": REQUIRED_TOPICS,
    }
    out_dir = repo_root / "paper/showcase/recordings"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "tracka_isaac_showcase_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if args.save_stage:
        stage_path = repo_root / "paper/showcase/recordings/tracka_isaac_metrics_showcase.usda"
        stage.GetRootLayer().Export(str(stage_path))
        print(f"Saved stage: {stage_path}")
    print("Demo complete. Holding Isaac window open. Press Ctrl+C in terminal to close.")
    try:
        while True:
            app.update()
            time.sleep(1 / 60)
    except KeyboardInterrupt:
        print("Closing Isaac showcase.")
    finally:
        app.close()


if __name__ == "__main__":
    main()
