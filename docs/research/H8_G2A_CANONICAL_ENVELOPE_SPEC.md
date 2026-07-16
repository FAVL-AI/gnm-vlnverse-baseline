# H8 G2A — Canonical dependency-evidence envelope specification (design-only)

**Gate.** G2A — the first item of the G2 future-gate decomposition
(`H8_G2_CRYPTOGRAPHIC_TRUST_ARCHITECTURE.md` §28, §40). This document is the **detailed
specification** of the canonical signed envelope and its fixture/cross-language
test-vector plan. It **details** the architecture doc's §8 (envelope) and §9
(canonical bytes); it does not redefine or supersede them.

**Design-only — this milestone introduces no code.** No cryptographic primitive, key,
signature, timestamp, revocation record, external service, canonicaliser implementation,
or computed test-vector fixture is created here. Producing a schema module, a
canonicaliser, and the fixture vectors is the *separate, later* **G2A-implementation**
gate (schema + fixture-only cross-language vectors, still no real key / no signing / no
external service). Isaac, rendering, drive, capture, and hospital collection remain
blocked; `CL_BOUND_XY = 6.0` is untouched; the G1R2 resolver code is unchanged and its
suite (107) and the independent probes (28) remain the verified baseline.

---

## 1. Scope and non-goals

**In scope (design):** the exact field schema of the `h8-trust-envelope/1.0.0` envelope;
the signed-`payload` vs outer signature-block boundary; the canonical-byte pipeline
(strict parse → schema validation → JCS canonicalisation → digest); field availability
rules at G2A; the fixture/cross-language test-vector plan; the G2A-owned failure codes;
independent-review criteria.

**Out of scope (later gates):** signature creation/verification (G2B), trusted time
(G2C), revocation data/lookup (G2D), repository/release attestation (G2E), semantic
per-dependency verifiers (G2F), `.gitattributes`/filter binding verifier (G2G), combined
verifier (G2H). This document *references* those fields so the envelope is versioned once,
but marks them **UNAVAILABLE at G2A** rather than fabricating them.

**Non-goals (must not be claimed):** that dependencies are cryptographically verified;
that signatures, trusted timestamps, revocation, origin attestation, or semantic identity
proofs exist; that TOCTOU is closed; that runtime or capture is eligible.

## 2. Relationship to the committed G2 architecture

| Architecture (`640ddd0`) | Detailed here (G2A) |
| --- | --- |
| §8 signed resolver-report envelope | full field schema, types, required/optional, G2A availability |
| §9 canonical signed bytes (JCS, no floats, dup/unknown rejected) | the exact 4-stage canonical-byte pipeline + edge rules |
| §10 `signature_algorithm` signed field (Ed25519) | field encoding + downgrade-rejection schema rule (verification deferred to G2B) |
| §18 `per_dependency_identity_commitments[]` | the per-dependency commitment sub-schema |
| §19 `.gitattributes` closure digest | the `attributes_closure_digest` field |
| §20 `report_id`/`nonce`/`intended_use` + registry | anti-replay identity fields |
| §24 `TRUST_*` taxonomy | the G2A-owned subset (`TRUST_ENVELOPE_SCHEMA_INVALID`, `TRUST_CANONICALISATION_FAILED`) |

The envelope name/version is unchanged: **`h8-trust-envelope/1.0.0`**.

## 3. Canonical envelope field schema

The envelope is a JSON object with exactly two top-level members: **`payload`** (the
signed content) and **`signature_block`** (the detached signature, **outside** the signed
bytes). The signature covers the canonical bytes of `payload` only (§8).

**Requested-field reconciliation.** The G2 authorisation listed an "at minimum" field set;
each maps onto the committed `h8-trust-envelope/1.0.0` names below (canonical name wins;
the requested alias is noted) so this remains one schema, not a third divergent one.

### 3.1 `payload` — signed members

| Field | Type | Req | G2A availability | Meaning / requested alias |
| --- | --- | --- | --- | --- |
| `envelope_version` | string const `h8-trust-envelope/1.0.0` | yes | populated | schema/version binding *(alias: schema_version)* |
| `envelope_type` | string enum `resolver-report` | yes | populated | envelope kind *(alias: envelope_type)* |
| `report_schema_version` | string | yes | populated | resolver-report schema version |
| `resolver_id` | string | yes | populated | approved resolver identity |
| `resolver_version` | string | yes | populated | resolver software version *(alias: resolver_version)* |
| `resolver_trust_policy_version` | string | yes | populated | trust-policy version *(alias: policy_version)* |
| `repository_policy_id` | string | yes | populated | repository-policy identity |
| `repository_identity` | object `{canonical_name, root_commit}` | yes | populated | canonical repo identity *(alias: canonical_repository_identity)* |
| `observed_remote_origins` | array\<string\> | no | `UNAVAILABLE` (G2E) | fetch-observed remotes; not authoritative *(alias: observed_remote_origins)* |
| `head_commit` | string (40/64-hex oid) | yes | populated | resolved HEAD *(alias: resolved_commit_oid)* |
| `head_tree_oid` | string (oid) | yes | populated | resolved tree oid *(alias: resolved_tree_oid)* |
| `reference_input` | string | no | populated-if-any | requested ref/tag input *(alias: reference_input)* |
| `reference_resolution` | string enum `commit`\|`annotated_tag`\|`lightweight_tag`\|`none` | yes | populated | how the ref resolved *(alias: reference_resolution)* |
| `canonical_manifest_path` | string (POSIX rel) | yes | populated | canonical manifest path |
| `canonical_manifest_digest` | digest-string | yes | populated | manifest blob digest *(alias: content_manifest_digest)* |
| `manifest_schema_version` | string | yes | populated | manifest schema version |
| `manifest_schema_digest` | digest-string | yes | populated | manifest-schema blob digest |
| `closure_digest` | digest-string | yes | populated | deterministic closure digest (existing resolver output) |
| `attributes_closure_digest` | digest-string | yes | populated | effective `.gitattributes` closure (§19) |
| `git_env_policy_version` | string | yes | populated | G1R2 git-env policy version |
| `git_version` | string | yes | populated | git binary version observed |
| `mandatory_dependency_count` | integer | yes | populated | mandatory-set size |
| `accepted_count` / `rejected_count` / `unresolved_count` | integer | yes | populated | closure tallies |
| `per_dependency_identity_commitments` | array\<object\> (§3.3) | yes | populated | per-dependency Git + semantic commitments *(alias: semantic_identity_profile per entry)* |
| `digest_algorithm` | string enum `sha-256` | yes | populated | digest algorithm *(alias: digest_algorithm)* |
| `signature_algorithm` | string enum `ed25519` (allow-list) | yes | populated (declared) | signed algorithm field; unlisted → schema reject *(alias: signature_algorithm)* |
| `signing_key_id` | string | yes | `UNAVAILABLE` (G2B) | key id (chosen by policy, never caller) *(alias: signer_key_id)* |
| `observation_time` | RFC 3339 UTC `Z` | yes | populated (**untrusted**) | local observation time; freshness NOT claimed *(alias: observation_time)* |
| `issue_time` / `validity_start` / `expiry` | RFC 3339 UTC `Z` | yes | populated (untrusted clock) | validity window (untrusted until G2C) |
| `trusted_timestamp_reference` | string | no | `UNAVAILABLE` (G2C) | TSA/transparency proof ref *(alias: trusted_timestamp_reference)* |
| `revocation_snapshot_reference` | string | no | `UNAVAILABLE` (G2D) | revocation snapshot/policy ref *(alias: revocation_snapshot_reference / revocation_policy_version)* |
| `origin_attestation_reference` | string | no | `UNAVAILABLE` (G2E) | release/origin attestation ref *(alias: origin_attestation_reference)* |
| `report_id` | string (unique) | yes | populated | anti-replay id (§20) |
| `nonce` | string (≥128-bit, base64url) | yes | populated | anti-replay nonce |
| `intended_use` | string enum `preflight-document` | yes | const at G2A | never `capture`/`runtime` |
| `assurance_claims` | array\<string enum\> | yes | `["content-equivalent"]` at G2A | assurance ladder claims (§7); ≤ level 3 ever from a report |
| `verification_requirements` | object (§3.4) | yes | populated | what a verifier MUST check *(alias: verification_requirements)* |
| `critical_extensions` | array\<string\> | yes (may be empty) | `[]` at G2A | extension keys a verifier MUST understand or fail closed *(alias: critical_extensions)* |
| `extensions` | object | no | absent/`{}` | forward-growth NON-critical members |

### 3.2 `signature_block` — NOT signed

| Field | Type | G2A availability | Meaning |
| --- | --- | --- | --- |
| `signing_key_id` | string | `UNAVAILABLE` | echoes payload key id at verification time |
| `signature_algorithm` | string | `UNAVAILABLE` | MUST equal the signed `payload.signature_algorithm` (bind-back checked at G2B) |
| `signature` | string (base64url) | `UNAVAILABLE` | detached signature over canonical `payload` bytes (G2B) |
| `timestamp_proof` | object/string | `UNAVAILABLE` | trusted-time proof (G2C) |

At G2A a fixture envelope's `signature_block` is present with every member set to the
explicit sentinel `"UNAVAILABLE"` (never a fabricated signature). The G2A vectors verify
the **canonicalisation and schema of the payload**, not signatures.

### 3.3 `per_dependency_identity_commitments[]` sub-schema (details §18)

Each entry: `dependency_id` (string); `dependency_class` (enum from §18: `dataset-config`,
`dependency-manifest`, `manifest-schema`, `evidence-schema`, `trust-policy`, `module`,
`expected-routes`, `scene`, `level1-drive-manifest`, `cl-bound`, `canonicalisation-impl`,
`capture-validator`); `path` (POSIX rel); `git_blob_oid` (oid); `git_content_digest`
(digest-string, raw blob bytes — §19); `semantic_identity_profile` (object: `{scheme, id,
version, digest}` per the §18 commitment format, e.g. `cfg:<sha256>`, `rte:<sha256>`,
`clb:6.0`); `required` (bool — mirrors G1R2 mandatory-set). Unknown `dependency_class` →
`TRUST_ENVELOPE_SCHEMA_INVALID`. Semantic verification itself is G2F; G2A only fixes the
**shape** these commitments take in the signed bytes.

### 3.4 `verification_requirements` sub-object

Booleans a verifier MUST satisfy (all default true; a report cannot self-lower them):
`require_signature`, `require_authorised_signer`, `require_trusted_timestamp`,
`require_not_revoked`, `require_repository_attestation`, `require_semantic_identity`,
`require_attributes_binding`, `require_intended_use_match`. At G2A these are **declared**
in the schema; the verifier that consumes them is G2H. A report that sets any to `false`
is schema-invalid (prevents a forged report from waiving its own checks).

## 4. Canonical-byte pipeline (details §9)

Signing/verification operate on the canonical bytes of `payload`, produced by a **fixed
4-stage pipeline**. Any stage failing → fail closed.

1. **Strict parse.** Parse `payload` as UTF-8 JSON with **duplicate object keys rejected**
   (not last-wins) → `TRUST_ENVELOPE_SCHEMA_INVALID`. Reject BOM, NaN/Infinity, and any
   non-JSON token.
2. **Schema validation.** Validate against the `h8-trust-envelope/1.0.0` schema:
   required fields present; enums honoured; `envelope_version` an **exact** match (**no
   "accept unknown version"** → `TRUST_ENVELOPE_SCHEMA_INVALID`); **unknown top-level
   members rejected** except the designated `extensions` object; every key listed in
   `critical_extensions` MUST be present under `extensions` and understood by the verifier
   or fail closed; string length/array-size bounds enforced (oversized → reject);
   `signature_algorithm`/`digest_algorithm` within the allow-list (downgrade/unknown →
   reject).
3. **Canonicalisation.** Apply **JCS (RFC 8785)**: UTF-8; lexicographic key ordering by
   UTF-16 code unit; minimal string escaping; **no floating-point numbers permitted in the
   signed payload** (integers as shortest decimal; durations/coords as integers or decimal
   **strings**); Unicode **NFC** normalisation of all string values; POSIX
   forward-slash repo-relative paths; RFC 3339 UTC `Z` timestamps. `null` permitted
   **only** where the schema types a member nullable; **absent ≠ null** (see §5).
4. **Digest.** `sha-256` over the canonical UTF-8 bytes → the value signed at G2B. A
   one-byte change anywhere in the canonical bytes MUST change the digest.

**Determinism requirement.** For any two schema-valid inputs that differ only by member
ordering or insignificant whitespace, stages 3–4 MUST produce **identical** bytes and
digest. For any semantically different input, the digest MUST differ.

## 5. Absent vs null vs UNAVAILABLE (deterministic)

Three distinct states, never conflated:
- **Absent** — the member is not present. Allowed only for schema-optional members. Absent
  members do not appear in the canonical bytes.
- **`null`** — present with JSON null. Allowed only where the schema marks a member
  nullable. `null` **is** part of the canonical bytes; `absent` and `null` produce
  **different** digests (a G2A vector asserts this).
- **`"UNAVAILABLE"`** — an explicit string sentinel for a field whose *value* belongs to a
  later gate (time/revocation/attestation/signature/key). Present, canonicalised, and
  distinct from both absent and null. Fields at G2A that are not yet real MUST use
  `UNAVAILABLE` (or be schema-absent) — **never a fabricated value**.

## 6. Digest and string forms

- `digest-string`: lowercase `sha256:<64-hex>`. `digest_algorithm` is an explicit signed
  field (agility); unknown value → schema reject (no silent alternate digest).
- `oid`: lowercase hex, length 40 (SHA-1 repos) or 64 (SHA-256 repos); the repo's object
  format is bound via `repository_identity`.
- Timestamps: RFC 3339, UTC, trailing `Z`, no offset, no sub-second unless schema-fixed.
- Paths: POSIX, repo-relative, no `.`/`..` segments, no leading `/`.

## 7. Fixture & cross-language test-vector plan

The future **G2A-implementation** gate must ship exactly these vector classes (fixtures
only — synthetic payloads, `signature_block` = `UNAVAILABLE`; **no real signatures**).
Each vector = an input plus an expected canonical-bytes digest **or** an expected rejection
code. This document specifies them; it does not compute them.

| # | Vector | Input | Expected |
| --- | --- | --- | --- |
| 1 | valid minimal | required fields only, optionals absent/`UNAVAILABLE` | canonical bytes + digest D1 |
| 2 | valid full | every member populated/`UNAVAILABLE` incl. `extensions` | canonical bytes + digest D2 |
| 3 | field-order variation | vector 2 with members reordered | **identical** bytes + digest = D2 |
| 4 | Unicode edge | NFC/NFD variants, combining marks, emoji, RTL | NFC-normalised bytes; NFD input ⇒ same digest as NFC twin |
| 5 | line-ending edge | CR, LF, CRLF inside string values | schema policy: LF-only in canonical strings; CRLF ⇒ reject **or** normalise (rule fixed, tested) |
| 6 | duplicate-key | `payload` with a repeated key | `TRUST_ENVELOPE_SCHEMA_INVALID` |
| 7 | unknown critical field | unlisted top-level member, or `critical_extensions` naming an absent/ununderstood key | `TRUST_ENVELOPE_SCHEMA_INVALID` |
| 8 | null vs absent | one nullable member as `null` vs absent | two **different** digests |
| 9 | numeric format | float/exponent/leading-zero/`+`/NaN where integer required | reject (float prohibited) or normalise integer (rule fixed, tested) |
| 10 | oversized field | string/array beyond bound | `TRUST_ENVELOPE_SCHEMA_INVALID` |
| 11 | unsupported version | `envelope_version` ≠ `h8-trust-envelope/1.0.0` | `TRUST_ENVELOPE_SCHEMA_INVALID` (no unknown-version accept) |
| 12 | cross-language bytes | vectors 1–2 canonicalised by ≥2 independent implementations | byte-identical across implementations |
| 13 | one-byte mutation | vector 2 with a single canonical-byte change | digest ≠ D2 |

Coverage target: 100% of the above at the G2A-implementation gate, plus a
`canonicalisation-impl` self-commitment (§18 `can:<sha256>`) binding the vector-set digest
into the trust identity.

## 8. G2A-owned failure codes (design names only)

`TRUST_ENVELOPE_SCHEMA_INVALID`, `TRUST_CANONICALISATION_FAILED` (from §24). These remain
**design names**; they are NOT added to the resolver's `REASON_CODES` and no code path
emits them in this milestone.

## 9. Supported vs unsupported claims

**Supported after G2A design:** "H8 specifies a versioned canonical dependency-evidence
envelope (`h8-trust-envelope/1.0.0`), a deterministic 4-stage canonical-byte pipeline, and
a cross-language fixture test-vector plan, ready for implementation and independent
review."

**NOT supported:** any claim that envelopes are signed, that signatures/timestamps/
revocation/attestation/semantic proofs exist or are verified, that TOCTOU is closed, or
that runtime/capture is eligible. A future signed envelope reaches at most assurance
level 3 (resolver-authenticated) and stays **preflight-only** (§7).

## 10. Implementation sequence (future G2A-impl gate — not this milestone)

1. Envelope JSON schema file (`h8-trust-envelope/1.0.0`) — no code.
2. Strict parser + schema validator (duplicate-key/unknown-field/version/bounds) — pure,
   no crypto.
3. JCS canonicaliser + `sha-256` digest — using a mature library, no hand-rolled crypto.
4. The 13 fixture vectors + a second-language canonicaliser cross-check.
5. `TRUST_ENVELOPE_SCHEMA_INVALID`/`TRUST_CANONICALISATION_FAILED` wired with tests.
No key, no signing, no external service, no Isaac/capture.

## 11. Independent-review criteria for G2A

A reviewer should confirm, from the spec and (at the impl gate) the fixtures: exact-version
binding with no unknown-version acceptance; duplicate-key and unknown-critical-field
rejection; absent≠null≠UNAVAILABLE digests differ/agree as specified; float prohibition;
NFC determinism; cross-language byte identity; one-byte-mutation digest change; every
deferred field marked `UNAVAILABLE`/absent and never fabricated; `verification_requirements`
non-waivable; `intended_use` constant `preflight-document`; and that no signature, key, or
runtime/capture capability was introduced.
