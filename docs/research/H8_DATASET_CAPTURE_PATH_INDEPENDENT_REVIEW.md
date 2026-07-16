# H8 Dataset Capture-Path — Independent Review (Levels 1 & 2)

**Review type:** independent, falsification-first, review-only. No implementation, tests, configs, or
evidence were modified. Reviewer reconstructed verdicts from Git, the committed configuration,
implementation, tests, committed evidence, and reproducible local commands rather than trusting the
existing gate conclusions.

**Date:** 2026-07-16 · **Repository:** `gnm-vlnverse-baseline` (local; remote `origin` exists, **not
pushed/tagged**) · **Branch:** `h23-execfix` · **Reviewed HEAD:** `bb94c5a`.

## Scope & commits reviewed (full hashes, Git-resolved)

| Role | Full hash |
| --- | --- |
| Dataset capture config | `7a73c9fc012b97ee1bf94fe829a3c59eb915ff9f` |
| Dry-run emitter (implementation) | `ecae4cdd5de4082184fc65881cc836c612231bf8` |
| Dry-run evidence (Level 1) | `66fd81e62bc0d6c100e7b562b22fc8cc8a0d061e` |
| Capture-path implementation (Level 2) | `bd6168ab5ead2aa5724a6d9df1b7e52222fbf0b7` |
| Documentation completion | `db70ce39c0d99300ec4f4d2c0010f6cbe036cade` |
| Provenance reconciliation | `bb94c5aabe6d96bbe8e4be4ce6f3d7a0a37af4ce` |

**Ancestry (verified `git merge-base --is-ancestor`, all true):**
`7a73c9f → ecae4cd → 66fd81e → bd6168a → db70ce3 → bb94c5a` (linear).

**Commit roles verified by `git show --name-status`:** `7a73c9f` = config + config-test (A);
`ecae4cd` = harness + test (M, emitter); `66fd81e` = the five evidence files (A); `bd6168a` = harness +
test (M, capture-path); `db70ce3` = 6 docs; `bb94c5a` = 3 docs. All roles match the documentation.

## Level-1 review — plan validity

### Evidence files inspected (all first added in `66fd81e`, never modified)

`dataset_dryrun_manifest.json`, `dataset_plan_schema.json`, `dataset_split_validation_dryrun.json`,
`dataset_leakage_audit_dryrun.json`, `dataset_dryrun_report.md`. `dataset_split_validation_dryrun.json`
carries the per-instance list (generated evidence); the report `.md` is generated narrative derived from
the same run.

### Independent recomputation (from instance-level data, not summary fields)

- Instances listed: **8**, ids unique.
- Instances/split recomputed from the per-instance list: **train 4 / val 2 / test 2**.
- Frames/instance recomputed via `ceil(min_scale_target / n_instances_in_split)` from
  `minimum_scale_targets` (12/4/6): **train 3 / val 2 / test 3**.
- Records/split = instances × frames: **train 12 / val 4 / test 6**, **total 22**.
- All recomputed values equal the committed summary fields (`planned_instance_count`,
  `planned_split_instance_counts`, `planned_per_split_frame_counts`, `valid_plan_audit.per_split_counts`).
- Internal consistency: `audit_pass == (leakage_safe AND meets_min_scale)` holds; all four injected
  leakage cases report `failed_closed=True`.

### Source falsification (emitter/audit)

- **No hard-coded `"25/25"`** in the harness — `checks_passed` is the computed f-string
  `f"{res['n_pass']}/{res['n_total']}"`; `n_pass = sum(c["pass"])`, `all_pass = n_pass == n_total`.
- **No unconditional** `audit_pass=True` / `leakage_safe=True` — `audit_pass = bool(leakage_safe and
  meets_min_scale)` (derived). Config `.get(...)` defaults resolve to `False`/reject, i.e. fail-closed.
- A check that raises propagates → the CLI `dataset-dry-run` branch returns 2 (fail-closed), never a
  silent pass.
- The only `except: pass` on the emit path (relative-path display) cannot mask validation, which is
  computed beforehand. Output is written only under the caller-supplied `out_dir`.

### Reproduction (§5.4)

Command (fresh scratch dir, committed evidence untouched):
`python scripts/gnm/h8_synthetic_fork_recorded_mode.py --mode dataset-dry-run --config
configs/gnm/h8_synthetic_fork_recorded_mode_dataset.yaml --out-dir <scratch>` → exit 0,
`all_checks_pass=true`, 5 files. **All five files reproduce byte-for-byte (SHA-256 match)** against the
committed `66fd81e` evidence. Committed evidence confirmed byte-unchanged (`git diff --quiet`).

### Falsification (§5.5)

12 config mutations + 4 record-level injected leakage cases, all **rejected / failed closed**:
changed `CL_BOUND_XY`, forbidden capture auth, forbidden training auth, policy-inference auth,
action-probe auth, missing render-valid req, missing drive-valid req, duplicate coordinate across
splits, split collapse, malformed (no `instance_plan`), missing `minimum_scale`; and dup decision-frame,
dup goal-image, dup coordinate, single-instance collapse. No dataset artefacts were produced.

## Level-2 review — capture-path validity

### Implementation symbols reviewed (`bd6168a`)

`validate_dataset_capture_config`, `select_capture_mode`, `plan_dataset_capture`, `run_dataset_capture`,
`run_capture` (router), `dataset_instance_validity_gate`, `_validity_record_status`,
`null_evidence_provider`, `_run_pilot_capture` (renamed pilot body).

### Routing (§6.2, review-time spies)

Dataset config: `rc=0`, **dataset planner invoked, pilot planner invoked 0 times**, injected backend
called once. `select_capture_mode` returns `dataset`/`pilot`/`unknown` correctly. *Observation
(benign):* the dataset planner is built twice per run (once inside validation's 25-check recompute, once
inside planning) — deterministic, same result; the SELECTED planner is used and the PROHIBITED planner
is never used.

### Plan integrity through the routed path (§6.3)

The injected backend received a plan of **8 instances**, split **4/2/2**, **22 records**, per-split
**12/4/6**, carrying `scene_base = assets/scenes/synthetic_diagnostic_fork/synthetic_diagnostic_fork.usda`,
`CL_BOUND_XY = 6.0` — produced through the real routed code path (not a fixture bypass).

### Evidence gates (§6.4, 13 cases)

`valid` → `rc=0`, backend called, ready. Twelve defect cases (render & drive × {missing, false,
malformed, stale, instance-mismatch, scene-mismatch}) → **`rc=2`, backend 0 calls, ready=False,
structured reason naming instance `sfork_00` + prerequisite**, and **no dataset directory created**.

> **Limitation (recorded):** "stale" is a boolean flag in a **test-schema convention**, not a real
> freshness/expiry policy bound to timestamps or config hashes. Stale-rejection is verified at the
> convention level only.

### Production blocking (§6.5)

`run_capture` with no injected backend → **`rc=3`**, `isaacsim`/`omni` **not imported**, **no dataset
directory**. Real capture is inert.

### Pilot preservation (§6.6)

`_run_pilot_capture` body at `bd6168a` is **byte-identical** to the pre-`bd6168a` `run_capture` body
(only the `def` line renamed). `validate_pilot_config`, `pilot_capture_plan`, `pilot_verdict`,
`finalize_pilot`, `allowed_pilot_artifacts` are **unchanged** across `66fd81e → bd6168a`. Pilot suite
green.

## Validation parity (§7)

Every condition in the mandated parity table is **REJECT / REJECT** (Pass) across both the dry-run
checks and the capture validator: duplicate decision frame, duplicate goal image, duplicate coordinate,
split collapse, missing render-valid req, missing drive-valid req, changed `CL_BOUND_XY`, forbidden
authorisation. In **no case is the capture validator more permissive than the dry-run** (the safe
direction). One extra tested condition diverges — see `H8-REV-F-001`.

## Static / quality checks (§9)

`py_compile` **OK**; full relevant suite **82 passed** (recorded-mode + pilot-config + dataset-config,
incl. the 25-check audit and pilot regression); `git diff --check` clean; attribution clean; secrets
clean. **Ruff UNAVAILABLE** → `H8-C-006` remains open; **no lint-pass is claimed** (`py_compile` is not
a lint substitute).

## Negative-artifact audit (§8)

Working tree unchanged at 338 pre-existing unrelated paths (untouched); no
`hospital_h8_track_b_synthetic_fork_recorded_mode_dataset/` directory; committed dry-run evidence
byte-unchanged; no new `.png/.jpg/.jpeg/.npy/.bag/.db3/.mcap/.pt/.pth/.ckpt/.pkl/.bin`; review scratch
kept outside the repository. Zero boundary violations.

## Review findings

### H8-REV-F-001 — Dry-run 25 checks lack the stray-rollout-metric-key scan (parity asymmetry)

- **Requirement:** dry-run and capture validation agree on invalid conditions (§7).
- **Expected:** a config carrying a stray rollout-metric key (e.g. top-level `SR: 0.9`) rejected by both.
- **Observed:** `validate_dataset_capture_config` **rejects** it (its `_all_config_keys` scan flags
  `FORBIDDEN_METRIC_KEYS`); `dataset_dry_run_checks` **accepts** it (none of the 25 checks scan for stray
  rollout-metric keys). The capture validator is a **strict superset** of the 25 checks.
- **Evidence:** review parity harness (§7); `dataset_dry_run_checks` has no rollout-key check;
  `validate_dataset_capture_config` does.
- **Severity:** **Low.** Direction is fail-safe (capture stricter, never weaker); the committed config
  has no stray keys, so **the committed 25/25 evidence and Level-1 claim are unaffected**.
- **Impact:** the dry-run "25/25" alone does not guarantee absence of a stray rollout-metric key; a
  reader must not treat 25/25 as equivalent to capture-acceptance.
- **Containment:** real capture and independent review remain blocked; the capture gate already rejects
  the case.
- **Recommended mitigation (future remediation gate, not now):** add a stray-rollout-metric-key check to
  the 25 dry-run checks, **or** document that the capture validator is a strict superset of the dry-run.
- **Can the gate pass?** Yes — as PASS-WITH-LIMITATIONS; no implementation change is required for the
  committed claims to hold.

### H8-REV-F-002 — "Single source of plan validity" wording under-specifies the superset relationship

- **Requirement:** documentation matches implementation (§10).
- **Observed:** `H8-DCP-002` is titled "single source of plan validity." The capture validator reuses the
  25 checks **and adds** further guards (mode, `scene_base`, output-collision, per-control detail,
  forbidden-output list, per-instance render/drive-required, stray-rollout-key). The gate record already
  says it "adds capture-gate safety declarations," so this is a **precision** nuance, not a
  contradiction.
- **Severity:** **Low / informational.**
- **Recommended mitigation:** state explicitly that the capture validator is a strict **superset** of
  the 25 dry-run checks.
- **Can the gate pass?** Yes — minor documentation finding.

*(No finding required an implementation change to make a committed claim true; per the review rules,
implementation was not modified.)*

### Remediation dispositions (appended 2026-07-16 — original findings above preserved)

Remediation gate report: [`H8_DATASET_CAPTURE_PATH_REMEDIATION.md`](H8_DATASET_CAPTURE_PATH_REMEDIATION.md).

- **H8-REV-F-001 → `MITIGATED WITH DOCUMENTED LIMITATION`.** The strict-superset asymmetry is now
  declared **intentional** (`H8-DCP-014`) and locked by `test_capture_validator_never_weaker_than_dry_run`
  and `test_stray_rollout_key_is_capture_specific_H8_REV_F_001`. No 26th dry-run check was added (it
  would break the byte-identical `25/25` evidence). Residual limitation: the dry-run diagnostic alone
  still does not flag a stray rollout key — the enforcing capture gate does.
- **H8-REV-F-002 → `CLOSED`.** `H8-DCP-002` now states explicitly that the capture validator is a strict
  **superset** of the 25 dry-run checks; the gate record's implementation summary carries the same
  clarification.
- **H8-REV-F-003 (NEW, discovered during remediation) → `OPEN — DEFERRED`.** `dataset_dry_run_checks`
  raises `IndexError` when called **directly** on a malformed config with **no instances** (empty plan →
  `dataset_injected_leakage_cases([])` → `_cross_split_pair([])`). **Not a safety hole:** at both real
  boundaries it fails **closed** — the CLI `dataset-dry-run` branch returns `2` (verified:
  `{"dataset_dry_run": false, "error": "list index out of range"}`, no files written) and
  `validate_dataset_capture_config` catches it → `ok=False`. Severity Low. Recommended future mitigation:
  a graceful empty-plan guard so the direct call returns `all_pass=False` instead of raising. Deferred to
  a future hardening gate to keep this gate narrow; owner = evidence-schema/hardening gate.

## KPI results

| KPI | Target | Result |
| --- | --- | --- |
| Level-1 requirement coverage | 100% | 100% |
| Level-2 requirement coverage | 100% | 100% |
| Negative-case rejection rate | 100% | 100% (12 config + 4 injected + 12 evidence-gate) |
| Invalid-case zero-artefact rate | 100% | 100% |
| Planner-routing accuracy | 100% | 100% (selected planner used; prohibited planner 0 calls) |
| Evidence reproduction agreement | all agree | 100% (5/5 SHA-256; all counts & booleans) |
| Pilot regression pass rate | 100% | 100% (byte-identical body; suite green) |
| Documentation-to-implementation consistency | 100% | Material claims supported; 2 low-severity findings |
| Boundary violations | 0 | 0 |

Deferred and **not** counted as passing by omission: real evidence provider, real dataset backend,
runtime validity, Ruff.

## SWOT

**Strengths:** deterministic, byte-reproducible static validation; explicit fail-closed routing; strict
per-instance dual-evidence gate with structured reasons; verified provenance trail; clean separation of
evidence levels; byte-identical pilot preservation.

**Weaknesses:** no real evidence provider or backend; no runtime evidence; no captured dataset;
stale/expiry semantics are a test-schema convention only; parity asymmetry `H8-REV-F-001`; Ruff not run.

**Opportunities:** a formal, versioned render/drive-valid evidence schema; signed/hashed evidence
records bound to instance+scene+config+timestamp; a separately reviewed controlled Isaac backend gate
with runtime observability; reproducible capture manifests; an eventual dataset-quality audit.

**Threats:** synthetic evidence mistaken for runtime evidence; schema drift; silent identity mismatch;
partial-artefact creation in future backend code; pilot/dataset semantic convergence over time; premature
training or publication claims.

## Verdicts

- **Level-1 verdict: `PASS`.** Committed evidence exists and reproduces byte-for-byte; counts recompute
  independently; all 25 checks derive from real validation; every defined negative case fails closed; no
  runtime or dataset artefacts are produced.
- **Level-2 verdict: `PASS WITH DOCUMENTED LIMITATIONS`.** Explicit routing, dataset-planner use, pilot
  preservation, 13-case fail-closed evidence gating, pre-output blocking, and production inertness are
  all verified. Limitations: stale-semantics are a convention only; real evidence provider and backend
  are absent; parity asymmetry `H8-REV-F-001` (safe direction).
- **Documentation verdict: `PASS WITH MINOR DOCUMENTATION FINDINGS`.** Provenance, counts, level
  attributions, limitations, and blockers are accurate with no AI attribution; `H8-REV-F-002` is a
  low-severity precision nuance.

## Remaining blockers (before real dataset capture)

1. Reviewed, versioned render/drive-valid **evidence schema** (with real freshness/expiry semantics).
2. A **real evidence provider** binding evidence to instance + scene + config + freshness.
3. A separately reviewed **real dataset capture backend** and a live **Isaac/ROS 2 runtime-validity
   gate**.
4. Address `H8-REV-F-001` (parity) and `H8-REV-F-002` (wording) in a remediation gate, or accept them
   with explicit documentation.
5. Canonical **Ruff** run (`H8-C-006`).
6. Explicit capture authorisation.

## Next-gate recommendation

Proceed to a **remediation/hardening gate** (optional, for `H8-REV-F-001`/`-F-002` and Ruff), then an
**evidence-schema + evidence-provider gate**, then a separately reviewed **backend/runtime-validity
gate**. Do **not** proceed to real dataset capture.

## Boundary statement

Levels 1 (plan validity) and 2 (capture-path validity) are **independently confirmed**. **Runtime
(Level 3), dataset (Level 4), and model (Level 5) validity remain unproven.** **Real dataset capture
remains blocked.** During this review no Isaac launch, real capture, rendering, robot driving,
policy/model inference, action probe, training, checkpoint creation, 20/5/10, closed-loop evaluation,
push, tag, promotion, or publication occurred.
