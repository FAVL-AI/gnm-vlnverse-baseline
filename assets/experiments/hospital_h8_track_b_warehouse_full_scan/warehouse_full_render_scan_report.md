# H8-M Track-B Bounded Junction Render Scan (VALIDATION ONLY)

**Status: VALIDATION ONLY.** Render-scan only — no collection, no drive validation, no recording, no training, no rollout, no promotion; `CL_BOUND_XY` unchanged. Free camera at the raised (~0.12 m) robot-eye mount, level horizon.

**Key line:** Reachable asset != usable junction. Track-B only progresses if the render scan proves a real, depth-open branch with visually valid goal views and expected angular action separation.

## Scenes scanned
- `warehouse_full` — load_ok=True, prims=26329, probes=25, render_valid_junctions=[], weak=['p22', 'p03', 'p13', 'p33', 'p04', 'p14', 'p34']

## Method (corrected hospital method)
- Geometry-grounded interior grid over each scene's world bbox; at each probe, 4 cardinal views (E/N/W/S) with RGB + `distance_to_image_plane` depth.
- **Branch-choice junction = >= 3 cardinal directions depth-open (median central depth >= 3.0 m)** — arrive via one corridor, choose among >= 2 divergent onward branches. 2 opposite open = straight corridor; 2 perpendicular = L-corner; both are NOT a branch choice.
- Goal branches must be visually distinct (DINO cosine < 0.6) and >= 30.0 deg apart. **Depth openness is mandatory** — luma/DINO alone cannot separate an open corridor from a textured wall (the hospital false-positive lesson).

## Result
- Scenes that loaded: 1/1.
- **RENDER_VALID_JUNCTION:** NONE.
- **RENDER_VALID_BUT_VISUALLY_WEAK:** warehouse_full:p22, warehouse_full:p03, warehouse_full:p13, warehouse_full:p33, warehouse_full:p04, warehouse_full:p14, warehouse_full:p34.

### Per-probe classification (summary)
| scene | probe | class | n_open | open | sep | goalA depth | goalB depth | DINO | reason |
|---|---|---|---|---|---|---|---|---|---|
| warehouse_full | p00 | OPEN_FLOOR_NOT_JUNCTION | 4 | E|N|W|S | 90.0 | 23.923 | 20.293 | 0.871 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall, not a branch-choice junction |
| warehouse_full | p10 | OPEN_FLOOR_NOT_JUNCTION | 4 | E|N|W|S | 90.0 | 20.293 | 19.976 | 0.805 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall, not a branch-choice junction |
| warehouse_full | p20 | OPEN_FLOOR_NOT_JUNCTION | 4 | E|N|W|S | 90.0 | 20.293 | 15.875 | 0.812 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall, not a branch-choice junction |
| warehouse_full | p30 | OPEN_FLOOR_NOT_JUNCTION | 4 | E|N|W|S | 90.0 | 20.293 | 19.994 | 0.803 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall, not a branch-choice junction |
| warehouse_full | p40 | OPEN_FLOOR_NOT_JUNCTION | 4 | E|N|W|S | 90.0 | 23.941 | 20.293 | 0.854 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall, not a branch-choice junction |
| warehouse_full | p01 | OPEN_FLOOR_NOT_JUNCTION | 4 | E|N|W|S | 90.0 | 25.227 | 23.923 | 0.762 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall, not a branch-choice junction |
| warehouse_full | p11 | OPEN_FLOOR_NOT_JUNCTION | 4 | E|N|W|S | 90.0 | 25.227 | 19.805 | 0.78 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall, not a branch-choice junction |
| warehouse_full | p21 | OPEN_FLOOR_NOT_JUNCTION | 4 | E|N|W|S | 90.0 | 25.227 | 15.875 | 0.735 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall, not a branch-choice junction |
| warehouse_full | p31 | OPEN_FLOOR_NOT_JUNCTION | 4 | E|N|W|S | 90.0 | 25.227 | 19.823 | 0.805 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall, not a branch-choice junction |
| warehouse_full | p41 | OPEN_FLOOR_NOT_JUNCTION | 4 | E|N|W|S | 90.0 | 25.227 | 23.941 | 0.803 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall, not a branch-choice junction |
| warehouse_full | p02 | OPEN_FLOOR_NOT_JUNCTION | 4 | E|N|W|S | 90.0 | 30.162 | 13.578 | 0.679 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall, not a branch-choice junction |
| warehouse_full | p12 | OPEN_FLOOR_NOT_JUNCTION | 4 | E|N|W|S | 90.0 | 30.162 | 14.2 | 0.625 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall, not a branch-choice junction |
| warehouse_full | p22 | RENDER_VALID_BUT_VISUALLY_WEAK | 3 | E|W|S | 90.0 | 30.162 | 15.048 | 0.612 | branches not distinct (DINO 0.612) |
| warehouse_full | p32 | OPEN_FLOOR_NOT_JUNCTION | 4 | E|N|W|S | 90.0 | 30.162 | 14.339 | 0.6 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall, not a branch-choice junction |
| warehouse_full | p42 | OPEN_FLOOR_NOT_JUNCTION | 4 | E|N|W|S | 90.0 | 30.162 | 17.677 | 0.698 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall, not a branch-choice junction |
| warehouse_full | p03 | RENDER_VALID_BUT_VISUALLY_WEAK | 3 | E|N|S | 180.0 | 35.068 | 9.875 | 0.648 | branches not distinct (DINO 0.648) |
| warehouse_full | p13 | RENDER_VALID_BUT_VISUALLY_WEAK | 3 | E|N|S | 180.0 | 30.398 | 6.337 | 0.584 | VISUAL VERIFICATION (gate 13): the contact sheet shows a STRAIGHT AISLE — goalA(S) and goalB(N) are opposite ends of the SAME aisle (collinear, sep 180 deg), distinguishable only by a pallet/obstacle at one end; the decision(E) view is a rack face of boxes, not a navigable cross-aisle. Not a genuine angular fork; DINO 0.584 is a marginal artifact. Downgraded from RENDER_VALID_JUNCTION. |
| warehouse_full | p23 | WALL_ONLY | 0 |  | None | None | None | None | boxed/dead-end (0 open, walls <3.0m) |
| warehouse_full | p33 | RENDER_VALID_BUT_VISUALLY_WEAK | 3 | N|W|S | 180.0 | 6.226 | 4.201 | 0.779 | branches not distinct (DINO 0.779) |
| warehouse_full | p43 | WALL_ONLY | 1 | S | None | None | None | None | boxed/dead-end (1 open, walls <3.0m) |
| warehouse_full | p04 | RENDER_VALID_BUT_VISUALLY_WEAK | 3 | E|N|S | 180.0 | 14.765 | 13.94 | 0.875 | branches not distinct (DINO 0.875) |
| warehouse_full | p14 | RENDER_VALID_BUT_VISUALLY_WEAK | 4 | E|N|W|S | 180.0 | 7.525 | 6.89 | 0.794 | branches not distinct (DINO 0.794) |
| warehouse_full | p24 | WALL_ONLY | 2 | E|W | None | None | None | None | straight corridor (2 opposite open, no choice) |
| warehouse_full | p34 | RENDER_VALID_BUT_VISUALLY_WEAK | 3 | N|W|S | 180.0 | 4.763 | 4.385 | 0.88 | branches not distinct (DINO 0.88) |
| warehouse_full | p44 | WALL_ONLY | 2 | N|S | None | None | None | None | straight corridor (2 opposite open, no choice) |

## Decision
**NO_RENDER_VALID_JUNCTION_RECOMMEND_NEW_CORRIDOR_STRUCTURED_SCENE.**
- **No render-valid junction** in `warehouse_full`. → recommend **selecting or acquiring a new corridor-structured scene** (with real aisles / corridor forks) rather than scanning more random assets. Do NOT force a fake angular-branch claim.
- Bounded scan: absence is strong evidence, not proof; cardinal sampling resolves orthogonal junctions, not oblique forks.
- **Final counts (warehouse_full): OPEN_FLOOR_NOT_JUNCTION=14, RENDER_VALID_BUT_VISUALLY_WEAK=7, WALL_ONLY=4, RENDER_VALID_JUNCTION=0.** The visually-weak cases are straight / collinear aisles (opposite-end goals along one aisle), not true angular forks.
- **Track-B status: `office_isaac`, `warehouse_simple`, and `warehouse_full` have ALL failed the Track-B render-valid-junction gate.** No angular branch-choice training should begin from these scenes.
- **Next step: source or build a genuinely corridor-forked T/Y/cross-junction scene** — two navigable branches diverging >= 30 deg with visually distinct, branch-specific goal views — not more Isaac stock warehouses/offices.

## Visual verification (mandatory) & scene character
- **Class distribution (warehouse_full):** OPEN_FLOOR_NOT_JUNCTION=14, RENDER_VALID_BUT_VISUALLY_WEAK=7, WALL_ONLY=4.
- **Open-floor guard (explicit `OPEN_FLOOR_NOT_JUNCTION` class):** depth-openness in >=3 cardinal directions does NOT by itself mean a corridor junction — an OPEN HALL is open in every direction too. Points with all 4 cardinal depths >= 4.0 m (no bounding walls) are classified `OPEN_FLOOR_NOT_JUNCTION`. Rejected here: warehouse_full:p00, warehouse_full:p10, warehouse_full:p20, warehouse_full:p30, warehouse_full:p40, warehouse_full:p01, warehouse_full:p11, warehouse_full:p21, warehouse_full:p31, warehouse_full:p41, warehouse_full:p02, warehouse_full:p12, warehouse_full:p32, warehouse_full:p42.
- **Contact-sheet visual verification is MANDATORY (gate 13) before any probe is confirmed `RENDER_VALID_JUNCTION`.** Depth + embedding is necessary but NOT sufficient: in the prior office/warehouse scan an open-floor corner scored just under the DINO threshold and was only caught by visually inspecting the contact sheet. Any RENDER_VALID_JUNCTION below has been visually inspected; candidates that the images show are open floor / a shelf / a straight corridor are downgraded, not reported as forks.
- **Visual-verification downgrades applied (gate 13):** warehouse_full:p13 (RENDER_VALID_JUNCTION->RENDER_VALID_BUT_VISUALLY_WEAK). The automated gate flagged `warehouse_full:p13` as RENDER_VALID_JUNCTION, but the contact sheet shows a straight aisle (goalA/goalB are opposite ends of one aisle, sep 180 deg; the decision view is a rack face) — a distance/obstacle difference, not an angular fork — so it was downgraded. warehouse_full's scanned footprint is open floor (centre) plus straight parallel aisles along the racks: no cross-aisle / T-junction.

## Claim boundary
- Validation-only render scan; no collection, no recording, no drive validation, no rollout, no training, no promotion, no benchmark evidence; incumbent retained; `DIAGNOSTIC_ONLY_NOT_PROMOTED`; `CL_BOUND_XY` unchanged.
- **warehouse_full produced zero render-valid junctions — it FAILS the Track-B render-valid junction gate.**
- Reachable asset != usable junction; render-validity != drive-validity. **No angular branch-choice training should begin from this scene.** No real junction, no angular-branch training. Training remains blocked until a real junction, valid goal images, recorded decision frames, train/val/test splits, and a leakage audit exist.

## Artifacts
`assets/experiments/hospital_h8_track_b_warehouse_full_scan/`: `warehouse_full_render_scan_manifest.json`, `warehouse_full_render_scan_table.csv`, `warehouse_full_render_scan_report.md`, `warehouse_full_visual_similarity_matrix.{csv,md}`, `contact_sheets/`, `render_metadata/`. Harness: `scripts/gnm/h8_track_b_warehouse_full_render.py` (isaac), `scripts/gnm/h8_track_b_warehouse_full_analyze.py` (this). Raw .npy in scratchpad (not committed).
