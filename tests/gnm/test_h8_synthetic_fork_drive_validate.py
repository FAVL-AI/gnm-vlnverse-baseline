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


# ── FIX 1: collider matching covers Gprim primitives (not just Mesh) ──────────
def test_collider_types_include_gprim_primitives_not_just_mesh():
    # the DEFER bug was Mesh-only matching; the authored scene is Cube/Cone/Sphere/Cylinder
    for t in ("Cube", "Cone", "Sphere", "Cylinder", "Mesh"):
        assert t in dv.GPRIM_COLLIDER_TYPES, f"collider eligibility must include {t}"
    # curves/points are NOT solid colliders and must not be in the list
    for t in ("Points", "BasisCurves", "NurbsCurves"):
        assert t not in dv.GPRIM_COLLIDER_TYPES


def test_zero_colliders_still_fails_closed():
    # even with everything else good, zero colliders must not pass (missing collision geometry)
    r = _good_result()
    r["static_collision_precheck"]["scene_collider_count"] = 0
    assert dv.compute_verdict(r)[0] is False


# ── FIX 2: process exit code reflects the manifest verdict ────────────────────
def test_verdict_exit_code_mapping():
    assert dv.verdict_exit_code(True) == 0
    assert dv.verdict_exit_code(False) != 0
    assert dv.verdict_exit_code(None) != 0   # DEFER / incomplete -> nonzero (fail-closed)


def test_run_isaac_forces_exit_code_before_shutdown_can_mask_it():
    # REGRESSION: the first fix called app.close() BEFORE os._exit and the run exited 0 despite a
    # `pass: False` manifest — Isaac's app.close() hard-exits 0 and masked the failing verdict. The
    # corrected invariant: force the intended exit code BEFORE any app.close(); if app.close() is
    # present at all it must come strictly after os._exit (i.e. it can never preempt the exit code).
    start = HARNESS_SRC.index("def run_isaac(")
    end = HARNESS_SRC.index("\ndef finalize(", start)
    src = HARNESS_SRC[start:end]
    assert "verdict_exit_code(" in src, "run_isaac must derive exit code from the verdict"
    assert "os._exit(" in src, "run_isaac must force the exit code"
    if "app.close(" in src:
        assert src.index("os._exit(") < src.index("app.close("), \
            "os._exit must be forced BEFORE app.close() (which hard-exits 0 and masks failure)"


# ── FIX 3: floor/ground support contact is not scored as an obstacle collision ─
def test_floor_ground_contacts_are_support_not_collision():
    # the second DEFER cause: once the `Cube \"Floor\"` became a collider, the footprint overlap hit
    # the ground at every pose and every check failed. Floor/ground = expected support, not collision.
    for support in ("/World/Scene/Structure/Floor", "/World/Scene/ground_plane", "/World/Scene/FLOOR"):
        assert dv.is_support_contact(support) is True, f"{support} must be treated as support"
    # walls, end panels, stripes, props, and markers are REAL obstacles — never excluded
    for obstacle in ("/World/Scene/Structure/N_wall_W", "/World/Scene/End_N_blue",
                     "/World/Scene/Marker_E_square", "/World/Scene/N_stripe_1",
                     "/World/Robot/base"):
        assert dv.is_support_contact(obstacle) is False, f"{obstacle} must NOT be treated as support"
    assert dv.is_support_contact("") is False


def test_classify_contacts_splits_support_obstacle_and_drops_robot_self():
    paths = ["/World/Scene/Structure/Floor",      # support
             "/World/Scene/Structure/N_wall_W",   # obstacle
             "/World/Robot/base_link",            # robot self -> dropped
             "/World/Scene/ground",               # support
             "/World/Scene/End_N_blue",           # obstacle
             ""]                                  # empty -> dropped
    support, obstacle = dv.classify_contacts(paths, "/World/Robot")
    assert support == ["/World/Scene/Structure/Floor", "/World/Scene/ground"]
    assert obstacle == ["/World/Scene/Structure/N_wall_W", "/World/Scene/End_N_blue"]
    # robot self-hit and empty path appear in neither list
    for dropped in ("/World/Robot/base_link", ""):
        assert dropped not in support and dropped not in obstacle
    # a scene of ONLY floor support yields zero obstacle contacts (the drivable-clear case)
    s2, o2 = dv.classify_contacts(["/World/Scene/Floor", "/World/Scene/ground_plane"], "/World/Robot")
    assert len(o2) == 0 and len(s2) == 2


def test_output_schema_carries_contact_classification_metadata():
    schema = dv.output_schema()
    assert schema["contact_classification_rule"] == dv.CONTACT_CLASSIFICATION_RULE
    assert schema["support_contact_allowed"] is True
    # the rule must name both support and obstacle handling
    rule = dv.CONTACT_CLASSIFICATION_RULE.lower()
    assert "support" in rule and "obstacle" in rule and "floor" in rule


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
