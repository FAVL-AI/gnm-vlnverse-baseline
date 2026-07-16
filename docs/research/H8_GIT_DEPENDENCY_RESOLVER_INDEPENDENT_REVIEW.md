# H8 Git Dependency Resolver — Independent Review (G1 review)

**Gate:** `G1 Independent Git Dependency-Resolver Review` (adversarial, review-only). **Date:** 2026-07-16.
**Branch:** `h23-execfix`. **Commit reviewed:** `250c88fa2ff94bdb4d1ae3f9b673bf1b58aedb6a` (byte-identical;
`git diff 250c88f -- resolver/manifest` empty). **git:** 2.34.1.

This is an INDEPENDENT review. Verdicts are reconstructed from Git, code, and probes against **real
temporary Git repositories** plus independent digest calculations — not from the implementation report. It
does not modify the resolver, manifest, provider, schema, tests, config or evidence.

**Boundary honoured:** no G2/observer/Isaac/backend implementation; no Isaac/Omniverse/ROS 2 launch; no
render/drive/capture/inference/probe/train/20-5-10/closed-loop; no push/tag/promotion/capture.

## 1. Objective & method (§1)

Independently test the 11 bounded claims of §1 (clean acceptance, not-reject-all, deterministic resolution,
fail-closed dirty/substitution, repository-identity binding, path/symlink/LFS/submodule policy, stale
invalidation, no provider bypass, non-authorising preflight, zero-artifact failure, manifest completeness).
Method: re-run the committed suite independently; reconstruct the dependency graph from imports/file-reads;
and run bespoke adversarial probes against fresh temp repos (positive path, report forgery, manifest tamper,
manifest self-protection, repo spoof, dash-path, stale reuse, git-config influence).

## 2. Baseline (§2)

HEAD `250c88f` on `h23-execfix`, local/unpushed; resolver + manifest byte-identical to the commit. Prior
commits (`403c20b`, `dae2bee`, `a449ab6`, `97781ad`, `ebf8341`, …) unchanged (ancestors of HEAD). Only
pre-existing unrelated files dirty (`06_evaluate.py`, `scripts/datasets/*`) — excluded.

## 3. Implementation-diff inspection (§3) — decisions implemented, not just documented

Confirmed in code (`250c88f`): manifest v1.0.0 + loader + schema; repository discovery + identity by
`(canonical_name + root_commit)`; HEAD/object resolution; single-pass porcelain index+worktree inspection;
untracked/ignored handling; expected-mode; symlink policy; path containment; LFS pointer detection;
submodule (gitlink) handling; shallow/`provenance_requires_history`; arg-array Git runner with timeout;
volatile-excluded closure digest; report-binding + `provider_tree_state`; approved/fixture resolver
identity; 31 active + 1 reserved reason codes. **`H8-DCP-047…057` are implemented** (verified by probes),
not merely documented.

## 4. Positive path (§4) — NOT reject-all

Clean temp repo, real resolver over a 2-dependency manifest → `overall_accepted=True`, accepted 2/2,
rejected 0. Live-repo full closure (post-commit) accepts **13/13** bound to HEAD with a deterministic
digest (independently reproduced). Provider consumes an approved clean report → `PROVIDER_OK_PREFLIGHT`
(a **document**), `preflight_satisfies_capture_gate=False`, backend calls 0. **Pass — not reject-all.**

## 5. Independent dependency-closure audit (§5) — committed manifest is COMPLETE

Reconstructed the evidence-generation graph from imports and file reads:

| Reached from | Module/file | In manifest? | Alters a decision? |
|---|---|---|---|
| provider entry | `h8_evidence_provider.py` | yes | yes |
| provider import | `h8_evidence_schema.py` (schema+canon+digest+trust+CL_BOUND) | yes | yes |
| provider import | `h8_synthetic_fork_recorded_mode.py` (plan builder) | yes | yes |
| recorded-mode import | `h8_synthetic_fork_drive_validate.py` (CL_BOUND/scene consts) | yes | yes |
| provider read | dataset config YAML | yes | yes |
| provider read | scene `.usda` | yes | yes |
| resolver/manifest/schema (self) | 3 files | yes | yes |

The transitive import closure of the evidence path is exactly {provider, schema, recorded_mode,
drive_validate}; `h8_evidence_schema.py` and `h8_git_dependency_resolver.py` import nothing repo-internal;
`build_dataset_plan` reads only the config YAML. **All decision-critical files are in the 13-entry
manifest.** Notably the resolver manifest is *more complete* than the provider's own
`EVIDENCE_DEPENDENCY_PATHS` (which omits `recorded_mode.py`/`drive_validate.py`) — a strength. The three
Level-1 "reference" artefacts (drive-manifest, scene-spec, expected-routes) are conservatively included
though not machine-consumed by the generation path. **No omission finding in the committed manifest.**

## 6. Manifest self-protection (§6)

- **Passed by tracked PATH + self-listed:** dirtying the manifest file → the `manifest-self` dependency
  reports `DEPENDENCY_WORKTREE_MODIFICATION` → aggregate **rejected**. Self-protection **works** in the
  intended usage.
- **Gap:** the integration function `provider_tree_state(resolver, manifest, …)` accepts an **in-memory
  manifest dict**. A caller passing a *reduced* dict that omits a (dirty) dependency yields a smaller clean
  closure — the tampered dict is trusted as-is. See `H8-G1REV-F-002`.

## 7. Repository-identity adversarial review (§7)

Copying a tree into a freshly-initialised repo with the **same folder name** but a **different root
commit** → `GIT_REPOSITORY_MISMATCH` (rejected). Identity binds `(root_commit + toplevel + name)`, not
folder-name or remote alone. **Residual (`H8-G1REV-F-004`, Low):** an attacker who copies the *exact* Git
object history (same root commit) reproduces the identity — identity binds history, not physical origin;
strong origin proof needs signing (G2).

## 8. HEAD / index / worktree truth audit (§8) & flags (§9)

Independent `git rev-parse HEAD:<path>`, `ls-files --stage`, `git hash-object`, `sha256sum` cross-checks
match the resolver's head/index/worktree fields. The committed suite (re-run independently, 56 passed)
plus code review confirm: staged-mod, unstaged-mod, both, staged/unstaged deletion, rename, index-removal,
mode-change, `assume-unchanged` (`ls-files -v` lowercase tag), `skip-worktree` (`S` tag) all fail closed;
HEAD content is never reported as effective when index/worktree differ (a HEAD file absent from the index →
`DEPENDENCY_DELETED`).

## 9. Untracked/ignored (§10), path (§11), symlink (§12), TOCTOU (§13)

Untracked, ignored, deleted-then-recreated-untracked, case-variant → reject. Dash-path `-rf` →
`DEPENDENCY_MISSING` (protected by `--`, never an option). Absolute/`..`/NUL/backslash →
`DEPENDENCY_PATH_INVALID`. Committed symlink (unexpected) → `DEPENDENCY_SYMLINK_UNEXPECTED`; symlink to
`/etc/hosts` (allow_symlink) → `DEPENDENCY_SYMLINK_ESCAPE`; broken symlink → reject. **TOCTOU:** content
change alters the closure digest and re-resolution rejects; a report bound to an old digest is rejected.
**Residual:** static inspection cannot eliminate a symlink race between object inspection and digest — the
implementation correctly does not claim complete TOCTOU prevention (`H8-C-033`).

## 10. LFS (§14), submodule (§15), sparse/shallow (§16)

LFS pointer without materialised object → `DEPENDENCY_LFS_UNAVAILABLE` (git-lfs absent; never downloads);
malformed pointer → reject; `pointer_ok` policy accepts. Gitlink without submodule policy or commit
mismatch → `DEPENDENCY_SUBMODULE_MISMATCH` (never inits/fetches). Shallow repo +
`provenance_requires_history` → `GIT_HISTORY_INSUFFICIENT`. These are deterministic fail-closed states, not
unsafe acceptances.

## 11. Git command runner & configuration (§17/§18)

Every call is an argument array (`git -C <repo> …`), no shell; timeout enforced; rc/stderr captured;
pathspecs guarded by `--`; a dash path cannot become an option. **Residual (`H8-G1REV-F-003`, Low):**
`core.fileMode=false` makes a `chmod +x` invisible to Git → accepted; `core.symlinks=false`,
`core.autocrlf`, textconv/clean-smudge filters, replace-objects and alternate object databases can
similarly influence content/mode perception. The resolver uses plumbing but does not pin these config
values; document + harden in a later gate.

## 12. Determinism & stale invalidation (§19/§20/§21)

Identical state → identical decisions and closure digest; manifest reordering and different injected clocks
do not change the digest; changing one protected file/object-id/policy-version/identity-field/required-flag
changes the digest or rejects. State-based stale invalidation works (mutation → new digest → old-digest
binding rejected). `REPORT_STALE` remains **reserved** (no trusted clock yet) — correct.

## 13. Report forgery & trust identity (§22/§23) — FINDING

`report_binding_ok` checks `resolver_id ∈ APPROVED_RESOLVER_IDS`, `overall_accepted`, and optional
head/closure/repo binding — but performs **no authentication that the report was produced by a genuine
resolver execution**. A fake object whose `build_resolution_report()` returns
`{resolver_id: "h8-git-dependency-resolver", overall_accepted: True, …}` is **accepted**, and
`provider_tree_state(fake, …)` drives the provider to `PROVIDER_OK_PREFLIGHT`. The fixture-resolver-id case
is correctly rejected, but an *approved-id-presenting* fake is not. See `H8-G1REV-F-001`. (In the committed
wiring the genuine resolver class is used, so this requires injecting a fake resolver **object** —
code-level — and only ever yields a non-authorising preflight document; capture stays blocked.)

## 14. Provider integration call path (§24)

Protected preflight requires the resolver (absent/`None` `tree_state` → `PROVIDER_DIRTY_TREE`); there is no
`assume_clean` flag; fixture resolver, dirty closure, HEAD-mismatch and stale (closure-digest) all →
`PROVIDER_DIRTY_TREE`; an accepted report yields only a preflight **document**; capture is always blocked;
backend calls 0. **Two integration gaps** (F-001 fake-resolver, F-002 caller-manifest) qualify the "cannot
bypass" claim: bypass requires the caller to inject a fake resolver object or a reduced manifest — not a
data-only forgery, but a real trust-boundary weakness.

## 15. Manifest-omission probe (§25)

Review-only: a manifest that OMITS a (dirty) dependency accepts the reduced closure — demonstrating the
consequence of incompleteness. The **committed** manifest was independently verified complete (§5), so this
is not a committed-artifact omission; it is the integration-binding gap `H8-G1REV-F-002`. The committed
manifest was **not** modified.

## 16. Reason-code coverage (§26) & zero-output (§27)

31 active + 1 reserved (`REPORT_STALE`); **31/31 active codes triggered** by the suite (independently
re-run). Every negative probe produced **zero** provider output (`InMemorySink.atomic_ops == 0`) and **zero**
backend calls; no `assets/evidence/`, runtime or dataset directory, image, trajectory or rosbag was created.

## 17. Regressions (§28)

| Suite | Command | Result |
|---|---|---|
| resolver | `pytest test_h8_git_dependency_resolver.py` | **56 passed** |
| matching H8 (NOT whole repo) | `pytest tests/gnm/test_h8_*.py` | **279 passed** |
| provider+schema+recorded | `pytest …_provider …_schema …_recorded_mode` | **133 passed** (41+34+58) |
| dataset dry-run | `--mode dataset-dry-run --emit-schema` | **25/25 PASS** |
| Level-1 evidence | `git diff --quiet` | **5/5 byte-identical** |
| py_compile / attribution / secret / `git diff --check` | — | clean |
| Ruff | `python -m ruff` | **UNAVAILABLE → Open** (`H8-C-006`/`H8-C-013`) |

The 279 matching tests are the `test_h8_*.py` suite only — **not** the whole repository or Isaac tests.

## 18. Findings (§29)

### `H8-G1REV-F-001` — Resolver report is not authenticated (MEDIUM)
- **Expected:** a caller-created / non-genuine report cannot substitute for a trusted resolver report (§22).
- **Observed:** a fake object presenting the approved `resolver_id` with `overall_accepted=True` passes
  `report_binding_ok` and drives `provider_tree_state` → `PROVIDER_OK_PREFLIGHT`.
- **Root cause:** report trust is a self-declared `resolver_id` string; no signature / authentic-execution
  proof (signing is deferred to G2).
- **Safety impact:** in-process only; capture stays blocked; affects a non-authorising preflight document.
  **Escalates to HIGH** if resolver reports are ever persisted/serialised and re-consumed across a boundary.
- **Containment:** committed wiring uses the genuine resolver class.
- **Remediation:** have `provider_tree_state` construct/verify the resolver via a trusted internal factory
  (reject arbitrary objects) and/or sign reports (G2). **Owner:** bounded G1 remediation + G2 signatures.

### `H8-G1REV-F-002` — Integration boundary does not bind to the canonical manifest (MEDIUM)
- **Expected:** the provider integration verifies the canonical, tracked, self-protected manifest.
- **Observed:** `provider_tree_state`/`build_resolution_report` accept an in-memory manifest dict; a reduced
  dict hides a dirty/omitted dependency (the resolver protects the manifest only when passed by tracked
  PATH + self-listed, which it does correctly — §6).
- **Root cause:** manifest source is caller-chosen; not enforced to be the tracked file.
- **Safety impact:** capture stays blocked; a caller could obtain a preflight document over an incomplete
  closure.
- **Remediation:** the integration must load the manifest **by tracked path**, require the `manifest-self`
  dependency present + accepted, and verify the loaded manifest digest against the tracked file. **Owner:**
  bounded G1 remediation.

### `H8-G1REV-F-003` — Git-config can mask mode/symlink/EOL changes (LOW)
- `core.fileMode=false` hides `chmod` changes; `core.symlinks=false`, `autocrlf`, textconv/filters,
  replace-objects and alternate object DBs can similarly influence perception. **Remediation:** pin/inspect
  the relevant Git config (or use `-c core.fileMode=true` etc.) in a later gate. **Owner:** G1 remediation.

### `H8-G1REV-F-004` — Repository identity binds history, not physical origin (LOW)
- An exact copy of the Git object history (same root commit) reproduces identity. Documented residual;
  strong origin proof requires signing. **Owner:** G2.

No Critical or High finding.

## 19. Verdicts (§31)

| Dimension | Verdict |
|---|---|
| Declared dependency resolution | **PASS** |
| Manifest completeness (committed artifact) | **PASS** (independently verified complete) |
| Repository identity binding | **PASS WITH DOCUMENTED LIMITATIONS** (F-004 identical-history residual) |
| Dirty & substitution detection | **PASS** |
| Determinism & report invalidation | **PASS** |
| Provider integration boundary | **PASS WITH DOCUMENTED LIMITATIONS** (F-001, F-002) |
| Documentation | **PASS WITH MINOR FINDINGS** (qualify the report-authenticity / trust-identity wording) |
| **Overall G1 independent review** | **PASS WITH DOCUMENTED LIMITATIONS** |

## 20. G2 eligibility (§32)

**ELIGIBLE FOR G2 TRUST-INFRASTRUCTURE DESIGN** — no Critical/High finding; clean positive path,
repository identity, dirty/substitution detection, determinism, stale invalidation and manifest-by-path
self-protection all verified; preflight non-authorising; no backend/capture capability introduced. **Two
mandatory conditions** carry forward: (1) resolver-report authentication (`F-001`) — a first-class G2
signing requirement, and reports must not be persisted/cross-boundary until signed; (2) canonical-manifest
binding at the integration boundary (`F-002`). A **bounded G1 remediation** closing F-002/F-003 (and the
resolver-factory part of F-001) before G2 implementation is recommended (§21). Eligibility authorises only
G2 *design* — not signatures/revocation/observers/Isaac/capture.

## 21. Recommendation (§53)

Run a **bounded G1 remediation** first: (a) make `provider_tree_state` obtain the resolver from a trusted
internal factory and reject arbitrary report objects / unauthenticated approved-id reports; (b) enforce the
canonical manifest is loaded by tracked path, self-listed and digest-verified; (c) pin/inspect the
security-relevant Git config; (d) qualify the trust-identity wording. Then proceed to **G2 trust/signature/
revocation design** (which also delivers cryptographic report authentication, fully closing F-001/F-004).
The next Isaac-capable code (G4) remains several reviewed gates away.

## 22. KPIs (§33)

| KPI | Target | Result |
|---|---|---|
| G1 requirement review coverage | 100% | 100% |
| Independent dependency-graph coverage | 100% | 100% (import+read closure reconstructed) |
| Clean positive-path acceptance | 100% | 100% |
| Manifest self-protection (by path) | 100% | 100% |
| Repository-spoof rejection (diff root) | 100% | 100% |
| Dirty-state rejection | 100% | 100% |
| Untracked/ignored substitution rejection | 100% | 100% |
| Path/symlink escape rejection | 100% | 100% |
| Report-forgery rejection | 100% | **partial — F-001 (approved-id fake accepted)** |
| Stale-state report rejection | 100% | 100% (content-based) |
| Deterministic closure digest | 100% | 100% |
| Active reason-code coverage | 100% | 100% (31/31; 1 reserved) |
| Blocked-case provider output / backend calls | 0 | 0 / 0 |
| Provider / schema / recorded | 41/34/58 | 41/34/58 |
| Matching H8 suite | 279 | 279 |
| Dry-run | 25/25 | 25/25 |
| Level-1 evidence | 5/5 | 5/5 |
| Boundary violations | 0 | 0 |
| Ruff | Pass/Open | Open |

## 23. SWOT (§34)

**Strengths:** explicit + independently-verified-complete closure; genuine Git object/worktree binding;
fail-closed inspection; deterministic digest; required non-bypassable provider dirty-tree; no runtime
capability. **Weaknesses:** report not authenticated (F-001); integration trusts caller manifest (F-002);
git-config residuals (F-003); identical-history spoof residual (F-004); minimal worktree policy; LFS
materialisation unavailable; no trusted-clock expiry; Ruff unavailable. **Opportunities:** generated
dependency graph; signed resolver reports; trusted timestamps; broader Git-version conformance; stronger
object-DB identity. **Threats:** fake-resolver injection; caller-supplied manifest; git-config influence;
copied-history spoofing; stale reuse if persisted; symlink race; future provider bypass.

## 24. Limitations (§44) & boundary

Establishes resolver validity, closure completeness (committed artifact), repository-identity binding,
fail-closed detection, deterministic digest and (path-based) provider integration. **Does NOT establish**
Level-3 runtime validity, trusted time, signatures, revocation, dataset/model validity, or capture
authorisation. **This is not Level 3.** Levels 3–5 unproven; real hospital footage & trajectory collection
remains blocked.

---

## G1R Remediation Disposition (appended 2026-07-16)

The original review above is preserved unchanged. The bounded remediation gate **G1R — Harden H8 Git
resolver trust boundary** dispositions the four findings as follows (full detail in
`H8_GIT_DEPENDENCY_RESOLVER_REMEDIATION.md`). This disposition is the implementer's account and is
subject to a **focused independent G1R re-review** before G2.

| Finding | Severity | Disposition | Control |
| --- | --- | --- | --- |
| `H8-G1REV-F-001` | Medium | **PARTIALLY CLOSED — TRUSTED IN-PROCESS CONSTRUCTION** | In-process authenticity marker (`REPORT_UNAUTHENTIC`) rejects plain caller-forged dicts; primary control is `trusted_provider_tree_state`, which never accepts a caller report. Cryptographic authentication → G2 (`H8-C-039`). |
| `H8-G1REV-F-002` | Medium | **CLOSED** | `resolve_canonical` enforces the ONE canonical tracked manifest, self-listing, mandatory-id set, and resolves the manifest file itself. No caller-selected manifest is honoured. |
| `H8-G1REV-F-003` | Low | **MITIGATED WITH DOCUMENTED LIMITATIONS** | Config pinned on every invocation + replace-refs/alternates rejection; a test proves `core.fileMode=false` no longer masks a chmod. Not an exhaustive proof of no config influence (`H8-C-040`). |
| `H8-G1REV-F-004` | Low | **OPEN — DEFERRED TO G2 CRYPTOGRAPHIC ORIGIN ATTESTATION** | Not closable by ordinary Git inspection; explicitly NOT closed via remote-URL comparison (`H8-C-041`). |

**Still true after G1R:** this is not Level 3; trusted time, signatures, revocation, dataset/model
validity and capture authorisation remain out of scope. Levels 3–5 unproven; real hospital footage &
trajectory collection remains blocked.
