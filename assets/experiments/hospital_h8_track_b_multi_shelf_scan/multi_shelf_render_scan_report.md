# H8-M Track-B Bounded Junction Render Scan (VALIDATION ONLY)

**Status: VALIDATION ONLY.** Render-scan only — no collection, no drive validation, no recording, no training, no rollout, no promotion; `CL_BOUND_XY` unchanged. Free camera at the raised (~0.12 m) robot-eye mount, level horizon.

**Key line:** Reachable asset != usable junction. Track-B only progresses if the render scan proves a real, depth-open branch with visually valid goal views and expected angular action separation.

## Scenes scanned
- `warehouse_multiple_shelves` — load_ok=True, prims=8126, probes=25, render_valid_junctions=[], weak=['p04', 'p44']

## Method (corrected hospital method)
- Geometry-grounded interior grid over each scene's world bbox; at each probe, 4 cardinal views (E/N/W/S) with RGB + `distance_to_image_plane` depth.
- **Branch-choice junction = >= 3 cardinal directions depth-open (median central depth >= 3.0 m)** — arrive via one corridor, choose among >= 2 divergent onward branches. 2 opposite open = straight corridor; 2 perpendicular = L-corner; both are NOT a branch choice.
- Goal branches must be visually distinct (DINO cosine < 0.6) and >= 30.0 deg apart. **Depth openness is mandatory** — luma/DINO alone cannot separate an open corridor from a textured wall (the hospital false-positive lesson).

## Result
- Scenes that loaded: 1/1.
- **RENDER_VALID_JUNCTION:** NONE.
- **RENDER_VALID_BUT_VISUALLY_WEAK:** warehouse_multiple_shelves:p04, warehouse_multiple_shelves:p44.

### Per-probe classification (summary)
| scene | probe | class | n_open | open | sep | goalA depth | goalB depth | DINO | reason |
|---|---|---|---|---|---|---|---|---|---|
| warehouse_multiple_shelves | p00 | OPEN_FLOOR_NOT_JUNCTION | 4 | E|N|W|S | 90.0 | 7.079 | 17.463 | 0.682 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall (or a wide 4-way that visual verification must distinguish), not auto-confirmed as a branch-choice junction |
| warehouse_multiple_shelves | p10 | OPEN_FLOOR_NOT_JUNCTION | 4 | E|N|W|S | 90.0 | 11.046 | 17.463 | 0.621 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall (or a wide 4-way that visual verification must distinguish), not auto-confirmed as a branch-choice junction |
| warehouse_multiple_shelves | p20 | WALL_ONLY | 2 | N|S | None | None | None | None | straight corridor (2 opposite open, no choice) |
| warehouse_multiple_shelves | p30 | OPEN_FLOOR_NOT_JUNCTION | 4 | E|N|W|S | 90.0 | 13.393 | 11.008 | 0.628 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall (or a wide 4-way that visual verification must distinguish), not auto-confirmed as a branch-choice junction |
| warehouse_multiple_shelves | p40 | OPEN_FLOOR_NOT_JUNCTION | 4 | E|N|W|S | 90.0 | 17.471 | 7.278 | 0.659 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall (or a wide 4-way that visual verification must distinguish), not auto-confirmed as a branch-choice junction |
| warehouse_multiple_shelves | p01 | OPEN_FLOOR_NOT_JUNCTION | 4 | E|N|W|S | 90.0 | 7.489 | 15.055 | 0.616 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall (or a wide 4-way that visual verification must distinguish), not auto-confirmed as a branch-choice junction |
| warehouse_multiple_shelves | p11 | OPEN_FLOOR_NOT_JUNCTION | 4 | E|N|W|S | 90.0 | 11.196 | 15.226 | 0.548 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall (or a wide 4-way that visual verification must distinguish), not auto-confirmed as a branch-choice junction |
| warehouse_multiple_shelves | p21 | OPEN_FLOOR_NOT_JUNCTION | 4 | E|N|W|S | 90.0 | 9.107 | 5.281 | 0.528 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall (or a wide 4-way that visual verification must distinguish), not auto-confirmed as a branch-choice junction |
| warehouse_multiple_shelves | p31 | OPEN_FLOOR_NOT_JUNCTION | 4 | E|N|W|S | 90.0 | 15.055 | 11.063 | 0.601 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall (or a wide 4-way that visual verification must distinguish), not auto-confirmed as a branch-choice junction |
| warehouse_multiple_shelves | p41 | OPEN_FLOOR_NOT_JUNCTION | 4 | E|N|W|S | 90.0 | 15.055 | 7.95 | 0.623 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall (or a wide 4-way that visual verification must distinguish), not auto-confirmed as a branch-choice junction |
| warehouse_multiple_shelves | p02 | OPEN_FLOOR_NOT_JUNCTION | 4 | E|N|W|S | 90.0 | 5.489 | 12.559 | 0.597 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall (or a wide 4-way that visual verification must distinguish), not auto-confirmed as a branch-choice junction |
| warehouse_multiple_shelves | p12 | OPEN_FLOOR_NOT_JUNCTION | 4 | E|N|W|S | 90.0 | 11.196 | 12.846 | 0.533 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall (or a wide 4-way that visual verification must distinguish), not auto-confirmed as a branch-choice junction |
| warehouse_multiple_shelves | p22 | COLLINEAR_AISLE_NOT_JUNCTION | 3 | E|W|S | 90.0 | 8.669 | 7.713 | 0.414 | STRAIGHT AISLE: one through-axis open (E-W), the perpendicular axis is not a full crossing — two ends of one aisle, not an angular fork |
| warehouse_multiple_shelves | p32 | OPEN_FLOOR_NOT_JUNCTION | 4 | E|N|W|S | 90.0 | 12.846 | 11.158 | 0.545 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall (or a wide 4-way that visual verification must distinguish), not auto-confirmed as a branch-choice junction |
| warehouse_multiple_shelves | p42 | OPEN_FLOOR_NOT_JUNCTION | 4 | E|N|W|S | 90.0 | 12.817 | 5.451 | 0.62 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall (or a wide 4-way that visual verification must distinguish), not auto-confirmed as a branch-choice junction |
| warehouse_multiple_shelves | p03 | OPEN_FLOOR_NOT_JUNCTION | 4 | E|N|W|S | 90.0 | 5.054 | 6.89 | 0.604 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall (or a wide 4-way that visual verification must distinguish), not auto-confirmed as a branch-choice junction |
| warehouse_multiple_shelves | p13 | OPEN_FLOOR_NOT_JUNCTION | 4 | E|N|W|S | 90.0 | 10.133 | 10.438 | 0.607 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall (or a wide 4-way that visual verification must distinguish), not auto-confirmed as a branch-choice junction |
| warehouse_multiple_shelves | p23 | WALL_ONLY | 2 | E|W | None | None | None | None | straight corridor (2 opposite open, no choice) |
| warehouse_multiple_shelves | p33 | OPEN_FLOOR_NOT_JUNCTION | 4 | E|N|W|S | 90.0 | 10.931 | 19.733 | 0.569 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall (or a wide 4-way that visual verification must distinguish), not auto-confirmed as a branch-choice junction |
| warehouse_multiple_shelves | p43 | OPEN_FLOOR_NOT_JUNCTION | 4 | E|N|W|S | 90.0 | 6.541 | 4.76 | 0.568 | OPEN FLOOR: all 4 cardinal dirs depth >= 4.0 m (no bounding corridor walls) — open hall (or a wide 4-way that visual verification must distinguish), not auto-confirmed as a branch-choice junction |
| warehouse_multiple_shelves | p04 | RENDER_VALID_BUT_VISUALLY_WEAK | 4 | E|N|W|S | 90.0 | 4.678 | 22.17 | 0.639 | branches not distinct (DINO 0.639) |
| warehouse_multiple_shelves | p14 | COLLINEAR_AISLE_NOT_JUNCTION | 3 | N|W|S | 90.0 | 8.03 | 6.175 | 0.521 | STRAIGHT AISLE: one through-axis open (N-S), the perpendicular axis is not a full crossing — two ends of one aisle, not an angular fork |
| warehouse_multiple_shelves | p24 | WALL_ONLY | 0 |  | None | None | None | None | boxed/dead-end (0 open, walls <3.0m) |
| warehouse_multiple_shelves | p34 | COLLINEAR_AISLE_NOT_JUNCTION | 3 | E|N|S | 90.0 | 6.097 | 8.03 | 0.54 | STRAIGHT AISLE: one through-axis open (N-S), the perpendicular axis is not a full crossing — two ends of one aisle, not an angular fork |
| warehouse_multiple_shelves | p44 | RENDER_VALID_BUT_VISUALLY_WEAK | 4 | E|N|W|S | 90.0 | 4.758 | 22.141 | 0.608 | branches not distinct (DINO 0.608) |

## Decision
**NO_RENDER_VALID_JUNCTION_STOP_REAL_ASSETS_BUILD_SYNTHETIC_DIAGNOSTIC_FORK.**
- **No render-valid junction** in `warehouse_multiple_shelves`. → this was the final targeted real-world-like candidate; **stop real-asset scanning** and recommend **building a small `SYNTHETIC_DIAGNOSTIC_ONLY` T/Y/cross fork scene**. Do NOT force a fake angular-branch claim.
- Bounded scan: absence is strong evidence, not proof; cardinal sampling resolves orthogonal junctions, not oblique forks.
- **Final counts (warehouse_multiple_shelves): OPEN_FLOOR_NOT_JUNCTION=17, COLLINEAR_AISLE_NOT_JUNCTION=3, RENDER_VALID_BUT_VISUALLY_WEAK=2, WALL_ONLY=3, RENDER_VALID_JUNCTION=0.**
- **Track-B status: `hospital`, `office_isaac`, `warehouse_simple`, `warehouse_full`, and `warehouse_multiple_shelves` have ALL failed the Track-B render-valid-junction gate.** No angular branch-choice training should begin from these scenes.
- **Next step: build a small `SYNTHETIC_DIAGNOSTIC_ONLY` corridor-forked (T/Y/cross) scene** — two navigable branches diverging >= 30 deg with visually distinct, branch-specific goal views — clearly labelled synthetic/diagnostic-only. Real-asset scanning is now exhausted.

## Visual verification (mandatory) & scene character
- **Class distribution (warehouse_multiple_shelves):** COLLINEAR_AISLE_NOT_JUNCTION=3, OPEN_FLOOR_NOT_JUNCTION=17, RENDER_VALID_BUT_VISUALLY_WEAK=2, WALL_ONLY=3.
- **Explicit `OPEN_FLOOR_NOT_JUNCTION` and `COLLINEAR_AISLE_NOT_JUNCTION` guards:** depth-openness in >=3 cardinal directions is NOT a junction on its own. All 4 dirs >= 4.0 m ⇒ `OPEN_FLOOR_NOT_JUNCTION` (open hall or a wide 4-way that visual verification must distinguish). Exactly one through-axis open with the perpendicular axis not a full crossing ⇒ `COLLINEAR_AISLE_NOT_JUNCTION` (a straight aisle — two ends of one aisle, the `p13` warehouse_full pattern, now caught automatically).
- **Contact-sheet visual verification is MANDATORY (gate 14) before any probe is confirmed `RENDER_VALID_JUNCTION`** — and, because a real walled 4-way cross-aisle reads as `OPEN_FLOOR_NOT_JUNCTION` under central-depth sampling, the OPEN_FLOOR and COLLINEAR contact sheets were ALSO inspected for a genuine walled cross. Depth + embedding is necessary but not sufficient.
- **Visual-verification overrides applied (gate 14):** NONE (no automated RENDER_VALID_JUNCTION required downgrade; the guards rejected the false positives automatically).
- **Scene character (contact-sheet verified):** `warehouse_multiple_shelves` is an **open hall with perimeter shelving**, **not a navigable aisle-grid / cross-junction**. The shelf rows line the walls of one large open floor rather than partitioning it into a corridor grid, so central-depth sampling reads open in all four cardinal directions (`OPEN_FLOOR_NOT_JUNCTION`) with no bounding corridor walls to form a branch choice.
- **p04 and p44 were visually weak but FAILED human / contact-sheet verification:** their "perpendicular open pairs" are **shelf-face-vs-open-floor corners, not angular forks** — one heading looks into a nearby shelf face (~4.7 m) while the opposite heading looks across the full open hall (~22 m). They are corner/edge views of the open floor, not two navigable diverging branches; no promotion is warranted.

## Claim boundary
- Validation-only render scan; no collection, no recording, no drive validation, no rollout, no training, no promotion, no benchmark evidence; incumbent retained; `DIAGNOSTIC_ONLY_NOT_PROMOTED`; `CL_BOUND_XY` unchanged.
- **warehouse_multiple_shelves produced zero render-valid junctions — it FAILS the Track-B render-valid-junction gate.** It was the last untried real-world-like candidate; real-asset scanning is exhausted → move to a `SYNTHETIC_DIAGNOSTIC_ONLY` fork.
- Reachable asset != usable junction; render-validity != drive-validity. **No angular branch-choice training should begin from this scene.** No real junction, no angular-branch training. Training remains blocked until a real junction, valid goal images, recorded decision frames, train/val/test splits, and a leakage audit exist.

## Artifacts
`assets/experiments/hospital_h8_track_b_multi_shelf_scan/`: `multi_shelf_render_scan_manifest.json`, `multi_shelf_render_scan_table.csv`, `multi_shelf_render_scan_report.md`, `multi_shelf_visual_similarity_matrix.{csv,md}`, `contact_sheets/`, `render_metadata/`. Harness: `scripts/gnm/h8_track_b_multi_shelf_render.py` (isaac), `scripts/gnm/h8_track_b_multi_shelf_analyze.py` (this). Raw .npy in scratchpad (not committed).
