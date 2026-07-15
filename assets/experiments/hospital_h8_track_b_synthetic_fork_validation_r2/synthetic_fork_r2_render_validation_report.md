# H8-M Track-B SYNTHETIC_DIAGNOSTIC_ONLY Fork — Render-Scan Validation (Gates 1-7)

**Status: VALIDATION ONLY — R2 render-scan gates 1-7.** No drive-validation, no recording/recorded-mode, no trajectory collection, no leakage audit, no action-probe, no training, no promotion. Free camera at the raised (~0.12 m) robot-eye mount, level horizon. `CL_BOUND_XY` unchanged.

> **SYNTHETIC_DIAGNOSTIC_ONLY.** This tests whether the *authored* junction satisfies the render-valid angular branch-choice requirements. It is not hospital, real-scene, benchmark, or SOTA evidence, and authorizes no training.

## Scene
- `synthetic_diagnostic_fork` — asset `/home/favl/robotics/gnm-vlnverse-baseline/assets/scenes/synthetic_diagnostic_fork/synthetic_diagnostic_fork.usda`
- scene_load_ok=True, prims=55, world_bbox=[-4.0, -4.0, -0.1, 4.0, 4.0, 2.5]
- Designed 4-way cross: branch A=N (blue/circle, STRAIGHT), branch B=W (green/triangle, TURN_LEFT_90); E=distractor (orange), S=approach (red). Divergence A-B = 90.0 deg.

## Gate results (1-7)
| gate | pass | detail |
|---|---|---|
| 1_scene_load | True | ref_authored=True prims=55 bbox=[-4.0, -4.0, -0.1, 4.0, 4.0, 2.5] |
| 2_render_validity | True | decision/goalA/goalB + center N/W all luma>=15.0, black<=0.5, non-empty; depth_present=True |
| 3_depth_openness | True | branch N depth=3.5 m, branch W depth=3.5 m (both >= 3.0) |
| 4_open_floor_guard | True | all-4 >= 4.0 m? False (guard passes when NOT open-floor); depths E/N/W/S=[3.5, 3.5, 3.5, 3.5] |
| 5_visual_verification | DONE — improved, still confirms gate-6 fail | Human contact-sheet inspection complete: branches are now clearly distinct by shape family (N round: white disc + blue sphere; E boxy: square sign + crate; W pointed: yellow cone + cone prop; S cylindrical: bars + cylinder). Distinctness improved (center 0.79->0.62, goal images 0.734->0.649) BUT still >= 0.60: the CLOSE goal images look mostly at flat coloured wall (props/signs fall out of frame at 1.3 m) and every corridor shares an IDENTICAL gray shell (side walls, floor, ceiling) that dominates the embedding. Confirms the gate-6 failure; no override |
| 6_embedding_distinctness | False | DINO cosine(goalA_img,goalB_img)=0.649, cosine(centerN,centerW)=0.62; threshold < 0.6 |
| 7_action_angle | True | branch A=N (STRAIGHT) vs B=W (TURN_LEFT_90): sep=90.0 deg (>= 30.0); different local actions |

- **Automated gates (1,2,3,4,6,7) all pass:** False.
- **Automated classification of the N-vs-W branch pair:** `RENDER_VALID_BUT_VISUALLY_WEAK` — branches not distinct (DINO 0.649 >= 0.6).
- **Gate 5 (mandatory visual/contact-sheet verification): DONE.** Human inspection confirms the branches are now clearly distinct by shape family, and distinctness improved substantially (center N-vs-W 0.79 → **0.62**, goal images 0.734 → **0.649**). But it **still fails** the < 0.60 threshold, for two identifiable reasons visible in the contact sheets:
  1. **Close goal images are mostly flat wall.** `goalA_img`/`goalB_img` sit 1.3 m from the end wall, so the distinctive sign + prop fall largely out of frame and the image is dominated by the flat branch colour — the least distinctive view. (This is the higher/worse 0.649.)
  2. **Shared gray corridor shell.** All four arms use the same neutral side walls, floor, and ceiling opening; that shared structure dominates the DINO embedding of the center views (0.62).

### Required next revision (R3) before re-validation
- **Make the corridor shell branch-specific:** colour/pattern the **side walls and floor of each arm** to the branch identity (not just the end wall), so the whole field of view differs between branches — this attacks the 0.62 center-view similarity directly.
- **Fix the goal-image framing:** pull the goal-image cameras back (e.g. to ~2.0–2.5 m from the wall) or place the large sign/prop so the close goal view actually contains the distinctive structure, not flat colour.
- Keep the valid 4-way cross geometry, 90° A–B separation, depth-openness, open-floor/collinear guards, and `CL_BOUND_XY = 6.0` (all still pass). Re-run gates 1–7. Target: DINO cosine(branch A, branch B) `< 0.60` with margin.

## Per-view depth / luma (center probe)
| view | luma | lower_black_frac | median_depth_m | open>=3m | intended cue |
|---|---|---|---|---|---|
| center E | 138.5 | 0.0025 | 3.5 | True | orange/square (distractor) |
| center N | 137.0 | 0.0024 | 3.5 | True | blue/circle (branch A STRAIGHT) |
| center W | 121.9 | 0.0008 | 3.5 | True | green/triangle (branch B TURN_LEFT_90) |
| center S | 121.5 | 0.0024 | 3.5 | True | red/cross (approach) |
| open_floor(all4>=4m) | False | | | | ns_open=True ew_open=True |

## Embedding distinctness
- DINO cosine(goalA_img blue, goalB_img green) = **0.649** (threshold < 0.6).
- DINO cosine(center N, center W) = **0.62**.

## Decision
**SYNTHETIC_FORK_RENDER_SCAN_FAILED_REVISE_GEOMETRY_OR_MARKERS.**
- The render scan did NOT confirm a render-valid junction — **revise the synthetic scene geometry / visual markers before any drive-validation.** Do not proceed to training.
- Do not start training. Do not claim benchmark or real-scene evidence.

## Gates intentionally NOT run
- drive-validation, recorded-mode, leakage audit, action-probe, training — deferred to a later, separately-approved stage after gates 1-7 pass and are reviewed.

## Claim boundary
- SYNTHETIC_DIAGNOSTIC_ONLY; R2 validation-only render analysis; no drive validation; no recording; no trajectory collection; no training; not hospital evidence; not real-scene evidence; not benchmark evidence; not promotion; not full goal-conditioned ImageNav evidence; not SOTA; no autonomy claim; no training authorization; `CL_BOUND_XY` unchanged.
- One cross is not enough for a leakage-safe train/val/test split; future training requires a family of at least 6 disjoint junction instances.

## Artifacts
`assets/experiments/hospital_h8_track_b_synthetic_fork_validation/`: `synthetic_fork_render_validation_manifest.json`, `synthetic_fork_render_validation_table.csv`, `synthetic_fork_render_validation_report.md`, `synthetic_fork_visual_similarity_matrix.{csv,md}`, `contact_sheets/`, `render_metadata/`. Harness: `scripts/gnm/h8_track_b_synthetic_fork_render.py` (isaac), `scripts/gnm/h8_track_b_synthetic_fork_analyze.py` (this). Raw .npy in scratchpad (not committed).
