# H8 Dataset Capture-Path — Decision Log

Architectural / research decision records for the H8 synthetic-fork dataset capture-path wiring gate
(implementation commit `bd6168a`). Superseded or rejected decisions remain visible and are marked
accordingly — history is not rewritten to look cleaner than it was.

Status legend: **Proposed / Accepted / Superseded / Rejected.**

---

### H8-DCP-001 — Dedicated dataset capture validation

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | The committed capture path used only `validate_pilot_config`, which rejects a dataset config (wrong mode, missing `scene` key, non-pilot output dir, no `pilot_scope`). A dataset config could not enter the harness. |
| Decision | Add a dedicated fail-closed `validate_dataset_capture_config(cfg)` for the dataset-capture config. |
| Alternatives considered | (a) Relax `validate_pilot_config` to also accept dataset configs; (b) skip validation and rely on the planner. |
| Reason | (a) would entangle two distinct contracts and risk pilot regressions; (b) removes fail-closed safety. A separate validator keeps each contract explicit. |
| Evidence | `validate_dataset_capture_config` (harness); `test_A`, `test_G`, `test_J`. |
| Safety effect | Adds an explicit fail-closed boundary specific to dataset capture; malformed/contradictory safety fields are rejected. |
| Reversibility | Reversible (remove the function + its call). |
| Remaining risk | Validator could drift from the dry-run definition → mitigated by `H8-DCP-002`. |
| Status | **Accepted** |

### H8-DCP-002 — Shared dry-run invariants (single source of plan validity)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | Two validators (dry-run + capture) could accept different plans, silently diverging. |
| Decision | `validate_dataset_capture_config` **reuses** `dataset_dry_run_checks` (the canonical 25 checks) rather than re-implementing plan validity. |
| Alternatives considered | Duplicate the plan-validity rules inside the capture validator. |
| Reason | A single canonical definition prevents divergence between "what the dry-run certified" and "what capture will accept." |
| Evidence | `validate_dataset_capture_config` calls `dataset_dry_run_checks`; `test_dataset_dry_run_all_25_checks_pass` remains green. |
| Safety effect | Any plan that fails the 25 checks also fails capture validation. |
| Reversibility | Reversible. |
| Remaining risk | The capture validator adds extra checks beyond the 25; those extras are capture-gate declarations, not plan-validity changes. |
| Status | **Accepted** |

### H8-DCP-003 — Explicit mode selection

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | Capture routing must not guess between pilot and dataset semantics. |
| Decision | `select_capture_mode(cfg)` returns `pilot` / `dataset` / `unknown` from the config `mode`; the router acts on that. |
| Alternatives considered | Infer mode from output-dir suffix or presence of `instance_plan`. |
| Reason | Inference is brittle and can misroute; an explicit declared `mode` is auditable. |
| Evidence | `select_capture_mode`, `run_capture`; `test_H` (unknown → 2), `test_B`/`test_I`. |
| Safety effect | Unknown/absent mode fails closed (return 2), never captures. |
| Reversibility | Reversible. |
| Remaining risk | A config could declare a valid mode but be otherwise malformed → caught by the validators. |
| Status | **Accepted** |

### H8-DCP-004 — No pilot fallback

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | A dataset config must never be silently downgraded to a 1-instance pilot capture. |
| Decision | The dataset branch never calls `pilot_capture_plan`; it uses `build_dataset_plan(cfg)` exclusively. |
| Alternatives considered | Fall back to `pilot_capture_plan` when the dataset planner is unavailable. |
| Reason | Fallback would produce wrong scale (1 instance vs 8) and blur the claim boundary. |
| Evidence | `run_dataset_capture` uses `build_dataset_plan`; `test_B` asserts dataset-style ids and no `pilot_inst` ids. |
| Safety effect | Prevents scale/boundary contamination. |
| Reversibility | Reversible. |
| Remaining risk | None identified for the tested path. |
| Status | **Accepted** |

### H8-DCP-005 — Injected no-Isaac backend

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | The dataset branch must be testable without Isaac and must not initiate real capture at this gate. |
| Decision | Dataset routing is executable in tests only through an **injected** `capture_backend`; production (no backend) returns code **3** and captures nothing. Preferred a narrow DI seam over env-vars/monkeypatch. |
| Alternatives considered | (a) Implement the real Isaac backend now; (b) monkeypatch Isaac in tests; (c) env-var toggles. |
| Reason | (a) is out of scope and unsafe; (b)/(c) are implicit and fragile. A single injected callable is explicit and auditable. |
| Evidence | `run_dataset_capture(args, cfg, evidence_provider, capture_backend)`; `test_B`/`test_C` (stub backend), `test_L` (no backend → 3, nothing created). |
| Safety effect | Real capture cannot start without an explicitly injected backend; production path is inert. |
| Reversibility | Reversible. |
| Remaining risk | A no-Isaac stub cannot establish runtime validity → `H8-C-004` (accepted for this gate). |
| Status | **Accepted** |

### H8-DCP-006 — Per-instance dual evidence requirement

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | Capturing an instance without a verified renderable scene or drivable route is unsafe. |
| Decision | Each instance requires **both** render-valid and drive-valid evidence before it may proceed. |
| Alternatives considered | Require only one; or check validity post-hoc. |
| Reason | Both render and drive prerequisites are independent failure modes; both must hold pre-capture. |
| Evidence | `dataset_instance_validity_gate`; `test_D` (render), `test_E` (drive). |
| Safety effect | Fail-closed per instance; a single missing prerequisite blocks the whole run. |
| Reversibility | Reversible. |
| Remaining risk | Real evidence artefacts do not yet exist → `H8-C-005` (open blocker). |
| Status | **Accepted** |

### H8-DCP-007 — Evidence identity binding

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | Stale or mismatched evidence must not be honoured as a pass. |
| Decision | `false`, `malformed`, `stale`, `instance_mismatch`, and `scene_mismatch` evidence all fail closed with a structured reason. |
| Alternatives considered | Accept any present record; check only `passed`. |
| Reason | Presence alone is insufficient; evidence must bind to the correct instance and scene and be fresh. |
| Evidence | `_validity_record_status`; `test_F` (all five defect classes). |
| Safety effect | Prevents cross-instance / cross-scene / stale evidence from authorising capture. |
| Reversibility | Reversible. |
| Remaining risk | "stale" is a boolean flag; a real freshness/expiry policy is undefined → open question in the gate record. |
| Status | **Accepted** |

### H8-DCP-008 — Pre-output validation

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | No directory, manifest, image, or partial trajectory may be created before prerequisites pass. |
| Decision | `plan_dataset_capture` runs config + gate validation **before** any writer/backend is invoked; not-ready returns 2 with nothing created. |
| Alternatives considered | Create the output dir first, then validate. |
| Reason | Creating outputs before validation risks partial/leaky artefacts surviving a later failure. |
| Evidence | `plan_dataset_capture`, `run_dataset_capture`; `test_D`/`test_E` (backend never called), `test_L` (no dataset dir). |
| Safety effect | Zero artefacts after a failed prerequisite. |
| Reversibility | Reversible. |
| Remaining risk | Applies to the wiring path; a future real backend must preserve this ordering. |
| Status | **Accepted** |

### H8-DCP-009 — Fixed spatial bound

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | `CL_BOUND_XY` is a safety watchdog and must not change. |
| Decision | `CL_BOUND_XY` remains fixed and read-only at 6.0; the dataset validator rejects any config with `cl_bound_xy != 6.0`. |
| Alternatives considered | Make it configurable per dataset. |
| Reason | It is a safety invariant, not a tuning knob. |
| Evidence | `drive_validate.py:55`, `recorded_mode.py:59`; `test_J`. |
| Safety effect | Preserves the watchdog boundary. |
| Reversibility | Intentionally hard to change (safety). |
| Remaining risk | None identified. |
| Status | **Accepted** |

### H8-DCP-010 — Pilot-path preservation

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | The pilot capture contract must remain behaviourally unchanged. |
| Decision | The pilot body was extracted **verbatim** into `_run_pilot_capture`; validators/planners unchanged. |
| Alternatives considered | Refactor pilot + dataset into one generic path. |
| Reason | A shared rewrite risked pilot regressions; verbatim extraction is the lowest-risk change. |
| Evidence | `_run_pilot_capture`; pilot suite green; `test_I`. |
| Safety effect | No change to pilot failure behaviour. |
| Reversibility | Reversible. |
| Remaining risk | None identified. |
| Status | **Accepted** |

### H8-DCP-011 — Real capture remains blocked

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | This gate is wiring only; a real Isaac dataset backend is out of scope. |
| Decision | No real dataset capture backend is implemented or authorised; production dataset mode returns 3 without capturing. |
| Alternatives considered | Implement the backend in the same gate. |
| Reason | Runtime validity requires its own reviewed gate; conflating them would blur the evidence boundary. |
| Evidence | `run_dataset_capture` (no production backend); gate record §Remaining blockers. |
| Safety effect | Real capture cannot begin. |
| Reversibility | N/A (nothing to reverse). |
| Remaining risk | Backend + runtime validity remain open blockers. |
| Status | **Accepted** |

### H8-DCP-012 — Separate implementation and documentation commits

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | The implementation commit `bd6168a` did not include documentation; history must not be rewritten. |
| Decision | Preserve `bd6168a` as the technical implementation milestone and add a **separate documentation-only commit**; do not amend/rebase/squash. |
| Alternatives considered | Amend `bd6168a` to include docs. |
| Reason | Amending rewrites a reviewed milestone; a separate commit keeps an honest, auditable trail. |
| Evidence | This decision log + gate record; the documentation-only commit hash reported in the final report. |
| Safety effect | Preserves provenance integrity. |
| Reversibility | N/A. |
| Status | **Accepted** |
