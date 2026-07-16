# H8 Evidence-Provider Fixture-Separation & Trust-Boundary Remediation

**Gate type:** bounded provider/schema hardening. Resolves the independent-review findings
`H8-PREV-F-001..005`. No Isaac backend, runtime observer implementation, ROS 2, camera, robot,
capture, inference or training. Preflight evidence remains schema-valid-as-a-document yet **never**
authorises capture.

- **Date:** 2026-07-16 · **Branch:** `h23-execfix` (local, unpushed) · **Baseline HEAD:** `2790250`.
- **Reviewed provider** (`97781ad`) and **review report** (`2790250`) were byte-identical before this gate.
- **Changed:** `scripts/gnm/h8_evidence_schema.py` (positive producer trust), `scripts/gnm/h8_evidence_provider.py`
  (typed observer, mandatory dirty-tree, reason-code wiring), `tests/gnm/test_h8_evidence_provider_remediation.py`
  (new, 32 adversarial tests), + documentation.
- **Schema version unchanged** (`h8-evidence/1.0.0`): the fix uses an EXTERNAL trust policy over existing
  envelope fields — no new envelope fields, no format change, no downgrade surface added (§20).

## 1. Findings reproduced (pre-fix, §4)

| Finding | Reproduction | Observed BEFORE |
|---|---|---|
| F-001 | `synthetic_render_evidence()`, rename `producer.component="acme-real"`, reseal, `validate_envelope(production_mode=True)` | **ACCEPTED** (residual `provenance.producer_component=synthetic-test-fixture`, `run_id=synthetic-0001`, `diagnostic_ref=synthetic://`) |
| F-002 | `H8EvidenceProvider(mode="production", runtime_observer=object())` | `PROVIDER_OK_PREFLIGHT` (block bypassed by truthiness) |
| F-003 | `H8EvidenceProvider(mode="preflight", clock=…)` with **no** `tree_state` | `PROVIDER_OK_PREFLIGHT` (dirty check skipped) |
| F-004 | reason-code coverage | `ARTIFACT_DIGEST_FAILED`, `CLOCK_UNTRUSTED`, `MODE_INVALID`, `SCHEMA_REJECTED` never triggered |
| F-005 | docs §11 / `H8-DCP-028` | claim "production rejects fixture sentinels/producers" overstated the single-field check |

## 2. Remediation classification (§5)

| Finding | Class | Corrective control |
|---|---|---|
| F-001 | Implementation + schema trust-boundary hardening | Positive producer-trust policy + fixture defence-in-depth |
| F-002 | Typed interface + runtime capability hardening | `validate_runtime_observer` capability contract |
| F-003 | Production/preflight policy hardening | Mandatory, fail-closed dirty-tree enforcement |
| F-004 | Code/taxonomy cleanup + justified reservation | 3 codes wired reachable; `MODE_INVALID` reserved |
| F-005 | Documentation correction | Precise trust-model wording |

## 3. Positive production-trust design (F-001, §6/§7/§8)

Production acceptance is now **positive**: `check_production_trust(env, policy)` accepts only if the
producer is **registered, enabled, in a production-permitted trust class, and permitted for this
mode / evidence-type / schema-version** — AND the record carries **no residual fixture provenance**.
Unknown or incomplete → fail closed (`PRODUCER_NOT_AUTHORISED`); any fixture indicator → `FIXTURE_IN_PRODUCTION`.

**Producer trust policy** (`DEFAULT_PRODUCER_POLICY`, repository-controlled, static, **no secrets/keys**):

| producer_id | trust_class | permitted_modes | production-authorised? |
|---|---|---|---|
| `synthetic-test-fixture` | `fixture` | fixture | no |
| `h8-evidence-provider` | `preflight` | preflight | no |
| *(none)* | `runtime_authorised` | — | **empty this gate** |

`production_trust_classes = (runtime_authorised,)` — and **no** runtime producer is registered, so
**every current producer fails the production gate**. A future reviewed runtime producer is the only way
to populate it.

**Trust classes (§8):** `fixture` (fixture tests only), `preflight` (document-valid non-runtime),
`runtime_candidate` (cannot assert runtime validity until authorised), `runtime_authorised` (unavailable
this gate). A producer **cannot self-declare** a class: `trust_class` lives in the external policy keyed by
producer id, and the validator never reads a `trust_class` field from the envelope (test
`test_f001_self_declared_trust_class_ignored`).

**Fixture defence-in-depth (§9):** `_has_fixture_provenance` inspects 10 independent indicators —
`producer.component`, `producer.method`, `provenance.producer_component`, `provenance.run_id` (`synthetic-`
prefix), `provenance.method_id` (`synthetic-` prefix), `scene_source`, `config_source`,
`payload.diagnostic_ref` (`synthetic://`), and `producer`/`integrity` fixture `key_id`. Removing **one**
marker leaves the others — the renamed/removed-marker mutations all still reject (tests
`test_f001_*`). Positive trust plus defence-in-depth: a genuinely fixture-free but unregistered producer
still fails via `PRODUCER_NOT_AUTHORISED`.

**Positive path proven:** an injected test policy that authorises a `runtime_authorised` producer with
`status="valid"` **is** accepted (`test_f001_positive_path_accepts_authorised_producer`) — the mechanism
is not merely "reject everything"; it is a real allow-list that the default policy leaves empty.

## 4. Runtime-observer capability contract (F-002, §11/§12/§13)

`validate_runtime_observer(obj)` requires `observer_id`, `observer_version`, `supported_evidence_types`,
`supported_schema_versions`, `available is True`, callable `observe_render`/`observe_drive`, and an
`observer_id ∈ AUTHORISED_OBSERVER_IDS` (**empty this gate**). Rejected: `True`, `1`, `{}`, `object()`,
bare callables, partial-protocol objects, unavailable observers, and well-formed-but-unauthorised stubs.
The provider observer gate now returns `PROVIDER_BLOCKED_RUNTIME_OBSERVER_MISSING` for `None` and
`PROVIDER_OBSERVER_INVALID` for any present-but-invalid/unauthorised observer. **No Isaac observer is
implemented; stub observers are test-only and rejected by policy** — no runtime-valid evidence is created.

## 5. Mandatory dirty-tree enforcement (F-003, §14/§15)

`_preflight_prechecks` now fails closed when: `tree_state` is absent, the resolver raises, the result is
not a dict, or `dependency_dirty` is anything other than exactly `False`. There is **no** `allow_dirty`
override and **no** permissive default. The evidence-dependency closure is `EVIDENCE_DEPENDENCY_PATHS`
(config, scene `.usda`, `h8_evidence_schema.py`, `h8_evidence_provider.py`); each must also be readable.
Unrelated untracked files do not block (the caller's resolver scopes `dependency_dirty` to the dependency
set). Adversarial matrix in `test_f003_*`.

## 6. Reason-code taxonomy (F-004, §16)

`ARTIFACT_DIGEST_FAILED` (raising digest → guarded), `CLOCK_UNTRUSTED` (malformed clock → early
validation), and `SCHEMA_REJECTED` (a built envelope failing document validation, e.g. a mis-formatted
subject digest) are now **reachable and tested**. `PROVIDER_MODE_INVALID` is **reserved** (the constructor
rejects invalid modes, so the emit-time branch is an unreachable defensive guard) — listed in
`PROVIDER_RESERVED_CODES` and **excluded** from active-coverage. `PROVIDER_ACTIVE_CODES` (15 codes) are all
triggered by `test_f004_active_codes_all_triggerable_and_mode_invalid_reserved`.

## 7. Documentation correction (F-005, §17)

`H8_EVIDENCE_PROVIDER_IMPLEMENTATION.md` §11 now reads: *Production acceptance requires a positively
authorised producer and trust profile; fixture markers provide supplementary rejection signals but are not
the sole trust boundary.* The original failed single-sentinel design is preserved and cross-referenced (not
erased).

## 8. Preserved invariants (§18/§19/§25)

- **`document_only`** preflight still validates as a document and still fails the capture gate
  (`STATUS_NOT_VALID`); a preflight producer is not production-authorised even as a document
  (`test_document_only_preflight_still_blocks_capture`).
- Dual render+drive requirement, identity/window/revocation/integrity checks, capture validator,
  return-code behaviour, production-without-backend blocking, and no-output-before-validation all unchanged.
- **No backend / no output on any rejection** (`test_no_output_on_any_rejection`). Backend invocation on
  blocked/fixture cases remains **zero** (the provider has no backend and never calls the injected observer).
- **Level-1 five files byte-identical**; dry-run **25/25**; recorded-mode **58/58**; schema **34/34**;
  provider **41/41**; pilot path unmodified.

## 9. Threat-model updates (§32)

| Threat | Prevention | Detection | Residual |
|---|---|---|---|
| Single-sentinel bypass | positive trust + 10-signal defence-in-depth | `FIXTURE_IN_PRODUCTION`/`PRODUCER_NOT_AUTHORISED` | new indicators must be added if fixtures grow new markers |
| Producer-identity forgery | external registry keyed by producer id | `PRODUCER_NOT_AUTHORISED` | real signatures still deferred (`H8-C-009`) |
| Trust-class self-promotion | class lives in policy, never read from envelope | `PRODUCER_NOT_AUTHORISED` | — |
| Observer truthiness injection | typed capability contract | `PROVIDER_OBSERVER_INVALID` | real observer interface finalised at runtime gate |
| Partial observer capability | required attrs+methods+available | `PROVIDER_OBSERVER_INVALID` | — |
| Dirty-dependency generation | mandatory fail-closed dirty check | `PROVIDER_DIRTY_TREE` | caller must scope `dependency_dirty` correctly |
| Trust-policy tampering | static repo-controlled policy (in VCS) | code review / VCS diff | signed policy is future work |
| Registry / schema downgrade | strict supported-set + per-producer permitted versions | `SCHEMA_VERSION_UNSUPPORTED`/`PRODUCER_NOT_AUTHORISED` | migration policy (`H8-C-012`) |
| Fixture-marker stripping | 10-signal defence-in-depth | `FIXTURE_IN_PRODUCTION` | — |
| Evidence provenance laundering | positive producer auth (deny-by-default) | `PRODUCER_NOT_AUTHORISED` | trusted provenance chain (future) |

## 10. Verification (§24/§29)

`pytest` (remediation + provider + schema + recorded) → **165 passed**. Dry-run **25/25**. Level-1
**5/5** byte-identical. `py_compile` OK. Ruff **unavailable** (Open, `H8-C-006`/`H8-C-013`).
Attribution/secret scans clean (the string "NO … private keys" in a code comment is a scan false-positive,
not a secret). No `assets/evidence/` or dataset dir created. `git diff --check` clean.

| KPI | Target | Result |
|---|---|---|
| Finding reproduction | 5/5 | 5/5 |
| Finding disposition | 5/5 | 5/5 |
| Fixture mutation rejection | 100% | 100% |
| Unknown producer rejection | 100% | 100% |
| Producer self-promotion rejection | 100% | 100% |
| Invalid observer rejection | 100% | 100% |
| Protected dirty-tree rejection | 100% | 100% |
| Preflight capture-authorisation rejection | 100% | 100% |
| Failed-case zero-output rate | 100% | 100% |
| Backend invocation on blocked cases | 0 | 0 |
| Active reason-code coverage | 100% | 100% (15/15; 1 reserved) |
| Schema regression | 100% | 100% (34/34) |
| Provider regression | 100% | 100% (41/41) |
| Recorded-mode regression | 100% | 100% (58/58) |
| Dry-run | 25/25 | 25/25 |
| Level-1 hashes | 5/5 | 5/5 |
| Boundary violations | 0 | 0 |
| Ruff | Pass or explicitly Open | Open |

## 11. Finding dispositions (§27) & overall verdict (§28)

| Finding | Disposition |
|---|---|
| `H8-PREV-F-001` | **CLOSED** — removing/renaming any single (or several) fixture indicators no longer permits production acceptance; production requires positive authorisation, which the default policy grants to no producer. |
| `H8-PREV-F-002` | **CLOSED** — arbitrary truthy and incomplete observers are rejected by the typed capability contract; no observer is authorised this gate. |
| `H8-PREV-F-003` | **CLOSED** — protected preflight/production generation enforces cleanliness by default and cannot be bypassed by an ordinary caller option; absent/failing/ambiguous tree-state fails closed. |
| `H8-PREV-F-004` | **CLOSED (with documented reserved code)** — 3 codes now reachable+tested; `PROVIDER_MODE_INVALID` formally reserved. |
| `H8-PREV-F-005` | **CLOSED** — documentation corrected; original defect preserved. |

**Overall gate verdict: `PASS WITH DOCUMENTED LIMITATIONS`.** No finding remains Open; the fail-open
Medium findings (F-002, F-003) are resolved. Residual (documented, deferred) limitations: real runtime
observer, trusted clock, production signatures/keys, and operational revocation remain unbuilt — each owned
by a later gate. **Real capture remains blocked; Levels 3–5 unproven.**

## 12. Next gate (§42)

A **narrow independent re-review** of the remediated trust boundaries (positive producer authorisation,
fixture defence-in-depth, typed observer contract, mandatory dirty-tree) to confirm `H8-PREV-F-001` is
independently verified as **closed**. Only after an unqualified re-review pass may the separately authorised
**Isaac backend / runtime-validity design gate** begin. Progression: `provider review failure →
trust-boundary remediation → focused independent re-review → backend/runtime design → runtime validation →
explicit capture authorisation → hospital footage & trajectory collection`.
