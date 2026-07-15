"""tests/gnm/test_h8_synthetic_fork_drive_validate.py

Lightweight unit tests for the synthetic-fork drive-validation HARNESS
(scripts/gnm/h8_synthetic_fork_drive_validate.py). These run WITHOUT Isaac and WITHOUT any drive run:
they exercise the pure-python config/scene-identity/probe-plan/schema/safe-halt/refusal logic and
assert the harness carries no policy/model import and no rollout-metric / training fields.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from scripts.gnm import h8_synthetic_fork_drive_validate as dv  # noqa: E402

HARNESS_SRC = (REPO / "scripts/gnm/h8_synthetic_fork_drive_validate.py").read_text()


def test_no_policy_or_model_import_at_module_level():
    # The harness must not import or reference any policy/model/checkpoint/learning framework at
    # module scope. Isaac is allowed only deferred inside run_isaac(); check no ML frameworks appear.
    import ast
    tree = ast.parse(HARNESS_SRC)
    module_imports = []
    for node in tree.body:  # module-level only (deferred imports live inside functions)
        if isinstance(node, ast.Import):
            module_imports += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            module_imports.append(node.module or "")
    forbidden = ("torch", "timm", "tensorflow", "gnm", "policy", "model", "isaacsim", "omni", "pxr")
    for name in module_imports:
        assert not any(f in name.lower() for f in forbidden), f"forbidden module-level import: {name}"
    # and no actual checkpoint/weights LOADING call anywhere in the source (call-shaped tokens that
    # would never appear in the prose comments; the word "checkpoint" alone is allowed in a
    # "we do NOT load checkpoints" comment).
    for token in ("load_state_dict(", "torch.load(", ".load_weights(", "best.pt", "from_pretrained("):
        assert token not in HARNESS_SRC, f"forbidden loading call in harness: {token}"


def test_output_schema_only_validation_fields():
    schema = dv.output_schema()
    # no rollout-metric keys
    for k in dv.FORBIDDEN_METRIC_KEYS:
        assert k not in schema, f"rollout metric {k} must not be in the schema"
    # no training/label fields
    for bad in ("train", "val", "test", "label", "episode", "dataset", "reward", "loss"):
        assert not any(bad in key.lower() for key in schema), f"training-ish field '{bad}' in schema"
    # required validation-only fields present
    for req in ("scene_identity", "spawn_pose_check", "camera_pose_check",
                "static_collision_precheck", "north_probe", "west_probe", "contacts",
                "safe_halt", "pass", "fail_reasons", "claim_boundary"):
        assert req in schema, f"missing validation field: {req}"
    assert schema["cl_bound_xy_readonly"] == 6.0


def test_config_validation_works_without_isaac():
    ok, issues, ident = dv.validate_config()
    assert ok, f"config invalid: {issues}"
    assert ident["scene_identity_pass"], f"scene identity failed: {ident['failed_reasons']}"
    assert ident["observed_prim_count"] >= dv.EXPECTED_MIN_PRIMS


def test_main_validate_config_returns_zero_without_isaac():
    assert dv.main(["--mode", "validate-config"]) == 0


def test_probes_are_bounded_low_speed_and_in_bounds():
    probes = dv.probe_plan()
    assert {p["branch"] for p in probes} == {"N", "W"}
    for p in probes:
        assert p["scripted"] is True and p["policy_driven"] is False
        assert p["max_speed_mps"] <= dv.MAX_PROBE_SPEED_MPS
        assert p["max_distance_m"] <= dv.MAX_PROBE_DISTANCE_M
        assert p["endpoint_in_bounds"] is True
        assert abs(p["endpoint_xy"][0]) < dv.CL_BOUND_XY
        assert abs(p["endpoint_xy"][1]) < dv.CL_BOUND_XY
    dv.assert_probes_in_bounds(probes)  # must not raise


def test_safe_halt_is_zero_command():
    h = dv.safe_halt_command()
    assert h["linear_mps"] == 0.0 and h["angular_rps"] == 0.0
    assert h["cmd"] == "zero_velocity"


def test_refuses_training_and_action_probe_modes():
    import pytest
    for flag in ("--train", "--record", "--collect", "--action-probe", "--rollout", "--closed-loop"):
        with pytest.raises(SystemExit) as ei:
            dv.main([flag])
        assert ei.value.code != 0, f"{flag} must cause a nonzero refusal exit"


def test_cl_bound_xy_is_readonly_reference_value():
    # The harness only mirrors the watchdog value; it must be the safety constant, unchanged.
    assert dv.CL_BOUND_XY == 6.0


if __name__ == "__main__":  # allow running without pytest for the refusal-free tests
    import pytest as _pt
    raise SystemExit(_pt.main([__file__, "-q"]))
