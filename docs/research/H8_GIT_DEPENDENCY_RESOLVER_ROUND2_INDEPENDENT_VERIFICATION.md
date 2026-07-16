# H8 Git Dependency Resolver — G1R2 Independent Verification

**Gate:** G1R2 Independent Verification — focused, adversarial, **review-only**.
**Commit verified:** `efa671abc18bde1e6c1f942360cb8d957db60729` ("Complete H8 Git resolver boundary hardening").
**Branch:** `h23-execfix` (local, never pushed; 0 tags on HEAD). **git 2.34.1. Ruff unavailable (Open).**
**Claim boundary:** `SYNTHETIC_DIAGNOSTIC_ONLY`. No Isaac/Omniverse/ROS 2/render/drive/capture/inference/
training; no signing/keys/revocation/trusted-time/origin-attestation. **This is not Level 3.** Real
hospital footage & trajectory collection remains blocked.

This verification independently reconstructs behaviour from Git, source and temporary-repository probes,
comparing the pre-G1R2 module (`git show 2de2ee7:…`) against the current module. It changed **no** resolver,
provider, manifest, schema, test or configuration file. It does **not** re-author earlier documents.

---

## 1. Baseline

| Item | Value |
| --- | --- |
| HEAD | `efa671abc18bde1e6c1f942360cb8d957db60729` |
| Branch | `h23-execfix`, no upstream, not in `git branch -r` |
| Prior commits | `78703fded466…` (re-review), `2de2ee71d9e6…` (G1R), `b8e5204537…`, `250c88f…` — unchanged ancestors, not amended |
| Working tree | review-target files byte-identical to `efa671a`; 352 dirty entries are pre-existing unrelated noise, excluded |
| Author/committer | Frank Asante Van Laarhoven — no trailers, no vendor/AI attribution |

## 2. Findings under verification (from `…_REMEDIATION_ROUND2.md`)

`H8-G1RREV-F-001` (mandatory-set presence-only, Med), `-F-003` (`GIT_*` env not scrubbed, Low), `-F-004`
(imprecise docs, Info), `-F-002` (semantic identity, Low). Decisions `H8-DCP-063…066`; challenge `H8-C-042`.

## 3. Remediation → code mapping (diff `78703fd..efa671a`)

All documented controls exist in executable code: reason codes `MANDATORY_DEPENDENCY_NOT_REQUIRED`,
`MANIFEST_DUPLICATE_DEPENDENCY`, `GIT_ENV_UNSUPPORTED`; `_GIT_ENV_REMOVE`/`_GIT_ENV_REMOVE_PREFIXES`/
`_GIT_ENV_FORCE`/`_GIT_ENV_PROHIBITED`; `_build_git_env`/`_prohibited_git_env`; `load_dependency_manifest`
`duplicate_code`; the `resolve_canonical` env-reject + exact-`required is True` checks; runner env swap.

## 4. Pre-remediation reproduction (against `2de2ee7`)

Mandatory `h8-evidence-provider` weakened + dirtied: `required` ∈ {`false`, `null`, `0`, `[]`, `{}`} →
**ACCEPTED** (bug); `missing`/`1`/`"true"`/`"false"` were required by truthiness accident. Confirmed exactly.

## 5. Exact-Boolean enforcement (current) — VERIFIED

Every non-`True` form of `required` on a mandatory id rejects with **`MANDATORY_DEPENDENCY_NOT_REQUIRED`**:
`false`, missing, `null`, `0`, `1`, `"true"`, `"false"`, `[]`, `{}`. Only exact boolean `True` accepts
(baseline clean → `ACCEPTED`). The check is `by_id[i].get("required") is not True` — an identity test, so
truthiness (`1`, non-empty string) is insufficient. Python `bool` cannot be subclassed, so no Boolean
subclass bypass exists. The manifest is JSON (not YAML); duplicate JSON keys are collapsed by the parser
before validation (documented parser-level limitation) but duplicate **dependency ids** are still caught
after parsing (§6). A non-mandatory dependency may legitimately be `required:false`.

## 6. Duplicate dependency-ID — VERIFIED

Duplicate `h8-resolver` — identical, conflicting-`required`, different-path, one-optional — all →
**`MANIFEST_DUPLICATE_DEPENDENCY`** (fail closed, no last-write-wins). A case-variant id (`H8-Resolver`) is a
**distinct** id, so the real mandatory id becomes absent → `MANIFEST_INCOMPLETE` (does not satisfy the set).

## 7. Mandatory identity — VERIFIED (with documented F-002 limitation)

Enforced: exact id, exact `required: true`, presence of the fixed mandatory set, self-listing at the
canonical path, duplicate-freedom. Path pointing at a path with **no committed file** → fail closed. Path
re-pointed at **another tracked/clean file of the expected type** → **ACCEPTED** — the resolver binds
`path + tracked + clean + HEAD`, **not** content/semantic identity (`H8-G1RREV-F-002`). This is kept explicit
(dedicated test + docs); **not** disguised as solved. No claim of full semantic program-dependency discovery.

## 8. Git child-environment — VERIFIED

Table (parent → child):

| Variable | Inherited | Removed | Forced | Rejected-if-present | Rationale |
| --- | :--: | :--: | :--: | :--: | --- |
| `PATH`, `HOME` | ✓ | | | | ordinary — git must execute |
| `LC_ALL`, `LANG` | | | ✓ (=C) | | deterministic parser locale |
| `GIT_CONFIG_NOSYSTEM`, `GIT_ATTR_NOSYSTEM`, `GIT_OPTIONAL_LOCKS` | | | ✓ | | ignore system config/attrs; no locks |
| `GIT_CONFIG_GLOBAL` | | ✓ | ✓ (=/dev/null) | ✓ | neutralise hostile `~/.gitconfig` |
| `GIT_DIR`, `GIT_WORK_TREE`, `GIT_COMMON_DIR`, `GIT_INDEX_FILE`, `GIT_OBJECT_DIRECTORY`, `GIT_ALTERNATE_OBJECT_DIRECTORIES`, `GIT_REPLACE_REF_BASE`, `GIT_NAMESPACE`, `GIT_CONFIG_SYSTEM`, `GIT_CONFIG_COUNT` | | ✓ | | ✓ | redirect/inject — scrubbed **and** rejected |
| `GIT_CONFIG_KEY_*`, `GIT_CONFIG_VALUE_*` | | ✓ (prefix, all indices) | | ✓ | `-c`-via-env injection vector |
| `GIT_CEILING_DIRECTORIES`, `GIT_DISCOVERY_ACROSS_FILESYSTEM`, `GIT_LITERAL/GLOB/NOGLOB/ICASE_PATHSPECS` | | ✓ | | | neutralised (scrub); repo via `-C`, paths via `--` |

`GIT_CONFIG_KEY_{0,1,7,99}` all removed+rejected (wildcard family, not only index 0).

**Behavioural probes (§10/§11/§12):**
- 11/11 prohibited redirection/injection vars → `GIT_ENV_UNSUPPORTED` (fail closed).
- Scrubbed-only vars (pathspec/ceiling/discovery) → neutralised: still `ACCEPTED`, closure digest unchanged.
- Parent locale `en_US.UTF-8` → forced to C → closure digest unchanged.
- **Hostile `GIT_DIR` proof:** repo A (canonical clean) + decoy B; `GIT_DIR=B/.git` → `resolve_canonical(A)`
  rejects (`GIT_ENV_UNSUPPORTED`); the runner, **bypassing** the reject, still resolves **A**'s git-dir
  (scrubbed, not B). B never satisfies A's closure.
- 4/4 combined attacks (`GIT_DIR`+`GIT_INDEX_FILE`; object-dir+alternates; config-inject+pathspec;
  replace-base+alternates) → rejected.

## 9. Committed `.gitattributes` / filter limitation (§13)

`GIT_ATTR_NOSYSTEM=1` + config-nosystem/global-devnull neutralise **system/global** attributes and filters.
A **repository-local committed** `.gitattributes` + clean filter is still honoured by git; in git 2.34.1 an
attempted clean-filter mask of a mandatory dep did **not** succeed (the dep was still reported
`DEPENDENCY_WORKTREE_MODIFICATION`), but this is **not** claimed as exhaustive elimination — committed filter
influence remains the documented residual **`H8-C-040`** (author/committed-artifact boundary, deferred).

## 10. Positive clean path — VERIFIED (not test-specific)

On the **real repository** (canonical internal factory, canonical tracked manifest, no fixture resolver, no
monkeypatch, no bypass, no fixture-only env): all mandatory deps clean → `ACCEPTED`, bound to HEAD
`efa671a`, canonical manifest selected, closure digest deterministic across repeated runs; provider yields a
non-authorising preflight document; capture prerequisites reject it; backend invocation zero; no evidence
artifact created.

## 11. Caller report/manifest bypass — VERIFIED

`trusted_provider_tree_state` exposes none of `resolver/resolver_factory/report/resolution_report/manifest/
manifest_path/assume_clean/skip_resolution/allow_dirty`; unexpected `report=`/`manifest=`/`resolver=` kwargs
raise `TypeError`; a plain caller report → `REPORT_UNAUTHENTIC`. No caller-driven bypass of fresh internal
resolution.

## 12. Current-state / TOCTOU (§16)

`resolve_canonical` performs one `status --porcelain` pass plus per-dependency plumbing; the protected
provider re-resolves current state on **every** `tree_state()` call. A residual race window remains between
the status pass and provider serialisation (documented `H8-C-033`). No Level-3 or capture claim depends on
this race — a clean resolution authorises only a non-authorising preflight **document**; capture stays
blocked. Complete race elimination is **not** claimed and is deferred to the runtime/observer gates.

## 13. Reason-code coverage (§17)

`REASON_CODES` = 41 (40 active + 1 reserved `REPORT_STALE`). The three G1R2 codes are active and
deterministically triggered: `MANDATORY_DEPENDENCY_NOT_REQUIRED` (§5), `MANIFEST_DUPLICATE_DEPENDENCY` (§6),
`GIT_ENV_UNSUPPORTED` (§8). Each rejection produces zero provider output and zero backend calls.

## 14. Regression (§18)

| Suite / check | Command | Result |
| --- | --- | --- |
| Resolver | `pytest tests/gnm/test_h8_git_dependency_resolver.py` | **107 passed** |
| Provider | `…test_h8_evidence_provider.py` | 41 |
| Provider remediation | `…test_h8_evidence_provider_remediation.py` | 32 |
| Schema | `…test_h8_evidence_schema.py` | 34 |
| Recorded-mode | `…test_h8_synthetic_fork_recorded_mode.py` | 58 |
| Pilot | `…test_h8_synthetic_fork_pilot_config.py` | 11 |
| Full matching H8 | `pytest tests/gnm/test_h8_*.py` | **330 passed** |
| Dataset dry-run | `--mode dataset-dry-run --emit-schema --config …_dataset.yaml` | `all_checks_pass=True`, **byte-identical** |
| Level-1 evidence | `git status --porcelain` | **5/5 byte-identical** |
| `py_compile` | resolver + tests | OK |
| `CL_BOUND_XY` | `h8_evidence_schema.py:40` | **6.0** |
| Attribution / secret | grep | clean |
| Negative-artifact audit | — | no evidence/runtime/dataset dir |
| `git diff --check` | — | clean |
| Ruff | `python -m ruff` | unavailable — **Open** |

The `tests/gnm/test_h8_*.py` glob is the matching H8 suite, **not** the whole repository test suite.

## 15. New findings

- **`H8-G1R2REV-F-001` (INFORMATIONAL):** the Class-C environment rejection (`GIT_ENV_UNSUPPORTED`) fails
  closed whenever a prohibited `GIT_*` variable is present in the parent environment — including a benign CI
  or tooling context that sets one for unrelated reasons. This is the intended conservative, fail-closed
  posture (ambiguous env is never treated as clean) and is additionally backstopped by child-env scrubbing;
  operators should invoke the resolver from a clean environment. No remediation required.

No Critical, High or Medium finding. `H8-G1RREV-F-002` and the crypto/origin/TOCTOU/committed-filter items
remain correctly deferred rather than treated as passing.

## 16. Independent dispositions of the original findings

| Finding | Disposition |
| --- | --- |
| `H8-G1RREV-F-001` (required weakening) | **INDEPENDENTLY VERIFIED CLOSED** — all weakening forms (incl `[]`,`{}`) + duplicate forms reject; baseline clean accepts. |
| `H8-G1RREV-F-003` (`GIT_*` env) | **INDEPENDENTLY VERIFIED CLOSED** (env vector) — scrub + reject + forced-safe proven behaviourally; hostile `GIT_DIR` not redirected. |
| `H8-G1RREV-F-004` (documentation) | **INDEPENDENTLY VERIFIED CLOSED** — caller-manifest boundary now stated precisely. |
| `H8-G1RREV-F-002` (semantic identity) | **OPEN — ACCURATELY BOUNDED** — path-substitution to a tracked expected-type file still accepted; kept visible; content-identity binding deferred to G2. |

## 17. Control verdicts

| Control | Verdict |
| --- | --- |
| Exact mandatory-Boolean enforcement | **PASS** |
| Duplicate-ID protection | **PASS** |
| Mandatory identity enforcement | **PASS WITH DOCUMENTED LIMITATIONS** (content identity → G2) |
| Git child-environment security | **PASS** (committed-filter residual `H8-C-040` is a separate config surface) |
| Trusted resolver/provider integration | **PASS** |
| Documentation | **PASS** |
| **Overall G1R2 independent verification** | **PASS WITH DOCUMENTED LIMITATIONS** |

No unresolved Critical or High non-cryptographic finding.

## 18. G2 design eligibility — **ELIGIBLE FOR G2 CRYPTOGRAPHIC-TRUST DESIGN**

Exact required-Boolean enforcement verified; duplicate ids rejected; canonical positive path verified on the
real repository; hostile Git environment cannot redirect trust decisions (scrub + reject, behaviourally
proven); caller report/manifest bypasses remain blocked; no unresolved Critical/High non-cryptographic
finding; preflight non-authorising; backend invocation zero; cryptographic and origin residuals explicitly
deferred. Eligibility authorises **only** a separately scoped G2 architecture/design gate — **not** G2
implementation, observers, Isaac or capture.

## 19. KPIs

| KPI | Result |
| --- | --- |
| G1R2 requirement review coverage | 100% |
| Exact required-Boolean rejection | 100% (9/9 weakening forms) |
| Duplicate-ID rejection | 100% |
| Mandatory identity rejection | 100% (id/required/category/duplicate; content identity → G2) |
| Git-environment attack rejection/neutralisation | 100% |
| Combined environment attack rejection | 100% (4/4) |
| Hostile `GIT_DIR` non-redirection | 100% |
| Caller-report / caller-manifest rejection | 100% |
| Canonical positive-path acceptance | 100% (real repo) |
| Deterministic closure digest | 100% |
| Preflight capture rejection | 100% |
| Blocked-case provider output / backend calls | 0 / 0 |
| Resolver / Provider / Schema / Recorded-mode regression | 107 / 41 / 34 / 58 |
| Matching H8 regression | 330/330 |
| Dry-run | `all_checks_pass=True`, byte-identical |
| Level-1 evidence | 5/5 unchanged |
| Boundary violations | 0 |
| Ruff | Open (unavailable) |

Cryptographic authentication, trusted timestamps, revocation, physical-origin proof, exhaustive semantic
discovery, full TOCTOU elimination and Level 3 are **not** counted as passing.

## 20. SWOT

- **Strengths:** strict required-Boolean semantics; duplicate-ID rejection; policy-bound mandatory
  identities; explicit scrubbed+rejected Git child environment; trusted resolver construction; canonical
  manifest enforcement; deterministic non-authorising preflight; real-repo positive path.
- **Weaknesses:** no cryptographic report authentication; semantic dependency completeness curated (not
  discovered); committed attribute/filter influence partly unresolved (`H8-C-040`); residual TOCTOU; bounded
  to git 2.34.1; Ruff unavailable.
- **Opportunities:** signed resolver reports; trusted timestamps; revocation; release/repository attestation;
  generated semantic dependency graph; reusable provenance framework.
- **Threats:** a newly introduced dependency omitted from `REQUIRED_DEPENDENCY_IDS`; a future Git env var not
  covered; committed filter-policy manipulation; persisted-report forgery before G2; identical-history
  origin impersonation; future provider bypass; premature Level-3 claims.

## 21. Remaining G2-owned limitations

Cryptographic report authentication; trusted timestamps; revocation; repository/release attestation;
physical/organisational origin proof; semantic per-dependency content identity (`H8-G1RREV-F-002`); committed
`.gitattributes`/filter influence (`H8-C-040`); residual TOCTOU. **This is not Level 3.** Levels 3–5
unproven; real hospital footage & trajectory collection remains blocked.
