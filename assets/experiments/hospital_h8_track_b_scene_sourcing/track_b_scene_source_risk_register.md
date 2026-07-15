# H8-M Track-B Scene Source Risk Register (SOURCING ONLY)

**Status: sourcing/inventory only — no render, no scan, no drive, no train.** Risks below are
*expected* risks to be confirmed or refuted by a later bounded render-scan; none is a measurement.

## `warehouse_multiple_shelves` (PRIMARY, real-world-like)

| risk | severity | rationale | mitigation |
|---|---|---|---|
| No real cross-aisle / T-junction exists | **HIGH** | Larger sibling `warehouse_full` had only straight parallel aisles; multi-shelf may just be denser parallel aisles | Bounded render-scan with depth-openness + **open-floor guard**; downgrade if no cross-aisle |
| Open-floor false positive | **HIGH** | Warehouses have large open floor that reads open in all directions | Open-floor guard (all 4 cardinal depths ≥ 4 m ⇒ `OPEN_FLOOR_NOT_JUNCTION`) + mandatory contact-sheet verification |
| Collinear straight-aisle false positive | HIGH | An aisle's two ends read as a 180° "branch pair" (the `p13` failure) | Reject sep ≈ 180° collinear pairs as straight corridors; require perpendicular divergence + visual check |
| Aisle visual similarity (weak distinctness) | MED | Shelving looks alike down each aisle → DINO not distinct | Embedding-distinctness gate with margin; visual verification |
| Wall-only (shelf face) false positive | MED | Shelf faces at < 2 m read as walls | Depth `< 2 m ⇒ WALL_ONLY` |
| Lighting | LOW–MED | Warehouses rendered well-lit in prior scans | DomeLight; render-validity gate |

## `synthetic_diagnostic_fork` (BACKUP, SYNTHETIC_DIAGNOSTIC_ONLY)

| risk | severity | rationale | mitigation |
|---|---|---|---|
| Mislabelled as real / benchmark evidence | **HIGH (governance)** | A synthetic scene must never be presented as real-world or SOTA | Hard label `SYNTHETIC_DIAGNOSTIC_ONLY` in every artifact; claim boundary in reports |
| Over-idealised (too clean vs real navigation) | MED | A hand-built fork may not reflect real visual clutter | Keep it a *diagnostic* only; do not generalise its result to real scenes |
| Build effort / correctness | MED | Must satisfy the geometry + visual + gate requirements | Author to the requirements doc; verify by the same bounded render-scan (gates 1–7) |
| Drivability unproven | MED | Render-valid ≠ drive-valid | Drive-validation gate before any training |

## Cross-cutting risks (all candidates)

- **Reachable ≠ usable junction; render-validity ≠ drive-validity.** Every candidate is
  `UNVERIFIED_UNTIL_RENDER_SCAN`.
- **Automated gates false-positive** (open floor, shelf, straight aisle scoring near threshold) —
  contact-sheet human verification is **mandatory** before any `RENDER_VALID_JUNCTION`.
- **Licence:** Isaac stock assets are loaded by reference under NVIDIA Omniverse/Isaac Sim terms
  (research/eval); not vendored/redistributed.
- **No training** until a scene passes render **and** drive gates and a leakage-audited split of the
  minimum size (train ≥ 12 / val ≥ 4 / test ≥ 6) exists.
