"""H8-S1 — episode-manifest schema and validator fixture suite.

Thirty negative fixtures plus positive fixtures, covering every rejection path the 2026-07-22
forensic audit showed the historical corpus needs. Each negative case asserts its deterministic
reason code, so a silently weakened control fails a test rather than passing quietly.
"""
from __future__ import annotations

import copy
import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "gnm"))

from h8_episode_validator import (  # noqa: E402
    CANONICAL_RESOLUTION,
    COMPUTABLE_VALID,
    MANIFEST_VERSION,
    NOT_COMPUTED_MISSING_CONTACTS,
    NOT_COMPUTED_MISSING_GOAL,
    NOT_COMPUTED_MISSING_NAVMESH,
    NOT_COMPUTED_MISSING_REFERENCE_PATH,
    NOT_COMPUTED_MISSING_STOP_EVENT,
    NOT_COMPUTED_UNTRUSTED_METADATA,
    PATH_METRICS,
    GoalRegistry,
    metric_readiness,
    screen_duplicates,
    validate_manifest,
)
from h8_s1_reason_codes import (  # noqa: E402
    H8_ACQUISITION_ENCODING_MISMATCH,
    H8_ACQUISITION_RESOLUTION_MALFORMED,
    H8_ACQUISITION_RESOLUTION_MISMATCH,
    H8_ACQUISITION_RESOLUTION_MISSING,
    H8_CAMERA_IDENTITY_MISSING,
    H8_CAMERA_MOUNT_UNSUPPORTED,
    H8_CAPTURE_AUTHORISATION_MISSING,
    H8_CONTACT_TELEMETRY_UNAVAILABLE,
    H8_CONTROLLER_CHECKPOINT_MISSING,
    H8_CONTROLLER_MODE_MISSING,
    H8_CONTROLLER_MODE_UNKNOWN,
    H8_CONTROLLER_POLICY_MISMATCH,
    H8_GOAL_AMBIGUOUS,
    H8_GOAL_CAMERA_MISMATCH,
    H8_GOAL_HASH_MISMATCH,
    H8_GOAL_HASH_MISSING,
    H8_GOAL_ID_MISSING,
    H8_GOAL_ID_PLACEHOLDER,
    H8_GOAL_IMAGE_CROSS_SPLIT_REUSE,
    H8_GOAL_MAP_MISMATCH,
    H8_GOAL_NOT_FOUND,
    H8_GOAL_POSE_MISMATCH,
    H8_GOAL_RESOLUTION_MISMATCH,
    H8_GOAL_SCENE_MISMATCH,
    H8_GOAL_SPLIT_MISMATCH,
    H8_MANIFEST_SCHEMA_INVALID,
    H8_MANIFEST_VERSION_UNSUPPORTED,
    H8_MAP_VERSION_MISSING,
    H8_NAVMESH_VERSION_MISSING,
    H8_RETRY_NOT_INDEPENDENT,
    H8_ROUTE_SPLIT_DUPLICATE,
    H8_SCENE_DIGEST_MISSING,
    H8_SCENE_IDENTITY_FAILED,
    H8_SPLIT_UNKNOWN,
    H8_START_POSE_DECLARED_MISSING,
    H8_START_POSE_OBSERVED_MISSING,
    H8_START_POSE_TOLERANCE_EXCEEDED,
    H8_SUCCESS_CRITERION_NOT_PREREGISTERED,
    H8_SUCCESS_RADIUS_MISMATCH,
    H8_SUCCESS_RADIUS_MISSING,
)

SCHEMA_PATH = ROOT / "docs" / "research" / "schemas" / "h8_episode_manifest.schema.json"
SHA = "a" * 64
SHA_B = "b" * 64
SHA_SCENE = "c" * 64


def _goal_record(goal_id="h8_lobby_east_A", split="train", **over):
    rec = {
        "goal_id": goal_id,
        "scene_id": "isaac_hospital_5_1",
        "scene_usd_sha256": SHA_SCENE,
        "map_version": "h8_navmap_v2",
        "split": split,
        "goal_pose": {"x": 2.0, "y": 0.5, "yaw_rad": 0.1},
        "camera_prim": "/World/M3Pro/camera_link/rgb_camera",
        "camera_frame_id": "camera_link",
        "camera_resolution": [1280, 720],
        "camera_encoding": "rgb8",
        "goal_image_path": f"goals/{goal_id}.png",
        "goal_image_sha256": SHA,
        "goal_capture_timestamp": "2026-08-01T10:00:00Z",
        "capture_authorisation_id": "AUTH-H8-001",
    }
    rec.update(over)
    return rec


def valid_manifest(**over):
    m = {
        "manifest_version": MANIFEST_VERSION,
        "episode_id": "h8_lobby_east_A_20260801_100000",
        "capture_authorisation_id": "AUTH-H8-001",
        "commit_sha": "0" * 40,
        "config_sha256": "d" * 64,
        "scene": {
            "scene_id": "isaac_hospital_5_1",
            "scene_usd_path": "https://example.invalid/hospital.usd",
            "scene_usd_sha256": SHA_SCENE,
            "prim_count": 1909,
            "scene_mode": "hospital",
            "scene_identity_pass": True,
            "procedural_landmark_prims": [],
            "isaac_sim_version": "5.1.0.0",
        },
        "map": {"map_version": "h8_navmap_v2", "navmesh_version": "h8_navmesh_v1",
                "navigable_envelope": {"x_min": -9.9, "x_max": 4.0, "y_min": -0.8,
                                       "y_max": 1.1, "frame": "spawn_relative"}},
        "route": {"route_instance_id": "ri_east_A", "route_family": "same_start_fork",
                  "decision_frame_id": "df01", "leakage_group": "lg01",
                  "waypoints": [[1.4, 0.1], [2.0, 0.5]]},
        "split": "train",
        "start_pose_declared": {"x": 1.4, "y": 0.1, "yaw_rad": 0.0, "frame": "spawn_relative"},
        "start_pose_observed": {"x": 1.4, "y": 0.1, "yaw_rad": 0.0, "frame": "spawn_relative"},
        "start_pose_error": {"position_m": 0.0, "yaw_rad": 0.0, "within_tolerance": True,
                             "tolerance_position_m": 0.05, "tolerance_yaw_rad": 0.0873},
        "goal": {
            "goal_id": "h8_lobby_east_A",
            "goal_pose": {"x": 2.0, "y": 0.5, "yaw_rad": 0.1},
            "goal_image_path": "goals/h8_lobby_east_A.png",
            "goal_image_sha256": SHA,
            "goal_capture_episode_id": "goalbank_20260801_090000",
            "goal_capture_timestamp": "2026-08-01T09:00:00Z",
            "camera_intrinsics": {"fx": 600.0, "fy": 600.0, "cx": 640.0, "cy": 360.0,
                                  "width": 1280, "height": 720},
            "scene_usd_sha256": SHA_SCENE,
            "map_version": "h8_navmap_v2",
            "route_instance_id": "ri_east_A",
            "split": "train",
        },
        "success_criterion": {
            "success_radius_m": 0.5, "speed_threshold_ms": 0.05, "stationary_duration_s": 1.0,
            "sensitivity_radii_m": [0.25, 0.5, 0.75, 1.0],
            "pose_aligned_yaw_tolerance_rad": 0.5236,
            "preregistered": True, "approved_by": "Bo Wei",
        },
        "camera": {"camera_prim": "/World/M3Pro/camera_link/rgb_camera",
                   "camera_frame_id": "camera_link", "camera_mount_raise_m": 0.12,
                   "camera_resolution": [1280, 720], "camera_encoding": "rgb8",
                   "publish_rate_hz": 20.0},
        "controller": {"controller_mode": "scripted_waypoint_follower", "policy_in_loop": False},
        "reference_path": {"reference_path_id": "rp_east_A", "source": "navmesh_geodesic",
                           "navmesh_version": "h8_navmesh_v1", "geodesic_length_m": 0.72,
                           "nodes": [[1.4, 0.1], [2.0, 0.5]]},
        "stop_event": {"stop_emitted": True, "stop_timestamp": 42.0, "stop_step": 840,
                       "stop_pose": {"x": 2.0, "y": 0.5, "yaw_rad": 0.1},
                       "stop_source": "policy_terminating_action"},
        "contact_telemetry": {"contact_telemetry_available": True,
                              "detector": "physx_contact_report",
                              "detector_scope": ["base_link", "camera_link", "wheels"],
                              "recorded_to_bag_topic": "/contacts"},
        "counters": {"n_frames": 1400, "n_poses": 1400, "executed_path_length_m": 3.2,
                     "stationary_fraction": 0.2, "total_collision_count": 0, "return_code": 0,
                     "route_completed": True, "duration_sim_s": 70.0, "duration_wall_s": 500.0},
        "acceptance": {"time_alignment_verified": True, "max_image_pose_offset_s": 0.016,
                       "image_quality_pass": True, "black_band_fraction": 0.0,
                       "mean_luminance": 55.0, "admitted": True, "rejection_reasons": []},
    }
    for k, v in over.items():
        m[k] = v
    return m


def registry(*records):
    return GoalRegistry(list(records) or [_goal_record()])


def codes(m, **kw):
    return validate_manifest(m, **kw).reason_codes


# ================================ POSITIVE FIXTURES ==========================================


def test_p01_valid_manifest_passes():
    res = validate_manifest(valid_manifest(), registry=registry(), require_navmesh=True)
    assert res.ok, res.reason_codes
    assert res.reason_codes == []


def test_p02_valid_gnm_closed_loop_passes():
    m = valid_manifest()
    m["controller"] = {"controller_mode": "gnm_closed_loop", "policy_in_loop": True,
                       "policy_checkpoint_path": "ckpt/h8.pth",
                       "policy_checkpoint_sha256": "e" * 64}
    assert validate_manifest(m, registry=registry()).ok


def test_p03_schema_file_is_draft7_valid():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA_PATH.read_text())
    jsonschema.Draft7Validator.check_schema(schema)
    assert schema["$id"] == "h8-episode-manifest/2.0.0"


def test_p04_valid_manifest_conforms_to_json_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA_PATH.read_text())
    m = copy.deepcopy(valid_manifest())
    for pose_key in ("start_pose_declared", "start_pose_observed"):
        m[pose_key].pop("frame", None)  # schema pose has no `frame` member
    jsonschema.Draft7Validator(schema).validate(m)


# ================================ NEGATIVE FIXTURES ==========================================


def test_n01_placeholder_goal_id_rejected():
    m = valid_manifest()
    m["goal"]["goal_id"] = "h2_weave_J"
    assert H8_GOAL_ID_PLACEHOLDER in codes(m, registry=registry())


def test_n02_absent_goal_id_rejected():
    m = valid_manifest()
    m["goal"].pop("goal_id")
    assert H8_GOAL_ID_MISSING in codes(m, registry=registry())


def test_n03_unresolved_goal_id_rejected():
    m = valid_manifest()
    m["goal"]["goal_id"] = "not_in_the_bank"
    assert H8_GOAL_NOT_FOUND in codes(m, registry=registry())


def test_n04_goal_without_image_digest_rejected():
    m = valid_manifest()
    m["goal"].pop("goal_image_sha256")
    assert H8_GOAL_HASH_MISSING in codes(m, registry=registry())


def test_n05_goal_from_another_scene_digest_rejected():
    m = valid_manifest()
    assert H8_GOAL_SCENE_MISMATCH in codes(
        m, registry=registry(_goal_record(scene_usd_sha256="f" * 64)))


def test_n06_goal_from_another_map_version_rejected():
    m = valid_manifest()
    assert H8_GOAL_MAP_MISMATCH in codes(m, registry=registry(_goal_record(map_version="v_old")))


def test_n07_goal_from_another_split_rejected():
    m = valid_manifest()
    assert H8_GOAL_SPLIT_MISMATCH in codes(m, registry=registry(_goal_record(split="test")))


def test_n08_duplicate_goal_id_conflicting_content_rejected():
    reg = registry(_goal_record(), _goal_record(goal_image_sha256=SHA_B))
    assert H8_GOAL_AMBIGUOUS in codes(valid_manifest(), registry=reg)
    assert any(e["code"] == H8_GOAL_AMBIGUOUS for e in reg.structural_errors())


def test_n09_closed_loop_without_policy_in_loop_rejected():
    m = valid_manifest()
    m["controller"] = {"controller_mode": "gnm_closed_loop", "policy_in_loop": False}
    assert H8_CONTROLLER_POLICY_MISMATCH in codes(m, registry=registry())


def test_n10_scripted_follower_labelled_as_gnm_rejected():
    """The exact defect found in 92 historical episodes."""
    m = valid_manifest()
    m["controller"] = {"controller_mode": "gnm_closed_loop", "policy_in_loop": True}
    c = codes(m, registry=registry())
    assert H8_CONTROLLER_CHECKPOINT_MISSING in c, "a closed-loop claim needs a checkpoint digest"


def test_n10b_scripted_follower_claiming_policy_in_loop_rejected():
    m = valid_manifest()
    m["controller"] = {"controller_mode": "scripted_waypoint_follower", "policy_in_loop": True}
    assert H8_CONTROLLER_POLICY_MISMATCH in codes(m, registry=registry())


def test_n11_unknown_controller_mode_rejected():
    m = valid_manifest()
    m["controller"] = {"controller_mode": "autopilot", "policy_in_loop": False}
    assert H8_CONTROLLER_MODE_UNKNOWN in codes(m, registry=registry())


def test_n12_640x480_acquisition_rejected():
    """All 157 historical bags are 640x480."""
    m = valid_manifest()
    m["camera"]["camera_resolution"] = [640, 480]
    assert H8_ACQUISITION_RESOLUTION_MISMATCH in codes(m, registry=registry())


def test_n13_missing_camera_resolution_rejected():
    m = valid_manifest()
    m["camera"].pop("camera_resolution")
    assert H8_ACQUISITION_RESOLUTION_MISSING in codes(m, registry=registry())


def test_n14_malformed_resolution_string_rejected():
    m = valid_manifest()
    m["camera"]["camera_resolution"] = "1280x720"
    assert H8_ACQUISITION_RESOLUTION_MALFORMED in codes(m, registry=registry())


def test_n15_start_pose_error_above_tolerance_rejected():
    """84% of historical episodes would fail this."""
    m = valid_manifest()
    m["start_pose_declared"] = {"x": 0.0, "y": 0.0, "yaw_rad": 0.0, "frame": "spawn_relative"}
    assert H8_START_POSE_TOLERANCE_EXCEEDED in codes(m, registry=registry())


def test_n16_missing_observed_start_pose_rejected():
    m = valid_manifest()
    m.pop("start_pose_observed")
    assert H8_START_POSE_OBSERVED_MISSING in codes(m, registry=registry())


def test_n17_missing_declared_start_pose_rejected():
    m = valid_manifest()
    m.pop("start_pose_declared")
    assert H8_START_POSE_DECLARED_MISSING in codes(m, registry=registry())


def test_n18_start_pose_frame_mismatch_rejected():
    m = valid_manifest()
    m["start_pose_observed"]["frame"] = "isaac_world"
    from h8_s1_reason_codes import H8_START_POSE_FRAME_MISMATCH
    assert H8_START_POSE_FRAME_MISMATCH in codes(m, registry=registry())


def test_n19_missing_scene_digest_rejected():
    m = valid_manifest()
    m["scene"].pop("scene_usd_sha256")
    assert H8_SCENE_DIGEST_MISSING in codes(m, registry=registry())


def test_n20_missing_map_version_rejected():
    m = valid_manifest()
    m["map"].pop("map_version")
    assert H8_MAP_VERSION_MISSING in codes(m, registry=registry())


def test_n21_missing_navmesh_when_path_metrics_requested_rejected():
    m = valid_manifest()
    m["map"].pop("navmesh_version")
    assert H8_NAVMESH_VERSION_MISSING in codes(m, registry=registry(), require_navmesh=True)


def test_n22_missing_success_radius_rejected():
    m = valid_manifest()
    m["success_criterion"].pop("success_radius_m")
    assert H8_SUCCESS_RADIUS_MISSING in codes(m, registry=registry())


def test_n23_success_radius_differing_from_protocol_rejected():
    m = valid_manifest()
    m["success_criterion"]["success_radius_m"] = 3.0  # the Track A legacy value
    assert H8_SUCCESS_RADIUS_MISMATCH in codes(m, registry=registry())


def test_n24_route_instance_in_two_splits_rejected():
    a, b = valid_manifest(), valid_manifest()
    b["episode_id"] = "other"
    b["split"] = "test"
    out = screen_duplicates([a, b])
    assert not out["ok"]
    assert any(f["code"] == H8_ROUTE_SPLIT_DUPLICATE for f in out["findings"])


def test_n25_retry_not_counted_as_independent_sample():
    """h8mx_val_val_A / _retry were identical to four decimals in the audit."""
    a = valid_manifest()
    b = valid_manifest()
    b["episode_id"] = "h8_lobby_east_A_20260801_110000_retry"
    out = screen_duplicates([a, b])
    assert not out["ok"]
    assert any(f["code"] == H8_RETRY_NOT_INDEPENDENT for f in out["findings"])
    assert out["n_distinct_instances"] == 1


def test_n26_goal_image_reused_across_train_and_test_rejected():
    reg = registry(_goal_record(goal_id="g_train", split="train"),
                   _goal_record(goal_id="g_test", split="test"))
    errs = reg.structural_errors()
    assert any(e["code"] == H8_GOAL_IMAGE_CROSS_SPLIT_REUSE for e in errs)


def test_n27_unknown_split_rejected():
    m = valid_manifest()
    m["split"] = "holdout"
    assert H8_SPLIT_UNKNOWN in codes(m, registry=registry())


def test_n28_missing_capture_authorisation_rejected():
    m = valid_manifest()
    m.pop("capture_authorisation_id")
    assert H8_CAPTURE_AUTHORISATION_MISSING in codes(m, registry=registry())


def test_n29_unsupported_camera_mount_rejected():
    m = valid_manifest()
    m["camera"]["camera_mount_raise_m"] = 0.0  # the unraised mount: 38% frame occlusion
    assert H8_CAMERA_MOUNT_UNSUPPORTED in codes(m, registry=registry())


def test_n30_zero_collisions_without_telemetry_rejected():
    """Absence of telemetry must never be reported as zero collisions."""
    m = valid_manifest()
    m["contact_telemetry"] = {"contact_telemetry_available": False}
    m["counters"]["total_collision_count"] = 0
    assert H8_CONTACT_TELEMETRY_UNAVAILABLE in codes(m, registry=registry())
    assert metric_readiness(m)["collision_rate"] == NOT_COMPUTED_MISSING_CONTACTS


def test_n31_goal_hash_mismatch_rejected():
    m = valid_manifest()
    m["goal"]["goal_image_sha256"] = SHA_B
    assert H8_GOAL_HASH_MISMATCH in codes(m, registry=registry())


def test_n32_missing_camera_identity_rejected():
    m = valid_manifest()
    m["camera"].pop("camera_prim")
    assert H8_CAMERA_IDENTITY_MISSING in codes(m, registry=registry())


def test_n33_wrong_encoding_rejected():
    m = valid_manifest()
    m["camera"]["camera_encoding"] = "bgr8"
    assert H8_ACQUISITION_ENCODING_MISMATCH in codes(m, registry=registry())




# ======================== H8-S1R ACTIVE REASON-CODE CLOSURE ========================

def _assert_only_blocking_code(
    manifest,
    expected_code,
    *,
    goal_registry=None,
):
    """One controlled mutation must produce one exact blocking reason code."""
    active_registry = (
        goal_registry
        if goal_registry is not None
        else registry()
    )
    result = validate_manifest(
        manifest,
        registry=active_registry,
    )

    assert result.ok is False
    assert result.reason_codes == [expected_code]


def test_s1r_controller_mode_missing_is_blocking():
    m = valid_manifest()
    m["controller"].pop("controller_mode")

    _assert_only_blocking_code(
        m,
        H8_CONTROLLER_MODE_MISSING,
    )


def test_s1r_goal_camera_mismatch_is_blocking():
    m = valid_manifest()
    m["camera"]["camera_prim"] = "/World/M3Pro/other_camera"

    _assert_only_blocking_code(
        m,
        H8_GOAL_CAMERA_MISMATCH,
    )


def test_s1r_goal_pose_mismatch_is_blocking():
    m = valid_manifest()
    m["goal"]["goal_pose"]["x"] += 0.01

    _assert_only_blocking_code(
        m,
        H8_GOAL_POSE_MISMATCH,
    )


def test_s1r_goal_resolution_mismatch_is_blocking():
    m = valid_manifest()
    mismatched_registry = registry(
        _goal_record(camera_resolution=[640, 480])
    )

    _assert_only_blocking_code(
        m,
        H8_GOAL_RESOLUTION_MISMATCH,
        goal_registry=mismatched_registry,
    )


def test_s1r_manifest_schema_invalid_is_blocking():
    m = valid_manifest()
    m.pop("episode_id")

    _assert_only_blocking_code(
        m,
        H8_MANIFEST_SCHEMA_INVALID,
    )


def test_s1r_manifest_version_unsupported_is_blocking():
    m = valid_manifest()
    m["manifest_version"] = f"{MANIFEST_VERSION}.unsupported"

    _assert_only_blocking_code(
        m,
        H8_MANIFEST_VERSION_UNSUPPORTED,
    )


def test_s1r_scene_identity_failed_is_blocking():
    m = valid_manifest()
    m["scene"]["scene_identity_pass"] = False

    _assert_only_blocking_code(
        m,
        H8_SCENE_IDENTITY_FAILED,
    )


def test_s1r_success_criterion_not_preregistered_is_blocking():
    m = valid_manifest()
    m["success_criterion"]["preregistered"] = False

    _assert_only_blocking_code(
        m,
        H8_SUCCESS_CRITERION_NOT_PREREGISTERED,
    )


# ================================ METRIC READINESS ==========================================


def test_metric_readiness_valid_manifest():
    r = metric_readiness(valid_manifest())
    assert r["TL"] == COMPUTABLE_VALID
    assert r["SR_0.50"] == COMPUTABLE_VALID
    for m in PATH_METRICS:
        assert r[m] == COMPUTABLE_VALID


def test_path_metrics_not_computed_without_navmesh():
    m = valid_manifest()
    m["map"].pop("navmesh_version")
    r = metric_readiness(m)
    for name in PATH_METRICS:
        assert r[name] == NOT_COMPUTED_MISSING_NAVMESH


def test_path_metrics_not_computed_without_reference_path():
    m = valid_manifest()
    m["reference_path"]["source"] = "UNAVAILABLE"
    r = metric_readiness(m)
    for name in PATH_METRICS:
        assert r[name] == NOT_COMPUTED_MISSING_REFERENCE_PATH


def test_no_euclidean_substitution_for_path_metrics():
    """Removing the navmesh must not silently fall back to a straight-line approximation."""
    m = valid_manifest()
    m["map"].pop("navmesh_version")
    r = metric_readiness(m)
    assert all(r[name].startswith("NOT_COMPUTED") for name in PATH_METRICS)
    assert r["TL"] == COMPUTABLE_VALID, "TL needs only poses and stays valid"


def test_placeholder_goal_blocks_goal_metrics():
    m = valid_manifest()
    m["goal"]["goal_id"] = "h2_weave_J"
    r = metric_readiness(m)
    for name in ("SR_0.50", "OSR_0.50", "NE", "SR_OSR_GAP_0.50"):
        assert r[name] == NOT_COMPUTED_MISSING_GOAL


def test_missing_stop_event_blocks_sr_not_osr():
    m = valid_manifest()
    m["stop_event"] = {}
    r = metric_readiness(m)
    assert r["SR_0.50"] == NOT_COMPUTED_MISSING_STOP_EVENT
    assert r["OSR_0.50"] == COMPUTABLE_VALID


def test_invalid_manifest_marks_every_metric_untrusted():
    r = metric_readiness(valid_manifest(), manifest_valid=False)
    assert set(r.values()) == {NOT_COMPUTED_UNTRUSTED_METADATA}


def test_no_metric_state_is_a_numeric_zero():
    for state in metric_readiness(valid_manifest()).values():
        assert isinstance(state, str) and state != "0"


def test_canonical_resolution_constant():
    assert CANONICAL_RESOLUTION == [1280, 720]


def test_start_pose_yaw_wrap_does_not_false_trigger():
    m = valid_manifest()
    m["start_pose_declared"]["yaw_rad"] = math.pi - 0.01
    m["start_pose_observed"]["yaw_rad"] = -math.pi + 0.01
    assert H8_START_POSE_TOLERANCE_EXCEEDED not in codes(m, registry=registry())
