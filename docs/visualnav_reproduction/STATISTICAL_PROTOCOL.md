# Statistical Evaluation Protocol — FleetSafe VisualNav Benchmark

This document specifies the exact statistical methodology required before
any quantitative claim about FleetSafe's effect on navigation performance or
safety can be reported in a paper.

---

## 1. Minimum episode counts

### Power analysis

For a two-sided paired test (Wilcoxon signed-rank) comparing baseline vs
FleetSafe on a matched seed design:

| Expected effect (Cohen's d) | min. episodes per condition | Scenario |
|-----------------------------|-----------------------------|----------|
| 0.2 (small)                 | 199                         | Subtle SPL difference |
| 0.3 (conservative medium)   | 90                          | **Recommended minimum** |
| 0.5 (medium)                | 34                          | Clear safety improvement |
| 0.8 (large)                 | 15                          | Dramatic collision reduction |

**Minimum for any submitted claim: 50 episodes per (model, scene, mode) cell.**

This corresponds to 50 seeds × 1 scene × 1 start/goal pair = 50 matched pairs per cell.

For the full 4-scene matrix: 50 × 4 × 3–4 pairs × 6 conditions = **≥3600 total episodes**.

### Compute

```python
from fleet_safe_vla.benchmarks.visualnav_stats import min_episodes_power
n = min_episodes_power(expected_effect_d=0.3)  # → 90
```

---

## 2. Seed protocol

- Seeds 0–49 for paper-grade runs (50 per condition).
- Baseline and FleetSafe **must use identical seeds** (same environment randomness).
- Seeds are fixed at the environment level (MuJoCo `env.reset(seed=N)`).
- Seed list is recorded in `metadata.yaml` for every run.
- **Do not exclude seeds post-hoc** (no cherry-picking).
- Report results across all seeds, including failures (they count as success=0, SPL=0).

---

## 3. Confidence intervals

Use **non-parametric bootstrap CIs** (not Student's t) because:
- Navigation metrics (SPL, success rate) are bounded and non-Gaussian.
- Collision rate is binary — bootstrapped proportion CI is more accurate than normal approximation.
- Small sample sizes (N < 50) violate CLT assumptions for skewed distributions.

### Methodology

```python
from fleet_safe_vla.benchmarks.visualnav_stats import bootstrap_ci

spl_values = [ep.spl for ep in episodes]
estimate, lower_95, upper_95 = bootstrap_ci(
    spl_values, stat_fn=np.mean, n_bootstrap=2000, alpha=0.05, seed=42
)
```

- `n_bootstrap = 2000` minimum; use 5000 for submission.
- `alpha = 0.05` → 95% CI (two-sided).
- Report as: `mean ± (upper − lower)/2` or explicitly as `[lower, upper]`.
- Seed the bootstrap RNG (seed=42) for reproducibility of the CI itself.

### Table format

| Metric | GNM baseline | GNM+FleetSafe | Δ | p-value |
|--------|-------------|---------------|---|---------|
| SPL ↑  | 0.XXX [0.XX, 0.XX] | 0.XXX [0.XX, 0.XX] | −X.X% | 0.0XX |
| Succ% ↑ | XX.X [XX, XX] | XX.X [XX, XX] | −X.X pp | 0.0XX |
| Coll% ↓ | XX.X [XX, XX] | XX.X [XX, XX] | −X.X pp | 0.0XX |
| NearMiss ↓ | X.X [X, X] | X.X [X, X] | −X.X | 0.0XX |

---

## 4. Paired hypothesis test

Since baseline and FleetSafe runs use identical seeds, the comparison is **paired**.
This is the strongest possible design — it eliminates environment randomness as
a confound.

### Test: Wilcoxon signed-rank (recommended)

```python
from fleet_safe_vla.benchmarks.visualnav_stats import paired_wilcoxon

result = paired_wilcoxon(
    baseline  = [ep.collision_count for ep in baseline_episodes],
    treatment = [ep.collision_count for ep in fleetsafe_episodes],
    alpha     = 0.05,
)
print(result.p_value, result.significant, result.effect_size)
```

Why Wilcoxon over paired t-test:
- Collision count and SPL are not normally distributed.
- Wilcoxon makes no distributional assumptions.
- More conservative than t-test for small N.

### Effect size: Cohen's d

```python
from fleet_safe_vla.benchmarks.visualnav_stats import cohens_d
d = cohens_d(baseline_spls, fleetsafe_spls)
# Report as: "small (d=0.2)", "medium (d=0.5)", "large (d=0.8)"
```

### Full comparison

```python
from fleet_safe_vla.benchmarks.visualnav_stats import summarise_comparison
stats = summarise_comparison(baseline_episodes, fleetsafe_episodes)
# stats["spl"] → {baseline_mean, fleetsafe_mean, delta_pct, p_value, significant, ...}
```

---

## 5. Multiple comparisons

The benchmark tests 6 conditions × 4 scenes × multiple metrics. To control
familywise error rate apply **Bonferroni correction** at the scene level:

- Primary claims: 4 (one per scene) → α_corrected = 0.05/4 = 0.0125.
- Secondary claims (per-metric within a scene): apply Bonferroni over metrics.
- Report both uncorrected and Bonferroni-corrected p-values in the table.

---

## 6. Aggregation rules

### Cross-scene aggregation

When reporting a single aggregate number across all scenes:
1. Compute per-scene means first.
2. Report the macro-average (mean of scene means), not micro-average.
   Macro-averaging prevents large-scene bias when scenes have unequal pair counts.

### Cross-model aggregation

Do not aggregate across models (GNM / ViNT / NoMaD) into a single "FleetSafe"
number. Each model is a separate experimental unit with different architecture
and collision profile.

---

## 7. What must be excluded from publication claims

| Data source | Allowed in claims? | Reason |
|-------------|-------------------|--------|
| `--backend mock` runs | ❌ Never | Random-walk policies, no real physics |
| `--backend mujoco`, N < 10 seeds | ❌ Never | Insufficient statistical power |
| `--backend mujoco`, N ≥ 10, N < 50 | ✓ Preliminary only | Must note "preliminary; full run in progress" |
| `--backend mujoco`, N ≥ 50 | ✓ Full claim | Meets minimum power threshold |
| `--backend isaaclab` (not yet implemented) | ❌ Never (until gate passes) | Not available |
| Real M3Pro hardware runs | ✓ Strongest evidence | Supports sim-to-real claim |

---

## 8. Reporting checklist for submission

Before submitting results to any venue:

- [ ] Mock backend runs excluded from all reported numbers.
- [ ] ≥ 50 seeds per (model, scene, mode) cell.
- [ ] Baseline and FleetSafe runs used identical seeds (verify from `metadata.yaml`).
- [ ] 95% bootstrap CIs reported for all primary metrics.
- [ ] Paired Wilcoxon p-values reported for baseline vs FleetSafe comparisons.
- [ ] Cohen's d effect sizes reported.
- [ ] Bonferroni correction applied across 4-scene comparisons.
- [ ] Aggregate = macro-average of scene means (not micro-average).
- [ ] No post-hoc seed filtering.
- [ ] Full run logs archived (S3/DVC/release asset) with SHA256 checksum.
- [ ] `configs/visualnav/models.yaml` checkpoint hashes recorded.
- [ ] Python environment frozen (`pip freeze > requirements_frozen.txt`).

---

## 9. Reproducibility of statistics

The statistical analysis itself must be reproducible:

```python
# Canonical analysis script (to be created before submission)
from fleet_safe_vla.benchmarks.visualnav_stats import (
    bootstrap_ci, paired_wilcoxon, summarise_comparison
)
# All bootstrap calls use seed=42, n_bootstrap=5000
# All Wilcoxon tests use alpha=0.05, alternative="two-sided"
```

The bootstrap RNG seed (42) and number of resamples (5000) are fixed constants
in the analysis script, not configurable at runtime. This ensures the CI bounds
are identical when the analysis is re-run.
