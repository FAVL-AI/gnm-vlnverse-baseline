#!/usr/bin/env python3
"""
FleetSafe Live Supervisor Demo — real Isaac Sim + GNM / ViNT + CBF-QP safety filter.

Architecture
------------
  Isaac Sim camera  ──►  GNM / ViNT adapter  ──►  u_nom
                                                      │
                                           YahboomCBFFilter (CBF-QP)
                                                      │
                                                  u_safe ──► Isaac Sim robot

Telemetry: one JSON object per control step written to stdout.
The command-center backend reads stdout and broadcasts to the frontend via WebSocket.

Two modes
---------
  --mock      No Isaac required. Runs a kinematic corridor sim with synthetic
              camera images. Use this for UI testing / rapid iteration.

  (default)   Full Isaac AppLauncher — real physics, real Isaac Sim camera,
              real GNM / ViNT model inference. Requires:
                conda activate isaac
                python scripts/demo/run_supervisor_demo_isaac.py --model vint

Usage
-----
  # Mock mode (instant startup, no Isaac):
  python scripts/demo/run_supervisor_demo_isaac.py --mock --model vint

  # Real Isaac Sim:
  conda activate isaac
  python scripts/demo/run_supervisor_demo_isaac.py \\
      --model vint \\
      --scene hospital_corridor

  # Real Isaac, FleetSafe off (shows unfiltered navigation):
  python scripts/demo/run_supervisor_demo_isaac.py \\
      --model vint --no-fleetsafe

AppLauncher note
----------------
Isaac Sim's AppLauncher must be initialised BEFORE any isaaclab or omni import.
This script follows the same pattern as run_visualnav_benchmark_isaac.py.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

# ── Repo root ─────────────────────────────────────────────────────────────────
# NOTE: safety logger import happens after sys.path is set up (see below)

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from fleet_safe_vla.safety.certificate_logger import SafetyCertificateLogger  # noqa: E402

# ── Checkpoint registry ───────────────────────────────────────────────────────

_VNT = _REPO / "third_party" / "visualnav-transformer" / "model_weights"
_CHECKPOINTS: dict[str, Path] = {
    "gnm":   _VNT / "gnm"   / "gnm.pth",
    "vint":  _VNT / "vint"  / "vint.pth",
    "nomad": _VNT / "nomad" / "nomad.pth",
}

# ── stdout telemetry helpers ──────────────────────────────────────────────────

def emit(obj: dict) -> None:
    """Write one JSON line to stdout and flush immediately."""
    print(json.dumps(obj), flush=True)


def status(state: str, msg: str) -> None:
    emit({"type": "status", "state": state, "msg": msg})


# ── Camera image utilities ────────────────────────────────────────────────────

def _rgb_to_jpeg_b64(rgb: np.ndarray, quality: int = 72) -> str:
    """Encode (H, W, 3) uint8 RGB → data-URI base64 JPEG."""
    try:
        from PIL import Image
        buf = io.BytesIO()
        Image.fromarray(rgb.astype(np.uint8)).save(buf, format="JPEG", quality=quality)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""


def _zone(min_dist_m: float, d_safe: float) -> str:
    if min_dist_m > d_safe * 1.5:
        return "GREEN"
    if min_dist_m > d_safe:
        return "AMBER"
    return "RED"


def _is_blank_frame(rgb: np.ndarray, threshold: float = 5.0) -> bool:
    """Return True when mean pixel intensity is below threshold (black/blank frame)."""
    return float(np.mean(rgb)) < threshold


def _make_not_ready_image(w: int = 320, h: int = 240) -> np.ndarray:
    """Return a (h, w, 3) uint8 diagnostic image reading 'Isaac camera not ready'."""
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (w, h), (25, 25, 35))
        draw = ImageDraw.Draw(img)
        # Grid lines so the image is visually distinct from pure black
        for i in range(0, w, 20):
            draw.line([(i, 0), (i, h - 1)], fill=(45, 45, 55), width=1)
        for j in range(0, h, 20):
            draw.line([(0, j), (w - 1, j)], fill=(45, 45, 55), width=1)
        msg = "Isaac camera not ready"
        tx = max(4, w // 2 - len(msg) * 3)
        ty = h // 2 - 6
        draw.rectangle([tx - 4, ty - 4, tx + len(msg) * 6 + 4, ty + 14], fill=(60, 20, 20))
        draw.text((tx, ty), msg, fill=(220, 80, 80))
        return np.array(img, dtype=np.uint8)
    except Exception:
        arr = np.zeros((h, w, 3), dtype=np.uint8)
        arr[:, :, 0] = 30   # dark red tint — visually distinct from pure black
        return arr


# ── Argument parsing ──────────────────────────────────────────────────────────
# parse_known_args so Isaac's own AppLauncher flags pass through unmodified.

def _parse_args() -> tuple[argparse.Namespace, list[str]]:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    p.add_argument("--model",      default="vint",
                   choices=["gnm", "vint", "nomad", "mock"],
                   help="Navigation model. 'mock' skips Isaac.")
    p.add_argument("--scene",      default="hospital_corridor",
                   help="Scene name from hospital_scenes.SCENES")
    p.add_argument("--fleetsafe",  action=argparse.BooleanOptionalAction, default=True,
                   help="Enable FleetSafe CBF-QP filter (default: on)")
    p.add_argument("--mock",       action="store_true",
                   help="Skip Isaac; run kinematic mock sim")
    p.add_argument("--headless",   action=argparse.BooleanOptionalAction, default=False,
                   help="Suppress the Isaac Sim desktop window (default: window is shown)")
    p.add_argument("--stream",     action="store_true", default=False,
                   help="Also enable WebRTC livestream at http://localhost:49100")
    p.add_argument("--max-steps",  type=int, default=200)
    p.add_argument("--seed",       type=int, default=0)
    p.add_argument("--checkpoint", default=None,
                   help="Override checkpoint path")
    p.add_argument("--control-hz", type=float, default=4.0)
    p.add_argument("--v-max",      type=float, default=0.3,
                   help="Max forward velocity (m/s)")
    p.add_argument("--w-max",      type=float, default=0.7,
                   help="Max angular rate (rad/s)")
    p.add_argument("--d-safe",     type=float, default=0.50,
                   help="CBF safety margin (m) — conservative for demo")
    p.add_argument("--estop-dist", type=float, default=0.30,
                   help="Hard emergency-stop distance (m)")
    p.add_argument("--cert-log",   type=Path,
                   default=Path("results/certificates/isaac_supervisor_demo.jsonl"),
                   help="Path for per-step safety certificate JSONL log")
    p.add_argument("--no-cert-log", action="store_true",
                   help="Disable certificate logging")
    return p.parse_known_args()


# ── Mock simulation ───────────────────────────────────────────────────────────

def _make_firstperson_image(
    robot_x: float, robot_y: float, robot_yaw: float,
    obs_xy: np.ndarray, obs_r: np.ndarray,
    goal: np.ndarray,
    d_safe: float,
    img_w: int = 320, img_h: int = 240,
) -> str:
    """
    Render a first-person (egocentric) forward-facing view from the M3Pro camera.

    This is what GNM / ViNT / NoMaD receives as visual input: the scene as seen
    from the robot's front camera, not a top-down map.  Camera is mounted at
    0.13 m above the floor, 0.10 m forward of the robot centre (matching URDF).
    Horizontal FOV = 62°, perspective projection.
    """
    try:
        from PIL import Image, ImageDraw

        # ── Camera intrinsics (matching M3Pro URDF camera_link) ───────────────
        CAM_H   = 0.13        # height above floor (m)
        FOV_H   = math.radians(62)
        focal   = (img_w / 2.0) / math.tan(FOV_H / 2.0)
        cx      = img_w / 2.0
        horizon = img_h // 2  # horizon line at vertical centre

        # ── Hospital corridor geometry ────────────────────────────────────────
        HALF_W  = 1.5   # corridor half-width (m) — 3 m wide total
        CEIL_H  = 2.5   # ceiling height (m)
        MAX_D   = 12.0  # draw up to 12 m ahead

        # ── Colors ───────────────────────────────────────────────────────────
        C_CEIL_NEAR = (210, 208, 205)
        C_CEIL_FAR  = (185, 183, 180)
        C_FLOOR_FAR = (118, 113, 107)
        C_FLOOR_NEAR= ( 85,  80,  74)
        C_WALL      = (188, 184, 175)
        C_WALL_DARK = (155, 151, 143)

        img  = Image.new("RGB", (img_w, img_h), (180, 178, 174))
        draw = ImageDraw.Draw(img)

        # ── Helper: project robot-frame (fwd, left, ht) → pixel ──────────────
        def proj(fwd: float, left: float, ht: float) -> tuple[int, int] | None:
            if fwd < 0.05:
                return None
            sx = int(cx + (left / fwd) * focal)
            sy = int(horizon - ((ht - CAM_H) / fwd) * focal)
            return sx, sy

        def world_to_rf(wx: float, wy: float) -> tuple[float, float]:
            """World → robot frame (forward, left)."""
            dx, dy = wx - robot_x, wy - robot_y
            c, s   = math.cos(-robot_yaw), math.sin(-robot_yaw)
            return c * dx + s * dy, -s * dx + c * dy

        # ── Ceiling gradient (top half) ───────────────────────────────────────
        for row in range(horizon):
            t = row / max(1, horizon)           # 0=top, 1=horizon
            r = int(C_CEIL_NEAR[0] + (C_CEIL_FAR[0] - C_CEIL_NEAR[0]) * t)
            g = int(C_CEIL_NEAR[1] + (C_CEIL_FAR[1] - C_CEIL_NEAR[1]) * t)
            b = int(C_CEIL_NEAR[2] + (C_CEIL_FAR[2] - C_CEIL_NEAR[2]) * t)
            draw.line([(0, row), (img_w - 1, row)], fill=(r, g, b))

        # ── Floor gradient (bottom half) ──────────────────────────────────────
        for row in range(horizon, img_h):
            t = (row - horizon) / max(1, img_h - horizon)  # 0=horizon, 1=bottom
            r = int(C_FLOOR_FAR[0] + (C_FLOOR_NEAR[0] - C_FLOOR_FAR[0]) * t)
            g = int(C_FLOOR_FAR[1] + (C_FLOOR_NEAR[1] - C_FLOOR_FAR[1]) * t)
            b = int(C_FLOOR_FAR[2] + (C_FLOOR_NEAR[2] - C_FLOOR_FAR[2]) * t)
            draw.line([(0, row), (img_w - 1, row)], fill=(r, g, b))

        # ── Corridor walls as depth-sampled trapezoids ────────────────────────
        N_SLICES = 20
        ds = [MAX_D * (i + 1) / N_SLICES for i in range(N_SLICES)]

        for side, yw in [(+1, +HALF_W), (-1, -HALF_W)]:
            for i in range(len(ds) - 1):
                d0, d1 = ds[i], ds[i + 1]
                p_bot_near = proj(d0, yw, 0.0)
                p_top_near = proj(d0, yw, CEIL_H)
                p_bot_far  = proj(d1, yw, 0.0)
                p_top_far  = proj(d1, yw, CEIL_H)
                if not all((p_bot_near, p_top_near, p_bot_far, p_top_far)):
                    continue
                depth_t = d0 / MAX_D   # 0=near bright, 1=far dark
                shade   = int(255 * (1 - 0.35 * depth_t))
                wc      = C_WALL if side > 0 else C_WALL_DARK
                wc_s    = tuple(min(255, max(0, int(c * shade / 255))) for c in wc)
                poly    = [p_bot_near, p_top_near, p_top_far, p_bot_far]
                draw.polygon(poly, fill=wc_s)  # type: ignore[arg-type]

        # ── Floor tile grid (perspective-correct, depth cue) ─────────────────
        for d in [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 9.0]:
            pl = proj(d, -HALF_W, 0.0)
            pr = proj(d,  HALF_W, 0.0)
            if pl and pr:
                alpha = max(20, 80 - int(d * 6))
                line_c = tuple(max(0, c - alpha) for c in C_FLOOR_FAR)
                draw.line([pl, pr], fill=line_c, width=1)  # type: ignore[arg-type]
        # Longitudinal tile lines
        for y_off in [-1.0, -0.5, 0.0, 0.5, 1.0]:
            near = proj(0.3, y_off, 0.0)
            far  = proj(MAX_D, y_off, 0.0)
            if near and far:
                draw.line([near, far], fill=(98, 93, 87), width=1)

        # ── Ceiling fluorescent light strips ──────────────────────────────────
        for d in [1.5, 3.0, 5.0, 8.0]:
            lt = proj(d, -0.35, CEIL_H)
            rt = proj(d,  0.35, CEIL_H)
            if lt and rt:
                w = max(1, int(focal * 0.06 / d))
                draw.line([lt, rt], fill=(245, 245, 240), width=w)

        # ── Obstacles (depth-sorted, back to front) ───────────────────────────
        obs_items = []
        for (ox, oy), r in zip(obs_xy, obs_r):
            fwd, left = world_to_rf(ox, oy)
            if fwd > 0.15:
                obs_items.append((fwd, left, r))
        obs_items.sort(key=lambda t: -t[0])   # back-to-front

        for fwd, left, r in obs_items:
            half = r + 0.04
            ob_h = 1.60   # person-height obstacle (m)
            pts  = [
                proj(fwd, left - half,    0.0),
                proj(fwd, left + half,    0.0),
                proj(fwd, left + half,    ob_h),
                proj(fwd, left - half,    ob_h),
            ]
            if all(p is not None for p in pts):
                depth_shade = max(40, min(220, int(220 - fwd * 18)))
                in_danger   = fwd < d_safe
                fill_c      = (depth_shade, 60, 55) if in_danger else (depth_shade, depth_shade - 20, depth_shade - 30)
                draw.polygon(pts, fill=fill_c)  # type: ignore[arg-type]

                # Safety-ring outline when within CBF range
                if fwd < d_safe * 1.8:
                    cx_s = int(cx + (left / fwd) * focal)
                    cy_s = int(horizon - ((ob_h / 2.0 - CAM_H) / fwd) * focal)
                    ring_r = max(4, int(focal * (r + d_safe * 0.5) / fwd))
                    ring_c = (255, 60, 60) if in_danger else (255, 165, 0)
                    draw.ellipse(
                        [cx_s - ring_r, cy_s - ring_r,
                         cx_s + ring_r, cy_s + ring_r],
                        outline=ring_c, width=2,
                    )

        # ── Goal beacon ───────────────────────────────────────────────────────
        g_fwd, g_left = world_to_rf(float(goal[0]), float(goal[1]))
        if g_fwd > 0.1:
            gp = proj(g_fwd, g_left, 0.60)
            if gp:
                gr = max(4, int(focal * 0.18 / max(0.2, g_fwd)))
                draw.ellipse([gp[0] - gr, gp[1] - gr,
                              gp[0] + gr, gp[1] + gr],
                             fill=(30, 210, 90), outline=(80, 255, 130), width=2)
                draw.ellipse([gp[0] - 3, gp[1] - 3,
                              gp[0] + 3, gp[1] + 3], fill=(255, 255, 255))

        # ── HUD overlay: tiny camera label ───────────────────────────────────
        draw.rectangle([2, 2, 78, 11], fill=(0, 0, 0, 120))
        draw.text((4, 3), "CAM · FORWARD", fill=(180, 220, 180))

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=78)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""


def _run_mock(args: argparse.Namespace) -> None:
    """Kinematic corridor sim — no Isaac required."""
    from fleet_safe_vla.benchmarks.hospital_scenes import SCENES, get_scene_config
    scene = get_scene_config(args.scene)

    _cert_logger = (
        None if args.no_cert_log
        else SafetyCertificateLogger(args.cert_log)
    )

    status("starting", f"mock mode | scene={args.scene} model={args.model}")

    obs_xy = np.array(scene.obstacle_positions, dtype=np.float64)
    obs_r  = np.array(scene.obstacle_radii,     dtype=np.float64)
    goal   = np.array(scene.goal_xy,            dtype=np.float64)

    x, y, yaw = float(scene.start_xy[0]), float(scene.start_xy[1]), 0.0
    d_safe     = args.d_safe
    estop      = args.estop_dist
    dt         = 1.0 / args.control_hz

    interventions = 0
    collision     = False
    goal_reached  = False

    status("running", "mock episode started")

    for step in range(args.max_steps):
        t0 = time.perf_counter()
        robot_xy = np.array([x, y])

        # Surface distances to all obstacles
        dists = np.linalg.norm(obs_xy - robot_xy, axis=1) - obs_r if len(obs_r) else np.array([99.0])
        min_dist = float(np.min(dists))

        # Nominal proportional controller toward goal
        goal_angle = math.atan2(goal[1] - y, goal[0] - x)
        angle_err  = math.atan2(math.sin(goal_angle - yaw), math.cos(goal_angle - yaw))
        u_nom_vx   = float(args.v_max * max(0.0, math.cos(angle_err)))
        u_nom_wz   = float(min(args.w_max, max(-args.w_max, 1.5 * angle_err)))

        # Projected waypoints (robot frame)
        waypoints: list[list[float]] = [
            [round(u_nom_vx * dt * (i + 1), 3), round(u_nom_wz * dt * (i + 1) * 0.1, 3)]
            for i in range(3)
        ]

        # CBF safety filter (simplified analytic version for mock)
        intervened = False
        if args.fleetsafe:
            if min_dist < estop:
                u_safe_vx, u_safe_wz = 0.0, u_nom_wz
                intervened = True
                interventions += 1
            elif min_dist < d_safe:
                scale = (min_dist - estop) / max(1e-6, d_safe - estop)
                u_safe_vx = u_nom_vx * max(0.0, scale)
                u_safe_wz = u_nom_wz
                if abs(u_safe_vx - u_nom_vx) > 0.02:
                    intervened = True
                    interventions += 1
            else:
                u_safe_vx, u_safe_wz = u_nom_vx, u_nom_wz
        else:
            u_safe_vx, u_safe_wz = u_nom_vx, u_nom_wz

        # Kinematic integration
        x   += u_safe_vx * math.cos(yaw) * dt
        y   += u_safe_vx * math.sin(yaw) * dt
        yaw += u_safe_wz * dt

        inference_ms = (time.perf_counter() - t0) * 1000.0

        # Re-compute distances after move
        robot_xy = np.array([x, y])
        dists    = np.linalg.norm(obs_xy - robot_xy, axis=1) - obs_r if len(obs_r) else np.array([99.0])
        min_dist = float(np.min(dists))

        dist_to_goal = float(np.linalg.norm(goal - robot_xy))
        collision    = min_dist < -0.05
        goal_reached = dist_to_goal < 0.30

        camera_b64 = _make_firstperson_image(
            x, y, yaw, obs_xy, obs_r, goal, d_safe,
        )

        emit({
            "type": "frame",
            "step": step,
            "model": args.model,
            "fleetsafe_on": args.fleetsafe,
            "robot_x":   round(x, 4),
            "robot_y":   round(y, 4),
            "robot_yaw": round(yaw, 4),
            "raw_vx": round(u_nom_vx, 4),  "raw_vy": 0.0,  "raw_wz": round(u_nom_wz, 4),
            "safe_vx": round(u_safe_vx, 4), "safe_vy": 0.0, "safe_wz": round(u_safe_wz, 4),
            "intervened":          intervened,
            "min_dist_m":          round(min_dist, 4),
            "h_min":               round(min_dist ** 2 - d_safe ** 2, 4),
            "cbf_zone":            _zone(min_dist, d_safe),
            "intervention_count":  interventions,
            "waypoints":           waypoints,
            "inference_ms":        round(inference_ms, 2),
            "cbf_ms":              0.1,
            "collision":           collision,
            "goal_reached":        goal_reached,
            "dist_to_goal":        round(dist_to_goal, 4),
            "camera_b64":          camera_b64,
        })

        # ── Safety certificate (mock) ─────────────────────────────────────────
        if _cert_logger is not None:
            _h_min = round(min_dist ** 2 - d_safe ** 2, 4)
            _cert_logger.append_from_values(
                timestamp=step * dt,
                model_name=args.model,
                u_nom=[round(u_nom_vx, 4), round(u_nom_wz, 4)],
                u_safe=[round(u_safe_vx, 4), round(u_safe_wz, 4)],
                h_min=_h_min,
                min_dist_m=round(min_dist, 4),
                cbf_active=intervened,
                qp_status="optimal" if args.fleetsafe else "skipped",
                constraint_margin_min=round(max(0.0, _h_min * 0.1), 4),
                latency_ms=round(inference_ms, 2),
                safe=min_dist >= d_safe,
            )

        if collision or goal_reached:
            break

        time.sleep(max(0.0, dt - inference_ms / 1000.0))

    if _cert_logger is not None:
        _cert_logger.close()
        status("info", f"Safety certificates written to {_cert_logger.path} ({_cert_logger.count} steps)")

    emit({
        "type": "done",
        "collision": collision,
        "steps": step + 1,
        "summary": {
            "intervention_rate": round(interventions / max(1, step + 1), 3),
            "collision": collision,
            "goal_reached": goal_reached,
        },
    })


# ── Isaac Sim episode ─────────────────────────────────────────────────────────

def _run_isaac(args: argparse.Namespace) -> None:
    """Full Isaac Lab episode — called after AppLauncher is up."""

    # All downstream imports happen HERE, after AppLauncher.
    from fleet_safe_vla.benchmarks.hospital_scenes import SCENES, get_scene_config
    from fleet_safe_vla.envs.isaaclab.yahboom.m3pro_nav_env import IsaacNavBenchmarkEnv
    from fleet_safe_vla.integrations.visualnav_transformer.isaac_obs_adapter import (
        IsaacCameraObsAdapter,
    )
    from fleet_safe_vla.fleet_safety.yahboom_cbf import YahboomCBFConfig
    from fleet_safe_vla.integrations.visualnav_transformer.fleetsafe_wrapper import (
        FleetSafeWrapper,
    )

    scene = get_scene_config(args.scene)

    # ── Build adapter ─────────────────────────────────────────────────────────
    if args.model == "gnm":
        from fleet_safe_vla.integrations.visualnav_transformer.gnm_adapter import GNMAdapter
        adapter = GNMAdapter()
    elif args.model == "vint":
        from fleet_safe_vla.integrations.visualnav_transformer.vint_adapter import ViNTAdapter
        adapter = ViNTAdapter()
    elif args.model == "nomad":
        from fleet_safe_vla.integrations.visualnav_transformer.nomad_adapter import NoMaDAdapter
        adapter = NoMaDAdapter()
    else:
        # "mock" — straight-line adapter, no checkpoint
        from fleet_safe_vla.integrations.visualnav_transformer.base_adapter import (
            BaseVisualNavAdapter, ActionOutput,
        )

        class _MockAdapter(BaseVisualNavAdapter):
            model_name = "mock"
            image_size = (85, 64)
            context_size = 5
            def load_checkpoint(self, _path): pass
            def preprocess_observation(self, obs_imgs, goal_img): return {}
            def predict_action(self, _pre):
                return ActionOutput(
                    waypoints=np.array([[0.075, 0.0]]),
                    goal_reached=False,
                    raw_output={},
                    inference_ms=1.0,
                )
        adapter = _MockAdapter()

    if args.model != "mock":
        ckpt = Path(args.checkpoint) if args.checkpoint else _CHECKPOINTS.get(args.model)
        if ckpt is None or not ckpt.exists():
            emit({"type": "error", "msg": f"Checkpoint not found: {ckpt}"})
            return
        status("loading", f"loading {args.model} from {ckpt.name}")
        try:
            adapter.load_checkpoint(ckpt)
        except Exception as exc:
            emit({"type": "error", "msg": f"Failed to load checkpoint: {exc}"})
            return

    img_w, img_h   = getattr(adapter, "image_size", (85, 64))
    ctx_size        = getattr(adapter, "context_size", 5)

    # ── Build Isaac env ───────────────────────────────────────────────────────
    status("starting", f"launching Isaac env | scene={args.scene}")

    obs_positions_world = [np.array(p, dtype=np.float64) for p in scene.obstacle_positions]
    obs_radii           = list(scene.obstacle_radii)

    try:
        env = IsaacNavBenchmarkEnv(
            fixed_positions    = scene.obstacle_positions,
            obstacle_radii     = obs_radii,
            scene_name         = args.scene,
            max_episode_steps  = args.max_steps,
            control_hz         = args.control_hz,
            seed               = args.seed,
        )
    except Exception as exc:
        emit({"type": "error", "msg": f"IsaacNavBenchmarkEnv failed: {exc}"})
        return

    env.reset(seed=args.seed)
    env.teleport_to(scene.start_xy[0], scene.start_xy[1], yaw=0.0)
    has_cam = env.setup_camera(img_w, img_h)

    # ── Extra camera warm-up: wait up to 30 additional frames for a valid signal ──
    # setup_camera() already attempts 30 renders; this second pass catches cases
    # where RTX async compilation finishes slightly later.
    if has_cam:
        status("info", "Isaac camera warm-up: checking for first non-blank frame…")
        for _wi in range(30):
            _ft = env.get_rgb_frame()
            _mp = float(np.mean(_ft))
            if _mp > 5.0:
                status("info", f"Isaac camera ready after {_wi + 1} extra warm-up frames (mean={_mp:.1f})")
                break
        else:
            status("warn", "Isaac camera still blank after 30 extra warm-up frames — placeholder will be used")

    # Camera observation adapter
    cam_adapter = IsaacCameraObsAdapter(image_size=(img_w, img_h), context_size=ctx_size)
    cam_adapter.set_goal_image(IsaacCameraObsAdapter.make_checkerboard_goal(img_w, img_h))

    # ── FleetSafe wrapper with conservative demo parameters ───────────────────
    # smoothing=0.2 is critical — default 0.7 is too slow to stop for demo safety.
    cbf_cfg = YahboomCBFConfig(
        d_safe_m      = args.d_safe,
        estop_dist_m  = args.estop_dist,
        max_linear_ms = args.v_max,
        smoothing     = 0.2,    # Low smoothing = fast reaction (important for demo)
        alpha         = 2.0,    # Stronger CBF decay keeps robot away from barrier
    )

    wrapper: FleetSafeWrapper | None = None
    if args.fleetsafe:
        wrapper = FleetSafeWrapper(
            adapter,
            cbf_config  = cbf_cfg,
            v_max       = args.v_max,
            w_max       = args.w_max,
            control_hz  = args.control_hz,
        )

    goal_xy       = np.array(scene.goal_xy, dtype=np.float64)
    interventions = 0
    collision     = False
    goal_reached  = False
    min_dist      = 99.0

    _cert_logger = (
        None if args.no_cert_log
        else SafetyCertificateLogger(args.cert_log)
    )

    status("running", f"{args.model} + FleetSafe={args.fleetsafe} | {args.scene}")

    for step in range(args.max_steps):
        t0 = time.perf_counter()

        # Camera frame
        frame_rgb = (
            env.get_rgb_frame() if has_cam
            else IsaacCameraObsAdapter.make_random_obs(img_w, img_h, seed=args.seed + step)
        )
        # Log shape/stats for the first 5 frames so blank-camera issues are diagnosable
        if step < 5 and has_cam:
            print(
                f"[demo] step={step} frame shape={frame_rgb.shape} dtype={frame_rgb.dtype} "
                f"min={int(frame_rgb.min())} max={int(frame_rgb.max())} "
                f"mean={float(np.mean(frame_rgb)):.1f}",
                file=sys.stderr, flush=True,
            )
        cam_adapter.push_frame(frame_rgb)
        obs_imgs, goal_img = cam_adapter.get_context()
        preprocessed = adapter.preprocess_observation(obs_imgs, goal_img)

        # Robot state
        robot_pose = env.get_robot_pose()          # (x, y, yaw)
        robot_xy   = np.array(robot_pose[:2], dtype=np.float64)
        obs_vec    = getattr(env, "_last_obs", np.zeros(47, dtype=np.float32))

        if wrapper is not None:
            # FleetSafe path — pass world-frame obstacle positions + robot_xy explicitly
            step_res = wrapper.step(
                preprocessed,
                obs_vec,
                obs_positions_world,
                robot_xy      = robot_xy,
                obstacle_radii = obs_radii,
            )
            raw  = step_res.raw_cmd_vel
            safe = step_res.safe_cmd_vel
            intervened  = step_res.intervened
            min_dist    = step_res.min_dist_m
            cbf_ms      = max(0.0, step_res.total_ms - (step_res.action_output.inference_ms
                                                         if step_res.action_output else 0.0))
            inference_ms = step_res.action_output.inference_ms if step_res.action_output else 0.0
            wps_raw = step_res.action_output.waypoints if step_res.action_output else None
            if intervened:
                interventions += 1
        else:
            # No FleetSafe — raw model only
            t_inf  = time.perf_counter()
            action = adapter.predict_action(preprocessed)
            raw    = adapter.action_to_cmd_vel(
                action, v_max=args.v_max, w_max=args.w_max, control_hz=args.control_hz,
            )
            safe   = raw
            inference_ms = (time.perf_counter() - t_inf) * 1000.0
            cbf_ms       = 0.0
            intervened   = False
            wps_raw      = action.waypoints if action else None
            # Compute min_dist for telemetry
            if obs_positions_world:
                min_dist = min(
                    float(np.linalg.norm(robot_xy - p)) - r
                    for p, r in zip(obs_positions_world, obs_radii)
                )

        # Step physics
        _, _, terminated, truncated, info = env.step(
            np.array([safe.vx, safe.wz], dtype=np.float32)
        )

        dist_to_goal = float(np.linalg.norm(goal_xy - robot_xy))
        collision    = info.get("collision", min_dist < -0.02)
        goal_reached = dist_to_goal < 0.30 or info.get("success", False)

        # Waypoints: take first 4, convert to serialisable list
        waypoints: list[list[float]] = []
        if wps_raw is not None and len(wps_raw) > 0:
            for wp in wps_raw[:4]:
                waypoints.append([round(float(wp[0]), 3), round(float(wp[1]), 3)])

        if has_cam:
            if _is_blank_frame(frame_rgb):
                # Emit a readable diagnostic placeholder instead of a black frame
                _ph = _make_not_ready_image(max(img_w, 160), max(img_h, 120))
                camera_b64 = _rgb_to_jpeg_b64(_ph)
            else:
                camera_b64 = _rgb_to_jpeg_b64(frame_rgb)
        else:
            camera_b64 = ""

        emit({
            "type": "frame",
            "step": step,
            "model": args.model,
            "fleetsafe_on": args.fleetsafe,
            "robot_x":   round(float(robot_pose[0]), 4),
            "robot_y":   round(float(robot_pose[1]), 4),
            "robot_yaw": round(float(robot_pose[2]), 4),
            "raw_vx":  round(float(raw.vx),  4),
            "raw_vy":  round(float(raw.vy),  4),
            "raw_wz":  round(float(raw.wz),  4),
            "safe_vx": round(float(safe.vx), 4),
            "safe_vy": round(float(safe.vy), 4),
            "safe_wz": round(float(safe.wz), 4),
            "intervened":         intervened,
            "min_dist_m":         round(float(min_dist), 4),
            "h_min":              round(float(min_dist) ** 2 - args.d_safe ** 2, 4),
            "cbf_zone":           _zone(float(min_dist), args.d_safe),
            "intervention_count": interventions,
            "waypoints":          waypoints,
            "inference_ms":       round(float(inference_ms), 2),
            "cbf_ms":             round(float(cbf_ms), 2),
            "collision":          collision,
            "goal_reached":       goal_reached,
            "dist_to_goal":       round(float(dist_to_goal), 4),
            "camera_b64":         camera_b64,
        })

        # ── Safety certificate (Isaac) ─────────────────────────────────────────
        if _cert_logger is not None:
            _step_t = step / args.control_hz
            _h_min_val = round(float(min_dist) ** 2 - args.d_safe ** 2, 4)
            _qp_ok = "optimal" if args.fleetsafe else "skipped"
            _cert_logger.append_from_values(
                timestamp=_step_t,
                model_name=args.model,
                u_nom=[round(float(raw.vx), 4), round(float(raw.wz), 4)],
                u_safe=[round(float(safe.vx), 4), round(float(safe.wz), 4)],
                h_min=_h_min_val,
                min_dist_m=round(float(min_dist), 4),
                cbf_active=intervened,
                qp_status=_qp_ok,
                constraint_margin_min=round(max(0.0, _h_min_val * 0.1), 4),
                latency_ms=round(float(inference_ms) + float(cbf_ms), 2),
                safe=float(min_dist) >= args.d_safe,
            )

        if collision or goal_reached or terminated or truncated:
            break

    env.close()

    if _cert_logger is not None:
        _cert_logger.close()
        status("info", f"Safety certificates written to {_cert_logger.path} ({_cert_logger.count} steps)")

    emit({
        "type": "done",
        "collision": collision,
        "steps": step + 1,
        "summary": {
            "intervention_rate": round(interventions / max(1, step + 1), 3),
            "collision":    collision,
            "goal_reached": goal_reached,
            "min_dist_m":   round(float(min_dist), 4),
        },
    })


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    args, extra_isaac_args = _parse_args()

    # Mock mode: no Isaac needed
    if args.mock or args.model == "mock":
        args.mock = True
        _run_mock(args)
        return 0

    # Isaac mode: AppLauncher MUST be first
    try:
        from isaaclab.app import AppLauncher
    except ImportError:
        emit({
            "type": "error",
            "msg": (
                "isaaclab not found. Activate the isaac conda environment:\n"
                "  conda activate isaac\n"
                "  python scripts/demo/run_supervisor_demo_isaac.py --model vint"
            ),
        })
        return 1

    # headless=False (default): full Isaac Sim GUI window opens on desktop
    # headless=True + stream: WebRTC only at http://localhost:49100
    # headless=False + stream: GUI window AND WebRTC
    livestream = 1 if args.stream else 0
    # Decouple dashboard telemetry stream from Isaac WebRTC livestream.
    # On this machine, AppLauncher livestream can prevent the local Isaac GUI from opening.
    # Keep args.stream for dashboard telemetry, but disable AppLauncher livestream in GUI mode.
    app_livestream = livestream if args.headless else 0
    launcher_cfg = {"headless": args.headless, "livestream": app_livestream}
    _orig_argv = sys.argv[:]
    sys.argv   = [sys.argv[0]] + extra_isaac_args
    if not args.headless:
        status("info", "Isaac Sim GUI window will open on desktop")
    if args.stream:
        status("info", "WebRTC stream also available at http://localhost:49100")
    try:
        launcher = AppLauncher(launcher_cfg)
        app      = launcher.app   # noqa: F841 — keep alive
    except Exception as exc:
        emit({"type": "error", "msg": f"AppLauncher failed: {exc}"})
        return 1
    finally:
        sys.argv = _orig_argv

    try:
        _run_isaac(args)
    except Exception as exc:
        import traceback
        emit({"type": "error", "msg": f"{exc}\n{traceback.format_exc()}"})
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
