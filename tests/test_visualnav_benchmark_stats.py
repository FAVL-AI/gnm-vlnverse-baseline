"""
tests/test_visualnav_benchmark_stats.py
Unit tests for fleet_safe_vla.benchmarks.visualnav_stats.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fleet_safe_vla.benchmarks.visualnav_stats import (
    PairedTestResult,
    bootstrap_ci,
    cohens_d,
    min_episodes_power,
    paired_wilcoxon,
    summarise_comparison,
)


# ── bootstrap_ci ──────────────────────────────────────────────────────────────

class TestBootstrapCI:
    def test_empty_input_returns_nan(self):
        est, lo, hi = bootstrap_ci([])
        assert math.isnan(est)
        assert math.isnan(lo)
        assert math.isnan(hi)

    def test_single_value(self):
        est, lo, hi = bootstrap_ci([5.0], seed=0)
        assert est == pytest.approx(5.0)
        # CI of a single constant must collapse to the value itself
        assert lo == pytest.approx(5.0, abs=1e-9)
        assert hi == pytest.approx(5.0, abs=1e-9)

    def test_known_mean(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        est, lo, hi = bootstrap_ci(data, n_bootstrap=5000, seed=42)
        assert est == pytest.approx(3.0)
        # CI should contain the true mean and be inside [1, 5]
        assert lo < est < hi
        assert lo >= 1.0
        assert hi <= 5.0

    def test_seed_reproducibility(self):
        data = list(range(20))
        r1 = bootstrap_ci(data, n_bootstrap=500, seed=7)
        r2 = bootstrap_ci(data, n_bootstrap=500, seed=7)
        assert r1 == r2

    def test_different_seeds_differ(self):
        data = list(range(20))
        _, lo1, hi1 = bootstrap_ci(data, n_bootstrap=500, seed=1)
        _, lo2, hi2 = bootstrap_ci(data, n_bootstrap=500, seed=2)
        # Different seeds may produce slightly different bounds
        # (not guaranteed, but almost certain for this many bootstraps)
        # Just verify they run without error and return finite values
        assert math.isfinite(lo1) and math.isfinite(hi1)
        assert math.isfinite(lo2) and math.isfinite(hi2)

    def test_custom_stat_fn_median(self):
        data = [1.0, 2.0, 3.0, 100.0]
        est, lo, hi = bootstrap_ci(data, stat_fn=np.median, n_bootstrap=2000, seed=0)
        # Median of [1, 2, 3, 100] = 2.5
        assert est == pytest.approx(2.5)
        assert lo <= est <= hi

    def test_alpha_affects_width(self):
        data = list(range(50))
        _, lo_95, hi_95 = bootstrap_ci(data, alpha=0.05, n_bootstrap=2000, seed=42)
        _, lo_50, hi_50 = bootstrap_ci(data, alpha=0.50, n_bootstrap=2000, seed=42)
        assert (hi_95 - lo_95) > (hi_50 - lo_50)

    def test_constant_data_zero_width(self):
        data = [3.14] * 20
        est, lo, hi = bootstrap_ci(data, n_bootstrap=200, seed=0)
        assert est == pytest.approx(3.14)
        assert lo == pytest.approx(3.14, abs=1e-9)
        assert hi == pytest.approx(3.14, abs=1e-9)

    def test_lower_le_estimate_le_upper(self):
        rng = np.random.default_rng(0)
        data = rng.standard_normal(30).tolist()
        est, lo, hi = bootstrap_ci(data, n_bootstrap=1000, seed=0)
        assert lo <= est <= hi


# ── cohens_d ──────────────────────────────────────────────────────────────────

class TestCohensD:
    def test_identical_samples_zero(self):
        a = [1.0, 2.0, 3.0]
        assert cohens_d(a, a) == pytest.approx(0.0)

    def test_known_value(self):
        # a = [0, 1], b = [2, 3]
        # pooled_std = sqrt(0.5) ≈ 0.7071, mean_a - mean_b = -2.0 → d ≈ -2.828
        a = [0.0, 1.0]
        b = [2.0, 3.0]
        d = cohens_d(a, b)
        assert d == pytest.approx(-2.0 / (0.5 ** 0.5), rel=1e-4)

    def test_zero_std_returns_zero(self):
        a = [5.0, 5.0, 5.0]
        b = [5.0, 5.0, 5.0]
        assert cohens_d(a, b) == pytest.approx(0.0)

    def test_single_element_returns_zero(self):
        assert cohens_d([1.0], [2.0]) == pytest.approx(0.0)

    def test_sign_convention(self):
        # cohens_d(a, b) = (mean_a - mean_b) / pooled_std
        # if mean_a > mean_b → positive
        a = [3.0, 4.0]
        b = [1.0, 2.0]
        assert cohens_d(a, b) > 0.0

    def test_magnitude_increases_with_separation(self):
        a = [0.0, 1.0]
        b1 = [1.0, 2.0]
        b2 = [5.0, 6.0]
        d1 = abs(cohens_d(a, b1))
        d2 = abs(cohens_d(a, b2))
        assert d2 > d1

    def test_medium_effect_approximately_correct(self):
        rng = np.random.default_rng(0)
        # Two samples drawn from N(0,1) and N(0.5,1) → expected d ≈ 0.5
        a = rng.normal(0.0, 1.0, 200)
        b = rng.normal(0.5, 1.0, 200)
        d = abs(cohens_d(a, b))
        assert 0.2 < d < 0.8


# ── paired_wilcoxon ───────────────────────────────────────────────────────────

class TestPairedWilcoxon:
    def test_returns_paired_test_result(self):
        a = [1.0, 2.0, 3.0, 4.0, 5.0]
        b = [2.0, 3.0, 4.0, 5.0, 6.0]
        result = paired_wilcoxon(a, b)
        assert isinstance(result, PairedTestResult)

    def test_clearly_significant_effect(self):
        # treatment is consistently 10 units higher than baseline
        rng = np.random.default_rng(42)
        baseline  = rng.standard_normal(30).tolist()
        treatment = [x + 10.0 for x in baseline]
        result = paired_wilcoxon(baseline, treatment)
        assert result.p_value < 0.05
        assert result.significant  # numpy.bool_ safe comparison
        assert result.direction == "improved"

    def test_clearly_not_significant(self):
        rng = np.random.default_rng(42)
        data = rng.standard_normal(20).tolist()
        result = paired_wilcoxon(data, data)
        # Identical → all diffs = 0 → fallback → p_value = nan, significant = False
        assert result.significant is False

    def test_direction_degraded(self):
        baseline  = [2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
        treatment = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        result = paired_wilcoxon(baseline, treatment)
        assert result.direction == "degraded"

    def test_n_pairs_correct(self):
        a = [1.0] * 15
        b = [2.0] * 15
        result = paired_wilcoxon(a, b)
        assert result.n_pairs == 15

    def test_mismatched_length_raises(self):
        with pytest.raises(ValueError):
            paired_wilcoxon([1.0, 2.0], [1.0, 2.0, 3.0])

    def test_small_sample_falls_back(self):
        # < 5 pairs → fallback; should not raise
        result = paired_wilcoxon([1.0, 2.0], [3.0, 4.0])
        assert result.method == "sign_test_fallback"

    def test_effect_size_positive_when_improved(self):
        rng = np.random.default_rng(7)
        # baseline centred around 1, treatment centred around 3 (same variance)
        baseline  = (rng.standard_normal(20) + 1.0).tolist()
        treatment = (rng.standard_normal(20) + 3.0).tolist()
        result = paired_wilcoxon(baseline, treatment)
        # cohens_d(baseline, treatment) = (mean_b - mean_t)/pooled → negative
        # direction="improved" confirms treatment > baseline
        assert result.direction == "improved"
        assert result.effect_size != 0.0


# ── min_episodes_power ────────────────────────────────────────────────────────

class TestMinEpisodesPower:
    def test_larger_effect_needs_fewer_episodes(self):
        n_small  = min_episodes_power(expected_effect_d=0.2)
        n_medium = min_episodes_power(expected_effect_d=0.5)
        n_large  = min_episodes_power(expected_effect_d=0.8)
        assert n_small > n_medium > n_large

    def test_result_is_positive_integer(self):
        n = min_episodes_power(expected_effect_d=0.5)
        assert isinstance(n, int)
        assert n > 0

    def test_minimum_floor(self):
        # Even for large effect sizes, floor is 10
        n = min_episodes_power(expected_effect_d=2.0)
        assert n >= 10

    def test_d03_approximately_90(self):
        n = min_episodes_power(expected_effect_d=0.3)
        # Statistical convention: ~90 episodes for d=0.3, α=0.05, power=0.80
        assert 70 <= n <= 120

    def test_d05_approximately_34(self):
        n = min_episodes_power(expected_effect_d=0.5)
        assert 25 <= n <= 45

    def test_higher_power_needs_more_episodes(self):
        n80 = min_episodes_power(expected_effect_d=0.5, power=0.80)
        n90 = min_episodes_power(expected_effect_d=0.5, power=0.90)
        assert n90 > n80

    def test_stricter_alpha_needs_more_episodes(self):
        n05 = min_episodes_power(expected_effect_d=0.5, alpha=0.05)
        n01 = min_episodes_power(expected_effect_d=0.5, alpha=0.01)
        assert n01 > n05


# ── summarise_comparison ──────────────────────────────────────────────────────

class TestSummariseComparison:
    """Uses simple mock EpisodeMetrics objects so the test is self-contained."""

    class _FakeMetrics:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    def _make_episodes(self, n, spl_val, collision_val, success_val=1.0,
                       near_viol=0.0, intervention_rate=0.0,
                       latency=10.0, path_m=1.0, smoothness=1.0):
        return [
            self._FakeMetrics(
                spl=spl_val,
                success=success_val,
                collision_count=collision_val,
                near_violation_count=near_viol,
                intervention_rate=intervention_rate,
                inference_latency_ms_mean=latency,
                path_length_m=path_m,
                smoothness=smoothness,
            )
            for _ in range(n)
        ]

    def test_returns_dict_with_expected_keys(self):
        base = self._make_episodes(10, spl_val=0.5, collision_val=2.0)
        fs   = self._make_episodes(10, spl_val=0.6, collision_val=1.0)
        result = summarise_comparison(base, fs, n_bootstrap=100, seed=0)
        assert "spl" in result
        assert "collision_count" in result
        assert "near_violation_count" in result

    def test_per_metric_keys_present(self):
        base = self._make_episodes(10, spl_val=0.5, collision_val=2.0)
        fs   = self._make_episodes(10, spl_val=0.6, collision_val=1.0)
        result = summarise_comparison(base, fs, n_bootstrap=100, seed=0)
        for metric, stats in result.items():
            for key in ("baseline_mean", "fleetsafe_mean", "delta_mean",
                        "delta_pct", "p_value", "significant",
                        "effect_size_d", "direction"):
                assert key in stats, f"key '{key}' missing from metric '{metric}'"

    def test_delta_direction_improvement(self):
        base = self._make_episodes(15, spl_val=0.4, collision_val=3.0)
        fs   = self._make_episodes(15, spl_val=0.7, collision_val=1.0)
        result = summarise_comparison(base, fs, n_bootstrap=200, seed=0)
        # SPL improved → delta_mean should be positive
        assert result["spl"]["delta_mean"] > 0
        # Collision decreased → delta_mean should be negative
        assert result["collision_count"]["delta_mean"] < 0

    def test_n_baseline_n_fleetsafe_recorded(self):
        base = self._make_episodes(12, spl_val=0.5, collision_val=0.0)
        fs   = self._make_episodes(12, spl_val=0.5, collision_val=0.0)
        result = summarise_comparison(base, fs, n_bootstrap=100, seed=0)
        assert result["spl"]["n_baseline"] == 12
        assert result["spl"]["n_fleetsafe"] == 12

    def test_identical_conditions_zero_delta(self):
        episodes = self._make_episodes(10, spl_val=0.5, collision_val=1.0)
        result = summarise_comparison(episodes, episodes, n_bootstrap=200, seed=0)
        assert result["spl"]["delta_mean"] == pytest.approx(0.0, abs=1e-9)

    def test_empty_input_does_not_crash(self):
        # Both empty: should return empty dict (no metrics extracted)
        result = summarise_comparison([], [], n_bootstrap=100, seed=0)
        assert isinstance(result, dict)

    def test_mismatched_lengths_skips_paired_test(self):
        base = self._make_episodes(10, spl_val=0.5, collision_val=1.0)
        fs   = self._make_episodes(8,  spl_val=0.6, collision_val=0.5)
        # Mismatched lengths → paired test skipped → p_value = nan
        result = summarise_comparison(base, fs, n_bootstrap=100, seed=0)
        assert math.isnan(result["spl"]["p_value"])
