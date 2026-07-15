# H8-M Step B — Embedding Distinctness Search Report (VALIDATION ONLY)

**Status: VALIDATION ONLY.** Rendering is validation evidence only — NOT recording, training, rollout, promotion, or benchmark evidence. No robot was driven; no rosbag or trajectory was recorded; no model was trained; `CL_BOUND_XY` unchanged. Verified hospital.usd, scene gate **PASS**, free camera at the raised (~0.12 m) mount height, level horizon.

## Question
Are the H8-M Step-A candidate rooms/goals visually distinct enough (under an embedding gate) to support a stronger held-out visual split — and is the `recep_junction` angular branch render-valid?

## Method
- **Primary:** DINO ViT-S/16 cosine (DINO ViT-S/16 cosine (timm vit_small_patch16_224.dino)). **Secondary:** aHash 16x16 + global SSIM (in the CSV).
- Goal images rendered per zone (goalA/goalB) + the cross-scene placeholder; 17 goal views compared pairwise.
- Thresholds: **T_cross = 0.6** (cross-split leakage ceiling; calibrated at the largest gap in the observed cross-split distribution, clamped [0.45,0.80]; init 0.6); **T_dup = 0.92** (within-split near-duplicate).

## Observed DINO-cosine distribution
- cross-split: {'n': 106, 'min': np.float64(0.157), 'max': np.float64(0.914), 'mean': 0.456}
- within-split: {'n': 22, 'min': np.float64(0.235), 'max': np.float64(0.865), 'mean': 0.482}
- within-zone (goalA vs goalB): {'n': 8, 'min': np.float64(0.232), 'max': np.float64(0.909), 'mean': 0.559}

## Per-zone assessment
| zone | split | status | cross-split max DINO | goalA-vs-goalB DINO | same-split dup DINO | feasibility |
|---|---|---|---|---|---|---|
| recep_junction | test | render_invalid_needs_coordinate_correction | 0.514 | 0.283 | 0.545 | NEEDS_RENDER_VALIDATION+NEEDS_DRIVE_VALIDATION |
| recep_fork | test | visually_indistinct_reject_or_merge | 0.688 | 0.663 | 0.545 | NEEDS_RENDER_VALIDATION+NEEDS_DRIVE_VALIDATION |
| recep_desk_multiobj | train | visually_indistinct_reject_or_merge | 0.854 | 0.232 | 0.865 | NEEDS_RENDER_VALIDATION+NEEDS_DRIVE_VALIDATION |
| side_corridor | val | visually_indistinct_reject_or_merge | 0.815 | 0.408 | 0.785 | NEEDS_RENDER_VALIDATION+NEEDS_DRIVE_VALIDATION |
| waiting_seating | train | visually_distinct | 0.599 | 0.775 | 0.606 | NEEDS_RENDER_VALIDATION |
| lobby_vending_nearfar | train | visually_indistinct_reject_or_merge | 0.914 | 0.84 | 0.865 | DRIVE_VALIDATED |
| east_vending_nearfar | val | visually_indistinct_reject_or_merge | 0.914 | 0.909 | 0.785 | DRIVE_VALIDATED |
| lookalike_confuser | hard_negative | hard_negative_candidate | 0.768 | 0.365 | 0.734 | NEEDS_RENDER_VALIDATION+NEEDS_DRIVE_VALIDATION |
| hardneg_crossscene | hard_negative | hard_negative_candidate | 0.697 | None | 0.734 | DESIGN_ONLY |

- **visually distinct** (cross-split DINO < 0.6): h8m_waiting_seating.
- **visually indistinct (reject/merge)**: h8m_recep_fork, h8m_recep_desk_multiobj, h8m_side_corridor, h8m_lobby_vending_nearfar, h8m_east_vending_nearfar.

## recep_junction angular-branch check (the core H8-S fix)
- decision frame render-visible: **True**
- goalA render-valid (luma 0.0, lower-black 1.0): **False**
- goalB render-valid (luma 29.8, lower-black 0.7999): **False**
- goalA vs goalB visually distinguishable (both valid AND DINO 0.283 < T_cross 0.6): **False**
- **branch render-valid (decision visible AND both goals valid): False**
- within safe spawn-relocation envelope: **True**
- drive feasibility: **NOT_TESTED_UNTIL_STEP_C** (Step C).
- free-camera render: scene visibility + distinctness only; chassis occlusion and drivability are Step-C checks. A goal view that is black-void (luma~0) means the proposed branch coordinate points into unlit void/wall -> NOT a valid junction.

## Decision
**RE_SCOPE_H8M_ANGULAR_BRANCH_NOT_RENDER_VALID.**
- If embedding distinctness is promising and the junction is render-valid → Step C drive validation. If the true angular branch is visually indistinct or not render-valid → **re-scope H8-M** before drive validation. If candidate rooms collapse visually → reject/merge/defer them rather than forcing a fake held-out split.

## Interpretation (honest)
- **`recep_junction` is NOT render-valid**: goalA is a black void (luma 0.0, 100% lower black) and goalB is 80% black — the proposed branch coordinates point into unlit void/wall, and the decision frame is a straight corridor. No real junction exists at these coordinates.
- **An initial automated junction check falsely PASSED** by testing only the decision frame's occlusion; it was **corrected by adding render-validity gating on the GOAL views** (a goal view with luma < 15 or lower-frame black > 0.5 is a coordinate-into-wall, not a distinct branch). Under the fix the junction correctly fails.
- **Only 1 of 8 zones is visually distinct** (`waiting_seating`); the **vending / lobby / east zones collapse visually** (same alcove, DINO cross-split ≥ T_cross) and the reception fork/desk views are walls/windows.
- **The H8-M Step-A coordinates cannot currently support a true angular junction OR a multi-room held-out visual split** in this scene envelope.
- **This is a re-scope signal, NOT a success** — the validation gate did its job before any drive/record/train. A bounded real-junction render scan is the next step before any re-scope is finalized.

## Claim boundary
- Validation-only rendering; no recording, no training, no rollout, no promotion, no benchmark or autonomy claim; incumbent retained; `DIAGNOSTIC_ONLY_NOT_PROMOTED`.
- Free camera (no robot body): distinctness + scene visibility only; chassis occlusion and drivability are Step-C drive-validation checks. `CL_BOUND_XY` unchanged.

## Artifacts
`assets/experiments/hospital_h8_m_embedding_search/`: `h8m_embedding_manifest.json`, `h8m_visual_similarity_matrix.{csv,md}`, `h8m_embedding_search_report.md`, `contact_sheets/`, `render_metadata/`. Harness: `scripts/gnm/h8m_embedding_render.py` (isaac render), `scripts/gnm/h8m_embedding_analyze.py` (this analysis). Raw .npy kept in scratchpad (not committed).
