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
| Clarification (H8-REV-F-002, 2026-07-16) | The capture validator is a **strict SUPERSET** of the 25 dry-run checks: it reuses all 25 as the shared plan-validity core **and adds** capture-gate declarations (mode, `scene_base`, output-collision, capture-control detail, forbidden-output list, per-instance render/drive-required, **stray-rollout-metric-key scan**). "Single source of plan validity" refers to the shared 25-check core, not to identical acceptance. The relationship is one-directional: the capture validator is never more permissive than the dry-run (see `H8-DCP-014`). |

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

### H8-DCP-013 — Separate baseline, implementation, and evidence provenance

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | A cross-report review questioned whether Level 1 (25/25) was attributed to the correct commit. A read-only Git audit (`H8-C-007`) confirmed the attribution was correct but that the docs lacked an explicit provenance table separating the emitter from the generated evidence. |
| Decision | Each research milestone records **distinct** full hashes for: (1) analysis baseline, (2) implementation/emitter, (3) generated evidence, (4) capture-path implementation, (5) documentation. A baseline/emitter hash must not be used as the evidence hash unless the evidence artefacts are demonstrably contained in that commit. |
| Alternatives considered | (a) Leave prose-only references; (b) collapse emitter + evidence into one reported hash. |
| Reason | (a) permits the exact ambiguity raised; (b) is factually wrong here — emitter (`ecae4cd`) and evidence (`66fd81e`) are different commits. A canonical table with full hashes is auditable and prevents recurrence. |
| Evidence | Canonical provenance table in `H8_DATASET_CAPTURE_PATH_GATE.md` §A2; Git audit in `H8-C-007`. |
| Safety effect | Strengthens reproducibility; a reviewer inspects the correct repository state. |
| Reversibility | Reversible (documentation only). |
| Remaining risk | None identified. |
| Status | **Accepted** |

### H8-DCP-014 — Intentional dry-run / capture validation asymmetry (fail-safe direction)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | `H8-REV-F-001`: the dry-run's 25 plan-invariant checks do not scan for a stray rollout-metric key, while the enforcing capture validator does. A 26th numbered check would change the committed `25/25` evidence, which must stay byte-identical (`H8_DATASET_CAPTURE_PATH_GATE.md` §11 / evidence-preservation). |
| Decision | Treat the asymmetry as **intentional**: the dry-run is a plan-invariant diagnostic; the capture validator is the **enforcing strict superset**. The one-directional invariant "the capture validator is never more permissive than the dry-run" is locked by regression tests rather than by adding a 26th check. |
| Alternatives considered | (a) Add a 26th dry-run check — changes committed 25/25 evidence, disallowed; (b) fold the scan into an existing check — muddies its semantics and risks evidence drift; (c) leave undocumented — permits the ambiguity `H8-REV-F-001` raised. |
| Reason | Preserves byte-identical Level-1 evidence while making the relationship explicit and test-enforced; the finding is Low-severity and the direction is fail-safe (capture stricter, never weaker). |
| Evidence | `test_capture_validator_never_weaker_than_dry_run`; `test_stray_rollout_key_is_capture_specific_H8_REV_F_001`; `test_G` already locks capture-side rejection. |
| Safety effect | Guarantees the enforcing gate can never be weaker than the diagnostic; any accidental future weakening is caught by tests. |
| Reversibility | Reversible. |
| Remaining risk | The dry-run diagnostic alone still does not flag a stray rollout key (documented limitation; `H8-REV-F-001` = MITIGATED). |
| Status | **Accepted** |

### H8-DCP-015 — Stale-marker rejection is separate from production expiry semantics

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | The independent review found "stale" is a boolean marker in a test/injected evidence convention, not real runtime freshness. |
| Decision | The gate rejects evidence **explicitly marked** `stale: True` and makes **no** production-grade freshness claim: no timestamp parsing, no age policy, no clock source, no revocation, no replay-resistance. Age-like fields (`timestamp`, `age_s`) are **not** consulted. |
| Alternatives considered | Implement a speculative expiry/clock policy now. |
| Reason | A real freshness/expiry/revocation policy belongs to the future evidence-schema gate, not to capture-path wiring; inventing it now would overclaim. |
| Evidence | `_validity_record_status` (only the `stale` boolean is honoured); `test_stale_marker_rejection_does_not_claim_runtime_expiry_semantics`. |
| Safety effect | Keeps the claim boundary explicit; prevents mistaking marker-rejection for runtime freshness. |
| Reversibility | Reversible. |
| Remaining risk | Real freshness semantics remain unimplemented — an open blocker owned by the evidence-schema gate. |
| Status | **Accepted** |

### H8-DCP-016 — Require canonical Ruff verification before capture promotion

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | `H8-C-006`: Ruff is declared in `pyproject.toml` (`[tool.ruff]` — `line-length=100`, `select=["E","F","I","W"]`, `ignore=["E501"]`; dev-dep `ruff>=0.4`) but is **not installed** in any available environment, and the `Makefile` has no lint target. |
| Decision | Do **not** perform an uncontrolled install during a narrow gate. Keep `H8-C-006` **Open**. Require a canonical `ruff check` (from a `pip install -e '.[dev]'`-provisioned environment) to run and pass **before** any real dataset capture promotion. `py_compile` (passing) is recorded separately and is **not** a lint substitute. |
| Alternatives considered | (a) Global `pip install ruff` now — an uncontrolled env mutation affecting reproducibility; (b) claim lint passed from `py_compile` — false. |
| Reason | Preserves environment reproducibility and honesty; lint remains a genuine open verification item, not a hidden pass. |
| Evidence | `pyproject.toml` `[tool.ruff]`; `python -m ruff` unavailable in base and `.venv`; `H8-C-006` remains Open. |
| Safety effect | Prevents an unverified-lint state from being promoted silently. |
| Reversibility | N/A (process rule). |
| Remaining risk | Lint diagnostics unknown until the canonical env runs Ruff. |
| Status | **Accepted** |
