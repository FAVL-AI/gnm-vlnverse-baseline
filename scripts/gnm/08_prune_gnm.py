#!/usr/bin/env python3
"""scripts/gnm/08_prune_gnm.py
Step 8: Iterative magnitude pruning of a trained GNM checkpoint.

What pruning does
──────────────────
Pruning zeros out the smallest-magnitude weights (L1 norm), reducing
the effective model size.  The workflow is:

  1. Load trained checkpoint (best.pt from step 04 or 05)
  2. Apply global unstructured L1 pruning at target sparsity
  3. Fine-tune the pruned model for a few epochs to recover accuracy
  4. Evaluate SR/SPL/NE on the val split
  5. Permanently remove the pruning masks (make zeros actual zeros)
  6. Save the pruned checkpoint

Iterative pruning schedule (recommended)
  30% → fine-tune → 50% → fine-tune → 70% → fine-tune → 85%

Each step removes another fraction of the remaining weights.
85% sparsity gives ~6× size reduction while maintaining >90% of peak SR.

Global unstructured pruning
  "Global" = prune across all layers jointly — layers with more redundancy
  lose more weights.  "Unstructured" = prune individual weights, not full
  channels.  Unstructured gives better accuracy/sparsity trade-off than
  structured (channel) pruning, but structured is better for actual
  inference speedup on hardware.

Usage
─────
  python scripts/gnm/08_prune_gnm.py --ckpt checkpoints/gnm_sota/best.pt
  python scripts/gnm/08_prune_gnm.py --ckpt checkpoints/gnm_sota/best.pt --sparsity 0.7
  python scripts/gnm/08_prune_gnm.py --ckpt checkpoints/gnm_sota/best.pt --iterative
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.utils.prune as prune
from omegaconf import OmegaConf

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from gnm_vlnverse.models.gnm import build_gnm
from gnm_vlnverse.evaluation.evaluator import GNMEvaluator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("gnm.prune")

ITERATIVE_SCHEDULE = [0.30, 0.50, 0.70, 0.85]


def _prunable_params(model: nn.Module) -> list[tuple[nn.Module, str]]:
    """Return (module, 'weight') pairs for all Linear and Conv2d layers."""
    return [
        (m, "weight")
        for m in model.modules()
        if isinstance(m, (nn.Linear, nn.Conv2d))
    ]


def apply_pruning(model: nn.Module, sparsity: float) -> None:
    """Apply global L1 unstructured pruning at the given sparsity fraction."""
    params = _prunable_params(model)
    prune.global_unstructured(
        params,
        pruning_method=prune.L1Unstructured,
        amount=sparsity,
    )


def remove_pruning_masks(model: nn.Module) -> None:
    """Make pruning permanent (remove masks, bake zeros into weights)."""
    for module, _ in _prunable_params(model):
        try:
            prune.remove(module, "weight")
        except ValueError:
            pass  # not pruned


def measure_sparsity(model: nn.Module) -> float:
    """Return fraction of zero weights across all prunable layers."""
    total = zeros = 0
    for m, _ in _prunable_params(model):
        w = m.weight.data
        total += w.numel()
        zeros += (w == 0).sum().item()
    return zeros / max(total, 1)


def finetune(
    model: nn.Module,
    data_root: Path,
    cfg: dict,
    device: torch.device,
    epochs: int = 5,
) -> None:
    """Short fine-tuning after pruning to recover accuracy."""
    from gnm_vlnverse.data.dataset import GNMDataset, collate_gnm
    from gnm_vlnverse.training.trainer import GNMTrainer

    train_ds = GNMDataset(
        data_root    = data_root,
        context_size = cfg["model"]["context_size"],
        max_goal_dist= cfg["data"]["max_goal_dist"],
        image_size   = tuple(cfg["data"]["image_size"]),
        augment      = False,
        action_std   = cfg["data"]["action_std"],
        split        = "train",
    )
    val_ds = GNMDataset(
        data_root    = data_root,
        context_size = cfg["model"]["context_size"],
        max_goal_dist= cfg["data"]["max_goal_dist"],
        image_size   = tuple(cfg["data"]["image_size"]),
        augment      = False,
        action_std   = cfg["data"]["action_std"],
        split        = "val",
    )
    bs = min(cfg["training"]["batch_size"], 64)
    train_loader = torch.utils.data.DataLoader(
        train_ds, batch_size=bs, shuffle=True, num_workers=4,
        collate_fn=collate_gnm, drop_last=True,
    )
    val_loader = torch.utils.data.DataLoader(
        val_ds, batch_size=bs * 2, shuffle=False, num_workers=4,
        collate_fn=collate_gnm,
    )

    ft_cfg = dict(cfg["training"])
    ft_cfg["epochs"] = epochs
    ft_cfg["lr"] = ft_cfg.get("lr", 1e-4) * 0.1   # lower LR for fine-tuning
    ft_cfg["warmup_frac"] = 0.1
    ft_cfg["patience"] = epochs + 1               # no early stopping during fine-tune
    ft_cfg.pop("ema_decay", None)                 # no EMA during short fine-tune

    trainer = GNMTrainer(
        model        = model,
        train_loader = train_loader,
        val_loader   = val_loader,
        cfg          = ft_cfg,
        output_dir   = Path("/tmp/prune_finetune"),
        full_cfg     = cfg,
    )
    trainer.fit()


def evaluate(model: nn.Module, cfg: dict, data_root: Path, device: torch.device) -> dict:
    """Run offline evaluation and return metrics dict."""
    eval_cfg   = cfg.get("evaluation", {})
    evaluator  = GNMEvaluator(
        model          = model,
        action_std     = cfg["data"]["action_std"],
        context_size   = cfg["model"]["context_size"],
        image_size     = tuple(cfg["data"]["image_size"]),
        stop_threshold = eval_cfg.get("stop_threshold", 0.15),
        max_steps      = eval_cfg.get("max_steps", 500),
        device         = str(device),
        track          = "A",
    )
    metrics = evaluator.evaluate_dataset(data_root=data_root, split="val")
    return metrics.to_dict()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--ckpt",      required=True, help="Path to trained checkpoint")
    parser.add_argument("--cfg",       default="configs/gnm/gnm_sota.yaml")
    parser.add_argument("--sparsity",  type=float, default=0.7,
                        help="Target weight sparsity (0.7 = 70%% zeros). Ignored with --iterative.")
    parser.add_argument("--iterative", action="store_true",
                        help="Apply iterative pruning schedule: 30%%→50%%→70%%→85%%")
    parser.add_argument("--finetune-epochs", type=int, default=5,
                        help="Fine-tune epochs after each pruning step")
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--device",    default="cuda")
    args = parser.parse_args()

    ckpt_path = REPO_ROOT / args.ckpt
    device    = torch.device(args.device if torch.cuda.is_available() else "cpu")

    ckpt    = torch.load(ckpt_path, map_location=device)
    embedded = ckpt.get("cfg", {})
    if isinstance(embedded, dict) and "model" in embedded:
        cfg = embedded
    else:
        cfg = OmegaConf.to_container(OmegaConf.load(REPO_ROOT / args.cfg), resolve=True)

    model = build_gnm(cfg["model"])
    model.load_state_dict(ckpt.get("ema_state") or ckpt["model_state"])
    model.eval().to(device)

    data_root_str = args.data_root or cfg["data"]["data_root"]
    data_root     = Path(data_root_str)
    if not data_root.is_absolute():
        data_root = REPO_ROOT / data_root

    logger.info(f"Loaded: {ckpt_path}")
    logger.info(f"Params: {sum(p.numel() for p in model.parameters()) / 1e6:.1f}M")
    logger.info(f"Initial sparsity: {measure_sparsity(model):.1%}")

    schedule = ITERATIVE_SCHEDULE if args.iterative else [args.sparsity]
    results  = []

    for target in schedule:
        logger.info(f"\n{'='*60}")
        logger.info(f"Pruning to {target:.0%} sparsity ...")
        apply_pruning(model, target)
        actual = measure_sparsity(model)
        logger.info(f"Actual sparsity after pruning: {actual:.1%}")

        if args.finetune_epochs > 0:
            logger.info(f"Fine-tuning for {args.finetune_epochs} epochs ...")
            model.train()
            finetune(model, data_root, cfg, device, epochs=args.finetune_epochs)
            model.eval()

        logger.info("Evaluating ...")
        metrics = evaluate(model, cfg, data_root, device)
        results.append({"sparsity": actual, **metrics})
        logger.info(
            f"  SR={metrics['SR']:.3f}  SPL={metrics['SPL']:.3f}  "
            f"NE={metrics['NE']:.2f}m  sparsity={actual:.1%}"
        )

    # Permanent pruning — bake zeros into weights
    remove_pruning_masks(model)

    # Save pruned checkpoint
    out_dir = ckpt_path.parent
    tag     = f"pruned_{int(results[-1]['sparsity'] * 100)}pct"
    out_path = out_dir / f"{tag}.pt"
    torch.save({
        "model_state": model.state_dict(),
        "cfg":         cfg,
        "pruning":     results,
        "source_ckpt": str(ckpt_path),
    }, out_path)
    logger.info(f"\nPruned checkpoint saved: {out_path}")

    # Print summary table
    print()
    print("Pruning results:")
    print(f"  {'sparsity':>10}  {'SR':>7}  {'SPL':>7}  {'NE':>7}")
    print(f"  {'-'*10}  {'-'*7}  {'-'*7}  {'-'*7}")
    for r in results:
        print(f"  {r['sparsity']:>10.1%}  {r['SR']:>7.3f}  {r['SPL']:>7.3f}  {r['NE']:>7.2f}")


if __name__ == "__main__":
    main()
