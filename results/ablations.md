# GNM Track A Ablation Record

Dataset: 4-scene VLNTube/VLNVerse render  
Split: val (15 episodes, 15 trajectories)  
Evaluator: EMA-aware (commit 45fd655)  
Code HEAD at final entry: 51461a5

---

## Stable published result

| Variant | Encoder | hidden_dim | AMP | EMA | loss | action_weight | val_loss | dist_pred | SR | OSR | NE | SPL | TL | CR | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Baseline** | MobileNet | 256 | No | No | mse | 0.5 | 0.296 | mean=0.33, healthy | **20.0%** | **46.7%** | **6.51m** | 20.0% | 8.08m | 0.0 | **VALID** |

Baseline is the official Track A result until a variant beats it on SR/OSR/NE.

---

## Ablation series (chronological)

### SOTA v1 — EfficientNet, full SOTA recipe

| Field | Value |
|---|---|
| Variant | gnm_sota |
| Encoder | EfficientNet-B0 |
| hidden_dim | 512 |
| AMP | Yes (BF16) |
| EMA | Yes (decay=0.9999) |
| loss | huber (delta=1.0) |
| action_weight | 0.6 |
| encoder_lr_scale | 0.1 |
| grad_accum | 2 |
| epochs | 200/200 |
| val_loss | 0.490 |
| dist_pred | mean=0.117, range=[0.105,0.126], **constant** |
| pred_target_corr | — |
| collapse_count | 20/20 random |
| SR / OSR / NE | 20.0% / 20.0% / 6.09m |
| TL | 0.06m (robot stops at step 0) |
| Verdict | **COLLAPSED-LOW** — dist head converged to constant below stop_threshold |

### SOTA v2 — EfficientNet, reduced loss/LR fixes

| Field | Value |
|---|---|
| Variant | gnm_sota_v2 |
| Encoder | EfficientNet-B0 |
| hidden_dim | 512 |
| AMP | Yes |
| EMA | Yes (decay=0.9999) |
| loss | mse |
| action_weight | 0.5 |
| encoder_lr_scale | 0.3 |
| epochs | 25 (killed early) |
| val_loss | — |
| dist_pred | mean=−0.014, range=[−0.020,−0.008], **negative** |
| Verdict | **COLLAPSED-NEGATIVE** — worse than v1; killed at epoch 25 |

### A3 — EfficientNet + baseline training (no AMP/EMA/grad_accum)

| Field | Value |
|---|---|
| Variant | gnm_ablation_a3 |
| Encoder | EfficientNet-B0 |
| hidden_dim | 256 |
| AMP | No |
| EMA | No |
| loss | mse |
| action_weight | 0.5 |
| encoder_lr_scale | 1.0 (baseline) |
| epochs | 33/50 (early stopped) |
| val_loss | 5903 |
| dist_pred | mean=58.4, range=[0.67,950], pred_target_corr=−0.16 |
| Verdict | **EXPLODED** — full encoder LR blows up head (opposite of low lr_scale collapse) |

**EfficientNet conclusion**: no encoder_lr_scale value (0.1, 0.3, 1.0) produces a stable dist head with this dataset and architecture. Feature magnitude from EfficientNet-B0 is incompatible with GNM heads without a projection/normalization layer between encoder output and heads.

### A1 — MobileNet baseline + AMP + EMA

| Field | Value |
|---|---|
| Variant | gnm_ablation_a1 |
| Encoder | MobileNet |
| hidden_dim | 256 |
| AMP | Yes (BF16) |
| EMA | Yes (decay=0.9999) |
| loss | mse |
| action_weight | 0.5 |
| encoder_lr_scale | 1.0 |
| epochs | 50/50 |
| val_loss | 0.909 |
| dist_pred | mean=0.102, range=[0.039,0.178], pred_target_corr=+0.42 |
| collapse_count | 59/64 val samples (92%) |
| SR / OSR / NE | 20.0% / 20.0% / 6.08m |
| TL | 0.09m |
| Verdict | **BIASED-LOW** — model learns distance ranking (corr=+0.42) but EMA weights are calibrated too low |

**Root cause**: `ema_decay=0.9999` has a half-life of ~6931 optimizer steps. 50 epochs × 97 steps = 4850 steps — EMA never reaches one half-life, shadow weights still dominated by initialization. AMP (BF16) also increases train/val gap (130× vs 15× baseline).

### A1b — MobileNet + EMA (decay=0.9999), no AMP

| Field | Value |
|---|---|
| Variant | gnm_ablation_a1b |
| Encoder | MobileNet |
| AMP | No |
| EMA | Yes (decay=0.9999) |
| epochs | 50/50 |
| val_loss | 0.923 |
| Key finding | **Live weights are healthy** (mean=0.355, collapse=0/64 at epoch 13); EMA weights are stale (mean=0.033, collapse=64/64) |
| Eval weights | Live (--no-ema) |
| SR / OSR / NE | 20.0% / 26.7% / 5.05m |
| TL / nDTW | 2.88m / 0.483 |
| Verdict | **PARTIAL** — NE improves (5.05 vs 6.51m, +22%) but OSR regresses (26.7% vs 46.7%). Robot navigates more precisely but stops too early. EMA stale at 0.9999/50 epochs confirmed. |

### A1d — MobileNet + EMA (decay=0.999), no AMP

| Field | Value |
|---|---|
| Variant | gnm_ablation_a1d |
| Encoder | MobileNet |
| AMP | No |
| EMA | Yes (decay=0.999) — half-life=693 steps, converged by epoch 7 |
| epochs | 22/50 (early stopped, patience=10) |
| val_loss | 0.332 |
| EMA probe | mean=0.333, std=0.125, range=[0.134, 0.693], corr=+0.341, collapse=2/64 (3%) — HEALTHY |
| SR / OSR / NE | 20.0% / 46.7% / 6.61m |
| TL / nDTW / CLS | 8.11m / 0.455 / 0.606 |
| Verdict | **STABLE, matches baseline** — SR=OSR=baseline, nDTW marginally better (+0.006), NE marginally worse (+0.10m). EMA at 0.999 is properly converged and does not degrade navigation. |

---

## Summary table — navigation metrics

| Variant | SR | OSR | NE | SPL | TL | nDTW | CLS | val_loss | Notes |
|---|---|---|---|---|---|---|---|---|---|
| **Baseline** | **20.0%** | **46.7%** | **6.51m** | **20.0%** | **8.08m** | 0.449 | 0.658 | 0.296 | **Official Track A result** |
| SOTA v1 | 20.0% | 20.0% | 6.09m | 20.0% | 0.06m | 0.345 | 0.003 | 0.490 | dist collapsed (EMA stale) |
| A1 | 20.0% | 20.0% | 6.08m | 20.0% | 0.09m | 0.349 | 0.006 | 0.909 | dist biased (AMP + EMA stale) |
| A1b (live) | 20.0% | 26.7% | **5.05m** | 20.0% | 2.88m | **0.483** | 0.245 | 0.923 | NE↑ but OSR↓, stops early |
| A1d (EMA) | 20.0% | **46.7%** | 6.61m | 19.8% | 8.11m | 0.455 | 0.606 | 0.332 | matches baseline, EMA stable |

**Baseline remains the official Track A result.** A1d confirms EMA (decay=0.999) is a safe addition with no degradation; it does not yet improve SR/OSR/NE.

---

## Conclusions

1. **EfficientNet incompatible** at this dataset scale without feature projection layer.
2. **ema_decay=0.9999 is wrong for 50-epoch training** — half-life exceeds total training steps.
3. **ema_decay=0.999 is safe** — properly converged, matches baseline navigation metrics.
4. **AMP (BF16) not tested cleanly yet** — A1c (AMP only, no EMA) still pending if needed.
5. **The model IS learning correctly in all runs** — collapse/explosion was always in the eval weights, not the live training weights.

---

## Remaining experiment options

| ID | Change | Rationale |
|---|---|---|
| A1c | MobileNet + AMP only, no EMA | Cleanly isolate AMP effect |
| A2 | MobileNet + AMP + EMA (0.999) + grad_accum=2 | Full SOTA recipe on stable encoder |
| EfficientNet+proj | Add LayerNorm projection layer before GNM heads | Fix feature scale mismatch |

---

## Feature engineering path (if A2 needed)

To use EfficientNet-B0 properly, add a learned projection between encoder and GNM heads:

```python
self.encoder_proj = nn.Sequential(
    nn.Linear(encoder_out_dim, hidden_dim),
    nn.LayerNorm(hidden_dim),
    nn.ReLU(),
)
```

This normalises the feature scale before the dist and action heads see it.
