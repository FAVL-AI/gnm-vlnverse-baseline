"""tests/gnm/test_h8_evidence_schema.py

Conformance tests for the H8 render/drive EVIDENCE SCHEMA design gate
(scripts/gnm/h8_evidence_schema.py + docs/research/schemas/h8_evidence_envelope.schema.json).

These are pure, no-Isaac, no-capture tests: they exercise the schema/conformance validator over
SYNTHETIC fixtures only, prove every negative fixture fails closed with a stable reason code, and
prove the design gate touched neither the frozen Level-1 dry-run evidence nor the pilot/dataset
capture-path behaviour. NO Isaac, ROS 2, camera, robot, model, dataset, image, trajectory or rosbag.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from scripts.gnm import h8_evidence_schema as es  # noqa: E402
from scripts.gnm import h8_synthetic_fork_recorded_mode as rm  # noqa: E402

RT = "2026-07-16T12:00:00Z"  # injected review time, inside the default fixture window
SCHEMA_PATH = REPO / "docs/research/schemas/h8_evidence_envelope.schema.json"
DRYRUN_DIR = REPO / "assets/experiments/hospital_h8_track_b_synthetic_fork_recorded_mode_dataset_dryrun"

# canonical Level-1 SHA-256 prefixes (frozen at commit 66fd81e; must never change here)
_L1_HASHES = {
    "dataset_dryrun_manifest.json": "3833714d5dbf20a9",
    "dataset_plan_schema.json": "915e34f0430b6213",
    "dataset_split_validation_dryrun.json": "de70f96f74cd2d79",
    "dataset_leakage_audit_dryrun.json": "84eaea5277b7b1af",
    "dataset_dryrun_report.md": "02ce0c17fe2bf889",
}


def _expected(env):
    s = env["subject"]
    return {k: s[k] for k in ("dataset_plan_id", "instance_id", "split", "scene_id", "scene_digest",
                              "route_id", "route_plan_digest", "config_digest", "cl_bound_xy",
                              "coordinate_frame")}


def _reject(env, **kw):
    """Validate an envelope expecting rejection; return its reason code."""
    r = es.validate_envelope(env, review_time=RT, **kw)
    assert r["accepted"] is False, f"expected rejection, got {r}"
    return r["reason_code"]


# ── 1–3 acceptance ────────────────────────────────────────────────────────────────
def test_01_valid_render_accepted():
    r = es.synthetic_render_evidence()
    res = es.validate_envelope(r, review_time=RT, expected=_expected(r))
    assert res["accepted"] is True and res["reason_code"] == es.ACCEPTED


def test_02_valid_drive_accepted():
    d = es.synthetic_drive_evidence()
    res = es.validate_envelope(d, review_time=RT, expected=_expected(d))
    assert res["accepted"] is True


def test_03_valid_paired_accepted():
    rp, dp = es.synthetic_paired_evidence()
    res = es.validate_pair(rp, dp, review_time=RT, expected=_expected(rp))
    assert res["accepted"] is True


# ── 4–5 missing sides ───────────────────────────────────────────────────────────────
def test_04_missing_render_rejected():
    _, dp = es.synthetic_paired_evidence()
    r = es.validate_pair(None, dp, review_time=RT)
    assert r["accepted"] is False and r["reason_code"] == es.PAIR_INCOMPLETE


def test_05_missing_drive_rejected():
    rp, _ = es.synthetic_paired_evidence()
    r = es.validate_pair(rp, None, review_time=RT)
    assert r["accepted"] is False and r["reason_code"] == es.PAIR_INCOMPLETE


# ── 6–8 status + revocation ───────────────────────────────────────────────────────
def test_06_invalid_status_rejected():
    assert _reject(es.synthetic_render_evidence(status="invalid")) == es.STATUS_NOT_VALID


def test_07_indeterminate_status_rejected():
    assert _reject(es.synthetic_render_evidence(status="indeterminate")) == es.STATUS_NOT_VALID


def test_08_revoked_rejected():
    assert _reject(es.synthetic_render_evidence(**{"revocation.revoked": True})) == es.EVIDENCE_REVOKED
    assert _reject(es.synthetic_render_evidence(status="revoked")) == es.EVIDENCE_REVOKED


# ── 9–10 freshness ────────────────────────────────────────────────────────────────
def test_09_expired_rejected():
    env = es.synthetic_render_evidence(**{
        "observation_time": "2026-07-01T00:00:00Z", "issue_time": "2026-07-01T00:00:01Z",
        "validity_window.not_before": "2026-07-01T00:00:00Z",
        "validity_window.not_after": "2026-07-08T00:00:00Z"})
    assert _reject(env) == es.EVIDENCE_EXPIRED


def test_10_future_not_yet_valid_rejected():
    env = es.synthetic_render_evidence(**{
        "validity_window.not_before": "2026-08-01T00:00:00Z",
        "validity_window.not_after": "2026-08-08T00:00:00Z"})
    assert _reject(env) == es.EVIDENCE_NOT_YET_VALID


# ── 11–12 schema / timestamp ──────────────────────────────────────────────────────
def test_11_unsupported_schema_version_rejected():
    assert _reject(es.synthetic_render_evidence(schema_version="h8-evidence/0.9.0")) == \
        es.SCHEMA_VERSION_UNSUPPORTED


def test_12_malformed_timestamp_rejected():
    assert _reject(es.synthetic_render_evidence(observation_time="not-a-timestamp")) == \
        es.SCHEMA_MALFORMED
    # a naive (tz-less) timestamp is also rejected
    assert _reject(es.synthetic_render_evidence(observation_time="2026-07-16T00:00:00")) == \
        es.SCHEMA_MALFORMED


# ── 13–18 identity binding ────────────────────────────────────────────────────────
def test_13_instance_mismatch_rejected():
    r = es.synthetic_render_evidence()
    exp = {**_expected(r), "instance_id": "sfork_07"}
    assert _reject(r, expected=exp) == es.INSTANCE_MISMATCH


def test_14_scene_mismatch_rejected():
    r = es.synthetic_render_evidence()
    assert _reject(r, expected={**_expected(r), "scene_id": "other_scene"}) == es.SCENE_MISMATCH


def test_15_route_mismatch_rejected():
    r = es.synthetic_render_evidence()
    assert _reject(r, expected={**_expected(r), "route_id": "sfork_00_W"}) == es.ROUTE_MISMATCH


def test_16_config_mismatch_rejected():
    r = es.synthetic_render_evidence()
    assert _reject(r, expected={**_expected(r), "config_digest": "sha256:" + "d" * 64}) == \
        es.CONFIG_MISMATCH


def test_17_coordinate_frame_mismatch_rejected():
    r = es.synthetic_render_evidence()
    assert _reject(r, expected={**_expected(r), "coordinate_frame": "map"}) == es.FRAME_MISMATCH


def test_18_cl_bound_mismatch_rejected():
    # subject.cl_bound_xy != the 6.0 watchdog is rejected even without an expected binding
    assert _reject(es.synthetic_render_evidence(**{"subject.cl_bound_xy": 7.0})) == es.BOUND_MISMATCH


# ── 19–21 integrity / window / duplicate ──────────────────────────────────────────
def test_19_digest_mismatch_rejected():
    r = es.synthetic_render_evidence()
    r["subject"]["scene_id"] = "tampered-after-seal"  # invalidates subject + content digest
    assert _reject(r) == es.DIGEST_MISMATCH


def test_20_validity_window_mismatch_rejected():
    env = es.synthetic_render_evidence(**{
        "validity_window.not_before": "2026-07-23T00:00:00Z",
        "validity_window.not_after": "2026-07-16T00:00:00Z"})  # not_after <= not_before
    assert _reject(env) == es.VALIDITY_WINDOW_MISMATCH


def test_21_duplicate_evidence_id_rejected():
    r = es.synthetic_render_evidence()
    assert _reject(r, seen_ids={r["evidence_id"]}) == es.DUPLICATE_EVIDENCE_ID


# ── 22 unknown-field policy ───────────────────────────────────────────────────────
def test_22_unknown_field_rejected():
    r = es.synthetic_render_evidence(**{"unexpected_field": True})
    assert _reject(r) == es.SCHEMA_MALFORMED


# ── 23 reason-code stability ──────────────────────────────────────────────────────
def test_23_reason_codes_stable_and_result_shaped():
    r = es.synthetic_render_evidence(status="invalid")
    res = es.validate_envelope(r, review_time=RT)
    for key in ("accepted", "reason_code", "explanation", "evidence_id", "instance_id",
                "evidence_type", "failed_field", "expected", "observed", "schema_version",
                "validator_version"):
        assert key in res
    assert res["reason_code"] in es.REASON_CODES
    assert res["validator_version"] == es.VALIDATOR_VERSION


# ── 24 no filesystem output ───────────────────────────────────────────────────────
def test_24_no_filesystem_output_created():
    before = set(p.name for p in REPO.glob("assets/experiments/*"))
    for _ in range(3):
        es.validate_envelope(es.synthetic_render_evidence(), review_time=RT)
        es.validate_pair(*es.synthetic_paired_evidence(), review_time=RT)
    after = set(p.name for p in REPO.glob("assets/experiments/*"))
    assert before == after
    # the dataset capture output directory must never be created by this module
    assert not (REPO / "assets/experiments/"
                "hospital_h8_track_b_synthetic_fork_recorded_mode_dataset").exists()


# ── 25 no forbidden imports ───────────────────────────────────────────────────────
def test_25_no_isaac_ros_model_capture_import():
    src = (REPO / "scripts/gnm/h8_evidence_schema.py").read_text()
    for token in ("import omni", "isaacsim", "from omni", "rclpy", "import torch", "SimulationApp",
                  "open(", "Path("):
        assert token not in src, f"forbidden token {token!r} in evidence schema module"
    for mod in ("omni", "isaacsim", "rclpy", "torch"):
        assert mod not in sys.modules, f"{mod} unexpectedly imported"


# ── 26 recorded-mode harness unperturbed ──────────────────────────────────────────
def test_26_recorded_mode_dry_run_still_25_of_25():
    cfg = rm.load_dataset_config(
        REPO / "configs/gnm/h8_synthetic_fork_recorded_mode_dataset.yaml")
    res = rm.dataset_dry_run_checks(cfg)
    assert res["all_pass"] is True and res["n_total"] == 25 and res["n_pass"] == 25


# ── 27 Level-1 evidence hashes preserved ──────────────────────────────────────────
def test_27_level1_evidence_hashes_unchanged():
    for name, prefix in _L1_HASHES.items():
        h = hashlib.sha256((DRYRUN_DIR / name).read_bytes()).hexdigest()
        assert h[:16] == prefix, f"{name} Level-1 hash changed"


# ── 28 pilot + routing behaviour unchanged ────────────────────────────────────────
def test_28_pilot_and_routing_unchanged():
    assert rm.select_capture_mode({"mode": "pilot_capture_config_only"}) == "pilot"
    assert rm.select_capture_mode({"mode": "dataset_capture_config_only"}) == "dataset"
    assert rm.select_capture_mode({"mode": "???"}) == "unknown"
    for sym in ("validate_pilot_config", "pilot_capture_plan", "_run_pilot_capture"):
        assert hasattr(rm, sym)


# ── 29 empty-plan graceful (H8-REV-F-003) ─────────────────────────────────────────
def test_29_empty_plan_graceful_and_fail_closed():
    import copy
    cfg = rm.load_dataset_config(
        REPO / "configs/gnm/h8_synthetic_fork_recorded_mode_dataset.yaml")
    empty = copy.deepcopy(cfg)
    empty.pop("instance_plan", None)
    res = rm.dataset_dry_run_checks(empty)          # must NOT raise
    assert res["all_pass"] is False and res.get("empty_plan") is True
    ok, issues = rm.validate_dataset_capture_config(empty)
    assert ok is False


# ── 30 deterministic canonicalisation ─────────────────────────────────────────────
def test_30_canonicalisation_deterministic():
    a = {"b": 1, "a": 2, "c": {"y": 1, "x": 2}}
    b = {"c": {"x": 2, "y": 1}, "a": 2, "b": 1}
    assert es.canonical_bytes(a) == es.canonical_bytes(b)
    assert es.content_digest(a) == es.content_digest(b)
    # sealing a fixture twice is reproducible
    assert es.synthetic_render_evidence()["integrity"] == es.synthetic_render_evidence()["integrity"]


# ── extra: pairing + signature + production guard + schema-file consistency ────────
def test_extra_pair_binding_mismatch_rejected():
    rp, dp = es.synthetic_paired_evidence()
    dp["subject"]["scene_digest"] = "sha256:" + "e" * 64
    dp = es._seal(dp)  # keep internally consistent so we exercise the PAIR check, not DIGEST
    r = es.validate_pair(rp, dp, review_time=RT)
    assert r["accepted"] is False and r["reason_code"] == es.PAIR_BINDING_MISMATCH


def test_extra_signature_required_but_unverified_rejected():
    r = es.synthetic_render_evidence(verified=False)
    assert _reject(r, require_signature=True) == es.SIGNATURE_UNVERIFIED
    ok = es.synthetic_render_evidence(verified=True)
    assert es.validate_envelope(ok, review_time=RT, require_signature=True)["accepted"] is True


def test_extra_fixture_rejected_in_production():
    r = es.synthetic_render_evidence()
    assert _reject(r, production_mode=True) == es.FIXTURE_IN_PRODUCTION


def test_extra_schema_file_matches_validator_contract():
    schema = json.loads(SCHEMA_PATH.read_text())
    assert set(schema["required"]) == es._ENVELOPE_KEYS
    assert schema["properties"]["schema_version"]["const"] == es.SCHEMA_VERSION
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["subject"]["properties"]["cl_bound_xy"]["const"] == es.CL_BOUND_XY
