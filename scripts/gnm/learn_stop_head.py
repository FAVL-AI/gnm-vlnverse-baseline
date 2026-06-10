#!/usr/bin/env python3
"""Learned/calibrated Track A stop head.

This is a lightweight logistic stop head trained from runtime-only GNM traces.

Runtime features:
- dist_pred
- waypoint norm
- rolling dist mean
- rolling waypoint mean
- dist trend
- waypoint trend

Ground truth is used only to create training labels and final metrics.
It is never used inside the runtime stop decision.
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

from gnm_vlnverse.evaluation.metrics import nav_error, oracle_success, path_length, success
from scripts.gnm.ablate_deployable_stop_policy import (
    SUCCESS_RADIUS_M,
    load_checkpoint_and_config,
    precompute_predictions,
)
from gnm_vlnverse.evaluation.evaluator import GNMEvaluator


def _features(dist_hist: list[float], wp_hist: list[float], window: int = 3) -> np.ndarray:
    d = np.asarray(dist_hist, dtype=np.float32)
    w = np.asarray(wp_hist, dtype=np.float32)
    k = min(window, len(d))

    dist_now = float(d[-1])
    wp_now = float(w[-1])
    dist_mean = float(d[-k:].mean())
    wp_mean = float(w[-k:].mean())

    if len(d) >= 2:
        dist_trend = float(d[-1] - d[max(0, len(d) - k)])
        wp_trend = float(w[-1] - w[max(0, len(w) - k)])
    else:
        dist_trend = 0.0
        wp_trend = 0.0

    return np.array(
        [dist_now, wp_now, dist_mean, wp_mean, dist_trend, wp_trend],
        dtype=np.float32,
    )


def build_trace_rows(evaluator: GNMEvaluator, traj_dir: Path, window: int = 3) -> list[dict]:
    data, positions_gt, yaws_gt, goal_idx, preds = precompute_predictions(evaluator, traj_dir, -1)

    goal_pos = np.asarray(positions_gt[goal_idx], dtype=np.float32)
    sim_pos = np.asarray(positions_gt[0], dtype=np.float32)
    sim_yaw = float(yaws_gt[0])

    dist_hist: list[float] = []
    wp_hist: list[float] = []
    rows: list[dict] = []

    for item in preds:
        step = int(item["step"])
        dist_pred = float(item["dist_pred"])
        action_pred = np.asarray(item["action_pred"], dtype=np.float32)
        wp_norm = float(item["wp_norm"])

        dist_hist.append(dist_pred)
        wp_hist.append(wp_norm)

        x = _features(dist_hist, wp_hist, window=window)

        cos_y = np.cos(sim_yaw)
        sin_y = np.sin(sim_yaw)
        dx_world = cos_y * action_pred[0] - sin_y * action_pred[1]
        dy_world = sin_y * action_pred[0] + cos_y * action_pred[1]
        sim_pos = sim_pos + np.array([dx_world, dy_world], dtype=np.float32)

        true_dist = float(np.linalg.norm(sim_pos - goal_pos))
        label_stop = int(true_dist <= SUCCESS_RADIUS_M)

        rows.append(
            {
                "episode_id": traj_dir.name,
                "step": step,
                "dist_pred": dist_pred,
                "wp_norm": wp_norm,
                "dist_mean": float(x[2]),
                "wp_mean": float(x[3]),
                "dist_trend": float(x[4]),
                "wp_trend": float(x[5]),
                "true_dist_m": true_dist,
                "label_stop": label_stop,
                "x": x,
            }
        )

    return rows


def fit_logistic(X: np.ndarray, y: np.ndarray, lr: float = 0.1, epochs: int = 2000, l2: float = 1e-3):
    mu = X.mean(axis=0)
    sigma = X.std(axis=0) + 1e-6
    Xn = (X - mu) / sigma

    Xb = np.concatenate([np.ones((len(Xn), 1), dtype=np.float32), Xn], axis=1)
    w = np.zeros(Xb.shape[1], dtype=np.float32)

    pos = max(1.0, float(y.sum()))
    neg = max(1.0, float(len(y) - y.sum()))
    pos_weight = neg / pos
    weights = np.where(y > 0.5, pos_weight, 1.0).astype(np.float32)

    for _ in range(epochs):
        z = Xb @ w
        p = 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))
        grad = (Xb.T @ ((p - y) * weights)) / len(y)
        grad[1:] += l2 * w[1:]
        w -= lr * grad.astype(np.float32)

    return w, mu, sigma


def predict_prob(x: np.ndarray, w: np.ndarray, mu: np.ndarray, sigma: np.ndarray) -> float:
    xn = (x - mu) / sigma
    xb = np.concatenate([np.ones(1, dtype=np.float32), xn.astype(np.float32)])
    z = float(xb @ w)
    return float(1.0 / (1.0 + np.exp(-np.clip(z, -30, 30))))


def rollout_learned(
    evaluator: GNMEvaluator,
    traj_dir: Path,
    w: np.ndarray,
    mu: np.ndarray,
    sigma: np.ndarray,
    prob_threshold: float,
    stable_k: int,
    window: int,
) -> dict:
    data, positions_gt, yaws_gt, goal_idx, preds = precompute_predictions(evaluator, traj_dir, -1)

    goal_pos = tuple(positions_gt[goal_idx].tolist())
    sim_pos = np.asarray(positions_gt[0], dtype=np.float32)
    sim_yaw = float(yaws_gt[0])
    actual_path = [tuple(sim_pos.tolist())]

    dist_hist: list[float] = []
    wp_hist: list[float] = []
    probs: list[float] = []
    stable_count = 0
    stop_fired = False
    stop_step = ""

    for item in preds:
        step = int(item["step"])
        dist_pred = float(item["dist_pred"])
        action_pred = np.asarray(item["action_pred"], dtype=np.float32)
        wp_norm = float(item["wp_norm"])

        dist_hist.append(dist_pred)
        wp_hist.append(wp_norm)

        x = _features(dist_hist, wp_hist, window=window)
        p_stop = predict_prob(x, w, mu, sigma)
        probs.append(p_stop)

        cos_y = np.cos(sim_yaw)
        sin_y = np.sin(sim_yaw)
        dx_world = cos_y * action_pred[0] - sin_y * action_pred[1]
        dy_world = sin_y * action_pred[0] + cos_y * action_pred[1]
        sim_pos = sim_pos + np.array([dx_world, dy_world], dtype=np.float32)
        actual_path.append(tuple(sim_pos.tolist()))

        stable_count = stable_count + 1 if p_stop >= prob_threshold else 0
        if stable_count >= stable_k:
            stop_fired = True
            stop_step = step
            break

    ne = nav_error(actual_path, goal_pos)
    return {
        "episode_id": traj_dir.name,
        "stop_fired": stop_fired,
        "stop_step": stop_step,
        "n_steps": len(actual_path),
        "final_dist_m": ne,
        "success": success(ne, SUCCESS_RADIUS_M),
        "oracle_success": oracle_success(actual_path, goal_pos, SUCCESS_RADIUS_M),
        "path_length_m": path_length(actual_path),
        "p_stop_mean": float(np.mean(probs)) if probs else float("nan"),
        "p_stop_max": float(np.max(probs)) if probs else float("nan"),
    }


def summarise(rows: list[dict]) -> dict:
    n = len(rows)
    fired = [r for r in rows if r["stop_fired"]]
    return {
        "episodes": n,
        "SR_percent": 100.0 * sum(bool(r["success"]) for r in rows) / n,
        "OSR_percent": 100.0 * sum(bool(r["oracle_success"]) for r in rows) / n,
        "NE_m": sum(float(r["final_dist_m"]) for r in rows) / n,
        "TL_m": sum(float(r["path_length_m"]) for r in rows) / n,
        "stop_fired": len(fired),
        "mean_stop_step": (
            sum(float(r["stop_step"]) for r in fired) / len(fired)
            if fired
            else float("nan")
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ckpt", required=True)
    parser.add_argument("--cfg", default="configs/gnm/gnm_base.yaml")
    parser.add_argument("--data-root", default="datasets/vlntube")
    parser.add_argument("--split", default="val", help="Legacy mode: train and evaluate on the same split.")
    parser.add_argument("--train-split", default=None)
    parser.add_argument("--eval-split", default=None)
    parser.add_argument("--max-train-trajectories", type=int, default=0)
    parser.add_argument("--max-eval-trajectories", type=int, default=0)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--prob-threshold", type=float, default=0.5)
    parser.add_argument("--stable-k", type=int, default=3)
    parser.add_argument("--window", type=int, default=3)
    parser.add_argument("--out-dir", default="results/bo_reviewer_packet/learned_stop_head")
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

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    device = torch.device(args.device if torch.cuda.is_available() else "cpu")
    model, cfg = load_checkpoint_and_config(ckpt_path, cfg_path, device)

    evaluator = GNMEvaluator(
        model=model,
        action_std=tuple(cfg["data"]["action_std"]),
        context_size=cfg["model"]["context_size"],
        image_size=tuple(cfg["data"]["image_size"]),
        stop_threshold=0.15,
        max_steps=cfg.get("evaluation", {}).get("max_steps", 500),
        device=str(device),
        track="A",
    )

    train_split = args.train_split or args.split
    eval_split = args.eval_split or args.split

    train_dir = data_root / train_split
    eval_dir = data_root / eval_split

    train_traj_dirs = sorted(d for d in train_dir.iterdir() if d.is_dir())
    eval_traj_dirs = sorted(d for d in eval_dir.iterdir() if d.is_dir())

    if args.max_train_trajectories > 0:
        train_traj_dirs = train_traj_dirs[: args.max_train_trajectories]
    if args.max_eval_trajectories > 0:
        eval_traj_dirs = eval_traj_dirs[: args.max_eval_trajectories]

    trace_rows: list[dict] = []
    for traj_dir in train_traj_dirs:
        trace_rows.extend(build_trace_rows(evaluator, traj_dir, window=args.window))

    X = np.stack([r["x"] for r in trace_rows], axis=0)
    y = np.asarray([r["label_stop"] for r in trace_rows], dtype=np.float32)

    w, mu, sigma = fit_logistic(X, y)

    rollout_rows = [
        rollout_learned(
            evaluator,
            traj_dir,
            w,
            mu,
            sigma,
            args.prob_threshold,
            args.stable_k,
            args.window,
        )
        for traj_dir in eval_traj_dirs
    ]

    summary = summarise(rollout_rows)

    summary_csv = out_dir / "19_learned_stop_head.csv"
    details_csv = out_dir / "19_learned_stop_head_details.csv"
    trace_csv = out_dir / "19_learned_stop_head_traces.csv"
    coef_json = out_dir / "19_stop_head_coefficients.json"
    md_path = out_dir / "19_learned_stop_head.md"

    with summary_csv.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["policy", "episodes", "SR_percent", "OSR_percent", "NE_m", "TL_m", "stop_fired", "mean_stop_step"])
        mean_stop = "" if math.isnan(summary["mean_stop_step"]) else f"{summary['mean_stop_step']:.1f}"
        writer.writerow([
            "learned_logistic_stop_head",
            summary["episodes"],
            f"{summary['SR_percent']:.1f}",
            f"{summary['OSR_percent']:.1f}",
            f"{summary['NE_m']:.2f}",
            f"{summary['TL_m']:.2f}",
            summary["stop_fired"],
            mean_stop,
        ])

    with details_csv.open("w", newline="") as f:
        fieldnames = ["episode_id", "stop_fired", "stop_step", "n_steps", "final_dist_m", "success", "oracle_success", "path_length_m", "p_stop_mean", "p_stop_max"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rollout_rows:
            out = dict(r)
            for key in ["final_dist_m", "path_length_m", "p_stop_mean", "p_stop_max"]:
                out[key] = f"{float(out[key]):.4f}"
            writer.writerow(out)

    with trace_csv.open("w", newline="") as f:
        fieldnames = ["episode_id", "step", "dist_pred", "wp_norm", "dist_mean", "wp_mean", "dist_trend", "wp_trend", "true_dist_m", "label_stop"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in trace_rows:
            writer.writerow({k: r[k] for k in fieldnames})

    coef = {
        "feature_names": ["bias", "dist_pred", "wp_norm", "dist_mean", "wp_mean", "dist_trend", "wp_trend"],
        "weights": [float(v) for v in w.tolist()],
        "mean": [float(v) for v in mu.tolist()],
        "std": [float(v) for v in sigma.tolist()],
        "prob_threshold": args.prob_threshold,
        "stable_k": args.stable_k,
        "window": args.window,
        "train_split": train_split,
        "eval_split": eval_split,
        "train_episodes": len(train_traj_dirs),
        "eval_episodes": len(eval_traj_dirs),
        "training_samples": int(len(y)),
        "positive_stop_labels": int(y.sum()),
    }
    coef_json.write_text(json.dumps(coef, indent=2))

    md = [
        "# Learned Stop Head — Track A Train/Eval Protocol",
        "",
        "This experiment trains a lightweight logistic stop head on training trajectories and evaluates it on held-out validation trajectories.",
        "",
        "Stop decisions use only runtime signals: `dist_pred`, waypoint norm, rolling means, and short-term trends.",
        "Ground truth geometry is used only to create training labels and compute final metrics.",
        "",
        "## Result",
        "",
        "| Policy | Episodes | SR | OSR | NE (m) | TL (m) | Stop fired | Mean stop step |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        f"| learned_logistic_stop_head | {summary['episodes']} | {summary['SR_percent']:.1f}% | {summary['OSR_percent']:.1f}% | {summary['NE_m']:.2f} | {summary['TL_m']:.2f} | {summary['stop_fired']} | {mean_stop or 'n/a'} |",
        "",
        "## Train/evaluation protocol",
        "",
        f"- Train split: {train_split}",
        f"- Eval split: {eval_split}",
        f"- Train episodes: {len(train_traj_dirs)}",
        f"- Eval episodes: {len(eval_traj_dirs)}",
        f"- Training samples: {int(len(y))}",
        f"- Positive stop labels: {int(y.sum())}",
        "- Label definition: simulated robot is within 3.0m of the goal.",
        "",
        "## Interpretation",
        "",
        "This is the first learned/calibrated stop-policy baseline. It tests whether temporal runtime evidence can improve over fixed scalar thresholding.",
        "",
        "If it improves beyond 26.7% SR, it is evidence that learned stopping is a promising contribution. If it does not, the next step is richer stop supervision or a neural temporal head.",
        "",
    ]
    md_path.write_text("\n".join(md))

    print(summary_csv)
    print(details_csv)
    print(trace_csv)
    print(coef_json)
    print(md_path)


if __name__ == "__main__":
    main()
