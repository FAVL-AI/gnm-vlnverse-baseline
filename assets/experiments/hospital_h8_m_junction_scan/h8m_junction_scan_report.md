# H8-M Bounded Real-Junction Render Scan (VALIDATION ONLY)

**Status: VALIDATION ONLY.** Render-scan only — no drive validation, no recording, no training, no rollout, no promotion; `CL_BOUND_XY` unchanged. Verified hospital.usd, scene gate **PASS**, free camera at the raised (~0.12 m) mount, level horizon.

## Question
Does any render-valid T-junction/fork exist inside the safe +/-6 m envelope — i.e. a shared decision frame whose goal A and goal B lie along **divergent, actually-open** branches (>=30 deg apart, both render-valid, visually distinct)?

## Method
- 8 in-envelope candidates (T-junctions along the corridor, reception fork, corridor-end fans, a perpendicular reception cross), each rendered decision + goalA + goalB (branch reach 2.0 m).
- Render-valid goal view: luma >= 15.0 and lower-frame black <= 0.5. **Branch OPEN (the decisive test): median central depth >= 3.0 m** — a goal view that renders fine but faces a near wall (small depth) is WALL_ONLY, not a navigable branch. Branch distinctness: DINO cosine < 0.6. Angular separation >= 30.0 deg.
- **Why depth:** luma + distinctness alone cannot tell an open corridor from a textured wall (two different walls read as 'valid + distinct'); depth is the criterion that separates an open branch from a wall in front of the camera.
- Grounded in the known reachable geometry (H8 straight corridor + reception); a **bounded** scan, not an exhaustive floor-plan search.

## Candidates
| candidate | kind | class | sep (deg) | goalA depth (m) | goalB depth (m) | goalA luma | goalB luma | branch DINO |
|---|---|---|---|---|---|---|---|---|
| jc_corr_wmid_T | corridor T (+/-y) | WALL_ONLY | 180 | 3.55 | None | 33.1 | 125.9 | None |
| jc_corr_mid_T | corridor T (+/-y) | WALL_ONLY | 180 | 3.55 | None | 26.8 | 106.9 | None |
| jc_corr_c_T | corridor T (+/-y) | WALL_ONLY | 180 | 0.435 | 0.485 | 136.4 | 94.4 | None |
| jc_corr_e_T | corridor T (+/-y) | WALL_ONLY | 180 | 0.331 | None | 19.6 | 126.1 | None |
| jc_recep_fork | reception fork (+/-45) | WALL_ONLY | 90 | 1.298 | 1.908 | 29.6 | 88.3 | None |
| jc_corr_end_e | east corridor-end fan | WALL_ONLY | 80 | 1.413 | 1.965 | 23.7 | 37.3 | None |
| jc_corr_end_w | west corridor-end fan | WALL_ONLY | 80 | 1.083 | 0.239 | 43.5 | 0.0 | None |
| jc_recep_cross | reception cross (perp approach) | WALL_ONLY | 120 | 2.86 | 7.696 | 37.1 | 48.9 | None |

- **RENDER_VALID_JUNCTION:** NONE.
- **RENDER_VALID_BUT_VISUALLY_WEAK:** NONE.

## Decision
**NO_RENDER_VALID_JUNCTION_RECOMMEND_RESCOPE_OR_DIFFERENT_SCENE.**
- **No render-valid junction** was found in the bounded scan → recommend **re-scoping H8-M away from angular-branch claims in this scene**, or moving the angular-branch evidence to a different scene. Do NOT force a fake junction claim.
- **No angular branch-choice claim can be made in this hospital scene under the current safe +/-6 m envelope.** hospital.usd should remain a **distance/stop-axis** conditioning and hospital-scene visual-validity environment; angular branch-choice evidence must move to a different scene that contains a real fork/T-junction.
- This is a bounded scan; absence is strong evidence but not a proof that no junction exists anywhere in hospital.usd.

## Interpretation (honest)
- **No navigable junction exists in the bounded +/-6 m scan.** Every candidate branch view faces a wall or furniture within ~0.3-2.9 m (median central depth); the only open branch (`jc_recep_cross` goalB, 7.7 m) is paired with a blocked branch — so no candidate has TWO divergent open branches.
- **RGB-only vs depth-aware (why the gate changed):** a pixel-validity-only gate (decision + both goal views render-valid, angular sep >= 30.0 deg) would have accepted **7 candidates as apparent junctions** (jc_corr_wmid_T, jc_corr_mid_T, jc_corr_c_T, jc_corr_e_T, jc_recep_fork, jc_corr_end_e, jc_recep_cross) — luma + DINO cannot separate an open corridor from a textured wall (two different walls read as 'valid + distinct'). Adding the **depth-openness criterion** (median central depth >= 3.0 m on BOTH branches) reclassifies **all 7 of them to WALL_ONLY** (jc_corr_wmid_T, jc_corr_mid_T, jc_corr_c_T, jc_corr_e_T, jc_recep_fork, jc_corr_end_e, jc_recep_cross). Pixel validity != navigability — the same lesson as the recep_junction black-void fix, one level deeper.
- **This corroborates the H8 finding**: the reachable envelope is a single straight corridor with walls/furniture on the sides — no branching corridors.
- **Recommendation:** re-scope H8-M away from angular-branch claims in this scene (keep the distance/stop axis and any genuinely-distinct rooms), or move the angular-branch evidence to a different scene. Do NOT force a fake junction.

## Claim boundary
- Validation-only render; no drive, no recording, no training, no rollout, no promotion, no benchmark/autonomy claim; incumbent retained; `DIAGNOSTIC_ONLY_NOT_PROMOTED`; `CL_BOUND_XY` unchanged. Free camera (no robot body): drivability + chassis occlusion are Step-C checks.

## Artifacts
`assets/experiments/hospital_h8_m_junction_scan/`: `h8m_junction_scan_manifest.json`, `h8m_junction_scan_report.md`, `h8m_junction_scan_table.csv`, `contact_sheets/`, `render_metadata/`. Harness: `scripts/gnm/h8m_junction_scan_render.py` (isaac), `scripts/gnm/h8m_junction_scan_analyze.py` (this). Raw .npy in scratchpad (not committed).
