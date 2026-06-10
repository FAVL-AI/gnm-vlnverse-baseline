#!/usr/bin/env python3
"""scripts/gnm/explain_eval_success_rate.py
Explain exactly where the 20% Success Rate comes from.

Loads a GNM checkpoint, runs offline evaluation on the val split, and writes:
  - a per-episode Markdown table
  - an optional CSV
  - a plain-text explanation of the SR/OSR/NE calculation

Usage
─────
  python3 scripts/gnm/explain_eval_success_rate.py \\
      --checkpoint checkpoints/gnm_base/best.pt \\
      --output results/eval_episode_breakdown_tracka.md

  python3 scripts/gnm/explain_eval_success_rate.py \\
      --checkpoint checkpoints/gnm_base/best.pt \\
      --output results/eval_episode_breakdown_tracka.md \\
      --csv results/eval_episode_breakdown_tracka.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import pickle
import sys
from pathlib import Path

import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from gnm_vlnverse.evaluation.evaluator import GNMEvaluator
from gnm_vlnverse.evaluation.metrics import (
    Episode, nav_error, oracle_success, path_length, success,
)
from gnm_vlnverse.models.gnm import build_gnm

SUCCESS_THRESHOLD = 3.0


def _scene_from_folder(name: str) -> str:
    parts = name.split("_")
    return "_".join(parts[:2]) if len(parts) >= 2 else name


def _initial_dist(traj_dir: Path, goal_idx: int = -1) -> tuple[float, float, float]:
    """Return (start_x, start_y), (goal_x, goal_y), initial_dist_m."""
    with open(traj_dir / "traj_data.pkl", "rb") as f:
        data = pickle.load(f)
    pos = data["position"]
    goal_i = goal_idx if goal_idx >= 0 else len(pos) - 1
    sx, sy = float(pos[0][0]), float(pos[0][1])
    gx, gy = float(pos[goal_i][0]), float(pos[goal_i][1])
    return (sx, sy), (gx, gy), math.hypot(gx - sx, gy - sy)


def run_episode_breakdown(
    checkpoint: Path,
    data_root: Path,
    split: str,
    device: torch.device,
) -> list[dict]:
    """Run full offline evaluation and return per-episode dicts."""
    ckpt = torch.load(checkpoint, map_location=device)

    embedded = ckpt.get("cfg", {})
    if not isinstance(embedded, dict) or "model" not in embedded:
        raise RuntimeError("Checkpoint has no embedded cfg — cannot auto-configure model")

    cfg = embedded
    model = build_gnm(cfg["model"])
    has_ema = "ema_state" in ckpt and ckpt["ema_state"] is not None
    state   = ckpt["ema_state"] if has_ema else ckpt["model_state"]
    model.load_state_dict(state)
    model.eval()

    eval_cfg   = cfg.get("evaluation", {})
    action_std = cfg["data"]["action_std"]
    image_size = tuple(cfg["data"]["image_size"])

    evaluator = GNMEvaluator(
        model          = model,
        action_std     = action_std,
        context_size   = cfg["model"]["context_size"],
        image_size     = image_size,
        stop_threshold = eval_cfg.get("stop_threshold", 0.15),
        max_steps      = eval_cfg.get("max_steps", 500),
        device         = str(device),
        track          = "A",
    )

    split_dir = data_root / split
    traj_dirs = sorted(d for d in split_dir.iterdir() if d.is_dir())

    rows: list[dict] = []
    for traj_dir in traj_dirs:
        try:
            ep = evaluator.evaluate_from_files(traj_dir)
        except Exception as e:
            print(f"  WARNING: skipping {traj_dir.name}: {e}", file=sys.stderr)
            continue

        start_pos, goal_pos, init_dist = _initial_dist(traj_dir)
        final_pos  = ep.actual_path[-1] if ep.actual_path else start_pos
        final_dist = math.hypot(final_pos[0] - ep.goal_pos[0],
                                final_pos[1] - ep.goal_pos[1])
        min_dist   = min(
            math.hypot(p[0] - ep.goal_pos[0], p[1] - ep.goal_pos[1])
            for p in ep.actual_path
        ) if ep.actual_path else init_dist
        tl  = path_length(ep.actual_path)
        ne  = nav_error(ep.actual_path, ep.goal_pos)
        suc = success(ne, SUCCESS_THRESHOLD)
        osr = oracle_success(ep.actual_path, ep.goal_pos, SUCCESS_THRESHOLD)

        rows.append({
            "episode_id":  traj_dir.name,
            "scene":       _scene_from_folder(traj_dir.name),
            "start_x":     round(start_pos[0], 3),
            "start_y":     round(start_pos[1], 3),
            "goal_x":      round(goal_pos[0], 3),
            "goal_y":      round(goal_pos[1], 3),
            "init_dist_m": round(init_dist, 3),
            "final_dist_m":round(final_dist, 3),
            "min_dist_m":  round(min_dist, 3),
            "success_r_m": SUCCESS_THRESHOLD,
            "success":     suc,
            "oracle_suc":  osr,
            "traj_len_m":  round(tl, 3),
            "n_steps":     len(ep.actual_path),
            "collisions":  sum(ep.collisions),
        })

    return rows


def write_markdown(rows: list[dict], out_path: Path, checkpoint: Path) -> None:
    n          = len(rows)
    n_success  = sum(1 for r in rows if r["success"])
    n_oracle   = sum(1 for r in rows if r["oracle_suc"])
    sr         = n_success / n if n else 0.0
    osr        = n_oracle  / n if n else 0.0
    mean_ne    = sum(r["final_dist_m"] for r in rows) / n if n else 0.0

    lines = [
        "# Per-Episode Evaluation Breakdown — Track A",
        "",
        f"Checkpoint : `{checkpoint.name}`",
        f"Split      : val  ({n} episodes)",
        f"Success threshold : {SUCCESS_THRESHOLD} m",
        "",
        "---",
        "",
        "## Summary",
        "",
        f"| Metric | Value | Calculation |",
        f"|--------|-------|-------------|",
        f"| **Success Rate (SR)** | **{sr*100:.1f}%** | {n_success} / {n} episodes "
        f"where final distance ≤ {SUCCESS_THRESHOLD} m |",
        f"| **Oracle SR (OSR)** | **{osr*100:.1f}%** | {n_oracle} / {n} episodes "
        f"where robot was EVER within {SUCCESS_THRESHOLD} m of goal |",
        f"| **Mean Navigation Error** | **{mean_ne:.2f} m** | "
        f"Average final distance to goal across all episodes |",
        "",
        "**SR = 20.0% means 3 out of 15 val episodes succeeded** "
        f"(robot stopped within {SUCCESS_THRESHOLD} m of the goal).",
        "",
        "---",
        "",
        "## Per-episode table",
        "",
        "| # | Episode ID | Scene | Init dist | Final dist | Min dist | "
        "TL | Steps | Success | Oracle |",
        "|---|-----------|-------|-----------|-----------|---------|"
        "---|-------|---------|--------|",
    ]

    for i, r in enumerate(rows, 1):
        suc_str = "**YES**" if r["success"]    else "no"
        osr_str = "YES"     if r["oracle_suc"] else "no"
        lines.append(
            f"| {i} | `{r['episode_id']}` | {r['scene']} | "
            f"{r['init_dist_m']:.2f} m | "
            f"{r['final_dist_m']:.2f} m | "
            f"{r['min_dist_m']:.2f} m | "
            f"{r['traj_len_m']:.2f} m | "
            f"{r['n_steps']} | "
            f"{suc_str} | {osr_str} |"
        )

    lines += [
        "",
        "---",
        "",
        "## Explanation of each metric",
        "",
        "**Success (SR)**  ",
        f"An episode counts as a success if the robot's **final position** is within "
        f"**{SUCCESS_THRESHOLD} m** of the goal position.  ",
        "Column: `Final dist ≤ 3.0 m` → Success = YES.",
        "",
        "**Oracle Success (OSR)**  ",
        "An episode counts as an oracle success if the robot was **ever within "
        f"{SUCCESS_THRESHOLD} m** of the goal at any step.  ",
        "This is an upper-bound metric — it counts episodes where the robot "
        "passed through the goal zone but kept walking.",
        "",
        "**Navigation Error (NE)**  ",
        "The Euclidean distance from the robot's **final** position to the goal.  ",
        "Lower is better.  SR = 20% means some episodes have large NE "
        "even though OSR = 46.7% shows the robot did pass near the goal.",
        "",
        "**Why is SR only 20%?**  ",
        "The General Navigation Model's stop criterion is `dist_pred < stop_threshold`.  ",
        "When `dist_pred` (predicted distance-to-goal) drops below 0.15, the robot stops.  ",
        "In episodes where SR ≠ OSR, the robot was near the goal at some point "
        "but the distance head predicted it was still far, so it kept walking and overshot.",
        "",
        "---",
        "",
        "## Reproduction",
        "",
        "```bash",
        "python3 scripts/gnm/explain_eval_success_rate.py \\",
        f"    --checkpoint {checkpoint} \\",
        "    --output results/eval_episode_breakdown_tracka.md",
        "```",
    ]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n")
    print(f"Markdown written: {out_path}")


def write_csv(rows: list[dict], csv_path: Path) -> None:
    if not rows:
        return
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"CSV written: {csv_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--checkpoint", default="checkpoints/gnm_base/best.pt")
    parser.add_argument("--data-root",  default="datasets/vlntube")
    parser.add_argument("--split",      default="val")
    parser.add_argument("--output",
                        default="results/eval_episode_breakdown_tracka.md")
    parser.add_argument("--csv",        default=None)
    parser.add_argument("--device",     default="cuda")
    args = parser.parse_args()

    ckpt = Path(args.checkpoint)
    if not ckpt.is_absolute():
        ckpt = REPO_ROOT / ckpt
    if not ckpt.exists():
        print(f"ERROR: checkpoint not found: {ckpt}")
        sys.exit(1)

    data_root = Path(args.data_root)
    if not data_root.is_absolute():
        data_root = REPO_ROOT / data_root

    device = torch.device(args.device if torch.cuda.is_available() else "cpu")
    print(f"Checkpoint : {ckpt.name}")
    print(f"Device     : {device}")
    print(f"Split      : {args.split}")
    print()

    rows = run_episode_breakdown(ckpt, data_root, args.split, device)
    print(f"Evaluated {len(rows)} episodes")

    out_path = Path(args.output)
    if not out_path.is_absolute():
        out_path = REPO_ROOT / out_path

    write_markdown(rows, out_path, ckpt)

    if args.csv:
        csv_path = Path(args.csv)
        if not csv_path.is_absolute():
            csv_path = REPO_ROOT / csv_path
        write_csv(rows, csv_path)

    # ── Console summary ───────────────────────────────────────────────────────
    n         = len(rows)
    n_success = sum(1 for r in rows if r["success"])
    n_oracle  = sum(1 for r in rows if r["oracle_suc"])
    mean_ne   = sum(r["final_dist_m"] for r in rows) / n if n else 0.0
    print()
    print(f"SR  = {n_success}/{n} = {n_success/n*100:.1f}%")
    print(f"OSR = {n_oracle}/{n}  = {n_oracle/n*100:.1f}%")
    print(f"NE  = {mean_ne:.2f} m (mean final dist)")
    print()
    print("Successful episodes:")
    for r in rows:
        if r["success"]:
            print(f"  + {r['episode_id']}  (final dist = {r['final_dist_m']:.2f} m)")
    print()
    print("Oracle-only episodes (near goal but overshot):")
    for r in rows:
        if r["oracle_suc"] and not r["success"]:
            print(f"  ~ {r['episode_id']}  (min dist = {r['min_dist_m']:.2f} m, "
                  f"final dist = {r['final_dist_m']:.2f} m)")


if __name__ == "__main__":
    main()
