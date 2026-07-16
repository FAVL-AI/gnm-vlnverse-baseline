# H8 Git Dependency Resolver — G1R Trust-Boundary Remediation

**Gate:** G1R — Harden H8 Git resolver trust boundary
**Date:** 2026-07-16
**Scope:** `scripts/gnm/h8_git_dependency_resolver.py` (+ tests). Additive, design-and-implementation only.
**Claim boundary:** `SYNTHETIC_DIAGNOSTIC_ONLY`. This gate introduces **no** runtime, capture, Isaac,
Omniverse, ROS 2, render, drive, inference, training or dataset-writer capability. A clean resolution
permits **only** non-authorising preflight document generation, exactly as before. **This is not Level 3.**

This document records the remediation of the four findings raised by the independent G1 review
(`H8_GIT_DEPENDENCY_RESOLVER_INDEPENDENT_REVIEW.md`, §18). The review document is preserved unchanged with
an appended disposition table. The dispositions here are the implementer's account and are **subject to a
focused independent G1R re-review before G2**.

---

## 1. Findings and dispositions

| Finding | Severity | Disposition |
| --- | --- | --- |
| `H8-G1REV-F-001` — resolver report is not authenticated | Medium | **PARTIALLY CLOSED — TRUSTED IN-PROCESS CONSTRUCTION** |
| `H8-G1REV-F-002` — integration does not bind to the canonical manifest | Medium | **CLOSED** |
| `H8-G1REV-F-003` — Git config can mask mode/symlink/EOL/object identity | Low | **MITIGATED WITH DOCUMENTED LIMITATIONS** |
| `H8-G1REV-F-004` — identity binds history, not physical origin | Low | **OPEN — DEFERRED TO G2 CRYPTOGRAPHIC ORIGIN ATTESTATION** |

Decisions: `H8-DCP-058…062`. Challenges: `H8-C-039…041`.

---

## 2. F-001 — report authentication (PARTIAL) + trusted construction (PRIMARY)

**Problem.** `report_binding_ok` trusted a self-declared `resolver_id` string. A plain
`{"resolver_id": RESOLVER_ID, "overall_accepted": True}` dict passed and drove `provider_tree_state` to a
clean preflight — a forged resolution with no actual current-state resolution behind it.

**Two-layer remediation.**

1. **In-process authenticity marker (partial).** The genuine resolver stamps
   `authenticity = "h8-resolver-authentic/1.0.0"` (`_REPORT_AUTHENTICITY`) on **every** report it produces
   (accepted or rejected — the marker lives in the shared `base` dict). `report_binding_ok` now rejects any
   report lacking the marker with the new reason code **`REPORT_UNAUTHENTIC`**, *before* honouring
   `overall_accepted` or the `resolver_id`. An ordinary caller-forged dict is therefore rejected.
   This is **explicitly not cryptographic**: code with module access can import and copy the constant. That
   residual is honestly documented (`H8-C-039`) and a dedicated test (`test_g1r_module_access_forgery_is_
   documented_residual`) asserts it, so the limitation cannot be silently mistaken for full authentication.

2. **Trusted construction path (primary, structural).** Protected provider modes obtain their tree-state via
   the new factory **`trusted_provider_tree_state(repo_root, *, mode="preflight", ...)`**. It constructs the
   genuine resolver in-process and **re-resolves current state on every call**. It exposes **no parameter**
   for a caller-supplied resolver, resolution report, manifest object/path, or assume-clean flag. A
   `inspect.signature` test (`test_g1r_trusted_factory_has_no_report_or_manifest_injection`) enforces this
   structurally. The `git`/`fs` keywords are a **documented test-only fixture seam** carrying no acceptance
   authority (the resolver still fails closed on any dirty/missing/substituted dependency); the real provider
   construction path calls `trusted_provider_tree_state(repo_root)` with defaults.

The durable control is layer 2: a protected caller **never accepts a caller report at all**, so a forged
resolution cannot be substituted regardless of marker knowledge. Layer 1 hardens the lower-level
`report_binding_ok` seam that remains available to fixtures/tests. Full cryptographic report authentication
is deferred to **G2**.

## 3. F-002 — canonical manifest enforcement (CLOSED)

**Problem.** `provider_tree_state`/`build_resolution_report` accepted a caller-selected manifest (path or
in-memory dict). A reduced dict could omit or hide a dirty decision-critical dependency; the resolver only
protected the manifest when it was passed by tracked path and self-listed.

**Remediation — `resolve_canonical()`.** Protected callers use this method, which:

1. runs `inspect_git_config` first (see F-003) and fails closed on rejection;
2. loads **only** `CANONICAL_MANIFEST_REL = "configs/gnm/h8_dependency_manifest.json"` — never a
   caller-selected path or in-memory dict;
3. requires the manifest to **self-list at the canonical path** (the `h8-dependency-manifest` dependency's
   `path` must equal `CANONICAL_MANIFEST_REL`), else **`MANIFEST_NOT_CANONICAL`**;
4. enforces a machine-checked mandatory id set **`REQUIRED_DEPENDENCY_IDS`** (10 ids); any absent id →
   **`MANIFEST_INCOMPLETE`**. A caller can no longer silently drop a known decision-critical dependency;
5. delegates to `build_resolution_report(canonical_path)` so the canonical manifest **file itself** is
   resolved (tracked + unmodified + bound to HEAD), and defence-in-depth re-checks that the manifest-self
   dependency resolved clean.

`REQUIRED_DEPENDENCY_IDS` is a strict subset of the shipped manifest's ids and is asserted against the
shipped file (`test_g1r_canonical_constants_bind_shipped_manifest`), so drift is caught by tests.

## 4. F-003 — Git configuration and object identity (MITIGATED, documented limits)

**Problem.** Repository-local Git config could mask changes: `core.fileMode=false` (chmod), `core.symlinks`,
`core.autocrlf` (EOL), plus object-identity redirection via `refs/replace/*` and alternate object DBs.

**Remediation.**

* **Pinned on every invocation.** `SubprocessGitRunner.run` prepends
  `_GIT_SAFE_OVERRIDES = -c core.fileMode=true -c core.symlinks=true -c core.ignorecase=false
  -c core.autocrlf=false --no-replace-objects` and runs under `LC_ALL=C`/`LANG=C`. A behavioural test
  (`test_g1r_local_filemode_false_does_not_mask_mode_change`) sets `core.fileMode=false` locally, chmods a
  tracked file, and confirms the resolver still reports it **not accepted**.
* **Explicit inspection + rejection.** `inspect_git_config()` rejects a repository carrying replace refs
  (**`GIT_REPLACE_OBJECTS`**) or an alternate object database (**`GIT_ALTERNATE_OBJECTS`**); `resolve_canonical`
  runs it first and fails closed. A clean repository passes (not reject-all).

**Documented limitation (`H8-C-040`).** This neutralises the **enumerated** surfaces. It is **not** an
exhaustive proof that no Git configuration, clean/smudge filter or textconv can influence any observation.
That claim is deliberately *not* made. `GIT_CONFIG_UNSUPPORTED` is reserved for a future explicit
config-assertion path.

## 5. F-004 — physical origin (OPEN, deferred to G2)

Repository identity binds `(canonical_name + root_commit + history)`. An exact copy of the Git object
history reproduces that identity. This is **not** closable by ordinary Git inspection and is **explicitly not
closed via remote-URL comparison** (a remote URL is caller-mutable and proves nothing about physical origin).
Cryptographic origin attestation (signed provenance / attestation infrastructure) is deferred to **G2** or a
later provenance-infrastructure gate (`H8-C-041`).

---

## 6. New reason codes (taxonomy delta)

Six active codes added (all in `REASON_CODES` ∩ `ACTIVE_CODES`):

| Code | Meaning |
| --- | --- |
| `REPORT_UNAUTHENTIC` | report lacks the in-process authenticity marker (ordinary forgery) |
| `MANIFEST_NOT_CANONICAL` | protected mode selected/loaded a non-canonical or non-self-listing manifest |
| `MANIFEST_INCOMPLETE` | a machine-enforced mandatory dependency id is absent |
| `GIT_CONFIG_UNSUPPORTED` | reserved for explicit security-relevant config assertion (future) |
| `GIT_REPLACE_OBJECTS` | `refs/replace/*` present — object substitution surface |
| `GIT_ALTERNATE_OBJECTS` | alternate object database configured |

`REPORT_STALE` remains reserved; `RESERVED_CODES` unchanged.

---

## 7. Verification (this gate)

| Check | Command | Result |
| --- | --- | --- |
| Resolver suite | `pytest tests/gnm/test_h8_git_dependency_resolver.py` | **75/75 PASS** (56 prior + 19 G1R) |
| Full matching H8 suite | `pytest tests/gnm/test_h8_*.py` | **298 PASS** (279 pre-G1R + 19) |
| Dataset dry-run | `--mode dataset-dry-run --emit-schema --config …_dataset.yaml` | `all_checks_pass=True`; regeneration **byte-identical** |
| Level-1 evidence | `git status --porcelain` on tracked Level-1 artifacts | **CLEAN — 5/5 byte-identical to HEAD** |
| Byte-compile | `python -m py_compile` (resolver + tests) | OK |
| Attribution scan | grep for vendor/AI/co-author strings | none |
| Secret scan | grep for keys/tokens/private-key markers | none (only doc "capture token", parser `tokens` var) |
| Whitespace/conflict | `git diff --check` | clean |

**Positive-path proof (not reject-all):** `test_g1r_trusted_factory_clean_canonical_accepts`,
`test_g1r_provider_uses_trusted_factory_clean_permits_preflight` and
`test_g1r_clean_repo_passes_git_config_inspection` all show clean inputs are ACCEPTED.

Preserved invariants: `CL_BOUND_XY = 6.0` unchanged; provider trust boundary otherwise unchanged (the only
prior provider change, the additive `dependency_resolution_digest`, is retained); Ruff still **Open**
(`H8-C-006`/`H8-C-013`); real capture blocked; Levels 3–5 unproven.

---

## 8. Boundary and limitations

Establishes a hardened resolver→provider integration boundary: trusted in-process construction, canonical
manifest enforcement, mandatory-dependency-set enforcement, pinned Git config, and object-identity
substitution rejection. **Does NOT establish** cryptographic report authentication (F-001 residual, G2),
exhaustive Git-config independence (F-003 limit), physical-origin attestation (F-004, G2), Level-3 runtime
validity, trusted time, revocation, dataset/model validity, or capture authorisation. **This is not Level
3.** Real hospital footage & trajectory collection remains blocked.

**Recommendation:** a focused independent **G1R re-review** — proving (a) the trusted factory cannot be
induced to honour a caller-supplied resolution; (b) the canonical-manifest controls are not test-specific
and admit a legitimate clean resolution; (c) the Git-config pinning is behavioural, not merely declared;
(d) the F-001/F-004 residuals are honestly bounded — before opening **G2** (cryptographic report signing,
revocation, trusted timestamps, physical-origin attestation).
