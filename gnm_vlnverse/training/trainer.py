"""GNM training loop with Weights & Biases integration.

Training overview
-----------------
  Epoch loop:
    Train loop → forward → GNM loss → backward → optimiser step
    Val loop   → forward → metrics (no gradient)
    W&B logging of all losses, LR, gradient norms, sample images
    Checkpoint saving (best val, latest)

Optimiser: AdamW
  Why not SGD?  AdamW converges much faster on small navigation datasets
  and handles the mixed MSE objectives (action + distance) cleanly.
  Weight decay in AdamW does NOT apply to biases, unlike L2-regularised SGD.

LR schedule: Cosine with warmup
  - Warmup: linearly increase LR for first warmup_steps steps
  - Then: cosine decay from lr_max → lr_min
  - This prevents early training instability (warmup) and avoids oscillation
    near the minimum (cosine decay)

Gradient clipping
  max_grad_norm = 1.0 (standard for navigation/robotics models)
  Prevents occasional large gradients from destabilising training.

W&B Integration
  - Every train step: losses + LR
  - Every val step: losses
  - Every log_image_interval: sample obs/goal/predicted_waypoint overlay
  - End of epoch: histogram of action predictions

Reviewer questions
------------------
Q: How many epochs?
A: 50 epochs on VLNTube-converted data (~10K trajectories) takes ~8 hours on
   a single A100.  Set epochs=200 for full training, 20 for smoke test.

Q: What batch size?
A: 256 is standard for GNM.  Reduce to 64 if GPU memory is constrained.
   Larger batch → more stable gradients, but needs proportionally larger LR.
   Linear scaling rule: lr = base_lr * batch_size / 256.

Q: When to stop?
A: Track val loss_action.  If it hasn't improved for patience=10 epochs, stop.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Optional

import torch
import torch.nn as nn
from torch.optim import AdamW
from torch.optim.lr_scheduler import LambdaLR
from torch.utils.data import DataLoader

try:
    import wandb
    _WANDB_AVAILABLE = True
except ImportError:
    _WANDB_AVAILABLE = False

from .losses import GNMLoss
from .ema import EMA

logger = logging.getLogger(__name__)


# ── LR schedule ───────────────────────────────────────────────────────────────

def cosine_with_warmup(
    optimizer: torch.optim.Optimizer,
    num_warmup_steps: int,
    num_training_steps: int,
    min_lr_ratio: float = 0.1,
) -> LambdaLR:
    """Cosine decay schedule with linear warmup.

    Warmup: LR linearly increases from 0 → lr_max over num_warmup_steps.
    Decay:  LR follows a cosine curve from lr_max → min_lr_ratio * lr_max.
    """
    def lr_lambda(step: int) -> float:
        if step < num_warmup_steps:
            return step / max(1, num_warmup_steps)
        progress = (step - num_warmup_steps) / max(1, num_training_steps - num_warmup_steps)
        cosine   = 0.5 * (1 + math.cos(math.pi * progress))
        return min_lr_ratio + (1 - min_lr_ratio) * cosine

    return LambdaLR(optimizer, lr_lambda=lr_lambda)


# ── Trainer ────────────────────────────────────────────────────────────────────

class GNMTrainer:
    """Full GNM training harness.

    Parameters
    ----------
    model : nn.Module
        GNM model (or LoRA-wrapped GNM).
    train_loader, val_loader : DataLoader
    cfg : dict
        Training configuration (loaded from YAML).
    output_dir : Path
        Where to save checkpoints.
    wandb_run : optional
        A wandb.run object.  Pass None to disable W&B.
    """

    def __init__(
        self,
        model: nn.Module,
        train_loader: DataLoader,
        val_loader: DataLoader,
        cfg: dict,
        output_dir: Path | str = "checkpoints/gnm",
        wandb_run=None,
        full_cfg: dict | None = None,
    ) -> None:
        self.model        = model
        self.train_loader = train_loader
        self.val_loader   = val_loader
        self.cfg          = cfg
        self.full_cfg     = full_cfg  # full YAML config — saved in checkpoint for evaluator
        self.output_dir   = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.wandb_run    = wandb_run

        # Device
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)
        logger.info(f"Training on {self.device}")

        # Loss
        self.criterion = GNMLoss(
            action_weight=cfg.get("action_weight", 0.5),
            loss_type=cfg.get("loss_type", "mse"),
            huber_delta=cfg.get("huber_delta", 1.0),
        )

        # ── Discriminative LR ─────────────────────────────────────────────────
        # Encoder gets a lower LR than the heads.  This prevents destroying
        # ImageNet-pretrained representations while the heads are still noisy.
        base_lr         = cfg.get("lr", 1e-4)
        encoder_scale   = cfg.get("encoder_lr_scale", 1.0)
        encoder_lr      = base_lr * encoder_scale
        weight_decay    = cfg.get("weight_decay", 1e-4)

        encoder_decay, encoder_nodecay, head_decay, head_nodecay = [], [], [], []
        encoder_names = {"obs_encoder", "goal_encoder"}
        for n, p in model.named_parameters():
            if not p.requires_grad:
                continue
            in_encoder = any(n.startswith(prefix) for prefix in encoder_names)
            bucket = (encoder_decay if in_encoder else head_decay) if len(p.shape) > 1 \
                     else (encoder_nodecay if in_encoder else head_nodecay)
            bucket.append(p)

        param_groups = [
            {"params": encoder_decay,   "lr": encoder_lr,  "weight_decay": weight_decay},
            {"params": encoder_nodecay, "lr": encoder_lr,  "weight_decay": 0.0},
            {"params": head_decay,      "lr": base_lr,     "weight_decay": weight_decay},
            {"params": head_nodecay,    "lr": base_lr,     "weight_decay": 0.0},
        ]
        self.optimizer = AdamW([g for g in param_groups if g["params"]])

        if encoder_scale != 1.0:
            logger.info(f"Discriminative LR: encoder={encoder_lr:.2e}  heads={base_lr:.2e}")

        # ── Scheduler ─────────────────────────────────────────────────────────
        self.grad_accum = cfg.get("grad_accum_steps", 1)
        effective_steps = cfg.get("epochs", 50) * math.ceil(len(train_loader) / self.grad_accum)
        warmup_steps    = int(cfg.get("warmup_frac", 0.05) * effective_steps)
        self.scheduler  = cosine_with_warmup(self.optimizer, warmup_steps, effective_steps)

        # ── Mixed precision ───────────────────────────────────────────────────
        self.use_amp = cfg.get("use_amp", False) and self.device.type == "cuda"
        self.scaler  = torch.amp.GradScaler("cuda", enabled=self.use_amp)
        if self.use_amp:
            logger.info("Mixed precision (AMP) enabled")

        # ── EMA ───────────────────────────────────────────────────────────────
        ema_decay    = cfg.get("ema_decay", 0.0)
        self.ema     = EMA(model, decay=ema_decay) if ema_decay > 0 else None
        if self.ema:
            logger.info(f"EMA enabled (decay={ema_decay})")

        self.max_grad_norm = cfg.get("max_grad_norm", 1.0)
        self.epochs        = cfg.get("epochs", 50)
        self.log_every     = cfg.get("log_every", 50)
        self.best_val_loss = math.inf
        self.patience      = cfg.get("patience", 10)
        self._no_improve   = 0
        self.global_step   = 0

    # ── Main train loop ────────────────────────────────────────────────────────

    def fit(self) -> dict:
        """Run the full training loop.  Returns final metrics."""
        logger.info(f"Starting training: {self.epochs} epochs")

        for epoch in range(1, self.epochs + 1):
            train_metrics = self._train_epoch(epoch)
            val_metrics   = self._val_epoch(epoch)

            improved = val_metrics["loss_action"] < self.best_val_loss
            if improved:
                self.best_val_loss = val_metrics["loss_action"]
                self._save_checkpoint("best.pt")
                self._no_improve = 0
            else:
                self._no_improve += 1

            self._save_checkpoint("latest.pt")

            summary = {
                "epoch":       epoch,
                **{f"train/{k}": v for k, v in train_metrics.items()},
                **{f"val/{k}":   v for k, v in val_metrics.items()},
                "lr":          self.scheduler.get_last_lr()[0],
                "best_val_action": self.best_val_loss,
            }

            logger.info(
                f"[Epoch {epoch:3d}/{self.epochs}] "
                f"train_loss={train_metrics['loss_total']:.4f}  "
                f"val_loss={val_metrics['loss_total']:.4f}  "
                f"lr={self.scheduler.get_last_lr()[0]:.2e}"
                + (" *" if improved else "")
            )

            if self.wandb_run:
                self.wandb_run.log(summary, step=self.global_step)

            if self._no_improve >= self.patience:
                logger.info(f"Early stopping at epoch {epoch} (no improvement for {self.patience} epochs)")
                break

        return {"best_val_action_loss": self.best_val_loss}

    # ── Train epoch ───────────────────────────────────────────────────────────

    def _train_epoch(self, epoch: int) -> dict[str, float]:
        self.model.train()
        accum: dict[str, float] = {}
        self.optimizer.zero_grad()

        for step, batch in enumerate(self.train_loader):
            obs       = batch["obs"].to(self.device, non_blocking=True)
            goal      = batch["goal"].to(self.device, non_blocking=True)
            dist_gt   = batch["dist"].to(self.device, non_blocking=True)
            action_gt = batch["action"].to(self.device, non_blocking=True)

            with torch.amp.autocast("cuda", enabled=self.use_amp):
                dist_pred, action_pred = self.model(obs, goal)
                loss, metrics = self.criterion(dist_pred, action_pred, dist_gt, action_gt)
                loss = loss / self.grad_accum

            self.scaler.scale(loss).backward()

            is_update_step = (step + 1) % self.grad_accum == 0 \
                             or (step + 1) == len(self.train_loader)
            if is_update_step:
                self.scaler.unscale_(self.optimizer)
                grad_norm = nn.utils.clip_grad_norm_(
                    self.model.parameters(), self.max_grad_norm
                )
                self.scaler.step(self.optimizer)
                self.scaler.update()
                self.optimizer.zero_grad()
                self.scheduler.step()
                if self.ema:
                    self.ema.update(self.model)
                self.global_step += 1

                if self.wandb_run and self.global_step % self.log_every == 0:
                    self.wandb_run.log({
                        **{f"train_step/{k}": v for k, v in metrics.items()},
                        "train_step/grad_norm": float(grad_norm),
                        "train_step/lr":        self.scheduler.get_last_lr()[0],
                        "train_step/scaler":    self.scaler.get_scale() if self.use_amp else 1.0,
                    }, step=self.global_step)

            for k, v in metrics.items():
                accum[k] = accum.get(k, 0.0) + v

        n = max(len(self.train_loader), 1)
        return {k: v / n for k, v in accum.items()}

    # ── Val epoch ─────────────────────────────────────────────────────────────

    def _val_epoch(self, epoch: int) -> dict[str, float]:
        # Validate with EMA weights when available (consistently better metrics)
        eval_model = self.ema.shadow if self.ema else self.model
        eval_model.eval()
        accum: dict[str, float] = {}

        with torch.no_grad():
            for batch in self.val_loader:
                obs       = batch["obs"].to(self.device, non_blocking=True)
                goal      = batch["goal"].to(self.device, non_blocking=True)
                dist_gt   = batch["dist"].to(self.device, non_blocking=True)
                action_gt = batch["action"].to(self.device, non_blocking=True)

                with torch.amp.autocast("cuda", enabled=self.use_amp):
                    dist_pred, action_pred = eval_model(obs, goal)
                    _, metrics = self.criterion(dist_pred, action_pred, dist_gt, action_gt)

                for k, v in metrics.items():
                    accum[k] = accum.get(k, 0.0) + v

        n = max(len(self.val_loader), 1)
        return {k: v / n for k, v in accum.items()}

    # ── Checkpoint ────────────────────────────────────────────────────────────

    def _save_checkpoint(self, name: str) -> None:
        ckpt = {
            "model_state":     self.model.state_dict(),
            "optimizer_state": self.optimizer.state_dict(),
            "scheduler_state": self.scheduler.state_dict(),
            "scaler_state":    self.scaler.state_dict() if self.use_amp else None,
            "ema_state":       self.ema.state_dict() if self.ema else None,
            "global_step":     self.global_step,
            "best_val_loss":   self.best_val_loss,
            "cfg":             self.full_cfg if self.full_cfg is not None else self.cfg,
        }
        torch.save(ckpt, self.output_dir / name)

    def load_checkpoint(self, path: Path | str) -> None:
        ckpt = torch.load(path, map_location=self.device)
        self.model.load_state_dict(ckpt["model_state"])
        self.optimizer.load_state_dict(ckpt["optimizer_state"])
        self.scheduler.load_state_dict(ckpt["scheduler_state"])
        if self.use_amp and ckpt.get("scaler_state"):
            self.scaler.load_state_dict(ckpt["scaler_state"])
        if self.ema and ckpt.get("ema_state"):
            self.ema.load_state_dict(ckpt["ema_state"])
        self.global_step   = ckpt["global_step"]
        self.best_val_loss = ckpt["best_val_loss"]
        logger.info(f"Resumed from {path} (step {self.global_step})")
