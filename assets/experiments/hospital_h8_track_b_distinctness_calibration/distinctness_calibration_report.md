# H8 Track-B — Distinctness-Metric Calibration Report (METHODOLOGY ONLY)

**Status: methodology evidence only.** No drive-validation, no recording, no trajectory collection, no training, no promotion, no benchmark evidence, no real-scene performance claim, no SOTA, no autonomy claim. **The DINO threshold and the operational gate metric were NOT changed.** `CL_BOUND_XY` unchanged. Governed by `docs/research/H8_TRACK_B_DISTINCTNESS_METRIC_CALIBRATION_PLAN.md`.

## Question
Is the absolute `DINO cosine < 0.60` gate valid for corridor-style ImageNav goal distinctness, or should it be recalibrated or replaced? Evidence: labelled SAME / DISTINCT / HARD_NEGATIVE pairs from committed renders (25 pairs, 0 skipped for missing frames).

## Per-label similarity distributions
| metric | SAME | DISTINCT | HARD_NEGATIVE |
|---|---|---|---|
| dino_cos | n=9 mean=0.7938 median=0.808 range=[0.5878,1.0] std=0.1331 | n=10 mean=0.5748 median=0.6426 range=[0.2552,0.7956] std=0.1706 | n=6 mean=0.5916 median=0.6256 range=[0.3719,0.6786] std=0.1056 |
| clip_cos | n=9 mean=0.8058 median=0.7774 range=[0.5779,1.0] std=0.1269 | n=10 mean=0.6431 median=0.7082 range=[0.2619,0.9341] std=0.195 | n=6 mean=0.7956 median=0.856 range=[0.5245,0.8843] std=0.1263 |
| ahash_sim | n=9 mean=0.7674 median=0.7344 range=[0.5156,1.0] std=0.156 | n=10 mean=0.8125 median=0.8672 range=[0.625,0.9688] std=0.1196 | n=6 mean=0.5156 median=0.4688 range=[0.375,0.7656] std=0.1338 |
| ssim | n=9 mean=0.689 median=0.6954 range=[0.4585,1.0] std=0.1736 | n=10 mean=0.601 median=0.6665 range=[0.1059,0.9481] std=0.2505 | n=6 mean=0.3522 median=0.3718 range=[0.2197,0.4638] std=0.1045 |

## Separation analysis (does the metric tell SAME from DISTINCT?) — ALL pairs pooled
| metric | SAME mean | DISTINCT mean | gap | ranges overlap? | clean threshold | hard-neg note |
|---|---|---|---|---|---|---|
| dino_cos | 0.7938 | 0.5748 | 0.219 | True | None | HARD_NEG scores toward DISTINCT (metric treats look-alikes as different) - good |
| clip_cos | 0.8058 | 0.6431 | 0.1627 | True | None | HARD_NEG merges with SAME (metric over-similar on look-alikes) |
| ahash_sim | 0.7674 | 0.8125 | -0.0451 | True | None | HARD_NEG scores toward DISTINCT (metric treats look-alikes as different) - good |
| ssim | 0.689 | 0.601 | 0.088 | True | None | HARD_NEG scores toward DISTINCT (metric treats look-alikes as different) - good |

## Separation analysis SPLIT BY SOURCE FAMILY (the decisive view)
The pooled view mixes two regimes. Split apart, the real indoor scans and the synthetic symmetric 4-way cross behave oppositely — this is the key finding.

| metric | family | SAME (n, mean, range) | DISTINCT (n, mean, range) | ranges overlap? | clean threshold |
|---|---|---|---|---|---|
| dino_cos | real | n=2 mean=0.8751 median=0.8751 range=[0.8327,0.9175] std=0.0424 | n=4 mean=0.4223 median=0.3749 range=[0.2552,0.6841] std=0.1699 | False | 0.7584 |
| dino_cos | synthetic | n=7 mean=0.7706 median=0.7566 range=[0.5878,1.0] std=0.1408 | n=6 mean=0.6765 median=0.6622 range=[0.6163,0.7956] std=0.0586 | True | None |
| clip_cos | real | n=2 mean=0.9065 median=0.9065 range=[0.8948,0.9182] std=0.0117 | n=4 mean=0.5533 median=0.5086 range=[0.2619,0.9341] std=0.2773 | True | None |
| clip_cos | synthetic | n=7 mean=0.777 median=0.7524 range=[0.5779,1.0] std=0.1302 | n=6 mean=0.703 median=0.7129 range=[0.5891,0.7737] std=0.0558 | True | None |

**Reading it:** for **DINO on real hospital pairs**, known-distinct goals score far LOWER (more distinct) than known-same goals with a clean gap — DINO works on real indoor scenes. For **DINO on the synthetic cross**, known-same and known-distinct ranges OVERLAP and even INVERT (a genuinely-distinct N-vs-W pair scores higher/less-distinct than a same-branch near/far pair), because every arm of a symmetric cross shares the same corridor perspective/composition. The R1-R4 'failure' is therefore driven by the symmetric-cross geometry as much as by the metric; and separately, the absolute 0.60 constant is miscalibrated even for real scenes (real distinct pairs reach ~0.68, above 0.60).

## The current DINO < 0.60 gate on these pairs
- False NEGATIVES (DISTINCT pairs the gate misses, DINO >= 0.60): **7** (syn_R1_NvsW, syn_R2_NvsW, syn_R3_NvsW, syn_R4_NvsW, syn_R4_NvsE, syn_R4_WvsS, hosp_fork_vs_sidecorr).
- False POSITIVES (SAME pairs wrongly flagged distinct, DINO < 0.60): **1** (syn_R2_northSame).
- Hard negatives not flagged distinct (DINO >= 0.60): **3**.

## Recommendation (outcome A-E) — proposal only, NOT implemented
**Outcome A+E.** A + E (evidence-driven). On REAL hospital pairs DINO cosine separates SAME from DISTINCT cleanly (real DISTINCT max 0.6841 < real SAME min 0.8327; clean threshold ~0.7584), so DINO is usable on real indoor scenes — but the current absolute 0.60 gate is MISCALIBRATED (a real distinct pair at 0.6841 would be missed by < 0.60). On the SYNTHETIC symmetric 4-way cross DINO does NOT separate (same/distinct ranges overlap and invert) because every arm shares an identical corridor perspective/composition — a pathological case for a global composition embedding, not a general metric failure. RECOMMEND: (A) recalibrate the DINO threshold from real-scene separation (~0.7584, with margin) rather than the arbitrary 0.60; and (E) treat SYNTHETIC-fork distinctness as ADVISORY ONLY and gate goal-conditioning with a task-level ACTION-PROBE (does conditioning on goal A vs B change the decision-frame action?) after render/drive validation. Do NOT use synthetic symmetric-cross DINO scores as a pass/fail gate.

Notes:
- **CLIP** was computed via a timm CLIP-pretrained ViT-B/16 (LAION-2B checkpoint; standalone open_clip/clip packages absent). Available and included above.
- **CLIP does not rescue the gate on this set.** CLIP's SAME vs DISTINCT ranges OVERLAP for both families (synthetic: SAME mean 0.777 ~= DISTINCT mean 0.703, no clean threshold; real: SAME 0.8948-0.9182 overlaps DISTINCT 0.2619-0.9341). Switching to CLIP does NOT produce a clean separation where DINO fails — CLIP separates SAME/DISTINCT less well than DINO here, so it is not a fix for the symmetric-cross gate.
- **Policy-encoder** embedding is DEFERRED (loading a GNM checkpoint is out of scope without approval); recorded as N/A. If chosen as a candidate metric, run it under a separate approved step.
- aHash / SSIM are secondary diagnostics only, never a gate.
- The recommendation is data-driven from the pairs above; it is a proposal for review, and no threshold or metric change is applied here.

## Decision rule applied
- If DINO separates SAME vs DISTINCT with margin -> propose a calibrated threshold (A).
- If DINO does not separate -> reject DINO as the primary gate.
- If CLIP / policy-encoder separates better -> recommend it with evidence (B/C).
- If no embedding separates cleanly -> contact-sheet verification + task-level action-probe as the primary next gate (D/E).

## Claim boundary
Methodology evidence only. No drive validation, no recording, no training, no benchmark evidence, no real-scene performance claim, no promotion, no autonomy claim. `CL_BOUND_XY` unchanged. No DINO threshold or gate-metric change was made; recommendation is held for review.

## Artifacts
`assets/experiments/hospital_h8_track_b_distinctness_calibration/`: `distinctness_pair_manifest.json`, `distinctness_metric_results.{csv,md}`, `distinctness_distribution_summary.json`, `distinctness_false_positive_negative_table.md`, `distinctness_calibration_report.md`, `contact_sheets/`. Script: `scripts/gnm/h8_track_b_distinctness_calibration.py`.
