# H8 Git dependency resolver — focused independent G1R2 verification

**Scope.** Focused independent verification of the G1R2 boundary-hardening commit
`efa671abc18bde1e6c1f942360cb8d957db60729` ("Complete H8 Git resolver boundary
hardening") on branch `h23-execfix`, before the separately scoped G2 cryptographic-trust
**design** gate. Review-only: this pass changed **no** resolver/test/manifest/schema/
provider code; the resolver-relevant tracked files are byte-identical to `efa671a`.

**Method (independent, not the project's own test file).** Properties were reconstructed
from freshly constructed temporary git repositories (canonical manifest + full 13-file
closure, `expected_repository` unbound) and from the **live repository at `efa671a`**,
driving `resolve_canonical` / `trusted_provider_tree_state` / `SubprocessGitRunner`
directly and asserting reason codes. The project's own resolver suite was additionally run
as a regression cross-check.

**Non-actions.** No Isaac/Omniverse/ROS/render/drive/capture; pure-python + git on
temporary repositories only. Nothing pushed, tagged, or amended (`h23-execfix` has no
upstream; 0 tags on HEAD). Levels 3–5 remain unproven; real hospital collection blocked;
`CL_BOUND_XY=6.0` untouched.

---

## Result

**PASS — every claimed G1R2 property independently reproduced; no new finding.** The
verification produced **no** new Critical/High/Medium/Low finding. `H8-G1RREV-F-002`
(semantic per-dependency content identity) and the cryptographic/origin/TOCTOU items
remain OPEN and are honestly documented as deferred to G2.

**G2 eligibility = ELIGIBLE for the G2 cryptographic-trust DESIGN gate** (design only —
not capture, not Isaac). The two G1R re-review findings that gated eligibility
(`H8-G1RREV-F-001`, `H8-G1RREV-F-003`) are independently confirmed CLOSED.

---

## Independent evidence (28/28 checks passed)

### (a) Exact required-Boolean enforcement — `H8-G1RREV-F-001` CLOSED
`resolve_canonical` requires each of the 10 `REQUIRED_DEPENDENCY_IDS` to have
`required is True` (identity, no truthiness coercion).

- Control (`required=true`, committed clean canonical repo) → **ACCEPTED**.
- Every weakening form independently rejected with **`MANDATORY_DEPENDENCY_NOT_REQUIRED`**:
  `false`, `null`, `0`, `1`, `"true"`, `"false"`, `1.0`, and the **missing** key. (`1`,
  `1.0` and the string forms are notable: `== True` is irrelevant; only the boolean
  singleton passes.)
- Scope correct: a **non-mandatory** dependency committed with `required=false` still
  resolves **ACCEPTED** — the rule binds only the mandatory set.

### (b) Duplicate-ID rejection — `MANIFEST_DUPLICATE_DEPENDENCY`
- Duplicate mandatory id in the canonical manifest → **`MANIFEST_DUPLICATE_DEPENDENCY`**
  (last-write-wins collapse in a `{id: dep}` map is prevented).
- Empty id → **`DEPENDENCY_MANIFEST_INVALID`** (distinct code; the empty-id guard runs
  before the duplicate guard).
- The generic loader path (`load_dependency_manifest` without `duplicate_code`) still
  raises **`DEPENDENCY_MANIFEST_INVALID`** for duplicates — the specialised code is scoped
  to the canonical path only.

### (c) Git-environment scrub + reject **behaviour** — `H8-G1RREV-F-003` CLOSED
- `resolve_canonical` fails closed with **`GIT_ENV_UNSUPPORTED`** when any prohibited
  redirection variable is present in the parent environment: verified for `GIT_DIR`,
  **`GIT_ALTERNATE_OBJECT_DIRECTORIES`** (the exact variable the G1R re-review flagged as
  previously undetected), `GIT_OBJECT_DIRECTORY`, `GIT_INDEX_FILE`, `GIT_CONFIG_GLOBAL`,
  and the `GIT_CONFIG_KEY_*/VALUE_*/COUNT` config-injection vector.
- **Hostile `GIT_DIR` is not honoured**: with `GIT_DIR` pointed at a non-existent decoy,
  `SubprocessGitRunner.run(real_repo, ["rev-parse","HEAD"])` returns the **real** repo
  HEAD (child environment scrubbed the variable; identity carried by `-C`), not an error
  or the decoy.
- `_build_git_env()` structurally removes the redirectors and forces
  `GIT_CONFIG_GLOBAL=os.devnull`, `GIT_CONFIG_NOSYSTEM=1`, `LC_ALL=C`.

### (d) Preserved clean positive path (not test-specific)
- **Live repository** `resolve_canonical` → **ACCEPTED**, `reason_code=ACCEPTED`,
  `head_commit=efa671abc18b…`, `closure_digest=sha256:a7060613…`, evaluated against the
  real 13-entry manifest and real files **with the 352 dirty dataset files present in the
  working tree** (none in the closure). This is a live proof, not a fixture.
- Live `trusted_provider_tree_state(repo)()` → `dependency_dirty=False`,
  `resolution_reason=ACCEPTED`.

### (e) Residuals honestly bounded
- `trusted_provider_tree_state` exposes **no** caller-injection parameter
  (`resolver/report/manifest/assume_clean/allow_dirty` all absent from its signature); the
  only extra parameters are the documented test-only `git`/`fs` seam with no acceptance
  authority.
- `H8-G1RREV-F-002` is kept **visible**, not disguised: a dedicated test asserts the
  path-substitution case is **accepted** (`overall_accepted is True`), and the round-2
  remediation document lists it "OPEN — DOCUMENTED LIMITATION, deferred to G2" alongside
  the §11 G2-owned residuals (cryptographic report authentication, trusted timestamps,
  revocation, repository/release attestation, physical origin proof, semantic content
  identity, local committed `.gitattributes`/filter influence `H8-C-040`, residual
  TOCTOU).
- New reason codes (`MANDATORY_DEPENDENCY_NOT_REQUIRED`, `MANIFEST_DUPLICATE_DEPENDENCY`,
  `GIT_ENV_UNSUPPORTED`) are registered in `REASON_CODES`.

---

## Regression cross-check
- Project resolver suite `tests/gnm/test_h8_git_dependency_resolver.py`: **107 passed**
  (independent run, `python3 -m pytest`).
- Resolver-relevant tracked files clean and HEAD-bound; the working-tree modifications are
  dataset/experiment artifacts outside the resolver closure.

## Verdicts
| Control | Verdict |
|---|---|
| (a) exact required-Boolean, all weakening forms rejected | PASS |
| (b) duplicate-id rejection + distinct empty/generic codes | PASS |
| (c) git-env scrub + reject behaviour incl. hostile-`GIT_DIR` proof | PASS |
| (d) preserved clean positive path on the live repo | PASS |
| (e) F-002 / G2 residuals honestly bounded | PASS |
| Overall | **PASS WITH DOCUMENTED LIMITATIONS** |

## Recommendation
Open the separately scoped **G2 cryptographic-trust DESIGN gate** (design only — signing,
trusted timestamps, revocation, origin attestation, semantic content identity as its
agenda). No signing infrastructure, observer work, Isaac-capable code, or hospital capture
begins under this verification. Programme: G1R re-review → G1R2 → **G1R2 verification
(this document)** → G2 cryptographic-trust design.
