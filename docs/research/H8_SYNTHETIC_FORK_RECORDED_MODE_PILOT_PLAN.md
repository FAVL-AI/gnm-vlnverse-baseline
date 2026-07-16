# H8 Synthetic Fork — Tiny Real Recorded-Mode Pilot Plan (PLAN ONLY)

**Status: PLAN ONLY.** This document plans a *tiny* real recorded-mode pilot for the
`SYNTHETIC_DIAGNOSTIC_ONLY` fork. It authorises **nothing**: no recorded-mode capture, no Isaac
capture, no RGB image saving, no trajectory collection, no train/val/test dataset creation, no
action-probe, no training, no promotion, no push, no tag, no 20/5/10, no closed-loop policy testing.
`CL_BOUND_XY` is unchanged (6.0 m absolute watchdog, untouched). Running any pilot capture begins only
on explicit, separate review approval.

> **Boundary.** The dry-run proves the schema and leakage-audit logic. The tiny pilot should only prove
> that the capture harness can produce real files and metadata safely. It is not a dataset, not a
> benchmark, and not training authorization.

## 1. Purpose

The following gates are **already committed** on `h23-execfix`:

- **Render-valid reassessment** — `RENDER_VALID_JUNCTION` under the reviewed Outcome A + E rule.
- **Drive-validation PASS** — physical drivability certified (colliders established, floor support vs
  obstacle collision distinguished, exit code agrees with manifest verdict).
- **Recorded-mode plan** — the leakage-safe recorded-mode design.
- **Recorded-mode harness** — capture-capable, capture separately gated; fail-closed leakage audit.
- **CLI dry-run evidence** — the four dry-run artifacts reproducible from the committed CLI.

This document plans a **tiny real recorded-mode pilot** — a harness/schema validation capture of a very
small number of controlled examples — to confirm the capture path produces real files and metadata
safely. **It does not authorize capture or training.** Capture runs only under a separate approval, and
even a passing pilot is **not** a dataset, **not** a benchmark, and **not** training authorization.

## 2. Current evidence

- **Drive-validation PASS — commit `935ed85`** (pass=True, 61 colliders, obstacle contacts 0, support
  contacts 2, both N and W probes reached 0.6 m, all in bounds, exit code agrees with manifest).
- **Recorded-mode plan — commit `905ea50`** (`docs/research/H8_SYNTHETIC_FORK_RECORDED_MODE_PLAN.md`).
- **Recorded-mode harness — commit `6ad131e`** (`scripts/gnm/h8_synthetic_fork_recorded_mode.py` +
  tests; deferred Isaac imports; fail-closed leakage audit; forbidden-flag refusal).
- **Dry-run emitter — commit `6123ba6`** (harness emits the four named dry-run artifacts from the CLI).
- **CLI dry-run evidence — commit `03ed7f4`**
  (`assets/experiments/hospital_h8_track_b_synthetic_fork_recorded_mode_dryrun/`: manifest, schema,
  leakage-audit-dryrun with all six cases correct, report — DRY-RUN PASS).
- Claim boundary throughout: **`SYNTHETIC_DIAGNOSTIC_ONLY`**; `CL_BOUND_XY = 6.0` unchanged.

## 3. Pilot objective

The tiny pilot must verify — on a handful of real captured examples — that:

- the harness can **capture a small number of controlled examples** (decision frame + goal images)
  through the gated `capture` path;
- **image paths / indexing** are produced and resolve (a real `image_index` with populated paths);
- the **action-label table structure** is produced and populated with scripted, policy-free labels;
- **contact/collision status is logged** per captured frame (support vs obstacle classification);
- **metadata provenance** is captured (instance/decision-frame/goal IDs, coordinates, scene file, base
  commit, timestamp source, generator);
- the **leakage-audit machinery runs on real captured pilot records** (not just dummy cases) and reports
  its result and limitations;
- **no training** occurs — the pilot produces data + audit only.

## 4. Pilot scope

Minimal capture only — deliberately far below the full dataset target:

- a **small number of synthetic fork instances** (e.g. 1–2 disjoint instances/variants);
- a **small number of decision frames** (e.g. 1–2 per instance);
- **North-vs-West primary branch-choice examples** (STRAIGHT vs TURN_LEFT_90, ≈ 90° apart);
- **optional North-vs-East examples if supported** (STRAIGHT vs TURN_RIGHT_90), clearly secondary;
- **no full train/val/test dataset yet** (the pilot is intentionally below the 12/4/6 target);
- **no benchmark claim.**

The pilot's purpose is harness/schema validation on real files, not dataset construction.

## 5. Safety and capture protocol

All steps are **capture design only** here; when later approved, capture is bounded, scripted, and
policy-free, with a per-episode timeout wrapper + return-code capture (no process-pattern kills):

- **scene load** — load the labelled base USDA (and any variant), fail-closed on scene-identity
  mismatch;
- **validate colliders** — apply/count colliders across the authored `UsdGeom.Gprim` types; fail if the
  collider count is zero (reusing the drive-validation collider logic);
- **support-vs-obstacle contact classifier** — reuse the committed `is_support_contact` /
  `classify_contacts` (floor/ground → support/allowed; walls/panels/props/markers → obstacle/failure;
  robot self excluded);
- **camera validation** — robot-eye camera at z ≈ 0.47 m; each captured frame must render non-empty
  (non-black, unoccluded);
- **scripted capture poses only** — decision-frame and goal-image poses from known geometry; **no
  policy** places or drives the robot;
- **safe halt** — zero-velocity safe-halt on normal completion and on exception;
- **timeout guard** — each capture step under a bounded wall-clock timeout with rc capture;
- **fail-closed on collision/contact ambiguity** — an obstacle contact, an empty/invalid frame, or an
  unclassifiable contact aborts that frame (it is not recorded as a clean example);
- **no policy/model inference** — no GNM/goal-conditioned model is loaded or queried at any step.

## 6. Pilot artifacts allowed

When the pilot is later approved and run, it may produce **only**:

- a **pilot manifest**,
- a **pilot image index** (decision-frame + goal image IDs, paths, hashes),
- a **pilot action-label table** (per example: branch + scripted action class + route family),
- a **pilot contact log** (per-frame support/obstacle classification),
- a **pilot provenance table** (instance/frame/goal IDs, coordinates, scene file, base commit,
  timestamp source, generator),
- a **pilot leakage-audit report** (the audit run on the real pilot records, with limitations noted),
- a **pilot recording report** (per-criterion pass/fail + claim boundary).

It must **not** produce:

- **checkpoints**,
- **weights**,
- **wandb**,
- **rollout metrics** (no TL / NE / SR / OSR / SPL / nDTW / CR),
- **benchmark tables**,
- **model outputs**,
- **action-probe outputs**.

## 7. Pilot pass / fail criteria

**Pass only if ALL hold:**

- all expected pilot files are produced;
- captured **images are non-empty** (non-black, unoccluded);
- **labels are populated** (branch + scripted action class present for every example);
- **contact logs are present** for every captured frame;
- **no obstacle contacts** (support contacts allowed; obstacle contacts fail the frame);
- **metadata IDs are unique** (instance / decision-frame / goal-image IDs);
- the **leakage audit runs and reports any limitations** (a tiny pilot is expected to report
  below-target scale — that is a reported limitation, not a hidden failure);
- **no policy/model inference** occurred;
- **no training fields** appear in any artifact.

**Fail or defer if ANY occur:**

- **capture fails** (scene load / spawn / camera / collider failure);
- an **image is empty/invalid** (black/occluded);
- **collision/contact ambiguity** (an obstacle or unclassifiable contact);
- **missing metadata**;
- **duplicate IDs**;
- the **leakage audit fails** (contamination beyond the expected below-scale limitation);
- **any policy/model path is touched.**

On fail/defer: **stop, do not force a claim**, diagnose (harness, scene, or config), fix under review,
and re-run the pilot — a pilot failure is a legitimate harness-diagnostic result.

## 8. Leakage boundary

**The tiny pilot is NOT expected to satisfy the full minimum dataset target.** It is only a **harness
and schema validation pilot** — a proof that real files + metadata can be captured safely, on a handful
of examples. Its leakage audit is expected to report `below_min_scale` (and possibly single-instance),
which is a **reported limitation, not a certification of a trainable dataset**.

The full recorded-mode dataset still requires (unchanged from the recorded-mode plan):

- **train ≥ 12** decision frames,
- **val ≥ 4** decision frames,
- **test ≥ 6** decision frames,
- **ideally ≥ 6 disjoint junction instances**,
- **no reused decision frame across splits**,
- **no reused goal image across splits**,
- **no coordinate reuse across splits.**

None of these are satisfied by the pilot, and the pilot does not attempt to.

## 9. Claim boundary

- **`SYNTHETIC_DIAGNOSTIC_ONLY`** — authored idealised junction; a diagnostic of the model/objective.
- **Not hospital evidence.**
- **Not real-scene / real-world evidence.**
- **Not benchmark evidence.**
- **Not full goal-conditioned ImageNav evidence.**
- **No SOTA.**
- **No promotion** (`DIAGNOSTIC_ONLY_NOT_PROMOTED`; incumbent retained).
- **No autonomy claim.**
- **Not training authorization** — a passing pilot validates the capture harness only; it is not a
  dataset and does not license training.
- `CL_BOUND_XY` unchanged (6.0 m watchdog untouched). This plan implements no code, captures nothing,
  creates no dataset, and trains nothing.

## 10. Next gate after pilot plan

**Only after this plan is reviewed and approved:**

1. **implement or configure the tiny pilot capture** if needed (validation/capture-only; reusing the
   committed collider + support/obstacle classifier + safe-halt/timeout; refuses train/rollout/
   action-probe flags) — as a reviewed change, not run;
2. **run the tiny pilot capture under explicit approval** (bounded, scripted, policy-free);
3. **commit pilot evidence** (the allowed pilot artifacts only);
4. **then plan the full recorded-mode dataset or leakage audit** (the 12/4/6 disjoint-instance family);
5. **action-probe readiness only after the leakage audit** — a later, separate gate.

**Training remains blocked** until: tiny pilot capture → full recorded-mode dataset → split/leakage
audit → action-probe readiness → review approval **all** pass.

---

```text
The dry-run proves the schema and leakage-audit logic. The tiny pilot should only prove that the
capture harness can produce real files and metadata safely. It is not a dataset, not a benchmark, and
not training authorization.
```
