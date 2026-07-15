# H8-M Track-B — SYNTHETIC_DIAGNOSTIC_ONLY Fork: Claim Boundary

**Status: DESIGN ONLY.** This document governs what may and may **not** be claimed from the synthetic
fork scene, before it is built or run.

**Revision R2:** the scene was built and render-scanned. R1 (commit `be6ba04`) proved the **geometry**
is valid but **failed gate 6 (visual distinctness)** — so nothing about goal-conditioning can be
claimed yet. R2 revises the branch visuals (distinct shape families) and re-runs render-scan gates
1–7. Even a full gates-1–7 pass is only render-validity, not drive-validity, and authorizes no
training.

## Hard label

**`SYNTHETIC_DIAGNOSTIC_ONLY`.** This scene is **authored** by the project, not a real or vendored
asset. It exists solely to test the H8 goal-conditioned angular branch-selection hypothesis in
isolation, after five real-world-like Isaac scenes (`hospital`, `office_isaac`, `warehouse_simple`,
`warehouse_full`, `warehouse_multiple_shelves`) failed the Track-B render-valid-junction gate.

## May be claimed (only after the full validation plan passes)

- "On an **idealised, authored** 4-way cross junction, the goal-conditioned model **does / does not**
  change its decision-frame action when conditioned on branch A (north) vs branch B (west)." — an
  isolated **diagnostic** of the model/objective.
- That the diagnostic separates the **model/objective** question from the **scene-sourcing** question
  (which real Isaac stock assets could not answer).
- A **negative** action-probe result is a legitimate, publishable diagnostic of the model/objective.

## MUST NOT be claimed

- **Not** hospital evidence. **Not** real-world evidence. **Not** benchmark, SOTA, or leaderboard
  evidence. **Not** an autonomy or deployment claim.
- **Not** transferable: a positive result on this clean synthetic cross does **not** imply the model
  navigates real cluttered junctions. Do not generalise it to real scenes.
- **Not** a substitute for a real junction. It does not retroactively make `hospital` support angular
  branch-choice; Track-A (hospital = distance/stop-axis diagnostics only) is unchanged.
- **Not** promoted: `DIAGNOSTIC_ONLY_NOT_PROMOTED`; the incumbent checkpoint is retained.

## Governance invariants

- **`CL_BOUND_XY` unchanged** (6.0 m safety watchdog untouched; the scene fits inside ±3.5 m).
- **No training** is authorised by this design. Training remains blocked until the scene passes all
  render **and** drive gates and a leakage-audited split of the minimum size (train ≥ 12 / val ≥ 4 /
  test ≥ 6, disjoint instances) exists.
- **Render-validity ≠ drive-validity; guaranteed-by-construction ≠ drive-valid.** Every gate must be
  passed in order, with mandatory human visual verification, exactly as for real scenes.
- **Labelling:** every artifact, report, figure, and any future paper mention must carry the
  `SYNTHETIC_DIAGNOSTIC_ONLY` label. It is never presented as a real-scene or benchmark result.

## Boundary line

> No real T/Y/cross junction exists in the scanned real assets, so real-scene angular-branch training
> stays blocked. The synthetic fork tests the **model**, not the hospital — and only under a hard
> `SYNTHETIC_DIAGNOSTIC_ONLY` label.

## Canonical statements (apply to every artifact in this design set)

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
