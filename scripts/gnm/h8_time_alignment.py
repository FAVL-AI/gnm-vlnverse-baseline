"""scripts/gnm/h8_time_alignment.py

H8-S1 — DETERMINISTIC IMAGE-TO-POSE TIME ALIGNMENT.

Closes the blocker recorded by the 2026-07-22 forensic audit: rosbag messages are stamped in two
different clocks and no verified alignment procedure existed, so per-frame supervision could not be
asserted to pair the right image with the right pose.

AUTHORITATIVE CLOCK
    The ROS message **header stamp** is authoritative for alignment, in every context.
    Measured over eight historical bags (H8-S1 timing characterisation):
      * image and odometry header stamps are simulation time - monotonic, starting near zero, and
        contained within the /clock span of the same bag;
      * the rosbag *record* timestamp is wall-clock Unix epoch and ran 5.6x to 146.9x slower than
        simulation time, so it is NOT usable for alignment and is retained only for provenance.
    Mixing the two domains is refused (H8_TIME_DOMAIN_MISMATCH), never silently converted.

INTERPOLATION
    Position: linear between the bracketing poses.
    Orientation: shortest-path spherical linear interpolation (slerp) on the unit quaternion, so a
    yaw crossing +/-pi interpolates the short way round rather than sweeping backwards through zero.

NO EXTRAPOLATION
    A frame outside the pose series is refused, not extrapolated. In the historical bags this
    affects 0.09-0.27% of frames, all at the episode edges.

This module performs validation only. It captures nothing, launches nothing, and reads no live
topic.
"""
from __future__ import annotations

import bisect
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Sequence

from h8_s1_reason_codes import (
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
)

# --------------------------------------------------------------------------------------------
# Clock domains
# --------------------------------------------------------------------------------------------

CLOCK_SIM = "sim"
CLOCK_WALL = "wall"
CLOCK_MONOTONIC = "monotonic"
CLOCK_DOMAINS = (CLOCK_SIM, CLOCK_WALL, CLOCK_MONOTONIC)

#: The clock that alignment is performed in, for every context.
AUTHORITATIVE_CLOCK = CLOCK_SIM

# --------------------------------------------------------------------------------------------
# Tolerance — derived, not chosen. See docs/research/H8_TIME_ALIGNMENT_POLICY.md
# --------------------------------------------------------------------------------------------

#: Locked robot velocity limits (episode metadata `cl_limits`, unchanged since H2).
MAX_LINEAR_SPEED_MS = 0.2
MAX_ANGULAR_SPEED_RADS = 0.4

#: Observed publish period of both /camera/image_raw and /odom header stamps (20 Hz, sim time).
OBSERVED_PUBLISH_PERIOD_S = 0.05
#: Observed image-to-nearest-pose residual, p99 over eight bags: exactly one 60 Hz physics step.
OBSERVED_RESIDUAL_P99_S = 1.0 / 60.0

#: Dataset-acceptance tolerance. Above the observed p99 residual, below the publish period.
ALIGNMENT_TOLERANCE_S = 0.025
#: Wider tolerance permitted for diagnostic characterisation only; never for dataset admission.
DIAGNOSTIC_TOLERANCE_S = 0.05

#: Worst-case interpolation error implied by ALIGNMENT_TOLERANCE_S at the locked velocity limits.
MAX_POSITION_INTERPOLATION_ERROR_M = ALIGNMENT_TOLERANCE_S * MAX_LINEAR_SPEED_MS
MAX_YAW_INTERPOLATION_ERROR_DEG = math.degrees(ALIGNMENT_TOLERANCE_S * MAX_ANGULAR_SPEED_RADS)

ALIGNMENT_POLICY_VERSION = "h8-alignment/1.0.0"

STATUS_OK = "OK"
STATUS_REJECTED = "REJECTED"


# --------------------------------------------------------------------------------------------
# Data types
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Pose:
    """A time-stamped pose. `stamp` is in the clock named by `clock`."""

    stamp: float
    x: float
    y: float
    z: float = 0.0
    qx: float = 0.0
    qy: float = 0.0
    qz: float = 0.0
    qw: float = 1.0
    frame_id: str = "odom"
    child_frame_id: str = "base_footprint"
    clock: str = CLOCK_SIM


@dataclass
class AlignmentResult:
    """Per-frame alignment record. Every field required by the H8-S1 gate is present."""

    image_stamp: float | None = None
    image_frame_id: str | None = None
    pose_stamp_before: float | None = None
    pose_stamp_after: float | None = None
    alignment_method: str = "linear_position_slerp_orientation"
    positional_interpolation: str = "linear"
    angular_interpolation: str = "slerp_shortest_path"
    max_timestamp_gap_s: float = ALIGNMENT_TOLERANCE_S
    residual_s: float | None = None
    pose_source: str | None = None
    coordinate_frame: str | None = None
    child_frame: str | None = None
    clock_domain: str = AUTHORITATIVE_CLOCK
    policy_version: str = ALIGNMENT_POLICY_VERSION
    status: str = STATUS_REJECTED
    rejection_reason: str | None = None
    x: float | None = None
    y: float | None = None
    z: float | None = None
    yaw_rad: float | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------------------------
# Quaternion helpers
# --------------------------------------------------------------------------------------------


def _finite(*vals: float) -> bool:
    return all(isinstance(v, (int, float)) and math.isfinite(v) for v in vals)


def quaternion_is_valid(qx: float, qy: float, qz: float, qw: float, tol: float = 1e-3) -> bool:
    """A quaternion is usable iff it is finite and of unit norm within `tol`."""
    if not _finite(qx, qy, qz, qw):
        return False
    return abs(math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw) - 1.0) <= tol


def yaw_from_quaternion(qx: float, qy: float, qz: float, qw: float) -> float:
    """Yaw (Z) from a unit quaternion, in radians on (-pi, pi]."""
    siny = 2.0 * (qw * qz + qx * qy)
    cosy = 1.0 - 2.0 * (qy * qy + qz * qz)
    return math.atan2(siny, cosy)


def quaternion_from_yaw(yaw: float) -> tuple[float, float, float, float]:
    """Unit quaternion (x, y, z, w) for a pure-yaw rotation."""
    return (0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0))


def slerp(
    q0: Sequence[float], q1: Sequence[float], t: float, eps: float = 1e-8
) -> tuple[float, float, float, float]:
    """Shortest-path spherical linear interpolation between two unit quaternions.

    The sign flip on a negative dot product is what makes a +/-pi yaw crossing interpolate the
    short way round; without it the interpolation sweeps the long way and produces a pose that the
    robot never occupied.
    """
    x0, y0, z0, w0 = q0
    x1, y1, z1, w1 = q1
    dot = x0 * x1 + y0 * y1 + z0 * z1 + w0 * w1
    if dot < 0.0:  # take the short arc
        x1, y1, z1, w1, dot = -x1, -y1, -z1, -w1, -dot
    if dot > 1.0 - eps:  # nearly parallel: linear interpolation is numerically safer
        x = x0 + t * (x1 - x0)
        y = y0 + t * (y1 - y0)
        z = z0 + t * (z1 - z0)
        w = w0 + t * (w1 - w0)
    else:
        theta = math.acos(max(-1.0, min(1.0, dot)))
        s = math.sin(theta)
        a, b = math.sin((1.0 - t) * theta) / s, math.sin(t * theta) / s
        x, y, z, w = a * x0 + b * x1, a * y0 + b * y1, a * z0 + b * z1, a * w0 + b * w1
    n = math.sqrt(x * x + y * y + z * z + w * w)
    if n < eps:
        return (0.0, 0.0, 0.0, 1.0)
    return (x / n, y / n, z / n, w / n)


# --------------------------------------------------------------------------------------------
# Pose series
# --------------------------------------------------------------------------------------------


def validate_pose_series(poses: Sequence[Pose]) -> str | None:
    """Return a reason code if the series cannot be used for alignment, else None."""
    if not poses:
        return H8_ALIGNMENT_POSE_MISSING
    clocks = {p.clock for p in poses}
    if len(clocks) > 1:
        return H8_TIME_DOMAIN_MISMATCH
    stamps = [p.stamp for p in poses]
    if not _finite(*stamps):
        return H8_ALIGNMENT_NON_FINITE
    for i in range(1, len(stamps)):
        if stamps[i] < stamps[i - 1]:
            # A large backward jump is a clock reset; a small one is simply out of order.
            if stamps[i - 1] - stamps[i] > 1.0:
                return H8_ALIGNMENT_CLOCK_RESET
            return H8_ALIGNMENT_TIMESTAMP_ORDER_INVALID
    for p in poses:
        if not _finite(p.x, p.y, p.z):
            return H8_ALIGNMENT_NON_FINITE
        if not quaternion_is_valid(p.qx, p.qy, p.qz, p.qw):
            return H8_ALIGNMENT_QUATERNION_INVALID
    return None


# --------------------------------------------------------------------------------------------
# Alignment
# --------------------------------------------------------------------------------------------


def align_image_to_pose(
    image_stamp: float | None,
    poses: Sequence[Pose],
    *,
    image_frame_id: str | None = None,
    image_clock: str = CLOCK_SIM,
    tolerance_s: float = ALIGNMENT_TOLERANCE_S,
    expected_pose_frame: str | None = None,
    expected_child_frame: str | None = None,
    pose_source: str = "/odom",
    transform_resolved: bool = True,
) -> AlignmentResult:
    """Align one image timestamp to an interpolated pose. Fail-closed.

    Returns an :class:`AlignmentResult` whose ``status`` is ``OK`` only when a bracketing pose pair
    exists within ``tolerance_s`` and every validity check passes. Extrapolation is never performed.
    """
    r = AlignmentResult(
        image_stamp=image_stamp,
        image_frame_id=image_frame_id,
        max_timestamp_gap_s=tolerance_s,
        pose_source=pose_source,
        clock_domain=image_clock,
    )

    def reject(code: str, **detail: Any) -> AlignmentResult:
        r.status = STATUS_REJECTED
        r.rejection_reason = code
        r.detail.update(detail)
        return r

    if image_stamp is None or not _finite(image_stamp):
        return reject(H8_ALIGNMENT_IMAGE_STAMP_MISSING)
    if image_clock != AUTHORITATIVE_CLOCK:
        return reject(H8_TIME_DOMAIN_MISMATCH, image_clock=image_clock,
                      authoritative=AUTHORITATIVE_CLOCK)
    if not transform_resolved:
        return reject(H8_ALIGNMENT_TRANSFORM_UNRESOLVED)

    bad = validate_pose_series(poses)
    if bad:
        return reject(bad)

    if poses and poses[0].clock != image_clock:
        return reject(H8_TIME_DOMAIN_MISMATCH, pose_clock=poses[0].clock, image_clock=image_clock)

    if expected_pose_frame is not None and poses[0].frame_id != expected_pose_frame:
        return reject(H8_ALIGNMENT_FRAME_MISMATCH, pose_frame=poses[0].frame_id,
                      expected=expected_pose_frame)
    if expected_child_frame is not None and poses[0].child_frame_id != expected_child_frame:
        return reject(H8_ALIGNMENT_FRAME_MISMATCH, child_frame=poses[0].child_frame_id,
                      expected=expected_child_frame)

    r.coordinate_frame = poses[0].frame_id
    r.child_frame = poses[0].child_frame_id

    stamps = [p.stamp for p in poses]
    i = bisect.bisect_left(stamps, image_stamp)

    # Exact hit on a sample.
    if i < len(stamps) and stamps[i] == image_stamp:
        dupes = sum(1 for s in stamps if s == image_stamp)
        if dupes > 1:
            return reject(H8_ALIGNMENT_DUPLICATE_TIMESTAMP_AMBIGUOUS, duplicates=dupes)
        p = poses[i]
        r.pose_stamp_before = r.pose_stamp_after = p.stamp
        r.residual_s = 0.0
        r.x, r.y, r.z = p.x, p.y, p.z
        r.yaw_rad = yaw_from_quaternion(p.qx, p.qy, p.qz, p.qw)
        r.alignment_method = "exact_sample"
        r.status = STATUS_OK
        return r

    # Outside the series: refuse rather than extrapolate.
    if i == 0 or i >= len(stamps):
        nearest = stamps[0] if i == 0 else stamps[-1]
        gap = abs(image_stamp - nearest)
        code = (H8_ALIGNMENT_NO_BRACKETING_POSE if gap <= tolerance_s
                else H8_ALIGNMENT_EXTRAPOLATION_REFUSED)
        return reject(code, nearest_pose_stamp=nearest, gap_s=round(gap, 9))

    p0, p1 = poses[i - 1], poses[i]
    r.pose_stamp_before, r.pose_stamp_after = p0.stamp, p1.stamp
    span = p1.stamp - p0.stamp
    if span <= 0:
        return reject(H8_ALIGNMENT_DUPLICATE_TIMESTAMP_AMBIGUOUS, span_s=span)

    residual = min(image_stamp - p0.stamp, p1.stamp - image_stamp)
    r.residual_s = round(residual, 9)
    if residual > tolerance_s:
        return reject(H8_ALIGNMENT_GAP_EXCEEDED, residual_s=round(residual, 9),
                      tolerance_s=tolerance_s)

    t = (image_stamp - p0.stamp) / span
    x = p0.x + t * (p1.x - p0.x)
    y = p0.y + t * (p1.y - p0.y)
    z = p0.z + t * (p1.z - p0.z)
    qx, qy, qz, qw = slerp((p0.qx, p0.qy, p0.qz, p0.qw), (p1.qx, p1.qy, p1.qz, p1.qw), t)
    yaw = yaw_from_quaternion(qx, qy, qz, qw)
    if not _finite(x, y, z, yaw):
        return reject(H8_ALIGNMENT_NON_FINITE)

    r.x, r.y, r.z, r.yaw_rad = x, y, z, yaw
    r.status = STATUS_OK
    return r


def align_series(
    image_stamps: Iterable[float],
    poses: Sequence[Pose],
    **kwargs: Any,
) -> list[AlignmentResult]:
    """Align a whole image series. Returns one result per image, in input order."""
    return [align_image_to_pose(s, poses, **kwargs) for s in image_stamps]


def summarise(results: Sequence[AlignmentResult]) -> dict[str, Any]:
    """Aggregate alignment results into a report block."""
    ok = [r for r in results if r.status == STATUS_OK]
    res = sorted(r.residual_s for r in ok if r.residual_s is not None)
    reasons: dict[str, int] = {}
    for r in results:
        if r.rejection_reason:
            reasons[r.rejection_reason] = reasons.get(r.rejection_reason, 0) + 1

    def pct(p: float) -> float | None:
        if not res:
            return None
        return round(res[min(len(res) - 1, int(round(p * (len(res) - 1))))], 9)

    return {
        "policy_version": ALIGNMENT_POLICY_VERSION,
        "clock_domain": AUTHORITATIVE_CLOCK,
        "tolerance_s": kwargs_tolerance(results),
        "n_total": len(results),
        "n_aligned": len(ok),
        "n_rejected": len(results) - len(ok),
        "aligned_fraction": round(len(ok) / len(results), 6) if results else 0.0,
        "residual_p50_s": pct(0.5),
        "residual_p95_s": pct(0.95),
        "residual_p99_s": pct(0.99),
        "residual_max_s": round(res[-1], 9) if res else None,
        "rejection_reasons": dict(sorted(reasons.items())),
    }


def kwargs_tolerance(results: Sequence[AlignmentResult]) -> float:
    """The tolerance actually applied to a result set."""
    return results[0].max_timestamp_gap_s if results else ALIGNMENT_TOLERANCE_S


def tolerance_derivation() -> dict[str, Any]:
    """The evidence behind ALIGNMENT_TOLERANCE_S, for inclusion in reports."""
    return {
        "policy_version": ALIGNMENT_POLICY_VERSION,
        "authoritative_clock": AUTHORITATIVE_CLOCK,
        "observed_publish_period_s": OBSERVED_PUBLISH_PERIOD_S,
        "observed_publish_rate_hz": round(1.0 / OBSERVED_PUBLISH_PERIOD_S, 3),
        "observed_residual_p99_s": round(OBSERVED_RESIDUAL_P99_S, 9),
        "alignment_tolerance_s": ALIGNMENT_TOLERANCE_S,
        "alignment_tolerance_ms": ALIGNMENT_TOLERANCE_S * 1000.0,
        "diagnostic_tolerance_s": DIAGNOSTIC_TOLERANCE_S,
        "max_linear_speed_ms": MAX_LINEAR_SPEED_MS,
        "max_angular_speed_rads": MAX_ANGULAR_SPEED_RADS,
        "maximum_position_interpolation_error_m": round(MAX_POSITION_INTERPOLATION_ERROR_M, 6),
        "maximum_yaw_interpolation_error_deg": round(MAX_YAW_INTERPOLATION_ERROR_DEG, 6),
        "rationale": (
            "Tolerance sits above the measured p99 image-to-nearest-pose residual "
            "(1/60 s, one physics step) and below the 0.05 s publish period, so a bracketing pose "
            "pair is available for every interior frame while a genuinely stale pose is refused. "
            "At the locked velocity limits the implied worst-case interpolation error is "
            f"{MAX_POSITION_INTERPOLATION_ERROR_M * 1000:.1f} mm and "
            f"{MAX_YAW_INTERPOLATION_ERROR_DEG:.2f} deg, i.e. "
            f"{100 * MAX_POSITION_INTERPOLATION_ERROR_M / 0.5:.1f}% of the tau = 0.50 m success radius."
        ),
        "status": "PROPOSED_DATASET_ACCEPTANCE_TOLERANCE",
        "unresolved": (
            "Derived from 640x480 / 20 Hz historical simulation bags. It must be re-measured at the "
            "canonical 1280x720 acquisition resolution during Session B before it is treated as "
            "final; the publish period may change and the tolerance follows it."
        ),
    }
