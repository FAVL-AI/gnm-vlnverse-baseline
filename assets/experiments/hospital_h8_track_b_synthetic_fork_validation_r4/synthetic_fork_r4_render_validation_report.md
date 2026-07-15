# H8-M Track-B SYNTHETIC_DIAGNOSTIC_ONLY Fork — Render-Scan Validation (Gates 1-7)

**Status: VALIDATION ONLY — R4 render-scan gates 1-7.** No drive-validation, no recording/recorded-mode, no trajectory collection, no leakage audit, no action-probe, no training, no promotion; no metric/threshold change. Free camera at the raised (~0.12 m) robot-eye mount, level horizon. `CL_BOUND_XY` unchanged.

> **SYNTHETIC_DIAGNOSTIC_ONLY.** This tests whether the *authored* junction satisfies the render-valid angular branch-choice requirements. It is not hospital, real-scene, benchmark, or SOTA evidence, and authorizes no training.

## Scene
- `synthetic_diagnostic_fork` — asset `/home/favl/robotics/gnm-vlnverse-baseline/assets/scenes/synthetic_diagnostic_fork/synthetic_diagnostic_fork.usda`
- scene_load_ok=True, prims=91, world_bbox=[-4.0, -4.0, -0.1, 4.0, 4.0, 2.8]
- Designed 4-way cross: branch A=N (blue/circle, STRAIGHT), branch B=W (green/triangle, TURN_LEFT_90); E=distractor (orange), S=approach (red). Divergence A-B = 90.0 deg.

## Gate results (1-7)
| gate | pass | detail |
|---|---|---|
| 1_scene_load | True | ref_authored=True prims=91 bbox=[-4.0, -4.0, -0.1, 4.0, 4.0, 2.8] |
| 2_render_validity | True | decision + goalA/goalB @ chosen standoff 2.0 m + center N/W all luma>=15.0, black<=0.5, non-empty; depth_present=True |
| 3_depth_openness | True | branch N depth=3.5 m, branch W depth=3.5 m (both >= 3.0) |
| 4_open_floor_guard | True | all-4 >= 4.0 m? False (guard passes when NOT open-floor); depths E/N/W/S=[3.5, 3.5, 3.5, 3.5] |
| 5_visual_verification | DONE — corridors dramatically distinct to a human, DINO still fails | Human contact-sheet inspection: the four corridors are wildly distinct by eye (blue-round w/ big sphere, orange-boxy w/ cube, green NARROWED w/ hanging cone, red-columned). Yet DINO 0.696 center / 0.703 goal-images >= 0.60 and WORSE than R2/R3. Confirms a metric-suitability problem (DINO keys on the shared corridor perspective/composition), not a scene-design failure; no override |
| 6_embedding_distinctness | False | DINO goal-image cosine: standoff1.5=0.698, standoff2.0=0.703, best=0.703 @ 2.0 m; center N-vs-W=0.696; threshold < 0.6 |
| 7_action_angle | True | branch A=N (STRAIGHT) vs B=W (TURN_LEFT_90): sep=90.0 deg (>= 30.0); different local actions |

- **Automated gates (1,2,3,4,6,7) all pass:** False.
- **Automated classification of the N-vs-W branch pair:** `RENDER_VALID_BUT_VISUALLY_WEAK` — branches not distinct (DINO 0.703 >= 0.6).
- **Gate 5 (mandatory visual/contact-sheet verification): DONE.** The four corridors are dramatically distinct to a human (blue-round / orange-boxy / green-narrow-pointed / red-columned), yet DINO scores 0.696 / 0.703 ≥ 0.60 — and worse than R2/R3. Confirms the failure is a metric-suitability issue (DINO keys on the shared corridor perspective/composition), not a scene-design failure; no override.

## Per-view depth / luma (center probe)
| view | luma | lower_black_frac | median_depth_m | open>=3m | intended cue |
|---|---|---|---|---|---|
| center E | 90.4 | 0.0024 | 3.5 | True | orange/square (distractor) |
| center N | 74.0 | 0.0044 | 3.5 | True | blue/circle (branch A STRAIGHT) |
| center W | 56.0 | 0.0019 | 3.5 | True | green/triangle (branch B TURN_LEFT_90) |
| center S | 122.8 | 0.0079 | 3.5 | True | red/cross (approach) |
| open_floor(all4>=4m) | False | | | | ns_open=True ew_open=True |

## Embedding distinctness
- DINO goal-image cosine (blue vs green): standoff 1.5 m = **0.698**, standoff 2.0 m = **0.703**; best = **0.703** @ 2.0 m (threshold < 0.6).
- DINO cosine(center N, center W) = **0.696**.

## Decision
**SYNTHETIC_FORK_RENDER_SCAN_FAILED — gate 6 still fails after R1–R4; STOP and treat this as a metric-suitability question (do NOT proceed to drive-validation, do NOT change the metric/threshold without review).**

- Geometry gates (1 scene-load, 2 render-validity @ chosen 2.0 m standoff, 3 depth-openness 3.5 m all-4, 4 open-floor guard, 7 action-angle 90°) all **PASS**.
- **Gate 6 (embedding distinctness) still FAILS.** The chosen render-valid standoff is 2.0 m (the 1.5 m West goal was underlit — luma < 15 — so it was correctly rejected rather than allowed to score a false low-similarity win).

### Methodology note — R1 → R4 comparison (does DINO < 0.60 suit this synthetic corridor family?)

| rev | change | center N-vs-W | goal images | gate 6 |
|---|---|---|---|---|
| R1 | flat colour + small centered marker | 0.79 | 0.734 | fail |
| R2 | distinct shape families (sign+prop+wall pattern) | **0.62** | **0.649** | fail (best so far) |
| R3 | branch-specific corridor shell + goal-camera pull-back | 0.654 | 0.689 | fail (worsened) |
| R4 | per-branch geometry + dominant foreground + narrowed West | 0.696 | 0.703 | fail (worsened) |

**The evidence is now decisive and consistent across four revisions:**
- Colour, decor, shape-family props, branch-specific corridor shells, per-branch corridor **geometry** (narrowed West), dominant **foreground objects**, and goal-camera **standoff** were all tried. **None reached DINO cosine < 0.60.**
- Distinctness did **not** improve monotonically with effort — it was **best at R2 (0.62)** and got **worse** as more per-branch structure was added (R3 0.654, R4 0.696). Adding a big central object + floor strip + reliefs to every arm gives them a **shared "decorated corridor with a central object" composition**, which DINO encodes similarly.
- By eye (gate-5, confirmed on the R4 contact sheet) the four corridors are **dramatically distinct** (blue-round / orange-boxy / green-narrow-pointed / red-columned). The human–DINO disagreement is large.

**Conclusion:** for this synthetic 4-way-cross corridor family, **DINO ViT-S/16 cosine < 0.60 appears to be an unsuitable / miscalibrated distinctness gate.** The metric is dominated by the shared corridor perspective/composition that every arm of a symmetric cross necessarily has, and it does not track the (obvious) human-perceived distinctness. This is a **metric-suitability finding, not a scene-design failure** — the scene design space for appearance/geometry has been substantially explored.

### Recommended decision (to propose — NOT executed; no metric change was made here)
1. **Calibrate the gate, don't move the goalpost.** Measure DINO cosine on **known-distinct real-scene goal pairs** (e.g. the hospital / warehouse views already rendered) and on **known-same** pairs, to see what "distinct" actually is for DINO on indoor corridors. If real distinct pairs also sit ~0.6–0.7, the < 0.60 absolute threshold is simply wrong for this domain and should be replaced with a **relative / calibrated** criterion.
2. **Consider a colour/semantic-sensitive encoder** (e.g. CLIP) or the **actual policy encoder** as the distinctness metric, since that is what a goal-conditioned policy would really use — a documented methodology decision, made with review.
3. Only if a calibrated metric still shows the branches as non-distinct should the scene be considered inadequate.

- Do not start training. Do not claim benchmark or real-scene evidence. Do not proceed to drive-validation. **No metric or threshold change was applied in R4** — this report only recommends the methodology decision for review.

## Gates intentionally NOT run
- drive-validation, recorded-mode, leakage audit, action-probe, training — deferred to a later, separately-approved stage after gates 1-7 pass and are reviewed.

## Claim boundary
- SYNTHETIC_DIAGNOSTIC_ONLY; R4 validation-only render analysis; no drive validation; no recording; no trajectory collection; no training; no promotion; no metric/threshold change; not hospital evidence; not real-scene evidence; not benchmark evidence; not full goal-conditioned ImageNav evidence; not SOTA; no autonomy claim; no training authorization; `CL_BOUND_XY` unchanged.
- One cross is not enough for a leakage-safe train/val/test split; future training requires a family of at least 6 disjoint junction instances.

## Artifacts
`assets/experiments/hospital_h8_track_b_synthetic_fork_validation/`: `synthetic_fork_render_validation_manifest.json`, `synthetic_fork_render_validation_table.csv`, `synthetic_fork_render_validation_report.md`, `synthetic_fork_visual_similarity_matrix.{csv,md}`, `contact_sheets/`, `render_metadata/`. Harness: `scripts/gnm/h8_track_b_synthetic_fork_render.py` (isaac), `scripts/gnm/h8_track_b_synthetic_fork_analyze.py` (this). Raw .npy in scratchpad (not committed).
