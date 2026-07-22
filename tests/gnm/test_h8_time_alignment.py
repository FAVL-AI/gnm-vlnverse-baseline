"""H8-S1 — image-to-pose time-alignment tests.

Covers the twenty synthetic alignment fixtures required by the H8-S1 gate, plus the tolerance
derivation. Every rejection path asserts its deterministic reason code.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "gnm"))

from h8_s1_reason_codes import (  # noqa: E402
    H8_ALIGNMENT_CLOCK_RESET,
    H8_ALIGNMENT_DUPLICATE_TIMESTAMP_AMBIGUOUS,
    H8_ALIGNMENT_EXTRAPOLATION_REFUSED,
    H8_ALIGNMENT_FRAME_MISMATCH,
    H8_ALIGNMENT_GAP_EXCEEDED,
    H8_ALIGNMENT_IMAGE_STAMP_MISSING,
    H8_ALIGNMENT_NO_BRACKETING_POSE,
    H8_ALIGNMENT_NON_FINITE,
    H8_ALIGNMENT_POSE_MISSING,
    H8_ALIGNMENT_QUATERNION_INVALID,
    H8_ALIGNMENT_TIMESTAMP_ORDER_INVALID,
    H8_ALIGNMENT_TRANSFORM_UNRESOLVED,
    H8_TIME_DOMAIN_MISMATCH,
    is_valid_code,
)
from h8_time_alignment import (  # noqa: E402
    ALIGNMENT_TOLERANCE_S,
    AUTHORITATIVE_CLOCK,
    CLOCK_WALL,
    MAX_POSITION_INTERPOLATION_ERROR_M,
    MAX_YAW_INTERPOLATION_ERROR_DEG,
    STATUS_OK,
    STATUS_REJECTED,
    Pose,
    align_image_to_pose,
    align_series,
    quaternion_from_yaw,
    summarise,
    tolerance_derivation,
    yaw_from_quaternion,
)

PERIOD = 0.05


def _pose(t: float, x: float = 0.0, y: float = 0.0, yaw: float = 0.0, **kw) -> Pose:
    qx, qy, qz, qw = quaternion_from_yaw(yaw)
    return Pose(stamp=t, x=x, y=y, qx=qx, qy=qy, qz=qz, qw=qw, **kw)


def _series(n: int = 5, dt: float = PERIOD, vx: float = 0.2, dyaw: float = 0.0):
    return [_pose(i * dt, x=vx * i * dt, yaw=dyaw * i * dt) for i in range(n)]


# --- fixture 1: exact timestamp match -----------------------------------------------------------
def test_f01_exact_timestamp_match():
    poses = _series()
    r = align_image_to_pose(poses[2].stamp, poses)
    assert r.status == STATUS_OK
    assert r.alignment_method == "exact_sample"
    assert r.residual_s == 0.0
    assert r.x == pytest.approx(poses[2].x)


# --- fixture 2: midpoint interpolation ----------------------------------------------------------
def test_f02_midpoint_interpolation():
    poses = _series()
    t = (poses[1].stamp + poses[2].stamp) / 2.0
    r = align_image_to_pose(t, poses)
    assert r.status == STATUS_OK
    assert r.x == pytest.approx((poses[1].x + poses[2].x) / 2.0)
    assert r.pose_stamp_before == poses[1].stamp
    assert r.pose_stamp_after == poses[2].stamp


# --- fixtures 3 and 4: image near the earlier / later pose ---------------------------------------
def test_f03_image_near_earlier_pose():
    poses = _series()
    r = align_image_to_pose(poses[1].stamp + 0.001, poses)
    assert r.status == STATUS_OK
    assert r.x == pytest.approx(poses[1].x, abs=1e-3)


def test_f04_image_near_later_pose():
    poses = _series()
    r = align_image_to_pose(poses[2].stamp - 0.001, poses)
    assert r.status == STATUS_OK
    assert r.x == pytest.approx(poses[2].x, abs=1e-3)


# --- fixture 5: yaw crossing +/- pi ---------------------------------------------------------------
def test_f05_yaw_wrap_takes_short_arc():
    """Interpolating 175 deg -> -175 deg must pass through 180, not sweep back through zero."""
    poses = [_pose(0.0, yaw=math.radians(175.0)), _pose(PERIOD, yaw=math.radians(-175.0))]
    r = align_image_to_pose(PERIOD / 2.0, poses)
    assert r.status == STATUS_OK
    assert abs(r.yaw_rad) == pytest.approx(math.pi, abs=1e-6)


def test_f05b_yaw_wrap_never_returns_zero():
    poses = [_pose(0.0, yaw=math.radians(179.0)), _pose(PERIOD, yaw=math.radians(-179.0))]
    r = align_image_to_pose(PERIOD / 2.0, poses)
    assert abs(r.yaw_rad) > math.radians(179.0)


# --- fixture 6: stationary robot ------------------------------------------------------------------
def test_f06_stationary_robot():
    poses = [_pose(i * PERIOD, x=1.0, y=2.0, yaw=0.3) for i in range(4)]
    r = align_image_to_pose(1.5 * PERIOD, poses)
    assert r.status == STATUS_OK
    assert (r.x, r.y) == pytest.approx((1.0, 2.0))
    assert r.yaw_rad == pytest.approx(0.3)


# --- fixture 7: constant linear motion -------------------------------------------------------------
def test_f07_constant_linear_motion():
    poses = _series(vx=0.2)
    r = align_image_to_pose(1.5 * PERIOD, poses)
    assert r.x == pytest.approx(0.2 * 1.5 * PERIOD)


# --- fixture 8: constant angular motion -------------------------------------------------------------
def test_f08_constant_angular_motion():
    poses = _series(vx=0.0, dyaw=0.4)
    r = align_image_to_pose(1.5 * PERIOD, poses)
    assert r.status == STATUS_OK
    assert r.yaw_rad == pytest.approx(0.4 * 1.5 * PERIOD, abs=1e-9)


# --- fixtures 9 and 10: missing earlier / later pose --------------------------------------------------
def test_f09_missing_earlier_pose_is_refused():
    poses = _series()
    r = align_image_to_pose(poses[0].stamp - 0.001, poses)
    assert r.status == STATUS_REJECTED
    assert r.rejection_reason == H8_ALIGNMENT_NO_BRACKETING_POSE


def test_f10_missing_later_pose_is_refused():
    poses = _series()
    r = align_image_to_pose(poses[-1].stamp + 0.001, poses)
    assert r.status == STATUS_REJECTED
    assert r.rejection_reason == H8_ALIGNMENT_NO_BRACKETING_POSE


def test_f10b_far_outside_series_is_extrapolation_refused():
    poses = _series()
    r = align_image_to_pose(poses[-1].stamp + 10.0, poses)
    assert r.rejection_reason == H8_ALIGNMENT_EXTRAPOLATION_REFUSED


# --- fixtures 11-13: tolerance boundary ---------------------------------------------------------------
def _gap_case(gap: float):
    """Two poses `2*gap` apart with the image exactly in the middle -> residual == gap."""
    poses = [_pose(0.0, x=0.0), _pose(2 * gap, x=0.2 * 2 * gap)]
    return align_image_to_pose(gap, poses)


def test_f11_gap_just_below_tolerance_accepted():
    r = _gap_case(ALIGNMENT_TOLERANCE_S - 1e-6)
    assert r.status == STATUS_OK


def test_f12_gap_exactly_at_tolerance_accepted():
    r = _gap_case(ALIGNMENT_TOLERANCE_S)
    assert r.status == STATUS_OK, "boundary is inclusive by specification"


def test_f13_gap_just_above_tolerance_rejected():
    r = _gap_case(ALIGNMENT_TOLERANCE_S + 1e-6)
    assert r.status == STATUS_REJECTED
    assert r.rejection_reason == H8_ALIGNMENT_GAP_EXCEEDED


# --- fixture 14: duplicate pose timestamps ---------------------------------------------------------
def test_f14_duplicate_pose_timestamp_is_ambiguous():
    poses = [_pose(0.0), _pose(PERIOD, x=1.0), _pose(PERIOD, x=2.0), _pose(2 * PERIOD, x=3.0)]
    r = align_image_to_pose(PERIOD, poses)
    assert r.status == STATUS_REJECTED
    assert r.rejection_reason == H8_ALIGNMENT_DUPLICATE_TIMESTAMP_AMBIGUOUS


# --- fixture 15: out-of-order timestamps -------------------------------------------------------------
def test_f15_out_of_order_timestamps_rejected():
    poses = [_pose(0.0), _pose(2 * PERIOD), _pose(PERIOD)]
    r = align_image_to_pose(1.5 * PERIOD, poses)
    assert r.rejection_reason == H8_ALIGNMENT_TIMESTAMP_ORDER_INVALID


# --- fixture 16: clock reset -----------------------------------------------------------------------
def test_f16_clock_reset_rejected():
    poses = [_pose(0.0), _pose(100.0), _pose(1.0)]
    r = align_image_to_pose(50.0, poses)
    assert r.rejection_reason == H8_ALIGNMENT_CLOCK_RESET


# --- fixture 17: incompatible frame ids ---------------------------------------------------------------
def test_f17_frame_id_mismatch_rejected():
    poses = _series()
    r = align_image_to_pose(1.5 * PERIOD, poses, expected_pose_frame="map")
    assert r.rejection_reason == H8_ALIGNMENT_FRAME_MISMATCH


def test_f17b_child_frame_mismatch_rejected():
    poses = _series()
    r = align_image_to_pose(1.5 * PERIOD, poses, expected_child_frame="base_link")
    assert r.rejection_reason == H8_ALIGNMENT_FRAME_MISMATCH


# --- fixture 18: invalid quaternion ---------------------------------------------------------------------
def test_f18_invalid_quaternion_rejected():
    poses = [_pose(0.0), Pose(stamp=PERIOD, x=0.0, y=0.0, qx=0.0, qy=0.0, qz=0.0, qw=0.0)]
    r = align_image_to_pose(PERIOD / 2.0, poses)
    assert r.rejection_reason == H8_ALIGNMENT_QUATERNION_INVALID


# --- fixture 19: NaN position ------------------------------------------------------------------------
def test_f19_nan_position_rejected():
    poses = [_pose(0.0), _pose(PERIOD, x=float("nan"))]
    r = align_image_to_pose(PERIOD / 2.0, poses)
    assert r.rejection_reason == H8_ALIGNMENT_NON_FINITE


# --- fixture 20: unresolved transform ------------------------------------------------------------------
def test_f20_unresolved_transform_rejected():
    poses = _series()
    r = align_image_to_pose(1.5 * PERIOD, poses, transform_resolved=False)
    assert r.rejection_reason == H8_ALIGNMENT_TRANSFORM_UNRESOLVED


# --- additional guards ------------------------------------------------------------------------------
def test_missing_image_stamp_rejected():
    assert align_image_to_pose(None, _series()).rejection_reason == H8_ALIGNMENT_IMAGE_STAMP_MISSING


def test_empty_pose_series_rejected():
    assert align_image_to_pose(0.0, []).rejection_reason == H8_ALIGNMENT_POSE_MISSING


def test_wall_clock_image_refused_not_converted():
    """A wall-clock image stamp must be refused, never silently converted to sim time."""
    r = align_image_to_pose(1.78e9, _series(), image_clock=CLOCK_WALL)
    assert r.rejection_reason == H8_TIME_DOMAIN_MISMATCH


def test_mixed_clock_pose_series_refused():
    poses = [_pose(0.0, clock=AUTHORITATIVE_CLOCK), _pose(PERIOD, clock=CLOCK_WALL)]
    assert align_image_to_pose(PERIOD / 2, poses).rejection_reason == H8_TIME_DOMAIN_MISMATCH


def test_all_rejection_codes_are_registered():
    for code in (H8_ALIGNMENT_GAP_EXCEEDED, H8_ALIGNMENT_NO_BRACKETING_POSE,
                 H8_ALIGNMENT_CLOCK_RESET, H8_TIME_DOMAIN_MISMATCH,
                 H8_ALIGNMENT_QUATERNION_INVALID, H8_ALIGNMENT_NON_FINITE):
        assert is_valid_code(code)


def test_yaw_quaternion_roundtrip():
    for deg in (-179.0, -90.0, 0.0, 45.0, 179.0):
        q = quaternion_from_yaw(math.radians(deg))
        assert yaw_from_quaternion(*q) == pytest.approx(math.radians(deg), abs=1e-9)


def test_summarise_reports_rejections():
    poses = _series()
    stamps = [poses[0].stamp - 1.0, 1.5 * PERIOD, poses[-1].stamp + 1.0]
    out = summarise(align_series(stamps, poses))
    assert out["n_total"] == 3
    assert out["n_aligned"] == 1
    assert out["n_rejected"] == 2
    assert H8_ALIGNMENT_EXTRAPOLATION_REFUSED in out["rejection_reasons"]


def test_tolerance_derivation_is_evidence_backed():
    d = tolerance_derivation()
    assert d["authoritative_clock"] == AUTHORITATIVE_CLOCK == "sim"
    assert d["alignment_tolerance_s"] == ALIGNMENT_TOLERANCE_S == 0.025
    # Above the measured p99 residual, below the measured publish period.
    assert d["observed_residual_p99_s"] < d["alignment_tolerance_s"] < d["observed_publish_period_s"]
    assert d["maximum_position_interpolation_error_m"] == pytest.approx(0.005)
    assert d["maximum_yaw_interpolation_error_deg"] == pytest.approx(0.5729578, abs=1e-6)
    assert d["status"] == "PROPOSED_DATASET_ACCEPTANCE_TOLERANCE"
    assert d["unresolved"], "the 1280x720 re-measurement must remain flagged as unresolved"


def test_interpolation_error_bound_holds_empirically():
    """Worst-case interpolation error at the locked limits must match the documented bound."""
    poses = [_pose(0.0, x=0.0, yaw=0.0),
             _pose(2 * ALIGNMENT_TOLERANCE_S, x=0.2 * 2 * ALIGNMENT_TOLERANCE_S,
                   yaw=0.4 * 2 * ALIGNMENT_TOLERANCE_S)]
    r = align_image_to_pose(ALIGNMENT_TOLERANCE_S, poses)
    assert r.status == STATUS_OK
    assert abs(r.x - 0.2 * ALIGNMENT_TOLERANCE_S) <= MAX_POSITION_INTERPOLATION_ERROR_M
    assert math.degrees(abs(r.yaw_rad - 0.4 * ALIGNMENT_TOLERANCE_S)) \
        <= MAX_YAW_INTERPOLATION_ERROR_DEG
