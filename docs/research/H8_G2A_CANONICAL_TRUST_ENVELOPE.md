# H8 G2A — Canonical Trust-Envelope: Implementation & Verification

**Gate:** G2A — canonical dependency-evidence envelope **schema, canonicalisation and deterministic
fixture-test** (implementation). **Governing spec:** `docs/research/H8_G2A_CANONICAL_ENVELOPE_SPEC.md`
(committed `23d95c8`), which details `H8_G2_CRYPTOGRAPHIC_TRUST_ARCHITECTURE.md` §8/§9 (`640ddd0`). **This
document reports the implementation that conforms to that committed spec; the spec is authoritative.**
**Branch:** `h23-execfix` (local, unpushed). **Claim boundary:** `SYNTHETIC_DIAGNOSTIC_ONLY`.

**No production cryptographic capability is created.** No key, certificate, token, signature or trusted
timestamp; no KMS/TSA/CA/transparency/revocation connection; no signing/verification/trusted-time/revocation/
attestation; no observer/Isaac/Omniverse/ROS 2/render/drive/capture. **This gate does not establish
signature authenticity.** A schema-valid envelope is signature-**unverified**, freshness-**unverified**,
revocation-**unverified**, runtime-/capture-**ineligible**. Real capture remains blocked; Levels 3–5 unproven.

---

## 1. What was implemented

| Artifact | Path |
| --- | --- |
| Module (authoritative) | `scripts/gnm/h8_trust_envelope.py` |
| Reference JSON Schema | `configs/gnm/h8_trust_envelope_schema.json` |
| Fixture corpus | `tests/gnm/fixtures/h8_trust_envelope/` (`README.md`, `canonical_vectors.json`, `envelope_vectors/{positive,negative}/`, `catalogue.json`) |
| Tests | `tests/gnm/test_h8_trust_envelope.py` (**146 pass**) |

The module implements the spec's four-stage pipeline over the `payload`+`signature_block` envelope:
`parse_envelope_strict` (§4.1) → `validate_envelope` (§3, §4.2) → `canonicalise`/`canonicalise_payload`
(§4.3) → `compute_digest` (§4.4), plus `evaluate_envelope` (the strict, non-authorising result model, §9).

## 2. Conformance to the committed spec

- **Envelope shape (§3):** exactly two top-level members — `payload` (signed) and `signature_block`
  (detached, **not** signed). Canonical bytes cover `payload` only.
- **Payload fields (§3.1):** all required/optional members implemented with the spec's names and types
  (`envelope_version` const, `envelope_type=resolver-report`, `repository_identity{canonical_name,
  root_commit}`, `per_dependency_identity_commitments[]` with `semantic_identity_profile{scheme,id,version,
  digest}`, `digest_algorithm=sha-256`, `signature_algorithm=ed25519` declared, `intended_use=preflight-
  document`, `assurance_claims=["content-equivalent"]`, `verification_requirements` (8, non-waivable),
  `critical_extensions`).
- **signature_block (§3.2):** every member is the explicit `"UNAVAILABLE"` sentinel; no signature is
  fabricated.
- **Absent / null / UNAVAILABLE (§5):** three distinct states. Optional members absent → not in canonical
  bytes; `reference_input` may be `null` (present, in bytes, digest differs from absent); deferred fields use
  the `"UNAVAILABLE"` sentinel (in bytes, distinct). Tests assert absent≠null and that `UNAVAILABLE` appears.
- **Canonical bytes (§4.3):** JCS (RFC 8785) — UTF-8, UTF-16-code-unit key sort, minimal escaping, `/`
  unescaped, integers shortest-decimal, **floats prohibited**, **Unicode NFC normalisation of keys and string
  values**, POSIX paths, RFC 3339 UTC `Z` timestamps. Pure standard library (no third-party canonicaliser).
- **Digest (§4.4):** non-authenticating `sha256:<hex>` over canonical `payload` bytes.
- **Failure codes (§8):** exactly the two G2A-owned codes — `TRUST_ENVELOPE_SCHEMA_INVALID` (all
  structural/schema failures) and `TRUST_CANONICALISATION_FAILED` (canonicalisation-stage failures). These
  live in `h8_trust_envelope.py` and are **disjoint** from the Git resolver's `REASON_CODES`, which remains
  **41** (asserted).

### Spec deviations reconciled (recorded as decisions)

1. **Unicode NFC = normalisation (not rejection).** The spec §4.3 mandates *NFC normalisation* and vector 4
   requires an NFD input to produce the same digest as its NFC twin. Implemented as normalisation during
   canonicalisation (`H8-DCP-084`). (An earlier draft of this implementation rejected non-NFC input; that was
   corrected to match the committed spec.)
2. **Line endings (spec §7 vector 5):** the fixed rule chosen is **reject** — any string value containing a
   carriage return (`\r`) is `TRUST_ENVELOPE_SCHEMA_INVALID` (`H8-DCP-085`).
3. **Timestamps (§6):** no sub-second component is accepted (integer seconds, UTC `Z` only) — the stricter
   reading of "no sub-second unless schema-fixed" (`H8-DCP-086`).

## 3. Fixture & cross-language vectors (spec §7)

`tests/gnm/fixtures/h8_trust_envelope/` (see its `README.md`): **6 positive** vectors (valid-minimal [spec 1],
valid-full [spec 2], reordered-full [spec 3, identical digest], unicode NFC/NFD [spec 4, equal digests],
reference_input-null [spec 8]) and **34 negative** vectors (spec 5–11 plus enum/oid/digest/path/interval/
duplicate/sentinel/waived-requirement/assurance-escalation/intended-use/critical-extension cases), each with
its expected `TRUST_*` code, and **9 cross-language canonicalisation vectors** with exact
`canonical_utf8_hex` + `canonical_sha256` (including an NFC/NFD pair proven byte-identical). Positive digests
are pinned as drift/interop anchors; an independent implementation in any language reproduces
`canonical_utf8_hex` from `input_json`. **No second-language implementation is added here** (spec §7 vector
12 independent execution is a review activity).

Spec-vector mapping: 1→`valid_minimal`; 2→`valid_full`; 3→`reordered_full`; 4→`unicode_nfc`/`unicode_nfd`;
5→`carriage_return`; 6→`dup_top_key`/`dup_payload_key`; 7→`unknown_top_field`/`critical_extension`;
8→`reference_input_null` (+ `test_null_differs_from_absent`); 9→`float_value`/`nan_value`/`infinity_value`;
10→`oversized_nonce`; 11→`unsupported_version`; 12→`canonical_vectors.json`; 13→`test_changed_*` digest tests.

## 4. Determinism KPIs (spec §7)

Repeated canonical bytes/digest; reordered-payload (top-level and nested) equality; machine-root/cwd
independence; NFD→NFC digest equality; integer/timestamp ordering determinism — all asserted **100%**.

## 5. No-authorisation result model (spec §9)

`evaluate_envelope` reports `document_conformant`, `reason_code`, `canonical_bytes_available`,
`canonical_digest`, `classification`, `intended_use`, and ALWAYS reports `signature_verified=false`,
`signer_authorised=false`, `timestamp_verified=false`, `fresh=false`, `not_revoked="unverified"`,
`repository_attested=false`, `release_approved=false`, `semantic_identity_verified=false`,
`attributes_binding_verified=false`, `preflight_eligible=false`, `runtime_eligible=false`,
`capture_eligible=false` (re-applied after evaluation). The module exposes no `sign`/`verify_signature`/
`authorise`. Schema conformance is not trust acceptance.

## 6. Evidence boundary

**Establishes:** envelope-schema validity; canonical byte + digest determinism; fixture reproducibility;
structural downgrade/intended-use/assurance/waiver resistance; duplicate-key resistance; absent/null/
UNAVAILABLE distinction. **Does NOT establish:** signature validity; signer authorisation; key security;
trusted freshness; revocation; repository/origin attestation; semantic-identity verification; runtime or
capture eligibility. **Not cryptographically authenticated evidence.**

## 7. Verdict

**PASS** — strict schema; duplicate-key rejection before parse collapse; deterministic canonical bytes/
digest; NFC determinism; fixture-only vectors (`signature_block` all-`UNAVAILABLE`, no fabricated signature);
cross-language-consumable expected bytes; declared-only `signature_algorithm`; no production signing
capability; schema-valid envelopes remain non-authorising; the two G2A codes are isolated from the resolver
taxonomy (41 unchanged). Limitation: cross-language byte identity is asserted via committed vectors, not yet
executed in a second language.

**Recommended next:** an **independent G2A canonicalisation & fixture-vector review** (reproducing the
`canonical_utf8_hex` vectors in a second language, checking duplicate-key/absent-null-UNAVAILABLE/NFC/
downgrade behaviour) **before** G2B fixture-key and verifier-stub work.
