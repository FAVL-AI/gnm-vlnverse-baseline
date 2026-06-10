#!/usr/bin/env python3
"""scripts/gnm/05_train_lora.py
Step 5 of 7: Fine-tune GNM with LoRA for Track C.

What is LoRA? (explained for a 14-year-old)
────────────────────────────────────────────
Imagine GNM has 6 million weights that it learned over weeks.  We want it to
get even better at hospital navigation — but we don't want to forget everything
else it knows.

LoRA says: instead of changing the original weights, ADD a tiny correction on
top.  The correction is two small matrices A and B where A is (rank × input)
and B is (output × rank), and rank is a tiny number like 4 or 8.

A Linear layer normally has a weight matrix W of shape (out, in).  With LoRA:
  output = W·x  +  scale · B·A·x
             ↑         ↑
       original    LoRA correction
       (frozen)    (trainable)

Why does this work?
  The correction B·A has only rank×(in+out) parameters instead of in×out.
  If rank=8, in=512, out=512: 8×(512+512) = 8,192 params vs 262,144 original.
  That's 32× fewer trainable parameters!

Track C: LoRA fine-tuning
─────────────────────────
  1. Load pre-trained GNM checkpoint (from Track A training)
  2. Inject LoRA adapters into the encoder's Linear layers
  3. Freeze all original weights
  4. Train only the LoRA A/B matrices and prediction heads
  5. Save only the LoRA weights (small delta file, ~1 MB)

Usage
─────
    python scripts/gnm/05_train_lora.py
    python scripts/gnm/05_train_lora.py --base-ckpt checkpoints/gnm_base/best.pt
    python scripts/gnm/05_train_lora.py lora.rank=16 lora.alpha=32
    python scripts/gnm/05_train_lora.py lora.target=encoder_proj training.lr=3e-5
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import torch
from omegaconf import OmegaConf

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from gnm_vlnverse.data.dataset import GNMDataset, collate_gnm
from gnm_vlnverse.models.gnm import build_gnm
from gnm_vlnverse.models.lora import (
    count_lora_params,
    freeze_non_lora,
    inject_lora,
    lora_state_dict,
)
from gnm_vlnverse.training.trainer import GNMTrainer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("gnm.lora")

# ── LoRA target presets ────────────────────────────────────────────────────────
# Each preset is a list of regex patterns matching fully-qualified parameter names.
LORA_TARGETS = {
    "heads_only":     [r"dist_predictor\.\d+", r"action_predictor\.\d+"],
    "encoder_proj":   [r"encoder\.proj"],
    "full_encoder":   [r"encoder\.backbone\.*\.linear", r"encoder\.proj"],
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--cfg",
        default="configs/gnm/gnm_base.yaml",
        help="Base config YAML",
    )
    parser.add_argument(
        "--base-ckpt",
        default="checkpoints/gnm_base/best.pt",
        help="Pre-trained GNM checkpoint to fine-tune",
    )
    parser.add_argument(
        "--output-dir",
        default="checkpoints/gnm_lora",
        help="Where to save LoRA checkpoints",
    )
    parser.add_argument(
        "overrides",
        nargs="*",
        help="OmegaConf overrides: lora.rank=16  lora.alpha=32  training.lr=3e-5",
    )
    args = parser.parse_args()

    # ── Config ────────────────────────────────────────────────────────────────
    cfg_path = REPO_ROOT / args.cfg
    base_cfg = OmegaConf.load(cfg_path)
    cli_cfg  = OmegaConf.from_dotlist(args.overrides) if args.overrides else OmegaConf.create({})
    cfg      = OmegaConf.to_container(OmegaConf.merge(base_cfg, cli_cfg), resolve=True)

    # LoRA-specific config with defaults
    lora_cfg = cfg.get("lora", {})
    rank         = lora_cfg.get("rank", 8)
    alpha        = lora_cfg.get("alpha", 16.0)
    dropout      = lora_cfg.get("dropout", 0.05)
    target_name  = lora_cfg.get("target", "encoder_proj")
    freeze_base  = lora_cfg.get("freeze_base", True)

    logger.info(f"LoRA config: rank={rank}  alpha={alpha}  target={target_name}  freeze={freeze_base}")

    # ── Base model ────────────────────────────────────────────────────────────
    model = build_gnm(cfg["model"])

    ckpt_path = REPO_ROOT / args.base_ckpt
    if ckpt_path.exists():
        ckpt = torch.load(ckpt_path, map_location="cpu")
        model.load_state_dict(ckpt["model_state"])
        logger.info(f"Loaded base checkpoint: {ckpt_path}")
    else:
        logger.warning(
            f"Base checkpoint not found: {ckpt_path}\n"
            "  Training LoRA on randomly initialised weights — results will be poor.\n"
            "  Run 04_train_gnm.py first."
        )

    # ── Inject LoRA ───────────────────────────────────────────────────────────
    target_modules = LORA_TARGETS.get(target_name, LORA_TARGETS["encoder_proj"])
    inject_lora(model, target_modules=target_modules, rank=rank, alpha=alpha, dropout=dropout)

    if freeze_base:
        freeze_non_lora(model)

    param_info = count_lora_params(model)
    logger.info(
        f"LoRA injected:\n"
        f"  Total params:     {param_info['total']:,}\n"
        f"  Trainable params: {param_info['trainable']:,}\n"
        f"  LoRA params:      {param_info['lora_only']:,}\n"
        f"  LoRA fraction:    {param_info['pct']:.2f}%"
    )

    # ── Dataset ───────────────────────────────────────────────────────────────
    data_root   = REPO_ROOT / cfg["data"]["data_root"]
    image_size  = tuple(cfg["data"]["image_size"])
    action_std  = cfg["data"]["action_std"]

    train_ds = GNMDataset(
        data_root    = data_root,
        context_size = cfg["model"]["context_size"],
        max_goal_dist= cfg["data"]["max_goal_dist"],
        image_size   = image_size,
        augment      = True,
        action_std   = action_std,
        split        = "train",
    )
    val_ds = GNMDataset(
        data_root    = data_root,
        context_size = cfg["model"]["context_size"],
        max_goal_dist= cfg["data"]["max_goal_dist"],
        image_size   = image_size,
        augment      = False,
        action_std   = action_std,
        split        = "val",
    )

    # Smaller batch for LoRA (fewer trainable params → less memory pressure)
    bs = cfg["training"].get("batch_size", 128) // 2

    train_loader = torch.utils.data.DataLoader(
        train_ds, batch_size=bs, shuffle=True,
        num_workers=cfg["data"].get("num_workers", 4),
        pin_memory=True, collate_fn=collate_gnm, drop_last=True,
    )
    val_loader = torch.utils.data.DataLoader(
        val_ds, batch_size=bs * 2, shuffle=False,
        num_workers=cfg["data"].get("num_workers", 4),
        pin_memory=True, collate_fn=collate_gnm,
    )

    # Use smaller LR for LoRA (base already converged)
    lora_train_cfg = dict(cfg["training"])
    lora_train_cfg["lr"]     = lora_cfg.get("lr", cfg["training"]["lr"] / 3)
    lora_train_cfg["epochs"] = lora_cfg.get("epochs", 20)

    # ── W&B ───────────────────────────────────────────────────────────────────
    wandb_run = None
    try:
        import wandb
        wcfg = cfg.get("wandb", {})
        run_name = f"lora_r{rank}_a{int(alpha)}_{target_name}"
        wandb_run = wandb.init(
            project = wcfg.get("project", "fleetsafe-gnm-vlnverse"),
            entity  = wcfg.get("entity") or None,
            name    = run_name,
            tags    = wcfg.get("tags", []) + ["lora", "track_C"],
            config  = {**cfg, "lora": lora_cfg},
        )
        logger.info(f"W&B run: {wandb_run.url}")
    except Exception as e:
        logger.warning(f"W&B not available: {e}")

    # ── Train ─────────────────────────────────────────────────────────────────
    output_dir = REPO_ROOT / args.output_dir
    trainer = GNMTrainer(
        model        = model,
        train_loader = train_loader,
        val_loader   = val_loader,
        cfg          = lora_train_cfg,
        output_dir   = output_dir,
        wandb_run    = wandb_run,
    )

    logger.info("Starting LoRA fine-tuning...")
    result = trainer.fit()

    # Save LoRA-only weights (small delta file)
    lora_only_path = output_dir / "lora_weights.pt"
    torch.save(lora_state_dict(model), lora_only_path)
    logger.info(f"LoRA delta saved: {lora_only_path}  ({lora_only_path.stat().st_size / 1024:.0f} KB)")

    if wandb_run:
        wandb_run.log(result)
        wandb_run.save(str(lora_only_path))
        wandb_run.finish()

    logger.info(f"Best val action loss: {result['best_val_action_loss']:.6f}")
    logger.info("Next step:")
    logger.info(f"  python scripts/gnm/06_evaluate.py --ckpt {output_dir}/best.pt --track C")


if __name__ == "__main__":
    main()
