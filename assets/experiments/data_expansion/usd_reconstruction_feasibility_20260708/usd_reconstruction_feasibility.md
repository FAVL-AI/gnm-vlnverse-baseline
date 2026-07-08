# USD Reconstruction Feasibility — Stage 3A (kujiale_0092)

USD reconstruction is being assessed as an engineering prerequisite for
larger VLNVerse/VLNTube training-data generation. No new generated
training data has been added yet.

## Verdict: FEASIBLE — and reconstruction is NOT required

The premise of Stage 3 was that composed scene USDs would need to be
rebuilt from raw meshes (`vlntube_index.json` reports
`usd_scene_count: 0`). The inventory falsified that premise: **every one
of the four local scenes already ships an ~11 MB composed stage**
(`start_result_navigation.usd`) referencing 654 per-object USD meshes
with MDL materials. The index simply looked for a different filename
pattern.

## The actual blocker, found and solved

The composed stage references its meshes with paths relative to the
original authors' working directory
(`datasets/vlntube/envs/<scene>/Meshes/…`), which USD resolves relative
to the layer's own location — producing a doubled path and 654 broken
references on open. Fix: one relative symlink inside each scene dir
(`ln -s ../../.. datasets`) makes the doubled path resolve to the real
mesh directory. Zero file modification; broken references drop 654 → 0.
The symlink lives under the gitignored `datasets/` tree and must be
recreated per checkout (documented in recommended_next_steps.md).

## Isaac load-and-render smoke (evidence)

Headless Isaac 5.1 opened the fixed stage, composed all geometry, and
rendered a 640×480 RGB frame from a camera at the occupancy-map centre:
92.9% non-black, mean intensity 141 — real walls, floor materials and
lighting (`kujiale_0092_render_smoke.ppm`). Cosmetic Hydra warnings
about displayColor primvar sizes on some floor/window meshes do not
block rendering.

## Honest scope

- Camera placement used the raw occupancy `center` with a default
  orientation (looking down); the coordinate convention between
  occupancy.json/occupancy.png and stage world space still needs
  calibration before trajectory rendering (Stage 3B, first task).
- One valid rendered **trajectory** — the full Stage 3 gate — has not
  been produced yet; this report claims scene loading and single-frame
  rendering only.
- kujiale_0271 (test scene) was not touched.
