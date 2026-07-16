# H8 Dataset Capture-Path — Requirements Traceability Matrix

Maps every mandatory requirement of the dataset capture-path wiring gate to an implementation symbol, a
test, and audit evidence. Implementation is in `scripts/gnm/h8_synthetic_fork_recorded_mode.py`
(symbols) and tests in `tests/gnm/test_h8_synthetic_fork_recorded_mode.py` (unless noted). Symbol
references are preferred over line numbers; a few stable line numbers are given "as of `bd6168a`".

Coverage: **21 / 21 mandatory requirements mapped (100%)**; all mapped requirements **Pass** except
`H8-R-021` (this documentation follow-up, in progress at authoring time — marked Pass on commit).

| ID | Requirement | Implementation (symbol) | Test | Evidence | Status |
| --- | --- | --- | --- | --- | --- |
| H8-R-001 | Dedicated dataset validator | `validate_dataset_capture_config` | `test_A_valid_dataset_config_accepted_by_dataset_validator` | valid committed config accepted | Pass |
| H8-R-002 | Dataset mode uses dataset planner | `run_dataset_capture` → `build_dataset_plan`; `select_capture_mode` | `test_B_dataset_mode_routes_to_build_dataset_plan_not_pilot` | backend receives 8 dataset-id plan; no `pilot_inst` ids | Pass |
| H8-R-003 | Pilot mode remains unchanged | `_run_pilot_capture` (verbatim); `select_capture_mode` | `test_I_pilot_path_unchanged_and_routes_pilot` + pilot suite | pilot tests green; `select_capture_mode(pilot)=="pilot"` | Pass |
| H8-R-004 | Unknown modes fail closed | `run_capture` (unknown → return 2); `select_capture_mode` | `test_H_unknown_capture_mode_fails_closed` | bogus mode → rc 2, backend not called | Pass |
| H8-R-005 | Render-valid evidence required | `dataset_instance_validity_gate`, `_validity_record_status` | `test_D_missing_render_valid_fails_closed_before_output` | reason `render_valid/absent`; rc 2 | Pass |
| H8-R-006 | Drive-valid evidence required | `dataset_instance_validity_gate` | `test_E_missing_drive_valid_fails_closed_before_output` | reason `drive_valid/absent`; rc 2 | Pass |
| H8-R-007 | Stale evidence rejected | `_validity_record_status` (`stale` branch) | `test_F_defective_validity_evidence_fails_closed` | reason `stale`; not ready | Pass |
| H8-R-008 | Instance mismatch rejected | `_validity_record_status` (`instance_mismatch`) | `test_F_defective_validity_evidence_fails_closed` | reason `instance_mismatch` | Pass |
| H8-R-009 | Scene mismatch rejected | `_validity_record_status` (`scene_mismatch`) | `test_F_defective_validity_evidence_fails_closed` | reason `scene_mismatch` | Pass |
| H8-R-010 | No output before validation | `plan_dataset_capture`, `run_dataset_capture` (pre-writer validation) | `test_D`, `test_E`, `test_L_dataset_wiring_creates_no_artifacts_and_no_isaac` | backend never called on failure; no dataset dir | Pass |
| H8-R-011 | Plan remains 8 instances | `build_dataset_plan` | `test_C_routed_dataset_plan_has_exact_scale` | `len(instances)==8` | Pass |
| H8-R-012 | Plan remains 22 records | `build_dataset_plan` | `test_C_routed_dataset_plan_has_exact_scale` | `len(plan)==22` | Pass |
| H8-R-013 | Split remains 4/2/2 instances | `build_dataset_plan` / config `instance_plan` | `test_C_routed_dataset_plan_has_exact_scale` | `{train:4,val:2,test:2}` | Pass |
| H8-R-014 | Record split remains 12/4/6 | `build_dataset_plan`, `_plan_per_split` | `test_C_routed_dataset_plan_has_exact_scale` | `{train:12,val:4,test:6}` | Pass |
| H8-R-015 | Forbidden authorisations rejected | `validate_dataset_capture_config` | `test_G_dataset_validator_rejects_forbidden_authorizations` | `authorizes_*`, capture-controls, forbidden-output removal, rollout key all rejected | Pass |
| H8-R-016 | `CL_BOUND_XY == 6.0` | `CL_BOUND_XY` mirror (`recorded_mode.py:59` ← `drive_validate.py:55`); validator check | `test_J_cl_bound_xy_readonly_six_in_dataset_path` | value 6.0; `cl_bound_xy!=6.0` rejected | Pass |
| H8-R-017 | No Isaac modules imported | new code has no Isaac imports; Isaac deferred inside `_run_pilot_capture` only | `test_L_dataset_wiring_creates_no_artifacts_and_no_isaac` | `isaacsim`/`omni` not in `sys.modules` | Pass |
| H8-R-018 | Production path captures nothing without backend | `run_dataset_capture` (backend `None` → rc 3) | `test_L_dataset_wiring_creates_no_artifacts_and_no_isaac` | rc 3; no dataset dir | Pass |
| H8-R-019 | Dry-run evidence remains unchanged | (no change to evidence dir) | negative-artifact audit (`git diff` empty on dryrun dir) | audit output "dry-run evidence unchanged" | Pass |
| H8-R-020 | No push or tag | process boundary | Git audit | local-only; branch `h23-execfix`; no tags created | Pass |
| H8-R-021 | Documentation captures decisions and failures | this gate's docs (gate record, decision log, failure register, journal, traceability) | documentation audit | five documents authored + manuscript entry | Pass (on documentation commit) |

## Not-applicable / deferred requirements

The following mandated *behaviours* are intentionally **not implemented** at this gate and are recorded
as remaining blockers rather than test-covered requirements (see gate record §Remaining blockers):

- Real render-valid / drive-valid **evidence artefacts and schema** — deferred (`H8-C-005`).
- Real **dataset capture backend** and **runtime-validity** gate — deferred (`H8-DCP-011`, `H8-C-004`).
- **Ruff lint** execution — not run (Ruff unavailable, `H8-C-006`); `py_compile` passed.

Every mandatory instruction thus maps to an implementation reference, a test, an audit, or an explicit
deferral justification.
