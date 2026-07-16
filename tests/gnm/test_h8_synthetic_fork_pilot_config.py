"""tests/gnm/test_h8_synthetic_fork_pilot_config.py

Lightweight validation for the tiny recorded-mode pilot CAPTURE CONFIG
(configs/gnm/h8_synthetic_fork_recorded_mode_pilot.yaml). These run WITHOUT Isaac and WITHOUT any
capture: they only parse the committed config and assert it is a capture-DEFINITION that authorizes
nothing — no capture, no training, no policy/model/action-probe, no rollout metrics, no full dataset —
and that its planned output path is pilot-only. `CL_BOUND_XY` must stay 6.0 (read-only reference).
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

CONFIG_PATH = REPO / "configs/gnm/h8_synthetic_fork_recorded_mode_pilot.yaml"
ROLLOUT_METRIC_KEYS = ("TL", "NE", "SR", "OSR", "SPL", "nDTW", "CR")

# full-dataset / dry-run dirs the pilot output must NOT collide with
FULL_DATASET_DIR = "assets/experiments/hospital_h8_track_b_synthetic_fork_recorded_mode/"
DRYRUN_DIR = "assets/experiments/hospital_h8_track_b_synthetic_fork_recorded_mode_dryrun/"


def _cfg() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text())


def _all_keys(obj):
    """Recursively yield every mapping KEY in a parsed config (for metric-key scanning)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _all_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _all_keys(v)


# ── parses + claim boundary ───────────────────────────────────────────────────
def test_config_parses_and_has_pilot_mode():
    cfg = _cfg()
    assert isinstance(cfg, dict)
    assert cfg["claim_boundary"] == "SYNTHETIC_DIAGNOSTIC_ONLY"
    assert cfg["mode"] == "pilot_capture_config_only"


# ── authorizes nothing ────────────────────────────────────────────────────────
def test_authorizes_capture_is_false():
    assert _cfg()["authorizes_capture"] is False


def test_authorizes_training_is_false():
    assert _cfg()["authorizes_training"] is False


# ── no rollout metric keys anywhere ───────────────────────────────────────────
def test_no_rollout_metric_keys():
    cfg = _cfg()
    keys = set(_all_keys(cfg))
    for m in ROLLOUT_METRIC_KEYS:
        assert m not in keys, f"rollout metric key {m} must not appear as a config key"
    # 'rollout_metrics' may only appear as a FORBIDDEN-list entry, never as an emitted metric
    assert "rollout_metrics" in cfg["forbidden_outputs"]


# ── no train/val/test dataset authorization ───────────────────────────────────
def test_no_train_val_test_dataset_authorization():
    cfg = _cfg()
    assert cfg["pilot_scope"]["full_train_val_test_dataset"] is False
    assert "train_val_test_dataset_files" in cfg["forbidden_outputs"]


# ── no policy/model/action-probe authorization ────────────────────────────────
def test_no_policy_model_action_probe_authorization():
    cc = _cfg()["capture_controls"]
    assert cc["policy_inference"] is False
    assert cc["model_inference"] is False
    assert cc["closed_loop_policy_execution"] is False
    assert cc["action_probe"] is False
    assert cc["training"] is False
    assert cc["scripted_poses_only"] is True
    assert "action_probe_outputs" in _cfg()["forbidden_outputs"]
    assert "model_outputs" in _cfg()["forbidden_outputs"]


# ── CL_BOUND_XY stays 6.0 and read-only, consistent with the harness ──────────
def test_cl_bound_xy_is_six_and_readonly():
    cfg = _cfg()
    assert cfg["cl_bound_xy"] == 6.0
    assert cfg["cl_bound_xy_readonly"] is True
    # must equal the committed harness watchdog (single source), not a divergent literal
    from scripts.gnm import h8_synthetic_fork_recorded_mode as rm
    assert cfg["cl_bound_xy"] == rm.CL_BOUND_XY == 6.0


# ── output path is pilot-only, distinct from full-dataset + dry-run dirs ──────
def test_output_path_is_pilot_only_not_full_dataset():
    out = _cfg()["output_dir"]
    assert out.rstrip("/").endswith("_recorded_mode_pilot"), f"output must be pilot-only: {out}"
    assert out != FULL_DATASET_DIR, "pilot must NOT write to the full-dataset directory"
    assert out != DRYRUN_DIR, "pilot must NOT write to the dry-run directory"


# ── pilot scope is tiny; artifacts + checks present ───────────────────────────
def test_pilot_scope_is_tiny_and_primary_is_n_vs_w():
    sc = _cfg()["pilot_scope"]
    assert sc["max_instances"] <= 2 and sc["max_decision_frames"] <= 2
    assert sc["primary_route_family"] == "N_vs_W_90"
    assert sc["optional_secondary_route_family"] == "N_vs_E_90"
    assert sc["benchmark_claim"] is False


def test_required_artifacts_and_pass_checks_present():
    cfg = _cfg()
    for a in ("pilot_manifest", "pilot_image_index", "pilot_action_label_table", "pilot_contact_log",
              "pilot_provenance_table", "pilot_leakage_audit_report", "pilot_recording_report"):
        assert a in cfg["required_future_pilot_artifacts"], f"missing pilot artifact {a}"
    for c in ("images_non_empty", "labels_populated", "contact_logs_present", "obstacle_contacts_zero",
              "metadata_ids_unique", "leakage_audit_runs", "no_policy_model_path_touched",
              "no_training_fields"):
        assert c in cfg["pass_fail_checks"], f"missing pass/fail check {c}"


def test_full_dataset_target_documented():
    t = _cfg()["full_dataset_target"]
    assert t["min_train"] >= 12 and t["min_val"] >= 4 and t["min_test"] >= 6
    assert t["min_disjoint_instances"] >= 6
    assert t["no_decision_frame_reuse_across_splits"] is True
    assert t["no_goal_image_reuse_across_splits"] is True
    assert t["no_coordinate_reuse_across_splits"] is True
    assert t["leakage_audit_required_before_action_probe_or_training"] is True


if __name__ == "__main__":
    import pytest as _pt
    raise SystemExit(_pt.main([__file__, "-q"]))
