"""
visualnav_stats.py — Statistical analysis utilities for the FleetSafe VisualNav benchmark.

All functions are pure (no simulator, no filesystem): inputs are numbers / lists,
outputs are numbers / dicts.

Key functions
-------------
bootstrap_ci         : Non-parametric bootstrap confidence interval.
paired_wilcoxon      : Paired Wilcoxon signed-rank test (baseline vs FleetSafe).
cohens_d             : Cohen's d effect size for two independent samples.
min_episodes_power   : Minimum episodes per condition for given power.
summarise_comparison : Full statistical comparison of two episode metric lists.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np


# ── Bootstrap CI ──────────────────────────────────────────────────────────────

def bootstrap_ci(
    values:     Sequence[float],
    stat_fn:    Callable[[np.ndarray], float] = np.mean,
    n_bootstrap: int  = 2000,
    alpha:       float = 0.05,
    seed:        int | None = None,
) -> tuple[float, float, float]:
    """
    Non-parametric bootstrap confidence interval.

    Parameters
    ----------
    values      : Observed sample.
    stat_fn     : Statistic to estimate (default: mean).
    n_bootstrap : Number of bootstrap resamples.
    alpha       : Two-sided significance level (default 0.05 → 95% CI).
    seed        : RNG seed for reproducibility.

    Returns
    -------
    (estimate, lower, upper)
        estimate — stat_fn applied to the original sample.
        lower    — (alpha/2) percentile of bootstrap distribution.
        upper    — (1 - alpha/2) percentile of bootstrap distribution.
    """
    arr = np.asarray(values, dtype=float)
    if len(arr) == 0:
        return float("nan"), float("nan"), float("nan")

    rng  = np.random.default_rng(seed)
    estimate = float(stat_fn(arr))

    boot_stats = np.empty(n_bootstrap)
    for i in range(n_bootstrap):
        sample      = rng.choice(arr, size=len(arr), replace=True)
        boot_stats[i] = stat_fn(sample)

    lower = float(np.percentile(boot_stats, 100 * alpha / 2))
    upper = float(np.percentile(boot_stats, 100 * (1 - alpha / 2)))
    return estimate, lower, upper


# ── Paired test ───────────────────────────────────────────────────────────────

@dataclass
class PairedTestResult:
    statistic:   float
    p_value:     float
    significant: bool
    effect_size: float          # Cohen's d
    n_pairs:     int
    direction:   str            # "improved", "degraded", "no_change"
    method:      str            # "wilcoxon" | "t_test_paired"


def paired_wilcoxon(
    baseline:   Sequence[float],
    treatment:  Sequence[float],
    alpha:      float = 0.05,
    alternative: str  = "two-sided",
) -> PairedTestResult:
    """
    Paired Wilcoxon signed-rank test for baseline vs FleetSafe comparison.

    Use when metrics are measured on matched pairs (same seed, same scene,
    same start/goal — only safety layer differs).

    Parameters
    ----------
    baseline   : Metric values for baseline condition (no FleetSafe).
    treatment  : Metric values for treatment condition (FleetSafe enabled).
                 Must be same length as baseline, matched by (seed, scene, pair).
    alpha      : Significance threshold.
    alternative: "two-sided" | "greater" | "less".

    Returns
    -------
    PairedTestResult with statistic, p-value, significance, effect size.
    """
    try:
        from scipy.stats import wilcoxon
    except ImportError:
        return _paired_fallback(baseline, treatment, alpha)

    base_arr = np.asarray(baseline, dtype=float)
    trt_arr  = np.asarray(treatment, dtype=float)

    if len(base_arr) != len(trt_arr):
        raise ValueError("baseline and treatment must have equal length for paired test")
    if len(base_arr) < 5:
        return _paired_fallback(baseline, treatment, alpha)

    diff = trt_arr - base_arr
    # Skip zero differences (Wilcoxon requirement)
    nonzero = diff[diff != 0]
    if len(nonzero) < 5:
        return _paired_fallback(baseline, treatment, alpha)

    stat, p = wilcoxon(nonzero, alternative=alternative)
    d        = cohens_d(base_arr, trt_arr)
    mean_diff = float(np.mean(diff))

    return PairedTestResult(
        statistic   = float(stat),
        p_value     = float(p),
        significant = p < alpha,
        effect_size = d,
        n_pairs     = len(base_arr),
        direction   = "improved" if mean_diff > 0 else ("degraded" if mean_diff < 0 else "no_change"),
        method      = "wilcoxon",
    )


def _paired_fallback(
    baseline:  Sequence[float],
    treatment: Sequence[float],
    alpha:     float,
) -> PairedTestResult:
    """Fallback when scipy is unavailable or sample too small: sign test."""
    base_arr = np.asarray(baseline, dtype=float)
    trt_arr  = np.asarray(treatment, dtype=float)
    diff     = trt_arr - base_arr
    n        = len(diff)
    mean_diff = float(np.mean(diff)) if n > 0 else 0.0
    return PairedTestResult(
        statistic   = float(np.sum(diff > 0)),
        p_value     = float("nan"),
        significant = False,
        effect_size = cohens_d(base_arr, trt_arr) if n >= 2 else 0.0,
        n_pairs     = n,
        direction   = "improved" if mean_diff > 0 else ("degraded" if mean_diff < 0 else "no_change"),
        method      = "sign_test_fallback",
    )


# ── Effect size ───────────────────────────────────────────────────────────────

def cohens_d(a: Sequence[float], b: Sequence[float]) -> float:
    """
    Cohen's d effect size for two samples (pooled standard deviation).

    Interpretation: 0.2 = small, 0.5 = medium, 0.8 = large.
    Returns 0.0 if pooled std is zero (identical samples).
    """
    a_arr = np.asarray(a, dtype=float)
    b_arr = np.asarray(b, dtype=float)
    if len(a_arr) < 2 or len(b_arr) < 2:
        return 0.0
    pooled_std = float(np.sqrt(
        (np.var(a_arr, ddof=1) * (len(a_arr) - 1) +
         np.var(b_arr, ddof=1) * (len(b_arr) - 1))
        / (len(a_arr) + len(b_arr) - 2)
    ))
    if pooled_std == 0.0:
        return 0.0
    return float((np.mean(a_arr) - np.mean(b_arr)) / pooled_std)


# ── Power / minimum sample size ───────────────────────────────────────────────

def min_episodes_power(
    expected_effect_d: float = 0.5,
    alpha:             float = 0.05,
    power:             float = 0.80,
) -> int:
    """
    Approximate minimum episodes per condition for a paired t-test.

    Uses the analytical formula for two-sided paired t-test power.
    Returns a conservative integer.

    Parameters
    ----------
    expected_effect_d : Expected Cohen's d (0.2 small, 0.5 medium, 0.8 large).
    alpha             : Type I error rate.
    power             : Desired statistical power (1 - β).

    Notes
    -----
    For SPL differences between FleetSafe and baseline, a medium effect (d=0.5)
    is a conservative assumption. Use d=0.3 for a more conservative estimate.
    """
    try:
        from scipy.stats import norm
        z_alpha = norm.ppf(1 - alpha / 2)
        z_beta  = norm.ppf(power)
        n = ((z_alpha + z_beta) / expected_effect_d) ** 2
        return max(10, int(np.ceil(n)))
    except ImportError:
        # Fallback: hard-coded common values
        _table = {
            (0.2, 0.05, 0.80): 199,
            (0.3, 0.05, 0.80):  90,
            (0.5, 0.05, 0.80):  34,
            (0.8, 0.05, 0.80):  15,
        }
        key = (round(expected_effect_d, 1), round(alpha, 2), round(power, 2))
        return _table.get(key, 50)


# ── Full comparison summary ───────────────────────────────────────────────────

def summarise_comparison(
    baseline_metrics:  list,
    fleetsafe_metrics: list,
    alpha:             float = 0.05,
    n_bootstrap:       int   = 2000,
    seed:              int   = 42,
) -> dict:
    """
    Full statistical comparison of baseline vs FleetSafe episode metrics.

    Parameters
    ----------
    baseline_metrics  : list[EpisodeMetrics] for baseline condition.
    fleetsafe_metrics : list[EpisodeMetrics] for FleetSafe condition.
    alpha             : Significance threshold for hypothesis tests.
    n_bootstrap       : Bootstrap resamples for CIs.
    seed              : RNG seed.

    Returns
    -------
    dict with per-metric comparisons:
      {metric_name: {
        "baseline_mean", "baseline_ci_lower", "baseline_ci_upper",
        "fleetsafe_mean", "fleetsafe_ci_lower", "fleetsafe_ci_upper",
        "delta_mean",     "delta_pct",
        "p_value", "significant", "effect_size_d", "direction",
        "n_baseline", "n_fleetsafe",
      }}
    """
    METRICS = [
        "spl",
        "success",
        "collision_count",
        "near_violation_count",
        "intervention_rate",
        "inference_latency_ms_mean",
        "path_length_m",
        "smoothness",
    ]

    def _vals(metrics_list, attr):
        return [float(getattr(m, attr)) for m in metrics_list]

    result = {}
    for metric in METRICS:
        try:
            base_vals = _vals(baseline_metrics,  metric)
            fs_vals   = _vals(fleetsafe_metrics, metric)
        except AttributeError:
            continue

        b_est, b_lo, b_hi = bootstrap_ci(base_vals, n_bootstrap=n_bootstrap, alpha=alpha, seed=seed)
        f_est, f_lo, f_hi = bootstrap_ci(fs_vals,   n_bootstrap=n_bootstrap, alpha=alpha, seed=seed)

        delta_mean = f_est - b_est
        delta_pct  = (delta_mean / b_est * 100.0) if b_est != 0.0 else float("nan")

        # Paired test requires same length (matched seeds)
        if len(base_vals) == len(fs_vals) and len(base_vals) >= 5:
            test = paired_wilcoxon(base_vals, fs_vals, alpha=alpha)
            p_val = test.p_value
            sig   = test.significant
            eff_d = test.effect_size
            dirn  = test.direction
        else:
            p_val, sig, eff_d, dirn = float("nan"), False, 0.0, "unknown"

        result[metric] = {
            "baseline_mean":       b_est,
            "baseline_ci_lower":   b_lo,
            "baseline_ci_upper":   b_hi,
            "fleetsafe_mean":      f_est,
            "fleetsafe_ci_lower":  f_lo,
            "fleetsafe_ci_upper":  f_hi,
            "delta_mean":          delta_mean,
            "delta_pct":           delta_pct,
            "p_value":             p_val,
            "significant":         sig,
            "effect_size_d":       eff_d,
            "direction":           dirn,
            "n_baseline":          len(base_vals),
            "n_fleetsafe":         len(fs_vals),
        }

    return result
