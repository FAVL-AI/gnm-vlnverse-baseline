# H8 Synthetic Fork — Full Recorded-Mode Dataset Plan (PLAN ONLY)

**Status: PLAN ONLY.** This document plans how to scale from the committed one-instance pilot into a
leakage-safe `SYNTHETIC_DIAGNOSTIC_ONLY` diagnostic dataset. It authorises **nothing**: no
recorded-mode capture, no Isaac capture, no RGB image saving, no trajectory collection, no
train/val/test dataset creation, no action-probe, no training, no promotion, no push, no tag, no
20/5/10, no closed-loop policy testing. `CL_BOUND_XY` is unchanged (6.0 m absolute watchdog,
untouched). Building or running any capture begins only on explicit, separate review approval.

> **Boundary.** The pilot proves the capture path works. It does not prove dataset readiness. This
> document must plan scale, disjointness, splits, and leakage controls before any full capture or
> training.

## 1. Purpose

The **pilot capture evidence is committed at `2659168`** (`Add synthetic fork pilot capture evidence`):
a real tiny pilot capture produced non-empty RGB images, unique IDs, scripted labels, provenance, a
contact log (obstacle 0 / ambiguous 0), and an honest leakage audit. **That pilot is not a dataset and
not training authorization** — it is a single-instance, below-scale harness/schema validation. This
document defines what must be captured later to turn the working capture path into a
**leakage-auditable synthetic diagnostic dataset**. It implements no code, captures nothing, creates no
dataset, and trains nothing.

## 2. Current evidence ladder

All committed on `h23-execfix`:

- **Render-valid reassessment** — `RENDER_VALID_JUNCTION` under the reviewed Outcome A + E rule.
- **Drive-validation PASS — `935ed85`** (colliders established, floor support vs obstacle distinguished,
  exit code agrees with manifest verdict).
- **Recorded-mode plan — `905ea50`**.
- **Recorded-mode harness — `6ad131e`**.
- **Dry-run emitter — `6123ba6`**.
- **CLI dry-run evidence — `03ed7f4`**.
- **Tiny pilot plan — `aa7de13`**.
- **Pilot capture config — `c646225`**.
- **Executable pilot capture path — `82f60f9`**.
- **Pilot capture evidence — `2659168`**.

Claim boundary throughout: **`SYNTHETIC_DIAGNOSTIC_ONLY`**; `CL_BOUND_XY = 6.0` unchanged.

## 3. Pilot limitation

The committed pilot (`2659168`) is explicitly **not a dataset**:

- pilot captured **8 records/images** (example records),
- **10 RGB PNGs total** (2 decision-frame views + 8 branch-goal views),
- **1 synthetic fork instance**,
- **`leakage_safe = False`**,
- **`meets_min_scale = False`**,
- reasons: **`below_min_scale`**, **`single_instance_not_leakage_safe`**,
- therefore the pilot is **not trainable and not a benchmark** — it proves only that the capture path
  produces real files and honest metadata.

## 4. Full dataset objective

The full recorded-mode dataset must:

- create **controlled observation / goal / action examples** (decision-frame image o_d, goal image,
  scripted local action label) across a family of disjoint instances;
- support **same-start different-goal branch-choice testing** — the same decision frame paired with
  different goal images must carry different scripted actions;
- support **route-family labels** (primary angular branch choices + clearly-marked secondary controls);
- support the **leakage audit** (disjoint instance/frame/goal IDs and coordinates across splits);
- support a later **action-probe readiness review** (does conditioning on goal A vs goal B change the
  predicted action?) — a separate, later gate;
- remain **`SYNTHETIC_DIAGNOSTIC_ONLY`** — a diagnostic of the model/objective, never hospital,
  real-scene, or benchmark evidence.

## 5. Minimum dataset target

Use the committed target (unchanged from the recorded-mode plan):

- **train ≥ 12 decision frames**,
- **val ≥ 4 decision frames**,
- **test ≥ 6 decision frames**,
- **ideally ≥ 6 disjoint synthetic fork instances**,
- **no reused decision frame across splits**,
- **no reused goal image across splits**,
- **no coordinate reuse across splits**.

If genuine disjointness cannot reach these counts, the dataset is **not feasible at target scale** and
must be re-scoped or documented as under-powered — it must **not** be shipped as a leaky split.

## 6. Instance design

Plan to create/parameterize **disjoint** synthetic fork instances so that splits can be made across
instances with no shared frames/goals/coordinates:

- **instance IDs** — a stable unique ID per instance (e.g. `sfork_00`…`sfork_NN`);
- **branch layout variants** — vary the cross geometry within the render/drive-valid envelope (arm
  length/width, cross orientation, which arms are branches vs distractor) while keeping a genuine
  ≥ 30°/90° angular branch choice (never a collinear-180 pair as a primary);
- **floor-cue variants** — vary floor strips/markings per instance (still classified as **support**);
- **goal-marker variants** — vary the branch shape/colour/marker families so goal images are
  structurally distinct (per the distinctness lesson; DINO advisory on the symmetric cross);
- **camera/lighting variants** — only if **controlled and documented** (fixed robot-eye height ≈ 0.47 m,
  level horizon; lighting variation must not black out goal views);
- **coordinates separated enough to avoid reuse** — translate/rotate each instance so decision and goal
  coordinates do not collide across instances (the audit's coordinate-reuse check enforces this);
- **all navigable extent within `CL_BOUND_XY = 6.0`** (well inside; the watchdog is unchanged).

Every instance must **re-pass render-validity + drive-validity** before it may contribute frames.

## 7. Route families

Draw decision/goal pairs from (primary = angular branch choice, secondary = control only):

- **N-vs-W primary** — STRAIGHT vs TURN_LEFT_90 (≈ 90°, non-collinear);
- **N-vs-E secondary if supported** — STRAIGHT vs TURN_RIGHT_90 (≈ 90°);
- **same-start different-goal branch-choice pairs** — same o_d, different goal → action must change
  with the goal (the core goal-conditioning test);
- **hard-negative mismatched-goal examples** — a decision frame paired with a goal from a different
  instance / non-adjacent branch (tests goal sensitivity; a negative, not a positive target);
- **optional W-vs-E opposite-direction controls** — clearly marked **secondary** (collinear/opposite,
  not a fresh angular fork — the H8-S lesson);
- **near/far stop-distance examples** — **secondary only** (distance axis; not angular branch choice).

## 8. Capture protocol

Plan only (executed later, only if approved; each step bounded, scripted, policy-free, with a
per-episode timeout wrapper + return-code capture, no process-pattern kills):

- **config-driven capture** — instances/frames/route-families/poses come from the dataset capture
  config, not hard-coded;
- **scripted poses only** — no policy places or drives the robot;
- **camera validation** — robot-eye/front RGB camera set up and confirmed before saving;
- **non-empty image validation** — every decision and goal frame must render non-black/unoccluded
  before it is saved;
- **collider validation** — apply/count colliders across the authored Gprim types; require collider
  count > 0 (fail-closed if zero);
- **contact classification** — reuse the committed `is_support_contact` / `classify_contacts`;
- **support contacts separated from obstacle contacts** — floor/ground → support (allowed);
  walls/panels/props/markers → obstacle;
- **fail-closed on obstacle or ambiguous contact** — such a frame is aborted, not recorded as clean;
- **provenance written for every record** — instance/frame/goal IDs, coordinates, scene file, base
  commit, config, timestamp source, generator;
- **safe halt** — zero-velocity safe-halt on normal completion and on exception;
- **timeout guard** — each capture step under a bounded wall-clock timeout with rc capture.

No policy/model inference at any step.

## 9. Artifact set

Allowed future dataset artifacts:

- a **full recorded-mode manifest**,
- an **image index** (unique decision-frame + goal-image IDs, paths, hashes),
- an **action-label table** (scripted action classes + route-family labels),
- a **split manifest** (train/val/test membership by instance/frame/goal ID, fixed before training),
- a **contact log** (per-frame support/obstacle classification),
- a **provenance table**,
- a **leakage-audit report**,
- a **recording report** (per-criterion pass/fail + claim boundary).

Forbidden:

- **checkpoints**, **weights**, **wandb**, **rollout metrics** (no TL / NE / SR / OSR / SPL / nDTW /
  CR), **benchmark tables**, **model outputs**, **action-probe outputs**.

## 10. Leakage audit

Before any training, the audit must confirm:

- **split assignment before any training** (membership fixed; no post-hoc reassignment);
- **unique instance IDs**;
- **unique decision-frame IDs**;
- **unique goal-image IDs**;
- **coordinate reuse check** — no decision/goal coordinate shared across splits (within tolerance);
- **image hash check** — perceptual/byte hashes of goal images disjoint across splits;
- **near-duplicate visual check** — no visually near-identical instances straddling train and test;
- **route-family balance check** — splits are not degenerate on a single route family;
- **fail-closed if contamination is found** — training stays blocked until the audit passes and is
  reviewed.

## 11. Dataset pass / fail criteria

**Pass only if ALL hold:**

- **minimum scale is met** (train ≥ 12, val ≥ 4, test ≥ 6);
- **at least the planned disjoint instances exist** (ideally ≥ 6);
- **all images non-empty**;
- **all labels populated** (action class + route family);
- **all provenance present**;
- **obstacle contacts zero** (or an obstacle-touching frame is explicitly excluded, not silently kept);
- **ambiguous contacts zero**;
- **leakage audit passes** (§10);
- **no policy/model inference**;
- **no training fields**;
- **no rollout metrics**.

**Fail or defer if ANY occur:**

- **below minimum scale**;
- **single-instance only**;
- **duplicate IDs**;
- **reused coordinates across splits**;
- **invalid/empty images**;
- **missing labels**;
- **missing provenance**;
- **obstacle / ambiguous contacts**;
- **leakage audit fails**;
- **a policy/model path is touched**;
- **forbidden outputs produced**.

On fail/defer: **stop, do not force a claim**, diagnose (instances, geometry, config, or splits), fix
under review, and re-capture/re-audit. A dataset failure is a legitimate diagnostic result.

## 12. Claim boundary

- **`SYNTHETIC_DIAGNOSTIC_ONLY`** — authored idealised junction family; a diagnostic of the
  model/objective.
- **Not hospital evidence.**
- **Not real-scene / real-world evidence.**
- **Not benchmark evidence.**
- **Not full goal-conditioned ImageNav evidence.**
- **No SOTA.**
- **No promotion** (`DIAGNOSTIC_ONLY_NOT_PROMOTED`; incumbent retained).
- **No autonomy claim.**
- **Not training authorization** — a passing dataset + leakage audit is a prerequisite, not a licence
  to train.
- `CL_BOUND_XY` unchanged (6.0 m watchdog untouched). This plan implements no code, captures nothing,
  creates no dataset, and trains nothing.

## 13. Next gate after this plan

**Only after this plan is reviewed and approved:**

1. **update or create a full dataset capture config** (instances, route families, split assignment;
   `authorizes_capture: false` remains a static declaration — the run is authorized only by explicit
   external approval) — as a reviewed change;
2. **validate it in dry-run** (schema + leakage-audit logic on planned records, no Isaac);
3. **run full recorded-mode capture under explicit approval** (bounded, scripted, policy-free);
4. **commit full dataset capture evidence** (allowed artifacts only);
5. **run the split/leakage audit** (§10) on the real dataset;
6. **only then consider action-probe readiness** — a later, separate gate.

**Training remains blocked** until: full dataset capture → split/leakage audit → action-probe readiness
→ a separate review approval **all** pass.

---

```text
The pilot proves the capture path works. It does not prove dataset readiness. The next document must
plan scale, disjointness, splits, and leakage controls before any full capture or training.
```
