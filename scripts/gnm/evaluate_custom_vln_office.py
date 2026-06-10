"""
evaluate_custom_vln_office.py — Evaluate CustomVLN-Office episodes
===================================================================
Computes dataset and navigation metrics for collected episodes.
Does NOT fake model predictions. If gnm_base checkpoint is loadable,
optionally runs inference; otherwise reports label-only metrics.

Outputs:
  results/custom_vln_office/eval_summary.md
  results/custom_vln_office/eval_summary.csv

Usage:
  python3 scripts/gnm/evaluate_custom_vln_office.py --dry-run
  python3 scripts/gnm/evaluate_custom_vln_office.py
"""
import argparse
import csv
import json
import math
import os
import pickle
import sys
from pathlib import Path

import numpy as np

REPO       = Path(__file__).resolve().parents[2]
DATA_ROOT  = REPO / "datasets/custom_vln_office"
CKPT_PATH  = REPO / "checkpoints/gnm_base/best.pt"
OUT_DIR    = REPO / "results/custom_vln_office"
OUT_DIR.mkdir(parents=True, exist_ok=True)
GOAL_RADIUS = 2.0


def _load_episodes() -> list[dict]:
    eps = []
    for split in ("train", "val"):
        split_dir = DATA_ROOT / split
        if not split_dir.exists():
            continue
        for ep_dir in sorted(split_dir.iterdir()):
            pkl = ep_dir / "traj_data.pkl"
            if not pkl.exists():
                continue
            with open(pkl, "rb") as f:
                data = pickle.load(f)
            meta_path = ep_dir / "metadata.json"
            meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
            eps.append({
                "episode_id":   ep_dir.name,
                "split":        split,
                "data":         data,
                "meta":         meta,
                "ep_dir":       ep_dir,
            })
    return eps


def _evaluate_episode(ep: dict) -> dict:
    data = ep["data"]
    pos  = np.array(data["position"])
    T    = len(pos)
    sx, sy = float(pos[0][0]),  float(pos[0][1])
    gx, gy = float(pos[-1][0]), float(pos[-1][1])
    path_len = float(np.linalg.norm(np.diff(pos, axis=0), axis=1).sum())
    final_dist = math.hypot(pos[-1][0] - gx, pos[-1][1] - gy)
    min_dist   = float(np.min(np.sqrt((pos[:, 0] - gx)**2 + (pos[:, 1] - gy)**2)))
    success    = final_dist <= GOAL_RADIUS
    oracle     = min_dist   <= GOAL_RADIUS

    has_labels   = "local_waypoints" in data and len(data["local_waypoints"]) > 0
    n_rgb_frames = len(list((ep["ep_dir"] / "rgb").glob("*.jpg"))) if (ep["ep_dir"] / "rgb").exists() else 0
    has_actions  = (ep["ep_dir"] / "actions.jsonl").exists()

    return {
        "episode_id":         ep["episode_id"],
        "split":              ep["split"],
        "n_frames":           T,
        "n_rgb_frames":       n_rgb_frames,
        "path_length_m":      round(path_len, 3),
        "final_dist_m":       round(final_dist, 3),
        "min_dist_m":         round(min_dist, 3),
        "success":            success,
        "oracle_success":     oracle,
        "has_waypoint_labels":has_labels,
        "has_actions_jsonl":  has_actions,
        "instruction":        data.get("instruction", ""),
    }


def _try_gnm_inference(results: list[dict]) -> str:
    if not CKPT_PATH.exists():
        return "gnm_base checkpoint not found — model inference skipped"
    try:
        import torch
        ckpt = torch.load(str(CKPT_PATH), map_location="cpu")
        keys = list(ckpt.keys()) if isinstance(ckpt, dict) else ["(non-dict checkpoint)"]
        return (f"gnm_base checkpoint loaded OK ({len(keys)} keys). "
                "Full CustomVLN-Office inference pending (episode format differs from VLNVerse).")
    except Exception as e:
        return f"checkpoint load failed: {e}"


def run(dry_run: bool = False) -> None:
    print("CustomVLN-Office Evaluation")
    print("=" * 60)
    print(f"Mode: {'dry-run' if dry_run else 'live'}")

    eps = _load_episodes()
    if not eps:
        print()
        print("No episodes found. Run data collection first:")
        print("  python3 scripts/gnm/collect_custom_vln_office_data.py --dry-run")
        if not dry_run:
            return
        # In dry-run, proceed with empty result to still write the files
    results = [_evaluate_episode(ep) for ep in eps]

    train_r = [r for r in results if r["split"] == "train"]
    val_r   = [r for r in results if r["split"] == "val"]
    all_r   = results

    def _avg(lst, key):
        return round(sum(r[key] for r in lst) / len(lst), 3) if lst else 0.0

    inference_note = _try_gnm_inference(results)

    print(f"\n  Episodes: {len(all_r)} total  ({len(train_r)} train / {len(val_r)} val)")
    if all_r:
        print(f"  Avg path length   : {_avg(all_r, 'path_length_m')} m")
        print(f"  Avg final dist    : {_avg(all_r, 'final_dist_m')} m")
        print(f"  Avg min dist      : {_avg(all_r, 'min_dist_m')} m")
        print(f"  Waypoint labels   : {sum(r['has_waypoint_labels'] for r in all_r)}/{len(all_r)}")
        print(f"  Actions JSONL     : {sum(r['has_actions_jsonl'] for r in all_r)}/{len(all_r)}")
    print(f"\n  GNM inference: {inference_note}")

    # Markdown summary
    md_lines = [
        "# CustomVLN-Office — Evaluation Summary",
        "",
        "**Source:** `evaluate_custom_vln_office.py`  ",
        "**VLNVerse assets used:** NONE  ",
        "**Scene:** independent Isaac Sim primitives",
        "",
        "## Dataset",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total episodes | {len(all_r)} |",
        f"| Train episodes | {len(train_r)} |",
        f"| Val episodes   | {len(val_r)} |",
        f"| Goal radius    | {GOAL_RADIUS} m |",
        "",
        "## Navigation metrics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Avg path length | {_avg(all_r, 'path_length_m')} m |" if all_r else "| Avg path length | N/A |",
        f"| Avg final distance | {_avg(all_r, 'final_dist_m')} m |" if all_r else "| Avg final distance | N/A |",
        f"| Avg min distance | {_avg(all_r, 'min_dist_m')} m |" if all_r else "| Avg min distance | N/A |",
        f"| Episodes with waypoint labels | {sum(r['has_waypoint_labels'] for r in all_r)}/{len(all_r)} |" if all_r else "| Episodes with waypoint labels | N/A |",
        f"| Episodes with actions.jsonl | {sum(r['has_actions_jsonl'] for r in all_r)}/{len(all_r)} |" if all_r else "| Episodes with actions.jsonl | N/A |",
        "",
        "## GNM inference status",
        "",
        f"> {inference_note}",
        "",
        "> **Note:** This is an independent proof-of-method evaluation.",
        "> It is NOT an official VLNVerse benchmark result.",
        "> Official Track A result remains: SR 20.0%, OSR 46.7%, NE 6.51 m.",
        "",
        "## Per-episode breakdown",
        "",
        "| Episode | Split | Frames | Path (m) | Final dist (m) | Min dist (m) | Labels |",
        "|---------|-------|--------|----------|----------------|--------------|--------|",
    ]
    for r in results:
        md_lines.append(
            f"| {r['episode_id']} | {r['split']} | {r['n_frames']} "
            f"| {r['path_length_m']} | {r['final_dist_m']} | {r['min_dist_m']} "
            f"| {'yes' if r['has_waypoint_labels'] else 'no'} |"
        )
    md_lines += [
        "",
        "## Evidence statement",
        "",
        "CustomVLN-Office uses Isaac Sim assets to create an independent navigation environment.",
        "It does not use VLNVerse scenes, trajectories, or labels.",
        "The purpose is to demonstrate that the GNM-style pipeline can be built and controlled",
        "by us from scratch in Isaac Sim.",
    ]

    md_path = OUT_DIR / "eval_summary.md"
    md_path.write_text("\n".join(md_lines))
    print(f"\nMarkdown: {md_path}")

    # CSV
    csv_path = OUT_DIR / "eval_summary.csv"
    if results:
        with open(csv_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=[k for k in results[0] if k not in ("data", "ep_dir")])
            w.writeheader()
            for r in results:
                row = {k: v for k, v in r.items() if k not in ("data", "ep_dir")}
                w.writerow(row)
        print(f"CSV:      {csv_path}")
    else:
        csv_path.write_text("episode_id,split,n_frames,path_length_m,final_dist_m,min_dist_m,success,oracle_success,has_waypoint_labels,has_actions_jsonl\n")
        print(f"CSV:      {csv_path}  (empty — no episodes collected yet)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
