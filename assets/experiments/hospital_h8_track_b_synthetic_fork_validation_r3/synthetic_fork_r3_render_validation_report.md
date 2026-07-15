# H8-M Track-B SYNTHETIC_DIAGNOSTIC_ONLY Fork — Render-Scan Validation (Gates 1-7)

**Status: VALIDATION ONLY — R3 render-scan gates 1-7.** No drive-validation, no recording/recorded-mode, no trajectory collection, no leakage audit, no action-probe, no training, no promotion. Free camera at the raised (~0.12 m) robot-eye mount, level horizon. `CL_BOUND_XY` unchanged.

> **SYNTHETIC_DIAGNOSTIC_ONLY.** This tests whether the *authored* junction satisfies the render-valid angular branch-choice requirements. It is not hospital, real-scene, benchmark, or SOTA evidence, and authorizes no training.

## Scene
- `synthetic_diagnostic_fork` — asset `/home/favl/robotics/gnm-vlnverse-baseline/assets/scenes/synthetic_diagnostic_fork/synthetic_diagnostic_fork.usda`
- scene_load_ok=True, prims=83, world_bbox=[-4.0, -4.0, -0.1, 4.0, 4.0, 2.5]
- Designed 4-way cross: branch A=N (blue/circle, STRAIGHT), branch B=W (green/triangle, TURN_LEFT_90); E=distractor (orange), S=approach (red). Divergence A-B = 90.0 deg.

## Gate results (1-7)
| gate | pass | detail |
|---|---|---|
| 1_scene_load | True | ref_authored=True prims=83 bbox=[-4.0, -4.0, -0.1, 4.0, 4.0, 2.5] |
| 2_render_validity | True | decision/goalA/goalB + center N/W all luma>=15.0, black<=0.5, non-empty; depth_present=True |
| 3_depth_openness | True | branch N depth=3.5 m, branch W depth=3.5 m (both >= 3.0) |
| 4_open_floor_guard | True | all-4 >= 4.0 m? False (guard passes when NOT open-floor); depths E/N/W/S=[3.5, 3.5, 3.5, 3.5] |
| 5_visual_verification | DONE — branches obviously distinct to a human, DINO still fails | Human contact-sheet inspection: the four corridors are now dramatically distinct by eye (all-blue round, all-orange boxy, all-green cone-lined, all-red barred — full-shell colour + shape-family reliefs). Yet DINO still scores 0.654 (center N-vs-W) / 0.689 (goal images) >= 0.60 because all arms share the SAME corridor perspective geometry, to which DINO is far more sensitive than colour/decor. Confirms the failure is an embedding-metric x shared-geometry effect, NOT camera framing or shell colour; no override |
| 6_embedding_distinctness | False | DINO cosine(goalA_img,goalB_img)=0.689, cosine(centerN,centerW)=0.654; threshold < 0.6 |
| 7_action_angle | True | branch A=N (STRAIGHT) vs B=W (TURN_LEFT_90): sep=90.0 deg (>= 30.0); different local actions |

- **Automated gates (1,2,3,4,6,7) all pass:** False.
- **Automated classification of the N-vs-W branch pair:** `RENDER_VALID_BUT_VISUALLY_WEAK` — branches not distinct (DINO 0.689 >= 0.6).
- **Gate 5 (mandatory visual/contact-sheet verification): DONE.** The four corridors are dramatically distinct to a human (full-shell colour + shape-family reliefs), yet DINO still scores 0.654 / 0.689 >= 0.60 — the shared corridor perspective geometry dominates the embedding. Confirms the gate-6 failure; no override.

## Per-view depth / luma (center probe)
| view | luma | lower_black_frac | median_depth_m | open>=3m | intended cue |
|---|---|---|---|---|---|
| center E | 123.7 | 0.0024 | 3.5 | True | orange/square (distractor) |
| center N | 121.2 | 0.0026 | 3.5 | True | blue/circle (branch A STRAIGHT) |
| center W | 105.7 | 0.0009 | 3.5 | True | green/triangle (branch B TURN_LEFT_90) |
| center S | 95.9 | 0.0025 | 3.5 | True | red/cross (approach) |
| open_floor(all4>=4m) | False | | | | ns_open=True ew_open=True |

## Embedding distinctness
- DINO cosine(goalA_img blue, goalB_img green) = **0.689** (threshold < 0.6).
- DINO cosine(center N, center W) = **0.654**.

## Decision
**SYNTHETIC_FORK_RENDER_SCAN_FAILED_REVISE_GEOMETRY_OR_MARKERS — gate 6 still fails; do NOT proceed to drive-validation.**

- Geometry gates (1 scene-load, 2 render-validity, 3 depth-openness 3.5 m all-4, 4 open-floor guard, 7 action-angle 90°) all **PASS**, as in R1/R2.
- **Gate 6 (embedding distinctness) still FAILS, and did NOT improve — it slightly worsened.** DINO cosine progression across revisions:
  - center N-vs-W: R1 **0.79** → R2 **0.62** → R3 **0.654**.
  - goal images: R1 **0.734** → R2 **0.649** → R3 **0.689**.

### Diagnosis (per decision rule: camera framing vs corridor-shell similarity vs embedding threshold)
- **NOT camera framing.** Pulling the goal cameras back to ~2.3 m standoff **worsened** the goal-image score (0.649 → 0.689): from further back the goal image contains **more** of the shared receding-corridor geometry. Framing is not the lever.
- **NOT (fixable-by-)colour / decor of the shell.** R3 gave each arm a fully branch-specific shell — tinted side walls, a branch-colour floor strip, and shape-family reliefs — so the corridors are **obviously different to a human** (all-blue round vs all-green cone-lined vs all-orange boxy vs all-red barred). Yet the center score also worsened (0.62 → 0.654). Colour/decor is not the binding constraint.
- **The binding constraint is the embedding metric × shared corridor GEOMETRY.** DINO ViT-S/16 is strongly structure/perspective-focused and largely colour-invariant. All four arms share the **identical corridor perspective geometry** (rectangular tunnel receding to a flat end wall, same vanishing-point structure); DINO encodes that shared 3-D structure and floors the cosine at ~0.65 **regardless of colour, texture, decor, or camera standoff**. For an idealised **symmetric** cross with identical per-arm geometry, DINO cosine < 0.60 appears **effectively unreachable by appearance changes alone**.

### Recommended R4 options (to propose, NOT executed — held for review)
1. **Differentiate the corridor GEOMETRY per arm** (e.g. different arm length / width / height / cross-section, or a distinct large architectural feature that changes the silhouette), while keeping a cardinal ≥ 30° branch choice, depth-openness, and `CL_BOUND_XY = 6.0` — attack the shared perspective structure directly.
2. **Add large, close, branch-specific FOREGROUND geometry** that dominates the goal frame (occupies most pixels) so the shared corridor structure is no longer the dominant signal — while avoiding blocking the drive path or the depth-openness reading.
3. **Reconsider the distinctness metric / threshold.** DINO cosine on symmetric corridors has a high floor (~0.65); a colour/semantic-sensitive encoder (e.g. CLIP) or a task-relevant, calibrated distinctness measure/threshold may be the correct gate — this would be a documented methodology decision, not a scene hack.
- Do not start training. Do not claim benchmark or real-scene evidence. Do not proceed to drive-validation until gate 6 passes and is reviewed.

## Gates intentionally NOT run
- drive-validation, recorded-mode, leakage audit, action-probe, training — deferred to a later, separately-approved stage after gates 1-7 pass and are reviewed.

## Claim boundary
- SYNTHETIC_DIAGNOSTIC_ONLY; R3 validation-only render analysis; no drive validation; no recording; no trajectory collection; no training; no promotion; not hospital evidence; not real-scene evidence; not benchmark evidence; not full goal-conditioned ImageNav evidence; not SOTA; no autonomy claim; no training authorization; `CL_BOUND_XY` unchanged.
- One cross is not enough for a leakage-safe train/val/test split; future training requires a family of at least 6 disjoint junction instances.

## Artifacts
`assets/experiments/hospital_h8_track_b_synthetic_fork_validation/`: `synthetic_fork_render_validation_manifest.json`, `synthetic_fork_render_validation_table.csv`, `synthetic_fork_render_validation_report.md`, `synthetic_fork_visual_similarity_matrix.{csv,md}`, `contact_sheets/`, `render_metadata/`. Harness: `scripts/gnm/h8_track_b_synthetic_fork_render.py` (isaac), `scripts/gnm/h8_track_b_synthetic_fork_analyze.py` (this). Raw .npy in scratchpad (not committed).
