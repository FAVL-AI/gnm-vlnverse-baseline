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
H8_METRIC_INPUT_UNAVAILABLE = "H8_METRIC_INPUT_UNAVAILABLE"

# --- manifest structure -----------------------------------------------------------------------------
H8_MANIFEST_SCHEMA_INVALID = "H8_MANIFEST_SCHEMA_INVALID"
H8_MANIFEST_VERSION_UNSUPPORTED = "H8_MANIFEST_VERSION_UNSUPPORTED"

# --- contact telemetry ------------------------------------------------------------------------------
H8_CONTACT_TELEMETRY_UNAVAILABLE = "H8_CONTACT_TELEMETRY_UNAVAILABLE"
H8_CONTACT_TELEMETRY_ZERO_WITHOUT_DETECTOR = "H8_CONTACT_TELEMETRY_ZERO_WITHOUT_DETECTOR"


ALL_CODES: tuple[str, ...] = tuple(
    v for k, v in sorted(globals().items())
    if k.startswith("H8_") and isinstance(v, str)
)


def is_valid_code(code: str) -> bool:
    """True iff `code` is a registered H8-S1 reason code."""
    return code in ALL_CODES
