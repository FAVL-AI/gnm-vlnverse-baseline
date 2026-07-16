# H8 Git Dependency Resolver — Independent Trust-Boundary Re-review (G1R)

**Gate:** G1R Independent Trust-Boundary Re-review — focused, adversarial, **review-only**.
**Commit reviewed:** `2de2ee71d9e69cfefcbe1b92ed4af8ef90d59bca` ("Harden H8 Git resolver trust boundary").
**Branch:** `h23-execfix` (local, never pushed; 0 tags on HEAD).
**Date:** 2026-07-16. **git 2.34.1. Ruff unavailable (Open).**
**Claim boundary:** `SYNTHETIC_DIAGNOSTIC_ONLY`. No Isaac/Omniverse/ROS 2/render/drive/capture/inference/training.
**This is not Level 3.** Real hospital footage & trajectory collection remains blocked.

This review independently reconstructs behaviour from Git, source and temporary-repository probes. It changed
**no** resolver, provider, manifest, schema, test or configuration file. It does **not** re-author the
original implementation (`250c88f`), review (`b8e5204`) or remediation (`2de2ee7`) documents.

---

## 1. Baseline

| Item | Value |
| --- | --- |
| HEAD | `2de2ee71d9e69cfefcbe1b92ed4af8ef90d59bca` (the remediation commit) |
| Branch | `h23-execfix`, no upstream, `git branch -r` shows no `h23-execfix` |
| G1 impl / G1 review | `250c88fa…` / `b8e5204537…` — unchanged ancestors of HEAD |
| Earlier H8 commits | `403c20b`, `dae2bee`, `a449ab6`, `2790250`, `97781ad` — all still ancestors, not amended |
| Working tree | review-target files (resolver, tests, manifest, schema, provider) byte-identical to `2de2ee7`; the 352 dirty entries are pre-existing unrelated noise, excluded |
| Author/committer | Frank Asante Van Laarhoven — no trailers, no vendor/AI attribution |

## 2. Original G1 findings reviewed (from `H8_GIT_DEPENDENCY_RESOLVER_INDEPENDENT_REVIEW.md` §18)

| ID | Sev | Original observation |
| --- | --- | --- |
| `H8-G1REV-F-001` | Medium | Resolver report not authenticated — an approved-`resolver_id` fake with `overall_accepted=True` passed `report_binding_ok` → `PROVIDER_OK_PREFLIGHT`. |
| `H8-G1REV-F-002` | Medium | Integration accepted a caller in-memory manifest dict; a reduced dict hid a dirty/omitted dependency. |
| `H8-G1REV-F-003` | Low | Git config (`core.fileMode=false`, symlinks, autocrlf, filters, replace/alternate objects) can mask changes. |
| `H8-G1REV-F-004` | Low | Repository identity binds history, not physical origin — an exact copy reproduces identity. |

## 3. Pre-remediation reproduction (against `b8e5204`, in a temporary module)

- **F-001 reproduced:** `OLD.report_binding_ok({"resolver_id": RESOLVER_ID, "overall_accepted": True})` → `(True, ACCEPTED)`.
- **F-002 reproduced:** a reduced caller manifest dict omitting a **dirty** dependency → `dependency_dirty=False` (the omitted dirty dep is invisible).

Both original weaknesses are confirmed exactly as documented.

## 4. Remediation → executable-behaviour mapping (diff `b8e5204..2de2ee7`, resolver code)

Every documented control exists in executable code: 6 new reason codes; `_REPORT_AUTHENTICITY`;
`_GIT_SAFE_OVERRIDES`; `CANONICAL_MANIFEST_REL`; `REQUIRED_DEPENDENCY_IDS`; `inspect_git_config`;
`_canonical_reject`; `resolve_canonical`; `trusted_provider_tree_state`; the authenticity gate in
`report_binding_ok`; the config-override + `LC_ALL=C` env in `SubprocessGitRunner.run`.

## 5. Trusted-factory verification (F-001 primary control)

`inspect.signature(trusted_provider_tree_state)` parameters = `{repo_root, mode, expected_head,
expected_closure_digest, git, fs}`. **None** of `resolver, resolver_factory, report, resolution_report,
manifest, manifest_path, assume_clean, skip_resolution, allow_dirty` is present. Unexpected kwargs
(`report=`, `manifest=`, `resolver=`) raise `TypeError` — a report/manifest cannot be smuggled through
`**kwargs`. The factory constructs the genuine resolver in-process and re-resolves current state each call.
`git`/`fs` are a documented test-only fixture seam with no acceptance authority (the resolver still fails
closed on any dirty/missing/substituted dependency).

## 6. Caller-report forgery (F-001, ordinary routes)

| Forgery | Result |
| --- | --- |
| plain approved-id dict | `REPORT_UNAUTHENTIC` |
| changed `accepted` only | `REPORT_UNAUTHENTIC` |
| authenticity marker misspelled | `REPORT_UNAUTHENTIC` |
| fixture id + genuine marker | `RESOLVER_FIXTURE_IN_PROTECTED` |
| `None` / empty dict | `RESOLVER_UNAVAILABLE` / `REPORT_UNAUTHENTIC` |
| genuine clean canonical report | **ACCEPTED** (not reject-all) |

**Documented residual (honest):** a caller **with module access** can copy `_REPORT_AUTHENTICITY` into a
dict; `report_binding_ok` then accepts it. This is the in-process, non-cryptographic nature of the marker,
correctly deferred to G2. The durable control is that protected callers use `trusted_provider_tree_state`,
which never accepts a caller report at all.

## 7. Positive clean path (not test-specific)

A real clean canonical fixture repository (no fixture env-vars, no monkeypatch, no bypass flag, no
caller report/manifest) resolves via `trusted_provider_tree_state(repo)` → `dependency_dirty=False`,
`ACCEPTED`, canonical manifest selected internally, commit bound to HEAD. Run twice → identical
`closure_digest` (deterministic). The trusted factory is **not** reject-all.

## 8. Canonical-manifest enforcement (F-002)

| Case | Result |
| --- | --- |
| canonical clean | ACCEPTED |
| dirty canonical manifest (worktree modify) | rejected; manifest-self dep dirty |
| deleted canonical manifest | `DEPENDENCY_MANIFEST_INVALID`, fail closed |
| manifest not self-listing at canonical path | `MANIFEST_NOT_CANONICAL` |
| drop `h8-manifest-schema` / `h8-resolver` | `MANIFEST_INCOMPLETE` |
| manifest with foreign `root_commit` | `GIT_REPOSITORY_MISMATCH` |

A caller can no longer supply a reduced in-memory manifest or select an alternate manifest path — only the
tracked canonical file is loaded, and it must self-list, be clean, and be bound to HEAD.

**Manifest self-protection ordering confirmed:** git-state inspection → canonical path → load →
self-listing check → mandatory-id presence → resolve manifest file itself (tracked+clean+HEAD) →
defence-in-depth self-acceptance recheck. A manifest that marks **itself** optional and is then dirtied is
still rejected (`MANIFEST_NOT_CANONICAL`) by the defence-in-depth accepted-check.

## 9. Mandatory dependency-set enforcement — **PASS WITH DOCUMENTED LIMITATIONS**

`REQUIRED_DEPENDENCY_IDS` (10 ids) is a strict subset of the shipped manifest and is asserted against it.
Removal and id-rename of a mandatory dependency → `MANIFEST_INCOMPLETE` (rejected). **However**, two
adversarial cases are **not** rejected (new findings §11):

- marking a non-self mandatory dependency `required:false` then modifying it → **ACCEPTED** (weakening);
- re-pointing a mandatory dependency's `path` at a different tracked/clean/expected-type file → **ACCEPTED**
  (semantic identity not bound).

The enforced set (10 ids) is also narrower than the full semantic decision-critical category list (e.g.
producer-trust policy, capture-prerequisite validator, canonicalisation, digest implementation and the
`CL_BOUND_XY` source are not separate manifest entries). **No semantic-completeness claim is made.**

## 10. Git-configuration behavioural verification (F-003)

| Probe | Result |
| --- | --- |
| local `core.fileMode=false` + chmod | detected (`DEPENDENCY_WORKTREE_MODIFICATION`) — pin works |
| `refs/replace/*` present | `GIT_REPLACE_OBJECTS` (rejected) |
| alternates **file** present | `GIT_ALTERNATE_OBJECTS` (rejected) |
| clean/smudge filter masking a tamper | did **not** mask in git 2.34.1 (still detected); filters not pinned → documented limit |
| `GIT_ALTERNATE_OBJECT_DIRECTORIES` **env** | **not** detected by `inspect_git_config` (file-only) — residual (§11 F-003) |
| dash-leading pathspec `-rf` | no option injection (`--` guard) |
| clean repo | passes inspection (not reject-all) |

`_GIT_SAFE_OVERRIDES` (`core.fileMode/symlinks/ignorecase/autocrlf` + `--no-replace-objects`) and `LC_ALL=C`
are applied on every invocation; commands use argument arrays, no shell. F-003 is **mitigated for the
enumerated surfaces**, not exhaustively closed (filters/textconv and env-var object redirection are not
neutralised).

## 11. New re-review findings

### `H8-G1RREV-F-001` — Mandatory-set enforcement is presence-only; optional-weakening not rejected (MEDIUM)
- **Expected (objective 4):** mandatory dependency categories cannot be silently removed **or weakened**.
- **Observed:** a canonical manifest listing all mandatory ids but marking a non-self mandatory dependency
  (e.g. `h8-evidence-provider`, `h8-resolver`) `required:false` passes the presence check; a modified/dirty
  version of that dependency then does **not** fail the aggregate (`overall_accepted=True`). `resolve_canonical`
  only checks `REQUIRED_DEPENDENCY_IDS - set(by_id)`, never `required is True`.
- **Containment:** requires a **committed** change to the tracked canonical manifest (it must be clean to
  pass) — visible in Git history and reviewable; capture stays blocked; only a non-authorising preflight
  document over a weakened closure; backend calls zero. Manifest-self is protected by the defence-in-depth
  accepted-check. It does **not** create a new runtime-injection vector (a caller still cannot supply a
  manifest), but it undercuts the stated intent of the added mandatory-set control.
- **Remediation (bounded, one line of logic):** in `resolve_canonical`, require each id in
  `REQUIRED_DEPENDENCY_IDS` to be present **and** `required is True`; else `MANIFEST_INCOMPLETE`.
- **Owner:** bounded G1R remediation (round 2) before G2.

### `H8-G1RREV-F-002` — Semantic identity of a mandatory dependency is not bound (LOW)
- Re-pointing a mandatory dependency's `path` at another tracked/clean file of the expected type is
  accepted. The resolver binds `path + tracked + clean + HEAD`, not content/semantic identity. This
  reconfirms the pre-existing documented limitation (`H8-C-033`, "completeness is the author's
  responsibility"); it is not a new capability regression.
- **Remediation:** pin an expected per-dependency object/content digest in a future gate. **Owner:** G2/later.

### `H8-G1RREV-F-003` — Security-relevant Git env vars not scrubbed (LOW)
- `SubprocessGitRunner.run` inherits `os.environ` and overrides only `LC_ALL`/`LANG`. `inspect_git_config`
  detects the alternates **file** but not `GIT_ALTERNATE_OBJECT_DIRECTORIES`; `GIT_OBJECT_DIRECTORY`,
  `GIT_DIR`, `GIT_INDEX_FILE`, `GIT_REPLACE_REF_BASE` are likewise not neutralised. Content-addressing makes
  object substitution require a hash collision (LOW), and `--no-replace-objects` neutralises `refs/replace`,
  but env-var object redirection is a residual consistent with the remediation's own `H8-C-040`
  ("not exhaustive").
- **Remediation:** scrub/deny dangerous `GIT_*` env vars in the runner and/or extend `inspect_git_config`.
  **Owner:** bounded G1R remediation or G2.

### `H8-G1RREV-F-004` — Minor documentation-accuracy note (INFORMATIONAL)
- The remediation doc / `H8-DCP-060` describe the F-002 control as preventing a caller "silently dropping" a
  decision-critical dependency (accurate for drop/rename) but do not note that optional-weakening
  (F-001 above) and path-substitution (F-002 above) are not caught, nor that the enforced set is narrower
  than the full semantic category list. Recommend bounding the wording. Documentation verdict:
  **PASS WITH MINOR FINDINGS**.

No Critical or High finding.

## 12. Independent dispositions of the original findings

| Original | Disposition |
| --- | --- |
| `H8-G1REV-F-001` (report injection) | **INDEPENDENTLY VERIFIED PARTIALLY CLOSED** — ordinary caller injection prevented; trusted in-process construction mandatory; cryptographic/persisted-report authenticity correctly deferred to G2. |
| `H8-G1REV-F-002` (caller-controlled manifest) | **INDEPENDENTLY VERIFIED CLOSED** for its original vector (caller-supplied/reduced in-memory manifest); the added mandatory-set control has documented limits (§9, `H8-G1RREV-F-001/-002`). |
| `H8-G1REV-F-003` (Git configuration) | **INDEPENDENTLY VERIFIED MITIGATED** (enumerated surfaces), with documented residuals (filters, env-var object redirection). |
| `H8-G1REV-F-004` (identical history) | **OPEN — CORRECTLY DEFERRED TO G2** — an identical-history copy (matching directory basename) resolves ACCEPTED with identical `root_commit` + `closure_digest`; a differing remote URL is ignored; not claimed closed. |

## 13. Independent control verdicts

| Control | Verdict |
| --- | --- |
| Trusted resolver construction | **PASS WITH DOCUMENTED LIMITATIONS** (structural no-injection surface; in-process non-cryptographic marker residual → G2) |
| Canonical manifest enforcement | **PASS** |
| Mandatory dependency-set enforcement | **PASS WITH DOCUMENTED LIMITATIONS** (`H8-G1RREV-F-001/-002`) |
| Git-configuration security controls | **PASS WITH DOCUMENTED LIMITATIONS** (`H8-G1RREV-F-003`) |
| Provider integration boundary | **PASS** (clean→non-authorising preflight; dirty→blocked; backend 0; status never `valid`) |
| Documentation | **PASS WITH MINOR FINDINGS** (`H8-G1RREV-F-004`) |
| **Overall G1R re-review** | **PASS WITH DOCUMENTED LIMITATIONS** |

No unresolved Critical or High finding; the one MEDIUM (`H8-G1RREV-F-001`) is contained to the
committed-artifact boundary and one-line fixable.

## 14. KPIs

| KPI | Result |
| --- | --- |
| Original finding re-verification | 4/4 |
| Trusted factory enforcement (no injection surface) | 100% |
| Caller-report rejection (ordinary) | 100% |
| Caller-manifest rejection (in-memory/alternate path) | 100% |
| Canonical clean positive path | 100% |
| Mandatory dependency-category enforcement | presence/removal/rename 100%; **optional-weakening & substitution NOT enforced** (`H8-G1RREV-F-001/-002`) |
| Git-config adversarial rejection/neutralisation | fileMode/replace/alternates-file 100%; filters + env-var alternates residual (`H8-G1RREV-F-003`) |
| Replace-object rejection | 100% |
| Alternate-object rejection | file 100%; **env-var not detected** (residual) |
| Report-forgery rejection (ordinary) | 100% |
| Preflight capture rejection | 100% |
| Blocked-case output | 0 |
| Blocked-case backend calls | 0 |
| Deterministic closure digest | 100% (twice identical) |
| Resolver regression | 75/75 |
| Provider regression | 41/41 |
| Schema regression | 34/34 |
| Recorded-mode regression | 58/58 |
| Matching H8 regression (`tests/gnm/test_h8_*.py`) | 298/298 |
| Dataset dry-run | `all_checks_pass=True`; regeneration byte-identical |
| Level-1 hashes | 5/5 unchanged |
| Boundary violations | 0 |
| Ruff | **unavailable — Open** (not counted as passing) |

Signed reports, trusted timestamps, origin attestation, operational revocation, Level 3 and capture are
**not** counted as passing.

## 15. SWOT

- **Strengths:** trusted in-process resolver construction (no injection surface); canonical-manifest binding;
  fail-closed Git-state inspection (replace/alternates-file); deterministic closure digest; non-authorising
  provider integration; genuine clean positive path works.
- **Weaknesses:** no cryptographic report authentication; no physical-origin attestation; mandatory-set
  enforcement is presence-only (optional-weakening/substitution gaps); residual TOCTOU; env-var Git
  redirection not scrubbed; filters/textconv not pinned; bounded to git 2.34.1; Ruff unavailable.
- **Opportunities:** require `required is True` for mandatory ids; per-dependency expected-digest binding;
  signed resolver reports; external repository attestation; trusted timestamps; revocation; generated
  dependency graph.
- **Threats:** a future decision-critical dependency omitted from the mandatory set; committed manifest
  policy-weakening; new Git-config/env influence; copied-history impersonation; persisted-report forgery
  before G2; provider bypass introduced later; premature runtime claims.

## 16. G2 eligibility — **ELIGIBILITY INCONCLUSIVE**

The remediation is a genuine, net-positive hardening with no Critical/High finding, and every eligibility
criterion is met **except** "mandatory dependency categories enforced", which is undercut by the MEDIUM
`H8-G1RREV-F-001` (optional-weakening). Because G2 cryptographic trust infrastructure would be built directly
on top of the mandatory-set control, this reviewer declines a clean eligibility declaration and instead
recommends:

> a **bounded G1R remediation (round 2)** closing `H8-G1RREV-F-001` (require `required is True` for mandatory
> ids) and `H8-G1RREV-F-003` (scrub/deny security-relevant `GIT_*` env vars), plus a wording fix for
> `H8-G1RREV-F-004`, followed by a focused re-verification — **before** opening the separately scoped G2
> trust-infrastructure **design** gate.

Eligibility does not authorise G2 implementation, Isaac, observers or capture.

## 17. Remaining limitations

Cryptographic report authentication (F-001 residual), physical-origin attestation (F-004), exhaustive
Git-config/env independence (F-003 residual), semantic per-dependency identity (`H8-G1RREV-F-002`), residual
TOCTOU, bounded Git-version testing and Ruff availability all remain open. **This is not Level 3.** Real
hospital footage & trajectory collection remains blocked; Levels 3–5 unproven.
