"""
test_lidar_sanitizer.py — Unit tests for fleet_safe_vla.safety.lidar_sanitizer.

Covers:
  - Dead-zone zeros are ignored (filtered, not used for clearance)
  - Values at or below range_min are ignored
  - Values at range_min + epsilon boundary are ignored
  - Finite valid readings above the dead zone are preserved
  - 5th-percentile clearance is computed correctly
  - No valid beams → effective_clearance_m=0.0 (forces CBF e-stop)
  - raw_min is recorded even when all beams are filtered
  - merge_samples takes the worst-case clearance across scanners
"""
from __future__ import annotations

import math
import pytest

from fleet_safe_vla.safety.lidar_sanitizer import sanitize, merge_samples, LidarSample

RANGE_MIN = 0.05   # typical Yahboom LiDAR
RANGE_MAX = 12.0
EPSILON   = 0.02   # default dead-zone margin


# ── Helper ────────────────────────────────────────────────────────────────────

def _make_ranges(n_dead: int = 0, valid: list[float] | None = None,
                 n_inf: int = 0) -> list[float]:
    """Build a ranges list with dead-zone artifacts, valid readings, and infs."""
    dead  = [RANGE_MIN] * n_dead           # exactly range_min → filtered
    valid_vals = list(valid or [])
    infs  = [float("inf")] * n_inf
    return dead + valid_vals + infs


# ── 1. Dead-zone zeros are ignored ───────────────────────────────────────────

def test_dead_zone_returns_not_used_for_clearance():
    """range_min returns (0.05 m) must NOT become the effective clearance."""
    ranges = _make_ranges(n_dead=20, valid=[1.0, 1.1, 0.9, 1.2])
    s = sanitize(ranges, RANGE_MIN, RANGE_MAX, epsilon=EPSILON)
    assert s.effective_clearance_m > RANGE_MIN + EPSILON, (
        f"Dead-zone artifacts leaked into effective clearance: {s.effective_clearance_m}"
    )
    assert s.invalid_count >= 20


def test_dead_zone_exact_range_min_filtered():
    """Readings equal to range_min are below the threshold and must be discarded."""
    ranges = [RANGE_MIN] * 50 + [0.80, 0.85, 0.90]
    s = sanitize(ranges, RANGE_MIN, RANGE_MAX, epsilon=EPSILON)
    assert s.valid_count == 3
    assert s.invalid_count == 50


# ── 2. Values below range_min are ignored ────────────────────────────────────

def test_below_range_min_ignored():
    """Values strictly below range_min are non-finite or clearly invalid."""
    ranges = [0.001, 0.02, 0.04] + [1.0, 1.5, 2.0]
    s = sanitize(ranges, RANGE_MIN, RANGE_MAX, epsilon=EPSILON)
    # 0.001, 0.02, 0.04 are all ≤ range_min + epsilon (0.05 + 0.02 = 0.07)
    assert s.valid_count == 3
    for v in [0.001, 0.02, 0.04]:
        assert v not in [s.valid_min_m, s.effective_clearance_m]


# ── 3. Values at range_min + epsilon boundary ─────────────────────────────────

def test_value_at_threshold_filtered():
    """A reading exactly equal to range_min + epsilon is NOT valid (≤ threshold)."""
    threshold = RANGE_MIN + EPSILON   # 0.07 m
    ranges = [threshold, 1.0, 1.1]
    s = sanitize(ranges, RANGE_MIN, RANGE_MAX, epsilon=EPSILON)
    assert s.valid_count == 2, (
        f"threshold={threshold} should be filtered, valid_count should be 2, got {s.valid_count}"
    )


def test_value_just_above_threshold_kept():
    """A reading just above range_min + epsilon is valid."""
    threshold = RANGE_MIN + EPSILON   # 0.07 m
    just_above = threshold + 0.001    # 0.071 m
    ranges = [just_above, 1.0]
    s = sanitize(ranges, RANGE_MIN, RANGE_MAX, epsilon=EPSILON)
    assert s.valid_count == 2


# ── 4. Finite valid readings are preserved ───────────────────────────────────

def test_valid_readings_preserved():
    """Readings well above the dead zone are included in statistics."""
    valid_vals = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    ranges = valid_vals + [RANGE_MIN] * 5
    s = sanitize(ranges, RANGE_MIN, RANGE_MAX, epsilon=EPSILON)
    assert s.valid_count == len(valid_vals)
    assert math.isclose(s.valid_min_m, 0.5, rel_tol=1e-6)


def test_inf_values_discarded():
    """Non-finite readings (inf, nan) are discarded."""
    ranges = [float("inf"), float("nan"), 1.0, 1.5]
    s = sanitize(ranges, RANGE_MIN, RANGE_MAX, epsilon=EPSILON)
    assert s.valid_count == 2
    assert s.invalid_count == 2


def test_beyond_range_max_discarded():
    """Readings > range_max are discarded."""
    ranges = [RANGE_MAX + 1.0, RANGE_MAX + 5.0, 1.0, 1.5]
    s = sanitize(ranges, RANGE_MIN, RANGE_MAX, epsilon=EPSILON)
    assert s.valid_count == 2


# ── 5. Percentile clearance ───────────────────────────────────────────────────

def test_percentile_p05_correct():
    """5th percentile of 100 uniform readings is roughly the 5th smallest."""
    ranges = [0.10 * i for i in range(1, 101)]  # 0.10, 0.20, …, 10.00 m
    # All are above threshold 0.07; all below range_max 12.0
    s = sanitize(ranges, RANGE_MIN, RANGE_MAX, epsilon=EPSILON, percentile=5)
    # ceil(5/100 * 100) = 5 → index 4 (0-based) → 5th element = 0.50 m
    assert math.isclose(s.valid_p05_m, 0.50, rel_tol=1e-5), (
        f"Expected p05≈0.50, got {s.valid_p05_m}"
    )
    assert math.isclose(s.effective_clearance_m, 0.50, rel_tol=1e-5)


def test_percentile_single_valid_beam():
    """With one valid beam the percentile must equal that beam's range."""
    ranges = [RANGE_MIN] * 100 + [1.23]
    s = sanitize(ranges, RANGE_MIN, RANGE_MAX, epsilon=EPSILON, percentile=5)
    assert math.isclose(s.effective_clearance_m, 1.23, rel_tol=1e-5)
    assert s.valid_count == 1


def test_percentile_p10():
    """percentile=10 uses 10th percentile instead of 5th."""
    ranges = [float(i) for i in range(1, 11)]  # 1..10
    s = sanitize(ranges, RANGE_MIN, RANGE_MAX, epsilon=EPSILON, percentile=10)
    # ceil(10/100 * 10) = 1 → index 0 → 1.0 m
    assert math.isclose(s.effective_clearance_m, 1.0, rel_tol=1e-5)


def test_percentile_invalid_raises():
    """percentile outside 1–99 must raise ValueError."""
    with pytest.raises(ValueError):
        sanitize([1.0], RANGE_MIN, RANGE_MAX, percentile=0)
    with pytest.raises(ValueError):
        sanitize([1.0], RANGE_MIN, RANGE_MAX, percentile=100)


# ── 6. No valid beams → unsafe ────────────────────────────────────────────────

def test_no_valid_beams_returns_zero_clearance():
    """All-artifact scan must set effective_clearance_m=0.0 to force CBF e-stop."""
    ranges = [RANGE_MIN] * 200 + [float("inf")] * 50
    s = sanitize(ranges, RANGE_MIN, RANGE_MAX, epsilon=EPSILON)
    assert s.valid_count == 0
    assert s.effective_clearance_m == 0.0
    assert s.clearance_source == "invalid"


def test_empty_ranges_returns_zero_clearance():
    """Empty scan must also force e-stop."""
    s = sanitize([], RANGE_MIN, RANGE_MAX, epsilon=EPSILON)
    assert s.effective_clearance_m == 0.0


# ── 7. raw_min preserved even when all beams filtered ─────────────────────────

def test_raw_min_preserved_when_all_filtered():
    """raw_min_m records the actual sensor minimum even when it is an artifact."""
    artifact_val = 0.05
    ranges = [artifact_val] * 100 + [float("inf")] * 20
    s = sanitize(ranges, RANGE_MIN, RANGE_MAX, epsilon=EPSILON)
    assert math.isclose(s.raw_min_m, artifact_val, rel_tol=1e-6), (
        f"raw_min_m should be {artifact_val}, got {s.raw_min_m}"
    )
    assert s.valid_count == 0         # all filtered
    assert s.effective_clearance_m == 0.0  # e-stop triggered


def test_raw_min_is_true_minimum_not_valid_minimum():
    """raw_min reflects the smallest finite value, even if filtered as dead-zone."""
    ranges = [0.03, 0.05, 1.0, 2.0, 3.0]
    s = sanitize(ranges, RANGE_MIN, RANGE_MAX, epsilon=EPSILON)
    assert math.isclose(s.raw_min_m, 0.03, rel_tol=1e-6)
    assert s.valid_min_m > RANGE_MIN + EPSILON  # 1.0, not 0.03


def test_filtering_applied_flag():
    """filtering_applied must be True whenever any beams were discarded."""
    ranges_all_valid   = [1.0, 2.0, 3.0]
    ranges_with_artifacts = [RANGE_MIN] * 5 + [1.0, 2.0]

    s_clean = sanitize(ranges_all_valid, RANGE_MIN, RANGE_MAX, epsilon=EPSILON)
    assert s_clean.filtering_applied is False

    s_dirty = sanitize(ranges_with_artifacts, RANGE_MIN, RANGE_MAX, epsilon=EPSILON)
    assert s_dirty.filtering_applied is True


# ── 8. merge_samples ──────────────────────────────────────────────────────────

def test_merge_two_samples_worst_case():
    """merge_samples must return the minimum effective clearance."""
    s0 = sanitize([1.0, 1.1, 1.2], RANGE_MIN, RANGE_MAX, epsilon=EPSILON)
    s1 = sanitize([0.5, 0.6, 0.7], RANGE_MIN, RANGE_MAX, epsilon=EPSILON)
    merged = merge_samples(s0, s1)
    expected_eff = min(s0.effective_clearance_m, s1.effective_clearance_m)
    assert math.isclose(merged.effective_clearance_m, expected_eff, rel_tol=1e-6)


def test_merge_single_sample_identity():
    """merge_samples with one sample returns that sample unchanged."""
    s = sanitize([1.0, 1.1], RANGE_MIN, RANGE_MAX, epsilon=EPSILON)
    merged = merge_samples(s)
    assert merged is s


def test_merge_requires_at_least_one_sample():
    """merge_samples() with no arguments must raise ValueError."""
    with pytest.raises(ValueError):
        merge_samples()


def test_merge_combined_invalid_count():
    """merged.invalid_count is the sum of both scans' invalid counts."""
    s0 = sanitize([RANGE_MIN] * 5 + [1.0, 1.1], RANGE_MIN, RANGE_MAX, epsilon=EPSILON)
    s1 = sanitize([RANGE_MIN] * 8 + [0.9, 1.0], RANGE_MIN, RANGE_MAX, epsilon=EPSILON)
    merged = merge_samples(s0, s1)
    assert merged.invalid_count == s0.invalid_count + s1.invalid_count


# ── 9. to_dict round-trip ─────────────────────────────────────────────────────

def test_to_dict_has_all_required_keys():
    """to_dict() must include all audit fields needed by the certificate."""
    s = sanitize([0.8, 0.9, 1.0], RANGE_MIN, RANGE_MAX, epsilon=EPSILON)
    d = s.to_dict()
    required = {
        "raw_min_m", "valid_min_m", "valid_p05_m", "valid_p10_m",
        "effective_clearance_m", "clearance_source",
        "valid_count", "invalid_count", "total_beams",
        "range_min_m", "range_max_m", "epsilon_m",
        "percentile", "filtering_applied",
    }
    for key in required:
        assert key in d, f"Missing key in to_dict(): {key!r}"


def test_to_dict_values_are_json_serializable():
    """to_dict() values must be JSON-serializable (no numpy, no custom objects)."""
    import json
    s = sanitize([0.8, 0.9, 1.0], RANGE_MIN, RANGE_MAX, epsilon=EPSILON)
    # Must not raise
    json.dumps(s.to_dict())
