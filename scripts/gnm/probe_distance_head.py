#!/usr/bin/env python3
"""scripts/gnm/probe_distance_head.py
Diagnose distance-head collapse in a GNM checkpoint.

Loads N real samples from the val split, runs forward passes, and reports:
  dist_pred_mean   — healthy models: ~0.3-0.5 (varies with input)
  dist_pred_range  — healthy: [0.1, 0.9]; collapsed: tiny constant or negative
  dist_target_mean — ground truth, for reference
  pred_target_corr — Pearson r; healthy: >0.3; collapsed: near 0 or negative
  collapse_count   — samples where dist_pred < stop_threshold (triggers early stop)

Quick collapse test with random inputs (no dataset needed):
  python scripts/gnm/probe_distance_head.py --ckpt checkpoints/gnm_base/best.pt --random

Usage
─────
  python scripts/gnm/probe_distance_head.py --ckpt checkpoints/gnm_ablation_a3/best.pt
  python scripts/gnm/probe_distance_head.py --ckpt checkpoints/gnm_sota/best.pt --split val --n 128
  python scripts/gnm/probe_distance_head.py --ckpt checkpoints/gnm_base/best.pt --random --n 20
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from gnm_vlnverse.models.gnm import build_gnm


def probe_random(model: torch.nn.Module, n: int, stop_threshold: float) -> None:
    """Quick collapse check with random Gaussian inputs — no dataset needed."""
    dists: list[float] = []
    model.eval()
    with torch.no_grad():
        for seed in range(n):
            torch.manual_seed(seed)
            ctx = model.context_size if hasattr(model, "context_size") else 5
            obs  = torch.randn(1, ctx * 3, 96, 96)
            goal = torch.randn(1, 3, 96, 96)
            d = model(obs, goal)[0].squeeze().item()
            dists.append(d)

    arr = np.array(dists)
    collapse = int((arr < stop_threshold).sum())
    print(f"\n{'─'*55}")
    print(f" Distance head probe  (random inputs, n={n})")
    print(f"{'─'*55}")
    print(f"  dist_pred_mean    {arr.mean():.4f}")
    print(f"  dist_pred_std     {arr.std():.4f}")
    print(f"  dist_pred_range   [{arr.min():.4f}, {arr.max():.4f}]")
    print(f"  stop_threshold    {stop_threshold}")
    print(f"  collapse_count    {collapse}/{n}  ({100*collapse/n:.0f}%)")
    verdict = "HEALTHY" if collapse == 0 and arr.mean() > 0.2 else "COLLAPSED"
    print(f"  verdict           {verdict}")
    print(f"{'─'*55}\n")


def probe_real(
    model: torch.nn.Module,
    cfg: dict,
    data_root: Path,
    split: str,
    n: int,
    stop_threshold: float,
    device: torch.device,
) -> None:
    """Probe on real val samples — reports pred/target correlation."""
    from gnm_vlnverse.data.dataset import GNMDataset

    action_std = tuple(cfg["data"]["action_std"])
    image_size = tuple(cfg["data"]["image_size"])
    context_size = cfg["model"]["context_size"]

    ds = GNMDataset(
        data_root    = data_root,
        context_size = context_size,
        max_goal_dist= cfg["data"]["max_goal_dist"],
        image_size   = image_size,
        augment      = False,
        action_std   = action_std,
        split        = split,
    )

    indices = np.random.default_rng(0).choice(len(ds), size=min(n, len(ds)), replace=False)

    pred_dists:   list[float] = []
    target_dists: list[float] = []

    model.eval()
    with torch.no_grad():
        for i in indices:
            sample = ds[int(i)]
            obs  = sample["obs"].unsqueeze(0).to(device)
            goal = sample["goal"].unsqueeze(0).to(device)
            d_pred = model(obs, goal)[0].squeeze().item()
            d_tgt  = sample["dist"].item()
            pred_dists.append(d_pred)
            target_dists.append(d_tgt)

    pred  = np.array(pred_dists)
    tgt   = np.array(target_dists)
    corr  = float(np.corrcoef(pred, tgt)[0, 1]) if pred.std() > 1e-8 else 0.0
    collapse = int((pred < stop_threshold).sum())

    print(f"\n{'─'*55}")
    print(f" Distance head probe  (real {split} samples, n={len(pred)})")
    print(f"{'─'*55}")
    print(f"  dist_pred_mean    {pred.mean():.4f}")
    print(f"  dist_pred_std     {pred.std():.4f}")
    print(f"  dist_pred_range   [{pred.min():.4f}, {pred.max():.4f}]")
    print(f"  dist_target_mean  {tgt.mean():.4f}")
    print(f"  dist_target_range [{tgt.min():.4f}, {tgt.max():.4f}]")
    print(f"  pred_target_corr  {corr:+.4f}  (healthy: >0.3)")
    print(f"  stop_threshold    {stop_threshold}")
    print(f"  collapse_count    {collapse}/{len(pred)}  ({100*collapse/len(pred):.0f}%)")
    # Allow up to 5% collapse (borderline samples near threshold)
    healthy = (collapse / len(pred) < 0.05) and pred.mean() > 0.15 and corr > 0.2
    verdict = "HEALTHY" if healthy else "COLLAPSED"
    print(f"  verdict           {verdict}")
    print(f"{'─'*55}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ckpt",   required=True,  help="Path to checkpoint .pt")
    parser.add_argument("--split",  default="val",  help="Data split (val/train)")
    parser.add_argument("--n",      default=64, type=int, help="Number of samples")
    parser.add_argument("--random", action="store_true", help="Use random inputs (no dataset)")
    parser.add_argument("--data-root", default=None, help="Override data root from config")
    parser.add_argument("--stop-threshold", default=0.15, type=float)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()

    ckpt_path = Path(args.ckpt)
    if not ckpt_path.is_absolute():
        ckpt_path = REPO_ROOT / ckpt_path

    device = torch.device(args.device)
    ckpt = torch.load(ckpt_path, map_location=device)

    cfg = ckpt.get("cfg", {})
    if not isinstance(cfg, dict) or "model" not in cfg:
        print("ERROR: checkpoint has no embedded cfg — cannot auto-configure model")
        sys.exit(1)

    model = build_gnm(cfg["model"]).to(device)
    state = ckpt.get("ema_state") or ckpt["model_state"]
    model.load_state_dict(state)
    model.eval()

    gs   = ckpt.get("global_step", "?")
    vloss = ckpt.get("best_val_loss")
    vloss_str = f"{vloss:.4f}" if vloss is not None else "?"
    print(f"Checkpoint:   {ckpt_path.name}")
    print(f"global_step:  {gs}  (~epoch {gs//24 if isinstance(gs,int) else '?'}/200)")
    print(f"best_val_loss:{vloss_str}")
    print(f"weights:      {'EMA' if ckpt.get('ema_state') is not None else 'live'}")

    if args.random:
        probe_random(model, args.n, args.stop_threshold)
    else:
        data_root_str = args.data_root or cfg["data"]["data_root"]
        data_root = Path(data_root_str)
        if not data_root.is_absolute():
            data_root = REPO_ROOT / data_root
        probe_real(model, cfg, data_root, args.split, args.n,
                   args.stop_threshold, device)


if __name__ == "__main__":
    main()
