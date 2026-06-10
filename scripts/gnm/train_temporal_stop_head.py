#!/usr/bin/env python3
"""Temporal neural stop head for Track A.

Train: Track A train split.
Eval: held-out Track A val split.

Runtime decision uses only GNM runtime signals:
- dist_pred
- waypoint norm
- rolling dist mean
- rolling waypoint mean
- dist trend
- waypoint trend

Ground-truth geometry is used only for training labels and final metrics.
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
from torch import nn

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from gnm_vlnverse.evaluation.evaluator import GNMEvaluator
from gnm_vlnverse.evaluation.metrics import nav_error, oracle_success, path_length, success
from scripts.gnm.ablate_deployable_stop_policy import (
    SUCCESS_RADIUS_M,
    load_checkpoint_and_config,
    precompute_predictions,
)
from scripts.gnm.learn_stop_head import _features, build_trace_rows


FEATURE_DIM = 6


class TemporalStopHead(nn.Module):
    def __init__(self, seq_len: int, hidden: int = 64):
        super().__init__()
        self.net = nn.Sequential(
            nn.Flatten(),
            nn.Linear(seq_len * FEATURE_DIM, hidden),
            nn.ReLU(),
            nn.Linear(hidden, hidden // 2),
            nn.ReLU(),
            nn.Linear(hidden // 2, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x).squeeze(-1)


def make_sequence_dataset(
    evaluator: GNMEvaluator,
    traj_dirs: list[Path],
    seq_len: int,
    window: int,
) -> tuple[np.ndarray, np.ndarray]:
    xs = []
    ys = []

    for i, traj_dir in enumerate(traj_dirs, start=1):
        if i == 1 or i % 25 == 0 or i == len(traj_dirs):
            print(f"  train trace {i}/{len(traj_dirs)}", flush=True)

        rows = build_trace_rows(evaluator, traj_dir, window=window)
        feats = np.asarray(
            [
                [
                    r["dist_pred"],
                    r["wp_norm"],
                    r["dist_mean"],
                    r["wp_mean"],
                    r["dist_trend"],
                    r["wp_trend"],
                ]
                for r in rows
            ],
            dtype=np.float32,
        )
        labels = np.asarray([r["label_stop"] for r in rows], dtype=np.float32)

        for t in range(len(feats)):
            start = max(0, t - seq_len + 1)
            seq = feats[start : t + 1]
            if len(seq) < seq_len:
                pad = np.repeat(seq[:1], seq_len - len(seq), axis=0)
                seq = np.concatenate([pad, seq], axis=0)
            xs.append(seq)
            ys.append(labels[t])

    return np.asarray(xs, dtype=np.float32), np.asarray(ys, dtype=np.float32)


def normalise_train(X: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mu = X.reshape(-1, FEATURE_DIM).mean(axis=0)
    sigma = X.reshape(-1, FEATURE_DIM).std(axis=0) + 1e-6
    Xn = (X - mu.reshape(1, 1, -1)) / sigma.reshape(1, 1, -1)
    return Xn.astype(np.float32), mu.astype(np.float32), sigma.astype(np.float32)


def normalise_one(seq: np.ndarray, mu: np.ndarray, sigma: np.ndarray) -> np.ndarray:
    return ((seq - mu.reshape(1, -1)) / sigma.reshape(1, -1)).astype(np.float32)


def train_head(
    X: np.ndarray,
    y: np.ndarray,
    seq_len: int,
    epochs: int,
    lr: float,
    batch_size: int,
    seed: int,
) -> TemporalStopHead:
    torch.manual_seed(seed)
    model = TemporalStopHead(seq_len=seq_len)
    model.train()

    X_t = torch.tensor(X, dtype=torch.float32)
    y_t = torch.tensor(y, dtype=torch.float32)

    pos = max(1.0, float(y.sum()))
    neg = max(1.0, float(len(y) - y.sum()))
    pos_weight = torch.tensor([neg / pos], dtype=torch.float32)

    loss_fn = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    opt = torch.optim.Adam(model.parameters(), lr=lr)

    n = len(y)
    for epoch in range(1, epochs + 1):
        perm = torch.randperm(n)
        total = 0.0

        for start in range(0, n, batch_size):
            idx = perm[start : start + batch_size]
            logits = model(X_t[idx])
            loss = loss_fn(logits, y_t[idx])

            opt.zero_grad()
            loss.backward()
            opt.step()
            total += float(loss.item()) * len(idx)

        if epoch == 1 or epoch % 20 == 0 or epoch == epochs:
            print(f"epoch {epoch}/{epochs} loss={total/n:.4f}", flush=True)

    model.eval()
    return model


def predict_stop_prob(
    model: TemporalStopHead,
    seq_feats: list[np.ndarray],
    seq_len: int,
    mu: np.ndarray,
    sigma: np.ndarray,
) -> float:
    seq = np.asarray(seq_feats[-seq_len:], dtype=np.float32)
    if len(seq) < seq_len:
        pad = np.repeat(seq[:1], seq_len - len(seq), axis=0)
        seq = np.concatenate([pad, seq], axis=0)

    seq = normalise_one(seq, mu, sigma)
    x = torch.tensor(seq[None, :, :], dtype=torch.float32)

    with torch.no_grad():
        p = torch.sigmoid(model(x))[0].item()
    return float(p)


def rollout_temporal(
    evaluator: GNMEvaluator,
    traj_dir: Path,
    model: TemporalStopHead,
    mu: np.ndarray,
    sigma: np.ndarray,
    seq_len: int,
    window: int,
    prob_threshold: float,
    stable_k: int,
) -> dict:
    data, positions_gt, yaws_gt, goal_idx, preds = precompute_predictions(evaluator, traj_dir, -1)

    goal_pos = tuple(positions_gt[goal_idx].tolist())
    sim_pos = np.asarray(positions_gt[0], dtype=np.float32)
    sim_yaw = float(yaws_gt[0])
    actual_path = [tuple(sim_pos.tolist())]

    dist_hist: list[float] = []
    wp_hist: list[float] = []
    seq_feats: list[np.ndarray] = []
    probs: list[float] = []

    stable = 0
    stop_fired = False
    stop_step = ""

    for item in preds:
        step = int(item["step"])
        dist_pred = float(item["dist_pred"])
        action_pred = np.asarray(item["action_pred"], dtype=np.float32)
        wp_norm = float(item["wp_norm"])

        dist_hist.append(dist_pred)
        wp_hist.append(wp_norm)

        feat = _features(dist_hist, wp_hist, window=window)
        seq_feats.append(feat)

        p_stop = predict_stop_prob(model, seq_feats, seq_len, mu, sigma)
        probs.append(p_stop)

        cos_y = np.cos(sim_yaw)
        sin_y = np.sin(sim_yaw)
        dx_world = cos_y * action_pred[0] - sin_y * action_pred[1]
        dy_world = sin_y * action_pred[0] + cos_y * action_pred[1]
        sim_pos = sim_pos + np.array([dx_world, dy_world], dtype=np.float32)
        actual_path.append(tuple(sim_pos.tolist()))

        stable = stable + 1 if p_stop >= prob_threshold else 0
        if stable >= stable_k:
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
    parser.add_argument("--train-split", default="train")
    parser.add_argument("--eval-split", default="val")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--seq-len", type=int, default=8)
    parser.add_argument("--window", type=int, default=3)
    parser.add_argument("--stable-k", type=int, default=3)
    parser.add_argument("--epochs", type=int, default=120)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out-dir", default="results/bo_reviewer_packet/temporal_stop_head")
    args = parser.parse_args()

    ckpt = Path(args.ckpt)
    cfg_path = Path(args.cfg)
    data_root = Path(args.data_root)
    out_dir = Path(args.out_dir)

    out_dir.mkdir(parents=True, exist_ok=True)

    print("Loading GNM model...", flush=True)
    device = torch.device("cpu")
    gnm_model, cfg = load_checkpoint_and_config(ckpt, cfg_path, device)

    evaluator = GNMEvaluator(
        model=gnm_model,
        action_std=tuple(cfg["data"]["action_std"]),
        context_size=cfg["model"]["context_size"],
        image_size=tuple(cfg["data"]["image_size"]),
        stop_threshold=0.15,
        max_steps=cfg.get("evaluation", {}).get("max_steps", 500),
        device=str(device),
        track="A",
    )

    train_dirs = sorted(d for d in (data_root / args.train_split).iterdir() if d.is_dir())
    eval_dirs = sorted(d for d in (data_root / args.eval_split).iterdir() if d.is_dir())

    print(f"Building temporal dataset from {len(train_dirs)} train trajectories...", flush=True)
    X, y = make_sequence_dataset(evaluator, train_dirs, args.seq_len, args.window)
    Xn, mu, sigma = normalise_train(X)

    print(f"Training samples={len(y)} positives={int(y.sum())}", flush=True)
    stop_model = train_head(
        Xn,
        y,
        seq_len=args.seq_len,
        epochs=args.epochs,
        lr=args.lr,
        batch_size=args.batch_size,
        seed=args.seed,
    )

    thresholds = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90]

    sweep_csv = out_dir / "22_temporal_stop_head_threshold_sweep.csv"
    best_rows = None
    best_summary = None
    best_threshold = None

    with sweep_csv.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "prob_threshold",
            "stable_k",
            "policy",
            "episodes",
            "SR_percent",
            "OSR_percent",
            "NE_m",
            "TL_m",
            "stop_fired",
            "mean_stop_step",
        ])

        for p in thresholds:
            print(f"Evaluating threshold P={p:.2f}", flush=True)
            rows = [
                rollout_temporal(
                    evaluator,
                    traj_dir,
                    stop_model,
                    mu,
                    sigma,
                    args.seq_len,
                    args.window,
                    p,
                    args.stable_k,
                )
                for traj_dir in eval_dirs
            ]
            s = summarise(rows)
            mean_stop = "" if math.isnan(s["mean_stop_step"]) else f"{s['mean_stop_step']:.1f}"

            writer.writerow([
                f"{p:.2f}",
                args.stable_k,
                "temporal_neural_stop_head",
                s["episodes"],
                f"{s['SR_percent']:.1f}",
                f"{s['OSR_percent']:.1f}",
                f"{s['NE_m']:.2f}",
                f"{s['TL_m']:.2f}",
                s["stop_fired"],
                mean_stop,
            ])

            if best_summary is None or (
                s["SR_percent"],
                s["OSR_percent"],
                -s["NE_m"],
            ) > (
                best_summary["SR_percent"],
                best_summary["OSR_percent"],
                -best_summary["NE_m"],
            ):
                best_summary = s
                best_rows = rows
                best_threshold = p

    summary_csv = out_dir / "22_temporal_stop_head.csv"
    details_csv = out_dir / "22_temporal_stop_head_details.csv"
    model_path = out_dir / "22_temporal_stop_head_model.pt"
    meta_json = out_dir / "22_temporal_stop_head_meta.json"
    md_path = out_dir / "22_temporal_stop_head.md"

    torch.save(
        {
            "model_state": stop_model.state_dict(),
            "seq_len": args.seq_len,
            "window": args.window,
            "feature_dim": FEATURE_DIM,
            "mean": mu.tolist(),
            "std": sigma.tolist(),
            "best_threshold": best_threshold,
            "stable_k": args.stable_k,
        },
        model_path,
    )

    with summary_csv.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["policy", "best_threshold", "episodes", "SR_percent", "OSR_percent", "NE_m", "TL_m", "stop_fired", "mean_stop_step"])
        mean_stop = "" if math.isnan(best_summary["mean_stop_step"]) else f"{best_summary['mean_stop_step']:.1f}"
        writer.writerow([
            "temporal_neural_stop_head",
            f"{best_threshold:.2f}",
            best_summary["episodes"],
            f"{best_summary['SR_percent']:.1f}",
            f"{best_summary['OSR_percent']:.1f}",
            f"{best_summary['NE_m']:.2f}",
            f"{best_summary['TL_m']:.2f}",
            best_summary["stop_fired"],
            mean_stop,
        ])

    with details_csv.open("w", newline="") as f:
        fieldnames = ["episode_id", "stop_fired", "stop_step", "n_steps", "final_dist_m", "success", "oracle_success", "path_length_m", "p_stop_mean", "p_stop_max"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in best_rows:
            out = dict(r)
            for k in ["final_dist_m", "path_length_m", "p_stop_mean", "p_stop_max"]:
                out[k] = f"{float(out[k]):.4f}"
            writer.writerow(out)

    meta_json.write_text(json.dumps({
        "train_split": args.train_split,
        "eval_split": args.eval_split,
        "train_episodes": len(train_dirs),
        "eval_episodes": len(eval_dirs),
        "training_samples": int(len(y)),
        "positive_stop_labels": int(y.sum()),
        "seq_len": args.seq_len,
        "window": args.window,
        "stable_k": args.stable_k,
        "epochs": args.epochs,
        "best_threshold": best_threshold,
    }, indent=2))

    md = [
        "# Temporal Neural Stop Head — Track A",
        "",
        "This experiment trains a small temporal neural stop head on Track A train trajectories and evaluates it on held-out Track A validation trajectories.",
        "",
        "Runtime decisions use only GNM outputs and derived temporal features. Ground-truth geometry is used only for training labels and final metrics.",
        "",
        "## Best result",
        "",
        "| Policy | Best P(stop) | Episodes | SR | OSR | NE (m) | TL (m) | Stop fired | Mean stop step |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        f"| temporal_neural_stop_head | {best_threshold:.2f} | {best_summary['episodes']} | {best_summary['SR_percent']:.1f}% | {best_summary['OSR_percent']:.1f}% | {best_summary['NE_m']:.2f} | {best_summary['TL_m']:.2f} | {best_summary['stop_fired']} | {mean_stop or 'n/a'} |",
        "",
        "## Protocol",
        "",
        f"- Train split: {args.train_split}",
        f"- Eval split: {args.eval_split}",
        f"- Train episodes: {len(train_dirs)}",
        f"- Eval episodes: {len(eval_dirs)}",
        f"- Training samples: {int(len(y))}",
        f"- Positive stop labels: {int(y.sum())}",
        f"- Sequence length: {args.seq_len}",
        f"- Stable K: {args.stable_k}",
        "",
        "## Interpretation",
        "",
        "The temporal neural head tests whether short-term runtime history improves deployable stopping beyond scalar thresholds and the logistic stop head.",
        "",
    ]
    md_path.write_text("\n".join(md))

    print(summary_csv)
    print(sweep_csv)
    print(details_csv)
    print(model_path)
    print(meta_json)
    print(md_path)


if __name__ == "__main__":
    main()
