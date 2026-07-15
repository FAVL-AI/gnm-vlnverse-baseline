# H8-M Track-B — SYNTHETIC_DIAGNOSTIC_ONLY Fork: Validation Plan (PLAN ONLY)

**Status: PLAN ONLY.** No render, no drive, no recording, no training, no promotion, no commit is
authorised by this document. This is the ordered gate sequence to run *later, only if approved*.

> **SYNTHETIC_DIAGNOSTIC_ONLY** — a pass here is diagnostic evidence about the model/objective on an
> idealised junction, never real-scene, hospital, or benchmark evidence. `CL_BOUND_XY` unchanged.

## Reviewed distinctness-gate decision (Outcome A + E) — documentation/planning only

**Adopted in `docs/research/H8_TRACK_B_DISTINCTNESS_GATE_DECISION.md` (commit `53106f3`), on the
labelled calibration evidence in `assets/experiments/hospital_h8_track_b_distinctness_calibration/`
(commit `d5e5e25`).** This is a **documentation/planning update only — no metric is implemented, no
threshold is applied in code, no operational metric is switched.**

- **Outcome A (real indoor scenes):** the DINO distinctness gate is to be **recalibrated around
  ≈0.76 with documented margin and contact-sheet agreement**, replacing the arbitrary absolute
  `< 0.60` — *pending later, separately-reviewed implementation.* (Real hospital pairs separate
  cleanly: SAME 0.83–0.92 vs DISTINCT 0.26–0.68; `< 0.60` was too strict and would miss a real
  distinct pair at 0.68.)
- **Outcome E (this synthetic symmetric fork):** **DINO distinctness is ADVISORY ONLY.** On a
  symmetric 4-way cross every arm shares the same corridor perspective/composition, so DINO cosine
  does not separate same-from-distinct (it overlaps and even inverts) and **must not be used as a
  hard pass/fail gate here.** Gate 6 below is therefore **recorded as advisory**, not a blocker.
- **Required synthetic-fork render-validation gates are 1, 2, 3, 4, 5, and 7** (scene-load,
  render-validity, depth-openness, open-floor guard, visual/contact-sheet verification, action-angle
  separation). Gate 6 (embedding distinctness) is advisory and does not gate progression.
- **The synthetic fork cannot proceed to training until ALL of:** drive validation (gate 8) passes,
  recorded-mode data (gate 9) exists, split/leakage audit (gate 10) passes, task-level action-probe
  (gate 11) readiness passes, **and** review approval is given.
- All claim boundaries below are preserved (`SYNTHETIC_DIAGNOSTIC_ONLY`; not hospital / real-scene /
  benchmark evidence; no full ImageNav claim; no SOTA; no promotion; no autonomy claim).

**Revision status:** R1 (`be6ba04`) failed gate 6. R2 (`6930b65`) added shape families, improved but
still failed. R3 (`201f91b`) made the corridor shell branch-specific + pulled goal cameras back — gate
6 **worsened** (0.62 → 0.654, 0.649 → 0.689), isolating the cause as DINO sensitivity to the shared
corridor **perspective geometry**. R4 changes the geometry itself: large branch-specific high objects
(N sphere, W cone, E cube, S columns) dominating the upper goal frame + a narrowed West corridor,
with goal images at 1.5 m and 2.0 m standoff; **no metric/threshold change.** Gates 1–7 re-run under
`assets/experiments/hospital_h8_track_b_synthetic_fork_validation_r4/`. Drive-validation (gate 8) and
everything after remain deferred until gates 1–7 pass and are reviewed.

## Ordered validation gates

Required render-validation gates for the synthetic fork are **1, 2, 3, 4, 5, 7** (each must pass
before the next). **Gate 6 (embedding distinctness) is ADVISORY ONLY** for this symmetric fork per
the Outcome A + E decision above — its cosine is recorded, but it does not pass or fail the scene.

1. **Scene-load gate** — the USDA loads; `defaultPrim` resolves; expected prims present (floor, 4
   corridor arms, 4 coloured end panels, markers, dome); interior footprint is sane (bounded ≈
   ±3.5 m, no skybox-outlier world bbox). Fail ⇒ fix the USDA before anything else.

2. **Render-validity gate** — render the decision view and both goal views (goal A north, goal B
   west): non-blank, `luma >= 15`, low lower-frame black fraction, unoccluded straight corridors.

3. **Depth-openness gate** — at the decision point `(0,0)`, both branch headings have median central
   depth `>= 3.0 m` (design ≈ 3.5 m); the approach (south) is also open. Uses
   `distance_to_image_plane`, not luma/DINO alone (the hospital false-positive lesson).

4. **Open-floor guard** — confirm the center does **not** read all-4 cardinal depths `>= 4.0 m`
   (design 3.5 m ⇒ guard silent ⇒ junction). If a longer-arm variant reads `OPEN_FLOOR_NOT_JUNCTION`,
   it may proceed **only** via the gate-5 visual override, never automatically.

5. **Visual verification (mandatory, gate-14 discipline)** — a human/contact-sheet check confirms a
   walled 4-way cross with four distinct coloured/marked arms — **not** an open floor, collinear
   aisle, shelf face, or dead end. This is the arbiter; depth + embedding are necessary but not
   sufficient. No probe is `RENDER_VALID_JUNCTION` without it. Any override is recorded auditable.

6. **Embedding distinctness (ADVISORY ONLY for this symmetric fork).** Record DINO ViT-S/16 cosine
   between the two trained goal views. **This is not a hard pass/fail gate here** (Outcome E): a
   symmetric cross shares the same corridor perspective, so DINO does not separate same-from-distinct
   on it. The advisory cosine is logged alongside the mandatory gate-5 visual verification. *For real
   indoor scenes* (not this synthetic fork), the distinctness gate is to be recalibrated to a DINO
   threshold ≈0.76 with margin and contact-sheet agreement (Outcome A), pending later implementation —
   **not** applied in code by this plan.

7. **Action-angle separation gate** — the two branch headings diverge `>= 30°` (design 90°) and map
   to **different local actions** (`STRAIGHT` vs `TURN_LEFT_90`).

8. **Drive-validation gate** — the robot actually traverses approach → decision → each goal within
   `|x|,|y| <= CL_BOUND_XY (6.0)` with no collision; **both** branches are reachable and stoppable at
   the goal. **Render-validity ≠ drive-validity** — this gate is where that is proven.

9. **Recorded-mode gate** — record decision-frame + branch-frame episodes in the same pipeline format
   as the hospital data (goal image, observation, action), verifying the recorder emits valid,
   parseable episodes with correct goal conditioning.

10. **Leakage audit** — verify train/val/test draw from **disjoint junction instances** so no frame,
    goal image, coordinate, or instance id crosses splits. Goal images are hashed; coordinates and
    instance ids checked disjoint. Fail ⇒ do not train.

11. **Action-probe / training diagnostics** — *only after gates 1–10 pass:* run the H8 goal-conditioned
    action probe — does conditioning on goal A (north/blue) vs goal B (west/green) at the **same**
    decision frame change the predicted action (straight vs left)? Then any training diagnostics.
    This is the actual causal test the whole track exists to run.

## Minimum future dataset (leakage-safe)

- **train ≥ 12, val ≥ 4, test ≥ 6 episodes** (≥ 22 total).
- **Instance family required:** ≥ 6 **disjoint** junction instances (vary colour permutation, marker
  shapes, arm length 3.2–3.8 m, floor-cue variant, cross orientation).
- **Split by instance:** train ≥ 3 instances, val ≥ 1, test ≥ 2 — **disjoint**; episodes within a
  split come only from that split's instances via start-pose jitter.
- **No cross-split reuse** of frames, goal images, coordinates, goal ids, or junction instances. A
  single cross has only 2 goals, so a leakage-safe split is impossible without the instance family.

## Decision rule

- **Required render gates 1, 2, 3, 4, 5, 7 pass + gate-5 visual confirmation (gate 6 advisory cosine
  recorded) ⇒** hold for review before drive-validation. Do not treat render-validity as
  drive-validity, and do not block on the advisory DINO cosine.
- **Gate 8 drive-validation passes ⇒** hold for review before any recording/training.
- **Training remains blocked until ALL of** gate 8 (drive validation), gate 9 (recorded-mode data),
  gate 10 (split/leakage audit), gate 11 (action-probe readiness) **pass and review approval is
  given.**
- **Any required gate fails ⇒** stop; do not force a claim; fix the scene or revisit the design. A
  negative action-probe (gate 11) after all prior gates pass is itself a valid, publishable diagnostic
  result.

## What this plan does NOT authorise

No render, no drive, no recording, no training, no promotion, no push, no tag, no 20/5/10, no
closed-loop, no `CL_BOUND_XY` change. Build/validation begins only on explicit approval.

## Claim boundary (canonical statements — apply to every artifact in this design set)

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
