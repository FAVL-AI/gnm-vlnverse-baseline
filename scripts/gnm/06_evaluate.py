#!/usr/bin/env python3
"""scripts/gnm/06_evaluate.py
Step 6 of 7: Evaluate a trained GNM checkpoint on the val or test split.

What this script does
──────────────────────
  1. Loads the trained GNM checkpoint
  2. For each trajectory in the split:
       a. Loads the reference path (ground-truth positions from traj_data.pkl)
       b. Runs GNM inference frame-by-frame using a single-integrator simulator
       c. Computes all VLNVerse metrics for that episode
  3. Aggregates metrics across all episodes
  4. Prints a results table and saves JSON

Important: this is OFFLINE evaluation (no live Isaac Sim).
  - The robot's motion is simulated with a simple physics model (no collisions)
  - For physics-accurate evaluation, use evaluate_in_isaac() instead
  - Offline evaluation is reproducible and fast — ~1000 episodes/minute

Metric reference
─────────────────
  SR   — Success Rate: fraction of episodes where robot stopped within 3m of goal
  OSR  — Oracle SR: fraction where robot was EVER within 3m (upper bound)
  SPL  — SR × (shortest_path / actual_path): penalises detours
  NE   — Navigation Error: average final distance to goal (metres, lower better)
  TL   — Trajectory Length: average metres walked
  nDTW — Path similarity to reference trajectory [0,1], higher better
  CLS  — Coverage × Length Score [0,1], higher better
  CR   — Collision Rate [0,1], 0 = no collisions (offline: always 0)
  SRn  — Sub-goal success rate (for long-horizon tasks)

Usage
─────
    python scripts/gnm/06_evaluate.py --ckpt checkpoints/gnm_base/best.pt
    python scripts/gnm/06_evaluate.py --ckpt checkpoints/gnm_base/best.pt --split test
    python scripts/gnm/06_evaluate.py --ckpt checkpoints/gnm_lora/best.pt  --track C
    python scripts/gnm/06_evaluate.py --ckpt checkpoints/gnm_base/best.pt  --save-episodes
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import torch
import yaml
from omegaconf import OmegaConf

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from gnm_vlnverse.evaluation.evaluator import GNMEvaluator
from gnm_vlnverse.models.gnm import build_gnm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("gnm.eval")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--ckpt",
        required=True,
        help="Path to checkpoint .pt file",
    )
    parser.add_argument(
        "--cfg",
        default="configs/gnm/gnm_base.yaml",
        help="Config YAML (overridden by values stored in checkpoint)",
    )
    parser.add_argument(
        "--split",
        default="val",
        choices=["train", "val", "test"],
        help="Which split to evaluate on",
    )
    parser.add_argument(
        "--track",
        default="A",
        choices=["A", "B", "C"],
        help="Evaluation track (A=visual goal, B=language, C=LoRA)",
    )
    parser.add_argument(
        "--data-root",
        default=None,
        help="Override data root from config",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Where to write per-episode JSONs (default: next to checkpoint)",
    )
    parser.add_argument(
        "--save-episodes",
        action="store_true",
        help="Save per-episode result JSONs",
    )
    parser.add_argument(
        "--device",
        default="cuda",
        help="cuda | cpu",
    )
    parser.add_argument(
        "--no-ema",
        action="store_true",
        help="Force live model weights even if EMA shadow weights are present "
             "(use when ema_decay is too high for the number of training steps)",
    )
    parser.add_argument(
        "--split-config",
        default=None,
        help="Optional scene-level split YAML for scene-holdout evaluation. "
             "When set, test_scenes from the config are used to filter the "
             "evaluated split (use with --split train to evaluate held-out scenes).",
    )
    args = parser.parse_args()

    # ── Load checkpoint ───────────────────────────────────────────────────────
    ckpt_path = Path(args.ckpt)
    if not ckpt_path.is_absolute():
        ckpt_path = REPO_ROOT / ckpt_path
    if not ckpt_path.exists():
        logger.error(f"Checkpoint not found: {ckpt_path}")
        sys.exit(1)

    logger.info(f"Loading checkpoint: {ckpt_path}")
    device = torch.device(args.device if torch.cuda.is_available() else "cpu")
    ckpt   = torch.load(ckpt_path, map_location=device)

    # Config: prefer checkpoint-embedded full config, fall back to YAML.
    # Old checkpoints only stored the training sub-dict (no "model" key).
    embedded = ckpt.get("cfg", {})
    if isinstance(embedded, dict) and "model" in embedded:
        cfg = embedded
        logger.info("Using config embedded in checkpoint")
    else:
        cfg = OmegaConf.to_container(OmegaConf.load(REPO_ROOT / args.cfg), resolve=True)
        if embedded:
            logger.info("Checkpoint cfg is training-only — using full config from YAML")
        else:
            logger.info(f"Using config from {args.cfg}")

    # ── Build model ───────────────────────────────────────────────────────────
    model = build_gnm(cfg["model"])
    # Prefer EMA shadow weights (1-3% better for fully-converged runs); fall back
    # to live weights if EMA is absent or --no-ema is set.
    # Note: ema_decay=0.9999 needs ~7000 optimizer steps (≈70 epochs at bs=128)
    # to pass one half-life. For shorter runs use --no-ema or reduce ema_decay.
    has_ema = "ema_state" in ckpt and ckpt["ema_state"] is not None
    use_ema = has_ema and not args.no_ema
    state   = ckpt["ema_state"] if use_ema else ckpt["model_state"]
    model.load_state_dict(state)
    model.eval()
    logger.info(
        f"Model: {sum(p.numel() for p in model.parameters()) / 1e6:.1f}M params"
        f"  (weights: {'EMA shadow' if use_ema else 'live model'})"
        + (" [--no-ema forced]" if args.no_ema and has_ema else "")
    )

    # ── Evaluator ─────────────────────────────────────────────────────────────
    eval_cfg   = cfg.get("evaluation", {})
    action_std = cfg["data"]["action_std"]
    image_size = tuple(cfg["data"]["image_size"])

    evaluator = GNMEvaluator(
        model          = model,
        action_std     = action_std,
        context_size   = cfg["model"]["context_size"],
        image_size     = image_size,
        stop_threshold = eval_cfg.get("stop_threshold", 0.15),
        max_steps      = eval_cfg.get("max_steps", 500),
        device         = str(device),
        track          = args.track,
    )

    # ── Data root ─────────────────────────────────────────────────────────────
    data_root_str = args.data_root or cfg["data"]["data_root"]
    data_root     = Path(data_root_str)
    if not data_root.is_absolute():
        data_root = REPO_ROOT / data_root

    if not (data_root / args.split).exists():
        logger.error(f"Split directory not found: {data_root / args.split}")
        sys.exit(1)

    # ── Output dir ────────────────────────────────────────────────────────────
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = ckpt_path.parent / f"eval_{args.split}_track{args.track}"
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Scene filter (optional) ───────────────────────────────────────────────
    eval_scenes: list[str] | None = None
    if args.split_config:
        sc_path = Path(args.split_config)
        if not sc_path.is_absolute():
            sc_path = REPO_ROOT / sc_path
        if not sc_path.exists():
            logger.error(f"Split config not found: {sc_path}")
            sys.exit(1)
        with open(sc_path) as f:
            sc = yaml.safe_load(f)
        sc = sc.get("split", sc)
        eval_scenes = sc.get("test_scenes")
        logger.info(f"Scene-holdout eval: evaluating only scenes {eval_scenes}")

    # ── Run evaluation ────────────────────────────────────────────────────────
    logger.info(
        f"Evaluating on {args.split} split  "
        f"(Track {args.track}, data={data_root})"
    )

    metrics = evaluator.evaluate_dataset(
        data_root    = data_root,
        split        = args.split,
        output_dir   = output_dir if args.save_episodes else None,
        allow_scenes = eval_scenes,
    )

    # ── Print results ─────────────────────────────────────────────────────────
    print()
    print("═══════════════════════════════════════════════════════════════")
    print(f" GNM Evaluation Results — Track {args.track} — {args.split} split")
    print("═══════════════════════════════════════════════════════════════")
    print(f"  Episodes:           {metrics.n_episodes}")
    print(f"  SR   (Success Rate): {metrics.SR:.4f}  ({metrics.SR*100:.1f}%)")
    print(f"  OSR  (Oracle SR):    {metrics.OSR:.4f}  ({metrics.OSR*100:.1f}%)")
    print(f"  SPL  (Succ×Eff):    {metrics.SPL:.4f}  ({metrics.SPL*100:.1f}%)")
    print(f"  NE   (Nav Error):   {metrics.NE:.2f} m")
    print(f"  TL   (Traj Length): {metrics.TL:.2f} m")
    print(f"  nDTW (Path Match):  {metrics.nDTW:.4f}")
    print(f"  CLS  (Coverage×L):  {metrics.CLS:.4f}")
    print(f"  CR   (Collision):   {metrics.CR:.4f}  (0 in offline eval)")
    print(f"  SRn  (Sub-goal SR): {metrics.SRn:.4f}")
    print("═══════════════════════════════════════════════════════════════")
    print()

    # ── Save summary JSON ─────────────────────────────────────────────────────
    results_path = output_dir / "metrics_summary.json"
    result_dict  = metrics.to_dict()
    result_dict.update({
        "checkpoint":   str(ckpt_path),
        "split":        args.split,
        "track":        args.track,
        "data_root":    str(data_root),
        "stop_threshold": eval_cfg.get("stop_threshold", 0.15),
        "success_threshold": eval_cfg.get("success_threshold", 3.0),
    })
    results_path.write_text(json.dumps(result_dict, indent=2))
    logger.info(f"Metrics saved: {results_path}")

    # ── W&B logging ───────────────────────────────────────────────────────────
    try:
        import wandb
        if wandb.run:
            wandb.log({f"eval_{args.split}/{k}": v for k, v in metrics.to_dict().items()})
    except Exception:
        pass

    if metrics.SR < 0.1:
        logger.warning(
            "SR < 10% — check that action_std was computed correctly, "
            "and that the model was trained for enough epochs."
        )


if __name__ == "__main__":
    main()
