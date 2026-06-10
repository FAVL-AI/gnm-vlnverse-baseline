"""Tests for the CBF mathematical contract (no GPU, no ROS, no simulator).

Verifies:
  - h_i positive when distance > d_safe
  - h_i zero at distance exactly d_safe
  - h_i negative when distance < d_safe
  - CBF condition ḣ + α h ≥ 0 at boundary
  - QP-like command clipping respects actuator limits
  - Forward invariance: if h(0) >= 0 and CBF constraint holds, h(t) >= 0
"""

from __future__ import annotations

import math
import pytest


# ── CBF helper (inline, mirrors FleetSafe implementation) ────────────────────

def h_barrier(dist: float, d_safe: float) -> float:
    """h_i(x) = d_i^2 - d_safe^2."""
    return dist ** 2 - d_safe ** 2


def h_dot_unicycle(px: float, py: float, ox: float, oy: float,
                   v: float, psi: float) -> float:
    """ḣ for unicycle robot: 2 [(px-ox)·v·cosψ + (py-oy)·v·sinψ]."""
    return 2.0 * ((px - ox) * v * math.cos(psi) + (py - oy) * v * math.sin(psi))


def cbf_condition(h: float, h_dot: float, alpha: float) -> float:
    """Returns ḣ + α h (must be ≥ 0 for CBF constraint to hold)."""
    return h_dot + alpha * h


def clip_command(v: float, omega: float,
                 v_max: float = 0.5, omega_max: float = 1.0):
    """QP-like command clipping to actuator bounds."""
    v_safe = max(-v_max, min(v_max, v))
    omega_safe = max(-omega_max, min(omega_max, omega))
    return v_safe, omega_safe


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestBarrierFunction:
    """h_i(x) = d_i^2 - d_safe^2"""

    def test_h_positive_when_far(self):
        """Robot far from obstacle: h > 0 (safe)."""
        h = h_barrier(dist=2.0, d_safe=0.5)
        assert h > 0, f"Expected h > 0 when dist=2.0 > d_safe=0.5, got {h}"

    def test_h_zero_at_boundary(self):
        """Robot exactly at d_safe: h = 0 (boundary)."""
        h = h_barrier(dist=0.5, d_safe=0.5)
        assert abs(h) < 1e-12, f"Expected h = 0 at boundary, got {h}"

    def test_h_negative_when_close(self):
        """Robot inside unsafe zone: h < 0 (violation)."""
        h = h_barrier(dist=0.3, d_safe=0.5)
        assert h < 0, f"Expected h < 0 when dist=0.3 < d_safe=0.5, got {h}"

    def test_h_monotone_in_distance(self):
        """h is strictly increasing in distance."""
        d_safe = 0.5
        distances = [0.1, 0.3, 0.5, 0.7, 1.0, 2.0]
        hs = [h_barrier(d, d_safe) for d in distances]
        for i in range(len(hs) - 1):
            assert hs[i] < hs[i + 1], (
                f"h not monotone: h({distances[i]})={hs[i]:.3f} >= h({distances[i+1]})={hs[i+1]:.3f}"
            )

    @pytest.mark.parametrize("d_safe", [0.3, 0.5, 1.0])
    def test_h_zero_for_various_d_safe(self, d_safe):
        """h=0 at d_safe for multiple d_safe values."""
        h = h_barrier(d_safe, d_safe)
        assert abs(h) < 1e-12, f"h({d_safe}) != 0 for d_safe={d_safe}"


class TestCBFCondition:
    """ḣ + α h ≥ 0 must hold for the constraint to be satisfied."""

    def test_cbf_condition_satisfied_moving_away(self):
        """Robot moving away from obstacle satisfies CBF condition."""
        # Robot at (1, 0), obstacle at (0, 0), d=1, d_safe=0.5
        # Moving in +x direction (psi=0, v=0.5): moving away → ḣ > 0
        dist = 1.0
        h = h_barrier(dist, d_safe=0.5)  # = 0.75 > 0
        hd = h_dot_unicycle(px=1.0, py=0.0, ox=0.0, oy=0.0,
                            v=0.5, psi=0.0)  # positive (moving away)
        alpha = 1.0
        val = cbf_condition(h, hd, alpha)
        assert val >= 0, f"CBF condition violated when moving away: {val}"

    def test_cbf_condition_boundary_requires_positive_h_dot(self):
        """At the boundary (h=0), the CBF condition reduces to ḣ ≥ 0."""
        h = 0.0
        alpha = 1.0
        # ḣ = -0.1 violates (moving toward obstacle at boundary)
        assert cbf_condition(h, -0.1, alpha) < 0
        # ḣ = 0.1 satisfies
        assert cbf_condition(h, 0.1, alpha) >= 0

    def test_forward_invariance_exponential_lower_bound(self):
        """If h(0) >= 0 and ḣ + α h >= 0, then h(t) >= h(0)*exp(-α*t)."""
        h0 = 0.5
        alpha = 1.0
        dt = 0.001  # fine step — Euler discretisation error < 0.1%
        T = 2.0
        steps = int(T / dt)
        h = h0
        for _ in range(steps):
            h_dot_min = -alpha * h  # tightest CBF-consistent derivative
            h += h_dot_min * dt
        # Continuous lower bound: h(2) >= h(0)*exp(-2) ≈ 0.06767
        expected_lb = h0 * math.exp(-alpha * T)
        # Euler O(dt) error ≈ alpha^2 * h0 * dt * T / 2
        euler_error = alpha ** 2 * h0 * dt * T / 2
        assert h >= expected_lb - euler_error - 1e-9, (
            f"h={h:.6f} < lower bound {expected_lb:.6f} - euler_error {euler_error:.6f}"
        )

    def test_h_stays_nonneg_with_cbf_constraint(self):
        """h remains nonnegative when ḣ = -α h at every step (tight constraint)."""
        h0 = 1.0
        alpha = 0.5
        dt = 0.05
        h = h0
        for _ in range(100):
            h_dot = -alpha * h  # tight CBF constraint (equality)
            h = h + h_dot * dt
            assert h >= -1e-9, f"h went negative: {h}"


class TestCommandClipping:
    """QP-like command clipping respects actuator limits."""

    def test_clip_within_bounds_unchanged(self):
        v_s, w_s = clip_command(0.3, 0.5, v_max=0.5, omega_max=1.0)
        assert v_s == pytest.approx(0.3)
        assert w_s == pytest.approx(0.5)

    def test_clip_exceeds_v_max(self):
        v_s, _ = clip_command(1.0, 0.0, v_max=0.5)
        assert v_s == pytest.approx(0.5)

    def test_clip_negative_v(self):
        v_s, _ = clip_command(-1.0, 0.0, v_max=0.5)
        assert v_s == pytest.approx(-0.5)

    def test_clip_exceeds_omega_max(self):
        _, w_s = clip_command(0.0, 2.0, omega_max=1.0)
        assert w_s == pytest.approx(1.0)

    def test_clip_zero_command_unchanged(self):
        v_s, w_s = clip_command(0.0, 0.0)
        assert v_s == pytest.approx(0.0)
        assert w_s == pytest.approx(0.0)

    def test_clip_does_not_increase_magnitude(self):
        for v_in in (-2.0, -1.0, -0.1, 0.0, 0.1, 1.0, 2.0):
            v_s, _ = clip_command(v_in, 0.0, v_max=0.5)
            assert abs(v_s) <= 0.5 + 1e-9, f"|v_safe|={abs(v_s)} > v_max=0.5"
