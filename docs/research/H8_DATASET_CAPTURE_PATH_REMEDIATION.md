# H8 Dataset Capture-Path — Review-Finding Remediation & Hardening Gate

**Scope:** narrow remediation of the independent-review findings `H8-REV-F-001`, `H8-REV-F-002`, and the
open Ruff limitation `H8-C-006`. No evidence-provider, backend, Isaac, or dataset-capture development.
The five committed Level-1 evidence files were **not** altered or regenerated; no implementation `.py`
(non-test) file was changed. This report **appends** dispositions; the original review findings in
[`H8_DATASET_CAPTURE_PATH_INDEPENDENT_REVIEW.md`](H8_DATASET_CAPTURE_PATH_INDEPENDENT_REVIEW.md) are
preserved.

- **Date:** 2026-07-16 · **Branch:** `h23-execfix` (local, unpushed) · **Baseline HEAD:** `c6b42ac`.
- **Reviewed chain (Git-resolved):** `7a73c9fc012b97ee1bf94fe829a3c59eb915ff9f` →
  `ecae4cdd5de4082184fc65881cc836c612231bf8` → `66fd81e62bc0d6c100e7b562b22fc8cc8a0d061e` →
  `bd6168ab5ead2aa5724a6d9df1b7e52222fbf0b7` → `db70ce39c0d99300ec4f4d2c0010f6cbe036cade` →
  `bb94c5aabe6d96bbe8e4be4ce6f3d7a0a37af4ce` → `c6b42ac14eb52f80e3b0a3521d3eb3a826ac1627`.

## Remediation decision table

| Finding | Class | Corrective action | Files | Acceptance test | Final status |
| --- | --- | --- | --- | --- | --- |
| H8-REV-F-001 | A + B | Declare asymmetry intentional (`H8-DCP-014`) + 2 regression tests; no 26th check (would break byte-identical 25/25 evidence) | decision log, this report, review report, recorded-mode test | `test_capture_validator_never_weaker_than_dry_run`, `test_stray_rollout_key_is_capture_specific_H8_REV_F_001` | **MITIGATED WITH DOCUMENTED LIMITATION** |
| H8-REV-F-002 | A | Clarify `H8-DCP-002` + gate-record summary: capture validator is a strict superset | decision log, gate record, review report | (documented; superset also exercised by the F-001 test) | **CLOSED** |
| H8-C-006 (Ruff) | D (env) | Keep Open; document config + canonical command (`H8-DCP-016`); no install | failure register, decision log, this report | n/a | **OPEN — RUFF UNAVAILABLE** |
| H8-REV-F-003 (new) | D (deferred) | Record empty-plan `IndexError`; verify contained at both boundaries; defer graceful guard | this report, review report | boundary check (CLI rc=2; validator ok=False) | **OPEN — DEFERRED** |

## Per-finding detail

### H8-REV-F-001 — dry-run/capture parity asymmetry (stray rollout-metric key)

| Field | Content |
| --- | --- |
| Original severity | Low (fail-safe direction; committed evidence unaffected) |
| Reproduction | `cfg["SR"]=0.9` → `dataset_dry_run_checks(cfg)["all_pass"] is True`; `validate_dataset_capture_config(cfg)[0] is False`. Asymmetry confirmed. |
| Confirmed root cause | The 25 dry-run checks are plan-invariants and include no stray-rollout-metric-key scan; the capture validator adds one via `_all_config_keys` × `FORBIDDEN_METRIC_KEYS`. |
| Remediation class | A (documentation) + B (test-hardening) |
| Corrective action | `H8-DCP-014` declares the asymmetry intentional (capture = enforcing strict superset). No 26th numbered check — that would change the committed `checks_passed: 25/25` and regenerate the five evidence files, disallowed by the evidence-preservation rule. |
| Tests added | `test_capture_validator_never_weaker_than_dry_run` (locks the safe direction across 11 invalid mutations); `test_stray_rollout_key_is_capture_specific_H8_REV_F_001` (pins the intentional asymmetry). `test_G` already locks capture-side rejection. |
| Verification | Both new tests pass; full relevant suite 85 passed. |
| Residual limitation | The dry-run diagnostic alone still does not flag a stray rollout key; the enforcing capture gate does. |
| Final status | **MITIGATED WITH DOCUMENTED LIMITATION** |
| Future owner | Optional: fold the scan into the dry-run as a hard precondition (evidence-preserving) in a future hardening gate. |

### H8-REV-F-002 — "single source of plan validity" wording

| Field | Content |
| --- | --- |
| Original severity | Low / informational |
| Reproduction | Wording inspection: `H8-DCP-002` title implied identical validity; implementation is a superset. |
| Confirmed root cause | Documentation imprecision (not a code defect). |
| Remediation class | A (documentation) |
| Corrective action | `H8-DCP-002` gains a clarification row; `H8_DATASET_CAPTURE_PATH_GATE.md` implementation summary now says "strict superset … never more permissive than the dry-run". |
| Tests added | None required (documentation); the superset relationship is exercised by the F-001 tests. |
| Verification | Wording now matches implementation. |
| Residual limitation | None. |
| Final status | **CLOSED** |

### H8-C-006 — Ruff lint verification

| Field | Content |
| --- | --- |
| Re-check | `pyproject.toml` declares `[tool.ruff]` (`line-length=100`, `select=["E","F","I","W"]`, `ignore=["E501"]`) and dev-dep `ruff>=0.4`; `python -m ruff` is absent in base and `.venv`; `Makefile` has no lint target. |
| Action | No uncontrolled install (narrow-gate rule). `py_compile` passed (recorded separately, **not** a lint substitute). |
| Final status | **OPEN — RUFF UNAVAILABLE** |
| Future owner | Canonical `pip install -e '.[dev]'` env must run `ruff check` before capture promotion (`H8-DCP-016`). |

### H8-REV-F-003 — empty-plan direct-call `IndexError` (new, discovered during remediation)

| Field | Content |
| --- | --- |
| Discovery | While writing the F-001 parity test: `dataset_dry_run_checks(cfg)` raised `IndexError` on a `no_instance_plan` mutation. |
| Reproduction | Config with `instance_plan` removed → empty plan → `dataset_injected_leakage_cases([])` → `_cross_split_pair([])` → `recs[0]` `IndexError`. |
| Boundary safety (verified) | **Fails closed at both real boundaries:** CLI `dataset-dry-run` returns `2` (`{"dataset_dry_run": false, "error": "list index out of range"}`, no files written); `validate_dataset_capture_config` catches it → `ok=False` with an "instance" issue. Not a safety hole. |
| Severity | Low (robustness only; never reached via a well-formed config; both boundaries reject). |
| Corrective action this gate | Test made boundary-accurate (`_dry_run_rejects` treats a raise as rejection). Implementation **not** changed (out of the authorized F-001/F-002/C-006 scope). |
| Recommended future mitigation | Graceful empty-plan guard so a direct `dataset_dry_run_checks` call returns `all_pass=False` instead of raising. |
| Final status | **OPEN — DEFERRED** (owner = future hardening/evidence-schema gate) |

## Preserved invariants (verified this gate)

- **Level-1 evidence unchanged:** the five files in
  `assets/experiments/hospital_h8_track_b_synthetic_fork_recorded_mode_dataset_dryrun/` are byte-identical
  (`git diff --quiet` clean; SHA-256 unchanged). No implementation change could affect them (none made).
- **Pilot preservation:** no implementation file changed; the full pilot suite remains green.
- **Execution boundary:** no Isaac import, no capture, no inference, no dataset directory; the dataset
  route without an injected backend still returns code 3 and creates nothing.
- **Stale claim boundary (`H8-DCP-015`):** rejection is marker-based only; no timestamp/age/expiry/clock/
  revocation semantics are claimed (`test_stale_marker_rejection_does_not_claim_runtime_expiry_semantics`).

## Verdicts

- **H8-REV-F-001:** `MITIGATED WITH DOCUMENTED LIMITATION`.
- **H8-REV-F-002:** `CLOSED`.
- **Ruff / H8-C-006:** `OPEN — RUFF UNAVAILABLE`.
- **H8-REV-F-003 (new):** `OPEN — DEFERRED` (contained; fail-closed at both boundaries).
- **Overall remediation gate:** `PASS WITH DOCUMENTED LIMITATIONS` — no unresolved finding permits unsafe
  progression; real capture remains blocked; deferred items (`H8-C-006`, `H8-REV-F-003`, and the real
  evidence-schema/provider/backend) have explicit future owners; no overclaim introduced.

## Boundary statement

Levels 1 (plan validity) and 2 (capture-path validity) remain as independently reviewed. **Runtime
(Level 3), dataset (Level 4), and model (Level 5) validity remain unproven.** **Real dataset capture
remains blocked.** No Isaac launch, real capture, rendering, robot driving, policy/model inference,
action probe, training, checkpoint creation, 20/5/10, closed-loop evaluation, push, tag, promotion, or
publication occurred during this gate.

## Next authorised gate

Design the **real render/drive-valid evidence schema** (instance identity, scene identity, freshness,
revocation, integrity, provenance) — **before** any evidence-provider or backend work — then an
independent schema/provider review, then a separately reviewed backend/runtime-validity gate, then
explicit capture authorisation. The optional graceful empty-plan guard (`H8-REV-F-003`) and canonical
Ruff run (`H8-C-006`) may be folded into that hardening.
