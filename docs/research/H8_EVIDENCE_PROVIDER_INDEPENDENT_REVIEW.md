# H8 Non-Capturing Evidence Provider — Independent Adversarial Review

**Gate type:** adversarial, falsification-oriented **review only**. No implementation, schema, test,
config or evidence change was made to the reviewed artefacts. No Isaac, ROS 2, camera, robot, render,
drive, capture, inference or training. The verdict is reconstructed from code, Git history, independent
recomputation and reproducible adversarial probes — **not** from the implementation report.

- **Date:** 2026-07-16 · **Branch:** `h23-execfix` (local, unpushed) · **HEAD reviewed:** `97781ad`.
- **Primary commit under review:** `97781adadf4e708d7e6e03914e79724916f28864` ("Implement H8 non-capturing
  evidence provider").
- **Method note:** import/runtime-boundary results below combine **static** token scanning and a
  **runtime** `sys.modules` check; this is not a full transitive dependency-tree proof (stated as a
  limitation, §21).

## 1. Milestone chain & verified roles

| Commit | Role (from Git) |
|---|---|
| `7a73c9fc012b97ee1bf94fe829a3c59eb915ff9f` | dataset capture **config** |
| `ecae4cdd5de4082184fc65881cc836c612231bf8` | dry-run **emitter** |
| `66fd81e62bc0d6c100e7b562b22fc8cc8a0d061e` | dry-run **evidence** (25/25) |
| `bd6168ab5ead2aa5724a6d9df1b7e52222fbf0b7` | capture-path **wiring** |
| `db70ce39c0d99300ec4f4d2c0010f6cbe036cade` | capture-path **documentation** |
| `bb94c5aabe6d96bbe8e4be4ce6f3d7a0a37af4ce` | provenance **reconciliation** |
| `c6b42ac14eb52f80e3b0a3521d3eb3a826ac1627` | independent capture-path **review** |
| `31b1d01086524d13c08630a733fce81f84a1a428` | **bounded review-finding remediation** (6 files, +257/−5) |
| `ebf8341fff03b0af9a63fc41705c3f2ce622ed7a` | evidence **schema** |
| `97781adadf4e708d7e6e03914e79724916f28864` | evidence **provider** (this review's subject) |

HEAD = `97781ad`; all prior commits unchanged; branch local/unpushed/untagged; no unrelated working-tree
modification was incorporated into this review (the only dirty files are pre-existing unrelated scripts).

## 2. Provider symbols reviewed (§3)

`H8EvidenceProvider` (modes `fixture`/`preflight`/`production`), `load_configuration`, `load_plan`,
`resolve_instance`, `build_route_representation`, `build_subject_binding`, `build_provenance`,
`_evidence_id`, `_seal`, `_envelope_skeleton`, `build_render_preflight_evidence`,
`build_drive_preflight_evidence`, `_preflight_prechecks`, `emit_evidence`, `_emit_fixture`;
module helpers `default_reader`, `default_digest`, `InMemorySink`, `AtomicFileSink`,
`preflight_satisfies_capture_gate`, `_plus_days`; schema extension `validate_envelope(..., document_only)`
and `validate_pair(..., document_only)`. Implementation matches its documentation except where noted in
findings F-004/F-005.

## 3. Real dependency graph (§4) — independently digest-recomputed

| Evidence field | Source artefact | Path | Tracked | Canonicalisation | Digest | Kind |
|---|---|---|---|---|---|---|
| `subject.config_digest` | dataset config | `configs/gnm/h8_synthetic_fork_recorded_mode_dataset.yaml` | yes | raw bytes | sha256 | preflight |
| `provenance.plan_digest` | derived plan `build_dataset_plan(cfg)` | (from config) | yes | canonical JSON | sha256 | preflight |
| `subject.scene_digest` | scene `.usda` (33 827 B) | `assets/scenes/synthetic_diagnostic_fork/synthetic_diagnostic_fork.usda` | yes | raw bytes | sha256 | **scene-file** |
| `subject.route_plan_digest` | config-derived route rep | (from config `coord_offset`) | yes | canonical JSON | sha256 | **structural** |
| `subject.instance_id`/`split` | instance def | config `instance_plan` | yes | — | — | preflight |
| `subject.cl_bound_xy` | config `cl_bound_xy` | config | yes | — | — | preflight |
| `subject.coordinate_frame` | **provider-declared** `synthetic_fork_world` | — | n/a | — | — | preflight (`H8-C-015`) |
| `provenance.source_commit`/`producer_version`/`schema_version` | provenance | — | — | — | — | preflight |

**Independent recomputation (§5 of the probe):** `config_digest`, `scene_digest` and `plan_digest`
produced by the provider each **matched** a from-scratch `hashlib.sha256` recomputation (identical values).
No digest is a hard-coded constant, a dry-run-report copy, a fixture, an untracked file, or an
absolute-path artefact.

## 4. Canonicalisation & digest audit (§5/§6)

| Adversarial case | Required behaviour | Observed |
|---|---|---|
| Reordered JSON keys | digest preserved | ✅ preserved |
| `6` vs `6.0` | digest changes (int≠float in JSON) | ✅ changes |
| Extra unknown field | digest changes | ✅ changes |
| Changed `coord_offset` | route digest changes | ✅ changes |
| Config semantic change | config digest changes | ✅ changes |
| Scene content change (same path) | scene digest changes | ✅ changes |
| Absolute machine path in subject/provenance | absent | ✅ none present |
| Digest format | full 64-hex lowercase, `sha256:` | ✅ conforms |

Determinism holds; semantic changes propagate; no machine-specific path enters canonical identity.
**No canonicalisation finding.**

## 5. Evidence-ID / `H8-P-001` review (§7)

`H8-P-001` (short-slug fix) is correctly applied: ids are `h8ev-<render|drive>-<slug>-<seq>` and match
the schema regex (`render_valid` no longer leaks into the id). Render vs drive ids differ for one instance;
regeneration from identical inputs is idempotent; **the same id with changed content is rejected**
(`PROVIDER_OUTPUT_CONFLICT`); duplicate id in a bundle is rejected (`DUPLICATE_EVIDENCE_ID`). **No same-id
different-content acceptance.** `seq` is deterministic (digest-derived); collision resistance is
process-local only (`H8-C-018`, already documented). **No high-severity ID finding.**

## 6. `coord_offset` guard review (§8)

`coord_offset` originates in the config `instance_plan`; it is included in the canonical route
representation, so a changed offset changes the route digest (✅). Missing offset fails closed
(`PROVIDER_ARTIFACT_MISSING`). The guard binds the offset into route identity (not mere presence). Note:
the offset is a **namespacing** device, not a physical pose (already documented `H8-C-016`); the review
confirms the digest binds the representation faithfully. **No finding** beyond the documented structural
limitation.

## 7. `document_only` boundary review (§9) — capture table

| Render input | Drive input | Required | Observed |
|---|---|---|---|
| `document_only`/preflight | `document_only`/preflight | Block | ✅ `STATUS_NOT_VALID` |
| preflight render | runtime-`valid` (fixture) drive | Block | ✅ blocked on render |
| runtime-`valid` (fixture) render | preflight drive | Block | ✅ blocked on drive |
| `indeterminate` | `indeterminate` | Block | ✅ |
| missing | `document_only` | Block | ✅ `PAIR_INCOMPLETE` |
| `document_only` | missing | Block | ✅ `PAIR_INCOMPLETE` |
| fixture `valid` | fixture `valid` (production) | Block | ✅ `FIXTURE_IN_PRODUCTION` (unmodified fixture) |

Additional invariants verified: the provider has **no code path that sets `status="valid"`** (grep-proven);
a `document_only` envelope passed to the capture gate (`document_only=False`) is rejected
(`STATUS_NOT_VALID`); a schema **downgrade** is rejected even under `document_only`
(`SCHEMA_VERSION_UNSUPPORTED`). **The `document_only` mode cannot be used as an alternate path around the
render+drive runtime pair.** **PASS** for this axis.

## 8. Preflight→capture call-path & backend audit (§10)

`preflight_satisfies_capture_gate` returns `(authorises_capture=False, {is_valid_document:True})`.
A spy runtime observer injected into a preflight run was **never invoked** (call count = 0) and the output
remained `indeterminate`. The capture harness (`h8_synthetic_fork_recorded_mode.py`) does **not** import the
new schema/provider and still uses the old 4-field evidence gate, so provider output cannot bypass the
capture gate. **No backend call occurs.** **PASS.**

## 9. Findings

### H8-PREV-F-001 — Fixture/production separation depends on a single sentinel — **HIGH**

- **Reviewed requirement:** (§1.4) fixture evidence cannot enter production mode.
- **Expected:** a synthetic fixture is rejected in production regardless of which fixture marker is checked.
- **Observed:** `validate_envelope(env, production_mode=True)` rejects **only** on
  `producer.component == "synthetic-test-fixture"`. Renaming that one field
  (`producer.component="acme-real-producer"`, re-sealed) makes the fixture **ACCEPTED** in production
  single-env validation **and** the production capture-gate pair (`validate_pair(..., production_mode=True,
  document_only=False)` → `accepted=True`), while it still carries `provenance.producer_component=
  synthetic-test-fixture`, `run_id=synthetic-0001`, and `payload.diagnostic_ref=synthetic://render`.
- **Reproduction:** rename `producer.component`, `es._seal`, then `validate_envelope(production_mode=True)`
  and `validate_pair(production_mode=True, document_only=False)`.
- **Root cause:** the production fixture guard (`validate_envelope` step-4) inspects a single field; there is
  no defence-in-depth over fixture run-id prefixes, `synthetic://` diagnostic refs, or
  `provenance.producer_component`, and no positive production-producer allow-list.
- **Severity:** **High** (fixture-to-production promotion). **Not Critical:** no automated path wires
  `production_mode=True` into capture authorisation, and the capture harness does not consume these
  envelopes — so it is not *currently* capture-enabling.
- **Safety / evidence-level impact:** falsifies the documented "fixture cannot enter production" guarantee;
  would become capture-enabling if a future backend wires production-mode validation into authorisation.
- **Containment:** no current consumer of production-mode validation in a capture path.
- **Recommended mitigation (remediation gate):** reject in production if **any** fixture marker is present
  (`producer.component`, `provenance.producer_component`, `run_id` `synthetic-*` prefix, `diagnostic_ref`
  `synthetic://` scheme, fixture id patterns), or invert to a positive production-producer allow-list.
- **Owner gate:** bounded provider/schema remediation gate.
- **Verdict effect:** Fixture/production separation = **FAIL**; provider implementation cannot pass (§26).

### H8-PREV-F-002 — Runtime-observer gate is a truthiness presence check — **MEDIUM**

- **Reviewed requirement:** (§1.6) runtime-valid evidence cannot be generated without a legitimate runtime
  observer.
- **Observed:** the block fires only when `runtime_observer is None`. Injecting any truthy object
  (`runtime_observer=object()`) bypasses the production block and emits `PROVIDER_OK_PREFLIGHT`; the observer
  is **never invoked or validated**. Output remains `indeterminate` (fail-safe — **no** `valid` evidence
  results).
- **Severity:** **Medium** (fail-safe: no runtime-valid overclaim results, but the "legitimate observer"
  requirement is unmet and the gate is trivially bypassable).
- **Recommended mitigation:** validate the observer against a defined interface; do not treat an arbitrary
  truthy object as satisfying the runtime requirement.
- **Owner gate:** runtime-validity design gate / bounded remediation.

### H8-PREV-F-003 — Dirty-tree enforcement is opt-in (fail-open when `tree_state` is `None`) — **MEDIUM**

- **Reviewed requirement:** (§15) a dirty dependency artefact must fail closed.
- **Observed:** `_preflight_prechecks` runs the dirty check only `if self.tree_state`. With no `tree_state`
  injected, the check is skipped and preflight emits regardless of working-tree state.
- **Severity:** **Medium** (fail-open on an omitted DI dependency; the injected-`tree_state` path is correct
  and does fail closed).
- **Recommended mitigation:** require `tree_state` in preflight/production (fail closed if absent) or supply
  a fail-closed default resolver.
- **Owner gate:** bounded remediation.

### H8-PREV-F-004 — Declared-but-unused / unreachable provider reason codes — **LOW**

- **Observed:** of 15 declared `PROVIDER_*` codes, 11 were exercised. `PROVIDER_MODE_INVALID` is unreachable
  (the constructor rejects bad modes before `emit`), `PROVIDER_ARTIFACT_DIGEST_FAILED` is never emitted
  (digest failures surface as `PROVIDER_INTERNAL_ERROR`), and `PROVIDER_CLOCK_UNTRUSTED` is reserved but
  never emitted. `PROVIDER_SCHEMA_REJECTED` is reachable defensively but not triggered by these probes.
- **Severity:** **Low** (taxonomy hygiene; fail-closed containment).
- **Recommended mitigation:** wire these codes to their conditions or mark them explicitly *reserved*.

### H8-PREV-F-005 — Documentation overclaims fixture-rejection depth — **LOW (documentation)**

- **Observed:** the implementation doc §11 and `H8-DCP-028` state production "rejects fixture
  sentinels/producers"; the actual check is the single `producer.component` field (see F-001).
- **Severity:** **Low** (documentation accuracy).
- **Recommended mitigation:** correct the wording to reflect the shallow check and its remediation once
  F-001 is fixed.

## 10. Reason-code coverage (§20)

| Reason code | Triggered | Output created | Result |
|---|---|---|---|
| PROVIDER_OK_PREFLIGHT | ✅ | in-memory only | ok |
| PROVIDER_OK_FIXTURE | ✅ | none (fixture ns) | ok |
| PROVIDER_BLOCKED_RUNTIME_OBSERVER_MISSING | ✅ | none | ok |
| PROVIDER_FIXTURE_REJECTED | ✅ | none | ok |
| PROVIDER_ARTIFACT_MISSING | ✅ | none | ok |
| PROVIDER_DIRTY_TREE | ✅ | none | ok |
| PROVIDER_INSTANCE_UNKNOWN | ✅ | none | ok |
| PROVIDER_OUTPUT_CONFLICT | ✅ | none | ok |
| PROVIDER_SIGNATURE_REQUIRED | ✅ | none | ok |
| PROVIDER_BINDING_MISMATCH | ✅ | none | ok |
| PROVIDER_INTERNAL_ERROR | ✅ (bad clock) | none | ok |
| PROVIDER_SCHEMA_REJECTED | ⚠️ not triggered (reachable, defensive) | — | see F-004 |
| PROVIDER_ARTIFACT_DIGEST_FAILED | ❌ unused | — | F-004 |
| PROVIDER_CLOCK_UNTRUSTED | ❌ reserved/unused | — | F-004 |
| PROVIDER_MODE_INVALID | ❌ unreachable | — | F-004 |

Coverage: **11/15 exercised**; 4 accounted for by F-004. No triggered failure created any output.

## 11. Other audited axes (summary)

- **Mode separation (§11):** unknown/case-variant/whitespace-padded modes rejected at construction; fixture
  mode refuses a non-`fixture` namespace; no implicit fallback. **PASS** (except the F-002 observer bypass).
- **Scene identity (§13):** scene **file** digest only; path traversal and absolute paths rejected by the
  reader; missing/changed scene handled; `scene_loaded=false`. Accurately documented as file-not-runtime.
  **PASS.**
- **Route structural limits (§14):** drive payload leaves `within_spatial_bounds`, `collision_feasible`,
  `avoids_prohibited_geometry` **false**, `degraded=true`, `runtime_observed=false`, `status=indeterminate`.
  No drive-valid overclaim. **PASS.**
- **Atomic write (§16):** temp-dir test — final files written via temp+fsync+rename; no `.tmp` residue;
  failed validation wrote nothing. **PASS.**
- **Clock (§17):** injected; naive/malformed timestamps rejected; no wall-clock call in the provider; time
  recorded as observational (no trusted-clock claim). **PASS** (freshness remains unproven, as documented).
- **Signature (§18):** unsigned recorded honestly; `require_signature` fails closed; no key material.
  **PASS.**
- **Replay/conflict (§19):** same-id-different-content and duplicates rejected; process-local only (already
  documented). **PASS.**
- **Import/runtime boundary (§21):** no `omni/isaacsim/rclpy/torch/cv2/sensor_msgs` token in the provider;
  none imported at runtime. **PASS** (static + `sys.modules`; not a full transitive proof).

## 12. Reproduced tests (§22)

`pytest tests/gnm/test_h8_evidence_provider.py test_h8_evidence_schema.py
test_h8_synthetic_fork_recorded_mode.py` → **133 passed**. Dry-run **25/25** `all_pass=True`. Level-1 five
files **byte-identical**. No H8 code/test/config modified. `py_compile` OK. Ruff **unavailable** (Open).
Attribution/secret scans **clean**.

## 13. Verdicts (§26)

| Axis | Verdict |
|---|---|
| Provider implementation | **FAIL** — unresolved **High** `H8-PREV-F-001` (plus Medium F-002, F-003); otherwise well-structured and correctly bounded. Cannot pass per §26. |
| Canonicalisation & digest correctness | **PASS** |
| Preflight-to-capture boundary | **PASS** |
| Fixture/production separation | **FAIL** — `H8-PREV-F-001` |
| Documentation | **PASS WITH MINOR FINDINGS** — `H8-PREV-F-005`, `H8-PREV-F-004` |

**The provider commit `97781ad` must NOT be used to authorise the Isaac backend/runtime-validity gate.** A
bounded provider/schema remediation gate is required first (F-001 High mandatory; F-002/F-003 Medium;
F-004/F-005 Low).

## 14. KPIs (§27)

| KPI | Target | Result |
|---|---|---|
| Provider requirement review coverage | 100% | 100% (8/8 claims tested) |
| Real dependency digest recomputation | 100% | 100% (config/scene/plan matched) |
| Canonicalisation adversarial-case coverage | 100% | 100% |
| Fixture-to-production rejection | 100% | **FAIL (F-001)** — single-sentinel only |
| Preflight capture-authorisation rejection | 100% | 100% |
| Evidence-ID conflict rejection | 100% | 100% |
| Route-offset substitution rejection | 100% | 100% |
| Failed-case zero-output rate | 100% | 100% |
| Atomic-write safety | 100% of tested failures | 100% |
| Provider reason-code review coverage | 100% or justified gaps | 11/15 + 4 justified (F-004) |
| Schema regression | 100% | 100% (34/34) |
| Recorded-mode regression | 100% | 100% (58/58) |
| Level-1 hash preservation | 5/5 | 5/5 |
| Boundary violations | 0 | 0 |
| Ruff | Pass or explicitly Open | **Open** |

## 15. SWOT (§28)

- **Strengths:** deterministic real-artefact digests (independently confirmed); robust preflight↔runtime
  separation (no `status=valid` code path; observer never invoked); strong evidence-ID/conflict handling;
  clean dependency injection; safe atomic writes; 100% provider traceability; no runtime imports.
- **Weaknesses:** fixture/production separation defeated by one renamed field (**F-001**); observer gate is a
  truthiness check (**F-002**); dirty-tree opt-in (**F-003**); unused reason codes (**F-004**); no trusted
  clock/signatures/scene-content manifest; local-only replay; Ruff unavailable.
- **Opportunities:** positive production-producer allow-list; observer interface contract; mandatory
  tree-state; signed runtime evidence; trusted timestamping; scene-content manifests; evidence ledger.
- **Threats:** fixture-marker stripping into production (F-001); document evidence misread as runtime proof
  if a future backend wires production-mode validation to capture; TOCTOU/symlink substitution; schema
  downgrade (currently blocked); evidence-ID collision (process-local).

## 16. Limitations & evidence boundary

This review establishes review validity over commit `97781ad` only. It does **not** establish real render/
drive validity, trusted time, signatures, runtime capture readiness, dataset validity, or model validity —
**Levels 3–5 remain unproven** and **real hospital footage/trajectory capture remains blocked**. The
import-boundary result is static + `sys.modules`, not a full transitive dependency proof.

## 17. Required next gate

**A bounded provider/schema remediation gate** (not the backend gate): resolve `H8-PREV-F-001` (High,
mandatory), `H8-PREV-F-002` and `H8-PREV-F-003` (Medium), and `H8-PREV-F-004`/`H8-PREV-F-005` (Low), then a
brief re-review of the fixture-separation and observer/dirty-tree guarantees. Only after an **unqualified**
provider review pass may the separately authorised Isaac backend / runtime-validity design gate proceed.
Progression: `schema validity → non-capturing provider validity → independent provider review → provider
remediation → Isaac runtime backend validation → explicit capture authorisation → hospital footage &
trajectory collection`.

## 18. Remediation dispositions (appended after the trust-boundary remediation gate, 2026-07-16)

The findings above are preserved verbatim. Their dispositions after the bounded remediation gate (see
[`H8_EVIDENCE_PROVIDER_REMEDIATION.md`](H8_EVIDENCE_PROVIDER_REMEDIATION.md)):

| Finding | Disposition | Control |
|---|---|---|
| `H8-PREV-F-001` (High) | **CLOSED** | Positive producer-trust policy (deny-by-default; default authorises no production producer) + 10-signal fixture defence-in-depth. Removing/renaming any fixture indicator no longer permits production acceptance. `H8-DCP-029/030/031`. |
| `H8-PREV-F-002` (Medium) | **CLOSED** | Typed `validate_runtime_observer` capability contract; truthy/partial/unauthorised observers rejected (`PROVIDER_OBSERVER_INVALID`). `H8-DCP-032`. |
| `H8-PREV-F-003` (Medium) | **CLOSED** | Mandatory fail-closed dirty-tree enforcement (no permissive default, no override). `H8-DCP-033`. |
| `H8-PREV-F-004` (Low) | **CLOSED (reserved code documented)** | 3 codes wired reachable+tested; `PROVIDER_MODE_INVALID` reserved. `H8-DCP-034`. |
| `H8-PREV-F-005` (Low) | **CLOSED** | Implementation-doc §11 corrected to the positive-trust wording. |

**Post-remediation verdict re-statement:** the remediation gate returned `PASS WITH DOCUMENTED
LIMITATIONS` (all five findings CLOSED). This does **not** substitute for the required **focused
independent re-review**, which must independently confirm `H8-PREV-F-001` closed before the backend gate.
Real capture remains blocked; Levels 3–5 unproven.
