#!/usr/bin/env python3
"""Track A deployable stop-policy ablation.

This script tests runtime-only stop policies using GNM outputs:
- dist_pred
- action_pred / waypoint norm

Important:
Stop decisions do NOT use goal_pos, min_dist_m, oracle_success, or true
distance-to-goal. Ground truth is used only after rollout to compute metrics.
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
from omegaconf import OmegaConf

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from gnm_vlnverse.evaluation.evaluator import GNMEvaluator
from gnm_vlnverse.evaluation.metrics import (
    nav_error,
    oracle_success,
    path_length,
    success,
)
from gnm_vlnverse.models.gnm import build_gnm


SUCCESS_RADIUS_M = 3.0


def load_checkpoint_and_config(ckpt_path: Path, cfg_path: Path, device: torch.device):
    ckpt = torch.load(ckpt_path, map_location=device)

    embedded = ckpt.get("cfg", {})
    if isinstance(embedded, dict) and "model" in embedded:
        cfg = embedded
    else:
        cfg = OmegaConf.to_container(OmegaConf.load(cfg_path), resolve=True)

    model = build_gnm(cfg["model"])
    state = ckpt["ema_state"] if ckpt.get("ema_state") is not None else ckpt["model_state"]
    model.load_state_dict(state)
    model.eval()
    return model, cfg


def policy_should_stop(
    policy: str,
    dist_pred: float,
    wp_norm: float,
    state: dict[str, int],
    dist_threshold: float,
    wp_threshold: float,
    k: int = 3,
) -> bool:
    if policy == "baseline_dist":
        return dist_pred < dist_threshold

    if policy == "stable_dist_k3":
        state["dist_low"] = state.get("dist_low", 0) + 1 if dist_pred < dist_threshold else 0
        return state["dist_low"] >= k

    if policy == "waypoint_norm_k3":
        state["wp_low"] = state.get("wp_low", 0) + 1 if wp_norm < wp_threshold else 0
        return state["wp_low"] >= k

    if policy == "hybrid_dist_waypoint_k3":
        both_low = dist_pred < dist_threshold and wp_norm < wp_threshold
        state["hybrid_low"] = state.get("hybrid_low", 0) + 1 if both_low else 0
        return state["hybrid_low"] >= k

    raise ValueError(f"Unknown policy: {policy}")


def precompute_predictions(evaluator: GNMEvaluator, traj_dir: Path, goal_idx: int):
    with open(traj_dir / "traj_data.pkl", "rb") as f:
        data = pickle.load(f)

    positions_gt = data["position"]
    yaws_gt = data["yaw"]
    T = len(positions_gt)

    if goal_idx == -1:
        goal_idx = T - 1

    start_frame = evaluator._load_frame_np(traj_dir, 0)
    goal_np = evaluator._load_frame_np(traj_dir, goal_idx)
    evaluator.reset_context(start_frame)

    preds = []
    for step in range(min(T - 1, evaluator.max_steps)):
        frame_np = evaluator._load_frame_np(traj_dir, min(step, T - 1))
        dist_pred, action_pred = evaluator.predict(frame_np, goal_np)
        wp_norm = float(np.linalg.norm(action_pred[:2]))
        preds.append(
            {
                "step": step,
                "dist_pred": float(dist_pred),
                "action_pred": np.asarray(action_pred, dtype=np.float32),
                "wp_norm": wp_norm,
            }
        )

    return data, positions_gt, yaws_gt, goal_idx, preds


def rollout_policy(
    policy: str,
    traj_dir: Path,
    evaluator: GNMEvaluator,
    dist_threshold: float,
    wp_threshold: float,
):
    data, positions_gt, yaws_gt, goal_idx, preds = precompute_predictions(
        evaluator, traj_dir, -1
    )

    goal_pos = tuple(positions_gt[goal_idx].tolist())
    ref_path = [tuple(p.tolist()) for p in positions_gt]

    sim_pos = np.array(positions_gt[0], dtype=np.float32)
    sim_yaw = float(yaws_gt[0])
    actual_path = [tuple(sim_pos.tolist())]

    state: dict[str, int] = {}
    stop_fired = False
    stop_step = None

    dist_values = []
    wp_values = []

    for item in preds:
        step = int(item["step"])
        dist_pred = float(item["dist_pred"])
        action_pred = item["action_pred"]
        wp_norm = float(item["wp_norm"])

        dist_values.append(dist_pred)
        wp_values.append(wp_norm)

        cos_y = np.cos(sim_yaw)
        sin_y = np.sin(sim_yaw)
        dx_world = cos_y * action_pred[0] - sin_y * action_pred[1]
        dy_world = sin_y * action_pred[0] + cos_y * action_pred[1]
        sim_pos = sim_pos + np.array([dx_world, dy_world], dtype=np.float32)
        actual_path.append(tuple(sim_pos.tolist()))

        if policy_should_stop(
            policy,
            dist_pred,
            wp_norm,
            state,
            dist_threshold,
            wp_threshold,
        ):
            stop_fired = True
            stop_step = step
            break

    ne = nav_error(actual_path, goal_pos)
    s = success(ne, SUCCESS_RADIUS_M)
    osr = oracle_success(actual_path, goal_pos, SUCCESS_RADIUS_M)
    tl = path_length(actual_path)

    return {
        "episode_id": traj_dir.name,
        "policy": policy,
        "stop_fired": stop_fired,
        "stop_step": "" if stop_step is None else stop_step,
        "n_steps": len(actual_path),
        "final_dist_m": ne,
        "success": s,
        "oracle_success": osr,
        "path_length_m": tl,
        "dist_pred_mean": float(np.mean(dist_values)) if dist_values else float("nan"),
        "dist_pred_min": float(np.min(dist_values)) if dist_values else float("nan"),
        "wp_norm_mean": float(np.mean(wp_values)) if wp_values else float("nan"),
        "wp_norm_min": float(np.min(wp_values)) if wp_values else float("nan"),
    }


def summarise(policy: str, rows: list[dict]):
    n = len(rows)
    sr = 100.0 * sum(bool(r["success"]) for r in rows) / n if n else 0.0
    osr = 100.0 * sum(bool(r["oracle_success"]) for r in rows) / n if n else 0.0
    ne = sum(float(r["final_dist_m"]) for r in rows) / n if n else 0.0
    tl = sum(float(r["path_length_m"]) for r in rows) / n if n else 0.0
    fired_rows = [r for r in rows if bool(r["stop_fired"])]
    fired = len(fired_rows)
    mean_stop = (
        sum(float(r["stop_step"]) for r in fired_rows) / fired
        if fired
        else float("nan")
    )
    return {
        "policy": policy,
        "episodes": n,
        "SR_percent": sr,
        "OSR_percent": osr,
        "NE_m": ne,
        "TL_m": tl,
        "stop_fired": fired,
        "mean_stop_step": mean_stop,
    }


def write_markdown(path: Path, ckpt: Path, dist_threshold: float, wp_threshold: float, summaries: list[dict]):
    lines = [
        "# Track A Deployable Stop-Policy Ablation",
        "",
        f"Checkpoint: `{ckpt}`",
        "",
        f"Distance threshold: `{dist_threshold}`",
        f"Waypoint-norm threshold: `{wp_threshold}`",
        "",
        "Stop decisions use only runtime GNM outputs: `dist_pred` and `action_pred`.",
        "Oracle geometry is used only after rollout for metrics.",
        "",
        "## Results",
        "",
        "| Policy | Episodes | SR | OSR | NE (m) | TL (m) | Stop fired | Mean stop step |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for s in summaries:
        mean_stop = s["mean_stop_step"]
        mean_stop_text = "n/a" if math.isnan(mean_stop) else f"{mean_stop:.1f}"
        lines.append(
            f"| {s['policy']} | {s['episodes']} | "
            f"{s['SR_percent']:.1f}% | {s['OSR_percent']:.1f}% | "
            f"{s['NE_m']:.2f} | {s['TL_m']:.2f} | "
            f"{s['stop_fired']} | {mean_stop_text} |"
        )

    lines += [
        "",
        "## Interpretation",
        "",
        "This ablation tests whether simple runtime-only stopping gates can close part of the SR/OSR gap without oracle geometry.",
        "",
        "If SR does not improve beyond the baseline, the next step is a calibrated or learned stop head rather than another hand-tuned threshold.",
        "",
    ]
    path.write_text("\n".join(lines))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ckpt", required=True)
    parser.add_argument("--cfg", default="configs/gnm/gnm_base.yaml")
    parser.add_argument("--data-root", default="datasets/vlntube")
    parser.add_argument("--split", default="val")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--dist-threshold", type=float, default=0.15)
    parser.add_argument("--wp-threshold", type=float, default=0.20)
    parser.add_argument(
        "--out-dir",
        default="results/bo_reviewer_packet/deployable_stop_policy",
    )
    args = parser.parse_args()

    ckpt_path = Path(args.ckpt)
    if not ckpt_path.is_absolute():
        ckpt_path = REPO_ROOT / ckpt_path

    cfg_path = Path(args.cfg)
    if not cfg_path.is_absolute():
        cfg_path = REPO_ROOT / cfg_path

    data_root = Path(args.data_root)
    if not data_root.is_absolute():
        data_root = REPO_ROOT / data_root

    device = torch.device(args.device if torch.cuda.is_available() else "cpu")
    model, cfg = load_checkpoint_and_config(ckpt_path, cfg_path, device)

    evaluator = GNMEvaluator(
        model=model,
        action_std=tuple(cfg["data"]["action_std"]),
        context_size=cfg["model"]["context_size"],
        image_size=tuple(cfg["data"]["image_size"]),
        stop_threshold=args.dist_threshold,
        max_steps=cfg.get("evaluation", {}).get("max_steps", 500),
        device=str(device),
        track="A",
    )

    split_dir = data_root / args.split
    traj_dirs = sorted(d for d in split_dir.iterdir() if d.is_dir())

    policies = [
        "baseline_dist",
        "stable_dist_k3",
        "waypoint_norm_k3",
        "hybrid_dist_waypoint_k3",
    ]

    all_rows = []
    summaries = []

    for policy in policies:
        rows = [
            rollout_policy(
                policy,
                traj_dir,
                evaluator,
                args.dist_threshold,
                args.wp_threshold,
            )
            for traj_dir in traj_dirs
        ]
        all_rows.extend(rows)
        summaries.append(summarise(policy, rows))

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    summary_csv = out_dir / "17_deployable_stop_policy.csv"
    details_csv = out_dir / "17_deployable_stop_policy_details.csv"
    md_path = out_dir / "17_deployable_stop_policy.md"

    with summary_csv.open("w", newline="") as f:
        fieldnames = [
            "policy",
            "episodes",
            "SR_percent",
            "OSR_percent",
            "NE_m",
            "TL_m",
            "stop_fired",
            "mean_stop_step",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for s in summaries:
            writer.writerow(
                {
                    "policy": s["policy"],
                    "episodes": s["episodes"],
                    "SR_percent": f"{s['SR_percent']:.1f}",
                    "OSR_percent": f"{s['OSR_percent']:.1f}",
                    "NE_m": f"{s['NE_m']:.2f}",
                    "TL_m": f"{s['TL_m']:.2f}",
                    "stop_fired": s["stop_fired"],
                    "mean_stop_step": (
                        ""
                        if math.isnan(s["mean_stop_step"])
                        else f"{s['mean_stop_step']:.1f}"
                    ),
                }
            )

    with details_csv.open("w", newline="") as f:
        fieldnames = [
            "episode_id",
            "policy",
            "stop_fired",
            "stop_step",
            "n_steps",
            "final_dist_m",
            "success",
            "oracle_success",
            "path_length_m",
            "dist_pred_mean",
            "dist_pred_min",
            "wp_norm_mean",
            "wp_norm_min",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in all_rows:
            out = dict(r)
            for key in [
                "final_dist_m",
                "path_length_m",
                "dist_pred_mean",
                "dist_pred_min",
                "wp_norm_mean",
                "wp_norm_min",
            ]:
                out[key] = f"{float(out[key]):.4f}"
            writer.writerow(out)

    write_markdown(md_path, ckpt_path, args.dist_threshold, args.wp_threshold, summaries)

    print(summary_csv)
    print(details_csv)
    print(md_path)


if __name__ == "__main__":
    main()
