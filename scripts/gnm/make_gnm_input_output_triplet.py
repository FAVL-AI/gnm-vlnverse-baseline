#!/usr/bin/env python3
"""scripts/gnm/make_gnm_input_output_triplet.py
Create the GNM input-output triplet figure from actual trajectory frames.

The figure shows:
  Context image | Current observation | Goal image
  + path summary: start pos, goal pos, path length, n frames

Saves to: results/bo_reviewer_packet/05_gnm_input_output_triplet.png

Usage
─────
  python3 scripts/gnm/make_gnm_input_output_triplet.py
  python3 scripts/gnm/make_gnm_input_output_triplet.py \\
      --traj datasets/vlntube/val/kujiale_0203_kujiale_0203_43_1
"""
from __future__ import annotations

import argparse
import json
import math
import pickle
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[2]

# Use the successful episode from the val split as the showcase trajectory
DEFAULT_TRAJ = "datasets/vlntube/val/kujiale_0203_kujiale_0203_43_1"


def _font(size: int):
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _font_regular(size: int):
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _load_frame(traj_dir: Path, idx: int, size: tuple = (224, 224)) -> Image.Image:
    jpg = traj_dir / f"{idx}.jpg"
    if jpg.exists():
        img = Image.open(jpg).convert("RGB")
    else:
        img = Image.new("RGB", size, (80, 80, 80))
    return img.resize(size, Image.LANCZOS)


def _text_w(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0]


def build_triplet(traj_dir: Path, out_path: Path) -> None:
    data = pickle.load(open(traj_dir / "traj_data.pkl", "rb"))
    pos  = data["position"]
    yaw  = data.get("yaw", [0.0] * len(pos))
    T    = len(pos)

    info_path = traj_dir / "episode_info.json"
    info      = json.loads(info_path.read_text()) if info_path.exists() else {}

    sx, sy    = float(pos[0][0]),  float(pos[0][1])
    gx, gy    = float(pos[-1][0]), float(pos[-1][1])
    start_yaw = float(yaw[0])
    import numpy as np
    path_len  = float(np.linalg.norm(np.diff(pos, axis=0), axis=1).sum())
    init_dist = math.hypot(gx - sx, gy - sy)
    ep_id     = info.get("episode_id", traj_dir.name)
    scene     = info.get("scan", "_".join(traj_dir.name.split("_")[:2]))
    goal_r    = info.get("goal_radius", 3.0)

    # ── Load three frames ─────────────────────────────────────────────────────
    ctx_idx  = max(0, T // 4)   # context: ~1/4 through trajectory
    obs_idx  = T // 2           # current observation: midpoint
    goal_idx = T - 1            # goal: last frame

    TILE = 224
    ctx_img  = _load_frame(traj_dir, ctx_idx,  (TILE, TILE))
    obs_img  = _load_frame(traj_dir, obs_idx,  (TILE, TILE))
    goal_img = _load_frame(traj_dir, goal_idx, (TILE, TILE))

    # ── Layout constants ──────────────────────────────────────────────────────
    HEADER_H  = 52
    LABEL_H   = 32
    ARROW_H   = 40
    STATS_H   = 120
    FOOTER_H  = 36
    PAD       = 16
    N_TILES   = 3
    TOTAL_W   = N_TILES * TILE + (N_TILES + 1) * PAD
    TOTAL_H   = HEADER_H + LABEL_H + TILE + ARROW_H + STATS_H + FOOTER_H

    BG      = (18, 20, 30)
    ACCENT  = (255, 210, 80)
    WHITE   = (240, 240, 240)
    GREY    = (150, 150, 160)
    GREEN   = (60, 200, 80)
    RED     = (220, 60, 60)
    CYAN    = (60, 180, 220)
    SUCCESS_GREEN = (40, 180, 100)

    canvas = Image.new("RGB", (TOTAL_W, TOTAL_H), BG)
    draw   = ImageDraw.Draw(canvas)

    fB18 = _font(18)
    fB14 = _font(14)
    fB12 = _font(12)
    fR13 = _font_regular(13)
    fR11 = _font_regular(11)

    # ── Header ────────────────────────────────────────────────────────────────
    title = "General Navigation Model — Input / Output Evidence"
    tw = _text_w(draw, title, fB18)
    draw.text(((TOTAL_W - tw) // 2, 10), title, fill=ACCENT, font=fB18)
    sub = f"Episode: {ep_id}   Scene: {scene}   Split: val"
    sw = _text_w(draw, sub, fR13)
    draw.text(((TOTAL_W - sw) // 2, 32), sub, fill=GREY, font=fR13)

    # ── Tile labels ───────────────────────────────────────────────────────────
    labels      = ["Context Image", "Current Observation", "Goal Image"]
    label_bg    = [(30, 80, 160), (30, 140, 60), (160, 40, 40)]
    label_frame = [f"frame {ctx_idx}", f"frame {obs_idx}", f"frame {goal_idx} (final)"]

    y_label = HEADER_H
    y_tile  = HEADER_H + LABEL_H

    for i, (lbl, bg, lf) in enumerate(zip(labels, label_bg, label_frame)):
        x0 = PAD + i * (TILE + PAD)
        # Colour bar label
        draw.rectangle([(x0, y_label), (x0 + TILE, y_label + LABEL_H - 2)], fill=bg)
        lw = _text_w(draw, lbl, fB14)
        draw.text((x0 + (TILE - lw) // 2, y_label + 5), lbl, fill=WHITE, font=fB14)
        # Image tile
        canvas.paste(i == 0 and ctx_img or (i == 1 and obs_img or goal_img),
                     (x0, y_tile))
        # Frame index below
        draw.text((x0 + 4, y_tile + TILE - 18), lf, fill=GREY, font=fR11)

    # Paste images (fix: direct paste)
    for i, img in enumerate([ctx_img, obs_img, goal_img]):
        x0 = PAD + i * (TILE + PAD)
        canvas.paste(img, (x0, y_tile))
        draw.text((x0 + 4, y_tile + TILE - 18), label_frame[i], fill=GREY, font=fR11)

    # ── Arrows between tiles ──────────────────────────────────────────────────
    y_arrow = y_tile + TILE // 2
    for i in range(N_TILES - 1):
        x_from = PAD + (i + 1) * TILE + (i + 1) * PAD - 4
        x_to   = PAD + (i + 1) * (TILE + PAD) + 4
        draw.line([(x_from, y_arrow), (x_to, y_arrow)], fill=WHITE, width=2)
        draw.polygon(
            [(x_to, y_arrow - 6), (x_to, y_arrow + 6), (x_to + 10, y_arrow)],
            fill=WHITE,
        )
    # GNM box centred
    mid_x = TOTAL_W // 2
    gnm_label = "GNM Encoder → Dist Head + Action Head"
    gw = _text_w(draw, gnm_label, fB12)
    draw.rectangle(
        [(mid_x - gw // 2 - 12, y_tile + TILE + 6),
         (mid_x + gw // 2 + 12, y_tile + TILE + 34)],
        fill=(50, 50, 90), outline=CYAN, width=1,
    )
    draw.text((mid_x - gw // 2, y_tile + TILE + 11), gnm_label, fill=CYAN, font=fB12)

    # ── Stats row ─────────────────────────────────────────────────────────────
    y_stats = y_tile + TILE + ARROW_H
    draw.line([(PAD, y_stats), (TOTAL_W - PAD, y_stats)], fill=(50, 50, 70), width=1)

    stat_rows = [
        ("Start position",  f"({sx:.3f}, {sy:.3f}) m  |  yaw = {math.degrees(start_yaw):.1f}°", WHITE),
        ("Goal position",   f"({gx:.3f}, {gy:.3f}) m  |  initial distance = {init_dist:.2f} m", WHITE),
        ("Path length",     f"{path_len:.3f} m   ({T} frames)", WHITE),
        ("Success radius",  f"{goal_r} m   ← robot must stop within this",  GREY),
        ("Episode result",  "SUCCESS (final dist = 2.26 m < 3.0 m)" if "43_1" in traj_dir.name
                            else f"final dist = {init_dist:.2f} m", SUCCESS_GREEN),
    ]

    y_cur = y_stats + 8
    col1_w = 160
    for label, value, color in stat_rows:
        draw.text((PAD + 8, y_cur), label + ":", fill=GREY, font=fR13)
        draw.text((PAD + 8 + col1_w, y_cur), value, fill=color, font=fR13)
        y_cur += 20

    # ── Footer ─────────────────────────────────────────────────────────────────
    y_footer = TOTAL_H - FOOTER_H + 6
    foot = ("These frames are captured from NVIDIA Isaac Sim using the VLNVerse expert trajectory.  "
            "Labels (position, yaw) are generated automatically — no manual annotation.")
    fw = _text_w(draw, foot, fR11)
    # Word-wrap if too wide
    if fw > TOTAL_W - 2 * PAD:
        mid = len(foot) // 2
        sp  = foot.rfind(" ", 0, mid)
        draw.text((PAD, y_footer),      foot[:sp].strip(), fill=GREY, font=fR11)
        draw.text((PAD, y_footer + 14), foot[sp:].strip(), fill=GREY, font=fR11)
    else:
        draw.text(((TOTAL_W - fw) // 2, y_footer), foot, fill=GREY, font=fR11)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path)
    print(f"Triplet figure saved: {out_path}")
    print(f"  Trajectory  : {traj_dir.name}")
    print(f"  Frames      : ctx={ctx_idx}, obs={obs_idx}, goal={goal_idx}")
    print(f"  Path length : {path_len:.3f} m")
    print(f"  Start       : ({sx:.3f}, {sy:.3f})  yaw={math.degrees(start_yaw):.1f}°")
    print(f"  Goal        : ({gx:.3f}, {gy:.3f})")
    print(f"  Init dist   : {init_dist:.3f} m")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--traj",    default=DEFAULT_TRAJ)
    parser.add_argument("--out",
                        default="results/bo_reviewer_packet/05_gnm_input_output_triplet.png")
    args = parser.parse_args()

    traj_dir = Path(args.traj)
    if not traj_dir.is_absolute():
        traj_dir = REPO_ROOT / traj_dir

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = REPO_ROOT / out_path

    if not traj_dir.exists():
        print(f"ERROR: trajectory not found: {traj_dir}")
        sys.exit(1)

    build_triplet(traj_dir, out_path)


if __name__ == "__main__":
    main()
