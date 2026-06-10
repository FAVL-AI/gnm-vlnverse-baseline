# Versioning Policy

## Version constants

All version constants are defined in `fleet_safe_vla/benchmark_version.py`:

```python
BENCHMARK_VERSION      = "0.1.0"   # umbrella — bump when any component changes
PROTOCOL_VERSION       = "0.1.0"   # episode params, models, modes, backends
SCENESET_VERSION       = "0.1.0"   # canonical scene definitions
METRICSET_VERSION      = "0.1.0"   # metric formulas and statistical protocol
EXPLAINABILITY_VERSION = "0.1.0"   # scene graph, causal, counterfactual schema
GOVERNANCE_VERSION     = "0.1.0"   # governance rules
```

---

## Version embedding

Every benchmark artifact embeds all six version constants:

### `metadata.yaml` (run level)

```yaml
benchmark_version: "0.1.0"
protocol_version: "0.1.0"
sceneset_version: "0.1.0"
metricset_version: "0.1.0"
explainability_version: "0.1.0"
governance_version: "0.1.0"
git_commit: "abc1234"
protocol_file: "benchmarks/protocols/visualnav_v0.1.yaml"
scene_manifest_file: "benchmarks/scenes/canonical/SCENESET_v0.1.yaml"
metric_spec_file: "docs/metrics/METRIC_SPECIFICATION.md"
```

### `aggregate_metrics.json` (run level)

The `extra` block includes the same fields.

### `metrics.json` (episode level)

Each episode metrics file includes `benchmark_version` and `protocol_version`.

---

## Versioning semantics

We follow [Semantic Versioning 2.0.0](https://semver.org/):

```
MAJOR.MINOR.PATCH

MAJOR: incompatible change — results from prior version not comparable
MINOR: backward-compatible addition — new metric, scene, or model
PATCH: bug fix that does not change metric values on existing data
```

---

## Protocol files

Protocol files are named `visualnav_v{MAJOR}.{MINOR}.yaml`.

- `visualnav_v0.1.yaml` — initial release
- `visualnav_v0.2.yaml` — would be a backward-compatible addition
- `visualnav_v1.0.yaml` — would indicate a breaking change

**Protocol files are never modified after publication.** A new version creates
a new file. The old file remains in the repository for reproducibility.

---

## Scene manifests

Scene manifests are named `SCENESET_v{MAJOR}.{MINOR}.yaml`.

Scene hash fields (`hash: "placeholder_..."`) must be replaced with actual
SHA256 hashes of the canonical scene configuration before the first paper
submission that uses that scene version.

---

## Version comparison matrix

Results are comparable only when:

| Field | Must match |
|---|---|
| `benchmark_version` | Same MAJOR.MINOR |
| `protocol_version` | Same MAJOR.MINOR |
| `sceneset_version` | Same MAJOR.MINOR |
| `metricset_version` | Same MAJOR.MINOR |
| `backend` | Same backend |

Results from different `model` values on the same version are directly comparable
(that is the point of the benchmark).

---

## How to perform a version bump

1. Determine the impact: MAJOR, MINOR, or PATCH.
2. Update `fleet_safe_vla/benchmark_version.py`.
3. Create the new protocol/scene YAML with the new version number.
4. Add a `CHANGELOG.md` entry.
5. Commit with message: `chore(version): bump {component} to {new_version}`.
6. Tag the commit: `git tag v{BENCHMARK_VERSION}`.

The `BENCHMARK_VERSION` umbrella is always set to the highest component version
(e.g., if `METRICSET_VERSION` bumps from 0.1.0 to 0.2.0, `BENCHMARK_VERSION`
becomes 0.2.0).
