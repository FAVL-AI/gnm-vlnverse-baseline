# H8-M Track-B SYNTHETIC_DIAGNOSTIC_ONLY Fork — Render-Scan Validation (Gates 1-7)

**Status: VALIDATION ONLY — render-scan gates 1-7.** No drive-validation, no recording/recorded-mode, no trajectory collection, no leakage audit, no action-probe, no training, no promotion. Free camera at the raised (~0.12 m) robot-eye mount, level horizon. `CL_BOUND_XY` unchanged.

> **SYNTHETIC_DIAGNOSTIC_ONLY.** This tests whether the *authored* junction satisfies the render-valid angular branch-choice requirements. It is not hospital, real-scene, benchmark, or SOTA evidence, and authorizes no training.

## Scene
- `synthetic_diagnostic_fork` — asset `/home/favl/robotics/gnm-vlnverse-baseline/assets/scenes/synthetic_diagnostic_fork/synthetic_diagnostic_fork.usda`
- scene_load_ok=True, prims=34, world_bbox=[-4.0, -4.0, -0.1, 4.0, 4.0, 2.5]
- Designed 4-way cross: branch A=N (blue/circle, STRAIGHT), branch B=W (green/triangle, TURN_LEFT_90); E=distractor (orange), S=approach (red). Divergence A-B = 90.0 deg.

## Gate results (1-7)
| gate | pass | detail |
|---|---|---|
| 1_scene_load | True | ref_authored=True prims=34 bbox=[-4.0, -4.0, -0.1, 4.0, 4.0, 2.5] |
| 2_render_validity | True | decision/goalA/goalB + center N/W all luma>=15.0, black<=0.5, non-empty; depth_present=True |
| 3_depth_openness | True | branch N depth=3.5 m, branch W depth=3.5 m (both >= 3.0) |
| 4_open_floor_guard | True | all-4 >= 4.0 m? False (guard passes when NOT open-floor); depths E/N/W/S=[3.5, 3.5, 3.5, 3.5] |
| 5_visual_verification | DONE — CONFIRMS FAILURE | Human contact-sheet inspection complete: genuine walled 4-way cross geometry (four bounded corridors with distinct colored end walls; NOT open-floor / collinear / wall-only), BUT all four corridors are structurally identical (same gray side walls, floor, lighting, and a small centered marker), differing only in end-wall hue + marker shape → this CONFIRMS the gate-6 embedding-distinctness failure; NO RENDER_VALID_JUNCTION override |
| 6_embedding_distinctness | False | DINO cosine(goalA_img,goalB_img)=0.734, cosine(centerN,centerW)=0.79; threshold < 0.6 |
| 7_action_angle | True | branch A=N (STRAIGHT) vs B=W (TURN_LEFT_90): sep=90.0 deg (>= 30.0); different local actions |

- **Automated gates (1,2,3,4,6,7) all pass:** False.
- **Automated classification of the N-vs-W branch pair:** `RENDER_VALID_BUT_VISUALLY_WEAK` — branches not distinct (DINO 0.734 >= 0.6).
- **Gate 5 (mandatory visual/contact-sheet verification): DONE.** Human inspection of `contact_sheets/` confirms a genuine walled 4-way cross (N blue/sphere, E orange/square, W green/triangle, S red/cylinder — four bounded corridors, depth 3.5 m each). However, the four corridors are **structurally identical** — same gray side walls, floor, lighting, and a small centered marker — differing **only in end-wall hue and marker shape**. DINO ViT-S/16 is structure-focused and largely colour-invariant, so it scores the branch pair 0.734 (goal images) and 0.79 (center N vs W): it effectively sees the same corridor four times. The visual check therefore **confirms** the gate-6 failure; it does **not** override it.

## Per-view depth / luma (center probe)
| view | luma | lower_black_frac | median_depth_m | open>=3m | intended cue |
|---|---|---|---|---|---|
| center E | 139.7 | 0.0 | 3.5 | True | orange/square (distractor) |
| center N | 139.1 | 0.0 | 3.5 | True | blue/circle (branch A STRAIGHT) |
| center W | 125.4 | 0.0 | 3.5 | True | green/triangle (branch B TURN_LEFT_90) |
| center S | 127.5 | 0.0 | 3.5 | True | red/cross (approach) |
| open_floor(all4>=4m) | False | | | | ns_open=True ew_open=True |

## Embedding distinctness
- DINO cosine(goalA_img blue, goalB_img green) = **0.734** (threshold < 0.6).
- DINO cosine(center N, center W) = **0.79**.

## Decision
**SYNTHETIC_FORK_RENDER_SCAN_FAILED_REVISE_GEOMETRY_OR_MARKERS.**
- The render scan did NOT confirm a render-valid junction — **revise the synthetic scene geometry / visual markers before any drive-validation.** Do not proceed to training.
- Do not start training. Do not claim benchmark or real-scene evidence.

### Required revision before re-validation (gate-6 fix)
The geometry passes; the **visual markers do not**. Colour + a small centered marker is not enough
for a structure-focused, largely colour-invariant embedding (DINO) — the four corridors are the same
scene recoloured. To pass gate 6, make each branch **structurally/texturally distinct**, e.g.:
- full-wall branch-specific **textures/patterns** (not a flat hue), covering the end wall and ideally
  the side walls of each arm;
- **distinct props/geometry** down each corridor (different objects, different corridor width/length);
- **large branch signage / floor markings** that fill much of the view rather than one small marker;
- optionally per-branch lighting tint.
Re-run gates 1-7 after the revision. Target: DINO cosine(branch A, branch B) `< 0.60` with margin,
while keeping the depth-openness, open-floor, collinear, and action-angle gates (which already pass).

## Gates intentionally NOT run
- drive-validation, recorded-mode, leakage audit, action-probe, training — deferred to a later, separately-approved stage after gates 1-7 pass and are reviewed.

## Claim boundary
- SYNTHETIC_DIAGNOSTIC_ONLY; validation-only render analysis; no drive validation; no recording; no trajectory collection; no training; not hospital evidence; not real-scene evidence; not benchmark evidence; not promotion; not full goal-conditioned ImageNav evidence; not SOTA; no autonomy claim; no training authorization; `CL_BOUND_XY` unchanged.
- One cross is not enough for a leakage-safe train/val/test split; future training requires a family of at least 6 disjoint junction instances.

## Artifacts
`assets/experiments/hospital_h8_track_b_synthetic_fork_validation/`: `synthetic_fork_render_validation_manifest.json`, `synthetic_fork_render_validation_table.csv`, `synthetic_fork_render_validation_report.md`, `synthetic_fork_visual_similarity_matrix.{csv,md}`, `contact_sheets/`, `render_metadata/`. Harness: `scripts/gnm/h8_track_b_synthetic_fork_render.py` (isaac), `scripts/gnm/h8_track_b_synthetic_fork_analyze.py` (this). Raw .npy in scratchpad (not committed).
