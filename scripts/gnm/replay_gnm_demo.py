"""
replay_gnm_demo.py — GNM evidence dashboard in Isaac Sim
=========================================================
Opens a VLNVerse/kujiale USD scene and shows an always-visible evidence
dashboard with three navigable camera views.

Camera prims under /World/GNM_Replay (select → Look through selected camera):
  START_CAMERA   — placed at robot start pose (x, y, yaw)
  CURRENT_CAMERA — placed at trajectory mid-point or CURRENT_FRAME
  GOAL_CAMERA    — placed at robot goal pose (x, y, yaw)
  OVERVIEW_CAMERA — top-down overview of the full path

State panels (textured planes, always visible):
  START_STATE_PANEL, CURRENT_STATE_PANEL, GOAL_STATE_PANEL, PERFORMANCE_PANEL
  EVIDENCE_HUD_PANEL — full evidence chain summary

Image panels (frame images from trajectory):
  START_CAMERA_PANEL, CURRENT_CAMERA_PANEL, GOAL_CAMERA_PANEL
  CURRENT_OBS_PANEL, GOAL_IMAGE_PANEL (when SHOW_GNM_PANELS=1)

Non-GUI modes (no Isaac Sim):
  python3 scripts/gnm/replay_gnm_demo.py --dry-run-panels
  python3 scripts/gnm/replay_gnm_demo.py --list-scenes
  python3 scripts/gnm/replay_gnm_demo.py --prove-dataset
  python3 scripts/gnm/replay_gnm_demo.py --export-live-dashboard

Live dashboard (START VIEW | CURRENT LIVE VIEW | GOAL VIEW per frame):
  python3 scripts/gnm/replay_gnm_demo.py --export-live-dashboard
    Generates dashboard_NNNNNN.png sequence to results/bo_reviewer_packet/live_dashboard/
    Uses SCENE env var (default kujiale_0118).  No Isaac Sim required.
  EXPORT_LIVE_VIDEO=1 python3 scripts/gnm/replay_gnm_demo.py --export-live-dashboard
    Also exports live_gnm_input_dashboard.mp4 via imageio / ffmpeg.

Guided evidence tour (Isaac Sim, switches cameras + saves screenshots):
  conda activate isaac
  SCENE=kujiale_0271 TOUR=1 SHOW_GNM_PANELS=1 python scripts/gnm/replay_gnm_demo.py

Usage:
  conda activate isaac
  LIVE_DASHBOARD=1 AUTO_PLAY=1 SHOW_GNM_PANELS=1 MAX_STEPS=100000 python scripts/gnm/replay_gnm_demo.py
  SCENE=kujiale_0271 SHOW_GNM_PANELS=1 python scripts/gnm/replay_gnm_demo.py
  VIEW=START   SHOW_GNM_PANELS=1 python scripts/gnm/replay_gnm_demo.py
  VIEW=CURRENT SHOW_GNM_PANELS=1 python scripts/gnm/replay_gnm_demo.py
  VIEW=GOAL    SHOW_GNM_PANELS=1 python scripts/gnm/replay_gnm_demo.py
"""
# ── Imports that do NOT require Isaac Sim ─────────────────────────────────────
import json
import math
import os
import pickle
import sys
from pathlib import Path

import numpy as np

# ── Must parse CLI flags BEFORE SimulationApp is imported ────────────────────
_dry_run      = "--dry-run-panels"       in sys.argv
_list_scenes  = "--list-scenes"          in sys.argv
_prove_ds     = "--prove-dataset"        in sys.argv
_export_live  = "--export-live-dashboard" in sys.argv

REPO        = Path(__file__).resolve().parents[2]
SCENE             = os.environ.get("SCENE",             "kujiale_0118")
SPEED             = float(os.environ.get("SPEED",         "1.0"))
SHOW_PANELS       = os.environ.get("SHOW_GNM_PANELS",     "1") == "1"
VIEW              = os.environ.get("VIEW",                "").upper()   # START | CURRENT | GOAL
TOUR              = os.environ.get("TOUR",                "0") == "1"
LIVE_DASHBOARD    = os.environ.get("LIVE_DASHBOARD",      "0") == "1"
AUTO_PLAY         = os.environ.get("AUTO_PLAY",           "0") == "1"
PLAY_SPEED        = float(os.environ.get("PLAY_SPEED",    "1.0"))
DASHBOARD_EVERY_N = int(os.environ.get("DASHBOARD_EVERY_N", "1"))
SAVE_LIVE_FRAMES  = os.environ.get("SAVE_LIVE_FRAMES",    "1") == "1"
EXPORT_LIVE_VIDEO = os.environ.get("EXPORT_LIVE_VIDEO",   "0") == "1"

# Official benchmark results (Track A baseline)
OFFICIAL_SR  = 0.20
OFFICIAL_OSR = 0.4667
OFFICIAL_NE  = 6.51
N_SUCCESS    = 3
N_TOTAL      = 15
N_TRAIN      = 238
N_VAL        = 15
ALL_SCENES   = ["kujiale_0092", "kujiale_0118", "kujiale_0203", "kujiale_0271"]
HOLDOUT_SCENE = "kujiale_0271"
SPLIT_CONFIG = REPO / "configs/gnm/splits/scene_holdout_kujiale_0271.yaml"

train_root = REPO / "datasets/vlntube/train"
val_root   = REPO / "datasets/vlntube/val"

# ── --list-scenes mode (no trajectory data needed) ────────────────────────────
if _list_scenes:
    print("GNM dataset — available scenes")
    print("=" * 60)
    envs_dir = REPO / "datasets/vlntube/envs"
    for sc in ALL_SCENES:
        usd_path = envs_dir / sc / "start_result_navigation.usd"
        usd_ok   = "USD present" if usd_path.exists() else "USD missing"
        t_count  = len([d for d in train_root.iterdir() if d.name.startswith(sc)]) if train_root.exists() else 0
        v_count  = len([d for d in val_root.iterdir()   if d.name.startswith(sc)]) if val_root.exists()   else 0
        holdout  = "  ← held-out scene (scene_holdout config)" if sc == HOLDOUT_SCENE else ""
        print(f"  {sc:<20}  train={t_count:3d}  val={v_count:2d}  {usd_ok}{holdout}")
    print()
    print(f"  Total train : {N_TRAIN}")
    print(f"  Total val   : {N_VAL}")
    print()
    print(f"  Scene-holdout split config : {SPLIT_CONFIG}")
    if SPLIT_CONFIG.exists():
        print(f"  kujiale_0271 in holdout config : YES")
    print()
    print("  Isaac Sim USD assets (not committed, re-downloadable via VLNVerse):")
    for sc in ALL_SCENES:
        usd = envs_dir / sc / "start_result_navigation.usd"
        tag = "present" if usd.exists() else "missing"
        print(f"    {usd}  [{tag}]")
    sys.exit(0)

# ── Load trajectory data ──────────────────────────────────────────────────────
def _load_best_traj(root: Path, scene: str):
    if not root.exists():
        return None, 0.0
    candidates = sorted(d for d in root.iterdir() if d.name.startswith(scene))
    best_traj, best_len = None, 0.0
    for c in candidates:
        pkl = c / "traj_data.pkl"
        if not pkl.exists():
            continue
        try:
            pos = pickle.load(open(pkl, "rb"))["position"]
            length = float(np.linalg.norm(np.diff(pos, axis=0), axis=1).sum())
            if length > best_len:
                best_len, best_traj = length, c
        except Exception:
            continue
    return best_traj, best_len


best_traj, best_len = _load_best_traj(train_root, SCENE)
if best_traj is None:
    print(f"\nNo trajectory found for SCENE={SCENE} in train split.")
    print("Available scenes and counts:")
    for sc in ALL_SCENES:
        n = len([d for d in train_root.iterdir() if d.name.startswith(sc)]) if train_root.exists() else 0
        print(f"  {sc}  train={n}")
    print(f"\nRe-run with one of: SCENE=kujiale_0092 / kujiale_0118 / kujiale_0203 / kujiale_0271")
    sys.exit(1)

data      = pickle.load(open(best_traj / "traj_data.pkl", "rb"))
positions = data["position"]
yaws      = data.get("yaw", np.zeros(len(positions)))
n_steps   = len(positions)

info_path = best_traj / "episode_info.json"
ep_info   = json.loads(info_path.read_text()) if info_path.exists() else {}

sx, sy    = float(positions[0][0]),  float(positions[0][1])
gx, gy    = float(positions[-1][0]), float(positions[-1][1])
start_yaw = float(yaws[0])
goal_yaw  = float(yaws[-1])
init_dist = math.hypot(gx - sx, gy - sy)
path_len  = float(np.linalg.norm(np.diff(positions, axis=0), axis=1).sum())
goal_r    = float(ep_info.get("goal_radius", 3.0))
ep_id     = ep_info.get("episode_id", best_traj.name)
n_frames  = ep_info.get("n_steps", n_steps)
start_img = str(best_traj / "0.jpg")
goal_img  = str(best_traj / f"{n_steps - 1}.jpg")

CURRENT_FRAME = min(int(os.environ.get("CURRENT_FRAME", n_steps // 2)), n_steps - 1)
mx, my    = float(positions[CURRENT_FRAME][0]), float(positions[CURRENT_FRAME][1])
mid_yaw   = float(yaws[CURRENT_FRAME]) if CURRENT_FRAME < len(yaws) else 0.0
mid_img   = str(best_traj / f"{CURRENT_FRAME}.jpg")

# Determine split label for this trajectory
_in_val   = any(d.name == best_traj.name for d in val_root.iterdir()) if val_root.exists() else False
_split_label = "val" if _in_val else ("scene-holdout" if SCENE == HOLDOUT_SCENE else "train")

# Local waypoint targets: next WAYPOINT_HORIZON frames from CURRENT_FRAME
WAYPOINT_HORIZON = 5
_wp_indices = [min(CURRENT_FRAME + k + 1, n_steps - 1) for k in range(WAYPOINT_HORIZON)]
_wp_positions = [(float(positions[i][0]), float(positions[i][1])) for i in _wp_indices]

# ── --prove-dataset mode ──────────────────────────────────────────────────────
if _prove_ds:
    print("GNM dataset proof")
    print("=" * 65)
    print()
    # Count
    t_total = sum(1 for d in train_root.iterdir() if (d / "traj_data.pkl").exists()) if train_root.exists() else 0
    v_total = sum(1 for d in val_root.iterdir()   if (d / "traj_data.pkl").exists()) if val_root.exists()   else 0
    print(f"  Train trajectories : {t_total}  (target: {N_TRAIN})")
    print(f"  Val   trajectories : {v_total}  (target: {N_VAL})")
    print()
    print("  Per-scene breakdown:")
    for sc in ALL_SCENES:
        t = len([d for d in train_root.iterdir() if d.name.startswith(sc)]) if train_root.exists() else 0
        v = len([d for d in val_root.iterdir()   if d.name.startswith(sc)]) if val_root.exists()   else 0
        tag = "  ← held-out scene" if sc == HOLDOUT_SCENE else ""
        print(f"    {sc:<20}  train={t:3d}  val={v:2d}{tag}")
    print()
    print(f"  Sample trajectory  : {best_traj}")
    rgb_frames = sorted(best_traj.glob("*.jpg"))
    print(f"  RGB frames         : {len(rgb_frames)}")
    pkl_path = best_traj / "traj_data.pkl"
    print(f"  traj_data.pkl      : {pkl_path}  ({pkl_path.stat().st_size} bytes)")
    print(f"  position shape     : {np.array(positions).shape}")
    print(f"  Start  x={sx:.4f}  y={sy:.4f}  yaw={start_yaw:.4f} rad ({math.degrees(start_yaw):.1f}°)")
    print(f"  Goal   x={gx:.4f}  y={gy:.4f}  yaw={goal_yaw:.4f}  rad ({math.degrees(goal_yaw):.1f}°)")
    print(f"  Path length        : {path_len:.3f} m")
    print()
    print("  Label explanation:")
    print("  ─────────────────────────────────────────────────────────")
    print("  RGB images  : collected from Isaac Sim / VLNVerse replay")
    print("                Each frame is a 480×360 JPEG from the robot")
    print("                forward camera, saved as 0.jpg, 1.jpg, …")
    print()
    print("  positions   : world-frame (x, y) stored in traj_data.pkl")
    print("  yaw         : robot heading in radians, stored in traj_data.pkl")
    print()
    print("  waypoints   : derived at training time by GNMDataset.")
    print("                For obs frame i and goal idx g:")
    print("                  waypoint = positions[i+horizon] − positions[i]")
    print("                  (rotated into robot frame via yaw[i])")
    print()
    print("  GNM input   : current RGB image  +  goal RGB image")
    print("  GNM output  : local waypoint (delta_x, delta_y) prediction")
    print()
    print(f"  Validation files:")
    print(f"    results/bo_reviewer_packet/03_success_rate_breakdown.md")
    print(f"    results/bo_reviewer_packet/03_success_rate_breakdown.csv")
    print(f"    results/bo_reviewer_packet/04_scene_holdout_split.md")
    print()
    print(f"  Official Track A result:")
    print(f"    SR  = {N_SUCCESS}/{N_TOTAL} = {OFFICIAL_SR*100:.1f}%")
    print(f"    OSR = {int(OFFICIAL_OSR*N_TOTAL)}/{N_TOTAL} = {OFFICIAL_OSR*100:.1f}%")
    print(f"    NE  = {OFFICIAL_NE:.2f} m")
    sys.exit(0)

# ── Panel PNG generation (PIL only, no Isaac Sim) ─────────────────────────────
FIG_DIR       = REPO / "results/figures"
LIVE_DASH_DIR = REPO / "results/bo_reviewer_packet/live_dashboard"
FIG_DIR.mkdir(parents=True, exist_ok=True)
LIVE_DASH_DIR.mkdir(parents=True, exist_ok=True)


def _font(size: int):
    from PIL import ImageFont
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _font_r(size: int):
    from PIL import ImageFont
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _make_panel(title: str, lines: list[tuple[str, tuple]],
                width: int = 640, bg=(15, 18, 30),
                title_color=(255, 210, 60)) -> "Image":
    from PIL import Image, ImageDraw
    line_h  = 30
    pad     = 20
    title_h = 50
    height  = title_h + len(lines) * line_h + pad * 2
    img     = Image.new("RGB", (width, height), bg)
    draw    = ImageDraw.Draw(img)
    draw.rectangle([(0, 0), (width, title_h)], fill=(30, 35, 55))
    fB20 = _font(20)
    tw   = draw.textbbox((0, 0), title, font=fB20)[2]
    draw.text(((width - tw) // 2, 12), title, fill=title_color, font=fB20)
    fR16 = _font_r(16)
    fB16 = _font(16)
    y = title_h + pad
    for text, color in lines:
        if text.startswith("──"):
            draw.line([(pad, y + 8), (width - pad, y + 8)], fill=(50, 55, 75), width=1)
        else:
            label, _, value = text.partition(" : ")
            if value:
                draw.text((pad, y), label + " :", fill=(160, 165, 180), font=fR16)
                lw = draw.textbbox((0, 0), label + " :", font=fR16)[2]
                draw.text((pad + lw + 6, y), value, fill=color, font=fB16)
            else:
                draw.text((pad, y), text, fill=color, font=fR16)
        y += line_h
    return img


def _make_frame_panel(img_path: str, label: str, label_color: tuple,
                      subtext: str = "", frame_w: int = 480, frame_h: int = 360) -> "Image":
    from PIL import Image, ImageDraw
    BAR_H   = 44
    total_h = BAR_H + frame_h
    panel   = Image.new("RGB", (frame_w, total_h), (15, 18, 30))
    draw    = ImageDraw.Draw(panel)
    draw.rectangle([(0, 0), (frame_w, BAR_H)], fill=(30, 35, 55))
    fB18 = _font(18)
    fR13 = _font_r(13)
    draw.text((10, 6), label, fill=label_color, font=fB18)
    if subtext:
        sw = draw.textbbox((0, 0), subtext, font=fR13)[2]
        draw.text((frame_w - sw - 10, 14), subtext, fill=(160, 165, 180), font=fR13)
    src = Path(img_path)
    if src.exists():
        frame_img = Image.open(src).convert("RGB").resize((frame_w, frame_h))
        panel.paste(frame_img, (0, BAR_H))
    else:
        draw.text((10, BAR_H + 10), f"(no image: {src.name})", fill=(120, 80, 80), font=fR13)
    return panel


def generate_panels() -> dict[str, Path]:
    """Generate all dashboard panel PNGs. Returns {name: path}."""
    from PIL import Image
    WHITE  = (235, 235, 235)
    GREY   = (150, 155, 165)
    GREEN  = (60,  210, 90)
    YELLOW = (255, 210, 60)
    CYAN   = (60,  185, 225)
    RED    = (225, 80,  80)
    ORANGE = (255, 150,  40)

    panels = {}

    # ── START STATE ───────────────────────────────────────────────────────────
    img = _make_panel("START STATE", [
        (f"x_start : {sx:.4f} m",                                         WHITE),
        (f"y_start : {sy:.4f} m",                                         WHITE),
        (f"yaw     : {start_yaw:.4f} rad  ({math.degrees(start_yaw):.1f}°)", WHITE),
        ("── ──", GREY),
        (f"frame 0 (first recorded frame)",                                GREY),
        (f"episode : {ep_id}",                                             GREY),
        (f"scene   : {SCENE}",                                             CYAN),
        ("camera  : /World/GNM_Replay/START_CAMERA",                      GREEN),
    ], title_color=GREEN)
    p = FIG_DIR / "start_state_panel.png"
    img.save(p)
    panels["start_state"] = p

    # ── CURRENT STATE ─────────────────────────────────────────────────────────
    img = _make_panel("CURRENT STATE  (dynamic — follows ROBOT_MARKER)", [
        (f"x_current : {sx:.4f} m  ← changes during replay",             WHITE),
        (f"y_current : {sy:.4f} m  ← changes during replay",             WHITE),
        (f"yaw       : {start_yaw:.4f} rad  ← changes during replay",    WHITE),
        ("── ──", GREY),
        ("Terminal shows current state every 10 frames.",                 GREY),
        ("ROBOT_MARKER (blue cube) shows current position.",              CYAN),
        ("Cyan path spheres show all trajectory waypoints.",              CYAN),
        ("Orange cones show local waypoint targets from CURRENT_FRAME.",  ORANGE),
        ("camera  : /World/GNM_Replay/CURRENT_CAMERA",                   CYAN),
    ], title_color=CYAN)
    p = FIG_DIR / "current_state_panel.png"
    img.save(p)
    panels["current_state"] = p

    # ── GOAL STATE ────────────────────────────────────────────────────────────
    img = _make_panel("GOAL STATE", [
        (f"x_goal  : {gx:.4f} m",                                        WHITE),
        (f"y_goal  : {gy:.4f} m",                                        WHITE),
        (f"yaw     : {goal_yaw:.4f} rad  ({math.degrees(goal_yaw):.1f}°)", WHITE),
        ("── ──", GREY),
        (f"frame   : {n_frames - 1} (last recorded frame)",              GREY),
        (f"initial distance  : {init_dist:.3f} m",                       WHITE),
        (f"success radius    : {goal_r:.1f} m",                          YELLOW),
        ("camera  : /World/GNM_Replay/GOAL_CAMERA",                      RED),
    ], title_color=RED)
    p = FIG_DIR / "goal_state_panel.png"
    img.save(p)
    panels["goal_state"] = p

    # ── PERFORMANCE ───────────────────────────────────────────────────────────
    img = _make_panel("OFFICIAL TRACK A PERFORMANCE  (MobileNet GNM baseline)", [
        (f"Success Rate (SR)       : {N_SUCCESS}/{N_TOTAL} = {OFFICIAL_SR*100:.1f}%", GREEN),
        (f"Oracle Success Rate(OSR): {int(OFFICIAL_OSR*N_TOTAL)}/{N_TOTAL} = {OFFICIAL_OSR*100:.1f}%", YELLOW),
        (f"Navigation Error (NE)   : {OFFICIAL_NE:.2f} m  (lower is better)",        WHITE),
        ("── ──", GREY),
        ("SR : robot stopped within 3 m of goal (final position).",      GREY),
        ("OSR: robot was EVER within 3 m (may have overshot).",          GREY),
        ("SR < OSR because dist_pred did not trigger stop in time.",     GREY),
        ("── ──", GREY),
        (f"Val episodes : {N_TOTAL}  |  Successful : {N_SUCCESS}  |  Oracle : {int(OFFICIAL_OSR*N_TOTAL)}", WHITE),
        ("See results/bo_reviewer_packet/03_success_rate_breakdown.md",  CYAN),
    ], title_color=YELLOW, width=760)
    p = FIG_DIR / "performance_panel.png"
    img.save(p)
    panels["performance"] = p

    # ── EVIDENCE HUD ──────────────────────────────────────────────────────────
    _sc_holdout = "(held-out scene)" if SCENE == HOLDOUT_SCENE else "(train scene)"
    img = _make_panel("GNM EVIDENCE CHAIN — FleetSafe-VisualNav-Benchmark", [
        (f"Scene          : {SCENE}  {_sc_holdout}",                         CYAN),
        (f"Episode        : {ep_id}",                                         WHITE),
        (f"Split          : {_split_label}",                                  YELLOW),
        ("── ──", GREY),
        (f"Dataset        : {N_TRAIN} train + {N_VAL} val trajectories",      WHITE),
        ("Scenes         : kujiale_0092  kujiale_0118  kujiale_0203  kujiale_0271", WHITE),
        ("Held-out scene : kujiale_0271  (unseen floor-plan, no training data)",ORANGE),
        ("── ──", GREY),
        ("GNM input      : current RGB image  +  goal RGB image",             CYAN),
        ("GNM output     : local waypoint (delta_x, delta_y) in robot frame", CYAN),
        ("Waypoint label : from consecutive trajectory poses (traj_data.pkl)", GREY),
        ("Orange cones   : waypoint targets from CURRENT_FRAME (ground truth)", ORANGE),
        ("── ──", GREY),
        (f"Official SR    : {N_SUCCESS}/{N_TOTAL} = {OFFICIAL_SR*100:.1f}%",  GREEN),
        (f"Official OSR   : {int(OFFICIAL_OSR*N_TOTAL)}/{N_TOTAL} = {OFFICIAL_OSR*100:.1f}%", YELLOW),
        (f"Official NE    : {OFFICIAL_NE:.2f} m",                             WHITE),
        ("── ──", GREY),
        ("Validation     : results/bo_reviewer_packet/03_success_rate_breakdown.md", GREY),
        ("Holdout proof  : results/bo_reviewer_packet/04_scene_holdout_split.md",    GREY),
        ("Full chain     : results/bo_reviewer_packet/10_full_evidence_chain.md",    GREY),
    ], title_color=YELLOW, width=860)
    p = FIG_DIR / "evidence_hud_panel.png"
    img.save(p)
    panels["evidence_hud"] = p

    # ── Camera-view frame panels ───────────────────────────────────────────────
    frame_defs = [
        (start_img, "start_camera_panel",
         "START VIEW",   GREEN,  f"frame 0  |  x={sx:.2f} y={sy:.2f}  yaw={math.degrees(start_yaw):.0f}°"),
        (mid_img,   "current_camera_panel",
         "CURRENT VIEW", CYAN,   f"frame {CURRENT_FRAME}  |  x={mx:.2f} y={my:.2f}  yaw={math.degrees(mid_yaw):.0f}°"),
        (goal_img,  "goal_camera_panel",
         "GOAL VIEW",    RED,    f"frame {n_steps-1}  |  x={gx:.2f} y={gy:.2f}  yaw={math.degrees(goal_yaw):.0f}°"),
    ]
    for img_path, key, label, color, sub in frame_defs:
        panel_img = _make_frame_panel(img_path, label, color, subtext=sub)
        p = FIG_DIR / f"{key}.png"
        panel_img.save(p)
        panels[key] = p

    # ── GNM input panel (current obs + goal, side by side) ────────────────────
    obs_src  = best_traj / f"{CURRENT_FRAME}.jpg"
    goal_src = best_traj / f"{n_steps - 1}.jpg"
    from PIL import Image as _PIL_Image
    W, H = 320, 240
    gnm_in = _PIL_Image.new("RGB", (W * 2 + 4, H + 44), (15, 18, 30))
    from PIL import ImageDraw as _IDrawMod
    draw_in = _IDrawMod.Draw(gnm_in)
    draw_in.rectangle([(0, 0), (W * 2 + 4, 44)], fill=(30, 35, 55))
    draw_in.text((8, 8),       "GNM INPUT: current obs",    fill=(60, 185, 225), font=_font(14))
    draw_in.text((W + 12, 8),  "GNM INPUT: goal image",     fill=(225, 80, 80),  font=_font(14))
    if obs_src.exists():
        gnm_in.paste(_PIL_Image.open(obs_src).convert("RGB").resize((W, H)), (0, 44))
    if goal_src.exists():
        gnm_in.paste(_PIL_Image.open(goal_src).convert("RGB").resize((W, H)), (W + 4, 44))
    p = FIG_DIR / "gnm_input_panel.png"
    gnm_in.save(p)
    panels["gnm_input"] = p

    # ── Legacy obs / goal image copies ───────────────────────────────────────
    for src, name in [(best_traj / "0.jpg",              "gnm_image_panel_obs.png"),
                      (best_traj / f"{n_steps - 1}.jpg", "gnm_image_panel_goal.png")]:
        dst = FIG_DIR / name
        if src.exists():
            _PIL_Image.open(src).convert("RGB").resize((320, 240)).save(dst)
        panels[name.replace(".png", "")] = dst

    return panels


# ── Live dashboard frame builder ─────────────────────────────────────────────

def _make_live_dashboard_frame(
    frame_idx: int,
    current_img_path: str,
    rx: float,
    ry: float,
    ryaw: float,
) -> "Image":
    """Three-column per-frame dashboard: START VIEW | CURRENT LIVE VIEW | GOAL VIEW."""
    from PIL import Image, ImageDraw

    GREEN  = (60, 210, 90)
    CYAN   = (60, 185, 225)
    RED    = (225, 80, 80)
    WHITE  = (235, 235, 235)
    GREY   = (150, 155, 165)
    YELLOW = (255, 210, 60)
    BG     = (15, 18, 30)
    BAR_BG = (30, 35, 55)

    IMG_W, IMG_H = 320, 240
    GAP     = 8
    LABEL_H = 44
    INFO_H  = 96
    TITLE_H = 46

    total_w = IMG_W * 3 + GAP * 2
    total_h = TITLE_H + LABEL_H + IMG_H + INFO_H
    canvas  = Image.new("RGB", (total_w, total_h), BG)
    draw    = ImageDraw.Draw(canvas)

    fB18 = _font(18)
    fB14 = _font(14)
    fR13 = _font_r(13)
    fR12 = _font_r(12)

    # Title bar
    draw.rectangle([(0, 0), (total_w, TITLE_H)], fill=BAR_BG)
    title = (f"GNM LIVE REPLAY DASHBOARD  |  {SCENE}  |  "
             f"frame {frame_idx:4d} / {n_steps - 1}")
    tw = draw.textbbox((0, 0), title, font=fB18)[2]
    draw.text(((total_w - tw) // 2, 10), title, fill=YELLOW, font=fB18)

    # Column label bars
    col_x = [0, IMG_W + GAP, IMG_W * 2 + GAP * 2]
    cur_sub = f"frame {frame_idx}  |  x={rx:.2f} y={ry:.2f}  yaw={math.degrees(ryaw):.0f}°"
    col_defs = [
        ("START VIEW",        GREEN, f"frame 0  |  x={sx:.2f} y={sy:.2f}"),
        ("CURRENT LIVE VIEW", CYAN,  cur_sub),
        ("GOAL VIEW",         RED,   f"frame {n_steps - 1}  |  x={gx:.2f} y={gy:.2f}"),
    ]
    label_y = TITLE_H
    for i, (lbl, color, sub) in enumerate(col_defs):
        cx = col_x[i]
        draw.rectangle([(cx, label_y), (cx + IMG_W, label_y + LABEL_H)], fill=BAR_BG)
        draw.text((cx + 8, label_y + 5),  lbl, fill=color, font=fB14)
        sw = draw.textbbox((0, 0), sub, font=fR12)[2]
        draw.text((cx + IMG_W - sw - 6, label_y + 26), sub, fill=GREY, font=fR12)

    # Images
    img_y    = TITLE_H + LABEL_H
    srcs     = [start_img, current_img_path, goal_img]
    for i, src in enumerate(srcs):
        cx = col_x[i]
        p  = Path(src)
        if p.exists():
            fi = Image.open(p).convert("RGB").resize((IMG_W, IMG_H))
            canvas.paste(fi, (cx, img_y))
        else:
            draw.rectangle([(cx, img_y), (cx + IMG_W, img_y + IMG_H)], fill=(30, 25, 25))
            draw.text((cx + 10, img_y + IMG_H // 2),
                      "(no image)", fill=(100, 60, 60), font=fR12)

    # Info bar
    info_y = TITLE_H + LABEL_H + IMG_H
    draw.line([(0, info_y), (total_w, info_y)], fill=(50, 55, 75), width=2)

    dist = math.hypot(rx - gx, ry - gy)
    goal_reached = dist <= goal_r
    status_txt   = "GOAL REACHED" if goal_reached else "RUNNING"
    status_color = GREEN if goal_reached else CYAN

    r1 = (f"scene: {SCENE}   ep: {ep_id}   split: {_split_label}"
          f"   path_len: {path_len:.2f} m   success_radius: {goal_r:.1f} m")
    draw.text((8, info_y + 6), r1, fill=GREY, font=fR12)

    dist_txt = f"dist_to_goal: {dist:.2f} m    STATUS: "
    draw.text((8, info_y + 24), dist_txt, fill=WHITE, font=fR13)
    dtw = draw.textbbox((0, 0), dist_txt, font=fR13)[2]
    draw.text((8 + dtw, info_y + 24), status_txt, fill=status_color, font=fB14)

    r3 = (f"GNM INPUT: current RGB (frame {frame_idx}) + goal RGB (frame {n_steps - 1})"
          f"  →  local waypoint (delta_x, delta_y)"
          f"   [labels: traj_data.pkl — NOT model prediction]")
    draw.text((8, info_y + 48), r3, fill=GREY, font=fR12)

    r4 = (f"Official Track A result: SR={OFFICIAL_SR * 100:.1f}%  "
          f"OSR={OFFICIAL_OSR * 100:.1f}%  NE={OFFICIAL_NE:.2f} m"
          f"  ({N_SUCCESS}/{N_TOTAL} val eps, {N_TRAIN} train trajs)")
    draw.text((8, info_y + 66), r4, fill=YELLOW, font=fR12)

    return canvas


def _try_video_export(frame_dir: Path, out_path: Path, fps: int = 10) -> bool:
    """Export PNG sequence → mp4. Returns True on success."""
    frames = sorted(frame_dir.glob("dashboard_*.png"))
    if not frames:
        return False
    try:
        import imageio.v2 as iio
        from PIL import Image as _PILImg
        import numpy as _np
        with iio.get_writer(str(out_path), fps=fps, codec="libx264",
                            pixelformat="yuv420p", quality=8) as writer:
            for f in frames:
                writer.append_data(_np.array(_PILImg.open(f).convert("RGB")))
        return True
    except Exception:
        pass
    try:
        import subprocess
        pattern = str(frame_dir / "dashboard_%06d.png")
        r = subprocess.run(
            ["ffmpeg", "-y", "-framerate", str(fps), "-i", pattern,
             "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out_path)],
            capture_output=True, timeout=180,
        )
        return r.returncode == 0 and out_path.exists()
    except Exception:
        return False


# ── Dry-run mode: generate panels and exit ────────────────────────────────────
if _dry_run:
    print("Generating dashboard panel PNGs (no Isaac Sim)...")
    panels = generate_panels()
    for name, path in panels.items():
        print(f"  {name:<35} {path}")
    print(f"\nAll panels written to {FIG_DIR}")
    print(f"\nScene   : {SCENE}  split={_split_label}")
    print(f"Episode : {ep_id}")
    print("\nSTART STATE:")
    print(f"  x={sx:.4f}  y={sy:.4f}  yaw={start_yaw:.4f} rad ({math.degrees(start_yaw):.1f}°)")
    print(f"  camera: /World/GNM_Replay/START_CAMERA")
    print(f"\nCURRENT STATE  (frame {CURRENT_FRAME}):")
    print(f"  x={mx:.4f}  y={my:.4f}  yaw={mid_yaw:.4f} rad ({math.degrees(mid_yaw):.1f}°)")
    print(f"  camera: /World/GNM_Replay/CURRENT_CAMERA")
    print(f"  waypoint targets (next {WAYPOINT_HORIZON} frames): {_wp_positions}")
    print("\nGOAL STATE:")
    print(f"  x={gx:.4f}  y={gy:.4f}  yaw={goal_yaw:.4f} rad ({math.degrees(goal_yaw):.1f}°)")
    print(f"  camera: /World/GNM_Replay/GOAL_CAMERA")
    print("\nPERFORMANCE:")
    print(f"  SR  = {N_SUCCESS}/{N_TOTAL} = {OFFICIAL_SR*100:.1f}%")
    print(f"  OSR = {int(OFFICIAL_OSR*N_TOTAL)}/{N_TOTAL} = {OFFICIAL_OSR*100:.1f}%")
    print(f"  NE  = {OFFICIAL_NE:.2f} m")
    print("\nTo view in Isaac Sim:")
    print("  conda activate isaac && VIEW=START   SHOW_GNM_PANELS=1 python scripts/gnm/replay_gnm_demo.py")
    print("  conda activate isaac && VIEW=CURRENT SHOW_GNM_PANELS=1 python scripts/gnm/replay_gnm_demo.py")
    print("  conda activate isaac && VIEW=GOAL    SHOW_GNM_PANELS=1 python scripts/gnm/replay_gnm_demo.py")
    print("  conda activate isaac && SCENE=kujiale_0271 TOUR=1 SHOW_GNM_PANELS=1 python scripts/gnm/replay_gnm_demo.py")
    print()
    print("Live dashboard (no Isaac Sim):")
    print("  python3 scripts/gnm/replay_gnm_demo.py --export-live-dashboard")
    print("  EXPORT_LIVE_VIDEO=1 python3 scripts/gnm/replay_gnm_demo.py --export-live-dashboard")
    sys.exit(0)


# ── --export-live-dashboard mode (no Isaac Sim) ───────────────────────────────
if _export_live:
    print("Generating live GNM input dashboard PNG sequence (no Isaac Sim)...")
    print(f"  Scene    : {SCENE}  ({_split_label})")
    print(f"  Episode  : {ep_id}")
    print(f"  Frames   : {n_steps}")
    print(f"  Output   : {LIVE_DASH_DIR}/")
    print()
    LIVE_DASH_DIR.mkdir(parents=True, exist_ok=True)
    every_n = max(1, DASHBOARD_EVERY_N)
    saved   = 0
    for t in range(n_steps):
        if t % every_n != 0 and t != n_steps - 1:
            continue
        rx   = float(positions[t][0])
        ry   = float(positions[t][1])
        ryaw = float(yaws[t]) if t < len(yaws) else 0.0
        cur_img = str(best_traj / f"{t}.jpg")
        frame   = _make_live_dashboard_frame(t, cur_img, rx, ry, ryaw)
        out_p   = LIVE_DASH_DIR / f"dashboard_{t:06d}.png"
        frame.save(out_p)
        saved += 1
        if t % max(1, n_steps // 10) == 0:
            dist = math.hypot(rx - gx, ry - gy)
            status = "GOAL REACHED" if dist <= goal_r else "RUNNING"
            print(f"  frame {t:4d}/{n_steps - 1}  x={rx:.3f} y={ry:.3f}"
                  f"  dist_goal={dist:.2f} m  [{status}]")
    print()
    print(f"  Saved {saved} dashboard frames to {LIVE_DASH_DIR}/")
    # Thumbnail for reviewer: copy last and first frames
    first_p = LIVE_DASH_DIR / "dashboard_000000.png"
    last_key = ((n_steps - 1) // every_n) * every_n
    last_p  = LIVE_DASH_DIR / f"dashboard_{last_key:06d}.png"
    if first_p.exists():
        print(f"  First frame : {first_p}")
    if last_p.exists():
        print(f"  Last  frame : {last_p}")
    # Optional video export
    vid_path = LIVE_DASH_DIR / "live_gnm_input_dashboard.mp4"
    if EXPORT_LIVE_VIDEO:
        print()
        print(f"  Exporting video → {vid_path} ...")
        ok = _try_video_export(LIVE_DASH_DIR, vid_path, fps=10)
        if ok:
            print(f"  Video saved: {vid_path}")
        else:
            print("  Video export failed (imageio/ffmpeg not available).")
            print("  Install: pip install imageio[ffmpeg]  or  apt install ffmpeg")
    else:
        print()
        print("  To export video:")
        print("    EXPORT_LIVE_VIDEO=1 python3 scripts/gnm/replay_gnm_demo.py --export-live-dashboard")
    print()
    print("  Reviewer doc: results/bo_reviewer_packet/13_live_gnm_input_dashboard.md")
    print("  Isaac Sim live dashboard:")
    print("    conda activate isaac && LIVE_DASHBOARD=1 AUTO_PLAY=1 SHOW_GNM_PANELS=1 MAX_STEPS=100000 python scripts/gnm/replay_gnm_demo.py")
    sys.exit(0)

# ── Generate panels before opening Isaac Sim ─────────────────────────────────
print("Generating dashboard panels...")
panels = generate_panels()
for name, path in panels.items():
    print(f"  {path.name}")

# ── Terminal state summary ────────────────────────────────────────────────────
print()
print("═" * 65)
print("GNM Evidence Dashboard — Isaac Sim")
print(f"Scene      : {SCENE}  ({_split_label})")
print(f"Trajectory : {best_traj.name}")
print(f"Episode    : {ep_id}")
print()
print("Available scenes and train counts:")
for sc in ALL_SCENES:
    n = len([d for d in train_root.iterdir() if d.name.startswith(sc)]) if train_root.exists() else 0
    tag = "  ← held-out scene" if sc == HOLDOUT_SCENE else ""
    print(f"  {sc}  train={n}{tag}")
print()
print("START STATE:")
print(f"  x={sx:.4f}  y={sy:.4f}  yaw={start_yaw:.4f} rad ({math.degrees(start_yaw):.1f}°)")
print(f"  camera: /World/GNM_Replay/START_CAMERA")
print()
print(f"CURRENT STATE  (frame {CURRENT_FRAME}/{n_steps - 1}):")
print(f"  x={mx:.4f}  y={my:.4f}  yaw={mid_yaw:.4f} rad ({math.degrees(mid_yaw):.1f}°)")
print(f"  camera: /World/GNM_Replay/CURRENT_CAMERA")
print(f"  waypoint targets: {_wp_positions}")
print()
print("GOAL STATE:")
print(f"  x={gx:.4f}  y={gy:.4f}  yaw={goal_yaw:.4f} rad ({math.degrees(goal_yaw):.1f}°)")
print(f"  initial_dist={init_dist:.3f} m  success_radius={goal_r} m")
print(f"  camera: /World/GNM_Replay/GOAL_CAMERA")
print()
print("PERFORMANCE (official Track A baseline):")
print(f"  SR  = {N_SUCCESS}/{N_TOTAL} = {OFFICIAL_SR*100:.1f}%")
print(f"  OSR = {int(OFFICIAL_OSR*N_TOTAL)}/{N_TOTAL} = {OFFICIAL_OSR*100:.1f}%")
print(f"  NE  = {OFFICIAL_NE:.2f} m")
print()
if TOUR:
    print("TOUR=1 — will auto-switch cameras and save screenshots to:")
    print(f"  results/bo_reviewer_packet/screenshots/")
print("═" * 65)

# ── Now start Isaac Sim ───────────────────────────────────────────────────────
import time
from isaacsim import SimulationApp
app = SimulationApp({"headless": False, "renderer": "RayTracedLighting"})

import omni.usd
from pxr import UsdGeom, UsdShade, Gf, Sdf, Usd

# ── Load USD scene ────────────────────────────────────────────────────────────
usd = REPO / "datasets/vlntube/envs" / SCENE / "start_result_navigation.usd"
print(f"\nOpening: {usd}")
ctx = omni.usd.get_context()
ctx.open_stage(str(usd))
for _ in range(200):
    app.update()
    time.sleep(0.01)
stage = ctx.get_stage()
assert stage is not None, "Stage failed to load"


# ── Material helpers ──────────────────────────────────────────────────────────
def make_material(path: str, r: float, g: float, b: float):
    mat    = UsdShade.Material.Define(stage, path)
    shader = UsdShade.Shader.Define(stage, f"{path}/Shader")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(r, g, b))
    shader.CreateInput("roughness",    Sdf.ValueTypeNames.Float).Set(0.4)
    shader.CreateInput("metallic",     Sdf.ValueTypeNames.Float).Set(0.0)
    mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return mat


def make_texture_material(path: str, img_path: str):
    mat    = UsdShade.Material.Define(stage, path)
    shader = UsdShade.Shader.Define(stage, f"{path}/Shader")
    shader.CreateIdAttr("UsdPreviewSurface")
    tex = UsdShade.Shader.Define(stage, f"{path}/Texture")
    tex.CreateIdAttr("UsdUVTexture")
    tex.CreateInput("file",  Sdf.ValueTypeNames.Asset).Set(img_path)
    tex.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("clamp")
    tex.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("clamp")
    tex_out = tex.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
    st = UsdShade.Shader.Define(stage, f"{path}/PrimST")
    st.CreateIdAttr("UsdPrimvarReader_float2")
    st.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
    st_out = st.CreateOutput("result", Sdf.ValueTypeNames.Float2)
    tex.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(st_out)
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(tex_out)
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(1.0)
    shader.CreateInput("metallic",  Sdf.ValueTypeNames.Float).Set(0.0)
    mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return mat


def bind(prim, mat):
    UsdShade.MaterialBindingAPI(prim).Bind(mat)


def set_meta(prim: Usd.Prim, name: str, value) -> None:
    ns = "gnm"
    if isinstance(value, str):
        t = Sdf.ValueTypeNames.String
    elif isinstance(value, float):
        t = Sdf.ValueTypeNames.Double
    elif isinstance(value, int):
        t = Sdf.ValueTypeNames.Int
    elif isinstance(value, (list, tuple)) and len(value) == 2:
        attr = prim.CreateAttribute(f"{ns}:{name}", Sdf.ValueTypeNames.Double2, custom=True)
        attr.Set(Gf.Vec2d(*value))
        return
    else:
        t = Sdf.ValueTypeNames.String
        value = str(value)
    prim.CreateAttribute(f"{ns}:{name}", t, custom=True).Set(value)


def create_image_panel(prim_path: str, img_path: str,
                        x: float, y: float, z: float,
                        half_w: float = 2.0, half_h: float = 1.5) -> None:
    mesh = UsdGeom.Mesh.Define(stage, prim_path)
    mesh.CreatePointsAttr([
        Gf.Vec3f(-half_w, -half_h, 0), Gf.Vec3f(half_w, -half_h, 0),
        Gf.Vec3f( half_w,  half_h, 0), Gf.Vec3f(-half_w,  half_h, 0),
    ])
    mesh.CreateFaceVertexCountsAttr([4])
    mesh.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
    mesh.CreateNormalsAttr([Gf.Vec3f(0, 0, 1)] * 4)
    mesh.SetNormalsInterpolation("vertex")
    pvapi = UsdGeom.PrimvarsAPI(mesh.GetPrim())
    st_pv = pvapi.CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray,
                                UsdGeom.Tokens.varying)
    st_pv.Set([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)])
    mesh.AddTranslateOp().Set(Gf.Vec3d(x, y, z))
    mat = make_texture_material(f"{prim_path}/mat", img_path)
    bind(mesh.GetPrim(), mat)


def make_camera(prim_path: str, x: float, y: float, yaw_rad: float,
                height: float = 1.2) -> UsdGeom.Camera:
    """
    Camera at (x, y, height) pointing in the robot heading direction.
    USD cameras look along -Z by default.
    RotateX(90) → looks along +Y. RotateZ(yaw_deg - 90) → looks along heading.
    """
    cam = UsdGeom.Camera.Define(stage, prim_path)
    cam.CreateProjectionAttr(UsdGeom.Tokens.perspective)
    cam.CreateHorizontalApertureAttr(20.0)
    cam.CreateFocalLengthAttr(16.0)
    xformable = UsdGeom.Xformable(cam.GetPrim())
    xformable.ClearXformOpOrder()
    xformable.AddTranslateOp().Set(Gf.Vec3d(x, y, height))
    yaw_deg = math.degrees(yaw_rad)
    xformable.AddRotateXYZOp().Set(Gf.Vec3f(90.0, 0.0, yaw_deg - 90.0))
    return cam


def make_overview_camera(prim_path: str, cx: float, cy: float,
                          path_span: float) -> UsdGeom.Camera:
    """Top-down camera centred over the full path."""
    cam = UsdGeom.Camera.Define(stage, prim_path)
    cam.CreateProjectionAttr(UsdGeom.Tokens.perspective)
    cam.CreateHorizontalApertureAttr(20.0)
    height = max(path_span * 1.5, 12.0)
    cam.CreateFocalLengthAttr(max(8.0, 50.0 / height))
    xf = UsdGeom.Xformable(cam.GetPrim())
    xf.ClearXformOpOrder()
    xf.AddTranslateOp().Set(Gf.Vec3d(cx, cy, height))
    # look straight down: RotateX(0) USD cam already looks along -Z, no rotation needed
    # But we want to look down (+Z is up), so rotate X by 0 — camera already looks down
    xf.AddRotateXYZOp().Set(Gf.Vec3f(0.0, 0.0, 0.0))
    return cam


def _set_camera_meta(prim_path: str, role: str, x: float, y: float,
                     yaw_rad: float, frame_index: int, image_path: str) -> None:
    """Attach gnm:* custom USD attributes so the Property panel shows position + metrics."""
    prim = stage.GetPrimAtPath(prim_path)
    if not prim.IsValid():
        return
    set_meta(prim, "role",                       role)
    set_meta(prim, "scene_id",                   SCENE)
    set_meta(prim, "episode_id",                 ep_id)
    set_meta(prim, "x",                          x)
    set_meta(prim, "y",                          y)
    set_meta(prim, "yaw_rad",                    yaw_rad)
    set_meta(prim, "yaw_deg",                    math.degrees(yaw_rad))
    set_meta(prim, "frame_index",                frame_index)
    set_meta(prim, "image_path",                 image_path)
    set_meta(prim, "success_rate",               OFFICIAL_SR)
    set_meta(prim, "oracle_success_rate",        OFFICIAL_OSR)
    set_meta(prim, "navigation_error_m",         OFFICIAL_NE)
    set_meta(prim, "dataset_train_trajectories", N_TRAIN)
    set_meta(prim, "dataset_val_trajectories",   N_VAL)


def _switch_viewport(cam_path: str) -> bool:
    try:
        import omni.kit.viewport.utility as vp_util
        vp = vp_util.get_active_viewport()
        vp.camera_path = cam_path
        return True
    except Exception as e:
        print(f"  Viewport switch failed ({e}); manually select '{cam_path}'")
        return False


def _save_screenshot(out_path: Path) -> bool:
    """Try several Isaac Sim screenshot APIs. Returns True if succeeded."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # API 1: omni.renderer_capture (Isaac Sim 4.x)
    try:
        import omni.renderer_capture as _rc
        iface = _rc.acquire_renderer_capture_interface()
        iface.capture_next_frame_swapchain(str(out_path))
        for _ in range(5):
            app.update()
            time.sleep(0.1)
        if out_path.exists():
            return True
    except Exception:
        pass
    # API 2: omni.kit.capture (older Isaac Sim)
    try:
        import omni.kit.capture as _kc
        _kc.get_capture_interface().capture_image(str(out_path), "PNG")
        for _ in range(5):
            app.update()
            time.sleep(0.1)
        if out_path.exists():
            return True
    except Exception:
        pass
    return False


# ── Build overlay root ────────────────────────────────────────────────────────
root      = "/World/GNM_Replay"
mats_root = f"{root}/Materials"
UsdGeom.Xform.Define(stage, root)
UsdGeom.Xform.Define(stage, mats_root)

mat_dot      = make_material(f"{mats_root}/dot",      0.2, 0.6, 1.0)
mat_start    = make_material(f"{mats_root}/start",    0.1, 0.9, 0.2)
mat_goal     = make_material(f"{mats_root}/goal",     1.0, 0.2, 0.1)
mat_robot    = make_material(f"{mats_root}/robot",    0.2, 0.4, 1.0)
mat_waypoint = make_material(f"{mats_root}/waypoint", 1.0, 0.6, 0.1)  # orange

Z_MARKER = 1.0

# ── Cyan path dots ────────────────────────────────────────────────────────────
for i in range(n_steps):
    _x, _y = float(positions[i][0]), float(positions[i][1])
    s = UsdGeom.Sphere.Define(stage, f"{root}/path_{i:04d}")
    s.CreateRadiusAttr(0.07)
    s.AddTranslateOp().Set(Gf.Vec3d(_x, _y, Z_MARKER))
    bind(s.GetPrim(), mat_dot)

# ── Orange local waypoint markers (ground-truth labels from CURRENT_FRAME) ───
print()
print("Creating local waypoint markers (derived trajectory labels)...")
for k, (wpx, wpy) in enumerate(_wp_positions):
    wpp = f"{root}/WAYPOINT_{k:02d}"
    cone = UsdGeom.Cone.Define(stage, wpp)
    cone.CreateRadiusAttr(0.18)
    cone.CreateHeightAttr(0.5)
    xf = UsdGeom.Xformable(cone.GetPrim())
    xf.ClearXformOpOrder()
    xf.AddTranslateOp().Set(Gf.Vec3d(wpx, wpy, Z_MARKER + 0.25))
    bind(cone.GetPrim(), mat_waypoint)
    set_meta(cone.GetPrim(), "type",          "local_waypoint_target")
    set_meta(cone.GetPrim(), "source",        "derived_from_traj_data_pkl")
    set_meta(cone.GetPrim(), "frame_index",   _wp_indices[k])
    set_meta(cone.GetPrim(), "from_frame",    CURRENT_FRAME)
    set_meta(cone.GetPrim(), "horizon_steps", k + 1)
    print(f"  WAYPOINT_{k:02d}  frame={_wp_indices[k]}  ({wpx:.3f}, {wpy:.3f})")

# ── START sphere + metadata ──────────────────────────────────────────────────
st_sph = UsdGeom.Sphere.Define(stage, f"{root}/START")
st_sph.CreateRadiusAttr(0.35)
st_sph.AddTranslateOp().Set(Gf.Vec3d(sx, sy, Z_MARKER + 0.35))
bind(st_sph.GetPrim(), mat_start)
p = st_sph.GetPrim()
set_meta(p, "scene_id",         SCENE)
set_meta(p, "episode_id",       ep_id)
set_meta(p, "start_position",   [sx, sy])
set_meta(p, "start_yaw_rad",    start_yaw)
set_meta(p, "path_length_m",    path_len)
set_meta(p, "n_frames",         n_frames)
set_meta(p, "initial_dist_m",   init_dist)
set_meta(p, "success_radius_m", goal_r)
set_meta(p, "start_image_path", start_img)
set_meta(p, "camera_prim",      f"{root}/START_CAMERA")

# ── GOAL sphere + metadata ───────────────────────────────────────────────────
gl_sph = UsdGeom.Sphere.Define(stage, f"{root}/GOAL")
gl_sph.CreateRadiusAttr(0.40)
gl_sph.AddTranslateOp().Set(Gf.Vec3d(gx, gy, Z_MARKER + 0.40))
bind(gl_sph.GetPrim(), mat_goal)
p = gl_sph.GetPrim()
set_meta(p, "scene_id",         SCENE)
set_meta(p, "episode_id",       ep_id)
set_meta(p, "goal_position",    [gx, gy])
set_meta(p, "goal_yaw_rad",     goal_yaw)
set_meta(p, "initial_dist_m",   init_dist)
set_meta(p, "success_radius_m", goal_r)
set_meta(p, "goal_image_path",  goal_img)
set_meta(p, "camera_prim",      f"{root}/GOAL_CAMERA")

# ── GNM camera prims ──────────────────────────────────────────────────────────
print()
print("Creating GNM camera prims...")
try:
    make_camera(f"{root}/START_CAMERA",   sx, sy, start_yaw)
    _set_camera_meta(f"{root}/START_CAMERA",   "start",   sx, sy, start_yaw,   0,             start_img)
    print(f"  START_CAMERA   ({sx:.3f}, {sy:.3f}, 1.2m)  yaw={math.degrees(start_yaw):.1f}°")
except Exception as e:
    print(f"  START_CAMERA failed: {e}")

try:
    make_camera(f"{root}/CURRENT_CAMERA", mx, my, mid_yaw)
    _set_camera_meta(f"{root}/CURRENT_CAMERA", "current", mx, my, mid_yaw,     CURRENT_FRAME, mid_img)
    print(f"  CURRENT_CAMERA ({mx:.3f}, {my:.3f}, 1.2m)  yaw={math.degrees(mid_yaw):.1f}°  frame={CURRENT_FRAME}")
except Exception as e:
    print(f"  CURRENT_CAMERA failed: {e}")

try:
    make_camera(f"{root}/GOAL_CAMERA",    gx, gy, goal_yaw)
    _set_camera_meta(f"{root}/GOAL_CAMERA",    "goal",    gx, gy, goal_yaw,    n_steps - 1,   goal_img)
    print(f"  GOAL_CAMERA    ({gx:.3f}, {gy:.3f}, 1.2m)  yaw={math.degrees(goal_yaw):.1f}°")
except Exception as e:
    print(f"  GOAL_CAMERA failed: {e}")

try:
    _all_x = [float(positions[i][0]) for i in range(n_steps)]
    _all_y = [float(positions[i][1]) for i in range(n_steps)]
    _cx = (min(_all_x) + max(_all_x)) / 2
    _cy = (min(_all_y) + max(_all_y)) / 2
    _span = max(max(_all_x) - min(_all_x), max(_all_y) - min(_all_y))
    make_overview_camera(f"{root}/OVERVIEW_CAMERA", _cx, _cy, _span)
    print(f"  OVERVIEW_CAMERA  centre=({_cx:.2f}, {_cy:.2f})  span={_span:.1f} m")
except Exception as e:
    print(f"  OVERVIEW_CAMERA failed: {e}")

# ── Auto-set viewport camera if VIEW= is set ─────────────────────────────────
if VIEW in ("START", "CURRENT", "GOAL", "OVERVIEW"):
    camera_map = {
        "START":    f"{root}/START_CAMERA",
        "CURRENT":  f"{root}/CURRENT_CAMERA",
        "GOAL":     f"{root}/GOAL_CAMERA",
        "OVERVIEW": f"{root}/OVERVIEW_CAMERA",
    }
    target_cam = camera_map[VIEW]
    if _switch_viewport(target_cam):
        print(f"\n  Viewport set to: {target_cam}")

# ── Dashboard state panels (textured planes at Z=4) ───────────────────────────
cx_panel = (sx + gx) / 2
cy_panel = (sy + gy) / 2
PANEL_Z   = 4.0
PANEL_SEP = 5.0

panel_defs = [
    ("START_STATE_PANEL",   str(panels["start_state"]),   cx_panel - PANEL_SEP * 1.5, cy_panel, PANEL_Z, 2.0, 1.2),
    ("CURRENT_STATE_PANEL", str(panels["current_state"]), cx_panel - PANEL_SEP * 0.5, cy_panel, PANEL_Z, 2.0, 1.2),
    ("GOAL_STATE_PANEL",    str(panels["goal_state"]),    cx_panel + PANEL_SEP * 0.5, cy_panel, PANEL_Z, 2.0, 1.2),
    ("PERFORMANCE_PANEL",   str(panels["performance"]),   cx_panel + PANEL_SEP * 1.5, cy_panel, PANEL_Z, 2.4, 1.2),
    # Evidence HUD: above the centre
    ("EVIDENCE_HUD_PANEL",  str(panels["evidence_hud"]),  cx_panel, cy_panel, PANEL_Z + 3.5, 4.3, 1.6),
    # GNM input panel: at mid-point, lower
    ("GNM_INPUT_PANEL",     str(panels["gnm_input"]),     mx, my + 4.0, PANEL_Z + 2.5, 3.2, 1.2),
]

# Camera-view frame panels: placed near sphere markers
panel_defs += [
    ("START_CAMERA_PANEL",   str(panels["start_camera_panel"]),   sx, sy - 3.5, PANEL_Z, 2.0, 1.6),
    ("CURRENT_CAMERA_PANEL", str(panels["current_camera_panel"]), mx, my - 3.5, PANEL_Z, 2.0, 1.6),
    ("GOAL_CAMERA_PANEL",    str(panels["goal_camera_panel"]),    gx, gy - 3.5, PANEL_Z, 2.0, 1.6),
]

if SHOW_PANELS:
    panel_defs += [
        ("CURRENT_OBS_PANEL",  str(panels["gnm_image_panel_obs"]),  sx, sy, PANEL_Z + 1.5, 1.6, 1.2),
        ("GOAL_IMAGE_PANEL",   str(panels["gnm_image_panel_goal"]), gx, gy, PANEL_Z + 1.5, 1.6, 1.2),
    ]

print()
print("Creating image panels...")
for entry in panel_defs:
    name, png_path, px, py, pz, hw, hh = entry
    try:
        create_image_panel(f"{root}/{name}", png_path, px, py, pz, half_w=hw, half_h=hh)
        print(f"  Panel created: {name}")
    except Exception as e:
        print(f"  Panel {name} failed ({e})")

# ── LIVE_GNM_INPUT_DASHBOARD texture plane (when LIVE_DASHBOARD=1) ───────────
_live_dash_panel_path = f"{root}/LIVE_GNM_INPUT_DASHBOARD"
_live_dash_tex_shader_path = f"{_live_dash_panel_path}/mat/Texture"

if LIVE_DASHBOARD or AUTO_PLAY:
    # Generate frame 0 as initial texture
    LIVE_DASH_DIR.mkdir(parents=True, exist_ok=True)
    _init_frame = _make_live_dashboard_frame(0, start_img, sx, sy, start_yaw)
    _init_png   = LIVE_DASH_DIR / "dashboard_000000.png"
    _init_frame.save(_init_png)
    try:
        # Centred above the mid-point of the path at viewing height
        _lx = (sx + gx) / 2
        _ly = (sy + gy) / 2 + 6.0
        create_image_panel(
            _live_dash_panel_path,
            str(_init_png),
            _lx, _ly, PANEL_Z + 4.5,
            half_w=5.0, half_h=1.9,
        )
        print(f"  LIVE_GNM_INPUT_DASHBOARD panel created at ({_lx:.1f}, {_ly:.1f})")
    except Exception as e:
        print(f"  LIVE_GNM_INPUT_DASHBOARD panel failed ({e})")


def _update_live_dash_texture(png_path: Path) -> None:
    """Update the texture on LIVE_GNM_INPUT_DASHBOARD to a new PNG file."""
    prim = stage.GetPrimAtPath(_live_dash_tex_shader_path)
    if not prim.IsValid():
        return
    try:
        prim.GetAttribute("inputs:file").Set(str(png_path))
    except Exception:
        pass


# ── Moving ROBOT_MARKER ───────────────────────────────────────────────────────
robot_xform = UsdGeom.Xform.Define(stage, f"{root}/ROBOT_MARKER")
robot_body  = UsdGeom.Cube.Define(stage, f"{root}/ROBOT_MARKER/body")
robot_body.CreateSizeAttr(0.5)
robot_body.AddTranslateOp().Set(Gf.Vec3d(0, 0, 0.5))
bind(robot_body.GetPrim(), mat_robot)
xformable    = UsdGeom.Xformable(robot_xform.GetPrim())
xformable.ClearXformOpOrder()
translate_op = xformable.AddTranslateOp()
rotate_op    = xformable.AddRotateZOp()
translate_op.Set(Gf.Vec3d(sx, sy, 0.0))
rotate_op.Set(math.degrees(start_yaw))

# ── Final console summary ─────────────────────────────────────────────────────
print()
print("=" * 65)
print("GNM Evidence Dashboard ready.")
print()
print(f"Scene: {SCENE}  |  Episode: {ep_id}  |  Split: {_split_label}")
print()
print("Camera views (select in Stage → Look through selected camera):")
print(f"  /World/GNM_Replay/START_CAMERA   → frame 0 start observation")
print(f"  /World/GNM_Replay/CURRENT_CAMERA → frame {CURRENT_FRAME} mid-trajectory")
print(f"  /World/GNM_Replay/GOAL_CAMERA    → frame {n_steps - 1} goal observation")
print(f"  /World/GNM_Replay/OVERVIEW_CAMERA → top-down path overview")
print()
print("Orange cones = ground-truth local waypoint targets from CURRENT_FRAME")
print("  (derived from traj_data.pkl — NOT predicted model output)")
print()
print("EVIDENCE_HUD_PANEL shows full evidence chain in the scene.")
print()
if LIVE_DASHBOARD or AUTO_PLAY:
    print("LIVE_DASHBOARD=1 — LIVE_GNM_INPUT_DASHBOARD panel will update each frame.")
    print("  Layout: START VIEW | CURRENT LIVE VIEW | GOAL VIEW")
    print(f"  Frames saved to: {LIVE_DASH_DIR}/")
if TOUR:
    print("TOUR mode: switching cameras and saving screenshots...")
else:
    print("Run with TOUR=1 to auto-switch cameras and save screenshots.")
print()
print("  PERFORMANCE_PANEL — SR=20%  OSR=46.7%  NE=6.51m")
print("Press Ctrl-C to exit.")
print("=" * 65)

# ── TOUR mode: guided evidence walk ──────────────────────────────────────────
if TOUR:
    SCREENSHOT_DIR = REPO / "results/bo_reviewer_packet/screenshots"
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    tour_steps = [
        ("START",    f"{root}/START_CAMERA",    SCREENSHOT_DIR / "01_start_camera.png"),
        ("CURRENT",  f"{root}/CURRENT_CAMERA",  SCREENSHOT_DIR / "02_current_camera.png"),
        ("GOAL",     f"{root}/GOAL_CAMERA",     SCREENSHOT_DIR / "03_goal_camera.png"),
        ("OVERVIEW", f"{root}/OVERVIEW_CAMERA", SCREENSHOT_DIR / "04_overview_path.png"),
    ]
    print()
    print("TOUR: starting guided camera walk...")
    for step_name, cam_path, out_png in tour_steps:
        print(f"\n  [{step_name}]  switching viewport to {cam_path}")
        _switch_viewport(cam_path)
        print(f"  Waiting 3 seconds...")
        for _ in range(90):
            app.update()
            time.sleep(1.0 / 30)
        print(f"  Saving screenshot: {out_png}")
        ok = _save_screenshot(out_png)
        if ok:
            print(f"  Saved: {out_png}")
        else:
            print(f"  Screenshot API unavailable.")
            print(f"  Manual: use File → Screenshot in Isaac Sim → save to:")
            print(f"    {out_png}")
    print()
    print("TOUR complete. Screenshots (if saved):")
    for _, _, png in tour_steps:
        status = "OK" if png.exists() else "manual needed"
        print(f"  {png.name:<35} [{status}]")

# ── Waypoint cone translate ops (for per-frame updates) ──────────────────────
_wp_translate_ops = []
for k in range(WAYPOINT_HORIZON):
    wpp  = f"{root}/WAYPOINT_{k:02d}"
    prim = stage.GetPrimAtPath(wpp)
    if prim.IsValid():
        xf = UsdGeom.Xformable(prim)
        ops = xf.GetOrderedXformOps()
        t_op = next((o for o in ops if "translate" in str(o.GetOpName()).lower()), None)
        _wp_translate_ops.append(t_op)
    else:
        _wp_translate_ops.append(None)

# ── Replay loop ───────────────────────────────────────────────────────────────
idx          = 0
dt           = 0.05 / max(0.01, PLAY_SPEED if AUTO_PLAY else SPEED)
_play_active = AUTO_PLAY        # AUTO_PLAY advances automatically from frame 0
_goal_reached_logged = False

while True:
    _rx = float(positions[idx][0])
    _ry = float(positions[idx][1])
    _th = float(yaws[idx]) if idx < len(yaws) else 0.0

    # Move robot marker
    translate_op.Set(Gf.Vec3d(_rx, _ry, 0.0))
    rotate_op.Set(math.degrees(_th))

    # Update orange waypoint cones to current frame's lookahead
    _cur_wp_idx = [min(idx + k + 1, n_steps - 1) for k in range(WAYPOINT_HORIZON)]
    for k, op in enumerate(_wp_translate_ops):
        if op is not None:
            wpx = float(positions[_cur_wp_idx[k]][0])
            wpy = float(positions[_cur_wp_idx[k]][1])
            op.Set(Gf.Vec3d(wpx, wpy, Z_MARKER + 0.25))

    # Stop condition
    _dist_goal = math.hypot(_rx - gx, _ry - gy)
    _at_goal   = _dist_goal <= goal_r
    if _at_goal and not _goal_reached_logged:
        print(f"\n  *** GOAL REACHED ***  frame={idx}  dist={_dist_goal:.3f} m <= {goal_r} m")
        _goal_reached_logged = True

    # Per-frame console log
    if idx % 10 == 0:
        _status = "GOAL REACHED" if _at_goal else "RUNNING"
        print(f"  frame={idx:3d}  x={_rx:.4f}  y={_ry:.4f}"
              f"  yaw={math.degrees(_th):.1f}°"
              f"  dist_goal={_dist_goal:.3f} m  [{_status}]")

    # Live dashboard panel update
    if (LIVE_DASHBOARD or AUTO_PLAY) and idx % max(1, DASHBOARD_EVERY_N) == 0:
        _cur_img = str(best_traj / f"{idx}.jpg")
        _dash    = _make_live_dashboard_frame(idx, _cur_img, _rx, _ry, _th)
        _dash_p  = LIVE_DASH_DIR / f"dashboard_{idx:06d}.png"
        if SAVE_LIVE_FRAMES:
            _dash.save(_dash_p)
        _update_live_dash_texture(_dash_p)
        # Export video at end if requested
        if EXPORT_LIVE_VIDEO and idx == n_steps - 1:
            _vid = LIVE_DASH_DIR / "live_gnm_input_dashboard.mp4"
            print(f"\n  Exporting video → {_vid} ...")
            ok = _try_video_export(LIVE_DASH_DIR, _vid, fps=10)
            print(f"  Video {'saved' if ok else 'export failed'}: {_vid}")

    app.update()
    time.sleep(dt)

    if _play_active:
        idx += 1
        if idx >= n_steps:
            idx = 0
            _goal_reached_logged = False
            print(f"\n  END OF TRAJECTORY — looping back to frame 0")
    else:
        idx = (idx + 1) % n_steps
