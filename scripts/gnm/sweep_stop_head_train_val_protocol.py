#!/usr/bin/env python3
from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from gnm_vlnverse.evaluation.evaluator import GNMEvaluator
from scripts.gnm.ablate_deployable_stop_policy import load_checkpoint_and_config
from scripts.gnm.learn_stop_head import build_trace_rows, fit_logistic, rollout_learned, summarise

CKPT = Path("/home/favl/robotics/FleetSafe-VisualNav-Benchmark/checkpoints/gnm_base/best.pt")
CFG = Path("configs/gnm/gnm_base.yaml")
DATA_ROOT = Path("datasets/vlntube")
OUT = Path("results/bo_reviewer_packet/stop_head_train_val_protocol_sweep")
CSV_PATH = OUT / "21_stop_head_train_val_threshold_sweep.csv"

PROBS = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90]
STABLE_K = 3
WINDOW = 3


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    print("Loading model...", flush=True)
    device = torch.device("cpu")
    model, cfg = load_checkpoint_and_config(CKPT, CFG, device)

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

    train_dirs = sorted(d for d in (DATA_ROOT / "train").iterdir() if d.is_dir())
    val_dirs = sorted(d for d in (DATA_ROOT / "val").iterdir() if d.is_dir())

    print(f"Building train traces: {len(train_dirs)} trajectories", flush=True)
    trace_rows = []
    for i, traj_dir in enumerate(train_dirs, start=1):
        if i == 1 or i % 25 == 0 or i == len(train_dirs):
            print(f"  train trace {i}/{len(train_dirs)}", flush=True)
        trace_rows.extend(build_trace_rows(evaluator, traj_dir, window=WINDOW))

    X = np.stack([r["x"] for r in trace_rows], axis=0)
    y = np.asarray([r["label_stop"] for r in trace_rows], dtype=np.float32)

    print(f"Fitting logistic head: samples={len(y)}, positives={int(y.sum())}", flush=True)
    w, mu, sigma = fit_logistic(X, y)

    with CSV_PATH.open("w", newline="") as f:
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

        for p in PROBS:
            print(f"Evaluating P={p:.2f}", flush=True)
            rows = [
                rollout_learned(evaluator, d, w, mu, sigma, p, STABLE_K, WINDOW)
                for d in val_dirs
            ]
            s = summarise(rows)
            mean_stop = "" if np.isnan(s["mean_stop_step"]) else f"{s['mean_stop_step']:.1f}"
            writer.writerow([
                f"{p:.2f}",
                STABLE_K,
                "learned_logistic_stop_head_train_val",
                s["episodes"],
                f"{s['SR_percent']:.1f}",
                f"{s['OSR_percent']:.1f}",
                f"{s['NE_m']:.2f}",
                f"{s['TL_m']:.2f}",
                s["stop_fired"],
                mean_stop,
            ])

    print(CSV_PATH, flush=True)


if __name__ == "__main__":
    main()
