# H8 Isaac Backend and Runtime-Validity Architecture (Design Gate)

**Gate:** `H8 Isaac Backend and Runtime-Validity Architecture Design Gate` — architecture, interface,
threat-model, policy and test-harness **design only**. **Date:** 2026-07-16. **Branch:** `h23-execfix`.

**Boundary honoured (nothing executed):** no Isaac Sim launch, no Omniverse Kit init, no ROS 2 nodes, no
rendered frames, no robot motion, no RGB images / trajectories / rosbags / recorded-mode dataset, no
GNM/policy/action-probe/training/20-5-10/closed-loop, no push/tag/promotion/release, no capture
authorisation. This document specifies *what will be built and how it must fail closed* — it does not build
it and does not claim Isaac currently satisfies it. All interfaces below are **design specifications**; no
runtime code is committed in this gate (see `H8-DCP-045`).

## 0. Position in the evidence programme

Verified today: Level-1 plan validity, Level-2 fail-closed capture-path validity, schema-conformance
validity, non-capturing evidence-provider validity, independent closure of the provider trust-boundary
findings (`PASS WITH DOCUMENTED LIMITATIONS`), and **backend-design eligibility**. Not established:
Level-3 runtime, Level-4 dataset, Level-5 model validity; render-valid hospital footage; drive-valid
hospital routes; capture authorisation.

Programme state:
`provider trust re-review passed → **backend/runtime architecture design (this gate)** → Git resolver →
trust infrastructure → observer stubs → disabled Isaac worker → controlled runtime validation → explicit
capture authorisation → hospital footage & trajectory collection`.

## 1. Gate objective (§1)

Design a fail-closed Level-3 runtime architecture that can *later*: (1) launch the approved Isaac hospital
scene under an explicit execution gate; (2) verify the exact scene/robot/camera/route/configuration loaded
at runtime; (3) generate truthful render-valid and drive-valid evidence via approved runtime observers;
(4) bind runtime observations to the existing plan/instance/scene/route/config/provider identities;
(5) prevent preflight or `document_only` evidence from authorising capture; (6) block capture unless both
runtime render-valid and drive-valid evidence are current, authentic, non-revoked and correctly paired;
(7) terminate safely and create no dataset artefacts on any prerequisite failure; (8) preserve the existing
pilot path, dry-run evidence and Level-1/Level-2 guarantees.

## 2. Scientific question (§2)

> What runtime architecture and trust controls are necessary to establish truthful render-valid and
> drive-valid evidence for one H8 Isaac Sim hospital capture instance without allowing stale, forged,
> mismatched, preflight-only or partially observed evidence to authorise footage and trajectory collection?

## 3. Hypothesis (§3, falsifiable)

> A staged runtime architecture using a reviewed Git dependency resolver, authenticated runtime-observer
> contracts, trusted timestamping, signed evidence envelopes, revocation checking, exact runtime identity
> binding and a two-phase capture-authorisation protocol can fail closed before dataset output whenever the
> loaded Isaac scene, route, camera, robot, configuration or runtime evidence differs from the approved H8
> plan.

This gate evaluates whether the architecture can **express and test** these guarantees. It does **not**
establish that Isaac currently satisfies them.

## 4. Existing seams this design reuses (not re-invents)

The runtime architecture plugs into constructs that already exist and are reviewed:

| Existing construct | File | Role in runtime design |
|---|---|---|
| `run_dataset_capture(args, cfg, evidence_provider=None, capture_backend=None)` | `h8_synthetic_fork_recorded_mode.py:1079` | The **writer is already a separable DI slot**: `capture_backend=None → rc3, captures nothing`. The runtime worker is **not** the writer. |
| `dataset_instance_validity_gate(cfg, evidence_provider)` | `…recorded_mode.py:950` | Consumes evidence from an injected provider; runtime evidence (render+drive pair) feeds here. Default is `null_evidence_provider` (no evidence → blocked). |
| `plan_dataset_capture` → gate → readiness | `…recorded_mode.py:1058` | Plan/authorise vs execute separation — the seed of two-phase authorisation. |
| `precheck_scene_identity()` / `scene_identity_spec()` | `h8_synthetic_fork_drive_validate.py:171` | Seed of the **Runtime Identity Inspector** (`scene_identity_pass`, `observed_prim_count`). |
| `refuse_forbidden_modes(args)` | `…drive_validate.py:291` | Existing fail-closed mode guard the worker inherits. |
| `EVIDENCE_DEPENDENCY_PATHS`, `check_production_trust`, `validate_runtime_observer`, `_parse_ts` | `h8_evidence_provider.py`, `h8_evidence_schema.py` | Dependency closure, positive producer trust, typed observer contract, injected-clock parsing — all extended, none replaced. |

**Reconciliation principle:** runtime evidence uses the SAME `EvidenceEnvelope` schema (`h8-evidence/1.0.0`),
the SAME positive producer-trust policy, the SAME typed observer contract, and the SAME `document_only`
capture-gate distinction. Runtime adds *new producers, new observers, new statuses and a capture-authorisation
protocol* — it introduces **no** parallel evidence format and **no** weaker path.

## 5. Concrete Git dependency resolver — resolving `H8-PRREV-F-002` (§5)

The re-review's key deferred dependency: the provider trusts an injected `dependency_dirty` boolean but **no
concrete resolver exists**. This gate specifies one (implementation is the first future gate, `G1`).

### 5.1 Interface (design)

```text
GitDependencyResolver.resolve(closure: DependencyClosure, expected_commit: str, repo_root: Path)
  → DependencyResolution {
        clean: bool,                     # True ONLY if every dependency affirmatively clean
        commit: str,                     # resolved HEAD (or DETACHED marker)
        closure_digest: "sha256:…",      # digest over (path, blob_sha, mode) sorted — binds the whole set
        per_path: [{path, state, tracked, blob_sha, reason}],
        reason_code: str,                # CLEAN | one of the fail-closed codes below
        resolver_version: str,
    }
```

`clean` is `True` **iff** every path is `TRACKED_CLEAN` and inside the closure; any other per-path state,
any ambiguity, any tool error → `clean=False` with a specific reason code. There is no override.

### 5.2 Per-path state → decision (all non-clean states fail closed)

| Detected state | Decision | Reason code |
|---|---|---|
| tracked, unmodified, expected repo | **CLEAN** | `CLEAN` |
| staged modification | BLOCK | `DEP_STAGED_MODIFICATION` |
| unstaged modification | BLOCK | `DEP_UNSTAGED_MODIFICATION` |
| deleted | BLOCK | `DEP_DELETED` |
| renamed / moved | BLOCK | `DEP_RENAMED` |
| untracked replacement at a closure path | BLOCK | `DEP_UNTRACKED_REPLACEMENT` |
| ignored file used as a dependency | BLOCK | `DEP_IGNORED_DEPENDENCY` |
| symlink (unexpected) | BLOCK | `DEP_SYMLINK` |
| submodule pointer | BLOCK | `DEP_SUBMODULE` |
| Git LFS pointer (content absent) | BLOCK | `DEP_LFS_POINTER` |
| detached HEAD | BLOCK | `DEP_DETACHED_HEAD` |
| shallow clone (history incomplete) | BLOCK | `DEP_SHALLOW_CLONE` |
| missing `.git` | BLOCK | `DEP_NO_GIT` |
| `git` command failure / nonzero exit | BLOCK | `DEP_GIT_COMMAND_FAILED` |
| repository identity mismatch (wrong remote/root) | BLOCK | `DEP_REPO_MISMATCH` |
| path escapes / outside repository | BLOCK | `DEP_OUTSIDE_REPO` |
| declared `expected_commit` ≠ resolved HEAD | BLOCK | `DEP_COMMIT_MISMATCH` |
| any unlisted/ambiguous state | BLOCK | `DEP_INDETERMINATE` |

### 5.3 Dependency closure (minimum set, §5)

`DependencyClosure` = the union of: H8 dataset configuration; dataset plan; plan manifest; split definition;
evidence schema; evidence-provider implementation; canonicalisation code; digest code; producer trust
policy; runtime-observer policy; Isaac backend implementation; scene reference/scene file; route artefact;
coordinate frame; `coord_offset`; robot configuration; camera configuration; runtime evidence policy;
revocation policy; signature policy; clock policy. Concretely this **supersedes and extends** the current
`EVIDENCE_DEPENDENCY_PATHS` (config, scene `.usda`, `h8_evidence_schema.py`, `h8_evidence_provider.py`) with
the runtime files listed in §29. The resolver emits a `closure_digest` that later binds into runtime
identity (§10) so a changed closure invalidates all downstream evidence.

## 6. Runtime state machine (§6)

```text
BLOCKED
  ↓ preflight document valid + producer authorised + closure clean
PREFLIGHT_VERIFIED
  ↓ explicit execution-gate token (future gate) — NOT exercised here
RUNTIME_ENVIRONMENT_STARTED           (architectural only in this gate)
  ↓ runtime identity inspected + bound
RUNTIME_IDENTITY_VERIFIED
  ↓ render observer authorised + render-valid evidence signed
RENDER_OBSERVER_VALID
  ↓ drive observer authorised + drive-valid evidence signed
DRIVE_OBSERVER_VALID
  ↓ pair current/authentic/non-revoked/overlapping/bound
EVIDENCE_PAIR_VALID
  ↓ two-phase authorisation engine issues one-time token
CAPTURE_ARMED
  ↓ writer connected in a later gate + re-inspection unchanged
CAPTURE_ACTIVE
  ↓ integrity verified + manifest generated
CAPTURE_FINALISED
```

Every transition requires: an explicit previous state, the required evidence, policy approval, a structured
append-only audit record, a defined failure→rollback edge, and **zero implicit fallback**. Any failure
transitions to `BLOCKED` (before startup) or the stop/rollback path (§18) after startup. In this gate,
`RUNTIME_ENVIRONMENT_STARTED` and all later states are **definitions only** — none may be executed against
Isaac. Fail edges and their reason codes are enumerated in §20; failure-transition coverage is 100% of
states (§31).

## 7. Two-phase capture authorisation (§7)

**Phase A — Runtime evidence establishment.** In a *future authorised* gate the system may launch the
runtime, inspect scene/robot/camera/route and generate **signed** runtime render/drive evidence, and
validate the pair. It must **not** create dataset frames or trajectories. Phase A has **no writer wired**.

**Phase B — Capture activation.** Capture may begin only after ALL hold: render-valid runtime evidence
valid; drive-valid runtime evidence valid; identities match; validity windows overlap; neither revoked;
signatures verify; runtime state unchanged since inspection (§17 TOCTOU re-check); capture plan unchanged;
and an explicit **one-time capture-authorisation token** is issued.

**Capture-authorisation token (design; not minted this gate).**

```text
CaptureAuthToken {
  token_id: "cat-<uuid>",             issuer: "h8-capture-authoriser/<ver>",
  instance_id, split, dataset_plan_id,
  runtime_identity_digest: "sha256:…",  render_evidence_id, drive_evidence_id,
  trust_policy_version, signature_policy_version, revocation_policy_version, clock_policy_version,
  not_before, not_after,               # short window (minutes), trusted-clock stamped
  one_time: true,                      # consumed atomically; replay → CAPTURE_TOKEN_INVALID
  bound_closure_digest: "sha256:…",    # from §5 resolver
  signature: "<detached>",  key_id, signature_algorithm,
}
```

Semantics: issued by a dedicated authoriser (not the worker); single-use (atomic consume, like the S4B
authz-code pattern used elsewhere in the estate); revocable (§14); expires on the trusted clock; and bound
to the exact runtime-identity digest so any post-issue change (§17) invalidates it.

## 8. Runtime backend interface (§8)

A **narrow, typed** interface decouples capture logic from Isaac APIs. All methods return structured results
(never bare truthy values); every one defines inputs, outputs, reason codes, timeout, retry policy, cleanup
responsibility, idempotency, failure state and audit fields.

```text
H8RuntimeBackend (design; NOT implemented this gate)
├── prepare_runtime(plan, closure_digest)        → RuntimeResult
├── launch_runtime(exec_token)                    → RuntimeResult      # requires future execution gate
├── load_scene(scene_ref)                          → SceneResult
├── resolve_robot(robot_cfg)                        → IdentityResult
├── resolve_camera(camera_cfg)                      → IdentityResult
├── resolve_route(route_artifact)                   → IdentityResult
├── inspect_runtime_identity()                      → RuntimeIdentity
├── stop_runtime()                                  → RuntimeResult     # idempotent
└── emergency_stop()                                → RuntimeResult     # idempotent, always safe
```

`RuntimeResult` (shared shape): `{ ok: bool, reason_code: str, detail, timeout_s, attempts, cleaned_up: bool,
idempotent: bool, next_state, audit: {ts_wall, ts_sim, actor, closure_digest} }`. Contract rules: no method
may partially succeed silently; `stop_runtime`/`emergency_stop` are idempotent and always leave a safe state;
default results are the *blocked* result, so an unimplemented or crashed method reads as failure, not
success. **No Isaac implementation is authorised in this gate** — the interface is specified so the future
worker (`G4`) implements it behind an import-safe boundary.

## 9. Runtime observer architecture (§9)

Two observers, each satisfying the existing typed observer contract (`validate_runtime_observer`) **and** the
external producer trust policy (`check_production_trust`); neither is authorised until a reviewed policy adds
its id to `AUTHORISED_OBSERVER_IDS` (empty today).

**`RenderValidityObserver`** future checks: expected scene loaded; expected camera exists; camera prim/sensor
identity; transform matches approved config; resolution & encoding; frame received; frame non-empty; frame
not constant/corrupted; required geometry visible; runtime scene digest/manifest binding; trusted observation
timestamp; diagnostics reference.

**`DriveValidityObserver`** future checks: robot identity; route identity; start/goal binding; coordinate
frame; route geometry; collision feasibility; robot footprint; clearance threshold; prohibited geometry;
controller/kinematic assumptions; runtime route digest; trusted observation timestamp; diagnostics reference.

**Evidence-dimension separation (critical honesty control).** The design does **not** call four different
things "drive valid." It defines distinct dimensions:

| Dimension | Meaning | Evidence field |
|---|---|---|
| `route_structure_valid` | static route representation is well-formed & bound | drive payload (already exists at preflight) |
| `route_geometry_feasible` | simulated geometric feasibility (clearance, no prohibited geometry) | drive runtime payload |
| `route_execution_commanded` | controller commanded the route | future (later gate) |
| `route_traversal_succeeded` | robot physically traversed to goal | future (later gate) |

`drive_valid` for capture authorisation in the first runtime gate means **`route_geometry_feasible` under a
current, signed, bound observation** — not commanded execution or successful traversal, which are separate,
later, explicitly-labelled dimensions. This prevents the H8-S/earlier overclaim pattern.

## 10. Runtime identity binding (§10)

`RuntimeIdentity` binds (any mismatch blocks progression): repository commit; dependency-closure digest
(§5); simulator name+version; runtime/backend version; scene identifier; scene-file digest; runtime-loaded-
scene identity (prim inventory where feasible); referenced-asset manifest digest; robot asset identity;
robot-config digest; camera identity; camera-config digest; route digest; coordinate frame; `coord_offset`;
start pose; goal pose; goal-image identifier; `CL_BOUND_XY == 6.0` (watchdog, unchanged); dataset plan ID;
instance ID; split; configuration digest; observer identities; clock source; signature-policy version;
revocation-policy version. The tuple is canonicalised and hashed → `runtime_identity_digest`, which the
capture token (§7) and capture decision (§16) bind to.

## 11. Scene-content verification (§11)

The future backend must distinguish four identities — a file-path match is **insufficient**:

1. **scene-reference identity** (the ref string the config declares);
2. **scene-file identity** (SHA-256 of the primary `.usd/.usda` bytes — already computed by the provider);
3. **scene dependency-manifest identity** (digest/manifest of referenced assets);
4. **runtime-loaded-scene identity** (prim/path inventory + critical-asset + robot/camera prim identity as
   observed after load).

Design includes: primary scene-file digest; referenced-asset digest/manifest; runtime prim/path inventory
where feasible; critical-asset identity; robot & camera prim identity; scene-load error reporting;
unresolved-asset detection. **Documented limitation (§28):** proprietary, generated, or externally
referenced Isaac assets may not expose a stable content digest; where a digest is unavailable the design
records the reference identity + a runtime prim-inventory hash and marks asset-content identity
`indeterminate` (fail-closed for capture, not silently "valid"). This limitation is owned by gate `G6`.

## 12. Trusted-clock design (§12)

Resolve time architecturally; **do not treat Isaac simulation time as trusted wall time.**

- **Authoritative wall clock:** an external trusted UTC source (e.g. host NTP-disciplined clock or, in
  production, a trusted timestamping service) — proves *freshness*.
- **Local monotonic clock:** proves *ordering/duration*, immune to wall-clock steps.
- **Simulator time:** proves *simulation ordering only* — recorded separately, never used for freshness.
- Fields: observation time, issue time, validity start, expiry, max evidence age, allowable skew.
- **Backward-clock detection:** monotonic regression or wall-clock step beyond skew → `CLOCK_UNTRUSTED`.
- **Time-source health:** unavailable/unhealthy trusted time → fail closed (`CLOCK_UNTRUSTED`), capture
  blocked.

Observer/evidence policy records **both** `ts_sim` (simulation ordering) and `ts_wall` (trusted freshness)
in every runtime evidence envelope; the freshness/validity-window checks in the existing schema
(`_parse_ts`, validity window) run against `ts_wall` only.

## 13. Signature & key-management design (§13; no real secrets)

Authenticity for production runtime evidence, designed **without creating or committing any secret**:

- **Signing authority / producer identity / observer identity / key id / algorithm** declared in a
  signature policy (versioned).
- **Signature scope:** the canonical bytes of the evidence envelope (existing `canonical_bytes`, with derived
  integrity fields blanked as today) → a **detached** signature stored in `integrity.signature` with
  `signature_algorithm` and `key_id`.
- **Key storage external to the repository** (KMS/HSM/file outside the tree); **rotation** and **revocation**
  via the signature+revocation policies.
- **Verification policy:** unsigned runtime evidence → `RUNTIME_SIGNATURE_INVALID` (deny in production);
  unknown key → deny; expired/revoked key → deny. The existing schema `require_signature` +
  `verification_status` are the hook; production runtime requires `verification_status == "verified"`.
- **Never commit** private keys, production certificates, tokens, secrets, or placeholder values confusable
  with production keys. Synthetic **fixture-only** test keys may be designed for a future isolated test gate
  (`G2`) and MUST be explicitly labelled fixture-only and rejected by production trust (they carry fixture
  provenance, so `_has_fixture_provenance` + producer policy already reject them in production).

## 14. Revocation architecture (§14)

Operational revocation for: producer identity; observer identity; signing key; evidence id; capture-auth
token; scene; route; configuration; runtime/backend version. Design: a revocation source (versioned list or
service); defined update frequency; **offline behaviour = fail closed**; cached status with a **maximum cache
age**; supersession + emergency revocation; append-only audit trail. **If revocation status cannot be
obtained (or cache is stale beyond max age), capture remains blocked** (`REVOCATION_STATUS_UNAVAILABLE`).

## 15. Runtime evidence status model (§15)

No single overloaded Boolean `valid`. Distinct dimensions (all mandatory ones required for capture):

`document_conformant` · `producer_authorised` · `signature_verified` · `identity_bound` · `fresh` ·
`not_revoked` · `runtime_observed` · `render_valid` · `route_geometry_feasible` · `route_execution_valid`*
· `capture_authorised`. (*`route_execution_valid` is a later-gate dimension, not required for the first
runtime-validity gate.) The existing envelope `status` enum stays {valid, invalid, indeterminate, revoked};
the dimensions above are recorded in the runtime payload and evaluated by the capture decision (§16), so
"capture authorised" is a conjunction of dimensions, never a truthy field.

## 16. Capture-authorisation decision (§16)

```text
evaluate_capture_authorisation(plan, runtime_identity, render_evidence, drive_evidence,
                               trust_policy, signature_policy, revocation_state, clock_state)
  → CaptureDecision {
        authorised: bool, reason_code: str, failed_prerequisite: str|None,
        instance_id, evidence_ids: [render_id, drive_id],
        policy_versions: {trust, signature, revocation, clock},
        runtime_identity_digest: "sha256:…",
        decision_time: "<trusted wall RFC3339>", expiry: "<…>",
        one_time_token_ref: "cat-…"|None,
    }
```

Deterministic; **any unknown exception → denial** (`authorised=False`, `reason_code=RUNTIME_INTERNAL_ERROR`).
Prerequisite order (first failure wins, all fail-closed): closure clean → producer authorised → signatures
verified → identities bound & matched → fresh (trusted clock) → not revoked → render_valid → route geometry
feasible → windows overlap → pair correctly bound → token issuable. Mirrors the existing
`validate_pair`/`check_production_trust` semantics, extended with signature/revocation/clock/runtime-identity.

## 17. Runtime-change invalidation — TOCTOU (§17)

These changes immediately invalidate evidence and, after authorisation, **stop** capture
(`RUNTIME_STATE_CHANGED`): scene reload; scene-file change; referenced-asset change; robot change; camera
transform change; camera-resolution change; route change; `coord_offset` change; coordinate-frame change;
configuration change; simulator restart; backend restart; observer restart; clock-source change; policy
update; key rotation; revocation update. Mechanism: the `runtime_identity_digest` is re-inspected between
authorisation and each capture step; any delta → immediate stop + rollback (§18). This closes the
time-of-check/time-of-use window the threat model calls out.

## 18. Stop, rollback & quarantine policy (§18)

Fail-safe responses, in order of severity: (1) deny before runtime startup; (2) shut down runtime before
capture; (3) cancel capture authorisation (consume/void token); (4) stop frame writer; (5) stop trajectory
writer; (6) close rosbag safely; (7) mark partial data invalid; (8) **quarantine** partial artefacts;
(9) generate failure evidence (a signed `invalid`/`revoked` envelope); (10) require human review.
**Decision:** partial capture files are **quarantined** (moved to an invalid/forensic namespace), **never
deleted automatically** (forensic value) and **never auto-admitted** to the dataset. Admission to training
data requires the transactional gate (§19) plus human review.

## 19. Transactional output design (§19)

```text
planned → authorised → temporary capture → integrity verified → manifest generated → instance finalised → dataset admitted
```

Separate namespaces: `…/runtime/tmp/` (temporary runtime data); `…/runtime/quarantine/` (invalid/forensic);
`…/runtime/instances/<id>/` (approved instance data, post-validation); `datasets/…` (final dataset);
`assets/evidence/h8/runtime/` (audit evidence). **No file appears in an approved dataset namespace before
final validation.** This extends — does not bypass — the existing `run_dataset_capture` seam, where the
writer stays the injected `capture_backend` and only the finalisation step admits data.

## 20. Runtime reason-code taxonomy (§20) + reconciliation

New stable codes (UPPER_SNAKE, consistent with existing `es.*`/`PROVIDER_*`):

`RUNTIME_BACKEND_UNAVAILABLE` · `RUNTIME_LAUNCH_FAILED` · `SCENE_LOAD_FAILED` · `SCENE_IDENTITY_MISMATCH` ·
`ASSET_DEPENDENCY_MISMATCH` · `ROBOT_IDENTITY_MISMATCH` · `CAMERA_IDENTITY_MISMATCH` ·
`CAMERA_CONFIGURATION_MISMATCH` · `ROUTE_IDENTITY_MISMATCH` · `RUNTIME_OBSERVER_UNAUTHORISED` ·
`RENDER_OBSERVATION_FAILED` · `DRIVE_OBSERVATION_FAILED` · `RUNTIME_EVIDENCE_EXPIRED` ·
`RUNTIME_EVIDENCE_REVOKED` · `RUNTIME_SIGNATURE_INVALID` · `CLOCK_UNTRUSTED` ·
`REVOCATION_STATUS_UNAVAILABLE` · `CAPTURE_TOKEN_INVALID` · `RUNTIME_STATE_CHANGED` · `CAPTURE_ABORTED` ·
`PARTIAL_OUTPUT_QUARANTINED` · `RUNTIME_INTERNAL_ERROR` · plus the `DEP_*` resolver codes (§5.2).

**Reconciliation with existing codes:** `SCENE_IDENTITY_MISMATCH`/`ROUTE_IDENTITY_MISMATCH`/
`CAMERA_CONFIGURATION_MISMATCH` are the *runtime-observation* analogues of the schema's binding codes
`es.SCENE_MISMATCH`/`ROUTE_MISMATCH`/`CONFIG_MISMATCH`/`FRAME_MISMATCH`/`BOUND_MISMATCH` (which stay the
*document-level* codes). `CLOCK_UNTRUSTED` reuses the existing `PROVIDER_CLOCK_UNTRUSTED` semantics.
`RUNTIME_EVIDENCE_REVOKED`/`_EXPIRED` mirror `es.EVIDENCE_REVOKED`/`EVIDENCE_EXPIRED`. No existing code is
renamed; runtime codes are additive and namespaced by the `RUNTIME_`/`DEP_`/observation prefixes.

## 21. Runtime threat model (§21)

Each threat: mechanism → impact → prevention → detection → containment → residual risk → verification gate.

| # | Threat | Prevention → Detection → Containment | Verify gate |
|---|---|---|---|
| T1 | Malicious/incorrect backend | narrow typed iface, structured results, default-blocked | detect via identity mismatch | stop | G4/G5 |
| T2 | Scene substitution | scene-file digest + loaded-scene inventory | `SCENE_IDENTITY_MISMATCH` | block | G6 |
| T3 | Referenced-asset substitution | asset manifest digest | `ASSET_DEPENDENCY_MISMATCH` | block | G6 |
| T4 | Robot/camera substitution | identity+config digest | `ROBOT/CAMERA_IDENTITY_MISMATCH` | block | G6/G7 |
| T5 | Route substitution | route digest + binding | `ROUTE_IDENTITY_MISMATCH` | block | G7 |
| T6 | Stale runtime evidence | trusted-clock freshness + max age | `RUNTIME_EVIDENCE_EXPIRED` | block | G2/G8 |
| T7 | Observer impersonation | typed contract + `AUTHORISED_OBSERVER_IDS` + signature | `RUNTIME_OBSERVER_UNAUTHORISED` | block | G3 |
| T8 | Producer impersonation | positive producer trust (existing) | `PRODUCER_NOT_AUTHORISED` | block | done+G8 |
| T9 | Key compromise | external KMS, rotation, revocation | `RUNTIME_SIGNATURE_INVALID` | revoke+block | G2 |
| T10 | Clock manipulation | monotonic+wall cross-check, backward detection | `CLOCK_UNTRUSTED` | block | G2 |
| T11 | Simulation-time confusion | `ts_sim`≠`ts_wall`, freshness on wall only | policy | block | G3/G6 |
| T12 | Revocation failure/offline | fail-closed, max cache age | `REVOCATION_STATUS_UNAVAILABLE` | block | G2 |
| T13 | Capture-token replay | one-time atomic consume | `CAPTURE_TOKEN_INVALID` | block | G10 |
| T14 | Runtime state mutation after auth (TOCTOU) | re-inspect identity digest each step | `RUNTIME_STATE_CHANGED` | stop+quarantine | G9/G10 |
| T15 | Partial-output admission | transactional namespaces, quarantine, human review | audit | quarantine | G9 |
| T16 | Backend bypass / direct writer invocation | writer not owned by worker; DI seam only via authoriser+token | audit + no-writer capability | block | G4/G9 |
| T17 | Evidence/capture race, TOCTOU mutation | single-authoriser, token binds identity digest | as T13/T14 | stop | G10 |
| T18 | Unsafe retry / cleanup failure / crash-during-capture | idempotent stop, bounded retry, quarantine on crash | audit | quarantine | G9/G11 |
| T19 | Stale ROS 2 / camera frames | frame freshness + non-constant checks in render observer | `RENDER_OBSERVATION_FAILED` | block | G6 |
| T20 | Wrong coordinate frame / `coord_offset` | identity binding incl. frame+offset | `ROUTE_IDENTITY_MISMATCH` | block | G7 |
| T21 | Scene reset during recording | identity re-inspection (T14) | `RUNTIME_STATE_CHANGED` | stop | G10 |
| T22 | Future provider/schema downgrade | supported-set + policy `permitted_schema_versions` | `SCHEMA_VERSION_UNSUPPORTED`/`PRODUCER_NOT_AUTHORISED` | block | done |

Residual risk per threat is tracked in the challenge register (§28). Threat-to-control mapping = 100%.

## 22. Architecture alternatives (§22)

**Option A — in-process Isaac backend.** Simple; but failure coupling & crash propagation are high, isolation
& auditability low (a crash in Isaac can corrupt the capture controller and its audit trail). Rejected for
first gate.

**Option B — isolated Isaac worker process.** Controller ↔ constrained Isaac worker over a typed local
protocol. Strong process isolation & restartability; policy enforced controller-side; evidence signed at the
boundary; message integrity checkable. Moderate complexity. **Selected.**

**Option C — separate runtime service.** Enterprise-scalable; but adds deployment complexity, network trust,
heavier key management, latency. Deferred as a future scaling option, not needed for one-instance validation.

## 23. Recommended architecture decision (§23)

```text
Capture Orchestrator
        │
        ├── Git Dependency Resolver (§5)
        ├── Trust / Signature / Revocation / Clock Policy (§12–§14)
        ├── Capture Authorisation Engine (§16, issues one-time token §7)
        │
        └── Typed Local Runtime Protocol (§8)
                   │
             Isaac Worker
                   ├── Scene Loader (§11)
                   ├── Runtime Identity Inspector (§10)  ← extends precheck_scene_identity()
                   ├── Render Observer (§9)
                   ├── Drive Observer (§9)
                   └── NO Dataset Writer            ← H8-DCP-036
```

**Selected: Option B.** For the first runtime-validity gate the Isaac worker **owns no dataset writer**;
runtime evidence is reviewed **before** any capture-writer capability is connected. Rationale: prevents
runtime testing from silently becoming unauthorised capture; keeps the writer in the existing separable
`capture_backend` DI slot; matches the estate's isolate-and-authenticate pattern. Rejected alternatives and
reversibility recorded in `H8-DCP-035`.

## 24. Future gate decomposition (§24) — do NOT combine

| Gate | Scope | Writer? | Isaac? |
|---|---|---|---|
| **G1** | Git dependency-resolver implementation + independent review | no | no |
| G2 | Signature/key + revocation **test** infrastructure (fixture-only keys) | no | no |
| G3 | Runtime-observer protocol impl using **non-Isaac stubs** | no | no |
| G4 | Isaac worker skeleton, **startup disabled by default** | no | import-safe only |
| G5 | Isaac launch/readiness gate | no | yes (gated) |
| G6 | Scene-identity + render-observer gate | no | yes |
| G7 | Route/drive-observer gate | no | yes |
| G8 | Runtime evidence-pair independent review | no | no |
| G9 | Capture-writer transaction gate | writer built, not yet armed | no |
| G10 | One-instance capture **authorisation** | armed | yes |
| G11 | One-instance footage + trajectory capture | yes | yes |
| G12 | Dataset-quality admission gate | — | no |
| G13 | Full 8-instance capture approval | yes | yes |

**The first implementation gate is `G1` (Git resolver), not the Isaac backend.**

## 25. Design-only test plan (§25)

Test **specifications** (no runtime execution) authored for: Git dependency resolver (all §5.2 states);
trust-policy failure; signature verification; key revocation; evidence revocation; trusted-clock failure;
scene mismatch; camera mismatch; robot mismatch; route mismatch; stale evidence; state mutation after
authorisation; capture-token replay; observer failure; backend timeout; runtime crash; partial-output
quarantine; direct-writer bypass; wrong instance; wrong split; changed `CL_BOUND_XY`; missing render
evidence; missing drive evidence; document-only evidence; preflight evidence; fixture evidence; unsigned
runtime evidence; untrusted observer; expired token. Each maps to an owning gate in §24 and a threat in §21.
Coverage of the enumerated cases: **29/29 specified.**

## 26. Requirements traceability (§29) — 100%

Every runtime requirement → component / policy / interface / future test / owning gate / threat / status /
residual limitation. Representative rows (full mapping is the union of §5–§21):

| Requirement | Component | Policy | Interface | Test | Gate | Threat | Status |
|---|---|---|---|---|---|---|---|
| Dependency cleanliness (concrete) | Git Dependency Resolver | resolver policy | §5.1 | resolver suite | G1 | T15/T16 | designed |
| Scene identity at runtime | Identity Inspector + Scene Loader | scene policy | §8 `load_scene`/`inspect_runtime_identity` | scene-mismatch | G6 | T2/T3 | designed |
| Truthful render evidence | RenderValidityObserver | observer trust | §9 | render-observer | G6 | T7/T19 | designed |
| Truthful drive evidence (geometry) | DriveValidityObserver | observer trust | §9 | drive-observer | G7 | T5/T20 | designed |
| Freshness | Trusted Clock | clock policy | §12 | clock-failure | G2 | T6/T10 | designed |
| Authenticity | Signature svc | signature policy | §13 | signature | G2 | T9 | designed |
| Revocation | Revocation svc | revocation policy | §14 | revocation | G2 | T12 | designed |
| Capture gating | Authorisation Engine | all policies | §16 | token/pair | G10 | T13/T17 | designed |
| TOCTOU safety | Identity re-inspection | change policy | §17 | state-mutation | G10 | T14/T21 | designed |
| No auto-admit | Transactional output | output policy | §19 | quarantine | G9 | T15 | designed |
| No writer in worker | Worker capability | `H8-DCP-036` | §23 | writer-bypass | G4 | T16 | designed |

Traceability coverage = **100%** (every §5–§21 requirement has a component, interface, test and owning gate).

## 27. SMART objectives (§30) — status

1. **Runtime architecture** — 100% of runtime requirements map to a component, interface and future test.
   **Met (design).**
2. **Capture separation** — architecture assigns **no** dataset-writer capability to the initial Isaac worker
   (`H8-DCP-036`). **Met (design).**
3. **Trust dependencies** — Git, time, signature and revocation each have a fail-closed policy and an owning
   future gate (G1/G2). **Met (design).**

## 28. Open challenges (§28) — none marked implemented

`H8-C-020` concrete Git resolver not implemented; `H8-C-021` Isaac API/version compatibility untested;
`H8-C-022` simulator startup time/stability unknown; `H8-C-023` runtime scene-content identity unresolved
(proprietary/generated assets); `H8-C-024` camera validity thresholds unresolved; `H8-C-025` route clearance
thresholds unresolved; `H8-C-026` trusted clock unavailable; `H8-C-027` key management unavailable;
`H8-C-028` revocation service unavailable; `H8-C-029` runtime observer unavailable; `H8-C-030` capture token
unavailable; `H8-C-031` output transaction implementation unavailable; `H8-C-006`/`H8-C-013` Ruff
unavailable (**Open**); `H8-C-032` no Level-3 evidence exists. **All are design targets, not implemented
controls.**

## 29. Decisions & dependency-closure files (§27)

Decisions `H8-DCP-035…046` are recorded in `H8_DATASET_DECISION_LOG.md`. The runtime dependency closure
(§5.3) will, when the runtime files are created, include at minimum: `configs/gnm/h8_synthetic_fork_recorded_mode_dataset.yaml`;
the derived dataset plan + manifest + split; `scripts/gnm/h8_evidence_schema.py`;
`scripts/gnm/h8_evidence_provider.py`; the (future) `h8_runtime_backend.py`, `h8_git_dependency_resolver.py`,
runtime-observer, signature-policy, revocation-policy, clock-policy modules; the scene `.usda`; the route
artefact; robot & camera configs. Until those modules exist, the closure is a **specification**, and the
resolver gate (G1) makes it concrete.

## 30. KPIs (§31)

| KPI | Target | Result |
|---|---|---|
| Runtime requirement coverage | 100% | **100%** |
| Traceability coverage | 100% | **100%** |
| Threat-to-control mapping | 100% | **100% (22 threats + DEP states)** |
| Runtime state transitions specified | 100% | **100% (10 states)** |
| Failure transitions specified | 100% | **100%** |
| Evidence-to-authorisation prerequisites mapped | 100% | **100% (§16 order)** |
| Deferred-dependency ownership | 100% | **100% (each → G1–G13)** |
| Capture capability in first runtime worker | 0 | **0 (`H8-DCP-036`)** |
| Runtime operations executed | 0 | **0** |
| Dataset artefacts created | 0 | **0** |
| Level-1 hashes preserved | 5/5 | **5/5** |
| Existing provider/schema regressions | 100% where run | **100% (223 H8 tests pass, unchanged)** |
| Ruff | Pass or explicitly Open | **Open** |

## 31. SWOT (§32)

**Strengths:** validated plan & capture path; independently reviewed provider trust boundary; deny-by-default
producer authorisation; deterministic evidence binding; explicit non-authorising preflight evidence; reuse of
existing DI seams (writer already separable). **Weaknesses:** no concrete Git resolver; no runtime observer;
no trusted clock; no signatures; no revocation; no Isaac runtime evidence; Ruff unavailable. **Opportunities:**
isolated & auditable Isaac worker; signed runtime evidence; a reusable safe-capture architecture; scene/route
evidence benchmarks; future fleet-scale runtime validation. **Threats:** premature backend integration;
runtime-evidence overclaim; backend bypass; stale/substituted scene; observer impersonation; partial-dataset
contamination; capture before policy dependencies exist.

## 32. Verification (§33) — design-only

Recorded in the gate report: documentation consistency; commit-hash correctness; reason-code consistency;
**no implementation/runtime files changed**; **no Isaac imports added**; **no ROS 2 imports added**; **no
capture/writer code added**; Level-1 evidence files unchanged; no dataset/evidence runtime directory created;
attribution scan clean; secret scan clean; `git diff --check` clean; Ruff status accurately reported. No
executable interface stubs are added in this gate (`H8-DCP-045`); the interfaces above are specifications.

## 33. Gate verdict (§34)

**`PASS WITH DOCUMENTED LIMITATIONS`.** The architecture, trust-boundary design and explicit future-gate
decomposition are complete; no runtime or capture execution occurred; and there is no design ambiguity that
would let the first backend implementation include a dataset writer or bypass runtime evidence
(`H8-DCP-036`, §23). The "documented limitations" are the unbuilt dependencies (Git resolver, observers,
clock, signatures, revocation) — each owned by an explicit future gate (§24), none claimed as implemented.

## 34. Recommendation

Proceed — **only on explicit authorisation** — to the first **implementation** gate **`G1`: the Git
dependency-resolver**, not the Isaac backend. G1 is non-Isaac, non-capturing, independently reviewable, and
directly discharges `H8-PRREV-F-002`. Isaac launch remains gated behind G5 and multiple reviews.

Levels 3–5 remain **unproven**; real hospital footage & trajectory collection remains **blocked**.
