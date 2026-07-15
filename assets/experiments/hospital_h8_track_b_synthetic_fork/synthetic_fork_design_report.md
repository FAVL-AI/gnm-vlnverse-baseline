# H8-M Track-B — SYNTHETIC_DIAGNOSTIC_ONLY Fork: Design Report (DESIGN ONLY)

**Status: DESIGN / SPEC ONLY.** Nothing here is built, rendered, driven, recorded, trained,
promoted, or committed. This document specifies a small **authored** branch-choice junction to be
built and validated *later, only if approved*.

> **This is a SYNTHETIC_DIAGNOSTIC_ONLY scene. It is NOT the hospital, NOT a real-world scene, and
> NOT benchmark/SOTA evidence.** See `synthetic_fork_claim_boundary.md`.

## 1. Why a synthetic fork exists

Five real-world-like Isaac scenes were bounded-render-scanned and **all failed** the Track-B
render-valid-junction gate:

| scene | verdict | evidence commit |
|---|---|---|
| `hospital` | no junction in safe ±6 m envelope | `ff93e46` |
| `office_isaac` | open bullpen, under-lit, no junction | `21444e3` |
| `warehouse_simple` | open hall; `p32` open-floor false positive | `21444e3` |
| `warehouse_full` | open floor + straight parallel aisles; `p13` collinear false positive | `4e919ef` |
| `warehouse_multiple_shelves` | open hall with perimeter shelving, not a navigable aisle-grid | `4b350c3` |

Real-world-like stock-asset scanning is **exhausted**. The scene geometry — not the model — has been
the blocker. To test the H8 goal-conditioned angular branch-selection hypothesis at all, we author a
minimal, clearly-labelled synthetic junction whose geometry is **guaranteed by construction** and
**verifiable by the same render-scan**. A positive result isolates the model/objective question from
scene sourcing; a negative result is a clean diagnostic of the model/objective, not of asset supply.

## 2. Geometry: a four-way cross (`+`), not a left/right T

The Track-B cardinal render-scan classifies a classic left/right **T** as
`COLLINEAR_AISLE_NOT_JUNCTION`: standing at the T-center, the left and right arms are one straight
through-corridor (the analyzer sees `ns_open XOR ew_open`). That is the correct call for that
sampler — it cannot distinguish a T-center from a point along a straight corridor next to a doorway.

A **four-way cross** fixes this: both axes are through-corridors, so `ns_open == ew_open` and the
center is treated as a junction. The trained branch choice is then a genuine **perpendicular** pair,
never a collinear 180° pair.

```
                 [ N: BLUE wall + white circle ]      branch A (STRAIGHT)
                          |   |
                          | N |   arm 3.5 m
                          |   |
 [ W: GREEN +    ]-- W ---+   +--- E --[ E: ORANGE +   ]
 [ triangle ]   branch B  | X |  distractor   [ square ] (optional route C)
   (LEFT)                 |   |
                          | S |   arm 3.5 m
                          |   |
                 [ S: RED wall + white cross ]         approach / decision corridor
                        ^ start (0,-3.0) facing N
```

- **Corridor half-width** 1.0 m, **arm length** 3.5 m, **wall height** 2.5 m, **wall thickness**
  0.1 m, **robot-eye z** 0.47 m. All navigable points satisfy `|x|,|y| <= 3.5 m` — inside the 6.0 m
  safety watchdog. **`CL_BOUND_XY` is NOT modified.**
- **Decision point** = junction center `(0,0)`. **Start** `(0,-3.0)` facing north up the south arm.
- **Branch A (straight / north):** goal `(0,+3.0)`, blue wall + white circle, local action
  `STRAIGHT`.
- **Branch B (left / west):** goal `(-3.0,0)`, green wall + white triangle, local action
  `TURN_LEFT_90`.
- **Divergence A↔B = 90°** (in the preferred 60–90° band), **non-collinear**, both **cardinal** so
  the render-scan can resolve them.
- **East arm** is a distractor (optional route C, orange + square). It exists so the cross is a true
  4-way (both axes through-corridors) — it is **not** part of the primary A-vs-B pair.

## 3. Why this is EXPECTED to satisfy each Track-B gate (pending render-scan validation)

**These are expected design properties, not results.** The scene is **expected to satisfy the
render-valid junction gate, pending render-scan validation** — nothing below is proven until gates
1–7 actually run on the built USDA.

- **Render-validity (expected):** four distinctly-coloured, well-lit, unoccluded straight corridors →
  expected non-blank, luma ≥ 15, low black.
- **Depth-openness (expected):** center cardinal depths ≈ 3.5 m in all four directions → expected all
  open (≥ 3.0 m).
- **Open-floor guard (expected):** 3.5 m is `< 4.0 m`, so the guard is expected **not** to fire → the
  center is expected to be classified a junction, not `OPEN_FLOOR_NOT_JUNCTION`. (If arms are
  lengthened past ~3.9 m, expect `OPEN_FLOOR_NOT_JUNCTION` and apply the mandatory gate-5 visual
  override — a genuine walled cross is confirmed by eye.)
- **Collinear guard (expected):** `ns_open == ew_open == True` → expected **not**
  `COLLINEAR_AISLE_NOT_JUNCTION`.
- **Action-angle (by design):** trained pair is perpendicular (90° ≥ 30°) with different local
  actions.
- **Embedding distinctness (target):** blue+circle vs green+triangle vs distinct floor arrow → DINO
  cosine target `< 0.60` with margin.
- **Visual verification (mandatory):** the contact sheet must show a walled 4-way cross with four
  distinct arms — the arbiter, exactly as in every Track-B scan. Until it does, render-validity is
  **unproven**.

## 4. Honest priors and limits

- **Guaranteed junction ≠ guaranteed drive-validity.** Render-validity must still be confirmed by a
  drive-validation gate before any recording or training (render-validity ≠ drive-validity).
- **Idealised.** A hand-built cross has none of the clutter, lighting variation, or texture ambiguity
  of a real scene. Its result **must not** be generalised to real scenes or the hospital.
- **Cardinal-only.** The render-scan resolves 90° crosses, not oblique forks. A 60–70° Y-variant is
  an optional stretch that would be drive+visual validated only (flagged, not render-scan confirmed).
- **Single junction is leakage-prone.** One cross has only two goal coordinates; a leakage-safe
  train/val/test split requires a **family of ≥ 6 disjoint junction instances** (see the validation
  plan and `min_dataset` in the spec).

## 5. Artifacts in this design set

- `synthetic_fork_scene_spec.json` — full geometry, arms, visual design, render-scan expectation,
  `min_dataset`.
- `synthetic_fork_expected_routes.json` — start, decision point, routes A/B, distractor, forbidden
  (collinear) pairs.
- `synthetic_fork_validation_plan.md` — the ordered 11 validation gates + dataset/leakage rules.
- `synthetic_fork_claim_boundary.md` — what may and may **not** be claimed from this scene.
- `assets/scenes/synthetic_diagnostic_fork/synthetic_diagnostic_fork.usda` — a labelled, **UNVALIDATED**
  starting USDA implementing this geometry (not yet render-checked).

**No render, no recording, no drive, no training, no commit until reviewed and approved.**

## 5b. R2 revision — visual distinctness fix (gate-6)

The R1 render-scan (commit `be6ba04`) showed the geometry is valid (gates 1–4, 7 pass) but **gate 6
(embedding distinctness) failed**: DINO cosine 0.734 (blue vs green goal images) and 0.79 (center N
vs W), both ≥ 0.60. Contact-sheet verification confirmed the cause — the four corridors were
**structurally identical**, differing only in end-wall hue + a small centered marker, and DINO is
structure-focused and largely colour-invariant.

R2 fix: give each branch a distinct **shape family** (not just a hue), keeping the same valid 4-way
cross geometry, 90° A–B separation, and all coordinates inside `CL_BOUND_XY = 6.0`:

| branch | colour | shape family | large sign | floor prop | wall pattern |
|---|---|---|---|---|---|
| N (A, straight) | blue | **ROUND** | white circular disc | blue sphere | 3 horizontal industrial stripes |
| W (B, left) | green | **POINTED** | yellow triangular (cone) | green cone | dark chevron |
| E (distractor) | orange | **BOXY** | white square | orange crate (cube) | dark checker tiles |
| S (approach) | red | **CYLINDRICAL** | — | red cylinder | dark vertical bars |

Depth-safety: signs sit **high** on the end wall and wall patterns are **flush** (depth kept
≥ 3.0 m); floor props are **offset + low** so the central depth-openness reading is preserved. Result
is verified by re-running render-scan gates 1–7 (see
`assets/experiments/hospital_h8_track_b_synthetic_fork_validation_r2/`). No hue-only or small-marker-
only differences remain.

## 6. Claim boundary (canonical statements — apply to every artifact in this design set)

1. This is a **SYNTHETIC_DIAGNOSTIC_ONLY** scene.
2. It is **not hospital evidence**.
3. It is **not real-scene / real-world evidence**.
4. It is **not benchmark evidence**.
5. It is **not promotion** (`DIAGNOSTIC_ONLY_NOT_PROMOTED`; incumbent retained).
6. It is **not full goal-conditioned ImageNav evidence**.
7. It is **not SOTA**.
8. It makes **no autonomy claim**.
9. It carries **no training authorization** (training remains blocked).
10. **`CL_BOUND_XY` is unchanged** (6.0 m watchdog untouched).
11. **One cross is not enough** for a leakage-safe train/val/test split (a single junction has only two goal coordinates).
12. **Future training requires a family of at least 6 disjoint junction instances** (split by instance; no cross-split reuse of frames/goals/coordinates/instances).
