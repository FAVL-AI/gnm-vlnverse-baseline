"""tests/gnm/test_h8_synthetic_fork_recorded_mode.py

Lightweight unit tests for the synthetic-fork RECORDED-MODE harness
(scripts/gnm/h8_synthetic_fork_recorded_mode.py). They run WITHOUT Isaac and WITHOUT any capture:
they exercise the pure-python config / schema / scripted-action / and — critically — the fail-closed
leakage-audit logic that makes a leaky or single-instance split impossible to certify. They also
assert the harness carries no policy/model import and no training/checkpoint/rollout-metric fields,
and that forbidden flags are refused.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from scripts.gnm import h8_synthetic_fork_recorded_mode as rm  # noqa: E402

HARNESS_SRC = (REPO / "scripts/gnm/h8_synthetic_fork_recorded_mode.py").read_text()


def _rec(instance, dframe, goal, split, dxy, gxy, branch="N"):
    r = rm.example_record_schema()
    r.update({"instance_id": instance, "decision_frame_id": dframe, "goal_image_id": goal,
              "split": split, "decision_xy": list(dxy), "goal_xy": list(gxy), "branch": branch,
              "action_class": rm.scripted_action_for_branch(branch),
              "route_family": "N_vs_W_90"})
    return r


def _leakage_safe_set():
    """A small leakage-safe set: 6 disjoint instances, disjoint frame/goal ids + coordinates, and
    per-split minimums met (train>=12, val>=4, test>=6)."""
    recs = []
    n = 0
    # 6 train instances x2 frames, 2 val x2, 3 test x2 => train12 val4 test6, 11 instances
    layout = [("train", 6), ("val", 2), ("test", 3)]
    for split, n_inst in layout:
        for _ in range(n_inst):
            for k in range(2):
                n += 1
                recs.append(_rec(f"inst{n}", f"df{n}", f"gi{n}",
                                 split, (n * 1.0, 0.0), (n * 1.0, 3.0)))
    return recs


# ── fail-closed leakage audit ─────────────────────────────────────────────────
def test_single_instance_is_not_leakage_safe():
    # one cross instance alone can NEVER be split leakage-safe
    recs = [_rec("only", f"df{i}", f"gi{i}", "train", (i, 0), (i, 3)) for i in range(3)]
    a = rm.audit_examples(recs)
    assert a["single_instance_not_leakage_safe"] is True
    assert a["leakage_safe"] is False
    assert a["audit_pass"] is False
    assert "single_instance_not_leakage_safe" in a["reasons"]


def test_reused_decision_frame_id_across_splits_is_caught():
    recs = [_rec("i1", "SHARED_DF", "gi1", "train", (1, 0), (1, 3)),
            _rec("i2", "SHARED_DF", "gi2", "test", (2, 0), (2, 3))]
    a = rm.audit_examples(recs)
    assert "SHARED_DF" in a["reused_decision_frames_across_splits"]
    assert a["leakage_safe"] is False and "reused_decision_frame_across_splits" in a["reasons"]


def test_reused_goal_image_id_across_splits_is_caught():
    recs = [_rec("i1", "df1", "SHARED_GOAL", "train", (1, 0), (1, 3)),
            _rec("i2", "df2", "SHARED_GOAL", "val", (2, 0), (2, 3))]
    a = rm.audit_examples(recs)
    assert "SHARED_GOAL" in a["reused_goal_images_across_splits"]
    assert a["leakage_safe"] is False and "reused_goal_image_across_splits" in a["reasons"]


def test_reused_coordinate_across_splits_is_caught():
    # same physical decision coordinate (0,0) in two splits -> variants must translate; audit catches it
    recs = [_rec("i1", "df1", "gi1", "train", (0.0, 0.0), (0.0, 3.0)),
            _rec("i2", "df2", "gi2", "test", (0.0, 0.0), (5.0, 3.0))]
    a = rm.audit_examples(recs)
    assert a["reused_coordinates_across_splits"], "coordinate reuse must be flagged"
    assert a["leakage_safe"] is False and "reused_coordinate_across_splits" in a["reasons"]


def test_empty_set_is_not_leakage_safe():
    a = rm.audit_examples([])
    assert a["leakage_safe"] is False and a["audit_pass"] is False
    assert "empty_no_examples" in a["reasons"]


def test_below_min_scale_does_not_pass_even_if_disjoint():
    # 2 disjoint instances, disjoint ids/coords, but below the 12/4/6 + 6-instance targets
    recs = [_rec("i1", "df1", "gi1", "train", (1, 0), (1, 3)),
            _rec("i2", "df2", "gi2", "test", (2, 0), (2, 3))]
    a = rm.audit_examples(recs)
    assert a["meets_min_scale"] is False and a["audit_pass"] is False and "below_min_scale" in a["reasons"]


def test_leakage_safe_set_passes_audit():
    a = rm.audit_examples(_leakage_safe_set())
    assert a["single_instance_not_leakage_safe"] is False
    assert a["reused_decision_frames_across_splits"] == []
    assert a["reused_goal_images_across_splits"] == []
    assert a["reused_coordinates_across_splits"] == []
    assert a["leakage_safe"] is True
    assert a["meets_min_scale"] is True, f"per-split {a['per_split_counts']} instances {a['n_instances']}"
    assert a["audit_pass"] is True and a["reasons"] == []


# ── config / dry-run without Isaac ────────────────────────────────────────────
def test_validate_config_works_without_isaac():
    ok, issues, summary = rm.validate_config()
    assert ok, f"config invalid: {issues}"
    assert summary["claim_boundary"] == "SYNTHETIC_DIAGNOSTIC_ONLY"
    assert summary["cl_bound_xy_readonly"] == 6.0


def test_main_validate_config_returns_zero_without_isaac():
    assert rm.main(["--mode", "validate-config"]) == 0


def test_dry_run_without_emit_writes_nothing(tmp_path):
    # dry-run without --emit-schema must write no files (no capture, no schema file)
    rc = rm.main(["--mode", "dry-run", "--out-dir", str(tmp_path)])
    assert rc == 0
    assert list(tmp_path.iterdir()) == []


def test_dry_run_emit_writes_the_four_named_artifacts(tmp_path):
    import json
    rc = rm.main(["--mode", "dry-run", "--emit-schema", "--out-dir", str(tmp_path)])
    assert rc == 0
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == ["recorded_mode_dryrun_manifest.json", "recorded_mode_dryrun_report.md",
                     "recorded_mode_leakage_audit_dryrun.json", "recorded_mode_schema.json"]
    # no real capture artifacts of any kind
    assert not any(p.suffix in (".png", ".jpg", ".npy", ".bag", ".pt", ".ckpt", ".pkl")
                   for p in tmp_path.iterdir())

    # leakage-audit dry-run must carry the dummy cases and all must behave as expected
    audit = json.loads((tmp_path / "recorded_mode_leakage_audit_dryrun.json").read_text())
    case_names = {c["case"] for c in audit["cases"]}
    for required in ("one_instance_dataset_fails", "reused_decision_frame_id_fails",
                     "reused_goal_image_id_fails", "reused_coordinate_fails",
                     "insufficient_scale_fails", "valid_multi_instance_plan_passes"):
        assert required in case_names, f"missing dry-run audit case {required}"
    assert audit["all_cases_pass"] is True
    assert all(c["case_pass"] for c in audit["cases"])

    # schema file carries the three committed schemas; no rollout metric / real-capture data fields
    schema = json.loads((tmp_path / "recorded_mode_schema.json").read_text())
    for key in ("manifest_schema", "example_record_schema", "leakage_audit_schema"):
        assert key in schema
    blob = (tmp_path / "recorded_mode_schema.json").read_text() + \
        (tmp_path / "recorded_mode_dryrun_manifest.json").read_text()
    for metric in rm.FORBIDDEN_METRIC_KEYS:
        assert f'"{metric}"' not in blob, f"rollout metric {metric} must not appear in dry-run output"
    # example rgb-path templates must be null (no real image was captured)
    ex = rm.example_record_schema()
    assert ex["decision_rgb_path"] is None and ex["goal_rgb_path"] is None


def test_dry_run_audit_cases_helper_matches_required_set():
    cases = rm.dry_run_audit_cases()
    assert {c["case"] for c in cases} == {
        "one_instance_dataset_fails", "reused_decision_frame_id_fails", "reused_goal_image_id_fails",
        "reused_coordinate_fails", "insufficient_scale_fails", "valid_multi_instance_plan_passes"}
    assert all(c["case_pass"] for c in cases)


# ── no policy/model imports; no training/checkpoint/rollout fields ────────────
def test_no_policy_or_model_import_at_module_level():
    import ast
    tree = ast.parse(HARNESS_SRC)
    module_imports = []
    for node in tree.body:  # module-level only (Isaac imports are deferred inside run_capture)
        if isinstance(node, ast.Import):
            module_imports += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            module_imports.append(node.module or "")
    forbidden = ("torch", "timm", "tensorflow", "isaacsim", "omni", "pxr", "wandb")
    for name in module_imports:
        assert not any(f in name.lower() for f in forbidden), f"forbidden module-level import: {name}"
    for token in ("load_state_dict(", "torch.load(", ".load_weights(", "best.pt", "from_pretrained(",
                  "wandb.", "save_checkpoint("):
        assert token not in HARNESS_SRC, f"forbidden loading/checkpoint call in harness: {token}"


def test_schema_has_no_training_checkpoint_or_rollout_fields():
    for schema in (rm.recorded_mode_manifest_schema(), rm.example_record_schema(),
                   rm.leakage_audit_schema()):
        for k in rm.FORBIDDEN_METRIC_KEYS:
            assert k not in schema, f"rollout metric {k} must not be a schema field"
        # `no_*` keys are explicit NEGATION assertions (e.g. no_rollout_metrics=True) and are allowed;
        # any real training/checkpoint/rollout DATA field is not.
        data_keys = [key for key in schema if not key.lower().startswith("no_")]
        for bad in ("train_", "checkpoint", "weight", "reward", "loss", "rollout_metric", "wandb"):
            assert not any(bad in key.lower() for key in data_keys), f"forbidden-ish field '{bad}' in schema"
    # manifest explicitly asserts no policy/training/rollout
    m = rm.recorded_mode_manifest_schema()
    assert m["no_policy_inference"] is True and m["no_training"] is True and m["no_rollout_metrics"] is True


def test_scripted_actions_are_policy_free_and_geometry_derived():
    assert rm.scripted_action_for_branch("N") == "STRAIGHT"
    assert rm.scripted_action_for_branch("W") == "TURN_LEFT_90"
    assert rm.scripted_action_for_branch("E") == "TURN_RIGHT_90"
    bc = rm.branch_choice_label("W")
    assert bc["policy_driven"] is False and bc["action_class"] == "TURN_LEFT_90"
    import pytest
    with pytest.raises(ValueError):
        rm.scripted_action_for_branch("Q")


# ── forbidden flags are refused ───────────────────────────────────────────────
def test_forbidden_flags_are_refused():
    import pytest
    for flag in ("--train", "--action-probe", "--rollout", "--closed-loop", "--promote", "--collect"):
        with pytest.raises(SystemExit) as ei:
            rm.main([flag])
        assert ei.value.code != 0, f"{flag} must cause a nonzero refusal exit"


def test_cl_bound_xy_is_readonly_mirror_of_six():
    # recorded-mode mirrors the drive-validation watchdog; it must not redefine/modify it
    assert rm.CL_BOUND_XY == 6.0
    # the value comes from the drive-validation harness (single source), not a local literal edit
    from scripts.gnm import h8_synthetic_fork_drive_validate as dv
    assert rm.CL_BOUND_XY == dv.CL_BOUND_XY


if __name__ == "__main__":
    import pytest as _pt
    raise SystemExit(_pt.main([__file__, "-q"]))
