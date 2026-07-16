# H8 Git Dependency Resolver — G1R2 Mandatory-Dependency & Git-Environment Hardening

**Gate:** G1R2 — bounded, non-Isaac, non-capturing remediation (round 2).
**Baseline reviewed:** `2de2ee71d9e69cfefcbe1b92ed4af8ef90d59bca` (G1R); re-review `78703fded466bf91c8b98de8d6c5c0a66dd5a1e5`.
**Scope:** `scripts/gnm/h8_git_dependency_resolver.py` (+ tests) and documentation. Additive, non-capturing.
**Claim boundary:** `SYNTHETIC_DIAGNOSTIC_ONLY`. No Isaac/Omniverse/ROS 2/render/drive/capture/inference/
training; no signing/keys/revocation/trusted-time/origin-attestation. **This is not Level 3.** Real
hospital footage & trajectory collection remains blocked.

Closes the non-cryptographic defects raised by the G1R re-review. Earlier review/remediation reports are
preserved; the G1R remediation report carries an appended G1R2 clarification (closing `H8-G1RREV-F-004`).

---

## 1. Findings addressed

| Finding | Sev | Disposition |
| --- | --- | --- |
| `H8-G1RREV-F-001` — mandatory-set enforcement presence-only (optional-weakening accepted) | Medium | **CLOSED** |
| `H8-G1RREV-F-003` — security-relevant `GIT_*` env not scrubbed | Low | **CLOSED** (env vector); local committed filters remain `H8-C-040` |
| `H8-G1RREV-F-004` — imprecise caller-manifest documentation | Info | **CLOSED** |
| `H8-G1RREV-F-002` — semantic per-dependency identity not bound | Low | **OPEN — DOCUMENTED LIMITATION, deferred to G2** |

Decisions `H8-DCP-063…066`; challenge `H8-C-042`.

## 2. Pre-remediation reproduction (against `2de2ee7`)

- **F-001 required-flag:** on a mandatory id (`h8-evidence-provider`) that was then dirtied — `required:false`,
  `null`, `0` → **ACCEPTED** (weakened+dirty passed). `missing`/`1`/`"true"`/`"false"` were treated as
  required by truthiness accident. **Root cause:** `resolve_canonical` checked `REQUIRED_DEPENDENCY_IDS -
  set(by_id)` (presence) and `_dep_result` coerced `bool(dep.get("required", True))`.
- **F-003 env:** `GIT_INDEX_FILE` changed a clean result to a failure (env influenced the decision);
  `GIT_ALTERNATE_OBJECT_DIRECTORIES`/`GIT_CONFIG_GLOBAL` were inherited unscrubbed. **Root cause:** the runner
  built the child env from `dict(os.environ)` overriding only `LC_ALL`/`LANG`.
- Duplicate ids already failed closed (`DEPENDENCY_MANIFEST_INVALID`).

## 3. F-001 — exact `required: true` for mandatory ids (CLOSED)

`resolve_canonical` now enforces, after the presence check:

```
not_required = [i for i in REQUIRED_DEPENDENCY_IDS if by_id[i].get("required") is not True]
→ MANDATORY_DEPENDENCY_NOT_REQUIRED
```

`is not True` is an **identity** check — no truthiness coercion. Every weakening form rejects:
`false`, missing, `null`, `0`, `1`, `"true"`, `"false"` → `MANDATORY_DEPENDENCY_NOT_REQUIRED`; only exact
boolean `true` counts toward mandatory coverage. The manifest JSON schema already types `required` as
`boolean` and lists it as a required key. A **non-mandatory** dependency may still be `required:false`
legitimately (the control is scoped to the mandatory set). The original exploit (weaken to `false` **and**
dirty the file) now fails closed.

## 4. Duplicate mandatory dependency (CLOSED)

`load_dependency_manifest` splits empty-id (`DEPENDENCY_MANIFEST_INVALID`) from duplicate-id, and takes a
`duplicate_code`. The canonical path passes `MANIFEST_DUPLICATE_DEPENDENCY`, so duplicate mandatory ids fail
closed with a specific code rather than collapsing under last-write-wins in the `{id: dep}` map. The generic
`build_resolution_report` path keeps `DEPENDENCY_MANIFEST_INVALID` (no regression).

## 5. F-003 — explicit Git subprocess-environment policy (CLOSED for the env vector)

Three classes (see module constants):

- **Class A — forced-safe** (`_GIT_ENV_FORCE`, applied every invocation): `LC_ALL=C`, `LANG=C`,
  `GIT_CONFIG_NOSYSTEM=1` (ignore `/etc/gitconfig`), `GIT_CONFIG_GLOBAL=os.devnull` (neutralise a hostile
  `~/.gitconfig`), `GIT_ATTR_NOSYSTEM=1` (ignore system gitattributes/textconv/filters),
  `GIT_OPTIONAL_LOCKS=0`, `GIT_TERMINAL_PROMPT=0`. Repository identity is carried by `-C`, never by env.
- **Class B — removed from the child env** (`_GIT_ENV_REMOVE` + `GIT_CONFIG_KEY_*/GIT_CONFIG_VALUE_*`
  prefixes): `GIT_DIR`, `GIT_WORK_TREE`, `GIT_COMMON_DIR`, `GIT_OBJECT_DIRECTORY`,
  `GIT_ALTERNATE_OBJECT_DIRECTORIES`, `GIT_INDEX_FILE`, `GIT_REPLACE_REF_BASE`, `GIT_NAMESPACE`,
  `GIT_CONFIG[_GLOBAL/_SYSTEM/_COUNT]`, `GIT_CEILING_DIRECTORIES`, `GIT_DISCOVERY_ACROSS_FILESYSTEM`,
  `GIT_ATTR_SYSTEM`, and the four pathspec vars. `_build_git_env()` constructs the child env explicitly;
  ordinary vars (`PATH`, `HOME`, …) are preserved so git executes normally.
- **Class C — inspected and rejected** (`_GIT_ENV_PROHIBITED`): `resolve_canonical` calls
  `_prohibited_git_env()` first and fails closed with **`GIT_ENV_UNSUPPORTED`** if any redirection/override
  variable (or `GIT_CONFIG_KEY_*/VALUE_*`) is present in the parent environment — ambiguous env is never
  treated as clean, even though the child env also scrubs it (defence in depth).

**Behavioural proof:** under a hostile `GIT_DIR` pointing at a decoy repository, the runner's
`rev-parse --absolute-git-dir` still resolves the **real** repo's git-dir (scrubbed, not redirected). A
benign environment variable neither trips rejection nor changes the closure digest.

**Residual (unchanged `H8-C-040`):** repository-**local**, **committed** `.gitattributes` + clean/smudge
filter definitions are read (local config is always honoured); a committed hostile filter is within the
author/committed-artifact boundary and is **not** claimed eliminated. `GIT_ATTR_NOSYSTEM` + config-nosystem
neutralise the **system/global** vectors only.

## 6. F-004 — documentation boundary (CLOSED)

The G1R remediation report now carries an appended clarification stating precisely what the caller-manifest
control eliminates (arbitrary manifest selection; drop/rename/**downgrade-to-optional** weakening;
duplicate) and what it does **not** (semantic content identity of each mandatory entry; report cryptographic
authentication; physical origin). See that document's "G1R2 clarification" section.

## 7. F-002 — semantic per-dependency identity (OPEN — documented limitation)

Re-pointing a mandatory id's `path` at another tracked/clean file of the expected type is still accepted:
the resolver binds `path + tracked + clean + HEAD`, not content/semantic identity. Binding an expected
per-dependency content digest would require a manifest/schema content change and broad program analysis —
**out of scope** for this bounded gate and explicitly deferred to G2. This is kept visible by a dedicated
test (`test_g1r2_path_substitution_remains_documented_limitation`) so it is **not** disguised as solved
through category presence. Residual statement: *the resolver verifies declared identities and known policy
mappings; it does not automatically discover every semantic dependency introduced by future code.*

## 8. New reason codes

`MANDATORY_DEPENDENCY_NOT_REQUIRED`, `MANIFEST_DUPLICATE_DEPENDENCY`, `GIT_ENV_UNSUPPORTED`
(`REASON_CODES` 38 → 41; all active; each has deterministic tests). `REPORT_STALE` remains reserved.

## 9. Verification

| Check | Result |
| --- | --- |
| Resolver suite | **107 passed** (75 + 32 G1R2) |
| Full matching H8 suite (`tests/gnm/test_h8_*.py`) | **330 passed** (298 + 32) |
| Dataset dry-run | `all_checks_pass=True`; regeneration **byte-identical** |
| Level-1 evidence | **5/5 byte-identical** |
| `py_compile` (resolver + tests) | OK |
| Attribution / secret scans | clean |
| `git diff --check` | clean |
| Negative-artifact audit | no evidence/runtime/dataset dir created |
| `CL_BOUND_XY` | **6.0** (unchanged) |
| Ruff | **unavailable — Open** (not represented as passing) |

**Positive path preserved (not reject-all):** a clean canonical repo with a safe environment still resolves
`ACCEPTED` → `PROVIDER_OK_PREFLIGHT` (non-authorising document; capture blocked; backend 0).

## 10. Provider-integration invariants (unchanged)

Protected provider operations still use the trusted factory + canonical manifest only; reject caller
reports and caller manifest paths; reject dirty/weakened manifests and hostile Git environments; permit
legitimate clean preflight generation; produce only non-authorising evidence; remain capture-blocked;
invoke no backend. Provider module unchanged.

## 11. G2-owned residuals (still deferred)

Cryptographic resolver-report authentication; trusted timestamps; report revocation; repository/release
attestation; authorised physical/organisational origin proof; production signing identities;
identical-history impersonation defence across trust domains; semantic per-dependency identity discovery;
residual TOCTOU.

## 12. Overall verdict

**PASS WITH DOCUMENTED LIMITATIONS.** Exact required-Boolean enforced; duplicate ids rejected; hostile Git
environment cannot redirect trust decisions (scrubbed + rejected); legitimate clean path usable; no caller
report/manifest bypass; preflight non-authorising; no runtime capability introduced. `H8-G1RREV-F-002` and
the cryptographic/origin/TOCTOU residuals remain explicitly deferred to G2.

**Recommendation:** a focused **independent G1R2 verification** — confirming exact required-Boolean
enforcement, duplicate rejection, Git-environment scrub+reject behaviour (not just constants), the preserved
clean positive path, and the honestly-bounded F-002/G2 residuals — **before** opening the separately scoped
G2 cryptographic-trust **design** gate. No signing infrastructure, observer work, Isaac-capable code or
hospital capture begins until these controls are independently verified.
