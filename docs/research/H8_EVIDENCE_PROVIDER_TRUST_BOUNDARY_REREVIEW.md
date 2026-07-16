# H8 Remediated Evidence-Provider Trust-Boundary — Independent Re-review

**Gate:** `H8 Remediated Evidence-Provider Trust-Boundary Independent Re-review` (focused adversarial
verification, review-only). **Date:** 2026-07-16. **Branch:** `h23-execfix`.

This report is an INDEPENDENT re-review. It does not restate the remediation report as proof; it
reproduces the original failure, re-runs the fixture-laundering matrix, adds novel laundering paths, and
probes the positive allow-list, observer contract, dirty-tree enforcement, reason-code taxonomy,
`document_only` boundary and preflight-to-capture boundary directly against the code at `a449ab6`. It does
not rewrite the original review or remediation reports.

**Boundary honoured:** no Isaac launch, rendering, driving, footage/trajectory/rosbag creation, inference,
action probe, training, 20/5/10, closed-loop, push, tag, promotion or publication. No backend, runtime
observer, ROS 2, camera, robot-control, capture writer or dataset collection was implemented.

---

## 1. Commits reviewed (full canonical hashes)

| Role | Hash |
|---|---|
| Remediation (subject of this re-review) | `a449ab6ccd307c2663a1d8ed35529ded8256f87a` |
| Provider implementation (pre-remediation) | `97781adadf4e708d7e6e03914e79724916f28864` |
| Provider independent review (failed) | `2790250807d5bd30d6b1703dbdfd220fed33b05b` |
| Evidence-schema implementation | `ebf8341fff03b0af9a63fc41705c3f2ce622ed7a` |
| Capture-path hardening | `31b1d01…` (`Harden H8 capture-path review findings`) |
| Schema-gate ancestor chain | `c6b42ac → bb94c5a → db70ce3 → bd6168a → 66fd81e → ecae4cd → 7a73c9f` |

**Baseline:** `HEAD = a449ab6…` on `h23-execfix`; branch local and unpushed. Working tree carries only
pre-existing, unrelated dataset/trajectory/config artefacts (datasets/*, scripts/datasets/*,
`scripts/gnm/06_evaluate.py`, and untracked `assets/experiments/**` outputs) — **none** under the
provider, schema, tests, or `docs/research` trust-boundary surface. All cited historical commits are
content-addressed and match the hashes above (unchanged).

## 2. Original findings under re-review

- `H8-PREV-F-001` (HIGH) — single-sentinel fixture trust: renaming `producer.component` laundered a fixture
  into production acceptance.
- `H8-PREV-F-002` (MED) — arbitrary truthy observer accepted.
- `H8-PREV-F-003` (MED) — dependency-cleanliness check was opt-in / skippable.
- `H8-PREV-F-004` (LOW) — unreachable reason codes conflated with active taxonomy.
- `H8-PREV-F-005` (LOW) — documentation overstated fixture detection.

## 3. Remediation diff reviewed

`git diff 2790250..a449ab6` — 8 files, +843/−24: `h8_evidence_schema.py` (+106), `h8_evidence_provider.py`
(+89), `test_h8_evidence_provider_remediation.py` (+349, new), and five docs. Controls confirmed present
in code (not merely documented):

- **Positive producer trust policy** (`check_production_trust`, `DEFAULT_PRODUCER_POLICY`): registry keyed
  by `producer.component`; requires enabled + production-authorised trust class + permitted
  mode/evidence-type/schema-version. Deny-by-default; **zero** production-authorised producers registered.
- **Trust classes** `fixture / preflight / runtime_candidate / runtime_authorised`; class is read from the
  external policy, never from the envelope.
- **Fixture defence-in-depth** (`_has_fixture_provenance`): 10 independent signals; any hit →
  `FIXTURE_IN_PRODUCTION`.
- **Typed observer contract** (`validate_runtime_observer`, `AUTHORISED_OBSERVER_IDS = ∅`).
- **Mandatory dirty-tree** (`_preflight_prechecks`): absent/raising/non-dict/`dependency_dirty≠False` →
  `PROVIDER_DIRTY_TREE`; no `allow_dirty` override.
- **Active vs reserved codes** (`PROVIDER_ACTIVE_CODES` = 15; `PROVIDER_RESERVED_CODES = {MODE_INVALID}`).
- Decisions `H8-DCP-029…034` are implemented as described.

## 4. Original F-001 bypass — reproduction and post-remediation result

Reproduced by importing the historical schema module from `97781ad` (stdlib-only, standalone). Built a
schema-valid fixture render envelope, **renamed only `producer.component`** (retaining all other fixture
provenance), and submitted under `production_mode=True`:

- **`97781ad` (pre): ACCEPTED** (`reason_code = ACCEPTED`) — the bypass is real and reproduced.
- **`a449ab6` (post): REJECTED** (`reason_code = FIXTURE_IN_PRODUCTION`) — residual fixture provenance is
  caught by defence-in-depth.
- **Fully scrubbed (all 10 signals removed) but producer unregistered: REJECTED**
  (`reason_code = PRODUCER_NOT_AUTHORISED`) — positive authorisation is decisive even when no fixture
  marker survives.

## 5. Positive allow-list — functional, not reject-all

Under an **injected** test policy authorising one producer (`h8-runtime-authorised`, class
`runtime_authorised`, production mode, schema `h8-evidence/1.0.0`, enabled) a fully re-attributed,
fixture-free, `status=valid` envelope is **ACCEPTED** (`reason_code = ACCEPTED`). The allow-list admits a
legitimately registered producer — it is not a deny-all. All rejection variants also hold:

| Case | Result |
|---|---|
| Authorised runtime producer (injected policy) | **ACCEPTED** |
| Same producer under `DEFAULT_PRODUCER_POLICY` | REJECTED (`PRODUCER_NOT_AUTHORISED`) — deny-by-default |
| Unknown producer | REJECTED |
| Disabled/revoked producer | REJECTED |
| Disallowed schema version | REJECTED |
| Disallowed evidence type | REJECTED |
| Preflight-class producer requesting production | REJECTED (wrong class) |
| Producer permitted only in preflight mode | REJECTED |
| Empty allow-list / malformed policy `{}` | REJECTED (fails closed) |

The registered **preflight** producer `h8-evidence-provider` is separately exercised by the provider's
preflight path (223 passing tests + dataset-dry-run): it produces `status=indeterminate` documents that
validate as documents and never satisfy the capture gate.

## 6. Producer-policy integrity

Policy is a **repository-controlled static dict** in `h8_evidence_schema.py` (part of the evidence
dependency closure via the dirty-tree scope). No secrets/keys. Identity comparison is **exact**:

| Probe | Result |
|---|---|
| Case-variant producer id (`H8-RUNTIME-AUTHORISED`) | REJECTED (no case-fold) |
| Trailing whitespace | REJECTED |
| Unicode look-alike (Cyrillic `е`) | REJECTED (exact bytes) |
| Self-declared `producer.trust_class` = runtime_authorised | IGNORED → REJECTED (registry authoritative) |
| Malformed/empty policy | Fails closed |

Note: Python dict literals cannot contain duplicate keys, so a duplicate producer id is a load-time
collapse rather than a runtime bypass; the last definition wins deterministically and is repository-visible.

## 7. Fixture-laundering matrix (21 mutations + 2 mixed pairs)

Every fixture-origin or unauthorised mutation is **rejected** under a policy that authorises a *different*
legitimate producer (the strict test — deny-all would trivially pass). **23/23 rejected (100%).**

Highlights: single-marker removal/rename, run-id/method-id/scene-source/config-source/key-id changes,
context "mode→production", self-declared trust class → all `FIXTURE_IN_PRODUCTION`. Evidence-id change →
`SCHEMA_MALFORMED`. All-signals-scrubbed but unknown producer → `PRODUCER_NOT_AUTHORISED`. **M17 (fixture
provenance copied under an authorised producer id) → `FIXTURE_IN_PRODUCTION`**: defence-in-depth rejects even
when the producer id is itself authorised. Mixed pairs (fixture render + authorised drive, and vice-versa)
→ rejected by `validate_pair`.

## 8. Ten-signal defence-in-depth

Starting from a fully-scrubbed, authorised-id envelope and re-introducing exactly **one** fixture signal at
a time, each signal is independently detected and each alone forces rejection:

| # | Signal | Independently evaluated | Removal alone permits acceptance | Result |
|---|---|---|---|---|
| 1 | `producer.component == synthetic-test-fixture` | yes | no | REJECTED |
| 2 | `producer.method == synthetic` | yes | no | REJECTED |
| 3 | `provenance.producer_component == fixture` | yes | no | REJECTED |
| 4 | `provenance.run_id` starts `synthetic-` | yes | no | REJECTED |
| 5 | `provenance.method_id` starts `synthetic-` | yes | no | REJECTED |
| 6 | `provenance.scene_source == synthetic` | yes | no | REJECTED |
| 7 | `provenance.config_source == synthetic` | yes | no | REJECTED |
| 8 | `payload.diagnostic_ref` scheme `synthetic://` | yes | no | REJECTED |
| 9 | `producer.key_id` starts `fixture` | yes | no | REJECTED |
| 10 | `integrity.key_id` starts `fixture` | yes | no | REJECTED |

No single signal is the primary boundary: with **all** signals removed and an unknown producer, acceptance
is still denied by positive authorisation (`PRODUCER_NOT_AUTHORISED`). Fixture signals are supplementary
rejection/diagnostics; positive authorisation is decisive.

## 9. Evidence self-promotion

Mutating only evidence-controlled fields (`producer.trust_class`, `provenance.trust_class`,
`integrity.verification_status`, context mode) cannot raise trust: the external policy is authoritative and
the registry class is read from the policy, never from the envelope. Result: **REJECTED**. Runtime-valid
status cannot be obtained by document mutation.

## 10. Runtime-observer contract

`validate_runtime_observer` rejects every adversarial input: `True`, `False`, `1`, non-empty string, dict,
arbitrary object, generic callable, render-only object, unavailable full observer, unsupported evidence
type, and `None`. A fully conforming observer is **rejected in production** (`AUTHORISED_OBSERVER_IDS` is
empty). **Not reject-all:** temporarily authorising the test observer id in a test-only context makes the
conforming observer pass protocol validation — proving the contract is satisfiable — after which the set is
restored to empty and production again rejects all observers. At the provider level, production mode with no
observer → `PROVIDER_BLOCKED_RUNTIME_OBSERVER_MISSING`; a truthy non-observer with `want_runtime_valid` →
`PROVIDER_OBSERVER_INVALID`; both create **no output**.

## 11. Mandatory dirty-tree

Provider preflight/production enforce cleanliness with **no opt-in and no override** (`allow_dirty` is not a
parameter; the only textual occurrence is an explanatory comment stating no such override exists). Fail-
closed on: absent resolver, raising resolver (Git-inspection failure), non-dict result, `dependency_dirty`
`True`/`None`/missing/truthy-non-`False`. **7/7 fail-closed, zero output.** Only an affirmatively-clean
`dependency_dirty is False` proceeds.

**Dependency closure** (`EVIDENCE_DEPENDENCY_PATHS`): dataset config, scene `.usda`, `h8_evidence_schema.py`,
`h8_evidence_provider.py`. The producer trust policy lives inside `h8_evidence_schema.py`, so a policy change
is a schema-file change and is inside the closure (not treated as unrelated documentation). **Documented
limitation:** the provider consumes an injected `dependency_dirty` boolean; there is **no concrete
git-based resolver** in the repository yet, so detection of staged/unstaged/untracked substitution of
protected artefacts is delegated to a resolver that must be built and independently reviewed before
production capture (see `H8-PRREV-F-002`, informational).

## 12. Active/reserved reason codes

`PROVIDER_ACTIVE_CODES` = 15 (all reachable and triggered by the remediation suite);
`PROVIDER_RESERVED_CODES` = `{PROVIDER_MODE_INVALID}`, excluded from active coverage and unreachable via the
constructor (bad mode raises `ValueError` before any code is emitted). **Active coverage 15/15; reserved 1,
documented.**

## 13. `document_only` and preflight-to-capture boundary

- Indeterminate document: **accepted** as a document (`document_only=True`); **rejected** at the capture
  gate (`document_only=False` → `STATUS_NOT_VALID`).
- `document_only` + `production_mode` + fixture producer → **rejected** (`FIXTURE_IN_PRODUCTION`): a
  preflight fixture cannot be laundered even as a production document.
- Schema downgrade → `SCHEMA_VERSION_UNSUPPORTED`.
- `preflight_satisfies_capture_gate` on an indeterminate envelope → `authorises_capture = False`,
  `is_valid_document = True`.
- A lone render document cannot form a render+drive pair (`PAIR_INCOMPLETE`) — `document_only` is not an
  alternate path around the dual requirement.
- Backend invocation: **zero** (no backend exists; provider imports no Isaac/ROS/torch/cv2; verified by a
  `sys.modules` audit after import).

## 14. Schema compatibility

Schema version is **unchanged** (`h8-evidence/1.0.0`). The new production control is supplied entirely by
the **external** trust policy over existing fields — evidence does not self-declare authorisation — so there
is no new envelope field, no downgrade surface, and no automatic upgrade of historical evidence into
authorised evidence. Compatibility is accurately documented.

## 15. Regression, audits, and preservation

| Check | Command (summary) | Result |
|---|---|---|
| Remediation+provider+schema+recorded | `pytest test_h8_evidence_provider_remediation/…provider/…schema/…recorded_mode` | **165 passed** |
| Full H8 suite | `pytest tests/gnm/test_h8_*.py` | **223 passed** |
| Dataset dry-run | `--mode dataset-dry-run … --emit-schema` | **25/25**, `overall=PASS`, all injected leakage failed closed |
| Level-1 evidence | `git diff --quiet` on synthetic-fork validation dirs | **byte-identical** (not in `a449ab6` diff) |
| Compilation | `py_compile` (both modules + test) | OK |
| Ruff | `python -m ruff` / `which ruff` | **UNAVAILABLE → Open** (`H8-C-006`/`H8-C-013`) |
| Negative-artifact audit | `assets/evidence/h8/{preflight,runtime}` | absent (none created) |
| Attribution scan | 8 remediation files | clean |
| Secret scan | 8 remediation files | clean |
| `git diff --check` | `2790250..a449ab6` | clean |
| Import audit | `sys.modules` after provider import | no Isaac/ROS/torch/cv2 |

Doc-consistency cross-check (code vs remediation doc claims): default-policy production-authorised producers
= 0; active codes = 15, reserved = `{PROVIDER_MODE_INVALID}`; authorised observer ids = 0; fixture signals =
10; trust classes = 4; schema version = `1.0.0`. **All documentation claims match implementation.**

## 16. New re-review findings

| ID | Severity | Control | Summary | Effect on closure / eligibility |
|---|---|---|---|---|
| `H8-PRREV-F-001` | LOW (informational) | Producer trust policy | Producer **software** version (`producer.version`) is not a modelled trust dimension — `check_production_trust` gates schema-version/mode/evidence-type/trust-class/enabled but not producer version. Not a security gap (schema version, the contract version, IS gated; zero runtime producers authorised). | None. Recommend documenting version-pinning as intentionally out-of-scope or adding `permitted_versions` if desired later. |
| `H8-PRREV-F-002` | LOW (informational / documented limitation) | Dirty-tree | The provider trusts an injected `dependency_dirty` boolean; **no concrete git resolver** exists yet, so staged/unstaged/untracked substitution detection is delegated to unbuilt code. Enforcement *contract* is correct and mandatory. | None on F-003 (contract verified). Must be built + reviewed before production capture; owned by the backend/runtime design gate. |
| `H8-PRREV-F-003` | INFORMATIONAL | Provider orchestration | In `MODE_PRODUCTION` the provider returns at the observer gate *before* reaching the schema-level positive `check_production_trust` (only exercised via direct `validate_envelope`). This is stricter defence-in-depth, not a defect, but the positive allow-list is currently reachable only through the schema API. | None. A future runtime provider should wire the trust policy into the provider path explicitly. |

No Critical/High/Medium re-review finding. No new laundering, self-promotion, observer-truthiness, or
capture-bypass path was found.

## 17. Closure verdicts for original findings

| Finding | Verdict |
|---|---|
| `H8-PREV-F-001` | **INDEPENDENTLY VERIFIED CLOSED** — marker removal/rename cannot permit acceptance; unknown producers reject; a positively registered producer is accepted (allow-list usable); preflight remains capture-blocked; 23/23 laundering rejections; no High-severity path remains. |
| `H8-PREV-F-002` | **INDEPENDENTLY VERIFIED CLOSED** — truthy/partial/malformed observers reject; conforming observer satisfiable only in an authorised test context; no production runtime evidence produced. |
| `H8-PREV-F-003` | **INDEPENDENTLY VERIFIED CLOSED** (with documented limitation `H8-PRREV-F-002`) — cleanliness mandatory by default; no ordinary bypass; dirty deps reject; Git-inspection failure rejects. |
| `H8-PREV-F-004` | **INDEPENDENTLY VERIFIED CLOSED** — 15/15 active codes covered; reserved code separated and unreachable. |
| `H8-PREV-F-005` | **INDEPENDENTLY VERIFIED CLOSED** — documentation matches the remediated implementation. |

## 18. Independent re-review verdicts

| Dimension | Verdict |
|---|---|
| Positive producer-authorisation control | **PASS** |
| Fixture/production separation | **PASS** |
| Runtime-observer contract | **PASS** |
| Dirty-tree enforcement | **PASS WITH DOCUMENTED LIMITATIONS** (concrete git resolver unbuilt) |
| Preflight-to-capture boundary | **PASS** |
| Documentation | **PASS WITH MINOR FINDINGS** (`H8-PRREV-F-001`/`-F-002` wording recommendations) |
| **Overall provider re-review** | **PASS WITH DOCUMENTED LIMITATIONS** |

The overall pass is legitimate: `H8-PREV-F-001` is independently verified Closed; no unresolved
Critical/High finding; positive authorisation is functional and deny-by-default (not reject-all); no fixture
can be laundered; dirty dependencies cannot generate protected evidence; arbitrary observer truthiness is
rejected; preflight evidence cannot authorise capture.

## 19. Backend-gate eligibility

**ELIGIBLE FOR BACKEND/RUNTIME DESIGN GATE.** All eligibility conditions are met: `H8-PREV-F-001`
unqualified closed; no unresolved High findings; producer authorisation functional and deny-by-default;
observer contract fail-closed; dirty-tree enforcement verified at the contract level; preflight-to-capture
boundary passing; real capture still explicitly blocked. **Eligibility authorises only a separately scoped
backend/runtime *design* gate — NOT Isaac execution, rendering, driving, or any capture.** The documented
limitations (concrete git resolver, real runtime observer, trusted clock, production signatures/keys,
operational revocation) are precisely the design-gate agenda and must be built and independently reviewed
before any capture authorisation.

## 20. KPIs

| KPI | Target | Result |
|---|---|---|
| Original finding re-verification | 5/5 | **5/5** |
| Positive authorised-preflight acceptance | 100% | **100%** |
| Unknown-producer rejection | 100% | **100%** |
| Fixture-laundering rejection | 100% | **100% (23/23)** |
| Producer self-promotion rejection | 100% | **100%** |
| Invalid-observer rejection | 100% | **100% (11/11 incl. None + conforming-unauthorised)** |
| Protected dirty-dependency rejection | 100% | **100% (7/7)** |
| Active reason-code coverage | 15/15 | **15/15 (+1 reserved)** |
| Preflight capture rejection | 100% | **100%** |
| Blocked-case backend calls | 0 | **0** |
| Blocked-case zero-output rate | 100% | **100%** |
| Provider regression | 41/41 | **41/41** (within 223 full-suite) |
| Schema regression | 34/34 | **34/34** (within 223) |
| Recorded-mode regression | 58/58 | **58/58** (within 223) |
| Dry-run | 25/25 | **25/25** |
| Level-1 evidence hashes | 5/5 unchanged | **5/5 unchanged** |
| Boundary violations | 0 | **0** |
| Ruff | Pass or explicitly Open | **Open** |

Runtime observers, trusted clocks, production signatures, operational revocation, Isaac runtime and dataset
capture are **not** counted as passing — they are unbuilt.

## 21. SWOT

**Strengths:** positive external producer authorisation (deny-by-default); 10-signal fixture
defence-in-depth that survives single/multi-marker scrubbing; typed observer capability contract; mandatory
fail-closed dependency cleanliness; non-authorising preflight documents; deterministic digests and atomic
writes; schema version unchanged (no downgrade surface).

**Weaknesses:** static repository-controlled producer registry (no cryptographic producer identity); no
concrete git tree-state resolver yet; no trusted runtime observer; no trusted clock; no production
signature/key management; no operational revocation; local-only replay protection; Ruff unavailable.

**Opportunities:** signed runtime-observer identities; key-backed producer authentication; trusted
timestamping; a revocation registry; scene-content manifests; a reviewed Isaac runtime integration.

**Threats:** producer-registry tampering (mitigated by dirty-tree closure once a real resolver exists);
authorised-identity impersonation without signatures; policy downgrade; fixture laundering through
unknown *future* fields; dependency-closure omission; backend bypass; premature capture claims.

## 22. Remaining limitations

Real runtime observer, trusted clock, production signatures/keys, operational revocation, and a concrete
git dirty-tree resolver are all unbuilt. Evidence Levels 3–5 (runtime, dataset, model) remain **unproven**.
Real hospital footage and trajectory collection remains **blocked**.

## 23. Traceability

New findings `H8-PRREV-F-001…003` originate in this re-review and do not modify the original `H8-PREV-*`
findings. Programme position:
`provider remediation → **independent trust-boundary re-review (this gate: PASS WITH DOCUMENTED LIMITATIONS)**
→ backend/runtime design → runtime validation → explicit capture approval → hospital footage & trajectory
collection`.
