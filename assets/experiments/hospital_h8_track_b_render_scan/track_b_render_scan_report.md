# H8-M Track-B Bounded Junction Render Scan (VALIDATION ONLY)

**Status: VALIDATION ONLY.** Render-scan only — no collection, no drive validation, no recording, no training, no rollout, no promotion; `CL_BOUND_XY` unchanged. Free camera at the raised (~0.12 m) robot-eye mount, level horizon.

**Key line:** Reachable asset != usable junction. Track-B only progresses if the render scan proves a real, depth-open branch with visually valid goal views and expected angular action separation.

## Scenes scanned
- `office_isaac` — load_ok=True, prims=4652, probes=16, render_valid_junctions=[], weak=['p03']
- `warehouse_simple` — load_ok=True, prims=3416, probes=16, render_valid_junctions=[], weak=['p00', 'p10', 'p20', 'p30', 'p01', 'p11', 'p21', 'p31', 'p02', 'p12', 'p22', 'p32', 'p03', 'p13', 'p23', 'p33']

## Method (corrected hospital method)
- Geometry-grounded interior grid over each scene's world bbox; at each probe, 4 cardinal views (E/N/W/S) with RGB + `distance_to_image_plane` depth.
- **Branch-choice junction = >= 3 cardinal directions depth-open (median central depth >= 3.0 m)** — arrive via one corridor, choose among >= 2 divergent onward branches. 2 opposite open = straight corridor; 2 perpendicular = L-corner; both are NOT a branch choice.
- Goal branches must be visually distinct (DINO cosine < 0.6) and >= 30.0 deg apart. **Depth openness is mandatory** — luma/DINO alone cannot separate an open corridor from a textured wall (the hospital false-positive lesson).

## Result
- Scenes that loaded: 2/2.
- **RENDER_VALID_JUNCTION:** NONE.
- **RENDER_VALID_BUT_VISUALLY_WEAK:** office_isaac:p03, warehouse_simple:p00, warehouse_simple:p10, warehouse_simple:p20, warehouse_simple:p30, warehouse_simple:p01, warehouse_simple:p11, warehouse_simple:p21, warehouse_simple:p31, warehouse_simple:p02, warehouse_simple:p12, warehouse_simple:p22, warehouse_simple:p32, warehouse_simple:p03, warehouse_simple:p13, warehouse_simple:p23, warehouse_simple:p33.

### Per-probe classification (summary)
| scene | probe | class | n_open | open | sep | goalA depth | goalB depth | DINO | reason |
|---|---|---|---|---|---|---|---|---|---|
| office_isaac | p00 | WALL_ONLY | 0 |  | None | None | None | None | boxed/dead-end (0 open, walls <3.0m) |
| office_isaac | p10 | WALL_ONLY | 0 |  | None | None | None | None | boxed/dead-end (0 open, walls <3.0m) |
| office_isaac | p20 | WALL_ONLY | 0 |  | None | None | None | None | boxed/dead-end (0 open, walls <3.0m) |
| office_isaac | p30 | WALL_ONLY | 0 |  | None | None | None | None | boxed/dead-end (0 open, walls <3.0m) |
| office_isaac | p01 | WALL_ONLY | 0 |  | None | None | None | None | boxed/dead-end (0 open, walls <3.0m) |
| office_isaac | p11 | WALL_ONLY | 2 | E|N | None | None | None | None | L-corner (2 perpendicular open, single forced turn) |
| office_isaac | p21 | WALL_ONLY | 2 | N|W | None | None | None | None | L-corner (2 perpendicular open, single forced turn) |
| office_isaac | p31 | WALL_ONLY | 0 |  | None | None | None | None | boxed/dead-end (0 open, walls <3.0m) |
| office_isaac | p02 | WALL_ONLY | 1 | N | None | None | None | None | boxed/dead-end (1 open, walls <3.0m) |
| office_isaac | p12 | WALL_ONLY | 0 |  | None | None | None | None | boxed/dead-end (0 open, walls <3.0m) |
| office_isaac | p22 | WALL_ONLY | 0 |  | None | None | None | None | boxed/dead-end (0 open, walls <3.0m) |
| office_isaac | p32 | WALL_ONLY | 0 |  | None | None | None | None | boxed/dead-end (0 open, walls <3.0m) |
| office_isaac | p03 | RENDER_VALID_BUT_VISUALLY_WEAK | 3 | N|W|S | 180.0 | 13.967 | 9.13 | 0.674 | branches not distinct (DINO 0.674) |
| office_isaac | p13 | WALL_ONLY | 1 | W | None | None | None | None | boxed/dead-end (1 open, walls <3.0m) |
| office_isaac | p23 | WALL_ONLY | 0 |  | None | None | None | None | boxed/dead-end (0 open, walls <3.0m) |
| office_isaac | p33 | WALL_ONLY | 2 | E|S | None | None | None | None | L-corner (2 perpendicular open, single forced turn) |
| warehouse_simple | p00 | RENDER_VALID_BUT_VISUALLY_WEAK | 4 | E|N|W|S | 90.0 | 20.719 | 14.684 | 0.695 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall, not a branch-choice junction |
| warehouse_simple | p10 | RENDER_VALID_BUT_VISUALLY_WEAK | 4 | E|N|W|S | 90.0 | 20.724 | 11.49 | 0.777 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall, not a branch-choice junction |
| warehouse_simple | p20 | RENDER_VALID_BUT_VISUALLY_WEAK | 4 | E|N|W|S | 90.0 | 20.752 | 11.145 | 0.704 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall, not a branch-choice junction |
| warehouse_simple | p30 | RENDER_VALID_BUT_VISUALLY_WEAK | 4 | E|N|W|S | 90.0 | 20.752 | 13.751 | 0.707 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall, not a branch-choice junction |
| warehouse_simple | p01 | RENDER_VALID_BUT_VISUALLY_WEAK | 4 | E|N|W|S | 90.0 | 16.218 | 14.684 | 0.65 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall, not a branch-choice junction |
| warehouse_simple | p11 | RENDER_VALID_BUT_VISUALLY_WEAK | 4 | E|N|W|S | 180.0 | 16.418 | 13.782 | 0.849 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall, not a branch-choice junction |
| warehouse_simple | p21 | RENDER_VALID_BUT_VISUALLY_WEAK | 4 | E|N|W|S | 180.0 | 16.418 | 13.782 | 0.842 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall, not a branch-choice junction |
| warehouse_simple | p31 | RENDER_VALID_BUT_VISUALLY_WEAK | 4 | E|N|W|S | 180.0 | 16.418 | 13.782 | 0.922 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall, not a branch-choice junction |
| warehouse_simple | p02 | RENDER_VALID_BUT_VISUALLY_WEAK | 4 | E|N|W|S | 90.0 | 18.118 | 14.578 | 0.72 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall, not a branch-choice junction |
| warehouse_simple | p12 | RENDER_VALID_BUT_VISUALLY_WEAK | 4 | E|N|W|S | 180.0 | 18.118 | 12.082 | 0.766 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall, not a branch-choice junction |
| warehouse_simple | p22 | RENDER_VALID_BUT_VISUALLY_WEAK | 4 | E|N|W|S | 180.0 | 18.118 | 12.082 | 0.84 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall, not a branch-choice junction |
| warehouse_simple | p32 | RENDER_VALID_BUT_VISUALLY_WEAK | 4 | E|N|W|S | 90.0 | 18.118 | 13.129 | 0.584 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall, not a branch-choice junction |
| warehouse_simple | p03 | RENDER_VALID_BUT_VISUALLY_WEAK | 4 | E|N|W|S | 90.0 | 22.452 | 14.684 | 0.694 | branches not distinct (DINO 0.694) |
| warehouse_simple | p13 | RENDER_VALID_BUT_VISUALLY_WEAK | 4 | E|N|W|S | 90.0 | 22.452 | 11.49 | 0.77 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall, not a branch-choice junction |
| warehouse_simple | p23 | RENDER_VALID_BUT_VISUALLY_WEAK | 4 | E|N|W|S | 90.0 | 22.452 | 9.999 | 0.606 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall, not a branch-choice junction |
| warehouse_simple | p33 | RENDER_VALID_BUT_VISUALLY_WEAK | 4 | E|N|W|S | 90.0 | 22.452 | 13.129 | 0.693 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall, not a branch-choice junction |

## Decision
**NO_RENDER_VALID_JUNCTION_RECOMMEND_WAREHOUSE_FULL_OR_NEW_SCENE.**
- **No render-valid junction** in either scene. Every depth-open multi-branch point is open floor or a straight (collinear) corridor — visually verified as NOT a navigable fork, so not usable for angular branch-choice. → recommend scanning `warehouse_full` next, or selecting/acquiring a new junction-capable scene. Do NOT force a fake angular-branch claim.
- Bounded scan: absence is strong evidence, not proof; cardinal sampling resolves orthogonal junctions, not oblique forks.

## Visual verification (mandatory) & scene character
- **Open-floor guard:** depth-openness in >=3 cardinal directions does NOT by itself mean a corridor junction — an OPEN HALL is open in every direction too. Points with all 4 cardinal depths >= 4.0 m (no bounding walls) are rejected as open floor, not a branch-choice junction. Rejected here: warehouse_simple:p00, warehouse_simple:p10, warehouse_simple:p20, warehouse_simple:p30, warehouse_simple:p01, warehouse_simple:p11, warehouse_simple:p21, warehouse_simple:p31, warehouse_simple:p02, warehouse_simple:p12, warehouse_simple:p22, warehouse_simple:p32, warehouse_simple:p13, warehouse_simple:p23, warehouse_simple:p33.
- **Contact sheets were visually inspected.** Automated depth+DINO initially flagged an open warehouse-floor corner as a junction (open floor one way, a shelf the other, DINO just under threshold) — VISUAL inspection showed it is NOT a navigable fork, and the open-floor guard now rejects it. Pixel+depth+embedding still required visual confirmation — the hospital false-positive lesson, again.
- **warehouse_simple** is a single large OPEN HALL with shelving along the walls — no aisles, no corridors, no T-junctions in the scanned footprint.
- **office_isaac** is an open-plan bullpen and is UNDER-LIT with the dome light: most probes render near-black (classified WALL_ONLY on low luma), so the office scan is partly INCONCLUSIVE; the lit regions show an open bullpen, not a corridor junction. A stronger lighting setup would be needed to fully scan the office.

## Claim boundary
- Validation-only render scan; no collection, no recording, no drive validation, no rollout, no training, no promotion, no benchmark evidence; incumbent retained; `DIAGNOSTIC_ONLY_NOT_PROMOTED`; `CL_BOUND_XY` unchanged.
- **office_isaac produced zero confirmed render-valid junctions** (partly inconclusive due to low lighting); **warehouse_simple produced zero render-valid junctions**. **Both scenes FAIL the Track-B render-valid junction gate.**
- **No angular branch-choice training should begin from these scenes.** No real junction, no angular-branch training. Reachable asset != usable junction; render-validity != drive-validity. Training remains blocked until a real junction, valid goal images, recorded decision frames, train/val/test splits, and a leakage audit exist.

## Artifacts
`assets/experiments/hospital_h8_track_b_render_scan/`: `track_b_render_scan_manifest.json`, `track_b_render_scan_table.csv`, `track_b_render_scan_report.md`, `track_b_visual_similarity_matrix.{csv,md}`, `contact_sheets/`, `render_metadata/`. Harness: `scripts/gnm/h8_track_b_render_scan_render.py` (isaac), `scripts/gnm/h8_track_b_render_scan_analyze.py` (this). Raw .npy in scratchpad (not committed).
