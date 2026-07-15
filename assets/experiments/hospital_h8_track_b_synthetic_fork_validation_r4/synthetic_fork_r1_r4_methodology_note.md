# Synthetic Diagnostic Fork — R1→R4 Methodology Note (metric-suitability)

**Status: methodology note, validation-only.** No drive-validation, no recording, no trajectory
collection, no training, no promotion. **No metric or threshold change was applied.** `CL_BOUND_XY`
unchanged. SYNTHETIC_DIAGNOSTIC_ONLY — not hospital / real-scene / benchmark / SOTA evidence.

## Question
Can an authored, idealised 4-way-cross junction be made to pass a **DINO ViT-S/16 cosine < 0.60**
goal-branch distinctness gate by changing the **scene** (appearance and/or geometry), without changing
the metric or threshold?

## What was tried, and the measured DINO cosine (lower = more distinct; gate wants < 0.60)

| rev | scene change (all keep the valid 4-way cross, 90° N–W, depth-openness 3.5 m, CL_BOUND_XY 6.0) | center N-vs-W | goal images |
|---|---|---|---|
| R1 | flat-colour end walls + small centered marker | 0.79 | 0.734 |
| R2 | distinct **shape families** per branch (large sign + floor prop + wall pattern) | **0.62** | **0.649** |
| R3 | branch-specific **corridor shell** (tinted side walls + floor strips + reliefs) + goal-camera pull-back to 2.3 m | 0.654 | 0.689 |
| R4 | per-branch **geometry** (narrowed West corridor) + **dominant foreground objects** (N sphere / W cone / E cube / S columns) + dual goal standoff (1.5 / 2.0 m) | 0.696 | 0.703 |

Every revision keeps geometry gates 1–4 and 7 **PASS** (scene-load, render-validity, depth-openness,
open-floor guard, action-angle 90°). Only **gate 6** fails, at every revision.

## Findings
1. **No scene change reached < 0.60.** Colour, decor, shape-family props, branch-specific shells,
   per-branch corridor geometry, dominant foreground objects, and camera standoff were all exercised.
2. **More effort did not help — it hurt.** The best distinctness was **R2 (0.62)**; adding more
   per-branch structure (R3, R4) **increased** cosine (to 0.654, then 0.696). Giving every arm a big
   central object + floor strip + reliefs produces a **shared "decorated corridor with a central
   object" composition** that DINO encodes similarly.
3. **Large human–DINO disagreement.** By eye the R4 corridors are dramatically distinct (blue-round /
   orange-boxy / green-narrow-pointed / red-columned), yet DINO puts them at ~0.70. DINO ViT-S/16 is
   strongly sensitive to the **shared corridor perspective/composition** that any symmetric cross
   necessarily has, and largely invariant to the colour/decor/geometry edits that a human uses to tell
   the branches apart.

## Conclusion
For this synthetic 4-way-cross corridor family, **`DINO cosine < 0.60` is an unsuitable /
miscalibrated distinctness gate.** The blocker is the **metric**, not the scene design — the scene
appearance/geometry space has been substantially explored across four revisions with no success and a
non-monotone (worsening) trend.

## Recommended next decision (to propose — NOT executed; requires review)
- **Calibrate the gate rather than move the threshold.** Compute DINO cosine on **known-distinct**
  real goal pairs (e.g. already-rendered hospital / warehouse views) and on **known-same** pairs. If
  genuinely-distinct indoor corridors also sit ~0.6–0.7, the absolute `< 0.60` threshold is wrong for
  this domain and should be replaced with a **relative / calibrated** criterion.
- **Or** use a colour/semantic-sensitive encoder (e.g. CLIP) or the **actual goal-conditioned policy
  encoder** as the distinctness metric — that is what a policy would really use.
- Only if a **calibrated** metric still shows the branches as non-distinct should the scene be judged
  inadequate. Changing the threshold without this calibration would look like moving the goalpost and
  is **not** done here.

## Boundary
Nothing here authorises drive-validation, recording, collection, training, promotion, push, tag,
20/5/10, or closed-loop testing. `CL_BOUND_XY` unchanged. Held for review.
