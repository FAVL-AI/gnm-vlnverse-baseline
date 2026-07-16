# H8 Git Dependency Resolver (Gate G1)

**Gate:** `G1 — H8 Git Dependency Resolver Implementation Gate` (non-Isaac, non-capturing implementation).
**Date:** 2026-07-16. **Branch:** `h23-execfix`. **Base commit:** `403c20b` (runtime architecture design).

**Boundary honoured (nothing executed):** no Isaac Sim / Omniverse Kit, no ROS 2, no rendering, driving,
image/trajectory/rosbag creation, inference, action probe, training, 20/5/10 or closed-loop; no Isaac
worker, runtime observer, capture token or dataset writer; no push/tag/promotion/release. The resolver
produces a structured dependency-resolution **report** only — a clean report permits ONLY non-authorising
preflight document generation and **never authorises capture**.

## 1. Objective (§1) & research question (§3)

> Are all files, policies, schemas, plans and artefacts required for this H8 evidence decision present,
> tracked, unmodified, bound to the EXPECTED repository and commit, and free from ambiguous substitution?

Discharges the re-review finding `H8-PRREV-F-002` (the provider previously trusted an injected
`dependency_dirty` boolean; no concrete resolver existed).

## 2. Hypothesis (§4)

> A resolver based on exact repository identity, tracked-path verification, Git index and worktree state,
> object identity, file-mode inspection and an explicit dependency closure can fail closed for staged,
> unstaged, deleted, renamed, untracked, ignored, symlinked, repository-mismatched or Git-unavailable
> dependencies without invoking Isaac or creating capture artefacts.

**Result: supported.** 56 tests (real temporary Git repositories + a FakeGit runner for tooling-absent
states) demonstrate a functional clean positive path and fail-closed rejection across the full adversarial
matrix, with zero provider output and zero backend invocation on every blocked case.

## 3. Files (§ deliverables)

| File | Role |
|---|---|
| `scripts/gnm/h8_git_dependency_resolver.py` | resolver, result models, reason codes, trust identity, provider adapter |
| `configs/gnm/h8_dependency_manifest.json` | canonical dependency closure (repo-tracked, self-referential) |
| `docs/research/schemas/h8_dependency_manifest.schema.json` | dependency-manifest JSON schema |
| `scripts/gnm/h8_evidence_provider.py` | **additive** only: `build_provenance` threads an optional `dependency_resolution_digest` |
| `tests/gnm/test_h8_git_dependency_resolver.py` | 56 positive/negative/integration/determinism tests |
| `docs/research/H8_GIT_DEPENDENCY_RESOLVER.md` | this document |

## 4. Resolver version & manifest version (§4/§5)

- Resolver: `h8-git-dependency-resolver/1.0.0`; dependency policy `h8-dependency-policy/1.0.0`.
- Manifest: `h8-dependency-manifest/1.0.0`.
- Approved resolver ids: `{h8-git-dependency-resolver}`; the `h8-fixture-resolver` id is **rejected** in
  protected use (mirrors the positive producer-authorisation design).

## 5. Dependency closure (§5)

The shipped manifest pins **13 mandatory** tracked dependencies (config, evidence schema, provider,
recorded-mode/plan builder, drive-validate/scene-gate, scene `.usda`, Level-1 drive-validation manifest,
scene spec, expected routes, evidence-envelope JSON schema, the resolver itself, the manifest itself, and
the manifest schema). Five **future** dependencies (signature/revocation/clock/observer-policy, runtime
backend) are recorded in a documentation-only `future_dependencies` array with `status:
not_yet_implemented` and an owning gate — they are **not** resolved until the files exist. Each dependency
carries: id, repository-relative path, type, required flag, owning gate, block reason; the manifest
`default_dependency_policy` supplies expected object type/mode/symlink/LFS/submodule/digest/history policy.

**Repository identity is bound by `(canonical_name + root_commit = 67b03838…)`, NOT by absolute machine
path, folder name, cwd, or mere `.git` presence** (§7).

## 6. Resolver architecture (§6)

Pure/narrowly side-effect-free; all effects injected (Git runner, filesystem reader, digest function,
optional clock). Git is invoked with **argument arrays** (`git -C <repo> <args>`), never shell strings.
Components: `resolve_repository_identity`, `resolve_head`, `is_shallow`, `is_detached`, `_status_map`
(single porcelain pass), `_ls_tree`/`_ls_files_stage`/`_ls_files_flags`, `evaluate_dependency`,
`_resolve_submodule`, `_resolve_lfs`, `_symlink_escapes`, `load_dependency_manifest`, `_closure_digest`,
`build_resolution_report`, plus the provider-boundary functions `report_binding_ok` and
`provider_tree_state`.

## 7. Policies (§7–§17)

- **Repository identity (§7):** `--show-toplevel` must equal the expected root path; if `root_commit` is
  declared it must be a genuine root commit in HEAD's history; optional `canonical_name` check. Copied
  files outside Git, nested/other repositories, and missing metadata all reject.
- **Commit binding (§8):** distinct HEAD blob id, index blob id and worktree digest are recorded. A file is
  never reported as "from HEAD" when its index/worktree content differs.
- **Tracked-file validation (§9):** present at the expected path, tracked, blob object, present in the
  index (a HEAD file absent from the index = staged deletion → reject), not modified/deleted/renamed/
  mode-changed, not symlink-substituted.
- **Staged/unstaged (§10):** a single porcelain pass distinguishes staged (`X`) vs worktree (`Y`) changes;
  rename/copy, delete, typechange, staged-modification and worktree-modification each get a specific code.
  `assume-unchanged` and `skip-worktree` are **forbidden** for protected dependencies (fail closed).
- **Untracked/ignored (§11):** untracked, ignored, and deleted-then-recreated-untracked all reject; an
  ignored file is not trusted merely because status normally omits it.
- **Symlink (§12):** protected dependencies must be ordinary tracked files unless `allow_symlink`;
  unexpected symlink, absolute target, escape-outside-repo, and broken/missing target all reject. Static
  inspection **cannot** claim complete TOCTOU elimination (documented, `H8-C-033`).
- **Path containment (§13):** absolute paths, `..` traversal, NUL, and backslash separators reject; git is
  never handed an out-of-repo path (they are caught as `DEPENDENCY_PATH_INVALID` first).
- **LFS (§14):** LFS pointer files are detected; the default `materialised_required` policy **fails closed**
  (git-lfs is not installed here — materialisation is never downloaded); malformed pointers reject; a
  `pointer_ok` policy accepts the pointer itself.
- **Submodule (§15):** a gitlink with no submodule policy, or a commit mismatch, rejects. Submodules are
  never initialised/updated.
- **Worktree/detached/shallow (§16):** detached HEAD is permitted where identity is unambiguous; a shallow
  repository with any `provenance_requires_history` dependency → `GIT_HISTORY_INSUFFICIENT`.
- **Git command failure (§17):** every git call has a timeout, captured rc/stderr, a structured failure
  code and no shell. Git unavailable/timeout/unexpected result → reject. "Could not inspect" is never clean.

## 8. Result & aggregate models (§18/§19)

Per-dependency result: id, path, accepted, reason_code, required, type, head/index object ids, worktree
digest, git status, tracked, object type, file mode, symlink/lfs/submodule status, policy+resolver
versions, explanation. Aggregate: overall_accepted, reason_code, repository identity, head_commit,
manifest_digest, dependency/accepted/rejected/unresolved counts, per-dependency results, **closure_digest**
(excludes volatile metadata → deterministic), failures, generation time + clock-trust classification.
Overall acceptance requires every **mandatory** dependency to pass; any unknown/unresolved mandatory
dependency rejects the aggregate.

## 9. Reason-code taxonomy (§20) — active vs reserved

32 codes total; **31 active, 1 reserved** (`REPORT_STALE`, reserved for a future time-based staleness path
that needs the not-yet-built trusted clock; stale reports are presently rejected via
`REPORT_CLOSURE_DIGEST_MISMATCH`, a content-bound check). **31/31 active codes are directly triggered** by
the test suite.

## 10. Provider integration boundary (§21) — fail closed

The evidence provider consumes the resolver **only** through the injected `tree_state` seam via
`provider_tree_state(resolver, manifest, *, mode, expected_head, expected_closure_digest)`. It returns the
provider's `{commit, dependency_dirty, resolution_digest, resolution}` dict, setting `dependency_dirty=True`
(fail closed) for any non-clean / unavailable / fixture-resolver / repo-mismatch / HEAD-mismatch / stale
(closure-digest-mismatch) condition, and only `False` for an approved, accepted, bound report. A clean
report permits a preflight **document** (status `indeterminate`) whose provenance records the
`dependency_resolution_digest`; it **never** yields runtime-valid evidence and never authorises capture.

| Resolver state | Provider result | Capture | Backend calls |
|---|---|---|---|
| approved clean report | `PROVIDER_OK_PREFLIGHT` (document) | blocked | 0 |
| dependency dirty | `PROVIDER_DIRTY_TREE` | blocked | 0 |
| resolver unavailable / crash | `PROVIDER_DIRTY_TREE` | blocked | 0 |
| fixture resolver in protected mode | `PROVIDER_DIRTY_TREE` | blocked | 0 |
| report HEAD mismatch | `PROVIDER_DIRTY_TREE` | blocked | 0 |
| stale (closure-digest mismatch) | `PROVIDER_DIRTY_TREE` | blocked | 0 |

There is no `assume_clean` bypass, no optional resolver in protected mode, and no capture authorisation from
a resolver report.

## 11. Resolver trust identity (§22) & stale invalidation (§24)

Resolver identity (`resolver_id`, version, policy version, approved/fixture classification) is external to
report *content* — a report cannot self-authorise; `report_binding_ok` rejects any non-approved
`resolver_id`. Stale invalidation is content-bound: a report is invalid when its `closure_digest` no longer
matches the caller's expected digest (HEAD change, index change, protected-file change, manifest/policy
change, or resolver-version change all change the digest). Strong time-based freshness is **not** claimed —
it depends on the future trusted clock (`REPORT_STALE` reserved, `H8-C-034`).

## 12. Determinism (§25)

Given identical repository/HEAD/index/worktree/manifest/policy/resolver-version, the resolver produces
identical dependency decisions and an identical `closure_digest`. Volatile fields (generation time, host
paths) are excluded from the digest. Verified: repeated runs and reordered manifest entries yield the same
closure digest; different injected clocks do not change it.

## 13. Threat model (§23)

| Threat | Prevention / detection → result |
|---|---|
| copied-repo spoofing / root confusion / nested repo | root-commit + toplevel binding → `GIT_REPOSITORY_MISMATCH`/`_NOT_FOUND` |
| staged / unstaged / both content substitution | porcelain X/Y → `DEPENDENCY_STAGED_MODIFICATION` / `_WORKTREE_MODIFICATION` |
| untracked / ignored / deleted-then-recreated substitution | tracked+index check → `DEPENDENCY_UNTRACKED` / `_DELETED` |
| path traversal / absolute / NUL | path validation → `DEPENDENCY_PATH_INVALID` |
| symlink escape / unexpected symlink / broken target | symlink policy → `DEPENDENCY_SYMLINK_UNEXPECTED` / `_ESCAPE` |
| symlink race (TOCTOU) | **residual** — static inspection cannot fully prevent (`H8-C-033`) |
| mode-change | expected-mode / typechange → `DEPENDENCY_MODE_CHANGED` |
| case-folding / Unicode-confusable path | exact tracked-path identity → missing/untracked |
| `assume-unchanged` / `skip-worktree` concealment | `ls-files -v` flags → `DEPENDENCY_ASSUME_UNCHANGED` / `_SKIP_WORKTREE` |
| sparse-checkout concealment | missing worktree file → `DEPENDENCY_MISSING` |
| LFS pointer without object / malformed pointer | pointer detection → `DEPENDENCY_LFS_UNAVAILABLE` |
| submodule commit substitution / dirty / missing | gitlink policy → `DEPENDENCY_SUBMODULE_MISMATCH` |
| Git binary failure / injection / timeout / partial output | arg-arrays, timeout, rc capture → `GIT_COMMAND_FAILED` / `_TIMEOUT` |
| shallow-history provenance gap | `--is-shallow-repository` → `GIT_HISTORY_INSUFFICIENT` |
| dependency-manifest omission | count reported; completeness is the manifest author's responsibility (`H8-C-035`) |
| resolver report forgery / fixture resolver in protected mode | approved-id gate → `RESOLVER_FIXTURE_IN_PROTECTED` |
| stale report reused after change | closure-digest binding → `REPORT_CLOSURE_DIGEST_MISMATCH` |
| blob/object mismatch | pinned sha check → `DEPENDENCY_BLOB_MISMATCH` |

Residual risks are recorded as challenges (§ below) and owned by future gates; complete TOCTOU prevention is
explicitly **not** claimed.

## 14. Conformance results (§26–§28)

- **Positive (§26):** clean single-file and full-closure accept; repository identity bound; optional-missing
  handled; deterministic + reorder-invariant closure digest; clock excluded from digest. The positive path
  proves the resolver is **not** reject-all.
- **Negative (§27):** staged/unstaged/both modification, delete, rename, missing, untracked,
  untracked-replacement, ignored, mode-change, object-type-tree, blob-mismatch, invalid paths
  (absolute/traversal/NUL/backslash), case-variant, unexpected/escape/broken symlink, assume-unchanged,
  skip-worktree, LFS-pointer-without-object, malformed-LFS, digest-failure, repository-not-found,
  repository-mismatch, empty-repo HEAD-unresolved, manifest-invalid, git-command-failed, git-timeout,
  shallow-history, submodule-mismatch — **all fail closed**.
- **Provider integration (§28):** the 6-row table above holds; **backend invocation = 0** and provider
  output = 0 on every blocked case.

## 15. Decisions & challenges

Decisions `H8-DCP-047…057` (decision log). Challenges `H8-C-033…038` (failure register): symlink-TOCTOU
residual; trusted-clock-dependent freshness; manifest-completeness responsibility; git-lfs materialisation
unverifiable here; git-version behaviour variance; Ruff unavailable (`H8-C-006`/`H8-C-013`).

## 16. Evidence boundary (§38)

Establishes: Git dependency-resolver validity; dependency-closure completeness (for the declared closure);
clean/dirty repository-state detection; repository identity binding; resolver/provider preflight
integration; a deterministic dependency-closure digest. **Does NOT establish:** runtime render/drive
validity, Isaac launch validity, trusted wall time, production signatures, operational revocation, dataset
validity, model validity, or capture authorisation. **This is not Level 3.**

## 17. Verdict (§39)

**`PASS WITH DOCUMENTED LIMITATIONS`** — functional clean positive path; every mandatory dirty/substitution
case fails closed; protected provider modes require the resolver (no bypass); no capture or backend
connectivity; documentation + traceability complete. Documented limitations: symlink-TOCTOU residual,
time-based freshness pending the trusted clock, git-lfs materialisation unverifiable in this environment,
and Ruff Open.

## 18. Recommendation (§55)

An **independent G1 resolver review** (adversarial re-verification of the fail-closed matrix, repository
identity binding, provider integration and determinism) should run **before** trust-infrastructure (G2) or
observer-stub (G3) implementation. The next Isaac-capable code remains several gates away:
`G1 review → resolver remediation → G2 trust/signature/revocation test infra → G3 observer stubs →
G4 disabled Isaac worker skeleton → G5 launch-readiness (reviewed)`.
