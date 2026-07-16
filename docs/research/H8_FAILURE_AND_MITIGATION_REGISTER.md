# H8 Dataset Capture-Path — Failure and Mitigation Register

Every observed failure, unexpected result, rejected approach, ambiguity, and incomplete capability for
the H8 synthetic-fork dataset capture-path wiring gate. Historical items (discovered in the readiness
analysis *before* this implementation) are recorded alongside challenges. Nothing is deleted because the
final implementation passes.

Status legend: **Open / Mitigated / Accepted / Closed.**

> **Honest chronology note.** During the *implementation* of `bd6168a`, no test failed: the narrow new
> tests passed 21/21 and the full relevant suite passed 82/82 on the first run, with no corrective code
> change required. The failures `H8-F-001…005` below are the **capture-path deficiencies discovered in
> the earlier readiness analysis**, which motivated this gate; they were mitigated by the `bd6168a`
> implementation and verified by the new tests. They are recorded here as historical, not as
> implementation-time regressions.

---

## Failures

### H8-F-001 — Dataset configuration not accepted by the capture-path validator

| Field | Content |
| --- | --- |
| Stage | Readiness / validation |
| Expected | Canonical dataset configuration is recognised by the capture path. |
| Observed | The capture path applied `validate_pilot_config`, which rejected the dataset config with 6 issues (`mode != pilot_capture_config_only`, `scene path missing: None`, non-pilot output dir, pilot-scope not tiny, full-dataset not authorised, benchmark_claim). |
| Detection method | Readiness analysis (pure-function call `validate_pilot_config(dataset_cfg)`). |
| Root cause | Capture path had no dataset-specific validator; pilot validator's contract is incompatible with a dataset config. |
| Impact | Correctness/safety: the validated dataset plan could not enter the harness. |
| Immediate containment | Readiness gate returned DEFER; no capture attempted. |
| Corrective action | Added `validate_dataset_capture_config` (`H8-DCP-001`) reusing the 25 dry-run checks (`H8-DCP-002`). |
| Verification | `test_A` (valid config accepted), `test_G` (forbidden authorisations rejected), `test_J` (bad `cl_bound_xy` rejected). |
| Regression protection | The above tests + shared `dataset_dry_run_checks`. |
| Residual risk | Validator/dry-run divergence → monitored via `H8-DCP-002`. |
| Status | **Mitigated** |

### H8-F-002 — Capture mode used pilot semantics

| Field | Content |
| --- | --- |
| Stage | Readiness / routing |
| Expected | Dataset mode uses dataset planning semantics. |
| Observed | `run_capture` unconditionally called `load_pilot_config` / `validate_pilot_config` / `pilot_capture_plan` / `cfg["scene"]`. |
| Detection method | `inspect.getsource(run_capture)` in the readiness analysis. |
| Root cause | Single hard-wired pilot capture path; no routing. |
| Impact | Wrong plan, wrong scale, boundary confusion. |
| Immediate containment | Readiness gate DEFER. |
| Corrective action | Explicit `select_capture_mode` + router `run_capture` (`H8-DCP-003`), no pilot fallback (`H8-DCP-004`). |
| Verification | `test_B` (dataset routes to dataset planner), `test_I` (pilot routes to pilot). |
| Regression protection | `test_B`, `test_H`, `test_I`. |
| Residual risk | None identified for tested paths. |
| Status | **Mitigated** |

### H8-F-003 — Wired pilot planner cannot build the dataset plan

| Field | Content |
| --- | --- |
| Stage | Readiness / routing |
| Expected | The routed planner returns 8 instances and 22 planned frame records. |
| Observed | `pilot_capture_plan(dataset_cfg)` produced 1 base-only instance (`pilot_inst0`); it reads `pilot_scope`, not `instance_plan`. |
| Detection method | Readiness analysis (direct call). |
| Root cause | Pilot planner cannot represent the dataset `instance_plan`. |
| Impact | Dataset execution path structurally unavailable. |
| Immediate containment | Readiness gate DEFER. |
| Corrective action | Route dataset mode to `build_dataset_plan(cfg)` + `cfg["scene_base"]` (`H8-DCP-004`). |
| Verification | `test_C` (exact 8 instances / 4-2-2 / 22 records / 12-4-6). |
| Regression protection | `test_C`. |
| Residual risk | None identified. |
| Status | **Mitigated** |

### H8-F-004 — Missing render-valid evidence did not defer

| Field | Content |
| --- | --- |
| Stage | Readiness / gating |
| Expected | Missing render-valid evidence blocks the instance before output. |
| Observed | The capture path had no per-instance render-valid gate (`run_capture` referenced no `render_valid_required`). |
| Detection method | Readiness analysis (source inspection). |
| Root cause | No prerequisite gating in the capture path. |
| Impact | Frames could be generated from an unverified render state. |
| Immediate containment | Readiness gate DEFER. |
| Corrective action | `dataset_instance_validity_gate` requires render-valid evidence pre-output (`H8-DCP-006`, `H8-DCP-008`). |
| Verification | `test_D` (absent), `test_F` (false/malformed/stale/instance-/scene-mismatch). |
| Regression protection | `test_D`, `test_F`. |
| Residual risk | Real render-valid artefacts not yet defined → `H8-C-005`. |
| Status | **Mitigated** |

### H8-F-005 — Missing drive-valid evidence did not defer

| Field | Content |
| --- | --- |
| Stage | Readiness / gating |
| Expected | Missing drive-valid evidence blocks the instance before output. |
| Observed | No per-instance drive-valid prerequisite in the capture path. |
| Detection method | Readiness analysis (source inspection). |
| Root cause | No prerequisite gating. |
| Impact | Trajectory capture could occur without a verified drivable route. |
| Immediate containment | Readiness gate DEFER. |
| Corrective action | `dataset_instance_validity_gate` requires drive-valid evidence pre-output (`H8-DCP-006`, `H8-DCP-008`). |
| Verification | `test_E` (absent); `test_F` shares the defect classes. |
| Regression protection | `test_E`, `test_F`. |
| Residual risk | Real drive-valid artefacts not yet defined → `H8-C-005`. |
| Status | **Mitigated** |

## Challenges

### H8-C-001 — Dry-run success could be misinterpreted as capture authorisation

- Risk: a 25/25 dry-run result may be presented as evidence that real capture is ready.
- Mitigation: separate plan-validity, path-validity, runtime-validity, data-validity, and
  training-validity gates; explicit five-level evidence boundary in the gate record and CLI output
  (`run_dataset_capture` prints `"authorized": false`).
- Verification: gate record §Evidence boundary; `run_dataset_capture` note string.
- Status: **Mitigated (monitor)**.

### H8-C-002 — Duplicated validation logic could diverge

- Risk: dry-run validator and capture validator could accept different plans.
- Mitigation: `validate_dataset_capture_config` reuses `dataset_dry_run_checks` (`H8-DCP-002`).
- Verification: same 25 checks drive both; `test_dataset_dry_run_all_25_checks_pass` + `test_A`.
- Status: **Mitigated (monitor)**.

### H8-C-003 — Partial artefacts could survive failed prerequisites

- Risk: a directory, manifest, RGB file, or partial trajectory could be created before a later failure.
- Mitigation: validate all instance prerequisites before any writer/backend is invoked (`H8-DCP-008`).
- Verification: `test_D`/`test_E` (backend never called), `test_L` + negative-artifact audit (no
  dataset dir; zero forbidden artefacts).
- Status: **Mitigated**.

### H8-C-004 — A no-Isaac backend cannot establish live runtime validity

- Risk: passing tests under a stub could be misread as runtime readiness.
- Mitigation: documented as a limitation; runtime validity deferred to a separate future gate.
- Verification: gate record §Evidence boundary (level 3 not established).
- Status: **Open / Accepted for this gate**.

### H8-C-005 — The real evidence-provider schema is not yet implemented

- Risk: the render/drive-valid evidence shape used here is provisional (`passed`, `instance_id`,
  `scene`, `stale`); a reviewed production schema and a real provider do not exist.
- Mitigation: default `null_evidence_provider` fails closed; a reviewed schema + provider is a named
  remaining blocker.
- Verification: gate record §Remaining blockers (items 1–2) and §Open questions.
- Status: **Open blocker**.

### H8-C-006 — Ruff was unavailable, so lint evidence is incomplete

| Field | Content |
| --- | --- |
| Expected | Run the repository's normal Ruff lint gate on the changed files. |
| Observed | `ruff` was not available in the environment (`python -m ruff --version` failed). |
| Containment | **No claim of Ruff success was made.** |
| Available verification | `python -m py_compile` passed on both changed files. |
| Status | **Open verification limitation (accepted for this gate)** |
| Next mitigation | Run Ruff in the canonical project environment before any later promotion or capture approval. |

> "Ruff unavailable" is explicitly **not** converted into "lint passed."
