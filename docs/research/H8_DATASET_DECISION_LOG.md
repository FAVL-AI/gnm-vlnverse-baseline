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

### H8-DCP-017 — Versioned fail-closed evidence envelope (unknown-field + downgrade protection)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | The capture-path gate consumed a provisional 4-field evidence record (`passed`/`instance_id`/`scene`/`stale`). The schema-design gate needs a production-shaped contract that cannot be silently reused across instances, scenes, routes, configs or time windows. |
| Decision | Define `EvidenceEnvelope` v`h8-evidence/1.0.0` with 14 required top-level sections (`schema_version`, `evidence_id`, `evidence_type`, `status`, `subject`, `context`, `producer`, `observation_time`, `issue_time`, `validity_window`, `integrity`, `provenance`, `revocation`, `payload`). The validator **rejects unknown top-level fields** (strict) and **rejects any `schema_version` not in the supported set** (no downgrade). Unsupported/malformed → fail closed. |
| Alternatives considered | (a) Extend the 4-field record — insufficient for identity/freshness/revocation/integrity; (b) permissive unknown-field handling — enables silent contract drift and downgrade attacks. |
| Reason | A strict, versioned envelope makes contract drift and version downgrade detectable and deterministic. |
| Evidence | `scripts/gnm/h8_evidence_schema.py` (`_ENVELOPE_KEYS`, `SUPPORTED_SCHEMA_VERSIONS`); `docs/research/schemas/h8_evidence_envelope.schema.json` (`additionalProperties:false`); tests 11, 22, `test_extra_schema_file_matches_validator_contract`. |
| Safety effect | Unknown/extra fields and unsupported versions cannot pass; the schema file and the validator are asserted mutually consistent. |
| Reversibility | Reversible (design only; no provider). |
| Remaining risk | A real signed-envelope format is deferred (`H8-C-005`); this is schema-level only. |
| Status | **Accepted** |

### H8-DCP-018 — Identity binding to one instance, with the CL_BOUND_XY watchdog bound in-subject

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | Evidence for one instance/scene/route/config must not authorise another (cross-substitution threat). |
| Decision | `subject` binds `dataset_plan_id`, `instance_id`, `split`, `scene_id`, `scene_digest`, `route_id`, `route_plan_digest`, `config_digest`, `coordinate_frame`, and `cl_bound_xy` (plus optional `start_pose`/`goal_ref`/`sim_context`). The validator compares each against a caller-supplied `expected` binding; a mismatch fails closed with a specific code (`INSTANCE_/SCENE_/ROUTE_/CONFIG_/FRAME_/BOUND_MISMATCH`). `subject.cl_bound_xy` **must equal 6.0** (the read-only watchdog) independently of `expected`. |
| Alternatives considered | A single broad scene-level record authorising many instances — explicitly disallowed unless a reuse policy is separately reviewed. |
| Reason | Per-instance binding is the core defence against silent reuse; binding the watchdog value inside the evidence ties safety scope to the evidence itself. |
| Evidence | `_SUBJECT_COMMON`, `_BINDING_REASON`, step-7 bound check; tests 13–18. |
| Safety effect | Cross-instance/scene/route/config substitution and a wrong spatial bound all fail closed. |
| Reversibility | Reversible. |
| Remaining risk | Digests are trusted as supplied; a real producer must compute them truthfully (`H8-C-005`). |
| Status | **Accepted** |

### H8-DCP-019 — Explicit validity-window freshness + revocation (supersedes the stale marker)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | `H8-DCP-015` deferred real freshness to this gate; the `stale:true` marker is not a production policy. |
| Decision | Define freshness by `observation_time`, `issue_time` and a `validity_window` (`not_before`, `not_after`, `max_age_seconds`, `clock_source:"utc"`, `clock_skew_seconds`), all RFC 3339 **UTC, timezone-required**. Time is checked against an **injected `review_time`** (deterministic; no wall-clock). The validator rejects: naive/malformed timestamps, `not_after <= not_before`, `issue_time > not_after`, `observation_time > issue_time`, `review_time` outside the window (±skew), and observation older than `max_age_seconds`. Revocation is an explicit block (`revocation.revoked` or `status=="revoked"` → `EVIDENCE_REVOKED`), with `revoked_at`/`reason`/`authority`/`replacement`/`supersedes` fields. |
| Alternatives considered | Keep the boolean stale marker (overclaims); read the system clock in the validator (non-deterministic, breaks reproducible tests). |
| Reason | Explicit windows + injected review time give a deterministic, testable freshness policy without pretending a trusted clock exists yet. |
| Evidence | `_parse_ts`, step-9 window checks, `revocation` handling; tests 8–10, 12, 20. |
| Safety effect | Stale, replayed, future-dated, revoked and clock-ambiguous evidence all fail closed. |
| Reversibility | Reversible. |
| Remaining risk | A **trusted clock** and a **live revocation distribution** are not established (design only) — deferred to the provider/runtime gates. |
| Status | **Accepted** |

### H8-DCP-020 — Canonical-JSON digests + integrity/signature/fixture separation

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | Tamper/forgery threats need deterministic content binding; unsigned test fixtures must never be mistaken for authenticated evidence. |
| Decision | Canonicalisation `h8-canonical-json/1.0` = `json.dumps(sort_keys, separators=(",",":"), UTF-8, no-NaN)`. Bind three SHA-256 digests: `subject_digest`, `payload_digest`, `content_digest` (content computed with all derived integrity fields blanked). The validator recomputes and compares all three (`DIGEST_MISMATCH`). Signatures are **optional at schema level**: `verification_status ∈ {unsigned, unverified, verified}`; a caller may `require_signature`, then only `verified` passes (`SIGNATURE_UNVERIFIED`). Synthetic fixtures carry the `synthetic-test-fixture` producer sentinel and are rejected in `production_mode` (`FIXTURE_IN_PRODUCTION`). |
| Alternatives considered | Describe unsigned fixtures as authenticated (false); embed raw images for integrity (bloats schema — replaced by `diagnostic_ref`). |
| Reason | Deterministic digests detect tampering now; signature support is declared but honestly deferred; the fixture sentinel blocks accidental promotion. |
| Evidence | `canonical_bytes`, `compute_digests`, `_digest_view`, step-8; tests 19, 30, `test_extra_signature_required_but_unverified_rejected`, `test_extra_fixture_rejected_in_production`. |
| Safety effect | Payload/subject/content tampering, unverified signatures, and test-fixtures-in-production all fail closed. |
| Reversibility | Reversible. |
| Remaining risk | Real key management / signature verification is not implemented (`H8-C-005`); schema-level digest only. |
| Status | **Accepted** |

### H8-DCP-021 — Render+drive pairing must agree on all shared bindings

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | A capture instance needs BOTH render-valid and drive-valid evidence; a mismatched or half-present pair must not authorise capture. |
| Decision | `validate_pair` requires both sides to individually pass, to share every identity binding (`dataset_plan_id`, `instance_id`, `scene_digest`, `route_plan_digest`, `config_digest`, `coordinate_frame`, `cl_bound_xy`), and to have **overlapping** validity windows; otherwise `PAIR_INCOMPLETE` / `PAIR_BINDING_MISMATCH` / `PAIR_WINDOW_DISJOINT`. No broad scene-level record may authorise unrelated instances. |
| Alternatives considered | Accept a render record alone, or allow scene-level reuse without review. |
| Reason | Capture prerequisites are jointly render+drive for the same instance; the pair check enforces that jointly. |
| Evidence | `validate_pair`, `_PAIR_SHARED`; tests 3, 4, 5, `test_extra_pair_binding_mismatch_rejected`. |
| Safety effect | Partial pairs and cross-bound pairs fail closed. |
| Reversibility | Reversible. |
| Remaining risk | Reuse policy for legitimately shared scene evidence is intentionally NOT designed here (future reviewed extension). |
| Status | **Accepted** |

### H8-DCP-022 — H8-REV-F-003 resolved by a graceful empty-plan guard

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | `H8-REV-F-003`: a direct `dataset_dry_run_checks` call on a no-instance config raised `IndexError` (empty plan → `_cross_split_pair([])`), even though both real boundaries already failed closed. |
| Decision | Add a narrow early guard in `dataset_dry_run_checks` that returns `all_pass=False` + `empty_plan=True` (a `non_empty_plan` failed check) instead of raising, and a matching guard in `write_dataset_dry_run_artifacts` that refuses to emit for an empty plan. The guard fires **only** for an empty plan; a well-formed plan is unaffected. |
| Alternatives considered | Defer again (leave the direct-call raise); guard inside `_cross_split_pair` (produces degenerate leakage cases, less clear). |
| Reason | Cleanly separable, fires only on the empty-plan path, and makes the direct validator agree with `validate_dataset_capture_config`; no runtime scope added. |
| Evidence | `dataset_dry_run_checks` guard + emitter guard; `test_29_empty_plan_graceful_and_fail_closed`; CLI empty-plan run returns 2 and creates nothing; recorded-mode suite 58/58; Level-1 evidence byte-identical. |
| Safety effect | No uncaught exception escapes the public validator; empty plan rejected deterministically at every boundary with no output created. |
| Reversibility | Reversible. |
| Remaining risk | None identified; `H8-REV-F-003` moves to **Resolved**. |
| Status | **Accepted** |

### H8-DCP-023 — Document validity vs capture-gate satisfaction (`document_only`)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | Preflight evidence is a well-formed evidence *document* that must NOT authorise capture. The schema status enum is `{valid, invalid, indeterminate, revoked}`; misusing `valid` for preflight would overclaim. |
| Decision | Extend the schema validator with a versioned, tested `document_only` mode (envelope format unchanged, `schema_version` stays `h8-evidence/1.0.0`). `document_only=True` validates structure/binding/integrity/freshness/revocation but does NOT require `status=="valid"`; the default (`document_only=False`) is the capture gate and still requires `valid`. Revoked/unknown-status are rejected in both modes. |
| Alternatives considered | (a) Set preflight `status=valid` — dishonest; (b) add a 5th status — a format change/version bump; (c) duplicate structural validation in the provider — DRY/divergence risk (`H8-C-002`). |
| Reason | Cleanly separates "is this a well-formed evidence document" from "does it authorise capture" without altering truth semantics or the envelope format. |
| Evidence | `validate_envelope(..., document_only=...)`; `preflight_satisfies_capture_gate`; provider tests 25, 26, `test_extra_document_only_extension`. |
| Safety effect | Preflight documents can be validated and stored without ever satisfying the capture gate. |
| Reversibility | Reversible. |
| Remaining risk | None; the gate check remains the default, so no caller accidentally treats a document as capture authorisation. |
| Status | **Accepted** |

### H8-DCP-024 — Preflight uses `indeterminate`; a runtime observer is mandatory for `valid`

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | The provider must never fabricate runtime render/drive validity. |
| Decision | Preflight evidence carries `status="indeterminate"`, `runtime_observed=false`, and an explicit `unobserved_runtime_checks` list. Producing `valid` render/drive status requires an authorised runtime observer; with none injected (this gate), the provider **blocks** (`PROVIDER_BLOCKED_RUNTIME_OBSERVER_MISSING`) and never falls back. |
| Alternatives considered | Emit optimistic `valid` from structural checks — overclaims runtime facts. |
| Reason | Runtime validity is a distinct, unobserved fact; the provider records only what it observed. |
| Evidence | `emit_evidence` observer gate; tests 20, 21, 22, 23, 24. |
| Safety effect | No runtime overclaim can leave the provider. |
| Reversibility | Reversible. |
| Remaining risk | A real runtime observer + review is required before any `valid` runtime evidence exists. |
| Status | **Accepted** |

### H8-DCP-025 — Real artefact digests; scene-file ≠ runtime-loaded-scene

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | Evidence must bind to real committed artefacts, but a path/filename is not proof of loaded scene content. |
| Decision | Compute real SHA-256 digests over the committed config bytes, the derived canonical plan, the committed scene `.usda` bytes (a **scene-file** digest), and a config-derived route representation. Do NOT claim Isaac loaded the scene, that the loaded scene matched the file, that assets resolved, or that rendering was correct. |
| Alternatives considered | Treat the scene path as content proof — false. |
| Reason | Distinguishes scene-reference/file identity (establishable now) from runtime-loaded-scene identity (future). |
| Evidence | `default_digest`, `build_subject_binding`; tests 01–06; `H8-C-014`. |
| Safety effect | No runtime scene claim is made from a file digest. |
| Reversibility | Reversible. |
| Remaining risk | Runtime-loaded-scene digest deferred to the runtime provider. |
| Status | **Accepted** |

### H8-DCP-026 — Dependency-scoped dirty-tree policy, dedicated namespace, atomic writes

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | Evidence generation from a mutated dependency, into a shared location, or with partial writes, is unsafe. |
| Decision | (a) A modified evidence-**dependency** artefact (config/scene/schema/provider) fails closed (`PROVIDER_DIRTY_TREE`); unrelated untracked files do not block. (b) Output goes only to the dedicated `assets/evidence/h8/preflight/` namespace, distinct from dry-run/dataset/model/benchmark outputs. (c) Writes are fully validated in memory, then temp-file + fsync + atomic rename; failed validation creates nothing. |
| Alternatives considered | Global dirty check (too strict given many pre-existing untracked files); non-atomic write (risks partial evidence). |
| Reason | Ties evidence to a clean dependency snapshot and guarantees no partial/ambiguous artefacts. |
| Evidence | `_preflight_prechecks`, `AtomicFileSink`, `InMemorySink`; tests 16, 32, 33, 39. |
| Safety effect | No evidence from a mutated dependency; no partial output; no collision with other output classes. |
| Reversibility | Reversible. |
| Remaining risk | Full atomic snapshotting across all artefacts deferred. |
| Status | **Accepted** |

### H8-DCP-027 — Deterministic evidence IDs + process-local replay/conflict control

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | Evidence needs stable identity, idempotent regeneration, and conflict detection — without overclaiming distributed guarantees. |
| Decision | Evidence id = `h8ev-<render|drive>-<slug>-<seq>` (`seq` from a digest of `kind:instance`). Regeneration from identical inputs is idempotent; the same id with **changed** content conflicts (`PROVIDER_OUTPUT_CONFLICT`); duplicate id in a bundle is rejected. Replay/conflict control is **process/sink-local**; no distributed replay protection is claimed. |
| Alternatives considered | Random ids (non-idempotent); claim distributed protection (false without a shared ledger). |
| Reason | Deterministic ids give idempotency + conflict detection now; the distributed claim is honestly deferred. |
| Evidence | `_evidence_id`, sink conflict check; tests 30, 31; `H8-C-018`. |
| Safety effect | Same-id-different-content and duplicate bundles fail closed. |
| Reversibility | Reversible. |
| Remaining risk | Distributed replay protection needs a shared registry (future). |
| Status | **Accepted** |

### H8-DCP-028 — Provider/backend separation; fixtures, clock and signatures bounded

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | The provider must not become a capture backend or overclaim authenticity/time. |
| Decision | Production mode rejects fixture sentinels/producers and never falls back; the runtime observer, Isaac backend and capture are entirely separate future gates. The clock is injected and recorded as **untrusted/observational**; signatures are digest-only with `verification_status=unsigned`, and a required-but-absent signature fails closed (`PROVIDER_SIGNATURE_REQUIRED`). No production keys or secrets are committed. |
| Alternatives considered | Bundle a runtime observer or signer now — out of scope and unreviewed. |
| Reason | Keeps trust boundaries explicit and each future capability behind its own reviewed gate. |
| Evidence | mode handling, `require_signature`, fixture-namespace guard; tests 17, 18, 19, 22, 34. |
| Safety effect | No fixture-in-production, no trusted-clock/signature overclaim, no capture path. |
| Reversibility | Reversible. |
| Remaining risk | Trusted clock, key management, runtime observer and backend remain open, each owned by a later gate. |
| Status | **Accepted** |
