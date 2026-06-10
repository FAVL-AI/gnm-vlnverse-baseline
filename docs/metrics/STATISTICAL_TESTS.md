# Statistical Tests — FleetSafe VisualNav Benchmark v0.1

---

## Test selection rationale

Navigation metrics (success rate, SPL, collision rate) are not normally distributed:
- `success_rate` and `collision_rate` are binary proportions.
- `spl_mean` is bounded [0, 1] with a spike at 0.

The paired Wilcoxon signed-rank test is used because:
1. Non-parametric: makes no distributional assumption.
2. Paired: each (seed × scene × start_goal_pair) is compared within a pair,
   controlling for scene-level and seed-level variance.
3. Directional: tests the hypothesis H₁: FleetSafe > baseline (or < for safety).

---

## Primary comparison procedure

For each (model, scene) combination:

1. Collect paired observations: `(baseline_value_i, fleetsafe_value_i)` for i = 1..50.
2. Apply **paired Wilcoxon signed-rank test** (two-sided; then one-sided if significant).
3. Apply **Bonferroni correction** over the number of primary endpoint comparisons.
4. Report: W statistic, p-value, corrected p-value, significance at α=0.05.

Implementation: `fleet_safe_vla.benchmarks.visualnav_stats.paired_wilcoxon`

---

## Bootstrap confidence intervals

For all reported metrics:

1. Resample with replacement (10 000 iterations).
2. Compute the statistic on each resample.
3. Report the 2.5th–97.5th percentile range as the 95% CI.
4. CIs are reported as `[lower, upper]`.

Implementation: `fleet_safe_vla.benchmarks.visualnav_stats.bootstrap_ci`

---

## Effect size (Cohen's d)

For continuous metrics (SPL, delta_l2, latency):

```
d = (mean_A - mean_B) / pooled_std
pooled_std = sqrt((std_A² + std_B²) / 2)
```

Interpretation:
- |d| < 0.2: negligible
- |d| ∈ [0.2, 0.5): small
- |d| ∈ [0.5, 0.8): medium
- |d| ≥ 0.8: large

Only effects with |d| ≥ 0.2 are reported as substantive.
Effects with |d| < 0.2 are reported as "negligible" even if statistically significant.

Implementation: `fleet_safe_vla.benchmarks.visualnav_stats.cohens_d`

---

## Power analysis

Minimum sample size for α=0.05, power=0.80 is estimated at:

- Small effect (d=0.2): ~198 episodes per condition
- Medium effect (d=0.5): ~32 episodes per condition
- Large effect (d=0.8): ~14 episodes per condition

With 50 seeds × 4 scenes = 200 observations per condition, the benchmark is
adequately powered for medium and large effects. Small effects require the full
200 episodes and may not be reliably detected with scene-level subsets.

Implementation: `fleet_safe_vla.benchmarks.visualnav_stats.min_episodes_for_power`

---

## Multiple comparisons

Primary comparisons (Bonferroni family):
- 3 models × 2 primary metrics = 6 comparisons
- Corrected α = 0.05 / 6 ≈ 0.0083

Secondary comparisons (not Bonferroni-corrected; descriptive only):
- Scene-level breakdowns
- Latency comparisons
- Explainability metric comparisons

---

## Reporting template

For a primary endpoint:

```
Metric: collision_rate
Model:  GNM
Comparison: baseline vs fleetsafe (mujoco, n=200 episodes, 50 seeds × 4 scenes)

baseline:  0.18 [0.13, 0.24] (95% bootstrap CI)
fleetsafe: 0.04 [0.01, 0.08]

Wilcoxon W=3420, p=0.0001, corrected p=0.0006 (< 0.0083)
Cohen's d = -0.81 (large; fleetsafe lower collision rate)

Conclusion: FleetSafe significantly reduces collision rate for GNM
            (large effect, Bonferroni-corrected p < 0.0083).
```

---

## `summarise_comparison` output fields

The `visualnav_stats.summarise_comparison` function returns:

```python
{
    "metric":           "collision_rate",
    "n_pairs":          200,
    "mean_a":           0.18,
    "mean_b":           0.04,
    "ci_a":             [0.13, 0.24],
    "ci_b":             [0.01, 0.08],
    "wilcoxon_stat":    3420.0,
    "p_value":          0.0001,
    "significant":      True,
    "direction":        "improved",   # or "degraded" or "no_change"
    "effect_size":      -0.81,
    "effect_magnitude": "large",
}
```
