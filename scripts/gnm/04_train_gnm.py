#!/usr/bin/env python3
"""scripts/gnm/04_train_gnm.py
Step 4 of 7: Train GNM on VLNVerse data (Track A — pure visual-goal navigation).

What this script does
──────────────────────
  1. Loads config from YAML (configs/gnm/gnm_base.yaml)
  2. Builds GNM model (MobileNetV2 encoder + dist/action heads)
  3. Creates train/val DataLoaders from converted dataset
  4. Initialises W&B run
  5. Runs GNMTrainer.fit() — epochs of forward/backward + LR schedule
  6. Saves best.pt and latest.pt checkpoints

How to understand the config overrides
────────────────────────────────────────
  Parameters can be overridden from the command line in `key=value` form
  using OmegaConf dot notation:

    python scripts/gnm/04_train_gnm.py training.lr=3e-4
    python scripts/gnm/04_train_gnm.py training.epochs=5 training.batch_size=32
    python scripts/gnm/04_train_gnm.py model.encoder=efficientnet

  To override nested keys use dot notation:
    model.context_size=3   data.max_goal_dist=10   wandb.name=my_run

Reviewer notes
──────────────
  - Training on A100 (40 GB): ~8 h for 200 epochs, batch 256
  - Training on RTX 3090 (24 GB): ~12 h for 200 epochs, batch 128
  - Smoke test (5 epochs, batch 32): ~10 min on any modern GPU
  - Action normalization: MUST run 03_compute_action_std.py first

Outputs
───────
  checkpoints/gnm_base/
    best.pt     — lowest val action loss
    latest.pt   — after every epoch
"""
from __future__ import annotations

import argparse
import logging
import random
import sys
from pathlib import Path

import numpy as np
import torch
import yaml
from omegaconf import OmegaConf

# ── Paths ─────────────────────────────────────────────────────────────────────
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
logger = logging.getLogger("gnm.train")


# ── Config loading ─────────────────────────────────────────────────────────────

def load_config(cfg_path: str, overrides: list[str]) -> dict:
    """Load YAML then apply CLI overrides (key=value format)."""
    base = OmegaConf.load(cfg_path)
    if overrides:
        cli  = OmegaConf.from_dotlist(overrides)
        base = OmegaConf.merge(base, cli)
    return OmegaConf.to_container(base, resolve=True)


# ── Reproducibility ───────────────────────────────────────────────────────────

def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark     = False


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--cfg",
        default="configs/gnm/gnm_base.yaml",
        help="Path to YAML config",
    )
    parser.add_argument(
        "--split-config",
        default=None,
        help="Optional scene-level split YAML "
             "(e.g. configs/gnm/splits/scene_holdout_kujiale_0271.yaml). "
             "When set, train_scenes from the config are used to filter the "
             "training split; test_scenes are excluded from training.",
    )
    parser.add_argument(
        "overrides",
        nargs="*",
        help="OmegaConf overrides: key=value  e.g. training.lr=3e-4",
    )
    args = parser.parse_args()

    cfg_path = REPO_ROOT / args.cfg
    if not cfg_path.exists():
        logger.error(f"Config not found: {cfg_path}")
        sys.exit(1)

    cfg = load_config(str(cfg_path), args.overrides)
    logger.info(f"Config loaded from {cfg_path}")

    # ── Seed ──────────────────────────────────────────────────────────────────
    seed = cfg["training"].get("seed", 42)
    set_seed(seed)
    logger.info(f"Seed: {seed}")

    # ── Check action_std ──────────────────────────────────────────────────────
    action_std = cfg["data"]["action_std"]
    if action_std == [1.0, 1.0]:
        logger.warning(
            "action_std is [1.0, 1.0] (default).  "
            "Run 03_compute_action_std.py --update-config first for correct normalisation."
        )

    # ── Scene filter (optional) ───────────────────────────────────────────────
    train_scenes: list[str] | None = None
    if args.split_config:
        split_cfg_path = REPO_ROOT / args.split_config
        if not split_cfg_path.exists():
            logger.error(f"Split config not found: {split_cfg_path}")
            sys.exit(1)
        with open(split_cfg_path) as f:
            sc = yaml.safe_load(f)
        sc = sc.get("split", sc)
        train_scenes = sc.get("train_scenes")
        test_scenes  = sc.get("test_scenes", [])
        logger.info(
            f"Scene holdout split: train={train_scenes}  test={test_scenes}"
        )

    # ── Dataset ───────────────────────────────────────────────────────────────
    data_root  = REPO_ROOT / cfg["data"]["data_root"]
    image_size = tuple(cfg["data"]["image_size"])

    logger.info(f"Loading dataset from {data_root}")

    train_ds = GNMDataset(
        data_root    = data_root,
        context_size = cfg["model"]["context_size"],
        max_goal_dist= cfg["data"]["max_goal_dist"],
        image_size   = image_size,
        augment      = cfg["data"].get("augment", True),
        action_std   = action_std,
        split        = "train",
        allow_scenes = train_scenes,
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

    logger.info(f"Train: {len(train_ds):,} samples  |  Val: {len(val_ds):,} samples")

    if len(train_ds) == 0:
        logger.error("Training dataset is empty. Run 03_convert_data.py first.")
        sys.exit(1)

    batch_size  = cfg["training"]["batch_size"]
    num_workers = cfg["data"].get("num_workers", 4)
    pin_memory  = cfg["data"].get("pin_memory", True)

    train_loader = torch.utils.data.DataLoader(
        train_ds,
        batch_size  = batch_size,
        shuffle     = True,
        num_workers = num_workers,
        pin_memory  = pin_memory,
        collate_fn  = collate_gnm,
        drop_last   = True,
    )
    val_loader = torch.utils.data.DataLoader(
        val_ds,
        batch_size  = batch_size * 2,
        shuffle     = False,
        num_workers = num_workers,
        pin_memory  = pin_memory,
        collate_fn  = collate_gnm,
    )

    # ── Model ─────────────────────────────────────────────────────────────────
    model = build_gnm(cfg["model"])
    param_info = model.count_parameters()
    logger.info(
        f"GNM model built: "
        f"{param_info['total'] / 1e6:.1f}M params total  "
        f"({param_info['encoder'] / 1e6:.1f}M encoder + "
        f"{param_info['heads'] / 1e6:.1f}M heads)"
    )

    # ── W&B ───────────────────────────────────────────────────────────────────
    wandb_run = None
    wcfg      = cfg.get("wandb", {})
    try:
        import wandb
        wandb_run = wandb.init(
            project = wcfg.get("project", "fleetsafe-gnm-vlnverse"),
            entity  = wcfg.get("entity")  or None,
            name    = wcfg.get("name", "gnm_base_track_A"),
            tags    = wcfg.get("tags", []),
            notes   = wcfg.get("notes", ""),
            config  = cfg,
            resume  = "allow",
        )
        logger.info(f"W&B run: {wandb_run.url}")
    except ImportError:
        logger.warning("wandb not installed — training without W&B logging")
    except Exception as e:
        logger.warning(f"W&B init failed ({e}) — training without W&B logging")

    # ── Train ─────────────────────────────────────────────────────────────────
    output_dir = REPO_ROOT / cfg["checkpoint"]["output_dir"]
    trainer    = GNMTrainer(
        model        = model,
        train_loader = train_loader,
        val_loader   = val_loader,
        cfg          = cfg["training"],
        output_dir   = output_dir,
        wandb_run    = wandb_run,
        full_cfg     = cfg,
    )

    # Override log_every from checkpoint section
    trainer.log_every = cfg["checkpoint"].get("log_every", 50)

    # Resume from checkpoint if one exists
    latest_ckpt = output_dir / "latest.pt"
    if latest_ckpt.exists():
        logger.info(f"Resuming from {latest_ckpt}")
        trainer.load_checkpoint(latest_ckpt)

    logger.info("Starting training...")
    result = trainer.fit()

    if wandb_run:
        wandb_run.log(result)
        wandb_run.finish()

    logger.info(
        f"Training complete.  Best val action loss: {result['best_val_action_loss']:.6f}"
    )
    logger.info(f"Checkpoints saved to: {output_dir}")
    logger.info("")
    logger.info("Next step:")
    logger.info("  python scripts/gnm/06_evaluate.py --ckpt checkpoints/gnm_base/best.pt")


if __name__ == "__main__":
    main()
