#!/usr/bin/env python3
"""scripts/gnm/make_evidence_panel.py
Generate the GNM architecture evidence panel PNG from actual trajectory frames.

Creates:
  results/figures/gnm_architecture_evidence_panel.png
    — Current observation image | Context image | Goal image
      with labels and architecture annotation

  results/figures/gnm_image_panel_obs.png   — current obs (for USD plane)
  results/figures/gnm_image_panel_goal.png  — goal image (for USD plane)

Usage
─────
  python3 scripts/gnm/make_evidence_panel.py \\
      --traj datasets/vlntube/train/kujiale_0118_kujiale_0118_25_3

  python3 scripts/gnm/make_evidence_panel.py   # uses longest val trajectory
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[2]


def _pick_trajectory(data_root: Path) -> Path:
    """Pick the longest trajectory in the val split for display."""
    import pickle
    val_dir = data_root / "val"
    best, best_len = None, 0
    for d in sorted(val_dir.iterdir()):
        pkl = d / "traj_data.pkl"
        if not pkl.exists():
            continue
        try:
            data = pickle.load(open(pkl, "rb"))
            n = len(data["position"])
            if n > best_len:
                best, best_len = d, n
        except Exception:
            continue
    return best


def _load_frame(traj_dir: Path, idx: int, size: tuple[int, int] = (192, 192)) -> Image.Image:
    jpg = traj_dir / f"{idx}.jpg"
    if not jpg.exists():
        img = Image.new("RGB", size, (128, 128, 128))
    else:
        img = Image.open(jpg).convert("RGB")
    return img.resize(size, Image.LANCZOS)


def _add_label(img: Image.Image, text: str, bg: tuple, fg: tuple = (255, 255, 255)) -> Image.Image:
    LABEL_H = 28
    canvas = Image.new("RGB", (img.width, img.height + LABEL_H), bg)
    draw   = ImageDraw.Draw(canvas)
    canvas.paste(img, (0, 0))
    draw.rectangle([(0, img.height), (img.width, img.height + LABEL_H)], fill=bg)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
    except Exception:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((img.width - tw) // 2, img.height + (LABEL_H - th) // 2),
        text, fill=fg, font=font,
    )
    return canvas


def build_panel(traj_dir: Path, out_dir: Path) -> None:
    import pickle
    data = pickle.load(open(traj_dir / "traj_data.pkl", "rb"))
    T    = len(data["position"])
    mid  = T // 2

    obs_img  = _load_frame(traj_dir, 0)
    ctx_img  = _load_frame(traj_dir, mid)
    goal_img = _load_frame(traj_dir, T - 1)

    # Save individual panels for USD plane textures
    out_dir.mkdir(parents=True, exist_ok=True)
    obs_path  = out_dir / "gnm_image_panel_obs.png"
    goal_path = out_dir / "gnm_image_panel_goal.png"
    obs_img.save(obs_path)
    goal_img.save(goal_path)
    print(f"  obs panel : {obs_path}")
    print(f"  goal panel: {goal_path}")

    # Build labelled tiles
    TILE = 192
    obs_tile  = _add_label(obs_img,  "Current Observation",    bg=(30, 120, 30))
    ctx_tile  = _add_label(ctx_img,  "Context Frame (mid)",    bg=(30, 80, 160))
    goal_tile = _add_label(goal_img, "Goal Image",             bg=(160, 30, 30))

    H = obs_tile.height
    W = obs_tile.width

    # Header
    HEADER_H   = 40
    FOOTER_H   = 56
    PADDING    = 12
    total_w    = 3 * W + 4 * PADDING
    total_h    = HEADER_H + H + FOOTER_H

    canvas = Image.new("RGB", (total_w, total_h), (25, 25, 35))
    draw   = ImageDraw.Draw(canvas)

    # Header text
    try:
        hfont = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
        sfont = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
    except Exception:
        hfont = ImageFont.load_default()
        sfont = hfont

    title = "General Navigation Model — Input Evidence"
    tbbox = draw.textbbox((0, 0), title, font=hfont)
    tw    = tbbox[2] - tbbox[0]
    draw.text(((total_w - tw) // 2, 8), title, fill=(255, 220, 100), font=hfont)

    # Tiles
    y0 = HEADER_H
    for i, tile in enumerate([obs_tile, ctx_tile, goal_tile]):
        x0 = PADDING + i * (W + PADDING)
        canvas.paste(tile, (x0, y0))

    # Arrow annotations between tiles
    arrow_y  = y0 + H // 2
    for i in range(2):
        x_start = PADDING + (i + 1) * W + (i + 1) * PADDING - 4
        x_end   = PADDING + (i + 1) * (W + PADDING) + 4
        draw.line([(x_start, arrow_y), (x_end, arrow_y)], fill=(200, 200, 200), width=2)
        draw.polygon(
            [(x_end, arrow_y - 5), (x_end, arrow_y + 5), (x_end + 8, arrow_y)],
            fill=(200, 200, 200),
        )

    # Footer
    footer1 = "Encoder → shared feature space → Distance head + Action/Waypoint head"
    footer2 = f"Trajectory: {traj_dir.name}   Frames: {T}   Output: local waypoint path (cyan prims in Isaac Sim)"
    fb1 = draw.textbbox((0, 0), footer1, font=sfont)
    fb2 = draw.textbbox((0, 0), footer2, font=sfont)
    fy = y0 + H + 8
    draw.text(((total_w - (fb1[2] - fb1[0])) // 2, fy),      footer1, fill=(180, 180, 180), font=sfont)
    draw.text(((total_w - (fb2[2] - fb2[0])) // 2, fy + 22), footer2, fill=(140, 140, 140), font=sfont)

    panel_path = out_dir / "gnm_architecture_evidence_panel.png"
    canvas.save(panel_path)
    print(f"  panel     : {panel_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--traj",      default=None,
                        help="Trajectory folder path (default: longest val trajectory)")
    parser.add_argument("--data-root", default="datasets/vlntube")
    parser.add_argument("--out-dir",   default="results/figures")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir

    if args.traj:
        traj_dir = Path(args.traj)
        if not traj_dir.is_absolute():
            traj_dir = REPO_ROOT / traj_dir
    else:
        data_root = Path(args.data_root)
        if not data_root.is_absolute():
            data_root = REPO_ROOT / data_root
        traj_dir = _pick_trajectory(data_root)
        if traj_dir is None:
            print("ERROR: no trajectories found")
            sys.exit(1)

    print(f"Using trajectory: {traj_dir.name}")
    build_panel(traj_dir, out_dir)


if __name__ == "__main__":
    main()
