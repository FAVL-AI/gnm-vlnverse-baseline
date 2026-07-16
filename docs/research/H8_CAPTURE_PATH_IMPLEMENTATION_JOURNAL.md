# H8 Dataset Capture-Path — Implementation Journal

Chronological, append-only record for the dataset capture-path wiring gate (implementation commit
`bd6168a`). Only facts supported by Git, tests, shell output, and the retained gate report are recorded.
Exact wall-clock times for individual steps are **Not recoverable from retained evidence**; the Git
commit time is the one reliable timestamp. Session date: 2026-07-16.

Legend for unavailable detail: *Not recoverable from retained evidence.*

---

### Step 1 — Readiness analysis (prior gate, before this implementation)

- Time: *Not recoverable from retained evidence* (before `bd6168a`, 2026-07-16).
- Action: pure-function analysis + `inspect.getsource(run_capture)` against the dataset config.
- File/function: `run_capture`, `validate_pilot_config`, `pilot_capture_plan`, `build_dataset_plan`.
- Expected: determine whether the committed capture path can consume the dataset config.
- Actual: five deficiencies found — `H8-F-001…005` (pilot-only validator, pilot semantics, pilot planner
  can't build 8/22, no render-valid gate, no drive-valid gate).
- Interpretation: readiness = DEFER; capture path is pilot-only.
- Next action: implement fail-closed dataset capture wiring under review.

### Step 2 — Establish verified baseline

- Time: *Not recoverable from retained evidence*.
- Action: `git rev-parse HEAD`, `git status`, gate-history review.
- Expected: baseline at the dry-run evidence commit.
- Actual: HEAD `66fd81e` (`Add synthetic fork dataset dry-run evidence`); harness/test tree clean; 338
  unrelated pre-existing untracked/modified paths (prior work).
- Interpretation: safe baseline to implement on.
- Next action: read the current `run_capture` + `main` dispatch.

### Step 3 — Read current capture path and dispatch

- Action: read `run_capture` (pilot body) and `main`.
- Expected: confirm pilot-only structure + how `main` dispatches capture.
- Actual: `run_capture` hard-wired to pilot; `main` ran pilot pre-validation before the capture branch
  (would reject a dataset config before routing).
- Interpretation: need (a) verbatim pilot extraction, (b) explicit router, (c) move capture dispatch
  above pilot pre-validation in `main`.
- Next action: implement.

### Step 4 — Extract pilot body verbatim

- Action: rename `def run_capture(args)` → `def _run_pilot_capture(args)` (body unchanged, pragma kept).
- File/function: `_run_pilot_capture`.
- Expected: pilot behaviour unchanged.
- Actual: rename applied; body byte-identical.
- Interpretation: `H8-DCP-010` satisfied.
- Next action: add the dataset capture path + router.

### Step 5 — Add dataset capture path (validator, routing, planner, gate, DI seam)

- Action: insert `null_evidence_provider`, `_validity_record_status`, `dataset_instance_validity_gate`,
  `_plan_per_split`, `validate_dataset_capture_config`, `select_capture_mode`, `plan_dataset_capture`,
  `run_dataset_capture`, and the router `run_capture(args, evidence_provider, capture_backend)`.
- Expected: dataset mode routes to `build_dataset_plan`; unknown fails closed; production returns 3;
  per-instance render/drive-valid gate fails closed; validator reuses the 25 checks.
- Actual: implemented as designed (`H8-DCP-001…008`, `H8-DCP-011`).
- Interpretation: routing + gating + validation wired via a narrow DI seam.
- Next action: fix `main` dispatch order.

### Step 6 — Route capture in `main` before pilot pre-validation

- Action: move the `--mode capture` branch above the pilot-only pre-validation; remove the duplicate
  lower branch.
- Expected: a dataset config reaches the router instead of being rejected by `validate_pilot_config`.
- Actual: applied; 6 deletions overall (rename + moved/removed capture branch).
- Interpretation: dispatch order correct.
- Next action: add tests A–L.

### Step 7 — Add focused tests A–L + helpers

- Action: add `_SpyBackend`, `_good_evidence`, `_capture_args`, and `test_A_…test_L_` (+ existing
  routing/25-check tests).
- Expected: cover routing, exact scale, gating, defect classes, forbidden authorisations, unknown mode,
  pilot preservation, `CL_BOUND_XY`, no-artifact/no-Isaac.
- Actual: tests added.
- Next action: verify.

### Step 8 — First verification run (py_compile + narrow tests)

- Action: `python -m py_compile` both files; `pytest -k "test_A_ … test_L_ … 25 … select_capture_mode"`.
- Expected: compile clean; narrow tests pass.
- Actual: **py_compile OK**; **21 passed, 34 deselected**. **No failure.**
- Interpretation: routing/gating correct on first run; no corrective change needed.
- Next action: run full relevant suites.

### Step 9 — Full relevant-suite run

- Action: `pytest test_h8_synthetic_fork_recorded_mode.py + …_pilot_config.py + …_dataset_config.py`.
- Expected: all green, including the 25-check dry-run audit and pilot regression.
- Actual: **82 passed** (was 71 pre-gate; +11 new). **No failure.**
- Interpretation: pilot regression clean; dry-run audit intact.
- Next action: negative-artifact + attribution audits.

### Step 10 — Negative-artifact / integrity audit

- Action: check for dataset dir, forbidden extensions, dry-run evidence diff, Isaac imports in diff,
  `CL_BOUND_XY` value.
- Expected: nothing forbidden created; dry-run evidence unchanged; `CL_BOUND_XY == 6.0`.
- Actual: no `…_recorded_mode_dataset/` dir; no forbidden extensions; dry-run evidence unchanged; no
  Isaac/model imports added; `CL_BOUND_XY == 6.0` (`drive_validate.py:55`, `recorded_mode.py:59`).
- Interpretation: boundary preserved.
- Next action: lint.

### Step 11 — Lint

- Action: `python -m ruff --version`.
- Expected: run Ruff on changed files.
- Actual: **Ruff unavailable** in the environment. `py_compile` already passed.
- Interpretation: lint evidence incomplete → `H8-C-006` (open verification limitation). **No Ruff pass
  claimed.**
- Next action: commit implementation.

### Step 12 — Implementation commit

- Action: stage the two files; commit with Frank-only identity; no `--no-verify`.
- Expected: one local commit, no trailers, not pushed/tagged.
- Actual: `bd6168a` — `Wire fail-closed dataset capture planning`; author+committer Frank
  `<F.Van-Laarhoven2@newcastle.ac.uk>`; trailers `[]`; committed 2026-07-16T05:07:51+01:00; 2 files,
  402 insertions, 6 deletions. Not pushed, not tagged.
- Interpretation: technical implementation milestone recorded.
- Next action: (this gate) documentation-completeness audit + documentation-only commit.

### Step 13 — Documentation-completeness gate (this document's commit)

- Action: baseline re-confirm (`HEAD == bd6168a`, tree clean for harness/test); audit existing docs;
  create gate record, decision log, failure register, journal, traceability; append a manuscript entry;
  re-run the relevant suite for a fresh count; documentation consistency + attribution audits.
- Expected: no implementation/test change; documentation-only commit; counts consistent (8/22, 4/2/2,
  12/4/6); no AI attribution.
- Actual: fresh suite re-run **82 passed**; documentation files authored; see the final report for the
  documentation-only commit hash and audit results.
- Interpretation: documentation acceptance evidence completed as a separate commit; `bd6168a`
  unchanged.
