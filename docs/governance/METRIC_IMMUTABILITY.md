# Metric Immutability Policy

## Principle

Once a metric is published in a paper claim:

1. Its formula is frozen for that `metricset_version`.
2. Its directionality (higher/lower better) is frozen.
3. Its confidence interval method is frozen.
4. Any change to the above requires a new `metricset_version`.

A metric added *after* a publication that only appears in newer runs is not
retroactively applied to old runs.

---

## Metric change categories

### Allowed without version bump

- Fixing a bug in the metric implementation that caused wrong values on
  test data (PATCH). All affected results must be marked stale and
  re-computed before use in any publication claim.
- Adding a new metric that does not affect any existing metric.

### Requires MINOR version bump

- Adding a new metric to the standard metric set.
- Changing the default confidence interval width (alpha).
- Changing the bootstrap iteration count.

### Requires MAJOR version bump

- Changing the formula for any existing metric (SPL, collision rate, etc.).
- Changing the directionality of any metric.
- Removing a metric from the standard set.
- Changing the statistical test used for significance testing.

---

## Frozen metric formulas (v0.1)

These formulas are frozen at METRICSET_VERSION 0.1.0 and must not change without
a version bump.

### SPL (Success weighted by Path Length)

```
SPL = (1/N) Σ_i  success_i × (optimal_path_i / max(path_length_i, optimal_path_i))
```

- `success_i` ∈ {0, 1}
- `optimal_path_i` = Euclidean start→goal distance
- `path_length_i` = actual trajectory length

### Collision rate

```
collision_rate = collision_episodes / total_episodes
```

An episode is a collision episode if `collision_count > 0`.

### Intervention rate

```
intervention_rate = intervention_steps / total_steps
```

Per episode, then averaged across episodes.

### Near-violation count

```
near_violation_count = Σ_t  [min_dist_m_t < near_violation_threshold_m]
```

Per episode. Threshold is 0.45 m (v0.1).

### Action delta L2

```
delta_l2 = ‖safe_cmd - raw_cmd‖₂
```

Per step. Reported as mean over all steps in episode, then mean over episodes.

---

## Immutability audit

The metric spec file is `docs/metrics/METRIC_SPECIFICATION.md`.
Every run records:

```yaml
metric_spec_file: "docs/metrics/METRIC_SPECIFICATION.md"
metricset_version: "0.1.0"
```

If the metric spec file changes, `metricset_version` must be bumped before
the next run. Runs from an earlier metricset_version must not be directly
compared to runs from a newer metricset_version in publication tables without
an explicit version annotation.

---

## Stale result policy

A result is stale if:

1. A PATCH-level metric bug was fixed after the result was produced, OR
2. The `metricset_version` in the result artifact differs from the current version.

Stale results must be re-computed or explicitly labelled `(stale, v{version})`
in any presentation.
