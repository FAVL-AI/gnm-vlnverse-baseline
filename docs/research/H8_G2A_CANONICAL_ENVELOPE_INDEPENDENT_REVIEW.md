# H8 G2A — Independent Canonicalisation & Fixture-Vector Review

**Gate:** G2A independent review — **adversarial, review-only**. No implementation, key, signature, verifier,
trusted-time, revocation, attestation, observer, Isaac/Omniverse/ROS 2, render/drive/capture.
**Commit reviewed:** `6ed67acc6c7dcde5befcbabfba35b62bde569341` ("Implement H8 canonical trust-envelope
schema"). **Governing spec:** `H8_G2A_CANONICAL_ENVELOPE_SPEC.md` (`23d95c8`). **Branch:** `h23-execfix`
(local, unpushed). This review changed **no** implementation, schema, fixture, test, resolver, provider,
config or evidence file. Independent artifacts (an independent Python canonicaliser and a Node.js
canonicaliser) were run out-of-tree and are not committed.

---

## 1. Baseline & roles

HEAD = `6ed67acc6c7dcde5befcbabfba35b62bde569341` on `h23-execfix`; all milestones intact ancestors:

| Commit | Full hash | Role |
| --- | --- | --- |
| `efa671a` | `efa671abc18bde1e6c1f942360cb8d957db60729` | G1R2 resolver hardening (impl) |
| `a3da51e` | `a3da51e2c15068d39ddfcac9b30efe4874627d26` | G1R2 independent verification (doc) |
| `640ddd0` | `640ddd060ee1eae364e78b05fbe8b227f7728d94` | **G2 cryptographic-trust architecture (design)** |
| `23d95c8` | `23d95c8a10dc27b678b1c4f7abc5fb7bcd5a9e43` | **G2A canonical-envelope SPEC (design-only, parallel session)** |
| `6ed67ac` | `6ed67acc6c7dcde5befcbabfba35b62bde569341` | **G2A implementation (reviewed here)** |

Unrelated working-tree changes (datasets/, scripts/datasets/, yahboom assets) are pre-existing noise from
other work, were never staged into any G2 commit, and are excluded.

## 2. Deliverable inventory & task-tracker discrepancy

`6ed67ac` contains all six expected deliverables: (1) module `scripts/gnm/h8_trust_envelope.py`;
(2) schema `configs/gnm/h8_trust_envelope_schema.json`; (3) fixture corpus
`tests/gnm/fixtures/h8_trust_envelope/`; (4) tests `tests/gnm/test_h8_trust_envelope.py`; (5) doc
`docs/research/H8_G2A_CANONICAL_TRUST_ENVELOPE.md`; (6) register updates (decision log + failure register).
**The "6 tasks, 0 done" display was stale task-tracker interface state, not omitted deliverables** — all six
are present and byte-verified in the commit. Per the review instruction, this is **not** a finding.

## 3. Canonical representation

JCS (RFC 8785), UTF-8 text, **no third-party library**. Key ordering: UTF-16 code units. Strings: minimal
escaping (`\b\t\n\f\r`, `"`, `\`, `\u00xx`), `/` unescaped, **Unicode NFC normalisation** of keys and
values. Numbers: integers only, shortest decimal; floats/`NaN`/`±Infinity` rejected. Booleans `true`/`false`;
`null` only where schema-nullable. Timestamps RFC 3339 UTC `Z`. Duplicate keys rejected pre-collapse.
Unknown fields rejected. Matches architecture `H8-DCP-067` and spec §4.3; the spec's NFC wording is realised
as normalisation (impl `H8-DCP-085`), confirmed correct here.

## 4. Signed-payload boundary & signature self-reference (critical area) — PASS

The envelope has exactly `{payload, signature_block}`. Canonical bytes = `canonicalise(payload)` **only**;
`signature_block` is excluded. This is a clean **detached-signature** design (non-recursive).

| Field / section | In document canonical bytes? | In future signed bytes (G2B)? | Mutable after signing? |
| --- | :---: | :---: | :---: |
| `payload.*` (all members) | yes | yes | no (any change → new digest) |
| `payload.signature_algorithm` (`ed25519`) | yes | yes | no — algorithm is bound in, blocking substitution |
| `payload.signing_key_id` (`UNAVAILABLE`) | yes | yes | no |
| `signature_block.signature` | **no** | **no** (it *is* the signature) | n/a |
| `signature_block.signing_key_id/…/timestamp_proof` | **no** | no | yes (detached metadata) |

Verified: `canonicalise_payload(env) == canonicalise(env["payload"])`; mutating `signature_block` does not
change signed bytes; the payload digest is independent of `signature_block`; the payload contains **no**
`signature`/`document_digest`/self-digest field. **No self-referential signing boundary** — G2B signing is
unambiguous.

## 5. Strict parser & duplicate-key matrix — PASS

`parse_envelope_strict` uses a JSON `object_pairs_hook` that rejects a repeated key **before** object
construction. Verified rejection (→ `TRUST_ENVELOPE_SCHEMA_INVALID`, no canonical bytes, no digest, no
eligibility) for duplicate keys at: root, `payload`, `repository_identity`, a dependency commitment,
`semantic_identity_profile`, `verification_requirements`, `signature_block`, `extensions`; plus duplicate
`dependency_id` across array entries. A duplicate key whose two representations differ only by Unicode form
(NFC vs NFD) is byte-distinct at parse, then caught at canonicalisation as a post-NFC key collision →
`TRUST_CANONICALISATION_FAILED`.

## 6. Absent / null / UNAVAILABLE — PASS

Three states are distinct and correct: `reference_input` absent (not in bytes) vs `null` (present, different
digest) vs a string value; required `signing_key_id` accepts only `"UNAVAILABLE"` (populated key / `null` /
empty / absent all reject); optional deferred refs accept absent or `"UNAVAILABLE"` only (a real URL / `null`
reject). No absent trust dimension is promoted; `false`/`0`/`[]` never silently pass where the schema types
otherwise (`verification_requirements` waiver rejected; empty `assurance_claims` rejected).

## 7. Unicode/NFC & numeric — PASS (one LOW note)

Unicode: NFD input canonicalises to the NFC digest (keys and values); zero-width characters are preserved
deterministically (not stripped); a carriage return in a string value is rejected. Numeric: `1.0`, `1.5`,
exponent, `NaN`, `±Infinity`, negative-zero-float and leading-zero literals all reject; negative counts
reject; a 10^25 integer canonicalises to shortest decimal. **Cross-language caveat — see F-002.**

## 8. Timestamp & path — PASS (one LOW note)

Timestamps: RFC 3339 UTC `Z` enforced; sub-second, lowercase `z`, numeric offset, missing `Z` all reject;
interval `validity_start ≤ issue ≤ expiry`, `start < expiry` enforced; day > 31 and month > 12 reject; no
timestamp is treated as trusted or fresh. **Calendar-day validity is not fully enforced — see F-001.** Paths:
absolute POSIX, absolute Windows, `..` traversal, `.` component, repeated separators, backslash, empty and
NUL all reject; machine-absolute paths cannot enter canonical identity.

## 9. Intended-use, assurance, version/downgrade, extensions, dependencies — PASS

Intended-use: only `preflight-document`; `capture`/`runtime`/case/whitespace variants reject. Assurance: only
`["content-equivalent"]`; every stronger dimension and mixed lists reject. Version: exact `1.0.0`; previous/
future/missing/empty reject; `digest_algorithm` and `signature_algorithm` downgrades reject; **no
accept-unknown-version**. Extensions: non-critical accepted and canonicalised; any critical extension (or one
naming an absent key) rejects; unknown payload fields reject; reordered extension members are deterministic.
Dependencies: changing path/oid/content-digest/required/semantic-digest changes canonical bytes or rejects;
array order is significant (reordering changes bytes) — every decision-critical change is observable.

## 10. Fixture / production separation & no-authorisation — PASS

`signature_block` members must all be `"UNAVAILABLE"`; any non-sentinel value rejects. No PEM/private-key
material in the corpus. For every valid envelope, `evaluate_envelope` reports `signature_verified`,
`signer_authorised`, `timestamp_verified`, `fresh`, `repository_attested`, `release_approved`,
`semantic_identity_verified`, `attributes_binding_verified`, `preflight_eligible`, `runtime_eligible`,
`capture_eligible` = **false** and `not_revoked` = `"unverified"`. The module exposes no `sign`/
`verify_signature`/`authorise`. Schema conformance is not trust acceptance.

## 11. Independent byte/digest recomputation — PASS (breaks circularity)

An **independent Python canonicaliser** (re-derived from JCS + spec §4.3, not importing the reviewed
`canonicalise`) reproduced, three-way (committed == independent == reviewed): all **9** canonical
micro-vectors (bytes + SHA-256) and all **6** positive-envelope payload digests, plus determinism
(reordered == full, NFC == NFD, null ≠ absent) and the negative-parse spot checks (dup/float/NaN/Inf/BOM).

| Fixture | Committed digest | Reviewed impl | Independent Python | Node.js | Result |
| --- | --- | :---: | :---: | :---: | :---: |
| valid_minimal | `sha256:9e30266771d579f0…` | = | = | = | ✓ |
| valid_full | `sha256:d7d6041d554f904b…` | = | = | = | ✓ |
| reordered_full | = valid_full | = | = | = | ✓ |
| unicode_nfc / unicode_nfd | equal pair | = | = | = | ✓ |
| reference_input_null | ≠ minimal | = | = | = | ✓ |

## 12. Second-language reproduction (Node.js v22) — PASS (with F-002 caveat)

An independent **Node.js** canonicaliser (built-ins only; integer literals preserved as `BigInt` via the
`JSON.parse` reviver `context.source`) reproduced **byte-for-byte** all 9 canonical micro-vectors (including
the 10^25 integer) and all 6 positive-envelope payload digests, plus reordered == full, NFC == NFD, null ≠
absent, and float rejection. It also demonstrated that a **naïve** `JSON.parse` mis-serialises 10^25 →
`F-002`. Java 11 is also available but not required. **Cross-language byte identity is confirmed.**

## 13. Fixture-vector corpus inventory & integrity — PASS

6 positive + 34 negative envelope vectors + 9 canonical micro-vectors. Catalogue integrity: every referenced
file exists; no stale/unreferenced file; no duplicate fixture id; every positive carries a pinned
`expected_canonical_digest`; no negative carries one; every negative carries an expected reason code. Anchors:
`catalogue.json` = `sha256:23acf0cc4a13c8a9664b30849c0f715849081044748eb05a05ea6a540a17d45e`;
`canonical_vectors.json` = `sha256:f86f0d0684f93c714684c05e69a5402bf461ef4372433b2cd52c6bdcbedabf86`. Raw
byte vectors (dup/float/NaN/Inf/BOM/non-object/CR) are committed as `.raw` (not serializer-producible).

## 14. Environment independence & regression — PASS

Canonical bytes depend only on schema content (cwd/machine-root independent — verified). Regression:
**H8 files in isolation 328/328 pass** (resolver 107 + provider + evidence-schema + trust-envelope 146);
resolver byte-identical to `efa671a`; Level-1 recorded-mode `config_valid=true`, `scene_identity_pass=true`,
`cl_bound_xy=6.0`; dataset dry-run 25/25 (provider `test_41_42`); Level-1 five-file hashes unchanged
(`test_43`). The full `tests/gnm/` run shows 4 failures that are **unrelated to G2A** — 2 `yahboom` asset
tests (different subsystem, pre-existing working-tree state) and 2 H8 import-scanners (`test_35_38`,
`test_25`) that assert `torch`/`cv2`/`isaacsim` are absent from `sys.modules`, polluted by the yahboom tests
importing them earlier in the same process. In isolation those two import-scanners pass.

## 15. Findings

### `H8-G2AREV-F-001` — Timestamp calendar-day validity not enforced — **LOW**

- **Requirement:** timestamp syntax validation (spec §4.2/§6).
- **Observed:** `_check_timestamp` range-checks month 1–12 and day 1–31 only; calendrically-impossible dates
  (`2026-02-30`, `2026-04-31`) are accepted when the validity interval is consistent.
- **Reproduction:** set `validity_start=issue_time=2026-02-30T00:00:00Z`, `expiry=2026-02-30T01:00:00Z` →
  `document_conformant=true`.
- **Root cause:** no month-specific day-count / leap-year check.
- **Trust impact:** **none at G2A** — the timestamp is untrusted, syntax + interval only, never parsed to a
  real instant or used for freshness; the ordering tuple `(y,mo,d,h,mi,s)` remains consistent.
- **Containment:** fail-closed-neutral.
- **Remediation:** G2C (trusted time) MUST enforce true calendar validity before consuming timestamps;
  optionally tighten in a bounded G2A remediation.
- **G2B eligibility effect:** none (non-blocking).

### `H8-G2AREV-F-002` — Cross-language big-integer parsing caveat — **LOW**

- **Requirement:** cross-language canonical-byte reproduction (spec §7 v12).
- **Observed:** the `scalars` canonical micro-vector contains `10^25` (> 2^53). A naïve second-language JSON
  parser (JS `JSON.parse`) silently corrupts it; correct reproduction needs an arbitrary-precision / big-int
  parser (demonstrated working in Node via `BigInt` + reviver `context.source`).
- **Root cause:** JSON has no integer-width bound; some language default parsers use IEEE-754 doubles.
- **Trust impact:** **none for real envelopes** — every H8 envelope integer is a small count; no envelope
  field uses integers beyond 2^53.
- **Containment:** the reviewed Python and the Node reproduction both handle it correctly.
- **Remediation:** document in the corpus README that canonical integers require arbitrary-precision handling
  across languages (or bound integer magnitude); consider adding a big-int guidance note.
- **G2B eligibility effect:** none (non-blocking).

No Critical, High or Medium findings.

## 16. Reason-code review — PASS

Exactly `TRUST_OK`, `TRUST_ENVELOPE_SCHEMA_INVALID`, `TRUST_CANONICALISATION_FAILED` are defined/emitted;
disjoint from the resolver's `REASON_CODES` (unchanged at **41**). Signature/key/trusted-time/revocation/
attestation codes remain design-only (not defined in the module). A float reaching canonicalisation →
`TRUST_CANONICALISATION_FAILED`; all schema failures → `TRUST_ENVELOPE_SCHEMA_INVALID`, with no canonical
output and no eligibility.

## 17. Verdicts

| Dimension | Verdict |
| --- | --- |
| Strict parser | **PASS** |
| Schema & downgrade controls | **PASS** |
| Canonical byte determinism | **PASS** |
| Cross-language interoperability | **PASS** (F-002 big-int caveat documented) |
| Fixture / production separation | **PASS** |
| No-authorisation boundary | **PASS** |
| Documentation | **PASS WITH MINOR FINDINGS** (F-001, F-002; add big-int README note) |
| **Overall G2A independent review** | **PASS WITH DOCUMENTED LIMITATIONS** |

## 18. G2B eligibility

**ELIGIBLE FOR G2B FIXTURE-KEY AND VERIFIER-STUB DESIGN.** All criteria met: no unresolved Critical/High;
duplicate keys reject before mapping construction; signed-payload boundary precise and non-recursive
(detached); canonical bytes independently reproduced (Python) and reproduced in a second language (Node);
fixture evidence non-production; all trust dimensions false/unverified; runtime and capture eligibility
false; no real key or signature material. Eligibility authorises only a separately-scoped G2B design or
fixture-only implementation gate — not production keys, signing services, observers, Isaac or capture.

## 19. KPIs

| KPI | Result |
| --- | --- |
| G2A requirement review coverage | 100% |
| Duplicate-key rejection | 100% (9 depths + array + NFC-collision) |
| Absent/null/UNAVAILABLE distinction | 100% |
| Unicode/NFC determinism | 100% |
| Numeric-rule enforcement | 100% |
| Timestamp-syntax enforcement | 100% (calendar-day = F-001 LOW) |
| Version/downgrade rejection | 100% |
| Intended-use escalation rejection | 100% |
| Assurance escalation rejection | 100% |
| Canonical-byte determinism | 100% |
| Canonical-digest determinism | 100% |
| Independent recomputation agreement | 100% (Python) |
| Second-language vector agreement | 100% (Node; F-002 big-int caveat) |
| Fixture protected-mode rejection | 100% |
| Runtime eligibility | 0 |
| Capture eligibility | 0 |
| Keys created | 0 |
| Signatures created | 0 |
| Runtime operations | 0 |
| Resolver regression | 100% (107/107) |
| Dry-run | 25/25 |
| Level-1 hashes | 5/5 unchanged |
| Boundary violations | 0 |
| Ruff | Open (unavailable) |

## 20. SWOT

- **Strengths:** strict duplicate-key parser (reject-before-collapse); deterministic JCS+NFC canonical bytes;
  clean detached signed-payload boundary; explicit version/extension policy; fixture-only vectors;
  non-authorising result model; independently + cross-language reproduced bytes.
- **Weaknesses:** no signer/verifier/trusted-time/revocation (by design, future gates); calendar-day laxity
  (F-001); cross-language big-integer caveat (F-002); canonicaliser is standard-library and language-specific
  parsers differ on big integers; Ruff unavailable.
- **Opportunities:** portable fixture-only verifier stubs; public canonicalisation vectors; a second-language
  reference canonicaliser as a permanent CI check; reusable trust-envelope format.
- **Threats:** cross-language canonicalisation disagreement (mitigated here); big-integer/Unicode ambiguity;
  premature claims of cryptographic authenticity; fixture-key promotion (blocked by sentinel policy).

## 21. Verdict & recommendation

**Overall: PASS WITH DOCUMENTED LIMITATIONS.** G2A supports all twelve bounded claims. Two LOW findings
(F-001 calendar-day, F-002 big-integer cross-language) are non-blocking and belong to G2C / documentation.
**Recommendation:** proceed to **G2B fixture-only key and verifier-stub design/implementation** (no
production keys, no signing service, no external service, no observers, no Isaac, no capture); optionally
fold a bounded G2A remediation (calendar-day check + big-int README note) into that work. The reviewed
implementation is correct, deterministic and interoperable within its stated boundary.
