# H8 Synthetic Fork — Recorded-Mode Plan (PLAN ONLY)

**Status: PLAN ONLY.** This document defines the next gate after render-validation and
drive-validation for the `SYNTHETIC_DIAGNOSTIC_ONLY` fork. It authorises **nothing**: no recording,
no trajectory collection, no train/val/test data creation, no action-probe, no training, no
promotion, no push, no tag, no 20/5/10, no closed-loop policy testing. `CL_BOUND_XY` is unchanged
(6.0 m absolute watchdog, untouched). Building or running any of the steps below begins only on
explicit review approval.

> **Boundary.** Drive-validation passed, but **training is still blocked.** The next evidence needed
> is a leakage-safe recorded-mode plan, then data capture, then split/leakage audit, then
> action-probe readiness — each separately reviewed. This document is the first of those and produces
> no data.

## 1. Purpose

The synthetic diagnostic fork has now passed **two committed prerequisite gates**:

- **Render-valid reassessment — commit `0eea29f`** (`Add synthetic fork R4 reassessment evidence`):
  reassessed classification **`RENDER_VALID_JUNCTION`** under the reviewed **Outcome A + E**
  distinctness rule (embedding distinctness advisory only on the symmetric cross; required gates =
  scene-load, render-validity, depth-openness, open-floor guard, mandatory visual/contact-sheet
  verification, and action-angle separation).
- **Drive-validation PASS — commit `935ed85`** (`Add synthetic fork drive validation pass evidence`):
  physical drivability certified under bounded scripted low-speed probes with colliders established
  and floor support correctly distinguished from obstacle collision.

**Neither of these authorises training.** Render-validity proves the branches look like a valid
junction; drive-validity proves a body with real extent can physically traverse them. Producing
*learning data* is a distinct, higher-bar step: it needs controlled observation/goal/action examples,
a leakage-safe split family, and an audit — none of which exist yet. **Recorded-mode must be planned
(this document), reviewed, and only then dry-run** before any real data capture. This plan implements
no code, records nothing, and trains nothing.

## 2. Current evidence

- Claim boundary: **`SYNTHETIC_DIAGNOSTIC_ONLY`** — an authored idealised 4-way cross; a diagnostic of
  the model/objective, never hospital, real-scene, or benchmark evidence.
- Render-valid classification: **`RENDER_VALID_JUNCTION`** (commit `0eea29f`); embedding distinctness
  DINO **advisory only** (Outcome E) on the symmetric cross; real-scene DINO recalibrated to ≈0.76
  with margin (Outcome A) applies to real scenes, not this synthetic fork.
- Drive-validation (commit `935ed85`, harness commit `ddc3f75`): **`pass=True`**, process exit code
  agrees with the manifest verdict.
  - **61 colliders** applied (44 Cube + 4 Sphere + 9 Cone + 4 Cylinder); collider provenance populated.
  - **Obstacle contacts: 0** (static pre-check and both probes; obstacle `hit_prims` empty).
  - **Support contacts: 2** (`/World/Scene/Structure/Floor` and `/World/Scene/Structure/S_floor_strip`,
    the latter a ~4 cm flat floor cue — support, not obstacle).
  - **Both N and W probes completed** (reached, advanced 0.6 m, 240 steps each, 0 contacts, not
    timed out); 480 pose-trace samples (240 per probe); no timeouts.
  - **All poses in bounds** — spawn, both probes, safe-halt well inside the watchdog.
  - `compute_verdict()` had **no incomplete fields**.
- Geometry (authored scene): 4-way cross, junction centre `(0,0)`, spawn `(0, −3.0)` facing north
  (heading 90°), arms ≈ 3.5 m deep, North corridor native half-width ±1.0 m, West corridor narrowed
  to ±0.78 m, wall height 2.5 m, robot-eye camera z ≈ 0.47 m; all navigable extent `|x|,|y| ≤ 3.5 m`.
- **`CL_BOUND_XY = 6.0` unchanged** (read-only watchdog; every drive-validation pose stayed inside it).

## 3. Recorded-mode objective

Recorded-mode must produce **controlled, labelled examples** for a goal-conditioned branch-choice
diagnostic — and nothing else. Specifically it must produce:

- **Controlled observation / goal / action examples** — each example is (observation image o_d at the
  decision frame, goal image, local action label), captured under fixed, reproducible poses.
- **Decision-frame images** — the robot-eye view at the junction centre `(0,0)` facing the approach
  heading, from which the branch decision is made.
- **Goal A / goal B images** — the branch-endpoint views (e.g. North branch goal, West branch goal)
  that condition the choice; each goal image tied to a specific branch.
- **Scripted / expert local action labels** — the correct short-horizon action for reaching each goal
  from the decision frame (e.g. STRAIGHT for North, TURN_LEFT_90 for West), computed by a **scripted
  policy-free rule** from known geometry — never by a learned policy.
- **Branch-choice labels** — a discrete label per (decision-frame, goal) pair naming the chosen branch
  (N / W / E / …) and its expected action class.
- **Metadata needed for leakage audit** — instance ID, decision-frame ID, goal-image ID, coordinates,
  hashes, split assignment (see §7).
- **No policy inference** — no GNM/goal-conditioned model is loaded or queried at any capture step;
  motion and labels are scripted.
- **No model training** — recorded-mode outputs data + audit only; training is a later, separately
  gated step.

## 4. Dataset design

**One cross instance is not enough for a leakage-safe train/val/test split.** A single 4-way cross has
only a small fixed set of goals (N/W/E/S) and one decision coordinate; splitting it would reuse the
same frames, goal images, and coordinates across train/val/test → guaranteed contamination.
Recorded-mode therefore requires a **family of disjoint synthetic fork instances** (varied by colour
permutation, marker/shape family, arm length/width, floor cue, and cross orientation) so that splits
can be made across *instances* with no shared frames.

**Minimum target (leakage-safe):**

- **train ≥ 12 decision frames**,
- **val ≥ 4 decision frames**,
- **test ≥ 6 decision frames**,
- **at least 6 disjoint junction instances if possible** (so each split draws from different instances),
- **no reused decision frame across splits**,
- **no reused goal image across splits**,
- **no coordinate reuse across splits** (a decision/goal coordinate that appears in train must not
  appear in val or test).

If the family cannot reach these counts with genuine disjointness, recorded-mode is **not feasible at
target scale** and must be re-scoped (more instances, or a documented smaller-scale diagnostic clearly
labelled as under-powered) — it must **not** be shipped as a leaky split.

## 5. Route families

Recorded-mode should draw decision/goal pairs from these families, with the angular branch-choice
families as the primary scientific content:

- **North vs West 90° branch choice** — primary angular branch choice (STRAIGHT vs TURN_LEFT_90),
  non-collinear, ≈ 90° apart.
- **North vs East 90° branch choice if supported** — the mirror angular choice (STRAIGHT vs
  TURN_RIGHT_90), included where the east arm renders and drives valid.
- **West vs East opposite-direction control** — a left-vs-right (≈180° apart) pair, included **only if
  clearly marked SECONDARY** (it is a collinear/opposite control, not a fresh angular fork — this is
  the H8-S collinearity lesson; it must never be counted as a primary angular example).
- **Same-start different-goal branch choice** — same decision frame o_d, different goal image → the
  action must change with the goal (the core goal-conditioning test).
- **Hard-negative mismatched goal** — a decision frame paired with a goal from a *different* instance
  or a non-adjacent branch, expected to be flagged/handled as a negative (tests goal sensitivity, not
  a positive training target).
- **Near/far stop-distance examples** — distance/stop-axis pairs (H8-S style), included **only as
  SECONDARY** (they do not test angular branch choice).

## 6. Recording protocol (plan only)

All steps below are **validation/capture design only** — nothing is executed by this document. When
later approved, each is bounded, low-speed, policy-free, and carries a per-episode timeout wrapper
with return-code capture (no process-pattern kills).

- **Scene instance creation or parameterized variants** — generate the disjoint fork instances (§4)
  from the labelled `SYNTHETIC_DIAGNOSTIC_ONLY` base, varying colour/marker/arm/orientation; each
  instance re-passes render-validity + drive-validity before it may contribute frames.
- **Spawn pose list** — per instance, the spawn pose(s) (e.g. `(0, −3.0)` heading 90°) with valid
  articulation state, mirroring the drive-validation spawn.
- **Decision-frame pose list** — the junction-centre pose(s) `(0,0)` at each approach heading from
  which o_d is captured.
- **Goal-image pose list** — per branch, the goal-view pose (branch endpoint, robot-eye height
  ≈ 0.47 m) captured at a render-valid standoff (non-black, unoccluded).
- **Scripted action generation** — the correct local action per (decision-frame, goal) computed from
  known geometry by a fixed rule (STRAIGHT / TURN_LEFT_90 / TURN_RIGHT_90 / …); **no policy**.
- **Camera capture settings** — resolution, clipping range, exposure/lighting matching the render and
  drive gates; RGB (and depth if needed) captured deterministically.
- **Metadata schema** — per example: instance_id, decision_frame_id, goal_image_id, branch label,
  expected action class, spawn/decision/goal coordinates, heading, camera params, image hash, split
  assignment, provenance (scene file, commit, timestamp source), claim-boundary tag.
- **Per-frame provenance** — record which instance/scene/commit each frame came from so leakage and
  reproducibility are auditable.
- **Collision/contact check during capture** — reuse the drive-validation contact classification
  (floor/ground → support; walls/panels/props/markers → obstacle) so no frame is captured from a
  penetrating/blocked pose; obstacle contact aborts that frame.
- **Safe halt** — zero-velocity safe-halt on normal completion and on exception at every capture step.
- **Timeout guard** — each capture step runs under a bounded wall-clock timeout with return-code
  capture; on timeout, halt safely and record the rc (no kill-by-name).

## 7. Leakage audit requirements

Before any training, a leakage audit must confirm:

- **Unique instance IDs** — every fork instance has a stable unique ID.
- **Unique goal image IDs** — every goal image has a unique ID; no ID appears in more than one split.
- **Unique decision-frame IDs** — every decision frame has a unique ID; no ID appears in more than one
  split.
- **Split assignment before training** — train/val/test membership is fixed and recorded **before**
  any training is considered (no post-hoc reassignment).
- **Coordinate reuse check** — no decision/goal coordinate (within a tolerance) is shared across
  splits.
- **Goal image hash check** — perceptual/byte hashes of goal images are disjoint across splits (no
  identical goal image in two splits).
- **Near-duplicate visual check** — a contact-sheet / embedding near-duplicate scan across splits
  (same lesson as the distinctness gate: two visually near-identical instances must not straddle
  train and test).
- **No train/val/test contamination** — the audit fails closed if any of the above is violated;
  training stays blocked until the audit passes and is reviewed.

## 8. Allowed artifacts after future recording

When recording is later approved and run, it may produce **only** these artifacts:

- a **recorded-mode manifest** (instances, poses, capture config, claim boundary);
- an **image index** (decision-frame + goal images with IDs, hashes, provenance);
- an **action-label table** (per example: branch label + expected action class + generating rule);
- a **split manifest** (train/val/test membership by instance/frame/goal ID);
- a **leakage audit report** (the §7 checks + pass/fail);
- a **contact/collision log** (per-frame support/obstacle classification during capture);
- a **recording report** (per-criterion pass/fail + claim boundary).

It must **not** produce:

- **trained model weights**,
- **checkpoints**,
- **wandb** runs/logs,
- **rollout metrics** (no TL / NE / SR / OSR / SPL / nDTW / CR),
- **benchmark claims**,
- **promotion** (incumbent retained; `DIAGNOSTIC_ONLY_NOT_PROMOTED`).

## 9. Claim boundary

- **`SYNTHETIC_DIAGNOSTIC_ONLY`** — authored idealised junction; a diagnostic of the model/objective.
- **Not hospital evidence.**
- **Not real-scene / real-world evidence.**
- **Not benchmark evidence.**
- **Not full goal-conditioned ImageNav evidence.**
- **No SOTA.**
- **No rollout metrics** — no TL / NE / SR / OSR / SPL / nDTW / CR (there is no policy rollout in
  recorded-mode).
- **No policy inference. No model training.**
- **No promotion** (`DIAGNOSTIC_ONLY_NOT_PROMOTED`; incumbent retained).
- **No autonomy claim.**
- **Not training authorization** — a passing recorded-mode plan/capture/audit is a prerequisite, not a
  license to train.
- `CL_BOUND_XY` unchanged (6.0 m watchdog untouched). This plan implements no code, records nothing,
  creates no dataset, and trains nothing.

## 10. Next gate after plan

**Only after this plan is reviewed and approved:**

1. **implement the recorded-mode harness if needed** (validation/capture-only; deferred Isaac imports;
   fail-closed contact classification reused from drive-validation; refuses train/rollout/action-probe
   flags) — as a reviewed code change, not run;
2. **then run a small recording dry-run** (one or few instances, schema + a handful of frames) to
   verify the manifest/label/provenance shape — reviewed before scaling;
3. **then produce the leakage audit** (§7) over the captured family — reviewed;
4. **then action-probe readiness** (does conditioning on goal A vs goal B at the same decision frame
   change the predicted action?) — a later, separate gate;
5. **then review before training.**

**Training remains blocked** until recorded-mode plan (this doc) → recorded data capture →
split/leakage audit → action-probe readiness → review approval **all** pass.

---

```text
Drive-validation passed, but training is still blocked. The next evidence needed is a leakage-safe
recorded-mode plan, then data capture, then split/leakage audit, then action-probe readiness.
```
