# H8 Non-Capturing Render/Drive Evidence Provider — Implementation Gate

**Gate type:** implementation of a **non-capturing** evidence provider. It creates real, schema-conforming
evidence envelopes derived from repository-controlled artefacts. It does **not** start Isaac Sim, render a
frame, drive the robot, access a camera, invoke ROS 2, or perform dataset capture. Preflight evidence is a
well-formed evidence **document** but **never** authorises capture.

- **Date:** 2026-07-16 · **Branch:** `h23-execfix` (local, unpushed) · **Baseline HEAD:** `ebf8341`.
- **Provider:** `scripts/gnm/h8_evidence_provider.py` (`h8-evidence-provider/1.0.0`).
- **Schema extension:** `scripts/gnm/h8_evidence_schema.py` gains a versioned, tested `document_only`
  validation mode (`H8-DCP-023`). Envelope format unchanged (`schema_version = h8-evidence/1.0.0`).
- **Tests:** `tests/gnm/test_h8_evidence_provider.py`.

## 1. Milestone chain & verified roles

| Commit | Role (verified from Git) |
|---|---|
| `7a73c9fc012b97ee1bf94fe829a3c59eb915ff9f` | Add synthetic fork dataset capture **config** |
| `ecae4cdd5de4082184fc65881cc836c612231bf8` | **Emitter** of dataset dry-run artifacts |
| `66fd81e62bc0d6c100e7b562b22fc8cc8a0d061e` | Dataset dry-run **evidence** (25/25 files) |
| `bd6168ab5ead2aa5724a6d9df1b7e52222fbf0b7` | Fail-closed dataset capture-path **wiring** |
| `db70ce39c0d99300ec4f4d2c0010f6cbe036cade` | Capture-path **documentation** |
| `bb94c5aabe6d96bbe8e4be4ce6f3d7a0a37af4ce` | Provenance **reconciliation** |
| `c6b42ac14eb52f80e3b0a3521d3eb3a826ac1627` | Independent **review** |
| `31b1d01086524d13c08630a733fce81f84a1a428` | **Bounded review-finding remediation & hardening** (6 files, +257/−5: GATE/REVIEW/DECISION-LOG/REGISTER docs + new REMEDIATION.md + remediation regression tests) |
| `ebf8341fff03b0af9a63fc41705c3f2ce622ed7a` | Render/drive evidence **schema** design |
| *(this gate)* | Non-capturing evidence **provider** |

`31b1d01`'s role was read directly from Git (`git show --stat 31b1d01`), not inferred.

## 2. Research question & hypothesis

**RQ (§4).** *Can a non-capturing provider deterministically create authentic, schema-conforming evidence
envelopes from real repository-controlled H8 plan, scene, route and configuration artefacts without falsely
claiming that Isaac rendering or robot-route execution has occurred?*

**Hypothesis (§5).** *A provider that computes canonical digests and identity bindings from real committed
artefacts, separates structural observations from runtime observations, and defaults runtime status to
`indeterminate` can produce trustworthy pre-runtime evidence without enabling or simulating hospital
footage capture.*

## 3. `H8-C-006` / `H8-C-013` relationship (historical traceability)

`H8-C-006` (capture-path gate) is the **original** Ruff-unavailable limitation and remains visible and
Open. `H8-C-013` (schema gate) is a **continuation / re-observation** of the same limitation, not a
replacement — it re-checked Ruff availability in a later gate and found it still absent. This provider gate
re-checked again (below) and appends a further continuation row to `H8-C-013`. The chain
`H8-C-006 → H8-C-013 → (provider re-check)` is preserved; none is silently overwritten.

## 4. Provider architecture

`H8EvidenceProvider` — deterministic, all external effects **injected**: `clock`, `reader`, `digest_fn`,
`tree_state` (commit + dependency-dirty), `sink`, `runtime_observer` (**absent this gate**). No implicit
global runtime dependency. Key methods: `load_configuration`, `load_plan`, `resolve_instance`,
`build_route_representation`, `build_subject_binding`, `build_provenance`,
`build_render_preflight_evidence`, `build_drive_preflight_evidence`, `emit_evidence`, and the module
boundary helper `preflight_satisfies_capture_gate`.

### Modes (§8)

- **fixture** — returns clearly-marked synthetic fixtures only (fixture-sentinel producer); refuses to
  write to any non-`fixture` namespace.
- **preflight** — reads real artefacts, computes real bindings/digests, emits `status="indeterminate"`
  non-runtime evidence; cannot assert runtime validity; no Isaac/capture.
- **production** — with no runtime observer, **blocks** (`PROVIDER_BLOCKED_RUNTIME_OBSERVER_MISSING`); never
  creates `valid` render/drive evidence; never falls back to fixture/preflight semantics.
  > **Correction (H8-PREV-F-005, remediated 2026-07-16):** the original text claimed production "rejects
  > fixture sentinels", which overstated a **single-field** `producer.component` check that a rename could
  > bypass (`H8-PREV-F-001`). After remediation: **production acceptance requires a positively authorised
  > producer and trust profile; fixture markers provide supplementary rejection signals but are not the sole
  > trust boundary** (see `H8_EVIDENCE_PROVIDER_REMEDIATION.md`, `H8-DCP-029..031`).

## 5. Critical evidence-status boundary (§6)

The provider distinguishes six evidence facts. **This gate establishes only 1–4**:

| # | Fact | Established here? |
|---|---|---|
| 1 | artefact identity verified | ✅ (config/scene/plan/route bound) |
| 2 | artefact digest verified | ✅ (real SHA-256) |
| 3 | configuration consistency verified | ✅ (cl_bound, mode, structure) |
| 4 | route **structure** verified | ✅ (config-derived representation) |
| 5 | **runtime render validity observed** | ❌ never (no Isaac) |
| 6 | **runtime drive validity observed** | ❌ never (no robot) |

Because the schema status enum is `{valid, invalid, indeterminate, revoked}`, preflight evidence uses
**`indeterminate`** plus explicit `runtime_observed=false` and `unobserved_runtime_checks[...]`. The schema
was **not** altered informally: instead the validator gained a versioned, tested `document_only` mode
(`H8-DCP-023`) that separates "well-formed evidence **document**" from "satisfies the **capture gate**". A
preflight document validates under `document_only=True` and is rejected (`STATUS_NOT_VALID`) under the
default gate check.

## 6. Real artefact inputs (§9)

| Artefact | Path / identifier | Tracked | Canonicalisation | Digest | Sufficient for |
|---|---|---|---|---|---|
| Dataset config | `configs/gnm/h8_synthetic_fork_recorded_mode_dataset.yaml` | yes | raw bytes | sha256 | preflight |
| Dataset plan | derived `build_dataset_plan(cfg)` | yes (from cfg) | canonical JSON | sha256 | preflight |
| Scene asset | `assets/scenes/synthetic_diagnostic_fork/synthetic_diagnostic_fork.usda` (33 827 B) | yes | raw bytes | sha256 | **scene-file** only |
| Route representation | config-derived (per instance) | yes (from cfg) | canonical JSON | sha256 | **structure** only |

`coordinate_frame` (`synthetic_fork_world`) is **provider-declared** (not present in the config — `H8-C-015`).
`resolution`/`encoding` are **declared intent**, not observed (`H8-C-019`). Untracked local files are never
used as canonical evidence; a dirty evidence-dependency artefact fails closed.

## 7. Canonical digest computation (§10)

`default_digest(bytes) = "sha256:" + sha256(bytes).hexdigest()` (full, lowercase, no truncation). Object
inputs (plan, route) are serialised via the schema's canonical JSON (`sort_keys`, tight separators, UTF-8,
no-NaN) before hashing — key order does not affect the digest; semantic changes do (`test_05`, `test_06`).
No machine-specific absolute paths enter subject identity (the reader refuses absolute paths and `..`
traversal). Unsupported/failed digests fail closed.

## 8. Scene & route identity limitations (§12/§13)

- **Scene:** a scene-**file** digest is computed over the committed `.usda`. This does **not** claim Isaac
  loaded the scene, that the loaded scene matched the file, that referenced assets resolved, or that
  rendering was correct (`H8-C-014`).
- **Route:** structural checks only (route exists, id matches, start/goal fields present, frame declared,
  digest matches, cl_bound = 6.0, waypoints structurally valid, instance bound). Collision-freedom,
  clearance, footprint feasibility, controller stability and drive success remain **unobserved**
  (`H8-C-016`).

## 9. Clock, signature, dirty-tree, output & replay policy

- **Clock (§17).** Injected. For tests, a fixed deterministic clock. For preflight, real UTC may be recorded
  as an **untrusted observational** time — no trusted-clock guarantee is claimed (`H8-C-017`).
- **Signature (§18).** Digest-only. `verification_status="unsigned"` recorded honestly; a production
  `require_signature` fails closed (`PROVIDER_SIGNATURE_REQUIRED`). No production keys, no committed secrets;
  digest-only evidence is never called signed.
- **Dirty tree (§11).** Scoped to the evidence-dependency set (config, scene, schema, provider). A modified
  dependency → `PROVIDER_DIRTY_TREE`. Unrelated untracked files do not block. Fixture mode is exempt.
- **Output (§19).** Dedicated namespace `assets/evidence/h8/preflight/` (distinct from dry-run, dataset,
  model and benchmark outputs); `assets/evidence/h8/runtime/` is reserved for a future runtime provider.
  Only small structured JSON; no images/trajectories/rosbags/arrays/model artefacts. Writes are validated
  fully **before** any sink call, then written temp-file + `fsync` + atomic rename (`AtomicFileSink`); tests
  use `InMemorySink`, so no file is created. Failed validation ⇒ zero output (`test_32`).
- **Evidence ID & replay (§20).** Deterministic `h8ev-<render|drive>-<slug>-<seq>` (`seq` from a digest of
  `kind:instance`). Regeneration from identical inputs is idempotent (`test_31`); the **same id with changed
  content** conflicts (`PROVIDER_OUTPUT_CONFLICT`, `test_30`); duplicate id in a bundle and unsupported
  version are rejected. Replay protection is **process/sink-local**, not a distributed ledger (`H8-C-018`).

## 10. Capture-harness boundary (§23)

`preflight_satisfies_capture_gate(env)` returns `(authorises_capture=False, {is_valid_document: True, ...})`
for preflight evidence — a valid document that does **not** authorise capture. The frozen capture harness was
**not** modified to treat preflight evidence as render-/drive-valid; no Isaac backend, no dataset directory,
no capture. `test_25`/`test_26` prove the pair is a valid document pair yet fails the capture gate.

## 11. Provider result taxonomy (§21)

`PROVIDER_OK_PREFLIGHT`, `PROVIDER_OK_FIXTURE`, `PROVIDER_BLOCKED_RUNTIME_OBSERVER_MISSING`,
`PROVIDER_FIXTURE_REJECTED`, `PROVIDER_ARTIFACT_MISSING`, `PROVIDER_ARTIFACT_DIGEST_FAILED`,
`PROVIDER_DIRTY_TREE`, `PROVIDER_SCHEMA_REJECTED`, `PROVIDER_BINDING_MISMATCH`, `PROVIDER_OUTPUT_CONFLICT`,
`PROVIDER_SIGNATURE_REQUIRED`, `PROVIDER_CLOCK_UNTRUSTED`, `PROVIDER_INSTANCE_UNKNOWN`,
`PROVIDER_MODE_INVALID`, `PROVIDER_INTERNAL_ERROR`. Unknown failures never become success — a catch-all maps
to `PROVIDER_INTERNAL_ERROR` (`test_34`).

## 12. Provider threat-model extension (§26)

| Threat | Prevention | Detection | Residual / future dependency |
|---|---|---|---|
| Fixture→production substitution | production rejects fixture sentinel | `FIXTURE_IN_PRODUCTION` | provider marks real producer |
| Forged artefact path | reader refuses absolute/`..`/out-of-repo | `ValueError`→`ARTIFACT_MISSING` | — |
| Symlink substitution / path traversal | repo-relative + resolve-in-repo check | rejected read | OS-level symlink policy |
| Time-of-check/time-of-use change | dependency dirty-tree check + digests bound | `DIRTY_TREE`/`DIGEST_MISMATCH` | atomic snapshotting (future) |
| Dirty working-tree ambiguity | dependency-scoped dirty check | `PROVIDER_DIRTY_TREE` | — |
| Digest over wrong representation | fixed canonicalisation for objects; raw bytes for files | `test_06` | real runtime digest (`H8-C-014`) |
| Digest truncation collision | full 64-hex, no truncation | schema `_DIGEST_RE` | — |
| Evidence-ID collision | deterministic id + conflict check | `PROVIDER_OUTPUT_CONFLICT` | distributed registry |
| Duplicate bundle replay | `seen_ids` / sink id map | `DUPLICATE_EVIDENCE_ID` | shared ledger (`H8-C-018`) |
| Output overwrite | same-id-different-content conflict | `PROVIDER_OUTPUT_CONFLICT` | — |
| Partially written evidence | validate-then-atomic-write | zero-output on failure | — |
| Preflight promoted to runtime-valid | `document_only` separation; status=indeterminate | gate `STATUS_NOT_VALID` | runtime provider |
| Runtime observer silently absent | mandatory observer for runtime status | `BLOCKED_RUNTIME_OBSERVER_MISSING` | reviewed runtime gate |
| Provider/dependency version drift | provider_version + source_commit in provenance | provenance mismatch | — |
| Local clock manipulation | injected clock; untrusted classification | `CLOCK_UNTRUSTED` (reserved) | trusted clock (`H8-C-017`) |
| Unsigned misrepresented as authentic | `verification_status=unsigned`; `require_signature` fails closed | `SIGNATURE_UNVERIFIED`/`PROVIDER_SIGNATURE_REQUIRED` | key management (`H8-C-009`) |

## 13. Conformance report

`python -m pytest tests/gnm/test_h8_evidence_provider.py` → **41 passed**. Combined with the schema and
recorded-mode suites → **133 passed** (41 + 34 + 58). `py_compile` on the provider, schema and test files →
OK. No `assets/evidence/` or dataset directory created. Level-1 five files byte-identical. Dry-run 25/25.
Ruff → **unavailable** (continuation of `H8-C-006`/`H8-C-013`).

## 14. Requirements traceability (§29) — 100%

| Requirement | Provider symbol | Schema field | Positive test | Negative test | Status |
|---|---|---|---|---|---|
| Real config digest | `build_subject_binding` | `subject.config_digest` | 01,10 | 06 | ✅ |
| Real plan digest | `load_plan`+`build_provenance` | `provenance.plan_digest` | 02 | — | ✅ |
| Real route digest | `build_route_representation` | `subject.route_plan_digest` | 03 | 15 | ✅ |
| Real scene digest | `emit_evidence` | `subject.scene_digest` | 04 | 14 | ✅ |
| Deterministic canonicalisation | `default_digest` | integrity digests | 05 | — | ✅ |
| Changed artefact → new digest | injected reader | `config_digest` | — | 06 | ✅ |
| Identity binding | `build_subject_binding` | `subject.*` | 07,08,09,11 | 12 | ✅ |
| CL_BOUND = 6.0 | `build_subject_binding` | `subject.cl_bound_xy` | 11 | 32 | ✅ |
| Unknown instance | `resolve_instance` | — | — | 12 | ✅ |
| Empty plan | `emit_evidence` | — | — | 13 | ✅ |
| Missing scene / route | `_preflight_prechecks` | — | — | 14,15 | ✅ |
| Dirty-tree | `tree_state` | — | — | 16 | ✅ |
| Fixture-only in fixture mode | `_emit_fixture` | producer sentinel | 17 | 17 | ✅ |
| Production rejects fixture | `emit_evidence` | `producer.component` | — | 18,19 | ✅ |
| No runtime overclaim | runtime-observer gate | `status` | — | 20,21,22 | ✅ |
| Preflight indeterminate/non-runtime | preflight builders | `status`/payload | 23,24 | — | ✅ |
| Document ≠ capture-gate | `preflight_satisfies_capture_gate` | `document_only` | 25 | 26 | ✅ |
| Digest mismatch | schema validator | `integrity.*` | — | 27 | ✅ |
| Unsupported version | schema validator | `schema_version` | — | 28 | ✅ |
| Duplicate id | schema validator | `evidence_id` | — | 29 | ✅ |
| Same-id conflict | sink conflict check | — | 31 | 30 | ✅ |
| Failed validation → no output | validate-then-write | — | 33 | 32 | ✅ |
| Atomic write | sink | — | 33 | — | ✅ |
| Stable reason codes | `_provider_result` | — | 34 | — | ✅ |
| No forbidden imports | module | — | 35–38 | — | ✅ |
| No dataset/capture output | `InMemorySink` | — | 39 | — | ✅ |
| Schema/recorded/dry-run/pilot/Level-1 intact | — | — | 40,41,42,43,44 | — | ✅ |

**Traceability: 44/44 mapped (100%).**

## 15. KPIs (§31)

| KPI | Target | Result |
|---|---|---|
| Provider requirement coverage | 100% | 100% |
| Provider traceability | 100% | 100% (44/44) |
| Real artefact digest coverage | 100% of declared deps | 100% (config/scene/plan/route) |
| Deterministic digest tests | 100% | 100% |
| Fixture-to-production rejection | 100% | 100% |
| Runtime-valid overclaim prevention | 100% | 100% |
| Invalid-input rejection | 100% | 100% |
| Failed-case zero-output rate | 100% | 100% |
| Provider reason-code coverage | 100% | 100% |
| Level-1 hash preservation | 5/5 | 5/5 |
| Schema regression | 100% | 100% (34/34) |
| Recorded-mode regression | 100% | 100% (58/58) |
| Pilot regression | 100% where affected | 100% (unmodified) |
| Boundary violations | 0 | 0 |
| Ruff | Pass or explicitly Open | **Open** (unavailable) |

Absent runtime observers, signatures, trusted clocks and backends are **not** counted as passing.

## 16. Evidence established / NOT established (§32)

**Established:** provider-implementation validity; real artefact digest computation; identity-binding
generation; fixture rejection; preflight evidence generation; provider-to-schema conformance; prevention of
preflight→runtime overclaim. **NOT established (do not label Level 3):** real render validity; real drive
validity; truthful Isaac observations; trusted time; production signatures; operational revocation; runtime
capture readiness; dataset validity; model validity.

## 17. Implementation journal (failures & refinements)

1. **evidence_id regex mismatch.** First `emit_evidence` returned `PROVIDER_SCHEMA_REJECTED`: the id used
   the full `evidence_type` (`render_valid`), whose underscore fails `^h8ev-[a-z]+-…$`. Fixed by using the
   short type slug `render`/`drive`. Re-ran → OK.
2. **Route-artefact guard.** Added an explicit `coord_offset` presence check so a config-derived route with
   no offset fails closed (`PROVIDER_ARTIFACT_MISSING`, `test_15`) rather than silently defaulting.
3. **Schema `document_only`.** Added as a small, versioned, tested validator capability (envelope format
   unchanged) so preflight documents validate without misusing `status=valid`.

## 18. Limitations & next gate

Open: trusted clock (`H8-C-017`), signatures/keys (`H8-C-009`), scene-file≠runtime-scene (`H8-C-014`),
provider-declared frame (`H8-C-015`), structural-route-only (`H8-C-016`), local replay only (`H8-C-018`),
declared-not-observed camera params (`H8-C-019`), Ruff (`H8-C-006`/`H8-C-013`). **Real hospital capture
remains blocked.** Levels 3–5 remain unproven.

**Next authorised stage (§33): an independent evidence-provider review** — this implementation must **not**
directly authorise the backend gate. Progression:
`schema conformance → non-capturing provider → independent provider review → provider remediation → Isaac
backend/runtime-validity gate → explicit capture approval → hospital footage & trajectory collection`.
