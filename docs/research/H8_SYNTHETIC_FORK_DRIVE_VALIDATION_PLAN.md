# H8 Synthetic Fork — Drive-Validation Plan (PLAN ONLY)

**Status: PLAN ONLY.** This document defines the next gate after render-validation for the
`SYNTHETIC_DIAGNOSTIC_ONLY` fork. It authorises **nothing**: no drive-validation run, no recording,
no trajectory collection, no action-probe, no training, no promotion, no push, no tag, no 20/5/10, no
closed-loop Isaac testing. `CL_BOUND_XY` is unchanged (6.0 m absolute watchdog, untouched). Building
or running any of the checks below begins only on explicit review approval.

> **Boundary.** The next question is not whether the model can train. The next question is whether the
> synthetic fork is physically drivable without collisions, clipping, or invalid camera/robot state.
> Only after that can recorded-mode data be planned.

## 1. Purpose

The synthetic diagnostic fork has passed the render-validation gates **1 (scene-load), 2
(render-validity), 3 (depth-openness), 4 (open-floor guard), 5 (visual/contact-sheet verification),
and 7 (action-angle separation)** under the reviewed **Outcome A + E** distinctness rule, with gate 6
(embedding distinctness) reported as **advisory only**. **Render-validity is not drive-validity.** A
scene that renders as a valid 4-way cross with distinct, depth-open branches may still be physically
un-drivable — the robot could clip a wall, fail to spawn, hit an invisible collider, or reach a branch
that is navigable to the free camera but blocked to a body with real extent. This plan defines the
**drive-validation gate (gate 8)** that must pass — and be reviewed — before any recorded-mode data
(gate 9) is even planned.

## 2. Current evidence

- **R4 reassessment committed `0eea29f`** (`Add synthetic fork R4 reassessment evidence`), reusing the
  committed R4 render (no re-render).
- Reassessed classification: **`RENDER_VALID_JUNCTION`**.
- Outcome: **`SYNTHETIC_FORK_RENDER_VALID_PENDING_DRIVE_VALIDATION_HOLD_FOR_REVIEW`**.
- Embedding distinctness: **DINO advisory only** (goal-image cosine 0.703, center N-vs-W 0.696; not a
  pass/fail gate on a symmetric cross — Outcome E).
- Action-angle: designed branch pair A=N (STRAIGHT) vs B=W (TURN_LEFT_90), separation **≈ 90°**.
- Geometry (from the authored scene): 4-way cross, junction centre `(0,0)`, start/spawn `(0, −3.0)`
  facing north (heading 90°), arms ≈ 3.5 m deep, North corridor native half-width ±1.0 m, West
  corridor narrowed to ±0.78 m, wall height 2.5 m; all navigable extent `|x|,|y| ≤ 3.5 m`, well inside
  the `CL_BOUND_XY = 6.0` watchdog.
- Claim boundary: **`SYNTHETIC_DIAGNOSTIC_ONLY`** — a diagnostic of the model/objective on an
  idealised junction, never hospital, real-scene, or benchmark evidence.

## 3. Drive-validation objective

Prove — physically, with no policy/model inference — that:

- the robot can **spawn safely** at `(0, −3.0)` facing north, in a valid articulation state;
- the robot can **face the decision frame** at the junction centre `(0,0)`;
- the **candidate goals are reachable** (approach → decision → each branch goal within the safe
  envelope);
- **branch N and branch W are both physically navigable** to a body with real extent (not just to the
  free camera);
- there is **no immediate collision** on spawn or during the short probes;
- there is **no wall clipping** (the body does not intersect corridor walls, especially the narrowed
  West corridor at ±0.78 m);
- there is **no blocked corridor** (no invisible collider, prop, or liner wall obstructs a branch);
- there is **no invalid physics/articulation state** (no NaN pose, no explosion, no dropped-through
  floor, no joint blow-up);
- there is **no safety-bound change** — `CL_BOUND_XY` stays 6.0 and the run stays inside it.

## 4. Validation protocol (checks to run later, only if approved)

All checks are **validation-only**, bounded, low-speed, and carry a per-episode timeout wrapper with
return-code capture (no process-pattern kills). No policy/model inference at any step.

1. **Scene load** — load `assets/scenes/synthetic_diagnostic_fork/synthetic_diagnostic_fork.usda`;
   confirm prims, bounded interior bbox, lighting (as in the render gate); fail-closed on mismatch.
2. **Robot spawn pose** — spawn the drive robot (the Yahboom M3Pro articulation used in the Track-A /
   H7 drive pipeline) at `(0, −3.0, floor)` heading 90°; assert a valid articulation state
   (finite root pose/velocities, joints within limits, no interpenetration at t=0).
3. **Camera pose** — attach the robot-eye camera at z ≈ 0.47 m, level horizon; confirm the decision
   frame renders (non-black, unoccluded) from the spawned body, matching the render-gate view.
4. **Static collision check** — before any motion, query the physics scene for existing contacts
   between the robot body and scene colliders; require **zero** static penetration.
5. **Short low-speed scripted probe toward North** — a bounded, low-speed, open-loop velocity/pose
   nudge from the decision point a short distance up the North corridor (a few tenths of a metre,
   hard-capped well inside `|y| ≤ 3.5 m`); **no policy** drives it — it is a fixed scripted motion.
6. **Short low-speed scripted probe toward West** — the same bounded low-speed scripted nudge along
   the narrowed West corridor (respecting the ±0.78 m half-width); **no policy**.
7. **Contact/collision logging** — log every physics contact (body pair, position, impulse) across
   spawn + both probes; any contact with a wall/prop is a fail signal.
8. **Timeout guard** — each probe runs under a bounded wall-clock timeout; on timeout, halt safely and
   record the return code (no kill-by-name).
9. **Emergency stop / safe halt** — verify a safe-halt path (zero-velocity command + physics settle)
   works and that the `CL_BOUND_XY = 6.0` watchdog would trigger a halt if any pose approached the
   bound (the probes are designed to stay far inside it).
10. **No policy/model inference** — explicitly assert that no GNM/goal-conditioned model is loaded or
    queried during drive-validation; motion is scripted, the purpose is physical drivability only.

## 5. Allowed outputs

Only **validation artifacts** may be produced (no training data, no labelled episodes):

- a **drive-validation manifest** (scene, spawn pose, camera pose, probe definitions, bounds, config);
- a **contact/collision log** (per-contact records across spawn + probes);
- a **short probe summary** (per-probe: reached distance, min wall clearance, contacts, timeout/rc,
  final pose, in-bounds flag);
- a **pose trace** if needed (bounded, low-rate root-pose samples for the two short probes);
- **screenshots / contact sheets** if needed (spawn view + probe endpoints for human verification);
- a **drive-validation report** (pass/fail per criterion + claim boundary).

**No training data is labelled from this step.** These are physical-drivability checks, not episodes.

## 6. Pass / fail criteria

**Pass only if ALL hold:**

- **both N and W branches are reachable** (each short probe advances without being blocked);
- **no collision/contact** during spawn or the short validation probes;
- **no severe camera occlusion** (the decision frame and probe views remain non-black / unoccluded);
- **no wall/floor clipping** (no body–wall interpenetration; positive clearance in the narrowed West
  corridor);
- **robot remains within bounds** (all poses inside the safe envelope, `|x|,|y|` well under
  `CL_BOUND_XY = 6.0`);
- **stop/safety guard works** (safe-halt succeeds; watchdog would trigger if approached).

**Fail or defer if ANY occur:**

- a **collision** occurs (body contacts a wall/prop/floor collider);
- a **branch is blocked** (an invisible collider, prop, or liner wall obstructs N or W);
- the **camera is invalid** (black/occluded decision or probe view from the spawned body);
- **physics is unstable** (NaN/exploding state, drop-through-floor, joint blow-up);
- the **robot leaves the safe envelope** (any pose approaches/exceeds the bound);
- the **scene cannot support basic navigation** (e.g. corridor too narrow for the body to enter).

On fail/defer: **stop, do not force a claim**, and revise the scene geometry (e.g. widen the West
corridor, move a liner/prop, adjust spawn) or the spawn/camera config — then re-run render + drive
gates under review. A drive-validation failure is itself a legitimate diagnostic result.

## 7. Explicit exclusions

This step does **not** authorise and must **not** produce:

- **no recording for training** (no recorded-mode episodes);
- **no rollout metric claim**; **no TL / NE / SR / OSR / SPL / nDTW / CR** are computed or reported
  (there is no policy rollout here);
- **no action-probe** (goal-A-vs-goal-B action test is a later, separate gate);
- **no model training**;
- **no benchmark evidence**;
- **no real-scene evidence**;
- **no hospital evidence**;
- **no autonomy or deployment claim**.

## 8. Next gate after drive validation

**Only if drive-validation passes and is reviewed:**

1. plan **recorded-mode data collection** (gate 9) — decision-frame + branch-frame episodes in the
   hospital pipeline format (goal image, observation, action);
2. define the **train/val/test split family** — a leakage-safe split needs ≥ 6 **disjoint** junction
   instances (a single cross has only two goals; vary colour permutation, marker shapes, arm length,
   floor-cue, cross orientation);
3. **leakage audit** (gate 10) — disjoint frames/goal-images/coordinates/instance-ids across splits;
4. **action-probe readiness** (gate 11) — does conditioning on goal A (north) vs goal B (west) at the
   same decision frame change the predicted action (straight vs left)?
5. **review approval** before any training.

**Training remains blocked** until render reassessment (done) → drive validation → recorded-mode data
→ split/leakage audit → action-probe readiness → review approval **all** pass.

## 9. Claim boundary

- **`SYNTHETIC_DIAGNOSTIC_ONLY`** — authored idealised junction; a diagnostic of the model/objective.
- **Not hospital evidence.** **Not real-scene / real-world evidence.** **Not benchmark evidence.**
- **Not full goal-conditioned ImageNav evidence.** **No SOTA.**
- **No promotion** (`DIAGNOSTIC_ONLY_NOT_PROMOTED`; incumbent retained).
- **No autonomy claim.**
- `CL_BOUND_XY` unchanged (6.0 m watchdog untouched). This plan implements no code, runs no drive,
  records nothing, and trains nothing; every check above is deferred to a later, separately-approved,
  reviewed step.
