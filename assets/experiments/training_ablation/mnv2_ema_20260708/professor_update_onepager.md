# MobileNetV2-GNM Training Ablation + Isaac Physics Evaluation
*(one-page professor update — 2026-07-08)*

## 1. Objective
Test whether Exponential Moving Average (EMA) improves the current
MobileNetV2-GNM baseline, and add a real Collision Rate from Isaac Sim.
Controlled design: same four-scene VLNVerse/VLNTube split (documented in
`dataset_manifest.json`), same seed/config/evaluator — EMA the only change.

## 2. Offline VLN evaluation (held-out 15 episodes)

| Model | EMA decay | SR ↑ | OSR ↑ | NE ↓ | SPL ↑ | Collision Rate | Weights |
|---|---:|---:|---:|---:|---:|---|---|
| MobileNetV2 baseline | none | **13.3** | **46.7** | **6.14** | **0.133** | N/A — offline evaluator has no physics/contact signal | live model |
| + EMA (requested ablation) | 0.9999 | 20.0* | 20.0 | 6.05 | 0.200* | N/A — offline evaluator | EMA shadow |
| + EMA (decay-horizon sanity) | 0.999 | 6.7 | 33.3 | 6.93 | 0.067 | N/A — offline evaluator | EMA shadow |

\* Degenerate: at decay 0.9999 the shadow lags near initialization for
this run length (trajectory length 0.13 m); its nominal SR consists of
episodes starting inside the 3 m success radius.

## 3. Isaac Sim physics evaluation (smoke test, 3 straight routes/ckpt)

| Model | NE ↓ | Collision Rate ↓ | Total collisions | Notes |
|---|---:|---:|---:|---|
| MobileNetV2 baseline | 0.82 m | **0.00 — measured** | 0 | PhysX chassis contacts; SR/OSR saturated (routes < 3 m radius) |
| + EMA 0.999 | 0.82 m | **0.00 — measured** | 0 | both checkpoints saturate the 0.2 m/s safety clamp |

Collision Rate is measured from PhysX chassis-contact events (wheel–floor
contact excluded by construction) and **validated by a positive control**:
a deliberate collision episode logged 27 contacts against the reception
desk. The measured zeros are therefore verified, not assumed.

## 4. Decision
**Baseline kept.** EMA 0.9999 rejected due to decay-horizon mismatch
(not "EMA failed" — decay must match training steps). EMA 0.999 achieved
the best validation loss but did not improve downstream navigation
metrics enough to replace the baseline; reported as a completed ablation.

## 5. Scientific notes
Small 15-episode held-out split (one episode = 6.7 pp SR) → preliminary,
high-variance. Isaac run is a physics smoke evaluation, not a full
campaign. EfficientNet paused to avoid confounding EMA with
backbone-capacity change (appendix on file). Our VLNVerse/VLNTube usage
is a controlled adapted subset, not a full benchmark submission
(protocol-alignment appendix on file).

## 6. Next step
Expand VLNVerse/VLNTube data primarily for training/validation; preserve
scene-level held-out testing; larger Isaac physics evaluation after the
selected checkpoint is finalized; resume EfficientNet after this
controlled baseline is reproducible.
