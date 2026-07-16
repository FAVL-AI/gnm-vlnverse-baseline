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

### H8-DCP-029 — Positive production trust (deny-by-default), not fixture-marker absence

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | `H8-PREV-F-001` (High): production acceptance depended on the ABSENCE of a single fixture marker (`producer.component`); renaming it laundered a fixture into production. |
| Decision | Production acceptance is POSITIVE: `check_production_trust` accepts only a producer that is registered, enabled, in a production-permitted trust class, and permitted for this mode/evidence-type/schema-version. Unknown/incomplete → `PRODUCER_NOT_AUTHORISED` (fail closed). The default policy authorises NO production producer, so everything fails closed this gate. |
| Alternatives considered | Extend the fixture blacklist (still a negative check; new fixture markers would reopen the hole). |
| Reason | Deny-by-default with an explicit allow-list cannot be bypassed by removing/renaming fixture markers. |
| Evidence | `check_production_trust`, `DEFAULT_PRODUCER_POLICY`; tests `test_f001_*`. |
| Safety effect | Fixture-to-production promotion and unknown-producer acceptance both fail closed. |
| Reversibility | Reversible. |
| Remaining risk | A real production producer requires a separately reviewed registration + signatures (`H8-C-009`). |
| Status | **Accepted** |

### H8-DCP-030 — External trust policy over self-declared evidence trust

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | Evidence must not be able to self-promote its trust class/mode/authorisation. |
| Decision | Trust is decided by an EXTERNAL, repository-controlled `ProducerTrustPolicy` keyed by producer id; the validator never reads a `trust_class`/authorisation field from the envelope. Schema version is unchanged — no new envelope fields. |
| Alternatives considered | An envelope `trust_class` field (self-declarable → forgeable). |
| Reason | External policy removes the self-promotion attack surface entirely. |
| Evidence | `test_f001_self_declared_trust_class_ignored`; policy read from `trust_policy` arg, not the envelope. |
| Safety effect | Trust-class self-promotion is structurally impossible. |
| Reversibility | Reversible. |
| Remaining risk | Policy integrity relies on VCS review; a signed policy is future work. |
| Status | **Accepted** |

### H8-DCP-031 — Fixture indicators are defence-in-depth, not the primary trust boundary

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | Fixture provenance must be caught even when individual markers are stripped. |
| Decision | `_has_fixture_provenance` inspects 10 independent indicators (producer component/method, provenance producer_component/run_id/method_id/scene_source/config_source, payload diagnostic_ref scheme, producer/integrity key_id). ANY hit → `FIXTURE_IN_PRODUCTION`. This SUPPLEMENTS the positive trust decision; it is not the sole boundary. |
| Alternatives considered | Rely on one sentinel (the original defect). |
| Reason | Removing one marker leaves the others; combined with deny-by-default, laundering fails. |
| Evidence | `test_f001_single_indicator_remaining_rejected`, `_renamed_/_removed_/_run_id_only_`. |
| Safety effect | Single-marker stripping cannot promote a fixture. |
| Reversibility | Reversible. |
| Remaining risk | New fixture markers must be added to the detector as fixtures evolve. |
| Status | **Accepted** |

### H8-DCP-032 — Typed runtime-observer capability contract (presence ≠ capability)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | `H8-PREV-F-002` (Medium): the runtime-observer gate was a truthiness check; any truthy object bypassed it. |
| Decision | `validate_runtime_observer` requires observer_id/version/supported_evidence_types/supported_schema_versions/`available is True`/callable observe_render+observe_drive AND an authorised observer_id (`AUTHORISED_OBSERVER_IDS` empty this gate). Invalid/partial/unauthorised → `PROVIDER_OBSERVER_INVALID`; None → `PROVIDER_BLOCKED_RUNTIME_OBSERVER_MISSING`. No Isaac observer implemented; stubs are test-only and unauthorised. |
| Alternatives considered | Keep the `is None` check (fail-open to truthiness). |
| Reason | Presence is not proof of capability; a typed contract + policy authorisation is required. |
| Evidence | `test_f002_*`. |
| Safety effect | Arbitrary/partial observers cannot enable runtime-valid emission (none is authorised anyway). |
| Reversibility | Reversible. |
| Remaining risk | The real observer interface is finalised at the runtime-validity gate. |
| Status | **Accepted** |

### H8-DCP-033 — Mandatory fail-closed dirty-tree enforcement

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | `H8-PREV-F-003` (Medium): dirty-tree enforcement was skipped when `tree_state` was not injected. |
| Decision | Protected preflight/production generation fails closed when the tree-state resolver is absent, raises, is non-dict, or does not report `dependency_dirty is False`. No `allow_dirty` override, no permissive default. Unrelated untracked files do not block (the resolver scopes `dependency_dirty` to the dependency set). |
| Alternatives considered | Opt-in check (the defect); a broad `allow_dirty=True` production flag (explicitly forbidden). |
| Reason | Cleanliness is a safety precondition and must not be silently omittable. |
| Evidence | `_preflight_prechecks`; `test_f003_*`. |
| Safety effect | Evidence cannot be generated from an unverified working tree. |
| Reversibility | Reversible. |
| Remaining risk | Correct scoping of `dependency_dirty` is the caller's responsibility (documented). |
| Status | **Accepted** |

### H8-DCP-034 — Active vs reserved provider reason codes

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | `H8-PREV-F-004` (Low): four provider reason codes were unused/unreachable. |
| Decision | `PROVIDER_ARTIFACT_DIGEST_FAILED`, `PROVIDER_CLOCK_UNTRUSTED`, `PROVIDER_SCHEMA_REJECTED` are wired reachable and tested; `PROVIDER_MODE_INVALID` is a RESERVED defensive code (`PROVIDER_RESERVED_CODES`) — the constructor rejects invalid modes, so its emit-branch is unreachable — and is excluded from active-coverage accounting. |
| Alternatives considered | Remove all four (loses defensive/future codes). |
| Reason | Active codes must all be triggerable; a small, explicitly-reserved set avoids false coverage claims. |
| Evidence | `test_f004_*`; `PROVIDER_ACTIVE_CODES` / `PROVIDER_RESERVED_CODES`. |
| Safety effect | Reason-code coverage is now honest; no silent dead taxonomy. |
| Reversibility | Reversible. |
| Remaining risk | None. |
| Status | **Accepted** |

## H8 Isaac Backend & Runtime-Validity Architecture Design Gate (2026-07-16)

Decisions from `docs/research/H8_ISAAC_BACKEND_RUNTIME_ARCHITECTURE.md`. Design-only; nothing implemented,
launched, or captured.

### H8-DCP-035 — Isolated Isaac worker architecture (Option B)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | Three patterns evaluated: in-process (A), isolated worker (B), separate service (C). |
| Decision | Select **Option B** — a Capture Orchestrator drives a constrained Isaac worker over a typed local protocol; strong process isolation, restartability, controller-side policy, boundary signing. |
| Alternatives considered | A (crash propagation, low isolation/auditability); C (deployment/network-trust/latency overhead, unneeded for one-instance validation). |
| Reason | Isolation and auditability dominate for a first runtime-validity gate. |
| Safety effect | An Isaac crash cannot corrupt the capture controller or its audit trail. |
| Reversibility | Reversible (C remains a future scaling option). |
| Remaining risk | Local-protocol integrity must be designed (owned G4). |
| Status | **Accepted** |

### H8-DCP-036 — First runtime worker owns NO dataset writer

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | Runtime testing must not silently become unauthorised capture. |
| Decision | The initial Isaac worker has **no dataset-writer capability**; the writer stays the existing separable `capture_backend` DI slot and is connected only at a later gate (G9), after runtime evidence is independently reviewed (G8). |
| Alternatives considered | Worker owns writer (couples testing to capture — rejected). |
| Reason | Capability separation prevents capture-before-authorisation. |
| Safety effect | `capture_backend=None → rc3, captures nothing` already holds; the worker cannot write frames/trajectories/rosbags. |
| Reversibility | Reversible under explicit later gate. |
| Remaining risk | Writer-bypass must be tested (G4/G9). |
| Status | **Accepted** |

### H8-DCP-037 — Two-phase capture authorisation + one-time token

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | Capture must not begin on a truthy status. |
| Decision | Phase A establishes signed runtime render/drive evidence (no writer); Phase B activates capture only after a one-time, expiring, revocable `CaptureAuthToken` bound to the exact `runtime_identity_digest`. |
| Alternatives considered | Single-phase gate (no TOCTOU protection — rejected). |
| Reason | Separates evidence establishment from capture activation; enables re-inspection (H8-DCP-042). |
| Safety effect | Preflight/document_only evidence can never authorise capture. |
| Reversibility | Reversible. |
| Remaining risk | Token infra unbuilt (`H8-C-030`, G10). |
| Status | **Accepted** |

### H8-DCP-038 — Positive runtime-observer authorisation (reuse existing contract)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | Observers must be authenticated, not merely present. |
| Decision | `RenderValidityObserver`/`DriveValidityObserver` must satisfy the existing typed `validate_runtime_observer` contract AND the external producer trust policy; `AUTHORISED_OBSERVER_IDS` is extended only via a reviewed policy (empty today). |
| Alternatives considered | New parallel observer scheme (rejected — reuse the reviewed contract). |
| Reason | No weaker parallel path; single reviewed trust surface. |
| Safety effect | Truthy/partial/unauthorised observers already fail closed. |
| Reversibility | Reversible. |
| Remaining risk | Real observer unbuilt (`H8-C-029`, G3/G6/G7). |
| Status | **Accepted** |

### H8-DCP-039 — Trusted-clock separation (sim time ≠ trusted wall time)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | Isaac simulation time is not trusted wall time. |
| Decision | Record `ts_sim` (simulation ordering) and `ts_wall` (trusted freshness) separately; freshness/validity windows evaluate `ts_wall` only; monotonic+wall cross-check detects backward clocks; unavailable trusted time → `CLOCK_UNTRUSTED`, capture blocked. |
| Alternatives considered | Use sim time for freshness (rejected — forgeable/unbounded). |
| Reason | Freshness must derive from a trusted external clock. |
| Safety effect | Stale/replayed evidence cannot pass as fresh. |
| Reversibility | Reversible. |
| Remaining risk | Trusted clock unavailable (`H8-C-026`, G2). |
| Status | **Accepted** |

### H8-DCP-040 — Signature & key-management model (no repo secrets)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | Production runtime evidence needs authenticity without committing secrets. |
| Decision | Detached signatures over canonical envelope bytes; keys stored external to the repo; rotation+revocation via policy; unsigned/unknown/expired/revoked → deny. Synthetic keys, if ever created, are fixture-only and rejected by production trust. No secret/placeholder-key is ever committed. |
| Alternatives considered | In-repo keys (rejected — secret exposure). |
| Reason | Authenticity with least secret exposure. |
| Safety effect | Forged/unsigned runtime evidence denied in production. |
| Reversibility | Reversible. |
| Remaining risk | Key mgmt unavailable (`H8-C-027`, G2). |
| Status | **Accepted** |

### H8-DCP-041 — Revocation dependency fail-closed

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | Revocation status may be offline or stale. |
| Decision | Revocation covers producer/observer/key/evidence-id/token/scene/route/config/backend-version; offline or cache-older-than-max-age → `REVOCATION_STATUS_UNAVAILABLE`, capture blocked. |
| Alternatives considered | Fail-open when offline (rejected). |
| Reason | Unknown revocation status must not authorise capture. |
| Safety effect | Capture blocked without current revocation evidence. |
| Reversibility | Reversible. |
| Remaining risk | Revocation service unavailable (`H8-C-028`, G2). |
| Status | **Accepted** |

### H8-DCP-042 — Runtime-change (TOCTOU) invalidation

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | State can change between authorisation and capture. |
| Decision | Re-inspect `runtime_identity_digest` between authorisation and each capture step; any delta (scene/asset/robot/camera/route/offset/frame/config/restart/policy/key/revocation) → `RUNTIME_STATE_CHANGED`, stop + quarantine. |
| Alternatives considered | One-shot check at authorisation (rejected — TOCTOU window). |
| Reason | Closes time-of-check/time-of-use gap. |
| Safety effect | Post-authorisation mutation halts capture. |
| Reversibility | Reversible. |
| Remaining risk | Re-inspection cost/impl (G10). |
| Status | **Accepted** |

### H8-DCP-043 — Partial-output quarantine (never auto-admit)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | A failure mid-capture may leave partial frames/trajectories. |
| Decision | Partial artefacts are quarantined to an invalid/forensic namespace, never auto-deleted and never auto-admitted; failure evidence is generated; admission requires the transactional gate + human review. |
| Alternatives considered | Auto-delete (loses forensics) / auto-retain-as-valid (contaminates dataset) — both rejected. |
| Reason | Forensic value without dataset contamination. |
| Safety effect | Partial data cannot enter training data automatically. |
| Reversibility | Reversible. |
| Remaining risk | Output transaction unbuilt (`H8-C-031`, G9). |
| Status | **Accepted** |

### H8-DCP-044 — One-instance-first progression; review before capture connectivity

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | The backend must not be one monolithic "implement" step. |
| Decision | 13 explicit future gates G1–G13; runtime evidence is independently reviewed (G8) before any writer is connected (G9); a single instance (G10/G11) precedes the 8-instance approval (G13). |
| Alternatives considered | Single "implement backend" phase (rejected). |
| Reason | Bounded, reviewable increments; no capture on green tests alone. |
| Safety effect | Each capability is gated and reviewed. |
| Reversibility | Reversible. |
| Remaining risk | None (process control). |
| Status | **Accepted** |

### H8-DCP-045 — Interfaces are specifications, not committed code, this gate

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | This is an architecture/design gate; the first implementation must be the Git resolver. |
| Decision | Runtime interfaces (`H8RuntimeBackend`, observers, resolver, authoriser) are specified as design pseudocode only; no runtime `.py` is committed here. The first implementation gate is `G1` (Git resolver). |
| Alternatives considered | Commit non-operational stubs now (deferred to avoid backend scope-creep before G1). |
| Reason | Keep the boundary crisp; resolver-first ordering. |
| Safety effect | No new importable runtime/Isaac code enters the tree this gate. |
| Reversibility | Reversible (stubs may be added at G3/G4). |
| Remaining risk | None. |
| Status | **Accepted** |

### H8-DCP-046 — Concrete Git dependency resolver (discharges H8-PRREV-F-002)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Context | The re-review found no concrete git resolver exists; the provider trusts an injected `dependency_dirty` bool. |
| Decision | Specify a deterministic `GitDependencyResolver` with an explicit fail-closed decision for every dependency state (staged/unstaged/deleted/renamed/untracked-replacement/ignored/symlink/submodule/LFS/detached/shallow/no-git/command-failure/repo-mismatch/outside-repo/commit-mismatch/indeterminate) over a named closure, emitting a `closure_digest` bound into runtime identity. Implementation + independent review is gate `G1`. |
| Alternatives considered | Keep trusting an injected boolean (rejected — the re-review's key deferred dependency). |
| Reason | A real, reviewed resolver is prerequisite to any runtime evidence. |
| Safety effect | Any unresolved/ambiguous dependency state blocks capture. |
| Reversibility | Reversible. |
| Remaining risk | Resolver unbuilt until G1 (`H8-C-020`). |
| Status | **Accepted** |

## G1 — H8 Git Dependency Resolver Implementation Gate (2026-07-16)

Decisions from `docs/research/H8_GIT_DEPENDENCY_RESOLVER.md` + `scripts/gnm/h8_git_dependency_resolver.py`.
Non-Isaac, non-capturing; implements the concrete resolver specified by `H8-DCP-046`.

### H8-DCP-047 — Git is the required provenance authority

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | Every H8 evidence-defining dependency must be proven against Git (tracked, unmodified, bound to HEAD). "Could not inspect" is never treated as clean; Git unavailable/timeout/failure → reject. |
| Reason | Filesystem state alone cannot prove provenance. |
| Safety effect | Dirty/substituted/Git-unavailable dependencies fail closed. |
| Status | **Accepted** |

### H8-DCP-048 — Explicit, versioned dependency closure (manifest)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | The closure is a repository-tracked, versioned manifest (`configs/gnm/h8_dependency_manifest.json`, `h8-dependency-manifest/1.0.0`) with a JSON schema; it is self-referential (lists the resolver + itself + its schema). Future policies are recorded as documentation-only `future_dependencies`. |
| Reason | The closure must be explicit, reviewable and itself provenance-bound. |
| Status | **Accepted** |

### H8-DCP-049 — Repository identity by root-commit + name (not path/cwd/.git)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | Repository identity binds `(canonical_name + root_commit)` plus toplevel; it does NOT rely on absolute machine path, folder name, cwd, or mere `.git` presence. |
| Reason | Copied/nested/other repositories must be rejected; identity must be portable and durable. |
| Status | **Accepted** |

### H8-DCP-050 — Staged AND unstaged states both forbidden

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | A protected dependency must match HEAD in both index and worktree; staged modification/addition, worktree modification, delete, rename, index-removal, mode change, `assume-unchanged` and `skip-worktree` all fail closed. |
| Reason | Only content bound to HEAD is provenance-valid. |
| Status | **Accepted** |

### H8-DCP-051 — Mandatory resolver in protected provider modes; no bypass

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | The provider consumes the resolver only via the injected `tree_state` seam; an absent/unavailable/fixture/mismatched/stale report yields `dependency_dirty=True` → `PROVIDER_DIRTY_TREE`. There is no `assume_clean` bypass and no capture authorisation from a resolver report. |
| Reason | The provider must never emit protected evidence without a clean, bound closure. |
| Status | **Accepted** |

### H8-DCP-052 — Explicit symlink policy (forbidden by default)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | Protected dependencies must be ordinary tracked files unless explicitly `allow_symlink`; unexpected symlink, absolute target, escape-outside-repo and broken target reject. Complete symlink-TOCTOU prevention is NOT claimed (`H8-C-033`). |
| Reason | Symlink substitution is a real redirection threat. |
| Status | **Accepted** |

### H8-DCP-053 — Explicit LFS and submodule policies (fail closed)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | LFS pointers are detected; `materialised_required` fails closed (git-lfs is not installed — materialisation is never downloaded); malformed pointers reject. Gitlinks with no submodule policy or a commit mismatch reject; submodules are never initialised/updated. |
| Reason | Pointer/gitlink content must be proven, not assumed. |
| Status | **Accepted** |

### H8-DCP-054 — Deterministic closure digest excluding volatile metadata

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | The `closure_digest` is computed over sorted (id, path, reason, head-object, required) and EXCLUDES timestamps/host paths, so identical repo state yields an identical digest regardless of run time or manifest ordering. |
| Reason | Determinism is required for report binding and stale detection. |
| Status | **Accepted** |

### H8-DCP-055 — Stale invalidation is content-bound (time-based deferred)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | A report is invalidated when its `closure_digest` no longer matches the caller's expected digest (any protected change alters it). Strong time-based freshness is deferred to the future trusted clock; `REPORT_STALE` is reserved (`H8-C-034`). |
| Reason | Content binding is provable now; time freshness is not (no trusted clock yet). |
| Status | **Accepted** |

### H8-DCP-056 — Fixture resolver prohibited in protected modes

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | Only an APPROVED `resolver_id` may back a protected provider mode; `h8-fixture-resolver` is rejected (`RESOLVER_FIXTURE_IN_PROTECTED`), mirroring the positive producer-authorisation design. A report cannot self-authorise through content. |
| Reason | Test resolvers must never gate protected evidence. |
| Status | **Accepted** |

### H8-DCP-057 — Additive provenance field only; provider trust unchanged

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | The only provider change is additive: `build_provenance` records an optional `dependency_resolution_digest` (None when absent). No trust-boundary guarantee, schema version, `document_only` semantics, dual render/drive prerequisite or `CL_BOUND_XY` is altered; all prior 223 H8 tests still pass. |
| Reason | Bind evidence to the resolved closure without weakening any existing control. |
| Status | **Accepted** |

### H8-DCP-058 — In-process report authenticity marker (F-001 partial)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | The genuine resolver stamps `authenticity = "h8-resolver-authentic/1.0.0"` on every report; `report_binding_ok` rejects any report lacking it (`REPORT_UNAUTHENTIC`) before honouring `overall_accepted`. This defeats an ordinary caller-forged dict presenting the approved `resolver_id`. It is explicitly NOT cryptographic — code with module access can copy the constant; that residual is documented and deferred to G2. |
| Reason | Close the plain-dict forgery path (`H8-G1REV-F-001`) in-process now; cryptographic authentication belongs to G2. |
| Status | **Accepted — PARTIAL (residual to G2)** |

### H8-DCP-059 — Trusted construction path for protected provider modes (F-001 primary control)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | Protected provider modes obtain their `tree_state` via `trusted_provider_tree_state(repo_root)`, which constructs the genuine resolver in-process and re-resolves current state on every call. It exposes NO parameter for a caller-supplied resolver, report, manifest object/path, or assume-clean flag (`git`/`fs` are a documented test-only fixture seam with no acceptance authority). A fabricated resolution cannot be substituted structurally, not merely by string check. |
| Reason | The durable control against forged resolutions is that protected callers never accept a caller report at all. |
| Status | **Accepted** |

### H8-DCP-060 — One canonical repository-tracked manifest (F-002)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | `resolve_canonical` loads ONLY `configs/gnm/h8_dependency_manifest.json` (`CANONICAL_MANIFEST_REL`); it never accepts a caller-selected path or in-memory dict. It requires the manifest to self-list at the canonical path (`MANIFEST_NOT_CANONICAL`), enforces a machine-checked mandatory id set `REQUIRED_DEPENDENCY_IDS` (`MANIFEST_INCOMPLETE`), and then resolves the manifest FILE itself (tracked + unmodified + bound to HEAD). A reduced or substituted manifest can no longer hide a dirty or omitted decision-critical dependency. |
| Reason | Close the caller-selected-manifest bypass (`H8-G1REV-F-002`); the tracked manifest is the single source of truth. |
| Status | **Accepted** |

### H8-DCP-061 — Security-relevant Git state pinned and inspected (F-003)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | Every protected git invocation prepends `-c core.fileMode=true -c core.symlinks=true -c core.ignorecase=false -c core.autocrlf=false --no-replace-objects` and runs under `LC_ALL=C`/`LANG=C`. `inspect_git_config` additionally REJECTS a repository carrying replace refs (`GIT_REPLACE_OBJECTS`) or an alternate object database (`GIT_ALTERNATE_OBJECTS`). A test proves a locally-set `core.fileMode=false` no longer masks a chmod. This is MITIGATED-WITH-LIMITATIONS: it neutralises the enumerated config surfaces, not an exhaustive proof that no Git configuration can influence any observation. |
| Reason | Close the enumerated config-masking surfaces (`H8-G1REV-F-003`) without over-claiming completeness. |
| Status | **Accepted — MITIGATED WITH DOCUMENTED LIMITATIONS** |

### H8-DCP-062 — Copied-history origin remains unresolved (F-004 deferred)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | Repository identity binds `(canonical_name + root_commit + history)`; an exact copy of the Git object history reproduces that identity. This is NOT closed by ordinary Git inspection and is explicitly NOT closed via remote-URL comparison (a remote URL is caller-mutable and proves nothing). Cryptographic origin attestation is deferred to G2 or a later provenance-infrastructure gate. |
| Reason | Honest scoping: physical-origin attestation requires signatures/attestation infrastructure out of scope for G1R. |
| Status | **Open — deferred to G2** |

### H8-DCP-063 — Exact Boolean `required` for mandatory dependencies (G1R2, closes H8-G1RREV-F-001)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | `resolve_canonical` enforces that every `REQUIRED_DEPENDENCY_IDS` entry is present AND has `required is True` (identity check, no truthiness coercion). `false`, missing, `null`, `0`, `1`, `"true"`, `"false"` all reject with `MANDATORY_DEPENDENCY_NOT_REQUIRED`. A mandatory dependency can no longer be silently downgraded to optional to hide a dirty/omitted artefact. Non-mandatory dependencies may still be `required:false`. |
| Reason | Presence alone was insufficient; the mandatory-set control must resist weakening, not only removal. |
| Status | **Accepted** |

### H8-DCP-064 — Duplicate mandatory dependency fails closed with a specific code (G1R2)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | `load_dependency_manifest` separates empty-id (`DEPENDENCY_MANIFEST_INVALID`) from duplicate-id and accepts a `duplicate_code`; the canonical path passes `MANIFEST_DUPLICATE_DEPENDENCY` so duplicate ids fail closed rather than collapsing under last-write-wins in the `{id: dep}` map. The generic path keeps `DEPENDENCY_MANIFEST_INVALID`. |
| Reason | A duplicate mandatory id must never be resolved ambiguously. |
| Status | **Accepted** |

### H8-DCP-065 — Explicit Git subprocess-environment policy (G1R2, closes H8-G1RREV-F-003 env vector)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | The git runner constructs the child environment explicitly (`_build_git_env`): Class A forced-safe (`LC_ALL/LANG=C`, `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=os.devnull`, `GIT_ATTR_NOSYSTEM=1`, `GIT_OPTIONAL_LOCKS=0`, `GIT_TERMINAL_PROMPT=0`); Class B removed (`GIT_DIR/WORK_TREE/COMMON_DIR/OBJECT_DIRECTORY/ALTERNATE_OBJECT_DIRECTORIES/INDEX_FILE/REPLACE_REF_BASE/NAMESPACE`, `GIT_CONFIG[_GLOBAL/_SYSTEM/_COUNT]`, `GIT_CONFIG_KEY_*/VALUE_*`, ceiling/discovery/attr-system/pathspec vars); Class C — `resolve_canonical` additionally fails closed (`GIT_ENV_UNSUPPORTED`) if any prohibited redirection/override var is present in the parent env. Repository identity is carried by `-C`, never inherited. Ordinary vars (PATH, HOME) are preserved. |
| Reason | Security-relevant Git environment must not redirect trust decisions; ambiguous env fails closed. |
| Status | **Accepted** |

### H8-DCP-066 — Known mandatory coverage ≠ semantic completeness; content identity deferred (G1R2)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | The mandatory-set control enforces presence + exact-required + known categories for a fixed id set; it does NOT prove the set captures every future semantic dependency, nor bind each entry's content identity (path-substitution to another expected-type tracked file is still accepted — `H8-G1RREV-F-002`). A dedicated test keeps this residual visible. Per-dependency expected-digest binding and semantic discovery are deferred to G2. Documentation (G1R remediation report clarification) states the caller-manifest boundary precisely (closes `H8-G1RREV-F-004`). |
| Reason | Honest scoping: do not disguise semantic-identity as solved through category presence. |
| Status | **Accepted — with documented limitation** |

## G2 — H8 Cryptographic Trust Architecture & Design Gate — decisions (2026-07-16)

**Design / specification / threat-model only.** No key, signature, certificate, token, signing/verification/
revocation/timestamp service, observer, Isaac, ROS 2, render, drive or capture is created. Every decision
below is a **design requirement for a future bounded implementation gate**, not an operational control.
Primary document: `docs/research/H8_G2_CRYPTOGRAPHIC_TRUST_ARCHITECTURE.md`.

### H8-DCP-067 — Canonicalisation = JCS (RFC 8785), floats prohibited (G2 §9)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | Signed bytes are produced by JSON Canonicalization Scheme (RFC 8785): UTF-8, lexicographic keys, shortest-decimal integers, **no floats in the signed payload**, NFC, POSIX repo-relative paths, RFC 3339 UTC `Z` times, duplicate keys rejected, unknown/extra fields rejected, explicit `extensions` object, schema-version bound in. Evaluated JCS vs deterministic CBOR (RFC 8949 §4.2) vs Protobuf; CBOR documented as migration option; Protobuf rejected for signing. |
| Reason | Cross-language reproducibility + JSON continuity + auditability; float ambiguity removed by prohibition. |
| Status | **Design-only** |

### H8-DCP-068 — Signature algorithm = Ed25519 initial, ECDSA P-256 (RFC 6979) migration (G2 §10)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | Initial Ed25519 (deterministic, 64-byte, misuse-resistant, no per-signature nonce); documented migration to ECDSA P-256 with RFC 6979 deterministic nonces for FIPS/KMS/HSM; RSA-PSS legacy-interop only. `signature_algorithm` is an explicit signed field; downgrade to an unlisted/weaker algorithm fails closed. **No key created.** |
| Reason | Strongest misuse-resistance for research; NIST-curve path preserved for regulated environments. |
| Status | **Design-only** |

### H8-DCP-069 — Single-purpose key hierarchy with usage binding (G2 §11)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | Offline root/policy → intermediate → single-purpose leaf keys (release-attestation, resolver-report, timestamp, runtime-observer [G3+], capture-authorisation [G9+]); fixture keys namespaced `h8-fixture-*` and excluded from production trust roots. A resolver-report key must not sign runtime-observer or capture evidence (usage binding + `TRUST_KEY_USAGE_INVALID`). |
| Reason | Least privilege; a resolver signature can never authorise runtime or capture. |
| Status | **Design-only** |

### H8-DCP-070 — Key storage: repository-stored private keys REJECTED for all tiers (G2 §12)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | Research-dev = OS keystore / TPM (local encrypted age/sops file **outside the repo** as fallback); production = HSM (PKCS#11) or cloud KMS, with workload-identity keyless signing preferred in CI. **Repository-stored private keys are rejected for research-dev, CI and production.** Fixture keys structurally cannot authorise production evidence. |
| Reason | Private keys must never live in tracked repository content. |
| Status | **Design-only** |

### H8-DCP-071 — Resolver never accepts a caller-selected key; unsigned = preflight-unauthenticated (G2 §13)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | Trust policy (not the caller/report) maps `resolver_id` → permitted `key_id`; the resolver holds no raw private key in production (external KMS/HSM signing); signing failure yields an unsigned/blocked report, never a silent accept; no report field self-declares an authorised key; persisted reports are re-verified (signature+time+revocation) before use. Extends the G1R no-injection principle. |
| Reason | Prevents self-declaration forgery (F-001 class) and caller key substitution. |
| Status | **Design-only** |

### H8-DCP-072 — Trusted time staged; Git/sim time NEVER a freshness proof (G2 §14)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | Separate untrusted wall clock / monotonic ordering clock / Git commit time / sim time / signed TSA time / verification time. Research = local monotonic + explicitly-untrusted time (freshness NOT claimed); CI = transparency-log inclusion time; production = RFC 3161 TSA and/or attested workload clock. `max_report_age`, `allowable_clock_skew`, backward-clock detection, authority-unavailable → deny. **Git commit time and simulator time are never trusted for freshness.** |
| Reason | Freshness requires an external trusted time source; internal clocks are attacker-influenced. |
| Status | **Design-only** |

### H8-DCP-073 — Fail-closed revocation architecture (G2 §15)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | Revocable subjects: signing key, resolver identity, producer identity, repository/release attestation, report id, policy version, dependency manifest, runtime observer, capture token (9). Signed revocation records `{subject_type, subject_id, effective_time, reason_code, supersedes, authority_sig}` distributed as signed bundles with `max_cache_age`; unavailable or stale-beyond-policy status → **deny** (`TRUST_REVOCATION_STATUS_UNAVAILABLE`); emergency channel + supersession + audit. |
| Reason | Compromise must be revocable and unknown revocation state must never fail open. |
| Status | **Design-only** |

### H8-DCP-074 — Repository/release attestation = signed tags + in-toto/SLSA, migrate to Sigstore (G2 §16)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | Initial model: signed Git tags (Ed25519/SSH-sig) marking approved commits/closures + CI-issued in-toto/SLSA provenance binding the release; production migration to Sigstore + Rekor transparency. **Stated limitation:** this proves an authorised release key approved a commit, NOT the physical origin of a given clone (deferred to §17). Remote URL and folder path are each insufficient. |
| Reason | Distinguishes copied history / approved repository / approved release / authorised org source. |
| Status | **Design-only** |

### H8-DCP-075 — Physical/organisational origin assurance ladder (G2 §17, extends H8-DCP-062)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | Content identity ≠ signing ≠ workload ≠ host ≠ network ≠ org ≠ physical-machine identity. A signature alone does NOT prove physical origin. Minimum H8-research claim = *organisationally authorised* (resolver-report key + release attestation both chain to the H8 research trust root, no physical-machine claim); stronger enterprise claim = host TPM/workload attestation bound into the envelope. Copied-history impersonation (`H8-C-041`) is addressed only at *organisationally authorised* and above. |
| Reason | Honest scoping of what a signature can and cannot prove about origin. |
| Status | **Design-only — supersedes the G2-deferral of H8-DCP-062 at the design level** |

### H8-DCP-076 — Curated semantic per-dependency identity commitments (G2 §18, addresses H8-G1RREV-F-002)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | The envelope carries `per_dependency_identity_commitments[]` — a bounded, curated rule per mandatory class (schema-id+digest, policy-id+version+digest, canonical route digest with `coord_offset`/start/goal, scene-id+digests, `CL_BOUND_XY` field+value `6.0`, canonicalisation algo-id+test-vector digest, etc.). Substituting a same-type tracked file changes the semantic commitment → `TRUST_SEMANTIC_IDENTITY_MISMATCH`. This is a curated control; it does **not** claim whole-program semantic discovery of unknown future dependencies. |
| Reason | Narrow, honest correction of F-002 without over-claiming semantic completeness. |
| Status | **Design-only — F-002 remains a documented residual until implemented + reviewed** |

### H8-DCP-077 — `.gitattributes`/filter binding via raw-blob + attributes-closure digest (G2 §19, addresses H8-C-040)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | Signed payload commits to **raw Git blob bytes** per dependency (independent of clean/smudge filters) plus a digest of the effective `.gitattributes` closure and filter/EOL/encoding/LFS policy; any attribute/filter change invalidates the report (`TRUST_ATTRIBUTES_POLICY_MISMATCH`). Representation distinction fixed: Git identity = raw blob bytes, semantic identity = canonical parsed content, worktree identity = diagnostic only. LFS materialised-object verification remains a documented limitation. |
| Reason | Committed local `.gitattributes`/filters (the H8-C-040 residual) must be bound, not just system/global neutralised. |
| Status | **Design-only** |

### H8-DCP-078 — Anti-replay: report_id + nonce + repo/HEAD/instance binding + consumption registry (G2 §20)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | Unique `report_id` + `nonce` + `intended_use` (e.g. `preflight-document`) + repository/HEAD/instance binding + validity window + append-only consumption registry for one-time reports + revocation lookup at verification. **A resolver report authorises preflight verification, not capture.** |
| Reason | Prevents reuse of old/valid/revoked/cross-repo/cross-instance reports. |
| Status | **Design-only** |

### H8-DCP-079 — Transparency/audit: append-only journal (research) → transparency log (production) (G2 §21)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | Research = append-only local journal (+ optional research-only evidence dir); production = transparency log with inclusion proofs; define append semantics, retention, privacy, conflict handling; split-view/equivocation noted as a threat. No ledger implemented this gate. |
| Reason | Independent auditability without introducing an operational ledger now. |
| Status | **Design-only** |

### H8-DCP-080 — Independent verifier holds only public roots, unknown exception → deny (G2 §22)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | `verify_resolver_envelope(...)` is distinct from the signer, holds only public trust roots (no signing key), returns structured dimensions, is version-pinned, and treats any unknown exception as **deny**. |
| Reason | Separation of duties + fail-closed verification. |
| Status | **Design-only** |

### H8-DCP-081 — Architecture: Option A (TPM/OS, research) → Option C (keyless workload identity, production) (G2 §26)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | Evaluated A (local detached/TPM), B (remote signing service), C (workload identity + transparency-backed keyless, e.g. Sigstore Fulcio+Rekor). Selected research-dev = A; future production = C; migration A→C via the versioned envelope + pluggable key-policy so verifiers accept both trust roots during transition. |
| Reason | Simplest validatable design now; keyless transparent signing for production later. |
| Status | **Design-only** |

### H8-DCP-082 — Versioned envelope, no "accept unknown version" fallback (G2 §30)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | Envelope/algorithm/key/trust-root/policy versioning with a bounded verifier backward-compat window, archived-roots verification of historical reports, fixture↔production separation, emergency algorithm disablement; deprecated schema rejected; **no accept-unknown-version fallback.** |
| Reason | Safe evolution without silent acceptance of unrecognised formats. |
| Status | **Design-only** |

### H8-DCP-083 — Privacy/data-minimisation in signed reports (G2 §31)

| Field | Content |
| --- | --- |
| Date | 2026-07-16 |
| Decision | Signed/shared reports exclude absolute paths, usernames, hostnames, internal addresses, secret ids, private URLs and raw environment variables; use stable pseudonymous policy ids. Signing does not make unnecessary personal/infrastructure data safe to disclose. Consistent with the deterministic `closure_digest` already excluding host paths. |
| Reason | Signing must not become a channel for leaking infrastructure/personal data. |
| Status | **Design-only** |

## G2A — Canonical Trust-Envelope Schema & Fixture-Only Test-Vector Gate — decisions (2026-07-17)

**Schema + canonicalisation + fixture-test gate**, implementing the committed governing spec
`docs/research/H8_G2A_CANONICAL_ENVELOPE_SPEC.md` (`23d95c8`). No production key/certificate/signature/token/
trusted timestamp/revocation record; no signing/verification/KMS/TSA/CA/transparency/revocation service; no
observer/Isaac/ROS 2/capture. `scripts/gnm/h8_trust_envelope.py` (+ `configs/gnm/h8_trust_envelope_
schema.json`), tests `tests/gnm/test_h8_trust_envelope.py` (146 pass). Schema conformance is NOT trust
acceptance. Implementation report: `docs/research/H8_G2A_CANONICAL_TRUST_ENVELOPE.md`.

### H8-DCP-084 — Implement the committed spec's `payload`+`signature_block` envelope

| Field | Content |
| --- | --- |
| Date | 2026-07-17 |
| Decision | The envelope has exactly two top-level members: `payload` (the signed content) and `signature_block` (detached, NOT signed). Canonical bytes cover `payload` only. Implemented exactly to `H8_G2A_CANONICAL_ENVELOPE_SPEC.md` §3 (committed `23d95c8`); the spec is authoritative and this module conforms. |
| Reason | Single source of truth: an implementation must match its governing committed spec. |
| Status | **Implemented (schema-only)** |

### H8-DCP-085 — Unicode NFC by NORMALISATION during canonicalisation (spec §4.3)

| Field | Content |
| --- | --- |
| Date | 2026-07-17 |
| Decision | The canonicaliser NFC-normalises every object key and string value, so an NFD input yields the same canonical bytes/digest as its NFC twin (spec §7 vector 4). This realises the spec's "NFC normalisation" wording and supersedes an earlier implementation draft that rejected non-NFC input. |
| Reason | Conform to the committed spec's determinism requirement (NFD ≡ NFC digest). |
| Status | **Implemented (schema-only)** |

### H8-DCP-086 — JCS (RFC 8785) with the standard library only; floats prohibited

| Field | Content |
| --- | --- |
| Date | 2026-07-17 |
| Decision | Canonicalisation is pure Python standard library (no third-party canonicaliser): UTF-8, UTF-16-code-unit key sort, minimal escaping, `/` unescaped, integers shortest-decimal. Floats/`NaN`/`±Infinity` are rejected at parse (`TRUST_ENVELOPE_SCHEMA_INVALID`) and in canonicalisation (`TRUST_CANONICALISATION_FAILED`). Realises architecture `H8-DCP-067`. |
| Reason | Minimise dependency/trust surface; remove float canonicalisation ambiguity. |
| Status | **Implemented (schema-only)** |

### H8-DCP-087 — Line-ending rule = reject carriage return in string values (spec §7 v5)

| Field | Content |
| --- | --- |
| Date | 2026-07-17 |
| Decision | The fixed line-ending rule is REJECT: any string value containing `\r` (CR/CRLF) → `TRUST_ENVELOPE_SCHEMA_INVALID`; LF-only in canonical strings. |
| Reason | A single deterministic, testable rule for the spec's line-ending edge case. |
| Status | **Implemented (schema-only)** |

### H8-DCP-088 — Timestamps: RFC 3339 UTC 'Z', no sub-second, interval-ordered, never freshness

| Field | Content |
| --- | --- |
| Date | 2026-07-17 |
| Decision | One representation only: `YYYY-MM-DDThh:mm:ssZ` (no offset, **no sub-second**), calendar-range checked, with `validity_start <= issue_time <= expiry` and `validity_start < expiry`. `observation_time`/`issue_time`/`validity_start`/`expiry` are syntax-validated but never consulted for freshness (trusted time = G2C); the spec marks the clock UNTRUSTED. |
| Reason | Deterministic time syntax without over-claiming trusted freshness (spec §6). |
| Status | **Implemented (schema-only)** |

### H8-DCP-089 — Absent / null / UNAVAILABLE tri-state; signature_block all-UNAVAILABLE, no fabricated signature

| Field | Content |
| --- | --- |
| Date | 2026-07-17 |
| Decision | Three distinct states (spec §5): optional members absent (not in canonical bytes); `reference_input` may be `null` (present, digest differs from absent); deferred fields (`signing_key_id`, `observed_remote_origins`, `trusted_timestamp_reference`, `revocation_snapshot_reference`, `origin_attestation_reference`) use the explicit `"UNAVAILABLE"` sentinel. `signature_block` has every member = `"UNAVAILABLE"`; `signature_algorithm` is DECLARED (`ed25519`, allow-list; downgrade → reject) but NO signature exists. Deferred values are never fabricated. |
| Reason | Carry the signed-envelope SHAPE with zero capability to sign, and keep absent/null/UNAVAILABLE unambiguous. |
| Status | **Implemented (schema-only)** |

### H8-DCP-090 — `verification_requirements` are non-waivable

| Field | Content |
| --- | --- |
| Date | 2026-07-17 |
| Decision | The 8 `verification_requirements` booleans (`require_signature`, `require_authorised_signer`, `require_trusted_timestamp`, `require_not_revoked`, `require_repository_attestation`, `require_semantic_identity`, `require_attributes_binding`, `require_intended_use_match`) must all be present and `true`; any `false` (or unknown key) → `TRUST_ENVELOPE_SCHEMA_INVALID`. A report cannot waive its own future checks (spec §3.4). |
| Reason | Prevent a forged report from disabling the checks a future verifier (G2H) must run. |
| Status | **Implemented (schema-only)** |

### H8-DCP-091 — `intended_use` const `preflight-document`; assurance exactly `["content-equivalent"]`

| Field | Content |
| --- | --- |
| Date | 2026-07-17 |
| Decision | `intended_use` must equal `preflight-document` (never runtime/capture); `assurance_claims` must equal exactly `["content-equivalent"]`. Anything else → `TRUST_ENVELOPE_SCHEMA_INVALID`. |
| Reason | An envelope cannot self-escalate its use or assurance beyond what G2A establishes (spec §3.1). |
| Status | **Implemented (schema-only)** |

### H8-DCP-092 — Two owned failure codes; taxonomy isolated; non-authenticating digest; non-authorising result

| Field | Content |
| --- | --- |
| Date | 2026-07-17 |
| Decision | G2A owns/emits exactly `TRUST_ENVELOPE_SCHEMA_INVALID` (all structural/schema failures) and `TRUST_CANONICALISATION_FAILED` (canonicalisation-stage failures) (spec §8). These live in `h8_trust_envelope.py` and are **disjoint** from the resolver's `REASON_CODES` (unchanged at **41**). `compute_digest` is a NON-AUTHENTICATING `sha256:<hex>`. `evaluate_envelope` always reports `signature_verified/signer_authorised/timestamp_verified/fresh/repository_attested/release_approved/semantic_identity_verified/attributes_binding_verified/preflight_eligible/runtime_eligible/capture_eligible` at their fail-closed values; the module exposes no `sign`/`verify_signature`/`authorise`. |
| Reason | Schema validity must never read as trust acceptance; the resolver's active taxonomy must not grow. |
| Status | **Implemented (schema-only)** |

### H8-DCP-093 — Exact-version binding, unknown-field rejection, critical-extension fail-closed, bounds

| Field | Content |
| --- | --- |
| Date | 2026-07-17 |
| Decision | `envelope_version` must exactly match `h8-trust-envelope/1.0.0` (no accept-unknown-version); unknown top-level or `payload` members are rejected; any `critical_extensions` entry (absent from `extensions`, or present but not understood — none are understood at G2A) fails closed; string length (≤512) and array size (≤4096) bounds enforced. |
| Reason | Controlled, signed-over extensibility with no silent acceptance of unknown formats or critical semantics. |
| Status | **Implemented (schema-only)** |
