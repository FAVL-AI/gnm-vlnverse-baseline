"""tests/gnm/test_h8_synthetic_fork_dataset_config.py

Lightweight validation for the full recorded-mode dataset CAPTURE CONFIG
(configs/gnm/h8_synthetic_fork_recorded_mode_dataset.yaml). These run WITHOUT Isaac and WITHOUT any
capture: they parse the committed config and assert it is a capture-DEFINITION that authorizes nothing
— no capture, no training, no policy/model/action-probe, no rollout metrics, no checkpoints/weights —
enforces the committed minimum scale + split policy, plans >= 6 disjoint render/drive-gated instances,
and writes to a dataset-only output path. `CL_BOUND_XY` must stay 6.0 (read-only reference).
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

CONFIG_PATH = REPO / "configs/gnm/h8_synthetic_fork_recorded_mode_dataset.yaml"
ROLLOUT_METRIC_KEYS = ("TL", "NE", "SR", "OSR", "SPL", "nDTW", "CR")

PILOT_DIR = "assets/experiments/hospital_h8_track_b_synthetic_fork_recorded_mode_pilot"
DRYRUN_DIR = "assets/experiments/hospital_h8_track_b_synthetic_fork_recorded_mode_dryrun"
FULL_RECMODE_DIR = "assets/experiments/hospital_h8_track_b_synthetic_fork_recorded_mode"


def _cfg() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text())


def _all_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _all_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _all_keys(v)


# ── parses + claim boundary + mode ────────────────────────────────────────────
def test_config_parses_and_has_dataset_mode():
    cfg = _cfg()
    assert isinstance(cfg, dict)
    assert cfg["claim_boundary"] == "SYNTHETIC_DIAGNOSTIC_ONLY"
    assert cfg["mode"] == "dataset_capture_config_only"


# ── authorizes nothing ────────────────────────────────────────────────────────
def test_authorizes_capture_is_false():
    assert _cfg()["authorizes_capture"] is False


def test_authorizes_training_is_false():
    assert _cfg()["authorizes_training"] is False


def test_config_does_not_authorize_capture_or_training():
    cfg = _cfg()
    assert cfg["authorizes_capture"] is False and cfg["authorizes_training"] is False
    cc = cfg["capture_controls"]
    assert cc["training"] is False and cc["policy_inference"] is False


# ── output path is dataset-only, distinct from pilot / dry-run / full-recmode ──
def test_output_path_is_dataset_only():
    out = _cfg()["output_dir"].rstrip("/")
    assert out.endswith("_recorded_mode_dataset"), f"output must be dataset-only: {out}"
    assert out not in (PILOT_DIR, DRYRUN_DIR, FULL_RECMODE_DIR)


# ── no rollout metric keys / no checkpoint-weight-wandb authorization ─────────
def test_no_rollout_metric_keys():
    cfg = _cfg()
    keys = set(_all_keys(cfg))
    for m in ROLLOUT_METRIC_KEYS:
        assert m not in keys, f"rollout metric key {m} must not appear as a config key"
    assert "rollout_metrics" in cfg["forbidden_outputs"]


def test_no_checkpoint_weight_wandb_authorization():
    forb = _cfg()["forbidden_outputs"]
    for x in ("checkpoints", "weights", "wandb", "benchmark_tables", "model_outputs",
              "action_probe_outputs"):
        assert x in forb, f"{x} must be a forbidden output"


# ── no policy/model/action-probe/training authorization ───────────────────────
def test_no_policy_model_action_probe_training_authorization():
    cc = _cfg()["capture_controls"]
    for k in ("policy_inference", "model_inference", "closed_loop_policy_execution", "action_probe",
              "training"):
        assert cc[k] is False, f"capture_controls.{k} must be false"
    assert cc["scripted_poses_only"] is True and cc["config_driven"] is True


# ── minimum scale + instance count ────────────────────────────────────────────
def test_minimum_scale_meets_committed_target():
    ms = _cfg()["minimum_scale"]
    assert ms["min_train"] >= 12
    assert ms["min_val"] >= 4
    assert ms["min_test"] >= 6
    assert ms["min_disjoint_instances"] >= 6


def test_planned_instance_count_is_at_least_six():
    ip = _cfg()["instance_plan"]
    assert ip["min_planned_instances"] >= 6
    ids = [i["id"] for i in ip["instances"]]
    assert len(ids) >= 6, f"need >= 6 planned instances, got {len(ids)}"
    assert len(set(ids)) == len(ids), "planned instance IDs must be unique"


# ── split policy forbids frame/goal/coordinate reuse ──────────────────────────
def test_split_policy_forbids_reuse():
    sp = _cfg()["split_policy"]
    assert sp["split_assignment_before_training"] is True
    assert sp["no_decision_frame_reuse_across_splits"] is True
    assert sp["no_goal_image_reuse_across_splits"] is True
    assert sp["no_coordinate_reuse_across_splits"] is True
    # instance leakage is forbidden unless explicitly justified AND marked unsafe
    assert sp["no_instance_leakage_across_splits"] is True
    assert sp["allow_instance_leakage_across_splits"] is False


def test_planned_instances_have_disjoint_coordinate_offsets_and_splits():
    ip = _cfg()["instance_plan"]
    offsets = [tuple(i["coord_offset"]) for i in ip["instances"]]
    assert len(set(offsets)) == len(offsets), "instance coordinate offsets must be disjoint"
    # every split is represented so a leakage-safe train/val/test split is achievable
    splits = {i["split"] for i in ip["instances"]}
    assert {"train", "val", "test"} <= splits


# ── each instance requires render-valid and drive-valid gates ─────────────────
def test_each_instance_requires_render_and_drive_validity():
    for i in _cfg()["instance_plan"]["instances"]:
        assert i["render_valid_required"] is True, f"{i['id']} must require render validity"
        assert i["drive_valid_required"] is True, f"{i['id']} must require drive validity"


# ── route families + artifacts present ────────────────────────────────────────
def test_route_families_primary_and_secondary():
    rf = _cfg()["route_families"]
    assert rf["N_vs_W_90"] == "primary"
    assert rf.get("N_vs_E_90") == "secondary"
    assert rf.get("W_vs_E_180") == "secondary"
    assert rf.get("near_far_stop_distance") == "secondary"
    assert rf.get("hard_negative_mismatched_goal") == "hard_negative"


def test_required_dataset_artifacts_and_pass_checks_present():
    cfg = _cfg()
    for a in ("full_recorded_mode_manifest", "image_index", "action_label_table", "split_manifest",
              "contact_log", "provenance_table", "leakage_audit_report", "recording_report"):
        assert a in cfg["required_future_dataset_artifacts"], f"missing artifact {a}"
    for c in ("minimum_scale_met", "planned_disjoint_instances_present", "images_non_empty",
              "labels_populated", "provenance_present", "ambiguous_contacts_zero",
              "leakage_audit_passes", "no_policy_model_inference", "no_training_fields",
              "no_rollout_metrics"):
        assert c in cfg["pass_fail_checks"], f"missing pass/fail check {c}"


# ── CL_BOUND_XY stays 6.0 and read-only, consistent with the harness ──────────
def test_cl_bound_xy_is_six_and_readonly():
    cfg = _cfg()
    assert cfg["cl_bound_xy"] == 6.0
    assert cfg["cl_bound_xy_readonly"] is True
    from scripts.gnm import h8_synthetic_fork_recorded_mode as rm
    assert cfg["cl_bound_xy"] == rm.CL_BOUND_XY == 6.0


if __name__ == "__main__":
    import pytest as _pt
    raise SystemExit(_pt.main([__file__, "-q"]))
