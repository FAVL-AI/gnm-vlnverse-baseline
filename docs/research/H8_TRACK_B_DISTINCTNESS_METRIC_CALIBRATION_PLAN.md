# H8 Track-B — Distinctness-Metric Calibration Plan (PLAN ONLY)

**Status: PLAN ONLY.** This document decides *how* to decide whether the gate-6 distinctness metric
is appropriate. It authorises **nothing**: no threshold change, no metric switch, no drive-validation,
no recording, no trajectory collection, no training, no promotion, no push, no tag, no 20/5/10, no
closed-loop testing. `CL_BOUND_XY` unchanged. SYNTHETIC_DIAGNOSTIC_ONLY context — not hospital /
real-scene / benchmark / SOTA evidence.

> **Framing.** R1–R4 show the synthetic-fork geometry is valid, but the absolute `DINO cosine < 0.60`
> distinctness gate is probably miscalibrated for symmetric corridor scenes. The next step is **not**
> training and **not** threshold-moving; it is a small calibration study comparing DINO, CLIP, and
> possibly the policy encoder on labelled same/distinct goal pairs.

## 1. Why calibration is needed

Gate 6 (goal-branch embedding distinctness) has failed at every synthetic-fork revision, while the
branches became *more* human-distinct:

- **R1** (`be6ba04`) — branch differences were mostly **hue + a small centered marker**. DINO center
  N-vs-W **0.79**, goal images **0.734**. Fail.
- **R2** (`6930b65`) — distinct **shape families** (sign + prop + wall pattern) per branch. Improved to
  center **0.62** / goal **0.649** — the best of all revisions — but still ≥ 0.60. Fail.
- **R3** (`201f91b`) — branch-specific **corridor shell** (tinted side walls + floor strips + reliefs)
  + goal-camera pull-back. **Worsened** to center **0.654** / goal **0.689**. Fail.
- **R4** (`f936c18`) — per-branch **geometry** (narrowed West corridor) + **dominant foreground
  objects** (N sphere / W cone / E cube / S columns). **Worsened again** to center **0.696** / goal
  **0.703**. Fail.

Human-visible branch distinction improved dramatically (by eye the R4 corridors are blue-round /
orange-boxy / green-narrow-pointed / red-columned), yet DINO cosine **rose** from 0.62 (R2) to 0.70
(R4). Distinctness did not track effort and was non-monotone. **Therefore the issue is most likely
metric calibration, not (only) scene design** — DINO ViT-S/16 appears dominated by the shared corridor
perspective/composition that any symmetric 4-way cross necessarily has.

Full progression (lower = more distinct; gate wants < 0.60):

| rev | center N-vs-W | goal images |
|---|---|---|
| R1 | 0.79 | 0.734 |
| R2 | **0.62** | **0.649** |
| R3 | 0.654 | 0.689 |
| R4 | 0.696 | 0.703 |

## 2. What must NOT happen

- **No silent threshold change.** The `< 0.60` value is not to be edited to manufacture a pass.
- **No metric switch without evidence.** DINO is not replaced until a calibration study justifies it.
- **No training before the gate is justified.** Gate 6 must be defensible first.
- **No benchmark claim.** No leaderboard / SOTA framing from this work.
- **No real-scene claim from synthetic data.** Synthetic-fork results never stand in for hospital or
  real-world performance.
- `CL_BOUND_XY` unchanged; no drive/record/collect/promote/push/tag/20-5-10/closed-loop.

## 3. Calibration dataset (small, labelled goal-image pairs)

Assemble a small labelled set of goal-view image pairs, each tagged `same` / `distinct` / `hard_neg`,
with a source tag (`synthetic_r*`, `hospital`, `warehouse`). Reuse already-rendered frames where
possible — **no new drive/record/collection**; free-camera renders only if a pair is missing.

- **known-same pairs** — same branch, adjacent frames / small viewpoint jitter, same corridor, same
  goal object (should score HIGH similarity). Source: within-branch frames of the synthetic fork and
  of the hospital/warehouse scans.
- **known-distinct pairs** — different branch goals, different room/zone goals, different
  object/texture goals (should score LOW similarity). Source: synthetic N-vs-W / N-vs-E, and
  cross-zone hospital pairs.
- **hard-negative pairs** — visually similar but semantically different corridor goals (e.g. two
  different straight corridors that look alike; the warehouse straight-aisle ends). These probe
  whether the metric over-merges look-alikes.
- **synthetic fork R1–R4 pairs** — the exact N-vs-W goal pairs already rendered (0.79 / 0.62 / 0.654 /
  0.696), as in-family reference points.
- **real render pairs from hospital / warehouse scans** where available (from the committed Track-A/
  Track-B render evidence), to anchor "what distinct looks like" for DINO on real indoor corridors.

Target size: ~15–30 pairs per label class — enough to see distribution overlap, small enough to
hand-verify every pair with a contact sheet. Record each pair's images, labels, and source in a small
manifest; **no cross-split leakage concerns yet** (this is metric calibration, not training data).

## 4. Metrics to compare (per pair)

- **DINO ViT-S/16 cosine** (the incumbent gate metric; `timm vit_small_patch16_224.dino`).
- **CLIP image-embedding cosine** — if a CLIP model is available in `gnm_train`; more colour/semantic
  sensitive than DINO.
- **the actual GNM / policy visual encoder embedding cosine** — if the policy's own encoder is
  loadable; this is what a goal-conditioned policy would really "see", so it is the most task-relevant
  metric.
- **aHash / SSIM** — secondary diagnostics only (already known to false-positive on texture; not a
  gate).
- **optional relative ranking score** — per anchor, `mean(same-pair similarity) − mean(distinct-pair
  similarity)`; a positive, well-separated gap is what a usable metric must produce.

## 5. Calibration method

1. Compute each metric for every labelled pair.
2. For each metric, plot / tabulate the **distributions** of `same` vs `distinct` (and where
   `hard_neg` falls).
3. Report the **overlap** between the same and distinct distributions.
4. If the two distributions **separate**, choose the threshold from the observed separation (e.g. a
   value in the gap, or an ROC-optimal point), with documented margin.
5. If the two distributions **do not separate**, **reject that metric** for this gate (it cannot tell
   same from distinct on corridor goals).
6. **Prefer a relative / calibrated threshold** (derived from same-vs-distinct separation) over an
   arbitrary absolute constant.
7. Document **false positives and false negatives** with contact sheets (pairs the metric mislabels
   relative to human judgement).

## 6. Acceptance rule (a metric may back the gate only if ALL hold)

- **known-same pairs score consistently higher** similarity than **known-distinct pairs** (clear
  separation, not just on average).
- **hard negatives are flagged** (the metric does not silently merge look-alike-but-different goals).
- the chosen **threshold has margin** (not sitting on top of the overlap).
- **contact-sheet verification agrees** with the metric on the labelled pairs.
- the decision **does not depend on one cherry-picked pair** (robust to leaving any single pair out).

## 7. Outcome options (choose after the study; each needs review)

- **A. Keep DINO, recalibrate the threshold** — if DINO separates same/distinct but the true boundary
  is (say) ~0.72 rather than 0.60.
- **B. Use CLIP instead** — if CLIP separates same/distinct cleanly where DINO does not.
- **C. Use policy-encoder embeddings** — if the GNM/policy encoder is the most faithful and separates
  well (most task-relevant).
- **D. Combined rule** — embedding distinctness **plus** mandatory contact-sheet verification (the
  metric advises; the human gate confirms).
- **E. Embedding as advisory only** — treat any embedding distinctness as advisory and require a
  **task-level action-probe** (does conditioning on goal A vs goal B change the decision-frame action?)
  *after* render- and drive-validation, as the real evidence of goal-conditioning.

## 8. Claim boundary

- This calibration work is **methodology evidence only**.
- **No model training authorization.**
- **No drive-validation authorization.**
- **No benchmark evidence.**
- **No real-scene evidence** (synthetic-fork pairs never stand in for hospital/real-world).
- **No SOTA.**
- **No promotion**; incumbent retained; `DIAGNOSTIC_ONLY_NOT_PROMOTED`.
- **No autonomy claim.**
- `CL_BOUND_XY` unchanged. Nothing here permits a threshold or metric change; those are decided only
  after the study, under review.
