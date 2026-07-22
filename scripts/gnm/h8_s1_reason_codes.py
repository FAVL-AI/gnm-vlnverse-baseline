"""scripts/gnm/h8_s1_reason_codes.py

H8-S1 — DETERMINISTIC REASON-CODE TAXONOMY.

Every fail-closed rejection raised by the H8-S1 controls (time alignment, episode-manifest
validation, goal-registry resolution, duplicate screening, dataset-builder ordering) is reported as
one of the codes below. Codes are stable identifiers: they are written into reports, asserted by
tests, and read by downstream tooling. Renaming a code is a breaking change.

Scope note: these codes describe *validation* outcomes only. They carry no trust or authentication
meaning; that boundary belongs to the H8 G2 envelope work and is deliberately not touched here.

Naming follows the existing repository convention of an `H8_` prefix and an
`H8_<SUBJECT>_<CONDITION>` body.
"""
from __future__ import annotations

from enum import Enum


class ReasonCodeStatus(str, Enum):
    """Lifecycle and test-coverage status for one declared H8-S1 reason code."""

    ACTIVE_REACHABLE = "ACTIVE_REACHABLE"
    RESERVED_NOT_ACTIVE = "RESERVED_NOT_ACTIVE"
    DEPRECATED_UNUSED = "DEPRECATED_UNUSED"
    DEFERRED_TO_LATER_IMPLEMENTATION = "DEFERRED_TO_LATER_IMPLEMENTATION"


# --- goal identity ---------------------------------------------------------------------------
H8_GOAL_ID_PLACEHOLDER = "H8_GOAL_ID_PLACEHOLDER"
H8_GOAL_ID_MISSING = "H8_GOAL_ID_MISSING"
H8_GOAL_NOT_FOUND = "H8_GOAL_NOT_FOUND"
H8_GOAL_AMBIGUOUS = "H8_GOAL_AMBIGUOUS"
H8_GOAL_HASH_MISSING = "H8_GOAL_HASH_MISSING"
H8_GOAL_HASH_MISMATCH = "H8_GOAL_HASH_MISMATCH"
H8_GOAL_SCENE_MISMATCH = "H8_GOAL_SCENE_MISMATCH"
H8_GOAL_MAP_MISMATCH = "H8_GOAL_MAP_MISMATCH"
H8_GOAL_SPLIT_MISMATCH = "H8_GOAL_SPLIT_MISMATCH"
H8_GOAL_POSE_MISMATCH = "H8_GOAL_POSE_MISMATCH"
H8_GOAL_CAMERA_MISMATCH = "H8_GOAL_CAMERA_MISMATCH"
H8_GOAL_RESOLUTION_MISMATCH = "H8_GOAL_RESOLUTION_MISMATCH"
H8_GOAL_IMAGE_CROSS_SPLIT_REUSE = "H8_GOAL_IMAGE_CROSS_SPLIT_REUSE"

# --- controller identity ---------------------------------------------------------------------
H8_CONTROLLER_MODE_UNKNOWN = "H8_CONTROLLER_MODE_UNKNOWN"
H8_CONTROLLER_MODE_MISSING = "H8_CONTROLLER_MODE_MISSING"
H8_CONTROLLER_POLICY_MISMATCH = "H8_CONTROLLER_POLICY_MISMATCH"
H8_CONTROLLER_CHECKPOINT_MISSING = "H8_CONTROLLER_CHECKPOINT_MISSING"

# --- acquisition configuration ----------------------------------------------------------------
H8_ACQUISITION_RESOLUTION_MISMATCH = "H8_ACQUISITION_RESOLUTION_MISMATCH"
H8_ACQUISITION_RESOLUTION_MISSING = "H8_ACQUISITION_RESOLUTION_MISSING"
H8_ACQUISITION_RESOLUTION_MALFORMED = "H8_ACQUISITION_RESOLUTION_MALFORMED"
H8_ACQUISITION_ENCODING_MISMATCH = "H8_ACQUISITION_ENCODING_MISMATCH"
H8_CAMERA_MOUNT_UNSUPPORTED = "H8_CAMERA_MOUNT_UNSUPPORTED"
H8_CAMERA_IDENTITY_MISSING = "H8_CAMERA_IDENTITY_MISSING"

# --- pose identity ------------------------------------------------------------------------------
H8_START_POSE_DECLARED_MISSING = "H8_START_POSE_DECLARED_MISSING"
H8_START_POSE_OBSERVED_MISSING = "H8_START_POSE_OBSERVED_MISSING"
H8_START_POSE_TOLERANCE_EXCEEDED = "H8_START_POSE_TOLERANCE_EXCEEDED"
H8_START_POSE_FRAME_MISMATCH = "H8_START_POSE_FRAME_MISMATCH"

# --- scene / map identity -----------------------------------------------------------------------
H8_SCENE_DIGEST_MISSING = "H8_SCENE_DIGEST_MISSING"
H8_SCENE_IDENTITY_FAILED = "H8_SCENE_IDENTITY_FAILED"
H8_MAP_VERSION_MISSING = "H8_MAP_VERSION_MISSING"
H8_NAVMESH_VERSION_MISSING = "H8_NAVMESH_VERSION_MISSING"

# --- success criterion --------------------------------------------------------------------------
H8_SUCCESS_RADIUS_MISSING = "H8_SUCCESS_RADIUS_MISSING"
H8_SUCCESS_RADIUS_MISMATCH = "H8_SUCCESS_RADIUS_MISMATCH"
H8_SUCCESS_CRITERION_NOT_PREREGISTERED = "H8_SUCCESS_CRITERION_NOT_PREREGISTERED"

# --- split / route independence -----------------------------------------------------------------
H8_SPLIT_UNKNOWN = "H8_SPLIT_UNKNOWN"
H8_ROUTE_SPLIT_DUPLICATE = "H8_ROUTE_SPLIT_DUPLICATE"
H8_RETRY_NOT_INDEPENDENT = "H8_RETRY_NOT_INDEPENDENT"

# --- authorisation ------------------------------------------------------------------------------
H8_CAPTURE_AUTHORISATION_MISSING = "H8_CAPTURE_AUTHORISATION_MISSING"

# --- time domain / alignment ----------------------------------------------------------------------
H8_TIME_DOMAIN_MISMATCH = "H8_TIME_DOMAIN_MISMATCH"
H8_ALIGNMENT_IMAGE_STAMP_MISSING = "H8_ALIGNMENT_IMAGE_STAMP_MISSING"
H8_ALIGNMENT_POSE_MISSING = "H8_ALIGNMENT_POSE_MISSING"
H8_ALIGNMENT_NO_BRACKETING_POSE = "H8_ALIGNMENT_NO_BRACKETING_POSE"
H8_ALIGNMENT_GAP_EXCEEDED = "H8_ALIGNMENT_GAP_EXCEEDED"
H8_ALIGNMENT_EXTRAPOLATION_REFUSED = "H8_ALIGNMENT_EXTRAPOLATION_REFUSED"
H8_ALIGNMENT_FRAME_MISMATCH = "H8_ALIGNMENT_FRAME_MISMATCH"
H8_ALIGNMENT_TIMESTAMP_ORDER_INVALID = "H8_ALIGNMENT_TIMESTAMP_ORDER_INVALID"
H8_ALIGNMENT_DUPLICATE_TIMESTAMP_AMBIGUOUS = "H8_ALIGNMENT_DUPLICATE_TIMESTAMP_AMBIGUOUS"
H8_ALIGNMENT_QUATERNION_INVALID = "H8_ALIGNMENT_QUATERNION_INVALID"
H8_ALIGNMENT_NON_FINITE = "H8_ALIGNMENT_NON_FINITE"
H8_ALIGNMENT_CLOCK_RESET = "H8_ALIGNMENT_CLOCK_RESET"
H8_ALIGNMENT_TRANSFORM_UNRESOLVED = "H8_ALIGNMENT_TRANSFORM_UNRESOLVED"

# --- metric availability --------------------------------------------------------------------------
#: DEPRECATED_UNUSED (H8-S1R, closing H8-S1REV-F-002). Never raised. It is redundant with the
#: specific `NOT_COMPUTED_*` readiness states in h8_episode_validator, each of which names the
#: missing input exactly (goal, success radius, reference path, navmesh, contacts, stop event,
#: latency timestamps, alignment, untrusted metadata). A generic "some input was unavailable" code
#: would be strictly less informative, so no code path is added to make it fire. Retained as a
#: declaration only, for compatibility with any external reader of the taxonomy; it is excluded
#: from the ACTIVE_REACHABLE coverage KPI. Recommend removal at the next taxonomy revision.
H8_METRIC_INPUT_UNAVAILABLE = "H8_METRIC_INPUT_UNAVAILABLE"

# --- manifest structure -----------------------------------------------------------------------------
H8_MANIFEST_SCHEMA_INVALID = "H8_MANIFEST_SCHEMA_INVALID"
H8_MANIFEST_VERSION_UNSUPPORTED = "H8_MANIFEST_VERSION_UNSUPPORTED"

# --- contact telemetry ------------------------------------------------------------------------------
H8_CONTACT_TELEMETRY_UNAVAILABLE = "H8_CONTACT_TELEMETRY_UNAVAILABLE"

#: DEFERRED_TO_LATER_IMPLEMENTATION (H8-S1R). The current fail-closed control reports
#: H8_CONTACT_TELEMETRY_UNAVAILABLE and marks collision metrics NOT_COMPUTED when no detector
#: evidence exists. This more specific declaration is retained for a later detector-aware schema
#: that can distinguish an explicit zero-collision claim from absent detector telemetry.
H8_CONTACT_TELEMETRY_ZERO_WITHOUT_DETECTOR = "H8_CONTACT_TELEMETRY_ZERO_WITHOUT_DETECTOR"


ALL_CODES: tuple[str, ...] = tuple(
    v for k, v in sorted(globals().items())
    if k.startswith("H8_") and isinstance(v, str)
)


# Every declared code is active by default. The two documented exceptions are overridden below.
# Constructing the map from ALL_CODES prevents accidental omission when the taxonomy changes.
REASON_CODE_STATUS: dict[str, ReasonCodeStatus] = {
    code: ReasonCodeStatus.ACTIVE_REACHABLE
    for code in ALL_CODES
}
REASON_CODE_STATUS[H8_METRIC_INPUT_UNAVAILABLE] = (
    ReasonCodeStatus.DEPRECATED_UNUSED
)
REASON_CODE_STATUS[H8_CONTACT_TELEMETRY_ZERO_WITHOUT_DETECTOR] = (
    ReasonCodeStatus.DEFERRED_TO_LATER_IMPLEMENTATION
)

ACTIVE_REASON_CODES: frozenset[str] = frozenset(
    code
    for code, status in REASON_CODE_STATUS.items()
    if status is ReasonCodeStatus.ACTIVE_REACHABLE
)

INACTIVE_REASON_CODES: frozenset[str] = frozenset(
    code
    for code, status in REASON_CODE_STATUS.items()
    if status is not ReasonCodeStatus.ACTIVE_REACHABLE
)

REASON_CODE_STATUS_COUNTS: dict[ReasonCodeStatus, int] = {
    status: sum(
        assigned_status is status
        for assigned_status in REASON_CODE_STATUS.values()
    )
    for status in ReasonCodeStatus
}


def is_valid_code(code: str) -> bool:
    """True iff `code` is a registered H8-S1 reason code."""
    return code in ALL_CODES
