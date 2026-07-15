"""tests/gnm/test_h8_synthetic_fork_drive_validate.py

Lightweight unit tests for the synthetic-fork drive-validation HARNESS
(scripts/gnm/h8_synthetic_fork_drive_validate.py). These run WITHOUT Isaac and WITHOUT any drive run:
they exercise the pure-python config / scene-identity / probe-plan / schema / safe-halt / refusal
logic and — critically — the fail-closed `compute_verdict()` guard that makes a null/incomplete run
impossible to pass. They also assert the harness carries no policy/model import and no
rollout-metric / training fields.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from scripts.gnm import h8_synthetic_fork_drive_validate as dv  # noqa: E402

HARNESS_SRC = (REPO / "scripts/gnm/h8_synthetic_fork_drive_validate.py").read_text()


def _good_result() -> dict:
    """A fully-populated, all-passing result dict (what a clean real run would produce)."""
    r = dv.output_schema()
    r["scene_identity"] = {"scene_identity_pass": True}
    r["scene_load"] = {"loaded": True, "prim_count": 92, "scene_collider_count": 40}
    r["spawn_pose_check"] = {"spawned": True, "valid_state": True, "in_bounds": True}
    r["camera_pose_check"] = {"resolved": True, "frame_nonempty": True, "mean_luma": 40.0}
    r["static_collision_precheck"] = {"queried": True, "scene_collider_count": 40,
                                      "contacts": 0, "clear": True}
    r["north_probe"] = {"branch": "N", "reached": True, "contacts": 0, "in_bounds": True,
                        "timed_out": False}
    r["west_probe"] = {"branch": "W", "reached": True, "contacts": 0, "in_bounds": True,
                       "timed_out": False}
    r["in_bounds"] = True
    r["safe_halt"] = {"executed": True}
    return r


# ── fail-closed verdict guard (the anti-null-pass core) ───────────────────────
def test_verdict_rejects_all_null_fields_no_false_pass():
    passed, reasons = dv.compute_verdict(dv.output_schema())  # everything None
    assert passed is False
    # every required physics field must be reported incomplete
    for field in dv.REQUIRED_CHECKS:
        assert f"incomplete_{field}" in reasons, f"missing incomplete_{field}"


def test_verdict_passes_only_when_all_fields_populated_and_good():
    passed, reasons = dv.compute_verdict(_good_result())
    assert passed is True, f"expected pass, reasons={reasons}"
    assert reasons == []


def test_verdict_fails_on_probe_contact():
    r = _good_result(); r["north_probe"]["contacts"] = 1
    passed, reasons = dv.compute_verdict(r)
    assert passed is False and "north_probe_failed" in reasons


def test_verdict_fails_on_incomplete_probe():
    r = _good_result(); r["west_probe"] = None
    passed, reasons = dv.compute_verdict(r)
    assert passed is False and "incomplete_west_probe" in reasons


def test_verdict_fails_on_static_collision():
    r = _good_result(); r["static_collision_precheck"]["contacts"] = 2
    r["static_collision_precheck"]["clear"] = False
    assert dv.compute_verdict(r)[0] is False


def test_verdict_fails_when_no_scene_colliders():
    # missing colliders must NOT read as "clear" — it fails closed
    r = _good_result(); r["static_collision_precheck"]["scene_collider_count"] = 0
    assert dv.compute_verdict(r)[0] is False


def test_verdict_fails_on_probe_timeout_and_out_of_bounds():
    r = _good_result(); r["north_probe"]["timed_out"] = True
    assert dv.compute_verdict(r)[0] is False
    r = _good_result(); r["in_bounds"] = False
    assert dv.compute_verdict(r)[0] is False


# ── no policy/model imports; no rollout/training fields ───────────────────────
def test_no_policy_or_model_import_at_module_level():
    import ast
    tree = ast.parse(HARNESS_SRC)
    module_imports = []
    for node in tree.body:  # module-level only (Isaac imports are deferred inside run_isaac)
        if isinstance(node, ast.Import):
            module_imports += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            module_imports.append(node.module or "")
    forbidden = ("torch", "timm", "tensorflow", "gnm", "policy", "model", "isaacsim", "omni", "pxr")
    for name in module_imports:
        assert not any(f in name.lower() for f in forbidden), f"forbidden module-level import: {name}"
    for token in ("load_state_dict(", "torch.load(", ".load_weights(", "best.pt", "from_pretrained("):
        assert token not in HARNESS_SRC, f"forbidden loading call in harness: {token}"


def test_output_schema_only_validation_fields():
    schema = dv.output_schema()
    for k in dv.FORBIDDEN_METRIC_KEYS:
        assert k not in schema, f"rollout metric {k} must not be in the schema"
    for bad in ("train", "val", "test", "label", "episode", "dataset", "reward", "loss"):
        assert not any(bad in key.lower() for key in schema), f"training-ish field '{bad}' in schema"
    for req in ("scene_identity", "scene_load", "spawn_pose_check", "camera_pose_check",
                "static_collision_precheck", "north_probe", "west_probe", "contacts",
                "safe_halt", "pass", "fail_reasons", "claim_boundary"):
        assert req in schema, f"missing validation field: {req}"
    assert schema["cl_bound_xy_readonly"] == 6.0


def test_required_checks_cover_every_physics_stage():
    # the verdict must gate on scene-load, spawn, camera, static-contact, both probes, bounds, halt
    for stage in ("scene_load", "spawn_pose_check", "camera_pose_check",
                  "static_collision_precheck", "north_probe", "west_probe", "in_bounds", "safe_halt"):
        assert stage in dv.REQUIRED_CHECKS, f"verdict does not gate on {stage}"


# ── config / modes / probes / safety (no Isaac) ───────────────────────────────
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
    dv.assert_probes_in_bounds(probes)


def test_safe_halt_is_zero_command():
    h = dv.safe_halt_command()
    assert h["linear_mps"] == 0.0 and h["angular_rps"] == 0.0
    assert h["cmd"] == "zero_velocity"
    assert h["executed"] is False  # not executed until run_isaac sets it


def test_refuses_training_and_action_probe_modes():
    import pytest
    for flag in ("--train", "--record", "--collect", "--action-probe", "--rollout", "--closed-loop"):
        with pytest.raises(SystemExit) as ei:
            dv.main([flag])
        assert ei.value.code != 0, f"{flag} must cause a nonzero refusal exit"


def test_cl_bound_xy_is_readonly_reference_value():
    assert dv.CL_BOUND_XY == 6.0


if __name__ == "__main__":
    import pytest as _pt
    raise SystemExit(_pt.main([__file__, "-q"]))
