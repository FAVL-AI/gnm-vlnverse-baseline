#!/usr/bin/env python3
"""scripts/gnm/09_finetune_progressive.py
Step 9: Progressive fine-tuning — staged encoder unfreezing with discriminative LR.

What progressive fine-tuning does
───────────────────────────────────
Standard fine-tuning unfreezes the full model and applies one learning rate.
Progressive fine-tuning avoids catastrophic forgetting of pretrained
representations by thawing the model in stages:

  Stage 1 — heads only (encoder frozen):
    Only dist_predictor and action_predictor are updated.
    Learns the VLNVerse action distribution without touching the encoder.
    3–5 epochs.

  Stage 2 — top encoder layers + heads:
    Unfreeze the last N feature blocks of the encoder.
    Encoder LR = base_lr × 0.1, heads LR = base_lr.
    3–5 epochs.

  Stage 3 — full model (discriminative LR):
    Entire model, but early encoder layers get 100× lower LR.
    Allows full adaptation while preserving low-level features.
    Until convergence.

Why discriminative LR?
  Early conv layers (edges, textures) transfer well and change little.
  Later layers (scene semantics) need more domain adaptation.
  Using the same LR for all layers either wastes early layer capacity
  or destroys pretrained features.

Use this script when
  - You have a checkpoint from Track A training (04_train_gnm.py)
  - You want to specialise it to a specific scene or instruction type
  - Or you want to transfer a checkpoint to a new domain (hospital→warehouse)

Usage
─────
  python scripts/gnm/09_finetune_progressive.py \
      --ckpt checkpoints/gnm_sota/best.pt

  python scripts/gnm/09_finetune_progressive.py \
      --ckpt checkpoints/gnm_sota/best.pt \
      --stage 1                              # heads only
      --stage-epochs 3,3,10                  # epochs per stage
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import torch
import torch.nn as nn
from omegaconf import OmegaConf

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from gnm_vlnverse.data.dataset import GNMDataset, collate_gnm
from gnm_vlnverse.models.gnm import build_gnm
from gnm_vlnverse.training.trainer import GNMTrainer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("gnm.finetune")


def _set_encoder_requires_grad(model: nn.Module, requires_grad: bool) -> None:
    for name in ("obs_encoder", "goal_encoder"):
        enc = getattr(model, name, None)
        if enc is not None:
            for p in enc.parameters():
                p.requires_grad_(requires_grad)


def _unfreeze_top_encoder_blocks(model: nn.Module, n_blocks: int) -> None:
    """Unfreeze the last n_blocks feature blocks of both encoders."""
    for name in ("obs_encoder", "goal_encoder"):
        enc = getattr(model, name, None)
        if enc is None:
            continue
        # features is a Sequential; unfreeze from the end
        features = enc.features
        n = len(features)
        for i, block in enumerate(features):
            freeze = i < (n - n_blocks)
            for p in block.parameters():
                p.requires_grad_(not freeze)
        # Always unfreeze the projection head
        for p in enc.project.parameters():
            p.requires_grad_(True)


def count_trainable(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


def make_loaders(cfg: dict, data_root: Path, bs: int):
    kw = dict(
        context_size = cfg["model"]["context_size"],
        max_goal_dist= cfg["data"]["max_goal_dist"],
        image_size   = tuple(cfg["data"]["image_size"]),
        action_std   = cfg["data"]["action_std"],
    )
    train_ds = GNMDataset(data_root=data_root, augment=True,  split="train", **kw)
    val_ds   = GNMDataset(data_root=data_root, augment=False, split="val",   **kw)
    train_loader = torch.utils.data.DataLoader(
        train_ds, batch_size=bs, shuffle=True, num_workers=4,
        collate_fn=collate_gnm, drop_last=True,
    )
    val_loader = torch.utils.data.DataLoader(
        val_ds, batch_size=bs * 2, shuffle=False, num_workers=4,
        collate_fn=collate_gnm,
    )
    return train_loader, val_loader


def run_stage(
    model: nn.Module,
    cfg: dict,
    data_root: Path,
    output_dir: Path,
    stage: int,
    epochs: int,
    base_lr: float,
    wandb_run=None,
) -> None:
    stage_cfg = dict(cfg["training"])
    stage_cfg["epochs"]       = epochs
    stage_cfg["patience"]     = epochs + 1   # no early stopping within a stage
    stage_cfg["warmup_frac"]  = 0.1
    stage_cfg["ema_decay"]    = 0.0           # no EMA during progressive stages

    if stage == 1:
        # Heads only
        _set_encoder_requires_grad(model, False)
        stage_cfg["lr"]              = base_lr
        stage_cfg["encoder_lr_scale"] = 0.0
        logger.info(f"Stage 1: heads only  trainable={count_trainable(model):,}")

    elif stage == 2:
        # Top 4 encoder blocks + heads
        _unfreeze_top_encoder_blocks(model, n_blocks=4)
        stage_cfg["lr"]              = base_lr
        stage_cfg["encoder_lr_scale"] = 0.1
        logger.info(f"Stage 2: top-4 blocks + heads  trainable={count_trainable(model):,}")

    else:
        # Stage 3: full model
        _set_encoder_requires_grad(model, True)
        stage_cfg["lr"]              = base_lr * 0.5   # gentler global LR
        stage_cfg["encoder_lr_scale"] = 0.01           # 100× lower for early encoder
        logger.info(f"Stage 3: full model (discriminative)  trainable={count_trainable(model):,}")

    bs = min(stage_cfg.get("batch_size", 128), 64)
    train_loader, val_loader = make_loaders(cfg, data_root, bs)

    trainer = GNMTrainer(
        model        = model,
        train_loader = train_loader,
        val_loader   = val_loader,
        cfg          = stage_cfg,
        output_dir   = output_dir / f"stage{stage}",
        wandb_run    = wandb_run,
        full_cfg     = cfg,
    )
    trainer.fit()
    logger.info(f"Stage {stage} done.  Best val loss: {trainer.best_val_loss:.6f}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--ckpt",          required=True)
    parser.add_argument("--cfg",           default="configs/gnm/gnm_sota.yaml")
    parser.add_argument("--stage",         type=int, default=0,
                        help="Run only this stage (1|2|3). Default 0 = all stages.")
    parser.add_argument("--stage-epochs",  default="5,5,20",
                        help="Comma-separated epochs for stages 1,2,3")
    parser.add_argument("--base-lr",       type=float, default=0.0,
                        help="Override base LR (default: use config value)")
    parser.add_argument("--output-dir",    default=None)
    parser.add_argument("--data-root",     default=None)
    parser.add_argument("--device",        default="cuda")
    args = parser.parse_args()

    ckpt_path = REPO_ROOT / args.ckpt
    device    = torch.device(args.device if torch.cuda.is_available() else "cpu")

    ckpt    = torch.load(ckpt_path, map_location=device)
    embedded = ckpt.get("cfg", {})
    cfg = embedded if (isinstance(embedded, dict) and "model" in embedded) else \
          OmegaConf.to_container(OmegaConf.load(REPO_ROOT / args.cfg), resolve=True)

    model = build_gnm(cfg["model"])
    # Prefer EMA weights as the starting point — they're the best val weights
    model.load_state_dict(ckpt.get("ema_state") or ckpt["model_state"])
    model.to(device)

    data_root_str = args.data_root or cfg["data"]["data_root"]
    data_root = Path(data_root_str)
    if not data_root.is_absolute():
        data_root = REPO_ROOT / data_root

    output_dir = Path(args.output_dir) if args.output_dir else \
                 REPO_ROOT / cfg["checkpoint"]["output_dir"].replace("gnm_sota", "gnm_progressive")

    base_lr    = args.base_lr or cfg["training"]["lr"]
    stage_eps  = [int(x) for x in args.stage_epochs.split(",")]
    stages     = [1, 2, 3] if args.stage == 0 else [args.stage]

    wandb_run = None
    try:
        import wandb
        wcfg = cfg.get("wandb", {})
        wandb_run = wandb.init(
            project = wcfg.get("project", "fleetsafe-gnm-vlnverse"),
            entity  = wcfg.get("entity") or None,
            name    = wcfg.get("name", "progressive_finetune"),
            tags    = wcfg.get("tags", []) + ["progressive_finetune"],
            config  = cfg,
            resume  = "allow",
        )
    except Exception:
        pass

    logger.info(f"Progressive fine-tuning from {ckpt_path}")
    logger.info(f"Stages: {stages}  epochs: {stage_eps}  base_lr: {base_lr:.2e}")

    for stage in stages:
        ep_idx = stage - 1
        epochs = stage_eps[ep_idx] if ep_idx < len(stage_eps) else 5
        run_stage(model, cfg, data_root, output_dir,
                  stage=stage, epochs=epochs, base_lr=base_lr, wandb_run=wandb_run)

    # Save final checkpoint with all stages completed
    final_path = output_dir / "progressive_final.pt"
    torch.save({
        "model_state": model.state_dict(),
        "cfg":         cfg,
        "source_ckpt": str(ckpt_path),
        "stages_run":  stages,
    }, final_path)
    logger.info(f"Final checkpoint: {final_path}")

    if wandb_run:
        wandb_run.finish()


if __name__ == "__main__":
    main()
