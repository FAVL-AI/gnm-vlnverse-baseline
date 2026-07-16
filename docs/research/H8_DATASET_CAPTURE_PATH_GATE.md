# H8 Synthetic-Fork Recorded-Mode Dataset Capture-Path Wiring Gate

**Gate record.** This is the permanent research/engineering record for the dataset capture-path wiring
gate. It is documentation-only evidence for the technical implementation commit `bd6168a`
(`Wire fail-closed dataset capture planning`). The implementation commit is preserved unchanged; this
record and its companion documents were added in a separate documentation-only commit.

Companion documents:
- Decision log — [`H8_DATASET_DECISION_LOG.md`](H8_DATASET_DECISION_LOG.md) (`H8-DCP-001…012`)
- Failure & mitigation register — [`H8_FAILURE_AND_MITIGATION_REGISTER.md`](H8_FAILURE_AND_MITIGATION_REGISTER.md) (`H8-F-*`, `H8-C-*`)
- Implementation journal — [`H8_CAPTURE_PATH_IMPLEMENTATION_JOURNAL.md`](H8_CAPTURE_PATH_IMPLEMENTATION_JOURNAL.md)
- Requirements traceability — [`H8_CAPTURE_PATH_TRACEABILITY.md`](H8_CAPTURE_PATH_TRACEABILITY.md) (`H8-R-001…021`)

---

## A. Gate identity

| Field | Value |
| --- | --- |
| Gate name | **H8 Synthetic-Fork Recorded-Mode Dataset Capture-Path Wiring Gate** |
| Date | 2026-07-16 |
| Repository | `gnm-vlnverse-baseline` (local; not pushed) |
| Baseline branch | `h23-execfix` |
| Baseline HEAD (before implementation) | `66fd81e` — `Add synthetic fork dataset dry-run evidence` |
| Implementation commit | `bd6168a` — `Wire fail-closed dataset capture planning` |
| Implementation commit time (from Git) | 2026-07-16T05:07:51+01:00 |
| Documentation commit | this document's commit (documentation-only follow-up; see the final report) |
| Operator identity (from Git) | Frank Asante Van Laarhoven `<F.Van-Laarhoven2@newcastle.ac.uk>` (author and committer) |
| Working-tree status before implementation | clean for the harness/test files; 338 unrelated pre-existing untracked/modified paths from prior work (not part of this gate) |
| Working-tree status after implementation | harness/test files committed and clean |
| Configuration file used | `configs/gnm/h8_synthetic_fork_recorded_mode_dataset.yaml` (committed at `7a73c9f`) |
| Relevant evidence directories | `assets/experiments/hospital_h8_track_b_synthetic_fork_recorded_mode_dataset_dryrun/` (dry-run evidence, `66fd81e`) |
| Relationship to earlier gate | Directly follows the dataset dry-run gate. The 25/25 dry-run (`66fd81e`) established **plan validity**; this gate establishes **capture-path validity** under an injected no-Isaac backend. |

Files changed in `bd6168a` (both non-documentation):
- `scripts/gnm/h8_synthetic_fork_recorded_mode.py` (+219 / −6 region)
- `tests/gnm/test_h8_synthetic_fork_recorded_mode.py` (+189)
- Total: 402 insertions, 6 deletions. No documentation file was included — which is why this documentation-only follow-up exists.

Gate history leading here (all local, branch `h23-execfix`):
`82f60f9` pilot capture path → `2659168` pilot capture evidence → `ba2bd58` dataset plan →
`7a73c9f` dataset capture config → `ecae4cd` dataset dry-run emitter → `66fd81e` dataset dry-run
evidence (25/25) → **`bd6168a` capture-path wiring** → *(this documentation commit)*.

## B. Purpose

This gate exists to determine whether the committed capture harness can **safely consume the validated
H8 dataset plan** — before any real dataset capture is approved.

Explicitly:
- the earlier dry-run established **plan validity** (the plan and its invariants);
- it did **not** establish capture-path executability;
- it did **not** authorise Isaac execution;
- it did **not** authorise data capture;
- it did **not** establish dataset quality;
- it did **not** authorise model inference or training.

This gate validates **software routing, configuration enforcement, and prerequisite gating only**.

## C. Research question

> Can the committed capture harness route an H8 dataset configuration to the dataset planner, preserve
> the existing pilot path, and fail closed before any output when render-valid or drive-valid evidence
> is missing or invalid?

## D. Hypothesis

> When the canonical H8 dataset configuration is supplied through an injected no-Isaac execution
> adapter, the harness will select the dataset planner, produce the validated eight-instance and
> twenty-two-record plan, preserve pilot semantics, and reject every instance lacking valid render-valid
> and drive-valid evidence before creating capture artefacts.

## E. Acceptance criteria

| # | Criterion | Result |
| --- | --- | --- |
| 1 | Dataset config accepted only when all required safety invariants pass | PASS (`test_A`, `test_G`, `test_J`) |
| 2 | Dataset mode routes only to `build_dataset_plan` | PASS (`test_B`) |
| 3 | Pilot mode continues to route only to the pilot planner | PASS (`test_I`) |
| 4 | Unknown modes fail closed | PASS (`test_H`) |
| 5 | Plan contains exactly 8 instances | PASS (`test_C`) |
| 6 | Split is exactly 4 train / 2 val / 2 test instances | PASS (`test_C`) |
| 7 | Plan contains exactly 22 planned frame records | PASS (`test_C`) |
| 8 | Frame split is exactly 12 train / 4 val / 6 test records | PASS (`test_C`) |
| 9 | Missing/invalid render-valid evidence blocks progression | PASS (`test_D`, `test_F`) |
| 10 | Missing/invalid drive-valid evidence blocks progression | PASS (`test_E`) |
| 11 | No partial output before prerequisite approval | PASS (`test_D`, `test_E`, `test_L`) |
| 12 | All 25 dataset dry-run checks remain green | PASS (`test_dataset_dry_run_all_25_checks_pass`) |
| 13 | `CL_BOUND_XY` remains exactly 6.0 | PASS (`test_J`; `drive_validate.py:55`, `recorded_mode.py:59`) |
| 14 | No Isaac/capture/inference/action-probe/training/checkpoint/push/tag/promotion | PASS (`test_L`; negative-artifact audit) |

## F. Scope boundary

**In scope:** configuration validation; dataset-plan validation; explicit mode routing; a no-Isaac
adapter / test seam; render-valid gating; drive-valid gating; structured fail-closed responses; unit
and regression tests; documentation; one local commit (implementation) + one local commit
(documentation).

**Out of scope:** Isaac Sim startup; ROS 2 runtime execution; camera capture; trajectory capture;
rosbag creation; RGB dataset generation; policy or GNM inference; action-probe execution; training or
fine-tuning; checkpoint generation; live closed-loop navigation; performance claims; dataset-quality
claims; benchmark claims; push, tag, release, or promotion.

## Implementation summary

- The existing pilot capture body was **extracted verbatim** into `_run_pilot_capture` (behaviour
  unchanged; still `# pragma: no cover`, still Isaac-gated). Harness symbol `_run_pilot_capture`.
- A new **explicit router** `run_capture(args, evidence_provider=None, capture_backend=None)` dispatches
  by `select_capture_mode(cfg)` → `pilot` / `dataset` / `unknown`. No implicit default; unknown/absent
  mode returns 2.
- `validate_dataset_capture_config(cfg)` — fail-closed dataset validator that reuses the canonical
  25-check `dataset_dry_run_checks` as the **single source of plan validity** and adds capture-gate
  safety declarations (mode, `authorizes_capture`/`authorizes_training` false, `scene_base`,
  dataset-only output dir, `cl_bound_xy == 6.0`, capture-control falses, forbidden outputs, per-instance
  render/drive-valid required, no rollout-metric key).
- `plan_dataset_capture(cfg, evidence_provider)` — pure, no-Isaac planning + gating: validate → build
  plan via `build_dataset_plan(cfg)` + `cfg["scene_base"]` → per-instance validity gate. Returns a
  structured readiness dict; creates nothing.
- `dataset_instance_validity_gate` + `_validity_record_status` — per-instance render-valid AND
  drive-valid evidence gate; `ok` only if present, well-formed, `passed is True`, instance-matched,
  scene-matched, not stale; else a structured reason (`absent`/`malformed`/`false`/`instance_mismatch`/
  `scene_mismatch`/`stale`) naming the instance and prerequisite. Default `null_evidence_provider`
  returns nothing → fails closed.
- `run_dataset_capture` return codes: **2** = not ready (config invalid or gate blocked, nothing
  created); **3** = ready but real capture not authorised at this gate (no backend injected, nothing
  captured); otherwise the injected no-Isaac backend's code. Real dataset capture is **not** implemented
  here.

## Verification results (exact, from the retained command output)

- `python -m py_compile` on both changed files → **OK**.
- Narrow new tests (`test_A_`…`test_L_` + routing/25-check) → **21 passed, 34 deselected**.
- Full relevant suites (`test_h8_synthetic_fork_recorded_mode.py` + `…_pilot_config.py` +
  `…_dataset_config.py`) → **82 passed** (was 71 before this gate; +11 new tests).
- **No test failed during this implementation; no corrective code change was required** (initial narrow
  run 21/21, initial full run 82/82). Session-step timestamps beyond the Git commit time are *not
  recoverable from retained evidence*.
- Result categories established: valid config accepted; dataset routing produced 8 instances / 22
  records; split 4/2/2 instances and 12/4/6 records; false / malformed / stale / instance-mismatch /
  scene-mismatch evidence each failed closed; forbidden authorisations rejected; unknown mode → 2; pilot
  mode selected the pilot route; changed `cl_bound_xy` rejected; no Isaac modules imported; production
  dataset path without a backend returned 3; no dataset directory created; committed dry-run evidence
  unchanged.
- **Ruff status: N/A — Ruff was unavailable in the environment; this is a verification limitation, not a
  lint pass** (see `H8-C-006`). `py_compile` passed.

## Negative-artifact audit

- No `assets/experiments/hospital_h8_track_b_synthetic_fork_recorded_mode_dataset/` directory created.
- Committed dry-run evidence directory unchanged (`git diff` empty).
- No new `.png/.jpg/.jpeg/.npy/.bag/.pt/.ckpt/.pth/.pkl/.bin` files.
- No Isaac/model imports added (`isaacsim`, `omni`, `pxr`, `torch`, `timm`, `wandb` absent from added
  lines); no `SimulationApp` outside the untouched pilot pragma body.

## Pilot regression

Pilot body extracted verbatim; all pilot tests (`validate_pilot_config`, `pilot_capture_plan`,
`pilot_verdict`, `finalize_pilot`, allowed-artifacts, output-path) remain green;
`select_capture_mode(pilot_cfg) == "pilot"`.

## CL_BOUND_XY result

`CL_BOUND_XY == 6.0`, read-only mirror unchanged (`h8_synthetic_fork_drive_validate.py:55`;
`h8_synthetic_fork_recorded_mode.py:59`); the dataset validator rejects any config with
`cl_bound_xy != 6.0`.

## Remaining blockers before real dataset capture

1. A reviewed **schema for real render-valid and drive-valid evidence**.
2. A **real evidence provider** binding evidence to instance, scene, configuration, and freshness.
3. A **separately reviewed real dataset capture backend** (the Isaac-executing body).
4. A **live Isaac/ROS 2 runtime-validity gate**.
5. Independent review of `bd6168a` and this documentation follow-up.
6. Explicit authorisation before any real dataset capture.
7. Canonical **Ruff lint execution** in the project environment if required by repository policy.

## Final evidence classification (see §Evidence boundary)

> The earlier 25/25 dataset dry-run established **plan validity**. Commit `bd6168a` established
> **capture-path validity** under an injected no-Isaac backend. Neither result establishes **runtime
> validity**, **dataset validity**, or **model validity**. **No real dataset exists.**

### Evidence boundary — five levels

1. **Plan validity** — established (25/25 dry-run, `66fd81e`).
2. **Capture-path validity** — established under a no-Isaac backend (`bd6168a`).
3. **Runtime validity** — **not established** (Isaac, ROS 2, rendering, driving, timing, recording).
4. **Dataset validity** — **not established** (image/trajectory quality, leakage, integrity, coverage,
   reproducibility).
5. **Model validity** — **not established** (training/evaluation performance claims).

This gate establishes **only levels 1 and 2**. Levels 3–5 remain unproven and unauthorised. Concretely:
no Isaac scene was launched; no robot path was driven; no camera frame was captured; no trajectory or
rosbag was recorded; no real render-valid or drive-valid artefact was supplied; no real dataset backend
exists; no training or evaluation was performed.

## Risk register

| Risk | Likelihood | Impact | Mitigation | Evidence | Residual status |
| --- | ---: | ---: | --- | --- | --- |
| Dataset mode falls through to pilot semantics | Medium | High | Explicit dispatch, no default | routing tests `test_B`/`test_H`/`test_I` | Closed for tested paths |
| Invalid evidence accepted | Medium | High | Strict schema + identity checks | negative tests `test_D`/`test_E`/`test_F` | Closed for tested schema cases |
| Partial outputs before failure | Medium | High | Preflight before writer creation | filesystem audit `test_D`/`test_E`/`test_L` | Closed for tested cases |
| Dry-run interpreted as capture approval | High | High | Evidence-boundary documentation | this record | Mitigated, monitor |
| Pilot behaviour regresses | Low–Medium | High | Verbatim extraction + regression tests | pilot suite | Closed |
| Validation implementations diverge | Medium | High | Shared canonical 25 checks | `validate_dataset_capture_config` reuses `dataset_dry_run_checks` | Mitigated, monitor |
| `CL_BOUND_XY` changes accidentally | Low | High | Invariant assertion + diff audit | `test_J`, diff audit | Closed |
| No-Isaac stub hides runtime defects | High | Medium | Separate future runtime gate | documented limitation `H8-C-004` | Accepted for this gate |
| Real evidence-provider absent | High | High | Future evidence-provider gate | `H8-C-005` | Open blocker |
| Real dataset backend absent | High | High | Future backend/runtime gate | `H8-DCP-011` | Open blocker |
| Ruff lint not executed | Medium | Low–Medium | Run Ruff in canonical env before promotion | `H8-C-006` | Open verification limitation |
| Documentation absent from implementation commit | — | Medium | This documentation-only commit | this record | Mitigated |

## Limitations and unresolved questions

This work does **not** prove: that Isaac loads the scene; that the robot can drive the planned routes;
that camera frames are render-correct; that ROS 2 timing is stable; that recording is lossless; that
trajectories match planned coordinates; that goal images are suitable; that no runtime leakage exists;
that the dataset is large enough for training; that training will improve ImageNav performance; that the
model is safe for closed-loop operation.

Open questions (documented, not silently assumed):
- **Evidence schema** — the render/drive-valid evidence shape used by the gate is provisional
  (`passed`, `instance_id`, `scene`, `stale`); the reviewed production schema is not yet defined.
- **Timestamp / validity-expiry semantics** — "stale" is currently a boolean flag; a real freshness /
  expiry policy (timestamps, config-hash binding) is undefined.
- **Instance identity & scene identity** — the gate checks equality of `instance_id` and `scene`
  strings; a canonical identity/hash binding to the actual authored scene is not yet specified.

## Manuscript integration

A concise, boundary-respecting entry for this gate has been added to the in-repo reproducible-project
manuscript (`docs/project_process/FleetSafe_VLN_Reproducible_Project_Manuscript.md`). The external
(Overleaf) manuscript is not reachable from this environment; the manuscript-ready evidence-boundary
paragraph is reproduced there for the author to transfer. No performance, dataset, or benchmark claim
was added to any manuscript.
