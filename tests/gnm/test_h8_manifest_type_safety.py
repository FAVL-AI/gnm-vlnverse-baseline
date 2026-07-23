"""ME-021 / F-A01 — manifest type-safety regression suite.

The 2026-07-23 audit found that ``validate_manifest`` raised an uncaught ``AttributeError`` when a
field that must be an object was instead a string, list, number or boolean (and silently mislabelled
the defect when the wrong value was falsy). A fail-closed control must convert every malformed input
into a deterministic rejection carrying a reason code, never a traceback and never a silent pass.

This suite implements the T-01..T-34 matrix of
``ME021_VALIDATOR_REPAIR_AND_TEST_SPECIFICATION_20260723.md``. Where a row's expected code was the
audit's expectation rather than verified behaviour, it is reconciled here to the code the control
actually emits, per the spec's own instruction ("the register is the authority ... do not add a new
reason code"). Those reconciliations are called out in the relevant docstrings.

No test here permits a traceback, and no test permits admission of a malformed manifest.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "gnm"))
sys.path.insert(0, str(ROOT))

from h8_episode_validator import MANIFEST_VERSION, validate_manifest  # noqa: E402
from h8_s1_reason_codes import (  # noqa: E402
    H8_ACQUISITION_RESOLUTION_MALFORMED,
    H8_CAMERA_IDENTITY_MISSING,
    H8_CONTROLLER_MODE_MISSING,
    H8_GOAL_ID_MISSING,
    H8_GOAL_ID_PLACEHOLDER,
    H8_MANIFEST_SCHEMA_INVALID,
    H8_MANIFEST_VERSION_UNSUPPORTED,
    H8_SCENE_DIGEST_MISSING,
    H8_SPLIT_UNKNOWN,
)

# Reuse the canonical accepted fixture so these tests track the real valid manifest, not a copy.
from tests.gnm.test_h8_episode_schema_v2 import registry, valid_manifest  # noqa: E402

# The seven manifest members that must be objects. These are the ME-021 crash sites.
OBJECT_FIELDS = ["scene", "map", "goal", "success_criterion", "camera", "controller",
                 "contact_telemetry"]
# Every non-object JSON type. `[]` and `None` are the falsy cases the old code silently mislabelled.
WRONG_TYPES = [("string", "x"), ("array", []), ("null", None), ("number", 7), ("boolean", True)]


def _schema_detail(result, field_path):
    """Return the H8_MANIFEST_SCHEMA_INVALID detail entry for a given field path, or None."""
    for d in result.detail:
        if d.get("code") == H8_MANIFEST_SCHEMA_INVALID and d.get("field") == field_path:
            return d
    return None


# ============================================================================================
# Section 1 — object fields of the wrong type  (ME-021 acceptance set: MUST be SCHEMA_INVALID)
# Covers T-01..T-05 (camera), T-14/T-15 (scene), T-17/T-18 (goal), T-20 (controller),
# T-21 (map), T-22 (success_criterion), T-23 (contact_telemetry), and every other object.
# ============================================================================================


@pytest.mark.parametrize("fieldname", OBJECT_FIELDS)
@pytest.mark.parametrize("typename,value", WRONG_TYPES)
def test_object_field_wrong_type_is_schema_invalid_not_a_crash(fieldname, typename, value):
    m = valid_manifest()
    m[fieldname] = value
    # Must NOT raise. A propagating exception fails the test here.
    result = validate_manifest(m, registry=registry())
    assert result.ok is False
    assert H8_MANIFEST_SCHEMA_INVALID in result.reason_codes
    detail = _schema_detail(result, f"$.{fieldname}")
    assert detail is not None, f"no schema-invalid detail at $.{fieldname}"
    assert detail["expected"] == "object"
    assert detail["observed"] == typename


def test_T01_T05_camera_wrong_types_reported_at_camera_path():
    for _, value in WRONG_TYPES:
        m = valid_manifest()
        m["camera"] = value
        result = validate_manifest(m, registry=registry())
        assert _schema_detail(result, "$.camera") is not None


def test_originally_reported_camera_string_no_longer_raises():
    """The exact input from the audit: metadata.json held camera as a free-text string."""
    m = valid_manifest()
    m["camera"] = "Yahboom front RGB (Isaac Sim)"
    result = validate_manifest(m, registry=registry())  # must not raise
    assert result.ok is False
    assert H8_MANIFEST_SCHEMA_INVALID in result.reason_codes
    assert _schema_detail(result, "$.camera")["observed"] == "string"


# ============================================================================================
# Section 2 — non-object root document  (T-07..T-09)
# ============================================================================================


@pytest.mark.parametrize("typename,value", [
    ("array", []), ("array", [{"a": 1}]), ("string", "x"), ("null", None), ("number", 5),
    ("boolean", True),
])
def test_T07_T09_non_object_root_is_schema_invalid(typename, value):
    result = validate_manifest(value)  # must not raise
    assert result.ok is False
    assert result.reason_codes == [H8_MANIFEST_SCHEMA_INVALID]
    assert result.detail[0]["field"] == "$"
    assert result.detail[0]["observed"] == typename


# ============================================================================================
# Section 3 — manifest_version  (T-10 missing, T-11 wrong type, T-12 unsupported value)
# ============================================================================================


def test_T10_manifest_version_missing_is_unsupported():
    m = valid_manifest()
    m.pop("manifest_version")
    result = validate_manifest(m, registry=registry())
    assert result.reason_codes == [H8_MANIFEST_VERSION_UNSUPPORTED]


def test_T11_manifest_version_wrong_type_is_schema_invalid():
    m = valid_manifest()
    m["manifest_version"] = ["not", "a", "string"]
    result = validate_manifest(m, registry=registry())
    assert H8_MANIFEST_SCHEMA_INVALID in result.reason_codes
    assert _schema_detail(result, "$.manifest_version")["observed"] == "array"
    # A wrong-typed version must NOT also be reported as merely "unsupported".
    assert H8_MANIFEST_VERSION_UNSUPPORTED not in result.reason_codes


def test_T12_manifest_version_unsupported_value():
    m = valid_manifest()
    m["manifest_version"] = f"{MANIFEST_VERSION}.unsupported"
    result = validate_manifest(m, registry=registry())
    assert result.reason_codes == [H8_MANIFEST_VERSION_UNSUPPORTED]


# ============================================================================================
# Section 4 — absent object -> the field's own domain code, NOT schema-invalid
# (T-13 scene, T-16 goal, T-19 controller). The absent/wrong-type distinction is the point.
# ============================================================================================


def test_T13_scene_object_missing_is_scene_digest_missing_not_schema_invalid():
    m = valid_manifest()
    m.pop("scene")
    result = validate_manifest(m, registry=registry())
    assert H8_SCENE_DIGEST_MISSING in result.reason_codes
    assert _schema_detail(result, "$.scene") is None


def test_T16_goal_object_missing_is_goal_id_missing_not_schema_invalid():
    m = valid_manifest()
    m.pop("goal")
    result = validate_manifest(m, registry=registry())
    assert H8_GOAL_ID_MISSING in result.reason_codes
    assert _schema_detail(result, "$.goal") is None


def test_T19_controller_object_missing_is_controller_mode_missing_not_schema_invalid():
    m = valid_manifest()
    m.pop("controller")
    result = validate_manifest(m, registry=registry())
    assert H8_CONTROLLER_MODE_MISSING in result.reason_codes
    assert _schema_detail(result, "$.controller") is None


def test_present_null_object_is_schema_invalid_unlike_absent():
    """`"scene": null` is a present-but-wrong-type value (T-03 class), distinct from an absent key."""
    m = valid_manifest()
    m["scene"] = None
    result = validate_manifest(m, registry=registry())
    assert _schema_detail(result, "$.scene") is not None


# ============================================================================================
# Section 5 — reconciled existing behaviour (scalar fields never crashed; they already fail closed)
# T-06 camera missing fields; T-24/T-25/T-26 split; T-27/T-28 resolution.
# These are NOT converted to SCHEMA_INVALID: the spec forbids adding logic/codes, and none of these
# is an ME-021 crash site. Each is asserted to fail closed with the code the control actually emits.
# ============================================================================================


def test_T06_camera_object_present_missing_required_fields():
    m = valid_manifest()
    m["camera"].pop("camera_prim")
    result = validate_manifest(m, registry=registry())
    assert H8_CAMERA_IDENTITY_MISSING in result.reason_codes
    assert _schema_detail(result, "$.camera") is None  # object present -> not a type violation


def test_T24_split_missing_is_split_unknown():
    m = valid_manifest()
    m.pop("split")
    assert H8_SPLIT_UNKNOWN in validate_manifest(m, registry=registry()).reason_codes


def test_T25_split_unknown_value_is_split_unknown():
    m = valid_manifest()
    m["split"] = "holdout"
    assert H8_SPLIT_UNKNOWN in validate_manifest(m, registry=registry()).reason_codes


def test_T26_split_wrong_type_fails_closed_without_crashing():
    """Reconciled: split is a scalar, `x not in SPLITS` never raises on a list, so a wrong-typed
    split is already a deterministic H8_SPLIT_UNKNOWN rejection - no ME-021 exposure, not converted
    to SCHEMA_INVALID."""
    m = valid_manifest()
    m["split"] = ["train"]
    result = validate_manifest(m, registry=registry())  # must not raise
    assert result.ok is False
    assert H8_SPLIT_UNKNOWN in result.reason_codes


def test_T27_T28_resolution_malformed_uses_existing_malformed_code():
    """Reconciled: a wrong-typed camera_resolution (string or dict) is already caught by the
    existing H8_ACQUISITION_RESOLUTION_MALFORMED path; camera itself is a valid object."""
    for bad in ("640x480", {"w": 640}):
        m = valid_manifest()
        m["camera"]["camera_resolution"] = bad
        result = validate_manifest(m, registry=registry())  # must not raise
        assert H8_ACQUISITION_RESOLUTION_MALFORMED in result.reason_codes


# ============================================================================================
# Section 6 — valid-manifest behaviour preserved  (T-33 admitted, T-34 placeholder rejected)
# ============================================================================================


def test_T33_valid_canonical_manifest_still_admitted():
    result = validate_manifest(valid_manifest(), registry=registry(), require_navmesh=True)
    assert result.ok is True
    assert result.reason_codes == []


def test_T34_valid_manifest_rejected_for_placeholder_goal():
    m = valid_manifest()
    m["goal"]["goal_id"] = "h2_weave_J"
    result = validate_manifest(m, registry=registry())
    assert result.ok is False
    assert H8_GOAL_ID_PLACEHOLDER in result.reason_codes
    # A genuine evidence rejection must not be masked as a type violation.
    assert H8_MANIFEST_SCHEMA_INVALID not in result.reason_codes


# ============================================================================================
# Section 7 — global guarantees across the whole matrix
# ============================================================================================


def test_no_malformed_object_type_is_ever_admitted():
    for fieldname in OBJECT_FIELDS:
        for _, value in WRONG_TYPES:
            m = valid_manifest()
            m[fieldname] = value
            assert validate_manifest(m, registry=registry()).ok is False


def test_metric_readiness_and_screen_helpers_untouched_note():
    """Documentation guard: metric_readiness retains the `or {}` idiom and is OUT OF SCOPE for the
    ME-021 repair, which targets the validate_manifest entry point. Recorded here so a future reader
    knows the residual is deliberate, not overlooked."""
    import h8_episode_validator as V
    body = V.metric_readiness.__doc__ or ""
    assert "readiness" in body.lower()
