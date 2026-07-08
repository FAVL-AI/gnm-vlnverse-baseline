# MobileNetV2-GNM Training Ablation Summary

**Objective:** Test whether Exponential Moving Average (EMA) improves the
current MobileNetV2-GNM baseline.

**Models trained (same split, scenes, preprocessing, image size, optimizer,
LR schedule, batch size, epochs, seed 42; EMA the only change):**
1. MobileNetV2-GNM baseline
2. MobileNetV2-GNM + EMA 0.9999 (originally requested ablation)
3. MobileNetV2-GNM + EMA 0.999 (decay-horizon sanity ablation: the run is
   ~4,700 optimizer steps, below one 0.9999 EMA half-life)

**Dataset:** current four-scene VLNVerse/VLNTube kujiale split
(238 train / 15 held-out episodes). Because the held-out split contains
only 15 episodes, this ablation is treated as a controlled preliminary
comparison (one episode = 6.7 pp of SR). Additional VLNVerse data will be
generated primarily to expand training and validation coverage; final
testing must remain held out, preferably at scene level, to avoid
train/test leakage.

## Table 1 — Offline held-out evaluation (Stage 1)

| Model | EMA decay | SR ↑ | OSR ↑ | NE ↓ | SPL ↑ | Collision Rate ↓ | Weight source | Decision |
|---|---:|---:|---:|---:|---:|---|---|---|
| MobileNetV2 baseline | none | **13.3** | **46.7** | **6.14** | **0.133** | N/A — offline evaluator; requires Isaac physics rollout | live model | **current baseline (kept)** |
| MobileNetV2 + EMA | 0.9999 | 20.0* | 20.0 | 6.05 | 0.200* | N/A — offline evaluator; requires Isaac physics rollout | EMA shadow | ablation only (degenerate*) |
| MobileNetV2 + EMA | 0.999 | 6.7 | 33.3 | 6.93 | 0.067 | N/A — offline evaluator; requires Isaac physics rollout | EMA shadow | ablation only |

\* Degenerate stationary-policy artifact: the 0.9999 shadow is undertrained
at this horizon (trajectory length 0.13 m); its nominal SR consists of
episodes whose start pose already lies inside the 3 m success radius.

**Decision (pre-registered rule):** neither EMA variant improves SR/SPL
without worsening NE → **the original MobileNetV2 baseline is kept**; EMA
is reported as a completed ablation. Interpretation: the 0.9999 failure is
a decay/horizon mismatch, not evidence that EMA fails; the 0.999 variant
achieved the best validation loss (0.23 vs 0.36) but this did not
translate to navigation metrics on the small split — EMA can be useful,
but the decay must match the number of training steps, and loss is an
imperfect proxy for SR.

## Table 2 — Isaac Sim physics smoke evaluation (Stage 2)

Collision Rate is not available in the offline VLN evaluator because that
evaluator does not simulate physical contact. It is therefore measured
separately from Isaac Sim physics rollouts using PhysX chassis-contact
events (wheel–floor contact excluded by construction). This Isaac
evaluation is a preliminary physics smoke test for Collision Rate and
trajectory consistency, not a full campaign-level benchmark.

| Model | Checkpoint | Episodes | SR ↑ | OSR ↑ | NE ↓ | SPL ↑ | Collision Rate ↓ | Total collisions | Coll/m | Notes |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| MobileNetV2 baseline | ablation_mnv2_baseline/best.pt (live) | 3 | 1.00† | 1.00† | 0.82 | 0.725 | **0.00 (measured)** | 0 | 0.0 | physics rollout |
| MobileNetV2 + EMA 0.999 | ablation_mnv2_ema0999/best.pt (EMA shadow) | 3 | 1.00† | 1.00† | 0.82 | 0.725 | **0.00 (measured)** | 0 | 0.0 | physics rollout |

† SR/OSR are trivially saturated in this smoke: all three routes are
shorter than the 3 m success radius. NE and Collision Rate are the
informative metrics here. The two checkpoints produce identical executed
trajectories because both saturate the 0.2 m/s safety clamp on straight
routes (raw intents differ: ~0.5 vs ~0.7 m/s) under weak yaw authority.

**Collision sensor positive control:** a deliberate collision episode
drove the chassis into the reception desk: 27 contact events logged
against `SM_ReceptionDesk_01a` from step 593 (and the emergency stop then
fired on the post-collision command anomaly). The measured zeros above are
therefore verified zeros, not absence of instrumentation.

**EfficientNet:** paused to avoid confounding EMA with backbone-capacity
changes (see appendix_efficientnet.md). **Next:** expand VLNVerse
training/validation data; resume EfficientNet after this controlled
baseline is reproducible; full campaign-level physics benchmark remains
future work.
