# Benchmark Governance

## Scope

This document defines the governance framework for FleetSafe-VisualNav-Benchmark.
Every process that produces, modifies, or publishes benchmark results is subject
to this framework.

---

## Core principle

> **FleetSafe benchmark results are append-only, versioned, reproducible scientific
> artifacts. Nothing published is silently changed retroactively.**

Any result that appears in a paper, preprint, or public report must be traceable
to a frozen artifact. Any change to protocol, scenes, or metrics requires a new
version number, not a silent update.

---

## Governance body

This benchmark is maintained by FAVL-AI. The current maintainer is the
repository owner. Governance decisions are recorded in this document and in
the git history of this repository.

---

## What governance covers

| Component | Governed by |
|---|---|
| Protocol (models, modes, episode params) | `benchmarks/protocols/visualnav_v*.yaml` |
| Canonical scenes | `benchmarks/scenes/canonical/SCENESET_v*.yaml` |
| Metric definitions | `docs/metrics/METRIC_SPECIFICATION.md` |
| Statistical tests | `docs/metrics/STATISTICAL_TESTS.md` |
| Transparency contract | `fleet_safe_vla/explainability/transparency_contract.py` |
| Version constants | `fleet_safe_vla/benchmark_version.py` |
| Frozen artifacts | `benchmarks/frozen/<version>/<run_id>/` |

---

## Change management

### Non-breaking changes (no version bump required)

- Bug fixes that do not change metric values on existing data
- Addition of new documentation
- Clarification of existing rules without changing their semantics

### Minor version bump (x.Y.0)

- Addition of a new metric that does not affect existing metrics
- Addition of a new scene that does not change existing scene results
- Addition of a new model that does not affect other model comparisons

### Major version bump (X.0.0)

- Any change to metric formula, units, or directionality
- Any change to canonical scene geometry or obstacle placement
- Any change to episode parameters (max_steps, control_hz, thresholds)
- Any change to statistical protocol
- Removal of any existing metric, scene, or model

### Versioning rules

- Version bumps are applied atomically: all six version constants are updated in
  `fleet_safe_vla/benchmark_version.py`.
- A `CHANGELOG.md` entry must accompany any version bump.
- Results from version X are not directly comparable to results from version Y.
  If a cross-version comparison is presented, it must be explicitly labelled.

---

## Publication claims

See [`CLAIMS_AND_LIMITATIONS.md`](CLAIMS_AND_LIMITATIONS.md) for the full rules.
Summary:

1. Only claims backed by a frozen artifact (`benchmarks/frozen/`) are accepted.
2. Mock backend results must never appear in publication tables.
3. Minimum 50 seeds per condition.
4. All claims must pass `validate_transparency_artifacts()`.
5. A claim not traceable to `audit_trail.json → transparency_status: PASS` is invalid.

---

## Audit trail

Every run produces:
- `metadata.yaml` — run parameters + version fields + git commit
- `audit_trail.json` per episode — model, backend, transparency status
- `aggregate_metrics.json` — summary + version fields

Every frozen artifact contains:
- `SHA256SUMS` — cryptographic hashes of all files
- `MANIFEST.json` — structured file list + metadata
- `GIT_STATE.txt` — `git log` and `git status` at freeze time
- `ENVIRONMENT.txt` — Python version, package list, OS

---

## Immutability

Once a run is frozen:
- The frozen directory is never overwritten without `--force`.
- The `--force` flag requires explicit justification (documented in the commit message).
- Frozen results from a prior version of the protocol are labelled with the protocol
  version that produced them and are not retroactively re-evaluated.

---

## Contact and issue reporting

Open an issue at https://github.com/FAVL-AI/FleetSafe-VisualNav-Benchmark/issues.
