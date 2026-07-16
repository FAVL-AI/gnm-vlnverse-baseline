# H8 G2 — Cryptographic Trust Architecture & Design

**Gate:** G2 — Cryptographic Trust Architecture and Design. **Design / specification / threat-model /
future-test-planning ONLY.**
**Baseline verified commit:** `a3da51e2c15068d39ddfcac9b30efe4874627d26` (G1R2 independent verification).
**G1R2 implementation:** `efa671abc18bde1e6c1f942360cb8d957db60729` (resolver byte-identical).
**Branch:** `h23-execfix` (local, unpushed, 0 tags).
**Claim boundary:** `SYNTHETIC_DIAGNOSTIC_ONLY`. **No cryptographic keys/signatures/certificates/tokens are
created; no signing/verification/revocation/timestamp service is implemented; no observer, Isaac, ROS 2,
render, drive or capture capability is introduced.** **This is not Level 3.** Real hospital footage &
trajectory collection remains blocked. Nothing here is an operational control — every item below is a
*design requirement* for a **future** bounded implementation gate.

---

## 1. Gate objective (§1)

Design the trust architecture that will transform the current in-process Git dependency-resolution report
into **externally verifiable, freshness-bound, revocable** evidence, specifying how future implementations
provide: (1) cryptographic authenticity for resolver reports; (2) authorised resolver/producer identities;
(3) trusted timestamping/freshness; (4) signing-key lifecycle; (5) report/key/producer/policy revocation;
(6) repository/release attestations; (7) origin claims with explicit assurance levels; (8) semantic
per-dependency identity; (9) `.gitattributes`/filter-policy binding; (10) safe verification before any
runtime/capture decision. **None of these is claimed operational.**

## 2. Research question (§2)

> What cryptographic trust architecture is required to prove that an H8 dependency-resolution report was
> created by an authorised resolver, for the intended repository and dependency closure, at a trustworthy
> time, under a non-revoked policy and key, without allowing copied history, persisted-report forgery or
> semantic dependency substitution to authorise runtime or capture progression?

## 3. Falsifiable hypothesis (§3, design-only)

> A versioned signed-envelope protocol — using externally authorised resolver identities, canonical signed
> bytes, trusted time, explicit revocation, repository/release attestations and policy-bound semantic
> dependency identities — can make forged, stale, revoked, copied-origin or semantically substituted
> resolver reports fail closed before runtime or capture authorisation.

## 5. Evidence boundary (§5)

**Establishes:** trust requirements; signing-envelope design; key/identity policy; trusted-time
architecture; revocation architecture; repository/release attestation design; semantic dependency-identity
design; future implementation/review decomposition. **Does NOT establish:** valid signatures; trusted time;
operational revocation; repository-origin authenticity; runtime/Isaac/render/drive/dataset/model validity;
capture authorisation. **Not Level 3.**

## 6. Trust-domain model (§6)

Distinct identities — never collapsed into one "trusted service":

| Domain | Identity | Authority | Trust assumption | Credential | Compromise impact | Revocation path | May issue | Must NEVER issue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Source repository | repo-policy ID + root_commit | defines canonical repo | history authentic-if-attested | — (attested externally) | wrong closure trusted | release-attestation revoke | content identity | capture auth |
| Approved release | release/commit attestation ID | approves a commit/closure | release key uncompromised | signing key | unapproved code trusted | key/attestation revoke | release approval | resolver signature |
| Git resolver | `RESOLVER_ID`/version | resolves closure deterministically | code integrity | resolver-report key | forged resolution | key revoke | signed resolution report | runtime/capture eligibility |
| Resolver host | workload/host ID | executes resolver | host not compromised | host/workload attestation | host-forged evidence | host-attestation revoke | host attestation | signatures |
| Producer/provider | producer ID (existing `check_production_trust`) | packages evidence | producer authorised | producer registration | fixture-as-prod | producer revoke | preflight document | capture token |
| Signing authority | intermediate CA/KMS ID | issues/authorises keys | key custody sound | root/intermediate key | mass forgery | key hierarchy revoke | key authorisation | reports directly |
| Timestamp authority | TSA ID | asserts time | TSA clock/keys sound | TSA key | stale/forward-dated evidence | TSA-key revoke | timestamp proof | reports |
| Revocation authority | revocation-policy ID | publishes revocations | availability + integrity | revocation-signing key | suppressed revocation | supersede + emergency | revocation records | reports |
| Policy authority | trust-policy ID/version | defines who/what is trusted | policy integrity | policy-signing key | trust-root swap | policy version revoke | policy versions | signatures |
| Runtime observer | observer ID (existing `validate_runtime_observer`) | attests runtime facts | observer authentic | observer-signing key | fake runtime validity | observer revoke | runtime evidence (G3+) | preflight signatures |
| Capture-auth authority | capture-policy ID | authorises capture (G9+) | strict gating | capture-signing key | unauthorised capture | capture-token revoke | capture token (future) | resolver reports |
| Verifier | verifier build ID | independent verification | verifier integrity, no signing key | trust roots (public) | false-accept | verifier version pin | accept/deny decision | any signature |
| Audit/evidence store | store ID | append-only record | tamper-evidence | store credential | history rewrite | store rotation | inclusion proof | trust decisions |

## 7. Assurance levels (§7)

Monotone ladder; **no level alone authorises capture**:

1. **Content-equivalent** — expected commits/blobs/closure present (what G1R2 already establishes).
2. **Release-attested** — an authorised release identity attests the commit/closure is approved.
3. **Resolver-authenticated** — an authorised resolver identity signed the report over canonical bytes.
4. **Host-attested** — the resolver ran on a recognised host/workload identity.
5. **Organisationally authorised** — resolver+host+release belong to an approved org trust domain.
6. **Runtime-authorised** — evidence is *eligible* for later runtime validation under an approved runtime
   policy (established only at G3+, never by a resolver report).

Required minima: **preflight evidence** → ≥ Resolver-authenticated (levels 1–3); **runtime-observer
evidence** → Host-attested + Organisationally authorised (levels 1–5) — deferred to G3+; **capture
consideration** → Runtime-authorised (level 6) **plus** a separate capture-authority token — deferred to
G9+. A signed resolver report reaches at most level 3 and remains preflight-only.

## 8. Signed resolver-report envelope (§8)

Versioned envelope `h8-trust-envelope/1.0.0` binding (signature covers the canonical bytes of the `payload`,
never a language object): `envelope_version`; `report_schema_version`; `resolver_id`; `resolver_version`;
`resolver_trust_policy_version`; `repository_policy_id`; `repository_identity {canonical_name, root_commit}`;
`head_commit`; `canonical_manifest_path`; `canonical_manifest_digest`; `manifest_schema_version`;
`manifest_schema_digest`; `closure_digest`; `mandatory_dependency_count`; `accepted_count`; `rejected_count`;
`unresolved_count`; `per_dependency_identity_commitments[]` (§18); `git_env_policy_version`; `git_version`;
`issue_time`; `validity_start`; `expiry`; `report_id` (unique) + `nonce`; `signing_key_id`;
`signature_algorithm`; `revocation_policy_version`; `timestamp_proof_ref`; `assurance_claims[]`. The
signature block (`signing_key_id`, `signature_algorithm`, `signature`, `timestamp_proof`) sits **outside**
the signed `payload`; `report_id`/`nonce`/`issue_time`/`validity_start`/`expiry` are **inside** it.

## 9. Canonical signed bytes (§9)

Rules: UTF-8; lexicographic key ordering; integers as shortest decimal, **no floats permitted** in the
signed payload (durations/coords expressed as integers or decimal strings — consistent with the existing
`_closure_digest` which already excludes volatile metadata); `null` only where schema-typed; Unicode NFC;
POSIX forward-slash repo-relative paths; RFC 3339 UTC `Z` timestamps; **duplicate keys rejected**;
unknown/extra fields **rejected** (no "accept unknown version"); explicit `extensions` object for growth;
schema-version bound into the signed bytes.

**Options evaluated:** (A) **JSON Canonicalization Scheme, RFC 8785 (JCS)** — JSON-native, matches the
existing JSON evidence envelopes, mature multi-language libraries, human-auditable; float-handling caveat
mitigated by prohibiting floats. (B) **Deterministic CBOR, RFC 8949 §4.2 core-det** — compact, unambiguous,
good for embedded/HSM, less human-readable. (C) **Protobuf deterministic serialisation** — schema-first,
fast, but "deterministic" is not canonical across languages/versions and is discouraged for signing.
**Decision:** **JCS (RFC 8785)** for research, prioritising cross-language reproducibility + JSON continuity
+ auditability; **deterministic CBOR** documented as the migration option if envelope size/embedded
verification becomes a constraint. Protobuf rejected for signed bytes. (Decision `H8-DCP-067`.)

## 10. Signature algorithm (§10)

| Algorithm | Assumptions | Deterministic | Sig size | Availability | HW-backed | Interop | Misuse resistance |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Ed25519** | EdDSA/Curve25519 | yes (built-in) | 64 B | very wide | growing (TPM2/PKCS#11) | high | strong (no nonce reuse) |
| ECDSA P-256 | NIST curve | only w/ RFC 6979 | ~64–72 B | universal | universal (KMS/HSM/TPM) | highest (FIPS) | nonce-reuse foot-gun |
| RSA-PSS 3072 | RSA | randomised | ~384 B | universal | universal | high | padding pitfalls |

**Decision:** initial **Ed25519** (deterministic, small, misuse-resistant, no per-sig nonce risk); **migration
path ECDSA P-256 (RFC 6979 deterministic)** for FIPS/KMS/HSM environments that mandate NIST curves. RSA-PSS
retained only as a legacy-interop fallback. `signature_algorithm` is an explicit signed field; **downgrade
to an unlisted/weaker algorithm fails closed** (`TRUST_SIGNATURE_INVALID`/policy reject). **No key created.**
(Decision `H8-DCP-068`.)

## 11. Key hierarchy (§11)

Distinct keys, least-privilege, no cross-authority:

```
Root trust / policy authority (offline)
 ├─ Intermediate signing authority
 │   ├─ Release-attestation key        (approves commits/closures)
 │   ├─ Resolver-report signing key    (signs §8 envelopes)     ← cannot sign runtime/capture
 │   ├─ Timestamp-authority key
 │   ├─ Runtime-observer signing key   (G3+)
 │   └─ Capture-authorisation key      (G9+)
 └─ Fixture/test keys (namespaced h8-fixture-*, isolated, never in production trust roots)
```

Each key: permitted usages (single purpose), key ID, validity period, rotation cadence, storage,
activation/suspension, revocation, destruction, audit. A resolver-report key **must not** be usable for
runtime-observer or capture-authorisation signing (usage bound in cert/policy + verifier `TRUST_KEY_USAGE_
INVALID`). (Decision `H8-DCP-069`.)

## 12. Key storage & execution identity (§12)

| Store | Research-dev | CI | Enterprise prod |
| --- | :--: | :--: | :--: |
| HSM (PKCS#11) | — | — | ✓ primary |
| Cloud KMS | — | ✓ | ✓ |
| TPM-backed | ✓ optional | — | ✓ optional |
| OS keystore | ✓ | — | — |
| Workload identity + remote signing (keyless) | — | ✓ preferred | ✓ |
| Local encrypted key file (age/sops, outside repo) | ✓ fallback | — | — |
| **Repository-stored private key** | **REJECTED** | **REJECTED** | **REJECTED** |

Fixture/test keys: `h8-fixture-*` namespaced, isolated, structurally incapable of authorising production
evidence, excluded from production trust roots (mirrors the existing fixture-resolver / producer-policy
deny-by-default). **Selected:** research-dev = OS keystore / TPM (local encrypted file as fallback);
production = HSM or cloud KMS with workload-identity keyless signing in CI. (Decision `H8-DCP-070`.)

## 13. Resolver authentication boundary (§13)

The resolver **never accepts a caller-selected key** (extends the G1R `trusted_provider_tree_state` no-
injection principle). Conceptual flow:

```
trusted resolver factory → canonical dependency resolution → trust-policy lookup
→ approved signing identity selection (policy maps resolver_id → permitted key_ids)
→ external signing operation (KMS/HSM/keystore; resolver never holds raw private key in prod)
→ signed resolver envelope → independent verification
```

Policy chooses the key (not the caller/report); unsupported/revoked keys → fail closed; signing failure →
`unsigned`/blocked, never a silent accept; **unsigned reports are classified preflight-*unauthenticated* and
may not progress past preflight**; persisted reports are re-verified (signature+time+revocation) **before
use**. **No report field self-declares an authorised key** (defeats the F-001-class self-declaration).
(Decision `H8-DCP-071`.)

## 14. Trusted-time architecture (§14)

Separate clocks: local wall clock (untrusted), monotonic process clock (ordering only), Git commit time
(**never** freshness proof), simulator time (**never** freshness proof), signed TSA time, verification time.
Policy fields: `issue_time`, `observation_time`, `validity_start`, `expiry`, `max_report_age`,
`allowable_clock_skew`, `timestamp_proof`, offline-verification rule, stale-cache handling, authority-
unavailable → **deny**, backward-clock detection. **Options:** RFC 3161 TSA; cloud trusted-time; signed
transparency-log inclusion time (e.g. Rekor); secure workload-clock attestation. **Staged decision:**
research = local monotonic + explicitly-`untrusted` time (freshness NOT claimed) → CI = transparency-log
inclusion time → production = RFC 3161 TSA and/or attested workload clock. **Git/sim time never trusted for
freshness.** (Decision `H8-DCP-072`.)

## 15. Revocation architecture (§15)

Revocable subjects: signing key; resolver identity; producer identity; repository/release attestation;
report ID; policy version; dependency manifest; runtime observer; capture token. Record: `{subject_type,
subject_id, effective_time, reason_code, supersedes, authority_sig}`. Distribution: signed revocation
bundle + offline cache with `max_cache_age`. **Fail-closed:** unavailable or stale-beyond-policy revocation
status → **deny progression** (`TRUST_REVOCATION_STATUS_UNAVAILABLE`). Emergency revocation channel;
supersession; audit trail; explicit effective time and reason. (Decision `H8-DCP-073`.)

## 16. Repository & release attestation (§16)

Distinguish: arbitrary copy of valid history ≠ approved repository ≠ approved release ≠ authorised org
source. **Remote URL alone insufficient; folder path alone insufficient; a signed commit authenticates an
authoring key, not necessarily the executing repo or release approval.** Options: signed Git commits; signed
Git tags; Sigstore/transparency-backed attestations; in-toto attestations; SLSA provenance; CI-issued
release attestations; repository-host identity; internal CA attestations. **Selected initial model:** signed
Git **tags** (Ed25519/SSH-sig) marking approved commits/closures + a CI-issued **in-toto/SLSA provenance**
attestation binding the release; **stated limitation** — this proves an authorised release **key** approved a
commit, not the *physical* origin of any given clone (that is §17). Production migration → Sigstore + Rekor
transparency. (Decision `H8-DCP-074`.)

## 17. Physical & organisational origin (§17)

Separate: content identity ≠ signing identity ≠ workload identity ≠ host identity ≠ network location ≠
organisational ownership ≠ physical machine identity. **A cryptographic signature alone does NOT prove
physical machine origin.** Mechanisms: TPM quotes; cloud workload identity; confidential-computing
attestation; CI workload identity; device certificates; signed build provenance. **Minimum viable H8-research
claim:** *organisationally authorised* = resolver-report key + release attestation both chain to the H8
research trust root (no physical-machine claim). **Stronger future enterprise claim:** host TPM/workload
attestation binding the executing host identity into the envelope. Copied-history impersonation is only
addressed at the *organisationally authorised* level and above, never by content identity. (Decision
`H8-DCP-075`.)

## 18. Semantic per-dependency content identity (§18) — addresses `H8-G1RREV-F-002`

Bounded, curated rules per mandatory class (NO whole-program semantic discovery):

| Dependency class | Git identity | Semantic identity | Signed commitment | Future verifier |
| --- | --- | --- | --- | --- |
| dataset-config | blob digest | schema-version + canonical config digest | `cfg:<sha256>` | schema-validate + digest match |
| dependency-manifest | blob digest | schema-valid canonical content + self-listing | `man:<sha256>` | canonicalise + digest |
| manifest-schema | blob digest | schema ID + digest | `sch:<sha256>` | digest match |
| evidence-schema (`.py`/`.json`) | blob digest | schema ID + version + digest | `evs:<sha256>` | id+version+digest |
| trust policy | blob digest | policy ID + version + digest | `pol:<sha256>` | id+version+digest |
| recorded-mode / drive-validate | blob digest | module ID + interface version + digest | `mod:<sha256>` | id+version+digest |
| expected-routes | blob digest | coord frame + ordered waypoints + `coord_offset` + start/goal binding + digest | `rte:<sha256>` | canonical route digest |
| scene-usda / scene-spec | blob digest | scene ID + scene-file digest + asset-manifest digest | `scn:<sha256>` | scene id + digests |
| level1-drive-manifest | blob digest | manifest ID + digest | `l1m:<sha256>` | id+digest |
| `CL_BOUND_XY` source | blob digest | policy field + value `6.0` | `clb:6.0` | field+value match |
| canonicalisation impl | blob digest | algorithm ID + test-vector-set digest | `can:<sha256>` | algo id + vectors |
| capture validator (future) | blob digest | policy version + impl digest | `cap:<sha256>` | version+digest |

The envelope carries `per_dependency_identity_commitments[]`; substituting a same-type tracked file changes
the **semantic** commitment (schema/policy/route/scene ID mismatch) → `TRUST_SEMANTIC_IDENTITY_MISMATCH`.
This is a **curated** control; it does not claim to discover unknown future dependencies. (Decision
`H8-DCP-076`.)

## 19. `.gitattributes` & filter-policy binding (§19) — addresses `H8-C-040`

Bind into trust identity: repo `.gitattributes` (+ applicable nested), clean/smudge filter config, EOL
policy, working-tree encoding, text/binary attributes, LFS attributes, export-ignore/export-subst.
**Representation distinction:** *Git content identity binds raw blob bytes*; *semantic identity binds
canonical parsed content*; *worktree identity is diagnostic only and must not replace either*. The signed
payload commits to **raw Git blob bytes** for each dependency (independent of clean/smudge filters) **plus** a
digest of the effective `.gitattributes` closure, so an attribute/filter-policy change invalidates the report
(`TRUST_ATTRIBUTES_POLICY_MISMATCH`). LFS objects committed by pointer bind the pointer-oid; materialised-
object verification remains a documented limitation (existing `DEPENDENCY_LFS_UNAVAILABLE`). (Decision
`H8-DCP-077`.)

## 20. Anti-replay design (§20)

Protects against: reuse of an old valid report; replay under a new provider request; cross-repository /
cross-instance reuse; use after key/policy revocation; use after dependency-state change; use after expiry;
duplication across capture attempts. Mechanisms: unique `report_id` + `nonce`; `intended_use` field (e.g.
`preflight-document`); repository+HEAD binding; instance/operation binding where relevant; validity window; a
**consumption registry** (append-only) for one-time reports; per-report one-time-vs-reusable policy;
revocation lookup at verification. **A resolver report authorises preflight verification, not capture.**
(Decision `H8-DCP-078`.)

## 21. Transparency & audit design (§21)

Options: append-only local journal; transparency log (Rekor-style); immutable object storage; tamper-evident
chained DB; external ledger; research-only Git evidence directory. Define append semantics, inclusion proof,
retention, privacy, deletion policy, conflict/duplicate handling, audit access. **Selected:** research =
append-only local journal + optional research-only evidence dir; production = transparency log with inclusion
proofs. Equivocation risk (`split-view`) noted as a threat. **No ledger implemented this gate.** (Decision
`H8-DCP-079`.)

## 22. Verification architecture (§22)

Independent verifier, **distinct from the signer**, holding only public trust roots (no signing key):

```
verify_resolver_envelope(envelope, trust_roots, key_policy, timestamp_policy, revocation_state,
                         repository_attestation_policy, semantic_dependency_policy, expected_use) -> Verdict
```

Returns structured dimensions (schema_conformant, canonical_bytes_valid, signature_valid, signer_authorised,
key_valid, timestamp_trusted, report_fresh, report_not_revoked, repository_attested, release_approved,
dependency_semantics_valid, intended_use_valid, overall_accepted, reason_code). **Any unknown exception →
deny.** Verifier build is version-pinned. (Decision `H8-DCP-080`.)

## 23. Trust decision model (§23)

No single overloaded `valid` Boolean. Dimensions: `document_conformant`, `signature_verified`,
`signer_authorised`, `timestamp_verified`, `fresh`, `not_revoked`, `repository_attested`, `release_approved`,
`resolver_identity_bound`, `dependency_closure_bound`, `semantic_identity_bound`, `intended_use_permitted`,
`preflight_eligible`, `runtime_eligible`, `capture_eligible`. **`preflight_eligible` may become true from a
fully-verified signed report; `runtime_eligible` and `capture_eligible` remain false without G3+/G9+
evidence.** Mirrors the existing evidence-schema multi-dimension design (render_valid/drive_valid,
`document_only` never = capture-gate pass).

## 24. Failure & reason-code taxonomy (§24)

New `TRUST_*` namespace (no collision with existing resolver/provider codes), each with a future
deterministic test: `TRUST_ENVELOPE_SCHEMA_INVALID`, `TRUST_CANONICALISATION_FAILED`,
`TRUST_SIGNATURE_MISSING`, `TRUST_SIGNATURE_INVALID`, `TRUST_SIGNER_UNKNOWN`, `TRUST_SIGNER_UNAUTHORISED`,
`TRUST_KEY_EXPIRED`, `TRUST_KEY_REVOKED`, `TRUST_KEY_USAGE_INVALID`, `TRUST_TIMESTAMP_MISSING`,
`TRUST_TIMESTAMP_INVALID`, `TRUST_TIMESTAMP_UNTRUSTED`, `TRUST_REPORT_EXPIRED`, `TRUST_REPORT_REVOKED`,
`TRUST_POLICY_REVOKED`, `TRUST_REPOSITORY_ATTESTATION_MISSING`, `TRUST_REPOSITORY_ATTESTATION_INVALID`,
`TRUST_RELEASE_NOT_APPROVED`, `TRUST_ORIGIN_ASSURANCE_INSUFFICIENT`, `TRUST_SEMANTIC_IDENTITY_MISMATCH`,
`TRUST_ATTRIBUTES_POLICY_MISMATCH`, `TRUST_REPORT_REPLAYED`, `TRUST_INTENDED_USE_MISMATCH`,
`TRUST_REVOCATION_STATUS_UNAVAILABLE`. These are **design names only** (not yet in `REASON_CODES`).

## 25. Threat model (§25)

Each: mechanism → impact → prevention → detection → containment → residual → owning future gate. Summary
(prevention/owner):

| Threat | Prevention (design) | Owner |
| --- | --- | --- |
| forged report / forged signer | signature over canonical bytes + authorised-key policy | G2A/G2B |
| stolen / expired / revoked key; key-usage confusion | key hierarchy + usage binding + revocation | G2B/G2D |
| algorithm downgrade | explicit signed algo field + allow-list | G2A |
| canonicalisation ambiguity / duplicate JSON keys | JCS + duplicate-key reject | G2A |
| timestamp forgery / stale / TSA compromise | TSA proof + max-age + skew + fail-closed | G2C |
| revocation suppression / stale cache / DoS | fail-closed on unavailable/stale + emergency channel | G2D |
| copied-history impersonation | release attestation + org-origin assurance | G2E |
| forged release attestation | attestation key policy + transparency | G2E |
| workload-identity impersonation / host-attestation replay | host attestation + nonce | G2E (enterprise) |
| report replay / cross-repo / cross-instance | report_id+nonce+repo/HEAD/instance binding + registry | G2A |
| semantic dependency substitution | per-dependency semantic commitments | G2F |
| `.gitattributes` / filter / LFS manipulation | raw-blob binding + attributes-closure digest | G2G |
| manifest / policy downgrade | version binding + no-unknown-version + revocation | G2A/G2D |
| trust-root replacement | offline root + pinned roots in verifier | G2B |
| fixture key promoted to production | namespaced fixture keys excluded from prod roots | G2B |
| signer/verifier collusion | separation of duties + transparency | G2E |
| transparency-log equivocation | inclusion proof + monitoring | G2H |
| premature runtime/capture claim | assurance ladder; report is preflight-only | all |

## 26. Architecture alternatives (§26)

- **Option A — local detached signatures** (resolver signs via protected OS/TPM key): simple, offline; but
  host compromise = key compromise, harder key distribution/revocation.
- **Option B — remote signing service** (resolver sends a digest to an authenticated signer): central policy,
  strong key protection, auditable; adds a network dependency + request-auth surface.
- **Option C — workload identity + transparency-backed keyless signing** (short-lived identity, e.g. Sigstore
  Fulcio + Rekor): CI-native, keyless, transparent, offline-verifiable via roots; higher operational
  complexity.

**Selected — research-dev = Option A** (TPM/OS key, offline, simplest to validate); **future production =
Option C** (keyless workload identity + transparency); **migration A→C** via the versioned envelope +
pluggable key-policy so verifiers accept both trust roots during transition. (Decision `H8-DCP-081`.)

## 27. Separation of duties (§27)

```
Git Dependency Resolver ── unsigned canonical report ──▶ Trust Packaging Service (policy + authorised signing)
   ▶ Timestamp/Transparency Service (freshness + inclusion) ▶ Independent Trust Verifier (sig+time+revocation+attestation)
   ▶ Evidence Provider (preflight DOCUMENT only) ▶ Capture Gate (remains BLOCKED without runtime evidence)
```

The dependency resolver holds **no** capture-authorisation authority.

## 28. Future implementation gates (§28)

G2A canonical signed-envelope schema + test vectors → G2B fixture-only key hierarchy + verifier stubs → G2C
trusted-time adapter (synthetic authority) → G2D revocation data model + fail-closed verifier → G2E
repository/release attestation policy → G2F semantic dependency-identity bindings → G2G `.gitattributes`/
filter binding → G2H combined trust verifier → **independent G2 security review** → G2 remediation →
production-key/external-service readiness design. **No gate introduces Isaac or capture capability.**

## 29. Design-only test plan (§29)

Future tests (all listed §29 items) map to gates: canonical signing vectors + cross-language bytes (G2A);
valid/modified-payload/modified-sig/wrong-key/unknown-key/expired-key/revoked-key/fixture-key-in-protected/
algo-downgrade/duplicate-keys/unknown-extension (G2A/G2B); timestamp-missing/forged/expired/skew (G2C);
revocation-unavailable/stale-cache/report-replay (G2D); repo-mismatch/release-not-approved/copied-history-
without-attestation (G2E); semantic config/route/scene/`CL_BOUND_XY` mismatch (G2F); `.gitattributes`/filter/
LFS mismatch (G2G); intended-use mismatch + **signed report passed directly to capture gate still blocked** +
**signed report non-authorising without runtime evidence** (G2H). Coverage target 100% at each gate.

## 30. Compatibility & migration (§30)

Envelope versioning; algorithm migration (Ed25519→ECDSA-P256); key rotation; trust-root rotation; policy
versioning; verifier backward-compat window; deprecated-schema rejection; historical-report verification via
archived roots; fixture↔production separation; emergency algorithm disablement. **No "accept unknown
version" fallback.** (Decision `H8-DCP-082`.)

## 31. Privacy & data-minimisation (§31)

Excluded from signed/shared reports: absolute filesystem paths; usernames; hostnames; internal network
addresses; secret identifiers; private repository URLs; raw environment variables. Use stable pseudonymous/
policy IDs. Signing does not make unnecessary personal/infrastructure data safe to disclose. (Consistent with
the existing deterministic `closure_digest` excluding host paths.) (Decision `H8-DCP-083`.)

## 32/35. Documentation & traceability

Primary doc = this file. Requirements traceability (target 100%): each §-requirement → trust component →
schema field → policy → threat → future gate → future positive/negative test → status(DESIGN) → limitation.
Every G2 requirement above maps to a domain (§6), an envelope field (§8) or policy (§14/§15/§16/§18/§19), a
threat (§25) and a future gate (§28); status = DESIGN-ONLY for all.

## 36. SMART objectives

1. **Signed evidence architecture** — define the complete envelope + verifier boundary; measurable = every
   signed field + verification dimension mapped to schema and future tests; design-only; prevents persisted-
   report forgery; complete within G2 design. **Status: MET (design).**
2. **Freshness & revocation** — define trusted-time + revocation policies; measurable = every stale/expired/
   revoked/unavailable state has a fail-closed decision; complete before G2 implementation. **Status: MET.**
3. **Origin & semantic identity** — define release/origin assurance + semantic commitments; measurable =
   each mandatory class has an identity rule + assurance requirement; complete before observer/Isaac work.
   **Status: MET (design).**

## 37. KPIs

| KPI | Result |
| --- | --- |
| G2 requirement coverage | 100% (design) |
| Trust-domain coverage | 13 domains |
| Signed-envelope field coverage | 100% (§8) |
| Verification-dimension coverage | 14 dimensions (§23) |
| Threat-to-control mapping | 100% (§25) |
| Key-usage separation | 100% (§11) |
| Revocation-state coverage | 9 subjects (§15) |
| Trusted-time failure coverage | 100% (§14) |
| Mandatory semantic identity coverage | 12 classes (§18) |
| Future implementation ownership | 100% (§28) |
| Runtime operations executed | 0 |
| Cryptographic keys created | 0 |
| Signatures created | 0 |
| Dataset artefacts created | 0 |
| Level-1 hashes preserved | 5/5 |
| Existing H8 regressions | 100% where run (design gate changed no code) |
| Boundary violations | 0 |
| Ruff | Open (unavailable) |

## 38. SWOT

- **Strengths:** independently verified Git resolver; strict canonical manifest; deterministic closure;
  trusted internal construction; explicit non-authorising preflight boundary to build on.
- **Weaknesses:** no cryptographic report auth; no trusted time; no revocation; no external origin proof;
  semantic identity curated; `.gitattributes` binding unimplemented; Ruff unavailable.
- **Opportunities:** signed independently-verifiable evidence; reusable provenance trust layer; transparency-
  backed research evidence; enterprise key management; secure runtime-observer onboarding.
- **Threats:** key compromise; timestamp/revocation failure; copied-history impersonation; algorithm
  downgrade; semantic substitution; fixture-key promotion; premature runtime/capture authorisation.

## 40. Gate verdict

**PASS WITH DOCUMENTED LIMITATIONS** — complete trust architecture; clear signer/verifier separation;
explicit key/time/revocation/attestation/semantic-identity designs; complete future-gate decomposition; **no
cryptographic or runtime operation performed**; unambiguous that a signed resolver report remains
**preflight-only**. All controls are designs, not implementations (§34 challenges).

**Recommended first implementation gate:** **G2A — canonical signed-envelope schema (`h8-trust-envelope/
1.0.0`, JCS) + fixture-only cross-language test vectors** — schema + canonicalisation + deterministic vectors
only, **no real key, no signing, no external service**, independently reviewable — rather than production
signing.
