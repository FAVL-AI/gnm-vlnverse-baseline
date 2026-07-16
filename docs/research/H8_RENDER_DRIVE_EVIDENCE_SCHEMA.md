# H8 Render-Valid & Drive-Valid Evidence Schema — Design Gate

**Gate type:** schema, policy, threat-model and conformance-test **design only**. No real evidence
provider, Isaac backend, ROS 2 integration, camera recorder, trajectory writer, or dataset-capture
operation was implemented. A schema-valid synthetic fixture is **NOT** runtime (Level-3) evidence and
must not be promoted to one.

- **Date:** 2026-07-16 · **Branch:** `h23-execfix` (local, unpushed) · **Baseline HEAD:** `31b1d01`.
- **Artifacts:** `scripts/gnm/h8_evidence_schema.py` (pure validator + fixtures),
  `docs/research/schemas/h8_evidence_envelope.schema.json` (machine-readable schema),
  `tests/gnm/test_h8_evidence_schema.py` (conformance tests).
- **Milestone chain:** `7a73c9f` → `ecae4cd` → `66fd81e` → `bd6168a` → `db70ce3` → `bb94c5a` →
  `c6b42ac` → `31b1d01` → *(this gate)*.

## 1. Objective, research question, hypothesis

**Objective (§1).** Design a versioned, fail-closed evidence contract that answers: *for a specific
planned H8 hospital capture instance, do we possess current, authentic, correctly bound and
independently verifiable evidence that the scene renders correctly and that the intended robot route is
drive-valid?* The schema must prevent evidence created for one instance, scene, route, configuration or
time window from being reused silently for another.

**Research question (§3).** *What minimum evidence schema and validation policy are required to bind
render-valid and drive-valid evidence to one H8 hospital dataset instance while preventing stale,
replayed, mismatched, revoked, malformed or unauthorised evidence from enabling capture?*

**Hypothesis (§4, falsifiable).** *A versioned evidence envelope containing canonical instance, scene,
route, configuration, producer, time, integrity and revocation fields can deterministically reject
evidence that is malformed, expired, replayed, identity-mismatched, scene-mismatched, route-mismatched,
configuration-mismatched, revoked or cryptographically unverifiable before any Isaac capture backend is
invoked.* This gate tests schema **expressiveness and validator behaviour** only; it does **not**
establish that a real provider produces truthful evidence.

## 2. Envelope architecture (§5)

Schema `SCHEMA_VERSION = h8-evidence/1.0.0`. One record per `evidence_type ∈ {render_valid,
drive_valid}`. 14 required top-level sections (strict — unknown top-level fields are rejected):

```
EvidenceEnvelope
├── schema_version        exact supported version (no downgrade)
├── evidence_id           ^h8ev-<type>-<slug>-<seq>$
├── evidence_type         render_valid | drive_valid
├── status                valid | invalid | indeterminate | revoked
├── subject               identity binding (§3 below)
├── context               route_family, claim_boundary, capture_mode (non-identity)
├── producer              component, version, method, key_id
├── observation_time      RFC 3339 UTC
├── issue_time            RFC 3339 UTC
├── validity_window       not_before, not_after, max_age_seconds, clock_source, clock_skew_seconds
├── integrity             canonicalization, digests (subject/payload/content), signature fields
├── provenance            producer/source_commit/run_id/host_label/method/scene+config source/parent
├── revocation            revoked, revoked_at, reason, authority, replacement, supersedes
└── payload               evidence-type-specific (§7 / §8)
```

## 3. Identity binding (§6)

`subject` binds evidence to exactly one instance. Fields required for **both** evidence types:
`dataset_plan_id`, `instance_id`, `split`, `scene_id`, `scene_digest`, `route_id`, `route_plan_digest`,
`config_digest`, `coordinate_frame`, `cl_bound_xy`. Optional/contextual: `start_pose`, `goal_ref`
(goal pose **or** goal-image id), `sim_context` (simulator + version, where applicable).

The validator compares each binding against a caller-supplied `expected` map; a mismatch fails closed
with a specific reason code (`INSTANCE_MISMATCH`, `SCENE_MISMATCH`, `ROUTE_MISMATCH`, `CONFIG_MISMATCH`,
`FRAME_MISMATCH`, `BOUND_MISMATCH`). **`subject.cl_bound_xy` must equal `6.0`** (the read-only watchdog,
mirrored from the drive-validation harness) independently of `expected` — safety scope is bound into the
evidence itself.

## 4. Render-valid payload (§7)

Minimum fields for a real provider to eventually establish scene-render validity (booleans unless noted):
`scene_loaded`, `camera_present`, `camera_transform_matches`, `resolution` `[w,h]`, `encoding`,
`frame_nonempty`, `frame_not_constant` (blank/constant/corrupt rejected), `required_geometry_visible`,
`no_invalid_render_condition`, `validation_method`, `thresholds` (object), `diagnostic_ref` (a traceable
reference — large image artefacts are **never** embedded in the schema). *These checks are NOT claimed to
have been executed during this gate.*

## 5. Drive-valid payload (§8)

Minimum fields for a real provider to eventually establish route drive-validity:
`start_bound_to_instance`, `goal_bound_to_instance`, `within_spatial_bounds`, `collision_feasible`,
`min_clearance_m` + `clearance_threshold_m`, `avoids_prohibited_geometry`, `route_length_m`,
`waypoint_count`, `coordinate_frame`, `validation_method`, `planner_version`, `sim_context`, `degraded`
(a degraded/uncertain result is **not** valid), `diagnostic_ref`. *No real planner, robot or Isaac
simulation was run.*

## 6. Status (§9), freshness (§10), revocation (§11), integrity (§12), provenance (§13)

- **Status.** Enum `{valid, invalid, indeterminate, revoked}`. **Only `valid` satisfies the gate**;
  missing/unknown/malformed/`invalid`/`indeterminate`/`revoked` all block. No truthy-string or Boolean
  coercion — the value must be exactly in the enum.
- **Freshness.** `observation_time`, `issue_time`, and a `validity_window` (`not_before`, `not_after`,
  `max_age_seconds`, `clock_source:"utc"`, `clock_skew_seconds`), all **RFC 3339 UTC with a required
  timezone**. Time is evaluated against an **injected `review_time`** (deterministic — the validator
  never reads a wall-clock). Rejections: naive/malformed timestamps; `not_after ≤ not_before`;
  `issue_time > not_after`; `observation_time > issue_time`; `review_time` outside `[not_before-skew,
  not_after+skew]`; observation older than `max_age_seconds`. This **supersedes** the capture-path
  `stale:true` marker (`H8-DCP-015` → `H8-DCP-019`).
- **Revocation.** `revocation.revoked` (or `status=="revoked"`) → `EVIDENCE_REVOKED`. Fields:
  `revoked_at`, `reason`, `authority`, `replacement_evidence_id`, `supersedes`. Revocation may be
  embedded (here) or externally resolved (future); the external revocation service is **not** built.
- **Integrity.** Canonicalisation `h8-canonical-json/1.0`. Three SHA-256 digests are bound and
  recomputed on validation: `subject_digest`, `payload_digest`, `content_digest` (over the whole
  envelope with derived integrity fields blanked). Signatures are **optional at schema level**:
  `verification_status ∈ {unsigned, unverified, verified}`; a caller may `require_signature`, then only
  `verified` passes. **Unsigned test fixtures are never described as authenticated evidence.**
- **Provenance.** `producer_component`/`version`, `source_commit`, `run_id`, `host_label`
  (non-sensitive), `method_id`, `scene_source`, `config_source`, `parent_evidence_id`, `generated_at`,
  `review_state`. No private paths, credentials, or personal data.

## 7. Pairing policy (§14)

`validate_pair(render, drive)` accepts only if: both individually pass; they **share every** binding in
`{dataset_plan_id, instance_id, scene_digest, route_plan_digest, config_digest, coordinate_frame,
cl_bound_xy}`; and their validity windows **overlap**. Otherwise `PAIR_INCOMPLETE` (one missing),
`PAIR_BINDING_MISMATCH`, or `PAIR_WINDOW_DISJOINT`. No broad scene-level record authorises unrelated
instances (reuse policy is deliberately undesigned — `H8-C-010`).

## 8. Canonicalisation procedure (§12/§15)

`canonical_bytes(obj) = json.dumps(obj, sort_keys=True, separators=(",",":"), ensure_ascii=False,
allow_nan=False).encode("utf-8")`. `content_digest = "sha256:" + sha256(canonical_bytes)`. The three
bound digests are `subject_digest = digest(subject)`, `payload_digest = digest(payload)`, and
`content_digest = digest(envelope with integrity.{subject_digest,payload_digest,content_digest,signature,
verification_status} blanked)` — making the content digest independent of the derived fields and stable
between sealing and validation. Determinism is asserted by `test_30`.

## 9. Reason-code taxonomy (§20)

Stable codes (all in `es.REASON_CODES`): `EVIDENCE_MISSING`, `SCHEMA_VERSION_UNSUPPORTED`,
`SCHEMA_MALFORMED`, `EVIDENCE_TYPE_INVALID`, `STATUS_NOT_VALID`, `EVIDENCE_EXPIRED`,
`EVIDENCE_NOT_YET_VALID`, `EVIDENCE_REVOKED`, `INSTANCE_MISMATCH`, `SCENE_MISMATCH`, `ROUTE_MISMATCH`,
`CONFIG_MISMATCH`, `FRAME_MISMATCH`, `BOUND_MISMATCH`, `DIGEST_MISMATCH`, `SIGNATURE_UNVERIFIED`,
`VALIDITY_WINDOW_MISMATCH`, `DUPLICATE_EVIDENCE_ID`, `FIXTURE_IN_PRODUCTION`, `PAIR_INCOMPLETE`,
`PAIR_BINDING_MISMATCH`, `PAIR_WINDOW_DISJOINT`, `ACCEPTED`.

## 10. Structured validation result (§19)

`validate_envelope`/`validate_pair` return: `accepted`, `reason_code`, `explanation`, `evidence_id`,
`instance_id`, `evidence_type`, `failed_field`, `expected`, `observed`, `schema_version`,
`validator_version`. Diagnostics never expose secrets or full sensitive payloads.

## 11. Conformance validator (§18) — what it may / must not do

**May:** parse the schema; validate field types/enums; validate identity bindings; validate time using
an **injected** review time; recompute/compare digests for synthetic fixtures; pair render+drive; return
structured rejection reasons. **Must not (and does not import):** Isaac, ROS 2, a camera, a robot, a
policy/model, dataset directories, RGB images, trajectories, rosbags, a real provider, or a capture
backend. `test_24`/`test_25` assert no filesystem output and no forbidden imports.

## 12. Threat model (§15)

| # | Threat | Mechanism | Impact | Prevention | Detection | Residual / future dependency |
|---|--------|-----------|--------|------------|-----------|------------------------------|
| 1 | Evidence replay | Re-present old valid evidence | Capture on stale state | validity window + `max_age` + duplicate-id set | `EVIDENCE_EXPIRED`/`DUPLICATE_EVIDENCE_ID` | trusted clock (`H8-C-008`) |
| 2 | Stale reuse | Use evidence past freshness | Capture on outdated render/route | `not_after`/`max_age_seconds` | `EVIDENCE_EXPIRED` | trusted clock |
| 3 | Cross-instance substitution | Evidence from another instance | Wrong instance certified | `expected.instance_id` binding | `INSTANCE_MISMATCH` | caller supplies correct `expected` |
| 4 | Cross-scene substitution | Different scene's evidence | Wrong scene certified | `scene_id` + `scene_digest` binding | `SCENE_MISMATCH` | real digest (`H8-C-011`) |
| 5 | Route substitution | Different route's evidence | Wrong route certified | `route_id` + `route_plan_digest` | `ROUTE_MISMATCH` | real digest |
| 6 | Configuration drift | Evidence under a different config | Unsafe config captured | `config_digest` binding | `CONFIG_MISMATCH` | real digest |
| 7 | Scene-asset mutation | Scene changed after evidence | Evidence no longer valid | `scene_digest` + revocation-on-change policy | `SCENE_MISMATCH`/`EVIDENCE_REVOKED` | change-detection producer |
| 8 | Forged producer identity | Fake producer | Untrusted evidence trusted | signature fields + `require_signature` | `SIGNATURE_UNVERIFIED` | real key mgmt (`H8-C-009`) |
| 9 | Payload modification | Tamper payload | False render/drive claim | `payload_digest` | `DIGEST_MISMATCH` | — |
| 10 | Subject/context modification | Tamper bindings | Rebind evidence | `subject_digest`/`content_digest` | `DIGEST_MISMATCH` | — |
| 11 | Signature failure | Bad/absent signature | Unauthentic evidence | `require_signature` → only `verified` | `SIGNATURE_UNVERIFIED` | real verification |
| 12 | Revoked reuse | Use revoked evidence | Capture on withdrawn evidence | `revocation.revoked`/`status` | `EVIDENCE_REVOKED` | live revocation distribution |
| 13 | Duplicate evidence id | Two records, same id | Ambiguous provenance/replay | `seen_ids` set | `DUPLICATE_EVIDENCE_ID` | durable id store |
| 14 | Conflicting valid records | Two "valid" for one slot | Ambiguity | per-instance binding + duplicate-id | mismatch/duplicate codes | selection policy (future) |
| 15 | Partial evidence pair | Only render or only drive | Half-verified capture | `validate_pair` both-required | `PAIR_INCOMPLETE` | — |
| 16 | Clock manipulation | Skewed/absent tz | Freshness bypass | tz-required + injected review time + skew bound | `SCHEMA_MALFORMED`/window codes | trusted clock |
| 17 | Unsupported schema version | Send off-version record | Bypass new checks | `SUPPORTED_SCHEMA_VERSIONS` | `SCHEMA_VERSION_UNSUPPORTED` | migration policy (`H8-C-012`) |
| 18 | Downgrade to weaker version | Force old schema | Weaker validation | strict supported-set (no ranges) | `SCHEMA_VERSION_UNSUPPORTED` | migration policy |
| 19 | Permissive unknown fields | Smuggle extra fields | Silent contract drift | strict top-level key set + `additionalProperties:false` | `SCHEMA_MALFORMED` | — |
| 20 | Fixture accepted in production | Test fixture reaches prod | Fake evidence trusted | `FIXTURE_PRODUCER` sentinel + `production_mode` | `FIXTURE_IN_PRODUCTION` | provider marks real producer |

## 13. Synthetic fixtures (§17) & conformance report

Fixtures are built in-code by `synthetic_render_evidence` / `synthetic_drive_evidence` /
`synthetic_paired_evidence`, each marked with the `synthetic-test-fixture` producer sentinel and
**not** written to any capture-output directory. Negative fixtures are derived by dotted-path overrides.
Coverage (positive + every negative class) is exercised by `tests/gnm/test_h8_evidence_schema.py`.

**Conformance result (this gate):** `python -m pytest tests/gnm/test_h8_evidence_schema.py` →
**34 passed**. Recorded-mode regression `tests/gnm/test_h8_synthetic_fork_recorded_mode.py` →
**58 passed**. `py_compile` on all changed Python files → OK. Ruff → **unavailable** (`H8-C-013`).

## 14. Requirements traceability (§25)

| Requirement | Schema field(s) | Validator | Positive fixture | Negative fixture | Test | Status |
|---|---|---|---|---|---|---|
| Versioned envelope, no downgrade | `schema_version` | step-1 | default | `schema_version=0.9.0` | 11 | ✅ |
| Strict unknown-field | top-level keys | step-2 | default | `unexpected_field` | 22 | ✅ |
| Evidence type constrained | `evidence_type` | step-2 | render/drive | pair type check | 1,2,`extra_pair` | ✅ |
| Status only-valid | `status` | step-5 | valid | invalid/indeterminate | 6,7 | ✅ |
| Revocation blocks | `revocation`/`status` | step-5 | not revoked | revoked | 8 | ✅ |
| Identity binding | `subject.*` | step-6/10 | matched `expected` | instance/scene/route/config/frame | 13–17 | ✅ |
| CL_BOUND_XY bound | `subject.cl_bound_xy` | step-7 | 6.0 | 7.0 | 18 | ✅ |
| Integrity digests | `integrity.*_digest` | step-8 | sealed | tampered-after-seal | 19 | ✅ |
| Signature policy | `integrity.verification_status` | step-8 | verified | unverified + `require_signature` | `extra_sig` | ✅ |
| Freshness window | `validity_window` | step-9 | in-window | expired / future / bad-order | 9,10,20 | ✅ |
| Timestamp format | time fields | `_parse_ts` | UTC-Z | malformed / naive | 12 | ✅ |
| Duplicate id | `evidence_id` + `seen_ids` | step-3 | unique | duplicate | 21 | ✅ |
| Fixture-in-production | `producer.component` | step-4 | prod producer | fixture sentinel | `extra_fixture` | ✅ |
| Pairing | shared bindings + window | `validate_pair` | matched pair | missing / mismatch | 3,4,5,`extra_pair` | ✅ |
| Canonicalisation deterministic | canonical JSON | `canonical_bytes` | reorder-equal | — | 30 | ✅ |
| Structured reasons | result shape | `_result` | — | any rejection | 23 | ✅ |
| No output / no forbidden import | — | module | — | — | 24,25 | ✅ |
| Level-1 preserved | — | — | — | — | 27 | ✅ |
| Recorded-mode unperturbed | — | — | — | — | 26,28 | ✅ |
| Empty-plan graceful (F-003) | harness guard | `dataset_dry_run_checks` | — | empty plan | 29 | ✅ |

**Traceability: 20/20 requirements mapped (100%).**

## 15. Evidence boundary (§27)

**Establishes:** schema validity; conformance-validator validity over synthetic fixtures; identity-binding
policy; freshness and revocation policy *definitions*; deterministic synthetic digest verification.
**Does NOT establish:** truthful real render/drive evidence; a trusted producer; a trusted clock;
operational key management; live revocation distribution; Isaac runtime validity; captured-dataset
validity; model validity. Schema-valid synthetic fixtures are **not** Level-3 runtime evidence.

## 16. KPIs (§28)

| KPI | Target | Result |
|---|---|---|
| Schema requirement coverage | 100% | 100% (20/20) |
| Traceability coverage | 100% | 100% |
| Defined negative-fixture rejection | 100% | 100% |
| Valid synthetic fixture acceptance | 100% | 100% |
| Identity-mismatch rejection | 100% | 100% |
| Time-policy rejection | 100% | 100% |
| Integrity-failure rejection | 100% | 100% |
| Structured-reason coverage | 100% | 100% |
| Level-1 hash preservation | 5/5 | 5/5 |
| Recorded-mode regression pass rate | 100% | 100% (58/58) |
| Pilot regression pass rate | 100% where affected | 100% (unmodified) |
| Boundary violations | 0 | 0 |
| Ruff | Pass or explicitly Open | **Open** (unavailable) |

## 17. Limitations & next gate

Open items carried forward: trusted clock (`H8-C-008`), real signature/key management (`H8-C-009`,
`H8-C-005`), scene-evidence reuse policy (`H8-C-010`), real digest truthfulness (`H8-C-011`), schema
migration policy (`H8-C-012`), Ruff (`H8-C-006`/`H8-C-013`). **Real hospital dataset capture remains
blocked.**

**Next authorised gate:** the **evidence-provider implementation gate** — implement a real (initially
still non-capturing) provider that emits envelopes conforming to this schema over real scene/route/config
artefacts, then an independent provider review, then a separately reviewed Isaac backend / runtime-validity
gate, then explicit capture authorisation. Scientific progression:
`validated capture plan → validated no-Isaac capture path → independent review → bounded remediation →
evidence schema → evidence provider → provider review → Isaac backend/runtime validation → explicit
collection approval → hospital footage & trajectory collection`.
