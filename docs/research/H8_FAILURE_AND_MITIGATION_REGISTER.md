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
| Remediation-gate re-check (2026-07-16) | Ruff is **declared** in `pyproject.toml` (`[tool.ruff]`: `line-length=100`, `select=["E","F","I","W"]`, `ignore=["E501"]`; dev-dep `ruff>=0.4`) but is **not installed** in the base or `.venv` environments, and the `Makefile` has **no lint target**. Per the narrow-gate rule, no uncontrolled install was performed. **Status stays Open** (`OPEN — RUFF UNAVAILABLE`). Canonical `ruff check` (from a `pip install -e '.[dev]'` environment) is required before capture promotion — see `H8-DCP-016`. `py_compile` passed and is recorded separately; it is **not** a lint substitute. |

> "Ruff unavailable" is explicitly **not** converted into "lint passed."

### H8-C-007 — Dry-run evidence commit provenance mismatch (raised, audited, resolved)

| Field | Content |
| --- | --- |
| Stage | Audit (documentation provenance) |
| Expected | Documentation identifies the exact commit containing the generated 25/25 dry-run evidence, distinct from the emitter commit. |
| Observed | A cross-report review questioned whether Level 1 was correctly attributed to `66fd81e`, since a prior readiness-analysis report described the state at `66fd81e` as "analysis-only" and associated the emitter with `ecae4cd`. The committed gate record's prose already labelled `ecae4cd` as *emitter* and `66fd81e` as *evidence (25/25)*, but it lacked an explicit canonical provenance table separating the two. |
| Detection method | Cross-report consistency review + read-only Git audit (`git show --name-status`, `git log --diff-filter=A`, `git log -S`, `git merge-base --is-ancestor`). |
| Impact | Reproducibility/provenance clarity: without an explicit table a reviewer could inspect the wrong repository state. No technical/capture-path impact. |
| Root cause | The emitter (`ecae4cd`, harness+tests, contains a `"25/25"` **test assertion**) and the generated evidence (`66fd81e`, the five files, contains the generated `"checks_passed": "25/25"` **result**) are distinct commits that both mention the `25/25` token; the documentation did not tabulate that distinction, and a separate readiness-analysis *activity* (uncommitted, HEAD at `66fd81e`) was phrased as "analysis-only". |
| Corrective action | Added a **canonical provenance table** (full hashes) to the gate record; added `H8-DCP-013`; recorded this reconciliation. **No commit hash in the documentation was found to be wrong; no hash was changed.** |
| Verification | `git log --diff-filter=A -- <dryrun dir>` → all five files first added in `66fd81e`; `git log -S'"checks_passed": "25/25"'` → only `66fd81e`; `ecae4cd` `-S'25/25'` hit = test assertion; timestamps `ecae4cd` 04:41:53 < `66fd81e` 04:46:11; `git log 66fd81e..bd6168a` → only `bd6168a` (no readiness-analysis commit). |
| Regression protection | Canonical provenance table with full hashes in the gate record; `H8-DCP-013` mandates distinct baseline/emitter/evidence hashes. |
| Residual risk | None for this attribution. Verdict: **A — `66fd81e` is correct.** |
| Status | **Closed** (Verdict A; documentation hardened; no hash correction was required) |

### H8-REV-F-003 — Empty-plan direct-call `IndexError` (raised in remediation, RESOLVED in the schema gate)

| Field | Content |
| --- | --- |
| Stage | Schema-design gate (§21 optional hardening) |
| Expected | A direct `dataset_dry_run_checks` call on a no-instance config rejects gracefully, matching `validate_dataset_capture_config`. |
| Observed (before) | It raised `IndexError` (empty plan → `_cross_split_pair([])` → `recs[0]`); both real boundaries already failed closed (CLI rc 2, validator `ok=False`), so it was a robustness/consistency gap, not a safety hole. |
| Root cause | No empty-plan guard before the leakage-injection cases. |
| Corrective action | Narrow guards in `dataset_dry_run_checks` (return `all_pass=False` + `empty_plan=True`, no raise) and `write_dataset_dry_run_artifacts` (refuse to emit) — see `H8-DCP-022`. Fires only on the empty-plan path. |
| Verification | `test_29_empty_plan_graceful_and_fail_closed`; CLI empty-plan run returns 2 and creates nothing; recorded-mode suite 58/58; Level-1 evidence byte-identical; valid-config dry-run still 25/25. |
| Residual risk | None identified. |
| Status | **Resolved** |

## Schema-design-gate challenges (H8 Render/Drive Evidence Schema, 2026-07-16)

### H8-C-008 — Freshness cannot be *proven* without a trusted clock

- Risk: the schema defines validity windows and `max_age_seconds`, but a real deployment needs a trusted time source; a schema-valid fixture does not prove real freshness.
- Mitigation: time is checked against an **injected** `review_time` (deterministic, test-scoped); `clock_source`/`clock_skew_seconds` are declared; the boundary statement records that a trusted clock is NOT established.
- Verification: `_parse_ts` + step-9 checks; tests 9, 10, 12, 20; `H8-DCP-019`.
- Status: **Open / Accepted for this gate** (trusted clock deferred to provider/runtime gates).

### H8-C-009 — Signature and key management are deferred

- Risk: integrity digests detect tampering but not forgery of producer identity without signatures.
- Mitigation: schema carries `signature`/`signature_algorithm`/`key_id`/`verification_status`; a caller may `require_signature`; unsigned fixtures are clearly `unsigned` and rejected in production mode. No real signing/verification is implemented.
- Verification: step-8 + `require_signature`; `test_extra_signature_required_but_unverified_rejected`; `H8-DCP-020`.
- Status: **Open blocker** (real key management owned by the provider gate; overlaps `H8-C-005`).

### H8-C-010 — Legitimate scene-evidence reuse is intentionally undesigned

- Risk: some render evidence may legitimately apply to several instances of the same scene; the current pairing policy forbids cross-instance reuse entirely, which may be stricter than necessary.
- Mitigation: default to the safe direction (no reuse) and flag any reuse policy as requiring a separate independent review.
- Verification: `validate_pair` shared-binding equality; `H8-DCP-021`.
- Status: **Open / Accepted** (deliberately conservative; reuse policy is future reviewed work).

### H8-C-011 — Digest truthfulness depends on a real producer

- Risk: the validator trusts the `scene_digest`/`route_plan_digest`/`config_digest` values as supplied; it verifies internal consistency, not that they reflect the real scene/route/config.
- Mitigation: documented as a schema-level limitation; a real provider must compute digests over real artefacts (runtime/provider gate).
- Verification: boundary statement; `H8-DCP-018`; `H8-C-005`.
- Status: **Open blocker** (provider gate).

### H8-C-012 — Schema-version compatibility / migration is unspecified

- Risk: only `h8-evidence/1.0.0` is supported; a future revision needs an explicit migration/compat policy to avoid silent downgrade.
- Mitigation: strict supported-set membership (`SUPPORTED_SCHEMA_VERSIONS`) fails closed on any other version now; a migration policy is a named future item.
- Verification: test 11; `H8-DCP-017`.
- Status: **Open / Accepted** (single-version by design this gate).

### H8-C-013 — Ruff re-check for the schema gate

| Field | Content |
| --- | --- |
| Expected | Run the canonical Ruff lint on the changed Python files (`h8_evidence_schema.py`, harness edit, tests). |
| Observed | `python -m ruff` remains unavailable in base and `.venv`; the `Makefile` still has no lint target (unchanged from `H8-C-006`). |
| Containment | No uncontrolled install performed; **no claim of Ruff success**. `python -m py_compile` passed on all three changed Python files (recorded separately; not a lint substitute). |
| Status | **Open — Ruff unavailable** (see `H8-C-006`, `H8-DCP-016`; canonical `ruff check` required before capture promotion). |
| Provider-gate re-check (2026-07-16) | Ruff re-checked again during the evidence-provider gate: `python -m ruff` still absent in base and `.venv`; `Makefile` still has no lint target. `H8-C-013` **continues** `H8-C-006` (same underlying limitation, re-observed per gate) — it does **not** replace it. Chain preserved: `H8-C-006 → H8-C-013 → provider-gate re-check`. `py_compile` passed on the provider, schema and test files (recorded separately; not a lint substitute). Status stays **Open**. |

## Evidence-provider-gate challenges (H8 Non-Capturing Evidence Provider, 2026-07-16)

### H8-C-014 — A scene-file digest is not a runtime-loaded-scene digest

- Risk: binding to the committed `.usda` file digest could be mistaken for proof that Isaac loaded that scene correctly.
- Mitigation: the provider computes only a **scene-file** digest and records `scene_loaded=false`, `runtime_observed=false`; the design doc lists loaded-scene identity as unobserved.
- Verification: preflight payload; tests 04, 23; `H8-DCP-025`.
- Status: **Open / Accepted** (runtime-loaded-scene digest owned by the runtime gate).

### H8-C-015 — `coordinate_frame` is provider-declared, not read from config

- Risk: the config declares no coordinate frame; the provider declares `synthetic_fork_world`, which is an assumption rather than an observed artefact fact.
- Mitigation: documented explicitly; the same declared frame is bound consistently into subject + route and checked on validation.
- Verification: `COORDINATE_FRAME`; design doc §6.
- Status: **Open / Accepted** (a config-declared frame would remove the assumption in a future revision).

### H8-C-016 — The route representation is config-derived structure, not a runtime-executed route

- Risk: the route-plan digest binds a structural representation (start/goal/waypoints from `coord_offset`), not a driven route; drive feasibility/clearance are unobserved.
- Mitigation: `degraded=true`, `runtime_observed=false`, `unobserved_runtime_checks` list; design doc §8.
- Verification: preflight drive payload; tests 03, 24; `H8-DCP-025`.
- Status: **Open / Accepted** (runtime drive validity owned by the runtime gate).

### H8-C-017 — Local clock is untrusted (observational only)

- Risk: preflight timestamps come from an injected/local clock with no trusted time source.
- Mitigation: clock is injected; time recorded as observational; no trusted-clock guarantee claimed; a `PROVIDER_CLOCK_UNTRUSTED` code is reserved.
- Verification: `H8-DCP-028`; design doc §9; overlaps `H8-C-008`.
- Status: **Open blocker** (trusted clock owned by the runtime/provider-review gates).

### H8-C-018 — Replay/conflict protection is process/sink-local

- Risk: duplicate/replayed evidence is detected only within one process/sink, not across distributed producers.
- Mitigation: deterministic ids + sink conflict map + `seen_ids`; no distributed guarantee is claimed.
- Verification: tests 29, 30, 31; `H8-DCP-027`.
- Status: **Open / Accepted** (distributed replay protection needs a shared registry).

### H8-C-019 — Camera resolution/encoding are declared intent, not observed

- Risk: the render payload carries `resolution`/`encoding` that are provider-declared, not read from a verified camera configuration.
- Mitigation: marked `resolution_encoding_declared_not_observed=true` and `camera_config_declared_not_verified=true` in `preflight_observations`; `runtime_observed=false`.
- Verification: render preflight payload; test 23.
- Status: **Open / Accepted** (verified camera config owned by the runtime gate).

### H8-P-001 — Evidence-ID regex mismatch (implementation refinement, resolved)

| Field | Content |
| --- | --- |
| Stage | Provider implementation |
| Observed | The first `emit_evidence` returned `PROVIDER_SCHEMA_REJECTED`: the evidence id embedded the full `evidence_type` (`render_valid`), whose underscore fails the schema id pattern `^h8ev-[a-z]+-…$`. |
| Root cause | Used `evidence_type` verbatim in the id "type" segment. |
| Corrective action | Use the short type slug (`render`/`drive`) in the id. |
| Verification | `_evidence_id`; provider suite 41/41; smoke test produced `h8ev-render-sfork00-3234` / `h8ev-drive-sfork00-5487`. |
| Status | **Resolved** |

## Provider independent-review findings — dispositions (trust-boundary remediation, 2026-07-16)

Findings raised by the independent review (`docs/research/H8_EVIDENCE_PROVIDER_INDEPENDENT_REVIEW.md`) and
their remediation-gate dispositions (`docs/research/H8_EVIDENCE_PROVIDER_REMEDIATION.md`). Original findings
are preserved in the review report; nothing is erased.

| Finding | Severity | Root cause | Disposition | Control (decision) |
| --- | --- | --- | --- | --- |
| `H8-PREV-F-001` | High | production trust = absence of a single fixture marker | **CLOSED** | positive producer-trust (deny-by-default) + 10-signal defence-in-depth (`H8-DCP-029/030/031`) |
| `H8-PREV-F-002` | Medium | runtime observer was a truthiness check | **CLOSED** | typed observer capability contract (`H8-DCP-032`) |
| `H8-PREV-F-003` | Medium | dirty-tree check opt-in when `tree_state` absent | **CLOSED** | mandatory fail-closed dirty-tree (`H8-DCP-033`) |
| `H8-PREV-F-004` | Low | 4 unused/unreachable reason codes | **CLOSED (1 reserved)** | 3 wired+tested; `PROVIDER_MODE_INVALID` reserved (`H8-DCP-034`) |
| `H8-PREV-F-005` | Low | docs overstated fixture-detection depth | **CLOSED** | implementation-doc §11 corrected to positive-trust wording |

Reproduction before fix, corrective controls, adversarial tests, and verification (165 tests, dry-run
25/25, Level-1 5/5) are recorded in the remediation report. Overall remediation verdict:
**`PASS WITH DOCUMENTED LIMITATIONS`** — all findings CLOSED; a focused independent re-review is required
before the backend gate. Real capture remains blocked; Levels 3–5 unproven. Ruff remains Open
(`H8-C-006`/`H8-C-013`).

## Provider trust-boundary independent re-review (dae2bee, 2026-07-16)

Independent re-review (`docs/research/H8_EVIDENCE_PROVIDER_TRUST_BOUNDARY_REREVIEW.md`) verified all five
`H8-PREV-F-*` findings **INDEPENDENTLY VERIFIED CLOSED** (F-001 reproduced pre-`97781ad`/rejected-post;
23/23 fixture-laundering rejection; positive allow-list proven usable; observer 11/11 and dirty-tree 7/7
fail-closed; 223 H8 tests, dry-run 25/25, Level-1 5/5). Overall **`PASS WITH DOCUMENTED LIMITATIONS`**;
**ELIGIBLE FOR BACKEND/RUNTIME DESIGN GATE**. New LOW/informational re-review findings:

| ID | Severity | Summary | Owner |
|---|---|---|---|
| `H8-PRREV-F-001` | Low (info) | producer *software* version not a modelled trust control (schema-version IS gated) | design note |
| `H8-PRREV-F-002` | Low (info) | no concrete git dirty-tree resolver exists — provider trusts an injected `dependency_dirty` bool | **backend gate G1** |
| `H8-PRREV-F-003` | Info | provider `MODE_PRODUCTION` returns at the observer gate before the schema positive-trust path (stricter, not a defect) | design note |

## H8 Isaac Backend & Runtime-Validity Architecture Design Gate — open challenges (2026-07-16)

Design-only (`docs/research/H8_ISAAC_BACKEND_RUNTIME_ARCHITECTURE.md`). These are design targets, **not
implemented controls**; each has an owning future gate (G1–G13).

| ID | Challenge | Owner gate |
|---|---|---|
| `H8-C-020` | Concrete Git dependency resolver not implemented (discharges `H8-PRREV-F-002`) | G1 |
| `H8-C-021` | Isaac APIs / version compatibility untested | G4/G5 |
| `H8-C-022` | Simulator startup time & stability unknown | G5 |
| `H8-C-023` | Runtime scene-content identity unresolved for proprietary/generated assets | G6 |
| `H8-C-024` | Camera validity thresholds unresolved | G6 |
| `H8-C-025` | Route clearance thresholds unresolved | G7 |
| `H8-C-026` | Trusted clock unavailable | G2 |
| `H8-C-027` | Key management unavailable | G2 |
| `H8-C-028` | Revocation service unavailable | G2 |
| `H8-C-029` | Runtime observer unavailable | G3/G6/G7 |
| `H8-C-030` | Capture-authorisation token infrastructure unavailable | G10 |
| `H8-C-031` | Output-transaction implementation unavailable | G9 |
| `H8-C-032` | No Level-3 runtime evidence exists | G6–G8 |

Design-gate verdict: **`PASS WITH DOCUMENTED LIMITATIONS`**. Selected architecture = isolated Isaac worker
(Option B, `H8-DCP-035`); first runtime worker owns **no** dataset writer (`H8-DCP-036`). **First
implementation gate = G1 (Git resolver), not the Isaac backend.** Real capture remains blocked; Levels 3–5
unproven; Ruff Open (`H8-C-006`/`H8-C-013`).

## G1 — H8 Git Dependency Resolver Implementation Gate — challenges (2026-07-16)

Implemented `scripts/gnm/h8_git_dependency_resolver.py` (discharges `H8-PRREV-F-002`). 56 tests pass
(real temp Git repos + FakeGit); 31/31 active reason codes triggered; provider integration fail-closed with
zero backend/output on blocked cases. Residual challenges (documented, not overclaimed):

| ID | Challenge | Owner |
|---|---|---|
| `H8-C-033` | Symlink time-of-check/time-of-use races cannot be fully prevented by static inspection | G1-review / runtime |
| `H8-C-034` | Time-based report freshness needs the not-yet-built trusted clock (`REPORT_STALE` reserved) | G2 |
| `H8-C-035` | Manifest completeness is the author's responsibility; the resolver proves only the declared closure | G1-review |
| `H8-C-036` | git-lfs is not installed here — LFS materialisation is unverifiable, so it fails closed | G2/env |
| `H8-C-037` | git-version behaviour variance (rename detection, porcelain nuances) — bounded by tests on git 2.34.1 | G1-review |
| `H8-C-038` | Detached-HEAD/linked-worktree acceptance policy is minimal; hardened rules deferred | G1-review |
| `H8-C-039` | In-process report authenticity is not cryptographic — code with module access can copy the marker constant; the durable control is that protected callers use the trusted factory and never accept a caller report. Full authentication → G2 | G1R (F-001) |
| `H8-C-040` | Git-config neutralisation covers the ENUMERATED surfaces (fileMode/symlinks/ignorecase/autocrlf/replace-objects/alternates); it is not an exhaustive proof that no Git configuration or filter can influence any observation | G1R (F-003) |
| `H8-C-041` | Copied-history spoofing (identical root commit + history in a physical copy) is NOT closed by Git inspection and MUST NOT be closed via remote-URL comparison; cryptographic origin attestation → G2 | G1R (F-004) |

Verdict: **`PASS WITH DOCUMENTED LIMITATIONS`**. Establishes resolver + closure + repository-identity
binding + fail-closed provider preflight integration + deterministic closure digest. Does NOT establish
Level-3 runtime validity, trusted time, signatures, revocation, dataset or model validity, or capture
authorisation. Recommend an **independent G1 review** before G2/G3. Real capture blocked; Levels 3–5
unproven; Ruff Open.
