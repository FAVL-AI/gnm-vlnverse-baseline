"""
lidar_sanitizer.py — Mathematically auditable LiDAR range filter.

Raw LiDAR minimum range is NOT reliable for safety decisions:
  - Many sensors return range_min (e.g., 0.05 m) for invalid readings.
  - Body self-returns produce spurious close readings.
  - A single bad beam would veto all motion if we blindly use raw min.

This module separates *sensor artifacts* from *real obstacles* by:
  1. Discarding non-finite (inf/nan) values.
  2. Discarding values ≤ range_min + epsilon (the sensor's own dead zone).
  3. Discarding values > range_max.
  4. Computing a robust percentile clearance (default: 5th percentile),
     so one noisy beam does not veto all motion.
  5. Preserving the raw minimum in every output for full auditability.

Safety is NEVER weakened: if the effective clearance after filtering
is still below the safety radius, the CBF/e-stop fires as normal.
The filter only prevents artifact beams from causing false e-stops.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence


# Default epsilon added to range_min to define the sensor dead zone.
# Most LiDARs that report range_min=0.05 m produce spurious readings
# at exactly range_min (or within a few mm) for invalid returns.
_DEFAULT_EPSILON_M: float = 0.02


@dataclass(frozen=True)
class LidarSample:
    """Sanitized result from one LaserScan message."""

    # ── Raw fields (always present, never modified) ───────────────────────
    raw_min_m:      float   # smallest value in the ranges array (may be artifact)
    range_min_m:    float   # sensor's declared minimum range
    range_max_m:    float   # sensor's declared maximum range
    total_beams:    int     # length of the original ranges array

    # ── Filtered fields ───────────────────────────────────────────────────
    valid_min_m:    float   # minimum of valid beams (inf if no valid beams)
    valid_p05_m:    float   # 5th-percentile of valid beams  (robust clearance)
    valid_p10_m:    float   # 10th-percentile of valid beams
    valid_count:    int     # number of beams that passed the filter
    invalid_count:  int     # number of beams that were discarded

    # ── Decision field ─────────────────────────────────────────────────────
    effective_clearance_m: float   # value used by the CBF (percentile or min)
    clearance_source:      str     # "p05", "p10", "valid_min", "raw_min", "invalid"

    # ── Filtering parameters ──────────────────────────────────────────────
    epsilon_m:             float   # dead-zone epsilon actually used
    percentile:            int     # which percentile was used (5 or 10)

    # ── Audit flag ────────────────────────────────────────────────────────
    filtering_applied: bool   # True if any beams were discarded

    @property
    def is_safe_at(self, d_safe: float) -> bool:
        return self.effective_clearance_m >= d_safe

    def to_dict(self) -> dict:
        return {
            "raw_min_m":             self.raw_min_m,
            "valid_min_m":           self.valid_min_m,
            "valid_p05_m":           self.valid_p05_m,
            "valid_p10_m":           self.valid_p10_m,
            "effective_clearance_m": self.effective_clearance_m,
            "clearance_source":      self.clearance_source,
            "valid_count":           self.valid_count,
            "invalid_count":         self.invalid_count,
            "total_beams":           self.total_beams,
            "range_min_m":           self.range_min_m,
            "range_max_m":           self.range_max_m,
            "epsilon_m":             self.epsilon_m,
            "percentile":            self.percentile,
            "filtering_applied":     self.filtering_applied,
        }


def sanitize(
    ranges: Sequence[float],
    range_min: float,
    range_max: float,
    *,
    epsilon: float = _DEFAULT_EPSILON_M,
    percentile: int = 5,
) -> LidarSample:
    """
    Sanitize a LaserScan ranges array and return an auditable LidarSample.

    Parameters
    ----------
    ranges      : Raw ranges from the sensor (metres).
    range_min   : Sensor's declared minimum valid range (metres).
    range_max   : Sensor's declared maximum valid range (metres).
    epsilon     : Dead-zone margin added to range_min.  Readings in
                  [range_min, range_min + epsilon] are treated as sensor
                  artifacts and discarded (default 0.02 m).
    percentile  : Which percentile to use for effective_clearance_m.
                  Must be 1–99 (default 5).

    Returns
    -------
    LidarSample with raw, filtered, and decision fields.
    """
    if not 1 <= percentile <= 99:
        raise ValueError(f"percentile must be 1–99, got {percentile}")

    ranges_list = list(ranges)
    total = len(ranges_list)

    # ── Raw minimum (full audit trail, no filtering) ──────────────────────
    finite_vals = [r for r in ranges_list if math.isfinite(r)]
    raw_min = min(finite_vals) if finite_vals else float("inf")

    # ── Filter: keep values that are clearly valid ────────────────────────
    threshold_lo = range_min + epsilon
    valid: list[float] = []
    for r in ranges_list:
        if not math.isfinite(r):
            continue
        if r <= threshold_lo:
            continue
        if r > range_max:
            continue
        valid.append(r)

    valid_count   = len(valid)
    invalid_count = total - valid_count

    # ── Aggregate statistics over valid beams ─────────────────────────────
    if valid_count == 0:
        # No valid readings — treat as maximum danger (force e-stop)
        return LidarSample(
            raw_min_m             = raw_min,
            range_min_m           = range_min,
            range_max_m           = range_max,
            total_beams           = total,
            valid_min_m           = float("inf"),
            valid_p05_m           = float("inf"),
            valid_p10_m           = float("inf"),
            valid_count           = 0,
            invalid_count         = invalid_count,
            effective_clearance_m = 0.0,
            clearance_source      = "invalid",
            epsilon_m             = epsilon,
            percentile            = percentile,
            filtering_applied     = invalid_count > 0,
        )

    valid_sorted = sorted(valid)
    valid_min    = valid_sorted[0]

    def _pctile(pct: int) -> float:
        idx = max(0, int(math.ceil(pct / 100.0 * valid_count)) - 1)
        idx = min(idx, valid_count - 1)
        return valid_sorted[idx]

    p05 = _pctile(5)
    p10 = _pctile(10)

    # Effective clearance: use the requested percentile
    eff = _pctile(percentile)
    src = f"p{percentile:02d}"

    return LidarSample(
        raw_min_m             = raw_min,
        range_min_m           = range_min,
        range_max_m           = range_max,
        total_beams           = total,
        valid_min_m           = valid_min,
        valid_p05_m           = p05,
        valid_p10_m           = p10,
        valid_count           = valid_count,
        invalid_count         = invalid_count,
        effective_clearance_m = eff,
        clearance_source      = src,
        epsilon_m             = epsilon,
        percentile            = percentile,
        filtering_applied     = invalid_count > 0,
    )


def merge_samples(*samples: LidarSample) -> LidarSample:
    """
    Merge multiple LidarSamples (e.g., scan0 + scan1) into a single
    worst-case sample.  The result's effective_clearance_m is the
    minimum across all inputs.

    Raw minimum and valid minimum are also the combined minimums.
    Invalid counts are summed.
    """
    if not samples:
        raise ValueError("merge_samples requires at least one sample")
    if len(samples) == 1:
        return samples[0]

    s0 = min(samples, key=lambda s: s.effective_clearance_m)

    combined_raw_min   = min(s.raw_min_m   for s in samples)
    combined_valid_min = min(s.valid_min_m for s in samples)
    combined_eff       = min(s.effective_clearance_m for s in samples)
    total_invalid      = sum(s.invalid_count for s in samples)
    total_valid        = sum(s.valid_count   for s in samples)
    total_beams        = sum(s.total_beams   for s in samples)
    filtering_applied  = any(s.filtering_applied for s in samples)

    return LidarSample(
        raw_min_m             = combined_raw_min,
        range_min_m           = s0.range_min_m,
        range_max_m           = s0.range_max_m,
        total_beams           = total_beams,
        valid_min_m           = combined_valid_min,
        valid_p05_m           = min(s.valid_p05_m for s in samples),
        valid_p10_m           = min(s.valid_p10_m for s in samples),
        valid_count           = total_valid,
        invalid_count         = total_invalid,
        effective_clearance_m = combined_eff,
        clearance_source      = f"merged({s0.clearance_source})",
        epsilon_m             = s0.epsilon_m,
        percentile            = s0.percentile,
        filtering_applied     = filtering_applied,
    )
