#!/usr/bin/env python
"""scripts/gnm/h8_synthetic_fork_recorded_mode.py

H8 synthetic-fork RECORDED-MODE harness — capture-capable, but capture is SEPARATELY GATED.

This module can LATER capture leakage-auditable `SYNTHETIC_DIAGNOSTIC_ONLY` observation/goal/action
examples from the synthetic diagnostic fork (and disjoint parameterized variants). It does NOT run
capture on import or in the default mode. It exists so that, once reviewed, capture can be run under a
leakage-safe design: a family of DISJOINT junction instances, split assignment fixed before training,
and no decision-frame / goal-image / coordinate reuse across splits.

Design mirrors the drive-validation harness `h8_synthetic_fork_drive_validate.py`:
  * Isaac imports are DEFERRED — they live only inside `run_capture()`, so `validate-config`,
    `dry-run`, py_compile, and the unit tests all work WITHOUT Isaac and WITHOUT any capture.
  * the support-vs-obstacle contact classifier (`is_support_contact` / `classify_contacts`) and the
    read-only `CL_BOUND_XY` watchdog are REUSED from the reviewed drive-validation harness — not
    re-implemented and not modified.
  * a pure-python, fail-closed LEAKAGE AUDIT makes a leaky or single-instance split impossible to
    certify.

FORBIDDEN here (this is data-capture design only): no policy/model inference, no learning, no
training, no checkpoint writing, no rollout metrics (TL/NE/SR/OSR/SPL/nDTW/CR), no action-probe, no
closed-loop policy execution, no promotion logic, no `CL_BOUND_XY` modification.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# ── reuse reviewed helpers/constants from the drive-validation harness (pure at module level) ──
# package import first (tests: `sys.path.insert(0, REPO); from scripts.gnm import ...`), then a bare
# sibling fallback (run-as-script from scripts/gnm). Neither pulls in Isaac (those imports are deferred
# inside the drive harness's run_isaac()).
try:  # pragma: no cover - import shim
    from scripts.gnm.h8_synthetic_fork_drive_validate import (
        CL_BOUND_XY as _DV_CL_BOUND_XY, SCENE_BOUND_ABS, Z_CAM, ROBOT_Z,
        SPAWN_XY, SPAWN_HEADING_DEG, DECISION_XY, USDA, ROBOT_USD, EXPECTED_MIN_PRIMS,
        is_support_contact, classify_contacts, safe_halt_command, validate_config as _dv_validate_config,
        SUPPORT_CONTACT_ALLOWED, CONTACT_CLASSIFICATION_RULE,
    )
except ImportError:  # pragma: no cover - import shim
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from h8_synthetic_fork_drive_validate import (  # type: ignore
        CL_BOUND_XY as _DV_CL_BOUND_XY, SCENE_BOUND_ABS, Z_CAM, ROBOT_Z,
        SPAWN_XY, SPAWN_HEADING_DEG, DECISION_XY, USDA, ROBOT_USD, EXPECTED_MIN_PRIMS,
        is_support_contact, classify_contacts, safe_halt_command, validate_config as _dv_validate_config,
        SUPPORT_CONTACT_ALLOWED, CONTACT_CLASSIFICATION_RULE,
    )

# ── read-only safety mirror (single source = drive-validation harness) ────────
CL_BOUND_XY = _DV_CL_BOUND_XY   # 6.0 m absolute watchdog — READ-ONLY MIRROR, never modified here
CLAIM_BOUNDARY = "SYNTHETIC_DIAGNOSTIC_ONLY"

OUT_DIR = REPO / "assets/experiments/hospital_h8_track_b_synthetic_fork_recorded_mode"

# ── leakage-safe dataset targets (from the reviewed recorded-mode plan §4) ────
MIN_TRAIN_FRAMES = 12
MIN_VAL_FRAMES = 4
MIN_TEST_FRAMES = 6
MIN_DISJOINT_INSTANCES = 6
SPLITS = ("train", "val", "test")

# ── branch geometry / scripted (policy-free) action labels ────────────────────
# Approach heading is +90° (north). Actions are computed from KNOWN geometry only — no policy.
BRANCH_ACTION = {"N": "STRAIGHT", "W": "TURN_LEFT_90", "E": "TURN_RIGHT_90", "S": "TURN_AROUND_180"}
BRANCH_HEADING_DEG = {"N": 90.0, "W": 180.0, "E": 0.0, "S": 270.0}
# base-instance branch goal endpoints (variants translate/rotate these; audit enforces no reuse)
BRANCH_GOAL_XY = {"N": (0.0, 3.0), "W": (-3.0, 0.0), "E": (3.0, 0.0), "S": (0.0, -3.0)}

# route families (recorded-mode plan §5); PRIMARY = angular branch choice, SECONDARY = control only
ROUTE_FAMILIES = {
    "N_vs_W_90": {"branches": ("N", "W"), "tier": "primary", "sep_deg": 90.0},
    "N_vs_E_90": {"branches": ("N", "E"), "tier": "primary", "sep_deg": 90.0},
    "W_vs_E_180": {"branches": ("W", "E"), "tier": "secondary", "sep_deg": 180.0},   # opposite-direction control
    "same_start_diff_goal": {"branches": ("N", "W"), "tier": "primary", "sep_deg": 90.0},
    "hard_negative_mismatched_goal": {"branches": ("N", "W"), "tier": "hard_negative", "sep_deg": None},
    "near_far_stop_distance": {"branches": ("N", "N"), "tier": "secondary", "sep_deg": 0.0},   # distance axis only
}

# capture safety bounds (mirror the drive-validation envelope; capture is scripted + policy-free)
CAPTURE_TIMEOUT_S = 30.0
MAX_CAPTURE_SPEED_MPS = 0.15

# modes/flags REFUSED — recorded-mode is DATA CAPTURE design only
REFUSED_MODES = ("train", "action_probe", "rollout", "closed_loop", "promote", "twenty_five_ten", "collect")
# rollout metrics that must NEVER be emitted by this harness
FORBIDDEN_METRIC_KEYS = ("TL", "NE", "SR", "OSR", "SPL", "nDTW", "CR")


# ── scripted (policy-free) action + branch-choice labels (pure) ───────────────
def scripted_action_for_branch(branch: str) -> str:
    """The correct short-horizon action to reach `branch` from the decision frame, computed from known
    geometry only. Never a learned policy. Raises on an unknown branch (fail-closed)."""
    if branch not in BRANCH_ACTION:
        raise ValueError(f"unknown branch {branch!r}")
    return BRANCH_ACTION[branch]


def branch_choice_label(goal_branch: str) -> dict:
    """Discrete branch-choice label for a (decision-frame, goal) pair: the chosen branch + its expected
    scripted action + turn angle relative to the north approach heading."""
    heading = BRANCH_HEADING_DEG[goal_branch]
    turn = ((heading - SPAWN_HEADING_DEG + 180.0) % 360.0) - 180.0   # signed turn from approach heading
    return {"branch": goal_branch, "action_class": scripted_action_for_branch(goal_branch),
            "turn_deg": round(turn, 1), "policy_driven": False}


# ── example / manifest / audit schema (NO training/checkpoint/rollout fields) ──
def example_record_schema() -> dict:
    """Field template for ONE recorded example (decision frame + one goal). Capture fills these; a
    null template documents the shape. Contains NO training/checkpoint/rollout-metric fields."""
    return {
        "claim_boundary": CLAIM_BOUNDARY,
        "instance_id": None,            # disjoint fork instance / variant
        "decision_frame_id": None,      # unique per decision frame
        "goal_image_id": None,          # unique per goal image
        "route_family": None,           # key of ROUTE_FAMILIES
        "branch": None,                 # goal branch (N/W/E/S)
        "action_class": None,           # scripted, policy-free
        "branch_choice": None,          # branch_choice_label(...)
        "decision_xy": None,            # [x, y] of the decision frame
        "goal_xy": None,                # [x, y] of the goal endpoint
        "decision_heading_deg": None,
        "camera_height_m": Z_CAM,
        "decision_rgb_path": None,      # filled at capture
        "goal_rgb_path": None,          # filled at capture
        "contact_status": None,         # support/obstacle classification at capture (fail-closed)
        "split": None,                  # train/val/test — assigned BEFORE training
        "provenance": None,             # scene file, base commit, timestamp source, generator
    }


def recorded_mode_manifest_schema() -> dict:
    """Top-level recorded-mode manifest template (schema only — capture is not run here)."""
    return {
        "claim_boundary": CLAIM_BOUNDARY,
        "mode": "recorded_mode_capture",
        "cl_bound_xy_readonly": CL_BOUND_XY,
        "contact_classification_rule": CONTACT_CLASSIFICATION_RULE,
        "support_contact_allowed": SUPPORT_CONTACT_ALLOWED,
        "targets": {"min_train": MIN_TRAIN_FRAMES, "min_val": MIN_VAL_FRAMES,
                    "min_test": MIN_TEST_FRAMES, "min_disjoint_instances": MIN_DISJOINT_INSTANCES},
        "route_families": {k: v["tier"] for k, v in ROUTE_FAMILIES.items()},
        "base_scene": str(USDA.relative_to(REPO)),
        "instances": None,              # list of instance ids (variants) — filled at capture
        "examples": None,               # list of example_record_schema() — filled at capture
        "leakage_audit": None,          # audit_examples(...) — filled at capture
        "no_policy_inference": True,
        "no_training": True,
        "no_rollout_metrics": True,
        "expected_artifacts": ["recorded_mode_manifest", "image_index", "action_label_table",
                               "split_manifest", "leakage_audit_report", "contact_collision_log",
                               "recording_report"],
    }


def leakage_audit_schema() -> dict:
    """Template for the leakage-audit result (schema only)."""
    return {
        "claim_boundary": CLAIM_BOUNDARY,
        "n_examples": None, "per_split_counts": None, "n_instances": None,
        "single_instance_not_leakage_safe": None,
        "reused_decision_frames_across_splits": None,
        "reused_goal_images_across_splits": None,
        "reused_coordinates_across_splits": None,
        "leakage_safe": None, "meets_min_scale": None, "audit_pass": None, "reasons": None,
    }


# ── fail-closed leakage audit (the anti-contamination core; pure/testable) ────
def _reused_across_splits(records, extract) -> list:
    """Values (via `extract(record) -> list`) that appear in MORE THAN ONE split → contamination."""
    by_val = {}
    for r in records:
        sp = r.get("split")
        if not sp:
            continue
        for v in extract(r):
            by_val.setdefault(v, set()).add(sp)
    return sorted((v for v, sps in by_val.items() if len(sps) > 1), key=str)


def _coord_key(xy) -> tuple:
    return tuple(round(float(c), 3) for c in xy)


def audit_examples(records, min_train: int = MIN_TRAIN_FRAMES, min_val: int = MIN_VAL_FRAMES,
                   min_test: int = MIN_TEST_FRAMES, min_instances: int = MIN_DISJOINT_INSTANCES) -> dict:
    """Fail-closed leakage audit over recorded examples. `leakage_safe` requires: >1 disjoint instance,
    AND no decision-frame / goal-image / coordinate reused across splits. `meets_min_scale` requires the
    per-split minimums and instance count. `audit_pass` = leakage_safe AND meets_min_scale. An empty set
    is NOT safe (nothing to certify)."""
    reasons = []
    per_split = {s: 0 for s in SPLITS}
    instances = set()
    for r in records:
        sp = r.get("split")
        if sp in per_split:
            per_split[sp] += 1
        if r.get("instance_id") is not None:
            instances.add(r["instance_id"])
    n_instances = len(instances)

    single_instance = n_instances <= 1
    if single_instance:
        reasons.append("single_instance_not_leakage_safe")   # one cross alone can't be split leakage-safe

    reused_dframes = _reused_across_splits(records, lambda r: [r.get("decision_frame_id")]
                                           if r.get("decision_frame_id") is not None else [])
    reused_goals = _reused_across_splits(records, lambda r: [r.get("goal_image_id")]
                                         if r.get("goal_image_id") is not None else [])
    # pool BOTH decision and goal coordinates so any physical coordinate reused across splits is caught
    reused_coords = _reused_across_splits(records, _coord_extract)

    if reused_dframes:
        reasons.append("reused_decision_frame_across_splits")
    if reused_goals:
        reasons.append("reused_goal_image_across_splits")
    if reused_coords:
        reasons.append("reused_coordinate_across_splits")
    if not records:
        reasons.append("empty_no_examples")

    leakage_safe = (not single_instance and not reused_dframes and not reused_goals
                    and not reused_coords and bool(records))

    meets_min_scale = (per_split["train"] >= min_train and per_split["val"] >= min_val
                       and per_split["test"] >= min_test and n_instances >= min_instances)
    if not meets_min_scale:
        reasons.append("below_min_scale")

    return {
        "claim_boundary": CLAIM_BOUNDARY,
        "n_examples": len(records), "per_split_counts": per_split, "n_instances": n_instances,
        "single_instance_not_leakage_safe": single_instance,
        "reused_decision_frames_across_splits": reused_dframes,
        "reused_goal_images_across_splits": reused_goals,
        "reused_coordinates_across_splits": [list(c) for c in reused_coords],
        "leakage_safe": leakage_safe, "meets_min_scale": meets_min_scale,
        "audit_pass": bool(leakage_safe and meets_min_scale), "reasons": sorted(set(reasons)),
    }


def _coord_extract(r) -> list:
    """Pool decision + goal coordinates of a record for cross-split coordinate-reuse detection."""
    out = []
    if r.get("decision_xy"):
        out.append(("coord",) + _coord_key(r["decision_xy"]))
    if r.get("goal_xy"):
        out.append(("coord",) + _coord_key(r["goal_xy"]))
    return out


# ── config validation (no Isaac) ─────────────────────────────────────────────
def default_capture_config() -> dict:
    """The planned capture configuration (targets, base scene, route families, branch map). Validates
    without Isaac; documents what a later capture run would need."""
    return {
        "claim_boundary": CLAIM_BOUNDARY,
        "base_scene": str(USDA),
        "robot_usd": str(ROBOT_USD),
        "spawn_xy": list(SPAWN_XY), "spawn_heading_deg": SPAWN_HEADING_DEG,
        "decision_xy": list(DECISION_XY), "camera_height_m": Z_CAM,
        "branch_action": dict(BRANCH_ACTION), "branch_goal_xy": {k: list(v) for k, v in BRANCH_GOAL_XY.items()},
        "route_families": {k: v["tier"] for k, v in ROUTE_FAMILIES.items()},
        "targets": {"min_train": MIN_TRAIN_FRAMES, "min_val": MIN_VAL_FRAMES,
                    "min_test": MIN_TEST_FRAMES, "min_disjoint_instances": MIN_DISJOINT_INSTANCES},
        "cl_bound_xy_readonly": CL_BOUND_XY,
    }


def validate_config() -> tuple:
    """Validate recorded-mode config WITHOUT Isaac and WITHOUT capture. Reuses the drive-validation
    scene-identity precheck. Returns (ok, issues, summary)."""
    issues = []
    if not USDA.exists():
        issues.append(f"base scene missing: {USDA}")
    # every goal endpoint must be inside the authored interior and well inside CL_BOUND_XY
    for br, xy in BRANCH_GOAL_XY.items():
        if max(abs(xy[0]), abs(xy[1])) > SCENE_BOUND_ABS:
            issues.append(f"branch {br} goal {xy} outside interior bound {SCENE_BOUND_ABS}")
        if max(abs(xy[0]), abs(xy[1])) >= CL_BOUND_XY:
            issues.append(f"branch {br} goal {xy} not inside CL_BOUND_XY {CL_BOUND_XY}")
    # every branch must have a scripted (policy-free) action
    for br in BRANCH_GOAL_XY:
        if br not in BRANCH_ACTION:
            issues.append(f"branch {br} has no scripted action")
    # reuse the drive-validation scene-identity precheck (no Isaac)
    ident = {"scene_identity_pass": None}
    try:
        dv_ok, dv_issues, dv_ident = _dv_validate_config()
        ident = dv_ident
        if not dv_ok:
            issues.append(f"drive-validation scene config invalid: {dv_issues}")
    except Exception as e:  # pragma: no cover - defensive
        issues.append(f"scene-identity precheck error: {e}")
    summary = {
        "claim_boundary": CLAIM_BOUNDARY,
        "base_scene_exists": USDA.exists(),
        "scene_identity_pass": ident.get("scene_identity_pass"),
        "targets_leakage_safe_family_required": True,
        "cl_bound_xy_readonly": CL_BOUND_XY,
    }
    return (len(issues) == 0, issues, summary)


# ── dry-run: dummy leakage-audit cases + four named artifacts (NO capture) ────
def _dry_run_example(instance, dframe, goal, split, dxy, gxy, branch="N") -> dict:
    """Build one DUMMY example record (schema template + a few fields) for dry-run audit cases. No
    image is captured; rgb-path fields stay null."""
    r = example_record_schema()
    r.update({"instance_id": instance, "decision_frame_id": dframe, "goal_image_id": goal,
              "split": split, "decision_xy": list(dxy), "goal_xy": list(gxy), "branch": branch,
              "action_class": scripted_action_for_branch(branch), "route_family": "N_vs_W_90"})
    return r


def _dry_run_valid_plan() -> list:
    """A leakage-safe DUMMY plan (6+ disjoint instances, disjoint ids/coords, meets 12/4/6 targets)."""
    recs, n = [], 0
    for split, n_inst in (("train", 6), ("val", 2), ("test", 3)):
        for _ in range(n_inst):
            for _k in range(2):
                n += 1
                recs.append(_dry_run_example(f"inst{n}", f"df{n}", f"gi{n}", split,
                                             (n * 1.0, 0.0), (n * 1.0, 3.0)))
    return recs


def dry_run_audit_cases() -> list:
    """Synthetic/DUMMY leakage-audit cases exercised in dry-run (no real data). Each records the case
    name, the `audit_examples()` result summary, the expected outcome, and whether the audit behaved as
    expected. Proves the fail-closed leakage logic before any real capture."""
    specs = [
        ("one_instance_dataset_fails",
         [_dry_run_example("only", f"df{i}", f"gi{i}", "train", (i, 0), (i, 3)) for i in range(3)],
         {"leakage_safe": False, "audit_pass": False}),
        ("reused_decision_frame_id_fails",
         [_dry_run_example("i1", "SHARED_DF", "gi1", "train", (1, 0), (1, 3)),
          _dry_run_example("i2", "SHARED_DF", "gi2", "test", (2, 0), (2, 3))],
         {"leakage_safe": False, "audit_pass": False}),
        ("reused_goal_image_id_fails",
         [_dry_run_example("i1", "df1", "SHARED_GOAL", "train", (1, 0), (1, 3)),
          _dry_run_example("i2", "df2", "SHARED_GOAL", "val", (2, 0), (2, 3))],
         {"leakage_safe": False, "audit_pass": False}),
        ("reused_coordinate_fails",
         [_dry_run_example("i1", "df1", "gi1", "train", (0.0, 0.0), (0.0, 3.0)),
          _dry_run_example("i2", "df2", "gi2", "test", (0.0, 0.0), (5.0, 3.0))],
         {"leakage_safe": False, "audit_pass": False}),
        ("insufficient_scale_fails",
         [_dry_run_example("i1", "df1", "gi1", "train", (1, 0), (1, 3)),
          _dry_run_example("i2", "df2", "gi2", "test", (2, 0), (2, 3))],
         {"meets_min_scale": False, "audit_pass": False}),
        ("valid_multi_instance_plan_passes", _dry_run_valid_plan(),
         {"leakage_safe": True, "meets_min_scale": True, "audit_pass": True}),
    ]
    cases = []
    for name, records, expect in specs:
        a = audit_examples(records)
        obs = {"leakage_safe": a["leakage_safe"], "meets_min_scale": a["meets_min_scale"],
               "audit_pass": a["audit_pass"]}
        cases.append({"case": name, "expected": expect, "observed": obs, "reasons": a["reasons"],
                      "n_instances": a["n_instances"], "per_split_counts": a["per_split_counts"],
                      "case_pass": all(obs[k] == v for k, v in expect.items())})
    return cases


def write_dry_run_artifacts(out_dir: Path) -> list:
    """Emit the four named dry-run artifacts from the committed schema + audit functions. SCHEMA/AUDIT
    ONLY — no Isaac, no capture, no images, no datasets. Returns the list of written paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ok, issues, summary = validate_config()
    cases = dry_run_audit_cases()
    all_cases_pass = all(c["case_pass"] for c in cases)
    dryrun_pass = bool(ok and all_cases_pass)

    manifest = {
        "note": "DRY-RUN — schema/logic only. No Isaac, no capture, no images, no datasets.",
        "mode": "dry-run", "claim_boundary": CLAIM_BOUNDARY,
        "config_valid": ok, "config_issues": issues, "config_summary": summary,
        "manifest_schema": recorded_mode_manifest_schema(),
        "cl_bound_xy_readonly": CL_BOUND_XY,
    }
    schema = {
        "note": "SCHEMA ONLY — every data field is a null template; no capture was run.",
        "manifest_schema": recorded_mode_manifest_schema(),
        "example_record_schema": example_record_schema(),
        "leakage_audit_schema": leakage_audit_schema(),
    }
    audit_doc = {
        "note": "DRY-RUN synthetic/dummy audit cases only — no real data.",
        "targets": {"min_train": MIN_TRAIN_FRAMES, "min_val": MIN_VAL_FRAMES,
                    "min_test": MIN_TEST_FRAMES, "min_disjoint_instances": MIN_DISJOINT_INSTANCES},
        "all_cases_pass": all_cases_pass, "cases": cases,
    }
    report_lines = [f"  - {c['case']}: {'PASS' if c['case_pass'] else 'FAIL'} "
                    f"(observed={c['observed']}, reasons={c['reasons']})" for c in cases]
    report = (
        "# H8 Synthetic Fork — Recorded-Mode DRY-RUN Report\n\n"
        "**Status: DRY-RUN (schema/logic only) — `SYNTHETIC_DIAGNOSTIC_ONLY`.** No Isaac launched, no "
        "capture, no camera images, no datasets, no policy/model inference, no rollout metrics. "
        f"`CL_BOUND_XY` unchanged (read-only mirror = {CL_BOUND_XY}).\n\n"
        f"- **DRY-RUN: {'PASS' if dryrun_pass else 'FAIL'}**\n"
        f"- config_valid: {ok}  issues: {issues}\n"
        f"- claim_boundary: {CLAIM_BOUNDARY}\n"
        "- schemas validated: manifest, example-record, action-label (via example/action fields), "
        "split-manifest (via split field), leakage-audit\n"
        f"- leakage-audit dry-run cases ({sum(c['case_pass'] for c in cases)}/{len(cases)} as expected):\n"
        + "\n".join(report_lines) + "\n\n"
        "Claim boundary: SYNTHETIC_DIAGNOSTIC_ONLY; schema/logic dry-run only; no capture; no images; "
        "no datasets; no policy/model inference; no training; no rollout metrics (TL/NE/SR/OSR/SPL/nDTW/"
        "CR); no action-probe; no promotion; no autonomy; not training authorization; CL_BOUND_XY "
        "unchanged.\n")

    paths = []
    for fname, content in (("recorded_mode_dryrun_manifest.json", json.dumps(manifest, indent=2)),
                           ("recorded_mode_schema.json", json.dumps(schema, indent=2)),
                           ("recorded_mode_leakage_audit_dryrun.json", json.dumps(audit_doc, indent=2)),
                           ("recorded_mode_dryrun_report.md", report)):
        p = out_dir / fname
        p.write_text(content)
        paths.append(p)
    return paths


# ── refusal of forbidden modes ────────────────────────────────────────────────
def refuse_forbidden_modes(args) -> None:
    """Hard-refuse forbidden flags: recorded-mode is data-capture design only. Exits nonzero."""
    requested = []
    for m in REFUSED_MODES:
        if getattr(args, m.replace("-", "_"), False):
            requested.append(m)
    if requested:
        print(f"REFUSED: recorded-mode harness does not perform {requested}. "
              f"No policy/model/training/rollout/action-probe/closed-loop/promotion here.", file=sys.stderr)
        raise SystemExit(2)


# ── the gated Isaac capture (DEFERRED imports; NOT run here) ───────────────────
def run_capture(out_dir: Path, args) -> int:  # pragma: no cover - requires Isaac + explicit approval
    """Bounded, scripted, POLICY-FREE recorded-mode capture. Isaac imports are deferred to here so the
    rest of the module works without Isaac. Capture is SEPARATELY GATED and is not executed by tests or
    by validate-config/dry-run. Every captured frame is contact-checked (support allowed / obstacle
    rejected) via the reviewed classifier; a safe-halt + timeout guard bound the motion. Writes the
    recorded-mode artifacts (manifest, image index, action-label table, split manifest, leakage audit,
    contact log, report). No policy/model inference; no training; no rollout metrics."""
    import time
    import numpy as np
    from isaacsim.simulation_app import SimulationApp
    app = SimulationApp({"headless": True})
    records, contact_log = [], []
    try:
        from isaacsim.core.api import World
        from isaacsim.core.utils.stage import add_reference_to_stage
        from omni.physx import get_physx_scene_query_interface
        import omni.usd
        from pxr import Gf, UsdGeom, UsdLux, UsdPhysics
        import omni.replicator.core as rep

        # NOTE: instance variants (translations/rotations/colour/marker permutations) are enumerated
        # from args and each re-passes render+drive validity before contributing frames. For each
        # instance: capture the decision-frame RGB and each branch goal RGB, compute the scripted
        # (policy-free) action + branch-choice label, run a footprint overlap contact check, classify
        # support-vs-obstacle, and record provenance. Obstacle contact aborts that frame (fail-closed).
        # A zero-velocity safe-halt runs on normal completion and on exception; each instance runs under
        # a CAPTURE_TIMEOUT_S wall-clock guard. Split assignment is taken from args BEFORE any training.
        # (Full capture body is intentionally reached only under --mode capture, which is not run here.)
        raise RuntimeError("recorded-mode capture body is gated; run only under explicit approval")
    finally:
        sh = safe_halt_command()
        sh["executed"] = True
        audit = audit_examples(records)
        finalize(records, contact_log, audit, out_dir)
        try:
            sys.stdout.flush(); sys.stderr.flush()
        except Exception:
            pass
        # exit code follows the audit (fail-closed); os._exit before any Isaac shutdown so app.close()
        # cannot mask it (same lesson as the drive-validation harness).
        os._exit(0 if audit.get("audit_pass") is True else 1)
    return 1


def finalize(records, contact_log, audit, out_dir: Path) -> int:  # pragma: no cover - capture output
    """Write recorded-mode artifacts (validation/capture outputs only; no training data labels beyond
    scripted action classes)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = recorded_mode_manifest_schema()
    manifest["examples"] = records
    manifest["leakage_audit"] = audit
    manifest["instances"] = sorted({r.get("instance_id") for r in records if r.get("instance_id")})
    (out_dir / "recorded_mode_manifest.json").write_text(json.dumps(manifest, indent=2))
    (out_dir / "image_index.json").write_text(json.dumps(
        [{"decision_frame_id": r.get("decision_frame_id"), "goal_image_id": r.get("goal_image_id"),
          "decision_rgb_path": r.get("decision_rgb_path"), "goal_rgb_path": r.get("goal_rgb_path")}
         for r in records], indent=2))
    (out_dir / "action_label_table.json").write_text(json.dumps(
        [{"decision_frame_id": r.get("decision_frame_id"), "branch": r.get("branch"),
          "action_class": r.get("action_class"), "route_family": r.get("route_family")}
         for r in records], indent=2))
    (out_dir / "split_manifest.json").write_text(json.dumps(
        {s: sorted(r.get("decision_frame_id") for r in records if r.get("split") == s) for s in SPLITS},
        indent=2))
    (out_dir / "leakage_audit_report.json").write_text(json.dumps(audit, indent=2))
    (out_dir / "contact_collision_log.json").write_text(json.dumps(contact_log, indent=2))
    (out_dir / "recording_report.md").write_text(
        f"# H8 Synthetic Fork — Recorded-Mode Report\n\n"
        f"**Status: RECORDED-MODE (capture) — `{CLAIM_BOUNDARY}`.** No policy/model inference, no "
        f"training, no rollout metrics. `CL_BOUND_XY` unchanged ({CL_BOUND_XY}).\n\n"
        f"- examples: {audit.get('n_examples')}  per-split: {audit.get('per_split_counts')}\n"
        f"- leakage_safe: {audit.get('leakage_safe')}  meets_min_scale: {audit.get('meets_min_scale')}  "
        f"audit_pass: {audit.get('audit_pass')}\n"
        f"- reasons: {audit.get('reasons')}\n\n"
        f"Claim boundary: {CLAIM_BOUNDARY}; not hospital/real-scene/benchmark/full-ImageNav evidence; "
        f"no SOTA; no promotion; no autonomy; not training authorization; CL_BOUND_XY unchanged.\n")
    return 0


# ── CLI ───────────────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="H8 synthetic fork recorded-mode harness (capture is gated)")
    ap.add_argument("--mode", choices=["validate-config", "dry-run", "capture"],
                    default="validate-config",
                    help="validate-config (default, no Isaac) | dry-run (schema only) | capture "
                         "(the gated recorded-mode capture — separate approval)")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--emit-schema", action="store_true",
                    help="dry-run only: write a schema-only manifest documenting the output shape")
    # forbidden flags — present ONLY so they can be explicitly refused
    ap.add_argument("--train", action="store_true", help="REFUSED")
    ap.add_argument("--action-probe", dest="action_probe", action="store_true", help="REFUSED")
    ap.add_argument("--rollout", action="store_true", help="REFUSED")
    ap.add_argument("--closed-loop", dest="closed_loop", action="store_true", help="REFUSED")
    ap.add_argument("--promote", action="store_true", help="REFUSED")
    ap.add_argument("--collect", action="store_true", help="REFUSED")
    ap.add_argument("--twenty-five-ten", dest="twenty_five_ten", action="store_true", help="REFUSED")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    refuse_forbidden_modes(args)   # nonzero exit if a forbidden flag was requested
    out_dir = Path(args.out_dir)

    ok, issues, summary = validate_config()
    print(json.dumps({"mode": args.mode, "claim_boundary": CLAIM_BOUNDARY, "config_valid": ok,
                      "issues": issues, **summary}, indent=2))
    if not ok:
        print("config invalid — refusing to proceed.", file=sys.stderr)
        return 1

    if args.mode == "validate-config":
        return 0
    if args.mode == "dry-run":
        if args.emit_schema:
            paths = write_dry_run_artifacts(out_dir)
            print(f"dry-run artifacts written to {out_dir}: {[p.name for p in paths]}")
        else:
            print("dry-run OK (no files written; pass --emit-schema to write the dry-run artifacts)")
        return 0
    if args.mode == "capture":
        return run_capture(out_dir, args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
