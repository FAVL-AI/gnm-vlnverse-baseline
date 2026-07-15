# H8 Track-B — Synthetic Diagnostic Fork R4 RE-ASSESSMENT (under implemented Outcome A + E)

**Status: VALIDATION / ANALYSIS ONLY — `SYNTHETIC_DIAGNOSTIC_ONLY`.** This re-assessment reuses the already-committed R4 render evidence and re-classifies it under the implemented reviewed distinctness rule (`scripts/gnm/h8_distinctness_gate.py`), in which the DINO embedding is **advisory only** for a symmetric cross. **No re-render, no drive-validation, no recording, no trajectory collection, no training, no promotion.** `CL_BOUND_XY` unchanged.

- Reassessment of: `assets/experiments/hospital_h8_track_b_synthetic_fork_validation_r4/synthetic_fork_r4_render_validation_manifest.json`
- Re-rendered: **No** — the committed R4 render (same validated frames) is reused; only the classification rule changed.
- Advisory embedding rule provenance: Reviewed rule from docs/research/H8_TRACK_B_DISTINCTNESS_GATE_DECISION.md (Outcome A + E), calibrated on the labelled evidence in assets/experiments/hospital_h8_track_b_distinctness_calibration/; plan docs/research/H8_TRACK_B_DISTINCTNESS_METRIC_CALIBRATION_PLAN.md. Not benchmark evidence.

## Reviewed rule applied (Outcome A + E)
- **Synthetic fork (Outcome E):** DINO cosine is **advisory only** — logged, never a hard pass/fail. A DINO cosine above the former 0.60 (or above the calibrated 0.76) does **not** fail the synthetic fork.
- **Required render gates:** 1 scene-load, 2 render-validity, 3 depth-openness, 4 open-floor guard, 5 visual/contact-sheet verification, 7 action-angle separation.
- **Gate 6 (embedding distinctness):** reported as an advisory DINO cosine, not a pass/fail.

## Gate results (reassessed)
| gate | result | detail |
|---|---|---|
| 1_scene_load | PASS | ref_authored=True prims=91 bbox=[-4.0, -4.0, -0.1, 4.0, 4.0, 2.8] |
| 2_render_validity | PASS | decision + goalA/goalB @ chosen standoff 2.0 m + center N/W all luma>=15.0, black<=0.5, non-empt |
| 3_depth_openness | PASS | branch N depth=3.5 m, branch W depth=3.5 m (both >= 3.0) |
| 4_open_floor_guard | PASS | all-4 >= 4.0 m? False (guard passes when NOT open-floor); depths E/N/W/S=[3.5, 3.5, 3.5, 3.5] |
| 5_visual_verification | ADVISORY/ MANUAL | MANDATORY human/contact-sheet inspection — recorded separately after this script; automated verd |
| 6_embedding_distinctness | ADVISORY/ MANUAL (advisory) | ADVISORY ONLY (Outcome E) — NOT a synthetic pass/fail gate. DINO goal-image cosine 0.703 (stando |
| 7_action_angle | PASS | branch A=N (STRAIGHT) vs B=W (TURN_LEFT_90): sep=90.0 deg (>= 30.0); different local actions |

- **Required render gates (1,2,3,4,7) all pass:** True.
- **Gate 5 (mandatory visual/contact-sheet):** DONE_CONFIRMS_METRIC_SUITABILITY_ISSUE: corridors dramatically distinct to a human (blue-round/orange-boxy/green-narrowed-pointed/red-column
- **Gate 6 embedding distinctness:** ADVISORY — DINO goal-image cosine **0.703**, center N-vs-W **0.696** (advisory reference 0.76; former hard 0.6 superseded). **Logged as advisory, not used as a hard failure.**

## Distinctness (advisory) block
- scene type: SYNTHETIC_DIAGNOSTIC_ONLY
- embedding distinctness: ADVISORY (not gated)
- DINO cosine: 0.703
- reference threshold (not gated): 0.76
- distinctness verdict: ADVISORY
- provenance: Reviewed rule from docs/research/H8_TRACK_B_DISTINCTNESS_GATE_DECISION.md (Outcome A + E), calibrated on the labelled evidence in assets/experiments/hospital_h8_track_b_distinctness_calibration/; plan docs/research/H8_TRACK_B_DISTINCTNESS_METRIC_CALIBRATION_PLAN.md. Not benchmark evidence.
- claim boundary: methodology-consistent code only; not benchmark / real-scene / SOTA evidence; no promotion; no autonomy claim; no training authorization; no drive-validation authorized

## Geometry & action-angle (reused from committed R4, unchanged)
- Scene load: prims 91, bbox [-4.0, -4.0, -0.1, 4.0, 4.0, 2.8] — **valid**.
- Depth-openness: center depths {'E': 3.5, 'N': 3.5, 'W': 3.5, 'S': 3.5} m (branches N/W both >= 3.0 m) — **geometry gates remained valid**.
- Open-floor guard: open_floor=False (not an open hall) — **passes**.
- Action-angle: designed branch pair A=N vs B=W, **sep ~90.0 deg** (approximately 90 deg, >= 30) — **remained valid**.
- Contact-sheet verification: the committed R4 gate-5 record confirms the four corridors are **branch-specific / dramatically distinct to a human** (blue-round / orange-boxy / green-narrow-pointed / red-columned) — **confirms branch-specific synthetic geometry**. Sheets copied to `contact_sheets/` (2 files).

## Reassessed decision
- **Reassessed classification: `RENDER_VALID_JUNCTION`.**
- **Outcome: `SYNTHETIC_FORK_RENDER_VALID_PENDING_DRIVE_VALIDATION_HOLD_FOR_REVIEW`.**

Under the reviewed rule the required render gates (1,2,3,4,5,7) are satisfied — the only prior R4 failure was the now-advisory DINO gate (6). Per the decision rule, **STOP for review before drive validation.** Do **not** start drive validation, recorded-mode data collection, action-probe, or training.

## Next gate (not started; on approval only)
render reassessment passes -> **drive validation** -> recorded-mode data exists -> split/leakage audit passes -> action-probe readiness passes -> review approval. **Training remains blocked** until all of these pass.

## Claim boundary
`SYNTHETIC_DIAGNOSTIC_ONLY`; advisory embedding rule applied; no real-scene benchmark claim; no hospital claim; no full goal-conditioned ImageNav claim; no SOTA; no promotion (`DIAGNOSTIC_ONLY_NOT_PROMOTED`, incumbent retained); no autonomy claim; no drive validation; no recording; no trajectory collection; no training; `CL_BOUND_XY` unchanged; geometry gates remained valid; action-angle remained approximately 90 deg; contact-sheet verification confirms branch-specific synthetic geometry; DINO value logged as advisory, not used as a hard failure.

## Artifacts
`assets/experiments/hospital_h8_track_b_synthetic_fork_validation_r4_reassessed/`: `synthetic_fork_r4_reassessed_manifest.json`, `synthetic_fork_r4_reassessed_table.csv`, `synthetic_fork_r4_reassessed_report.md`, `synthetic_fork_r4_reassessed_visual_similarity_matrix.{csv,md}`, `contact_sheets/`. Rule: `scripts/gnm/h8_distinctness_gate.py`; reassessor: `scripts/gnm/h8_track_b_synthetic_fork_r4_reassess.py`.
