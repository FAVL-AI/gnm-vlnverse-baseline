"""H8-S1 — dataset-builder skeleton tests.

Proves the fail-closed ordering, that no dataset artefact is ever produced at this gate, and that a
real historical manifest is rejected with the expected reason codes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "gnm"))

from build_h8_dataset_root import REQUIRED_TOPICS, STAGES, build_parser, run  # noqa: E402
from h8_episode_validator import (  # noqa: E402
    NOT_COMPUTED_UNTRUSTED_METADATA,
    PATH_METRICS,
)
from h8_s1_reason_codes import (  # noqa: E402
    H8_ACQUISITION_RESOLUTION_MISMATCH,
    H8_CONTACT_TELEMETRY_UNAVAILABLE,
    H8_CONTROLLER_CHECKPOINT_MISSING,
    H8_CONTROLLER_POLICY_MISMATCH,
    H8_GOAL_ID_PLACEHOLDER,
    H8_SCENE_DIGEST_MISSING,
    H8_START_POSE_DECLARED_MISSING,
    H8_START_POSE_TOLERANCE_EXCEEDED,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_h8_episode_schema_v2 import _goal_record, valid_manifest  # noqa: E402

SCHEMA = ROOT / "docs" / "research" / "schemas" / "h8_episode_manifest.schema.json"


def _write(tmp_path: Path, name: str, obj) -> str:
    p = tmp_path / name
    p.write_text(json.dumps(obj))
    return str(p)


def _full_manifest(**over):
    m = valid_manifest(**over)
    m["topics_recorded"] = list(REQUIRED_TOPICS)
    m["image_stamps"] = [0.05, 0.10, 0.15]
    m["pose_series"] = [
        {"stamp": t, "x": 0.2 * t, "y": 0.0, "qw": 1.0} for t in (0.0, 0.05, 0.10, 0.15, 0.20)
    ]
    return m


def _run(tmp_path, manifests, *, extra=None, goals=None):
    argv = ["--schema", str(SCHEMA), "--validate-only"]
    for i, m in enumerate(manifests):
        argv += ["--manifest", _write(tmp_path, f"m{i}.json", m)]
    argv += ["--goal-registry",
             _write(tmp_path, "goals.json", {"goals": goals or [_goal_record()]})]
    argv += ["--out-dir", str(tmp_path / "dataset")]
    argv += extra or []
    return run(argv)


def test_cli_exposes_the_required_flags():
    opts = {a.option_strings[0] for a in build_parser()._actions if a.option_strings}
    for flag in ("--validate-only", "--manifest", "--goal-registry", "--schema", "--out-dir",
                 "--dry-run", "--emit-plan", "--strict", "--alignment-policy", "--metric-policy"):
        assert flag in opts


def test_builder_validate_only_positive_path(tmp_path):
    code, rep = _run(tmp_path, [_full_manifest()])
    assert code == 0, rep.reason_codes
    assert rep.ok
    assert rep.episodes[0]["admitted"]


def test_builder_creates_no_dataset_on_success(tmp_path):
    code, rep = _run(tmp_path, [_full_manifest()])
    assert code == 0
    assert rep.dataset_created is False
    assert rep.images_written == 0
    assert rep.trajectories_written == 0
    assert rep.split_manifest_written is False
    assert rep.metrics_computed == 0
    assert not (tmp_path / "dataset").exists(), "S1 must not create the output directory"


def test_builder_creates_no_output_on_rejection(tmp_path):
    m = _full_manifest()
    m["goal"]["goal_id"] = "h2_weave_J"
    code, rep = _run(tmp_path, [m])
    assert code != 0
    assert H8_GOAL_ID_PLACEHOLDER in rep.reason_codes
    assert rep.dataset_created is False
    assert rep.images_written == 0 and rep.trajectories_written == 0
    assert not (tmp_path / "dataset").exists()


def test_builder_stage_order_is_fixed(tmp_path):
    _, rep = _run(tmp_path, [_full_manifest()])
    assert rep.stages_run[0] == "parse_cli"
    assert rep.stages_run[-1] == "emit_plan"
    # every stage run must be a declared stage, in declared order
    idx = [STAGES.index(s) for s in rep.stages_run]
    assert idx == sorted(idx)


def test_builder_blocks_before_episodes_on_bad_goal_registry(tmp_path):
    """A structurally invalid bank must stop the run before any episode is processed."""
    code, rep = _run(tmp_path, [_full_manifest()],
                     goals=[_goal_record(), _goal_record(goal_image_sha256="b" * 64)])
    assert code == 2
    assert rep.blocked_at == "goal_registry"
    assert rep.episodes == [], "no episode may be processed once the bank is invalid"


def test_builder_rejects_missing_required_topics(tmp_path):
    m = _full_manifest()
    m["topics_recorded"] = ["/camera/image_raw", "/odom"]
    code, rep = _run(tmp_path, [m])
    assert code != 0
    assert "/tf_static" in rep.episodes[0]["missing_topics"]


def test_builder_emits_plan_without_dataset(tmp_path):
    plan_path = tmp_path / "plan.json"
    code, _ = _run(tmp_path, [_full_manifest()], extra=["--emit-plan", str(plan_path)])
    assert code == 0
    plan = json.loads(plan_path.read_text())
    assert plan["would_write_to"].endswith("dataset")
    assert plan["n_admitted"] == 1
    assert plan["alignment"]["authoritative_clock"] == "sim"
    assert not (tmp_path / "dataset").exists()


def test_builder_strict_requires_navmesh(tmp_path):
    m = _full_manifest()
    m["map"].pop("navmesh_version")
    code, rep = _run(tmp_path, [m], extra=["--strict"])
    assert code != 0
    assert "H8_NAVMESH_VERSION_MISSING" in rep.reason_codes


def test_builder_path_metrics_not_computed_without_navmesh(tmp_path):
    m = _full_manifest()
    m["map"].pop("navmesh_version")
    _, rep = _run(tmp_path, [m])
    readiness = rep.episodes[0]["metric_readiness"]
    for name in PATH_METRICS:
        assert readiness[name].startswith("NOT_COMPUTED")


def test_builder_marks_metrics_untrusted_for_invalid_manifest(tmp_path):
    m = _full_manifest()
    m["camera"]["camera_resolution"] = [640, 480]
    _, rep = _run(tmp_path, [m])
    assert H8_ACQUISITION_RESOLUTION_MISMATCH in rep.reason_codes
    assert set(rep.episodes[0]["metric_readiness"].values()) == {NOT_COMPUTED_UNTRUSTED_METADATA}


def test_builder_detects_retry_as_non_independent(tmp_path):
    a, b = _full_manifest(), _full_manifest()
    b["episode_id"] = "h8_lobby_east_A_20260801_110000"
    code, rep = _run(tmp_path, [a, b])
    assert code != 0
    assert rep.duplicate_screening["n_distinct_instances"] == 1
    assert "H8_RETRY_NOT_INDEPENDENT" in rep.reason_codes


def test_builder_alignment_rejection_is_reported(tmp_path):
    m = _full_manifest()
    m["image_stamps"] = [0.05, 99.0]  # second frame far outside the pose series
    code, rep = _run(tmp_path, [m])
    assert code != 0
    assert rep.episodes[0]["alignment"]["n_rejected"] == 1


# ---------------------------------------------------------------------------------------------
# Historical-manifest negative compatibility test
# ---------------------------------------------------------------------------------------------

HISTORICAL = (ROOT / "assets" / "experiments" / "trajectories"
              / "h8mx_val_east_A_20260714_215023" / "episode_metadata.json")


@pytest.mark.skipif(not HISTORICAL.exists(), reason="historical episode metadata not present")
def test_historical_manifest_is_rejected_with_expected_codes(tmp_path):
    """A real historical episode must fail, proving v2 would have caught the audit defects.

    This is a NEGATIVE COMPATIBILITY TEST ONLY. The historical file is read, never modified, and
    never repaired.
    """
    before = HISTORICAL.read_bytes()
    legacy = json.loads(HISTORICAL.read_text())

    # Present the legacy record to the v2 validator exactly as it stands, mapped onto the v2
    # shape without inventing any value that the legacy record does not contain.
    m = {
        "manifest_version": legacy.get("manifest_version"),
        "episode_id": legacy.get("episode_id"),
        "scene": {"scene_identity_pass": None},
        "map": {},
        "split": None,
        "goal": {"goal_id": legacy.get("goal_id"), "goal_pose": legacy.get("goal_pose")},
        "success_criterion": {},
        "camera": {"camera_prim": legacy.get("camera_prim"),
                   "camera_frame_id": "camera_link",
                   "camera_mount_raise_m": legacy.get("camera_mount_raise_m"),
                   "camera_resolution": [640, 480], "camera_encoding": "rgb8"},
        "controller": {"controller_mode": legacy.get("policy_mode"),
                       "policy_in_loop": bool(legacy.get("closed_loop"))},
        "start_pose_declared": None,
        "start_pose_observed": None,
        "contact_telemetry": {"contact_telemetry_available": None},
    }
    code, rep = _run(tmp_path, [m])

    assert code != 0, "a historical manifest must never validate under v2"
    for expected in (H8_GOAL_ID_PLACEHOLDER, H8_ACQUISITION_RESOLUTION_MISMATCH,
                     H8_SCENE_DIGEST_MISSING, H8_CONTROLLER_CHECKPOINT_MISSING,
                     H8_START_POSE_DECLARED_MISSING, H8_CONTACT_TELEMETRY_UNAVAILABLE):
        assert expected in rep.reason_codes, f"{expected} not in {rep.reason_codes}"
    # The legacy record is internally self-consistent (policy_mode=gnm_closed_loop AND
    # closed_loop=true), which is precisely why its label was misleading: it asserts a learned
    # policy was driving while naming no checkpoint. H8_CONTROLLER_CHECKPOINT_MISSING is the
    # control that catches that class of claim - a closed-loop assertion must be backed by a
    # weights digest, not by a self-declared flag.
    assert H8_CONTROLLER_POLICY_MISMATCH not in rep.reason_codes
    assert rep.dataset_created is False
    assert rep.images_written == 0 and rep.trajectories_written == 0
    assert not (tmp_path / "dataset").exists()
    assert HISTORICAL.read_bytes() == before, "the historical file must be byte-identical"


@pytest.mark.skipif(not HISTORICAL.exists(), reason="historical episode metadata not present")
def test_historical_start_pose_error_would_be_rejected(tmp_path):
    """The legacy declared start pose (0,0) disagrees with the observed first pose (1.4, 0.1)."""
    legacy = json.loads(HISTORICAL.read_text())
    declared = legacy.get("start_pose_episode") or {}
    m = _full_manifest()
    m["start_pose_declared"] = {"x": declared.get("x", 0.0), "y": declared.get("y", 0.0),
                                "yaw_rad": declared.get("yaw_rad", 0.0)}
    m["start_pose_observed"] = {"x": 1.4, "y": 0.1, "yaw_rad": 0.0}
    code, rep = _run(tmp_path, [m])
    assert code != 0
    assert H8_START_POSE_TOLERANCE_EXCEEDED in rep.reason_codes
