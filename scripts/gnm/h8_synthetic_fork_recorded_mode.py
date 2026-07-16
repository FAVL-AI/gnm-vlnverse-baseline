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
        GPRIM_COLLIDER_TYPES,
        is_support_contact, classify_contacts, safe_halt_command, validate_config as _dv_validate_config,
        SUPPORT_CONTACT_ALLOWED, CONTACT_CLASSIFICATION_RULE,
    )
except ImportError:  # pragma: no cover - import shim
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from h8_synthetic_fork_drive_validate import (  # type: ignore
        CL_BOUND_XY as _DV_CL_BOUND_XY, SCENE_BOUND_ABS, Z_CAM, ROBOT_Z,
        SPAWN_XY, SPAWN_HEADING_DEG, DECISION_XY, USDA, ROBOT_USD, EXPECTED_MIN_PRIMS,
        GPRIM_COLLIDER_TYPES,
        is_support_contact, classify_contacts, safe_halt_command, validate_config as _dv_validate_config,
        SUPPORT_CONTACT_ALLOWED, CONTACT_CLASSIFICATION_RULE,
    )

# ── read-only safety mirror (single source = drive-validation harness) ────────
CL_BOUND_XY = _DV_CL_BOUND_XY   # 6.0 m absolute watchdog — READ-ONLY MIRROR, never modified here
CLAIM_BOUNDARY = "SYNTHETIC_DIAGNOSTIC_ONLY"

OUT_DIR = REPO / "assets/experiments/hospital_h8_track_b_synthetic_fork_recorded_mode"
DRYRUN_DIR = REPO / "assets/experiments/hospital_h8_track_b_synthetic_fork_recorded_mode_dryrun"
PILOT_DIR = REPO / "assets/experiments/hospital_h8_track_b_synthetic_fork_recorded_mode_pilot"
DATASET_DRYRUN_DIR = REPO / "assets/experiments/hospital_h8_track_b_synthetic_fork_recorded_mode_dataset_dryrun"

# the ONLY artifacts a pilot capture may emit, and the outputs it must never emit
ALLOWED_PILOT_ARTIFACTS = ("pilot_manifest", "pilot_image_index", "pilot_action_label_table",
                           "pilot_contact_log", "pilot_provenance_table", "pilot_leakage_audit_report",
                           "pilot_recording_report")
FORBIDDEN_PILOT_OUTPUTS = ("checkpoints", "weights", "wandb", "rollout_metrics", "benchmark_tables",
                           "model_outputs", "action_probe_outputs", "train_val_test_dataset_files")

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


# ── dataset-config DRY-RUN: validate the full dataset capture config + emit artifacts (NO capture) ──
ALLOWED_DATASET_DRYRUN_ARTIFACTS = ("dataset_dryrun_manifest.json", "dataset_plan_schema.json",
                                    "dataset_split_validation_dryrun.json",
                                    "dataset_leakage_audit_dryrun.json", "dataset_dryrun_report.md")
_REQUIRED_DATASET_ARTIFACTS = ("full_recorded_mode_manifest", "image_index", "action_label_table",
                               "split_manifest", "contact_log", "provenance_table",
                               "leakage_audit_report", "recording_report")
_REQUIRED_FORBIDDEN_OUTPUTS = ("checkpoints", "weights", "wandb", "rollout_metrics", "benchmark_tables",
                               "model_outputs", "action_probe_outputs")


def load_dataset_config(path) -> dict:
    """Load the full dataset capture config (YAML; lazy import). Raises FileNotFoundError on a missing
    path and ValueError on a non-mapping. No Isaac, no capture."""
    import yaml  # lazy — keeps module-level imports free of extra deps
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"dataset config not found: {path}")
    cfg = yaml.safe_load(p.read_text())
    if not isinstance(cfg, dict):
        raise ValueError(f"dataset config is not a mapping: {path}")
    return cfg


def _dataset_split_layout(cfg: dict) -> tuple:
    """(instances, by_split, frames_per_split) for the config. frames_per_split is the per-instance
    frame count each split needs to reach its per-split minimum (ceil division)."""
    ms = cfg.get("minimum_scale", {}) or {}
    targets = {"train": int(ms.get("min_train", MIN_TRAIN_FRAMES)),
               "val": int(ms.get("min_val", MIN_VAL_FRAMES)),
               "test": int(ms.get("min_test", MIN_TEST_FRAMES))}
    instances = (cfg.get("instance_plan", {}) or {}).get("instances", []) or []
    by_split = {}
    for i in instances:
        by_split.setdefault(i.get("split"), []).append(i)
    frames = {sp: max(1, -(-targets[sp] // max(1, len(by_split.get(sp, []))))) for sp in targets}
    return instances, by_split, frames


def build_dataset_plan(cfg: dict) -> list:
    """Build PLANNED (not captured) example records from the dataset config's instance_plan + split
    assignments at the config's minimum-scale target. Coordinates are namespaced by each instance's
    coord_offset + frame index so the leakage audit sees disjoint decision/goal coordinates. These
    records are a PLAN only — NO Isaac, NO capture, NO images (rgb-path fields stay null); they exist
    solely to exercise the fail-closed leakage audit before any real capture."""
    instances, _by_split, frames = _dataset_split_layout(cfg)
    recs = []
    for i in instances:
        sp = i.get("split")
        off = i.get("coord_offset") or [0, 0]
        ox, oy = float(off[0]), float(off[1])
        for k in range(frames.get(sp, 1)):
            recs.append({
                "claim_boundary": CLAIM_BOUNDARY, "instance_id": i.get("id"),
                "decision_frame_id": f"{i.get('id')}_df{k}", "goal_image_id": f"{i.get('id')}_df{k}_g",
                "split": sp, "decision_xy": [ox + 0.5 * k, oy], "goal_xy": [ox + 0.5 * k, oy + 3.0],
                "branch": "N", "action_class": scripted_action_for_branch("N"),
                "route_family": "N_vs_W_90", "decision_rgb_path": None, "goal_rgb_path": None})
    return recs


def _cross_split_pair(recs: list) -> tuple:
    """Two records from DIFFERENT splits (falls back to first/last if only one split is present)."""
    a = recs[0]
    b = next((r for r in recs if r.get("split") != a.get("split")), recs[-1])
    return a, b


def dataset_injected_leakage_cases(valid_plan: list) -> list:
    """Record-level injected leakage failures that MUST fail closed: duplicate decision-frame id across
    splits, duplicate goal-image id across splits, duplicate coordinate across splits, and single-
    instance collapse. Each result records the audit outcome + whether it failed closed as expected."""
    def cp(recs):
        return [dict(r) for r in recs]
    specs = []
    p = cp(valid_plan); a, b = _cross_split_pair(p); b["decision_frame_id"] = a["decision_frame_id"]
    specs.append(("dup_decision_frame_across_splits", p))
    p = cp(valid_plan); a, b = _cross_split_pair(p); b["goal_image_id"] = a["goal_image_id"]
    specs.append(("dup_goal_image_across_splits", p))
    p = cp(valid_plan); a, b = _cross_split_pair(p); b["decision_xy"] = list(a["decision_xy"])
    specs.append(("dup_coordinate_across_splits", p))
    p = cp(valid_plan)
    for r in p:
        r["instance_id"] = "only_one"
    specs.append(("single_instance_collapse", p))
    out = []
    for name, recs in specs:
        au = audit_examples(recs)
        out.append({"case": name, "leakage_safe": au["leakage_safe"], "audit_pass": au["audit_pass"],
                    "reasons": au["reasons"],
                    "failed_closed": (au["leakage_safe"] is False and au["audit_pass"] is False)})
    return out


def dataset_requirement_injection_cases(cfg: dict) -> list:
    """Optional config-level injected failures: removing render-valid or drive-valid from one instance
    must make the per-instance validity-requirement check fail closed."""
    import copy
    out = []
    for field, name in (("render_valid_required", "missing_render_valid_requirement"),
                        ("drive_valid_required", "missing_drive_valid_requirement")):
        c = copy.deepcopy(cfg)
        insts = (c.get("instance_plan", {}) or {}).get("instances", []) or []
        if insts:
            insts[0][field] = False   # inject the missing requirement
        holds = bool(insts) and all(i.get(field) is True for i in insts)
        out.append({"case": name, "requirement_holds": holds, "failed_closed": holds is False})
    return out


def dataset_dry_run_checks(cfg: dict) -> dict:
    """Run the 25 dataset-config dry-run checks over `cfg` (config fields + planned split + fail-closed
    leakage-audit logic). Returns the check list, the valid-plan audit, and the injected-failure results.
    No Isaac, no capture, no images."""
    instances, by_split, frames = _dataset_split_layout(cfg)
    valid_plan = build_dataset_plan(cfg)
    # H8-REV-F-003: an empty plan (no instances) has no cross-split pair to audit. Reject it
    # deterministically and gracefully here — never raise across this public validator boundary — so
    # the direct call agrees with validate_dataset_capture_config, which already fails an empty plan
    # closed. This guard only fires for an empty plan; a well-formed plan is unaffected.
    if not valid_plan:
        empty_check = [{"n": 0, "name": "non_empty_plan", "pass": False,
                        "detail": "no planned instances — an empty plan cannot be validated"}]
        return {"checks": empty_check, "n_pass": 0, "n_total": len(empty_check), "all_pass": False,
                "empty_plan": True, "valid_audit": None, "injected_leakage": [],
                "requirement_injection": [], "instances": instances,
                "by_split": {k: len(v) for k, v in by_split.items()}, "frames_per_split": frames}
    valid_audit = audit_examples(valid_plan)
    injected = dataset_injected_leakage_cases(valid_plan)
    req_inject = dataset_requirement_injection_cases(cfg)

    ms = cfg.get("minimum_scale", {}) or {}
    sp = cfg.get("split_policy", {}) or {}
    rf = cfg.get("route_families", {}) or {}
    cc = cfg.get("capture_controls", {}) or {}
    forb = cfg.get("forbidden_outputs", []) or []
    arts = cfg.get("required_future_dataset_artifacts", []) or []
    out = str(cfg.get("output_dir", "")).rstrip("/")
    offsets = {}
    for i in instances:
        offsets.setdefault(tuple(i.get("coord_offset") or []), []).append(i.get("split"))
    cross_split_offsets = sum(1 for _o, s in offsets.items() if len(set(s)) > 1)
    inst_ids = [i.get("id") for i in instances]

    C = []

    def chk(n, name, passed, detail=""):
        C.append({"n": n, "name": name, "pass": bool(passed), "detail": detail})

    chk(1, "config_parses", isinstance(cfg, dict), f"top_keys={len(cfg)}")
    chk(2, "claim_boundary_synthetic_only", cfg.get("claim_boundary") == CLAIM_BOUNDARY,
        str(cfg.get("claim_boundary")))
    chk(3, "authorizes_capture_false", cfg.get("authorizes_capture") is False)
    chk(4, "authorizes_training_false", cfg.get("authorizes_training") is False)
    chk(5, "output_dataset_only",
        out.endswith("_recorded_mode_dataset")
        and out not in (str(OUT_DIR.relative_to(REPO)), str(DRYRUN_DIR.relative_to(REPO)),
                        str(PILOT_DIR.relative_to(REPO))), out)
    chk(6, "cl_bound_xy_6_readonly",
        cfg.get("cl_bound_xy") == CL_BOUND_XY and cfg.get("cl_bound_xy_readonly") is True
        and CL_BOUND_XY == 6.0, f"cfg={cfg.get('cl_bound_xy')} harness={CL_BOUND_XY}")
    chk(7, "min_scale_targets",
        int(ms.get("min_train", 0)) >= 12 and int(ms.get("min_val", 0)) >= 4
        and int(ms.get("min_test", 0)) >= 6 and int(ms.get("min_disjoint_instances", 0)) >= 6,
        f"train>={ms.get('min_train')} val>={ms.get('min_val')} test>={ms.get('min_test')} "
        f"inst>={ms.get('min_disjoint_instances')}")
    chk(8, "planned_instance_count_ge_6",
        int((cfg.get("instance_plan", {}) or {}).get("min_planned_instances", 0)) >= 6
        and len(instances) >= 6, f"listed={len(instances)}")
    chk(9, "split_before_training", sp.get("split_assignment_before_training") is True)
    chk(10, "no_instance_reuse_across_splits",
        sp.get("no_instance_leakage_across_splits") is True
        and sp.get("allow_instance_leakage_across_splits") is False
        and len(set(inst_ids)) == len(inst_ids), f"unique={len(set(inst_ids))}/{len(inst_ids)}")
    chk(11, "no_coordinate_reuse_across_splits",
        sp.get("no_coordinate_reuse_across_splits") is True
        and len(set(offsets)) == len(instances) and cross_split_offsets == 0
        and not valid_audit["reused_coordinates_across_splits"],
        f"disjoint_offsets={len(set(offsets))}/{len(instances)} cross_split={cross_split_offsets}")
    chk(12, "no_decision_frame_reuse_across_splits",
        sp.get("no_decision_frame_reuse_across_splits") is True
        and not valid_audit["reused_decision_frames_across_splits"])
    chk(13, "no_goal_image_reuse_across_splits",
        sp.get("no_goal_image_reuse_across_splits") is True
        and not valid_audit["reused_goal_images_across_splits"])
    chk(14, "each_instance_render_valid_required",
        bool(instances) and all(i.get("render_valid_required") is True for i in instances))
    chk(15, "each_instance_drive_valid_required",
        bool(instances) and all(i.get("drive_valid_required") is True for i in instances))
    chk(16, "route_family_N_vs_W_primary", rf.get("N_vs_W_90") == "primary")
    chk(17, "same_start_diff_goal_present", rf.get("same_start_diff_goal") == "primary")
    chk(18, "hard_negative_mismatched_goal_present",
        rf.get("hard_negative_mismatched_goal") == "hard_negative")
    chk(19, "secondaries_marked_secondary",
        all(rf.get(k) == "secondary" for k in ("N_vs_E_90", "W_vs_E_180", "near_far_stop_distance")))
    chk(20, "scripted_config_driven_only",
        cc.get("config_driven") is True and cc.get("scripted_poses_only") is True)
    chk(21, "no_policy_model_action_probe_training",
        all(cc.get(k) is False for k in ("policy_inference", "model_inference",
            "closed_loop_policy_execution", "action_probe", "training")))
    chk(22, "forbidden_outputs_block_all", all(x in forb for x in _REQUIRED_FORBIDDEN_OUTPUTS),
        "missing=" + ",".join(x for x in _REQUIRED_FORBIDDEN_OUTPUTS if x not in forb))
    chk(23, "eight_required_artifacts_present",
        all(a in arts for a in _REQUIRED_DATASET_ARTIFACTS) and len(_REQUIRED_DATASET_ARTIFACTS) == 8,
        f"{sum(a in arts for a in _REQUIRED_DATASET_ARTIFACTS)}/8")
    chk(24, "injected_reuse_fails_closed",
        bool(injected) and all(c["failed_closed"] for c in injected)
        and all(c["failed_closed"] for c in req_inject),
        f"{sum(c['failed_closed'] for c in injected)}/{len(injected)} leakage + "
        f"{sum(c['failed_closed'] for c in req_inject)}/{len(req_inject)} requirement")
    chk(25, "valid_plan_passes_as_plan_validation",
        valid_audit["leakage_safe"] is True and valid_audit["meets_min_scale"] is True
        and valid_audit["audit_pass"] is True
        and all(r.get("decision_rgb_path") is None and r.get("goal_rgb_path") is None
                for r in valid_plan),
        f"per_split={valid_audit['per_split_counts']} n_inst={valid_audit['n_instances']} no_images=True")

    C.sort(key=lambda c: c["n"])
    n_pass = sum(1 for c in C if c["pass"])
    return {"checks": C, "n_pass": n_pass, "n_total": len(C), "all_pass": n_pass == len(C),
            "valid_audit": valid_audit, "injected_leakage": injected, "requirement_injection": req_inject,
            "instances": instances, "by_split": {k: len(v) for k, v in by_split.items()},
            "frames_per_split": frames}


def write_dataset_dry_run_artifacts(cfg_path, out_dir) -> tuple:
    """Emit the five named dataset-config dry-run artifacts from the committed checks + audit functions.
    CONFIG/SCHEMA/AUDIT ONLY — no Isaac, no capture, no images, no datasets. Returns (all_pass, paths)."""
    cfg = load_dataset_config(cfg_path)
    res = dataset_dry_run_checks(cfg)
    if res.get("empty_plan"):
        # H8-REV-F-003: refuse to emit ANY artifact for an empty plan (fail closed, create nothing).
        # The CLI wraps this in a try/except that returns 2, preserving the prior no-output behaviour.
        raise ValueError("empty plan — refusing to emit dataset dry-run artifacts")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    overall = "PASS" if res["all_pass"] else "FAIL"
    va = res["valid_audit"]
    rel_cfg = str(cfg_path)
    try:
        rel_cfg = str(Path(cfg_path).resolve().relative_to(REPO))
    except Exception:
        pass

    manifest = {
        "note": "DRY-RUN — dataset config validation only. No Isaac, no capture, no images, no datasets.",
        "mode": "dataset-dry-run", "claim_boundary": CLAIM_BOUNDARY, "config": rel_cfg,
        "config_valid": res["all_pass"], "overall": overall,
        "checks_passed": f"{res['n_pass']}/{res['n_total']}", "gate_history": cfg.get("gate_history"),
        "planned_instance_count": len(res["instances"]),
        "planned_split_instance_counts": res["by_split"],
        "planned_frames_per_split": res["frames_per_split"],
        "cl_bound_xy_readonly": CL_BOUND_XY,
        "allowed_dataset_dryrun_artifacts": list(ALLOWED_DATASET_DRYRUN_ARTIFACTS),
        "no_isaac": True, "no_capture": True, "no_images": True, "no_datasets": True,
        "no_policy_inference": True, "no_training": True, "no_rollout_metrics": True,
    }
    schema = {
        "note": "SCHEMA/PLAN ONLY — null-template record shape + dataset structural expectations; no capture.",
        "example_record_schema": example_record_schema(),
        "recorded_mode_manifest_schema": recorded_mode_manifest_schema(),
        "leakage_audit_schema": leakage_audit_schema(),
        "minimum_scale_targets": cfg.get("minimum_scale"),
        "required_future_dataset_artifacts": cfg.get("required_future_dataset_artifacts"),
        "forbidden_outputs": cfg.get("forbidden_outputs"),
        "route_families": cfg.get("route_families"),
    }
    split_doc = {
        "note": "PLANNED split validation — assignment BEFORE training; disjointness over planned records.",
        "split_policy": cfg.get("split_policy"),
        "instances": [{"id": i.get("id"), "split": i.get("split"), "coord_offset": i.get("coord_offset"),
                       "render_valid_required": i.get("render_valid_required"),
                       "drive_valid_required": i.get("drive_valid_required")} for i in res["instances"]],
        "per_split_instance_counts": res["by_split"],
        "planned_frames_per_split": res["frames_per_split"],
        "planned_per_split_frame_counts": va["per_split_counts"],
        "unique_instances": len({i.get("id") for i in res["instances"]}) == len(res["instances"]),
        "requirement_injection_cases": res["requirement_injection"],
    }
    audit_doc = {
        "note": "DRY-RUN leakage audit over the PLAN — plan validation only, NOT captured evidence; no images exist.",
        "targets": {"min_train": MIN_TRAIN_FRAMES, "min_val": MIN_VAL_FRAMES,
                    "min_test": MIN_TEST_FRAMES, "min_disjoint_instances": MIN_DISJOINT_INSTANCES},
        "valid_plan_audit": {
            "leakage_safe": va["leakage_safe"], "meets_min_scale": va["meets_min_scale"],
            "audit_pass": va["audit_pass"], "per_split_counts": va["per_split_counts"],
            "n_instances": va["n_instances"], "reasons": va["reasons"],
            "plan_validation_only_not_captured_evidence": True},
        "injected_leakage_cases": res["injected_leakage"],
        "all_injected_failed_closed": all(c["failed_closed"] for c in res["injected_leakage"]),
    }
    check_lines = [f"  - [{'PASS' if c['pass'] else 'FAIL'}] {c['n']:>2}. {c['name']}"
                   + (f"  ({c['detail']})" if c["detail"] else "") for c in res["checks"]]
    inj_lines = [f"  - {c['case']}: {'FAIL-CLOSED' if c['failed_closed'] else 'DID NOT FAIL'} "
                 f"(reasons={c['reasons']})" for c in res["injected_leakage"]]
    report = (
        "# H8 Synthetic Fork — Dataset-Config DRY-RUN Report\n\n"
        f"**Status: DRY-RUN (config/schema/audit only) — `{CLAIM_BOUNDARY}`.** No Isaac launched, no "
        "capture, no camera images, no datasets, no policy/model inference, no rollout metrics. "
        f"`CL_BOUND_XY` unchanged (read-only mirror = {CL_BOUND_XY}).\n\n"
        f"- **DRY-RUN: {overall}**  ({res['n_pass']}/{res['n_total']} checks)\n"
        f"- config: {rel_cfg}\n"
        f"- planned instances: {len(res['instances'])}  split instance counts: {res['by_split']}\n"
        f"- valid-plan audit (PLAN validation only, NOT captured evidence): leakage_safe="
        f"{va['leakage_safe']} meets_min_scale={va['meets_min_scale']} audit_pass={va['audit_pass']} "
        f"per_split={va['per_split_counts']}\n\n"
        "## 25 dataset dry-run checks\n" + "\n".join(check_lines) + "\n\n"
        "## Injected leakage failures (must fail closed)\n" + "\n".join(inj_lines) + "\n\n"
        "Claim boundary: SYNTHETIC_DIAGNOSTIC_ONLY; config/schema/audit dry-run only; no capture; no "
        "images; no datasets; no policy/model inference; no training; no rollout metrics "
        "(TL/NE/SR/OSR/SPL/nDTW/CR); no action-probe; no promotion; no autonomy; not training "
        "authorization; CL_BOUND_XY unchanged.\n")

    paths = []
    for fname, content in (("dataset_dryrun_manifest.json", json.dumps(manifest, indent=2)),
                           ("dataset_plan_schema.json", json.dumps(schema, indent=2)),
                           ("dataset_split_validation_dryrun.json", json.dumps(split_doc, indent=2)),
                           ("dataset_leakage_audit_dryrun.json", json.dumps(audit_doc, indent=2)),
                           ("dataset_dryrun_report.md", report)):
        p = out_dir / fname
        p.write_text(content)
        paths.append(p)
    return res["all_pass"], paths


# ── pilot capture config: load + fail-closed validate + capture plan (no Isaac) ──
def _all_config_keys(obj):
    """Recursively yield every mapping KEY in a parsed config (for metric-key scanning)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _all_config_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _all_config_keys(v)


def load_pilot_config(path) -> dict:
    """Load a pilot capture config (YAML). yaml is imported lazily so the module has no yaml dependency
    for its other modes. Raises FileNotFoundError on a missing path and ValueError on a non-mapping."""
    import yaml  # lazy — keeps module-level imports free of extra deps
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"pilot config not found: {path}")
    cfg = yaml.safe_load(p.read_text())
    if not isinstance(cfg, dict):
        raise ValueError(f"pilot config is not a mapping: {path}")
    return cfg


def validate_pilot_config(cfg: dict) -> tuple:
    """Fail-closed validation of a pilot capture config. Returns (ok, issues). It enforces the static
    safety declaration (`authorizes_capture: false`, `authorizes_training: false`), the tiny scope, the
    pilot-only output path, `cl_bound_xy == 6.0`, and that no policy/model/action-probe/training/rollout
    field is authorized. NOTE: `authorizes_capture: false` is a STATIC declaration — the actual capture
    run is authorized only by explicit external approval, never by the config itself."""
    issues = []
    if cfg.get("claim_boundary") != CLAIM_BOUNDARY:
        issues.append("claim_boundary != SYNTHETIC_DIAGNOSTIC_ONLY")
    if cfg.get("mode") != "pilot_capture_config_only":
        issues.append("mode != pilot_capture_config_only")
    if cfg.get("authorizes_capture") is not False:
        issues.append("authorizes_capture must be false")
    if cfg.get("authorizes_training") is not False:
        issues.append("authorizes_training must be false")
    scene = cfg.get("scene")
    if not scene or not (REPO / scene).exists():
        issues.append(f"scene path missing: {scene}")
    out = str(cfg.get("output_dir", "")).rstrip("/")
    if not out.endswith("_recorded_mode_pilot"):
        issues.append(f"output_dir not pilot-only: {out}")
    if out in (str(OUT_DIR.relative_to(REPO)), str(DRYRUN_DIR.relative_to(REPO))):
        issues.append("output_dir collides with the full-dataset or dry-run directory")
    if cfg.get("cl_bound_xy") != CL_BOUND_XY:
        issues.append(f"cl_bound_xy != {CL_BOUND_XY}")
    sc = cfg.get("pilot_scope", {}) or {}
    if int(sc.get("max_instances", 99)) > 2 or int(sc.get("max_decision_frames", 99)) > 2:
        issues.append("pilot scope is not tiny (max_instances/max_decision_frames must be <= 2)")
    if sc.get("full_train_val_test_dataset") is not False:
        issues.append("full train/val/test dataset must not be authorized")
    if sc.get("benchmark_claim") is not False:
        issues.append("benchmark_claim must be false")
    cc = cfg.get("capture_controls", {}) or {}
    if cc.get("scripted_poses_only") is not True:
        issues.append("capture_controls.scripted_poses_only must be true")
    for k in ("policy_inference", "model_inference", "closed_loop_policy_execution", "action_probe",
              "training"):
        if cc.get(k) is not False:
            issues.append(f"capture_controls.{k} must be false")
    for key in _all_config_keys(cfg):
        if key in FORBIDDEN_METRIC_KEYS:
            issues.append(f"rollout metric key {key} present in config")
    return (len(issues) == 0, issues)


def pilot_capture_plan(cfg: dict) -> list:
    """Turn a validated pilot config into the tiny list of planned capture UNITS (config-driven, pure,
    no Isaac). Each unit = one instance + one decision frame + one branch goal of a route family. Only
    the base scene is used (no variant geometry is defined), so instance count is 1 regardless of the
    config's upper bound; the leakage audit will honestly report that (below-scale / not disjoint)."""
    sc = cfg.get("pilot_scope", {}) or {}
    n_frames = max(1, min(int(sc.get("max_decision_frames", 1)), 2))
    variants = sc.get("instances") or [{"id": "pilot_inst0"}]      # base-only until variants are authored
    n_inst = max(1, min(int(sc.get("max_instances", 1)), len(variants)))
    families = [sc.get("primary_route_family", "N_vs_W_90")]
    sec = sc.get("optional_secondary_route_family")
    if sc.get("optional_secondary_only_if_supported") and sec in ROUTE_FAMILIES:
        families.append(sec)
    units = []
    for i in range(n_inst):
        inst = variants[i].get("id", f"pilot_inst{i}")
        for f in range(n_frames):
            df_id = f"{inst}_df{f}"
            for fam in families:
                for br in ROUTE_FAMILIES[fam]["branches"]:
                    units.append({
                        "instance_id": inst, "decision_frame_id": df_id,
                        "goal_image_id": f"{df_id}_{fam}_{br}",
                        "route_family": fam, "branch": br,
                        "action_class": scripted_action_for_branch(br),
                        "decision_xy": list(DECISION_XY), "goal_xy": list(BRANCH_GOAL_XY[br]),
                        "decision_heading_deg": SPAWN_HEADING_DEG,
                        "goal_heading_deg": BRANCH_HEADING_DEG[br]})
    return units


def allowed_pilot_artifacts() -> dict:
    """The pilot artifact contract: exactly the allowed artifacts, and the outputs that are forbidden."""
    return {"claim_boundary": CLAIM_BOUNDARY, "allowed": list(ALLOWED_PILOT_ARTIFACTS),
            "forbidden": list(FORBIDDEN_PILOT_OUTPUTS)}


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


# ── pilot verdict (pure, fail-closed; testable without Isaac) ─────────────────
def pilot_verdict(records, contact_log, audit) -> tuple:
    """Fail-closed pilot verdict from captured records. Pass requires: examples present, every RGB
    non-empty, labels populated, a contact log present, ZERO obstacle contacts, no ambiguous contact
    classification, unique goal-image IDs, and a leakage audit that ran. A tiny pilot's leakage audit
    is EXPECTED to report below-min-scale — that is a reported limitation, NOT a pilot failure. Returns
    (passed, fail_reasons)."""
    reasons = []
    if not records:
        reasons.append("no_examples")
    if any((not r.get("decision_rgb_nonempty")) or (not r.get("goal_rgb_nonempty")) for r in records):
        reasons.append("empty_or_invalid_image")
    if any((not r.get("action_class")) or (not r.get("branch")) for r in records):
        reasons.append("label_not_populated")
    if any(r.get("provenance") in (None, {}, "") for r in records):
        reasons.append("missing_provenance")
    if not contact_log:
        reasons.append("contact_log_missing")
    if any(int((r.get("contact_status") or {}).get("obstacle_contacts_count", 0)) > 0 for r in records):
        reasons.append("obstacle_contact")
    if any((r.get("contact_status") or {}).get("ambiguous") for r in records):
        reasons.append("ambiguous_contact")
    gids = [r.get("goal_image_id") for r in records]
    if len(set(gids)) != len(gids):
        reasons.append("duplicate_goal_image_id")
    if (not isinstance(audit, dict)) or audit.get("n_examples") is None:
        reasons.append("leakage_audit_missing")
    return (len(reasons) == 0, sorted(set(reasons)))


# ── the gated Isaac capture: REAL, config-driven (DEFERRED imports; NOT run here) ──
# ── dataset capture path: explicit routing + fail-closed planning + per-instance validity gate ──
# All of this is NO-ISAAC and creates NOTHING. Real dataset capture is NOT authorized at this wiring
# gate: the production dataset branch refuses to launch; a no-Isaac backend may be INJECTED for tests.

def null_evidence_provider(instance_id):  # noqa: ARG001 - deliberately returns no evidence
    """Default evidence provider: NO recorded render/drive-valid evidence exists, so every instance
    fails the validity gate closed. Tests inject a real provider through the DI seam."""
    return {}


def _validity_record_status(rec, instance_id, scene) -> str:
    """Classify one render/drive-valid evidence record. Returns 'ok' ONLY if the record is present,
    well-formed, `passed is True`, its instance id matches, its scene matches `scene`, and it is not
    stale. Otherwise a structured reason: absent / malformed / false / instance_mismatch /
    scene_mismatch / stale."""
    if rec is None:
        return "absent"
    if not isinstance(rec, dict) or "passed" not in rec:
        return "malformed"
    if rec.get("passed") is not True:
        return "false"
    if rec.get("instance_id") != instance_id:
        return "instance_mismatch"
    if scene is not None and rec.get("scene") != scene:
        return "scene_mismatch"
    if rec.get("stale") is True:
        return "stale"
    return "ok"


def dataset_instance_validity_gate(cfg: dict, evidence_provider=None) -> tuple:
    """Fail-closed per-instance render-valid + drive-valid EVIDENCE gate. For every planned instance it
    requires recorded render_valid AND drive_valid evidence that is present, well-formed, passed, matches
    the instance id + config `scene_base`, and is not stale. Returns (ok, gate_report, reasons). A
    reason names the blocking instance and prerequisite. NO Isaac, NO images, NO outputs."""
    if evidence_provider is None:
        evidence_provider = null_evidence_provider
    scene = cfg.get("scene_base")
    instances = (cfg.get("instance_plan", {}) or {}).get("instances", []) or []
    reasons, per_instance = [], []
    for inst in instances:
        iid = inst.get("id")
        try:
            ev = evidence_provider(iid) or {}
        except Exception as e:  # a provider error is a fail-closed condition, never a pass
            ev = {"_provider_error": str(e)}
        row = {"instance_id": iid, "render_valid": None, "drive_valid": None, "ok": True}
        for prereq in ("render_valid", "drive_valid"):
            rec = ev.get(prereq) if isinstance(ev, dict) else None
            status = _validity_record_status(rec, iid, scene)
            row[prereq] = status
            if status != "ok":
                row["ok"] = False
                reasons.append({"instance_id": iid, "prerequisite": prereq, "reason": status})
        per_instance.append(row)
    if not instances:
        reasons.append({"instance_id": None, "prerequisite": "instances", "reason": "no_planned_instances"})
    ok = bool(instances) and all(r["ok"] for r in per_instance)
    return ok, {"n_instances": len(instances), "per_instance": per_instance,
                "all_instances_gated_pass": ok}, reasons


def _plan_per_split(plan: list) -> dict:
    d = {}
    for r in plan:
        d[r.get("split")] = d.get(r.get("split"), 0) + 1
    return d


def validate_dataset_capture_config(cfg: dict) -> tuple:
    """Fail-closed validator for a DATASET capture config at the wiring gate. It reuses the existing
    25-check `dataset_dry_run_checks` as the SINGLE source of plan validity and adds the capture-gate
    safety declarations. `authorizes_capture` MUST remain false here — this validator never authorizes
    capture. Malformed/missing/contradictory safety fields are rejected. Returns (ok, issues)."""
    if not isinstance(cfg, dict):
        return False, ["config is not a mapping"]
    issues = []
    if cfg.get("mode") != "dataset_capture_config_only":
        issues.append("mode != dataset_capture_config_only")
    if cfg.get("claim_boundary") != CLAIM_BOUNDARY:
        issues.append("claim_boundary != SYNTHETIC_DIAGNOSTIC_ONLY")
    if cfg.get("authorizes_capture") is not False:
        issues.append("authorizes_capture must be false at this wiring gate")
    if cfg.get("authorizes_training") is not False:
        issues.append("authorizes_training must be false")
    scene = cfg.get("scene_base")
    if not scene or not isinstance(scene, str):
        issues.append("scene_base missing or not a string")
    out = str(cfg.get("output_dir", "")).rstrip("/")
    if not out.endswith("_recorded_mode_dataset"):
        issues.append(f"output_dir not dataset-only: {out}")
    if out in (str(OUT_DIR.relative_to(REPO)), str(DRYRUN_DIR.relative_to(REPO)),
               str(PILOT_DIR.relative_to(REPO)), str(DATASET_DRYRUN_DIR.relative_to(REPO))):
        issues.append("output_dir collides with a non-dataset directory")
    if cfg.get("cl_bound_xy") != CL_BOUND_XY:
        issues.append(f"cl_bound_xy != {CL_BOUND_XY}")
    cc = cfg.get("capture_controls", {}) or {}
    for k in ("policy_inference", "model_inference", "closed_loop_policy_execution", "action_probe",
              "training"):
        if cc.get(k) is not False:
            issues.append(f"capture_controls.{k} must be false")
    forb = cfg.get("forbidden_outputs", []) or []
    for x in _REQUIRED_FORBIDDEN_OUTPUTS:
        if x not in forb:
            issues.append(f"forbidden_outputs missing {x}")
    instances = (cfg.get("instance_plan", {}) or {}).get("instances", []) or []
    if not instances:
        issues.append("instance_plan has no instances")
    for i in instances:
        if i.get("render_valid_required") is not True:
            issues.append(f"instance {i.get('id')} missing render_valid_required")
        if i.get("drive_valid_required") is not True:
            issues.append(f"instance {i.get('id')} missing drive_valid_required")
    for key in _all_config_keys(cfg):
        if key in FORBIDDEN_METRIC_KEYS:
            issues.append(f"rollout metric key {key} present in config")
    # the dataset plan must pass the existing 25 dry-run checks (single source of plan validity)
    try:
        res = dataset_dry_run_checks(cfg)
        if not res["all_pass"]:
            issues.append("dataset dry-run checks failed: "
                          + ",".join(c["name"] for c in res["checks"] if not c["pass"]))
    except Exception as e:
        issues.append(f"dataset dry-run checks error: {e}")
    return (len(issues) == 0, issues)


def select_capture_mode(cfg: dict) -> str:
    """EXPLICIT capture routing decision by config mode. No implicit default: an unknown/absent mode
    returns 'unknown' (the caller fails closed)."""
    m = (cfg or {}).get("mode")
    if m == "pilot_capture_config_only":
        return "pilot"
    if m == "dataset_capture_config_only":
        return "dataset"
    return "unknown"


def plan_dataset_capture(cfg: dict, evidence_provider=None) -> dict:
    """PURE, no-Isaac dataset capture PLANNING + fail-closed gating. (1) validate the dataset capture
    config via `validate_dataset_capture_config` (reuses the 25 dry-run checks), (2) build the leakage-
    safe plan via `build_dataset_plan` + `cfg["scene_base"]`, (3) run the per-instance render/drive-valid
    evidence gate. Returns a structured readiness dict. Creates NO images, NO trajectories, NO dataset
    files, launches NO Isaac. `ready` requires config-valid AND a non-empty plan AND the gate passing."""
    cfg_ok, cfg_issues = validate_dataset_capture_config(cfg)
    plan = build_dataset_plan(cfg) if cfg_ok else []          # in-memory plan only (null rgb paths)
    gate_ok, gate_report, gate_reasons = dataset_instance_validity_gate(cfg, evidence_provider)
    ready = bool(cfg_ok and gate_ok and plan)
    blocking = []
    if not cfg_ok:
        blocking.append({"reason": "dataset_config_invalid", "detail": cfg_issues})
    blocking.extend(gate_reasons)
    return {"ready": ready, "config_valid": cfg_ok, "config_issues": cfg_issues,
            "scene_base": cfg.get("scene_base"),
            "n_instances": len({r["instance_id"] for r in plan}), "n_records": len(plan),
            "per_split_counts": _plan_per_split(plan), "validity_gate_pass": gate_ok,
            "validity_gate": gate_report, "blocking_reasons": blocking, "plan": plan}


def run_dataset_capture(args, cfg=None, evidence_provider=None, capture_backend=None) -> int:
    """Dataset capture entrypoint. Fail-closed PLAN + per-instance render/drive-valid gate (no Isaac).
    Never falls through to the pilot planner. Return codes: 2 = not ready (config invalid or a validity
    gate blocked) — nothing created; 3 = ready but real dataset capture is NOT authorized at this wiring
    gate (no `capture_backend` injected) — nothing captured; otherwise the injected no-Isaac backend's
    return code. An injected backend receives the VALIDATED plan and must not launch Isaac."""
    if cfg is None:
        cfg = load_dataset_config(args.config)
    readiness = plan_dataset_capture(cfg, evidence_provider=evidence_provider)
    if not readiness["ready"]:
        print(json.dumps({"dataset_capture_ready": False,
                          "blocking_reasons": readiness["blocking_reasons"]}, indent=2), file=sys.stderr)
        return 2   # fail closed: no Isaac, no images, no dataset files
    if capture_backend is None:
        print(json.dumps({"dataset_capture_ready": True, "authorized": False,
                          "note": "dataset plan + per-instance validity gate PASSED; real dataset "
                                  "capture is gated and requires separate approval — no capture initiated",
                          "n_instances": readiness["n_instances"], "n_records": readiness["n_records"],
                          "per_split_counts": readiness["per_split_counts"]}, indent=2))
        return 3   # ready-but-not-authorized: distinct nonzero code, nothing captured
    return int(capture_backend(cfg, readiness["plan"], readiness))   # injected no-Isaac backend (tests)


def run_capture(args, evidence_provider=None, capture_backend=None) -> int:
    """Route the gated capture by EXPLICIT config mode (`select_capture_mode`). No implicit default.
    pilot -> the unchanged pilot capture path; dataset -> the fail-closed dataset path (no-Isaac plan +
    validity gate; real capture gated); unknown/absent mode -> fail closed (return 2). The dataset-only
    DI hooks (`evidence_provider`, `capture_backend`) never touch the pilot path."""
    try:
        cfg = load_dataset_config(args.config)   # generic YAML load, only to read the declared mode
    except Exception as e:
        print(json.dumps({"capture_config_load_error": str(e)}, indent=2), file=sys.stderr)
        return 2
    sel = select_capture_mode(cfg)
    if sel == "pilot":
        return _run_pilot_capture(args)
    if sel == "dataset":
        return run_dataset_capture(args, cfg, evidence_provider=evidence_provider,
                                   capture_backend=capture_backend)
    print(json.dumps({"unknown_capture_config_mode": cfg.get("mode"),
                      "reason": "config mode must be pilot_capture_config_only or "
                                "dataset_capture_config_only"}, indent=2), file=sys.stderr)
    return 2   # fail closed on unknown/absent mode


def _run_pilot_capture(args) -> int:  # pragma: no cover - requires Isaac + explicit approval
    """REAL, config-driven tiny pilot capture. Loads + fail-closed validates the pilot config (no Isaac
    yet), builds the config-driven capture plan, then — behind the explicit `capture` mode — launches
    Isaac, loads the synthetic fork scene, applies/counts colliders (fail-closed if zero), sets up a
    robot-eye RGB camera, and for each planned unit captures the decision-frame + branch-goal RGB
    images (validating each is non-empty before saving), computes the scripted (policy-free) action +
    branch-choice labels, runs a footprint overlap contact check classified via the reviewed
    is_support_contact/classify_contacts (support allowed, obstacle/ambiguous fail-closed), and records
    unique IDs + coordinates + provenance. Runs the leakage audit on the real records, writes ONLY the
    allowed pilot artifacts, safe-halts on normal exit and exception, and enforces a timeout guard.
    NEVER touches any model/policy path; no training; no rollout metrics; `CL_BOUND_XY` is read-only."""
    import time
    import numpy as np

    # 1) load + fail-closed validate the pilot config (NO Isaac yet)
    cfg = load_pilot_config(args.config)
    ok, issues = validate_pilot_config(cfg)
    out_dir = REPO / str(cfg.get("output_dir", str(PILOT_DIR.relative_to(REPO)))).rstrip("/")
    if not ok:
        print(json.dumps({"pilot_config_valid": False, "issues": issues}, indent=2), file=sys.stderr)
        return 2   # fail closed WITHOUT launching Isaac or writing capture data
    plan = pilot_capture_plan(cfg)
    scene_path = REPO / cfg["scene"]
    img_dir = out_dir / "images"
    provenance = {"scene": cfg["scene"], "config": str(args.config),
                  "gate_history": cfg.get("gate_history"),
                  "harness": "scripts/gnm/h8_synthetic_fork_recorded_mode.py"}

    # 2) launch Isaac (deferred imports)
    from isaacsim.simulation_app import SimulationApp
    app = SimulationApp({"headless": True})
    records, contact_log = [], []
    passed, fail_reasons = False, ["capture_incomplete"]
    t_start = time.monotonic()
    try:
        from isaacsim.core.api import World
        from isaacsim.core.utils.stage import add_reference_to_stage
        from omni.physx import get_physx_scene_query_interface
        import omni.usd
        from pxr import Gf, UsdGeom, UsdLux, UsdPhysics
        import omni.replicator.core as rep
        try:
            from PIL import Image
        except Exception:
            Image = None

        def _yaw_quat(deg):
            h = math.radians(deg) * 0.5
            return np.array([math.cos(h), 0.0, 0.0, math.sin(h)])

        def _in_bounds(x, y):
            return abs(x) < CL_BOUND_XY and abs(y) < CL_BOUND_XY

        def _overlap(query, half, pos, quat):
            """Footprint box overlap → (obstacle_n, support_n, obstacle_paths, ambiguous)."""
            raw = {"paths": [], "ambiguous": False}

            def _report(hit):
                path = ""
                for attr in ("rigid_body", "collision", "prim_path"):
                    try:
                        path = str(getattr(hit, attr))
                        if path:
                            break
                    except Exception:
                        continue
                if path:
                    raw["paths"].append(path)
                else:
                    raw["ambiguous"] = True   # an unresolvable hit prim → ambiguous, fail-closed
                return True
            try:
                query.overlap_box(np.asarray(half, dtype=float),
                                  np.asarray([pos[0], pos[1], pos[2]], dtype=float),
                                  np.asarray([quat[1], quat[2], quat[3], quat[0]], dtype=float),
                                  _report, False)
            except Exception:
                raw["ambiguous"] = True
            support, obstacle = classify_contacts(raw["paths"], "/World/pilot_cam")
            return len(obstacle), len(support), obstacle, support, raw["ambiguous"]

        # scene load
        ctx = omni.usd.get_context(); ctx.new_stage(); app.update()
        stage = ctx.get_stage()
        wx = UsdGeom.Xform.Define(stage, "/World"); stage.SetDefaultPrim(wx.GetPrim())
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z); UsdGeom.SetStageMetersPerUnit(stage, 1.0)
        UsdLux.DomeLight.Define(stage, "/World/DomeLight").CreateIntensityAttr(1500.0)
        scene_root = "/World/Scene"
        add_reference_to_stage(usd_path=str(scene_path), prim_path=scene_root)
        for _ in range(120):
            app.update()

        # apply/count colliders across the authored Gprim types (fail-closed if zero)
        collider_n = 0
        for prim in stage.Traverse():
            if not str(prim.GetPath()).startswith(scene_root + "/"):
                continue
            if prim.IsA(UsdGeom.Gprim) and str(prim.GetTypeName()) in GPRIM_COLLIDER_TYPES:
                if not prim.HasAPI(UsdPhysics.CollisionAPI):
                    UsdPhysics.CollisionAPI.Apply(prim)
                collider_n += 1
        if collider_n == 0:
            raise RuntimeError("no colliders applied (scene has no solid Gprim geometry)")

        world = World(stage_units_in_meters=1.0)
        world.reset()
        query = get_physx_scene_query_interface()

        # robot-eye RGB camera
        cam_path = "/World/pilot_cam"
        cam = UsdGeom.Camera.Define(stage, cam_path)
        cam.CreateClippingRangeAttr(Gf.Vec2f(0.02, 1000.0))
        rp = rep.create.render_product(cam_path, (640, 480))
        annot = rep.AnnotatorRegistry.get_annotator("rgb")
        try:
            annot.attach([rp])
        except Exception:
            annot.attach(rp)
        img_dir.mkdir(parents=True, exist_ok=True)
        half = [0.16, 0.16, 0.12]

        def _capture(xy, heading, img_id):
            """Place the camera at (xy, Z_CAM) facing `heading`, render, validate non-empty, save PNG,
            and run a footprint overlap contact check. Returns (rel_path, nonempty, contact_status)."""
            UsdGeom.XformCommonAPI(stage.GetPrimAtPath(cam_path)).SetTranslate(Gf.Vec3d(xy[0], xy[1], Z_CAM))
            UsdGeom.XformCommonAPI(stage.GetPrimAtPath(cam_path)).SetRotate(Gf.Vec3f(90.0, 0.0, heading - 90.0))
            luma, nonempty, arr = 0.0, False, None
            for _ in range(12):
                try:
                    rep.orchestrator.step(rt_subframes=8)
                except Exception:
                    for _ in range(20):
                        app.update()
                arr = np.asarray(annot.get_data())
                if arr.size and arr.ndim >= 2:
                    luma = float(arr[..., :3].mean()); nonempty = luma > 1.0
                    break
            rel = None
            if nonempty and arr is not None and Image is not None:
                rgb = arr[..., :3].astype("uint8")
                p = img_dir / f"{img_id}.png"
                Image.fromarray(rgb).save(str(p))
                rel = str(p.relative_to(REPO))
            on, sn, opaths, spaths, ambiguous = _overlap(query, half, [xy[0], xy[1], ROBOT_Z], _yaw_quat(heading))
            cs = {"obstacle_contacts_count": on, "support_contacts_count": sn,
                  "support_contact_allowed": SUPPORT_CONTACT_ALLOWED, "obstacle_contact_failure": on > 0,
                  "ambiguous": bool(ambiguous), "hit_prims": opaths, "support_prims": spaths,
                  "in_bounds": _in_bounds(xy[0], xy[1]), "mean_luma": round(luma, 2)}
            return rel, nonempty, cs

        # capture each planned unit (decision frame + branch goal)
        for unit in plan:
            if time.monotonic() - t_start > CAPTURE_TIMEOUT_S * max(1, len(plan)):
                fail_reasons = ["timeout"]; break
            d_rel, d_ne, d_cs = _capture(unit["decision_xy"], unit["decision_heading_deg"],
                                         unit["decision_frame_id"])
            g_rel, g_ne, g_cs = _capture(unit["goal_xy"], unit["goal_heading_deg"], unit["goal_image_id"])
            contact_log.append({"decision_frame_id": unit["decision_frame_id"], "pose": "decision", **d_cs})
            contact_log.append({"goal_image_id": unit["goal_image_id"], "pose": "goal", **g_cs})
            merged = {"obstacle_contacts_count": d_cs["obstacle_contacts_count"] + g_cs["obstacle_contacts_count"],
                      "support_contacts_count": d_cs["support_contacts_count"] + g_cs["support_contacts_count"],
                      "ambiguous": d_cs["ambiguous"] or g_cs["ambiguous"]}
            rec = example_record_schema()
            rec.update({
                "instance_id": unit["instance_id"], "decision_frame_id": unit["decision_frame_id"],
                "goal_image_id": unit["goal_image_id"], "route_family": unit["route_family"],
                "branch": unit["branch"], "action_class": unit["action_class"],
                "branch_choice": branch_choice_label(unit["branch"]),
                "decision_xy": unit["decision_xy"], "goal_xy": unit["goal_xy"],
                "decision_heading_deg": unit["decision_heading_deg"],
                "decision_rgb_path": d_rel, "goal_rgb_path": g_rel,
                "decision_rgb_nonempty": bool(d_ne), "goal_rgb_nonempty": bool(g_ne),
                "contact_status": merged, "provenance": dict(provenance)})
            records.append(rec)
    except Exception as e:
        contact_log.append({"error": str(e)})
    finally:
        sh = safe_halt_command(); sh["executed"] = True     # safe-halt on normal exit AND exception
        audit = audit_examples(records)
        passed, fail_reasons = pilot_verdict(records, contact_log, audit)
        finalize_pilot(records, contact_log, audit, passed, fail_reasons, out_dir)
        try:
            sys.stdout.flush(); sys.stderr.flush()
        except Exception:
            pass
        # force the exit code BEFORE any Isaac shutdown so app.close() cannot mask a failing verdict
        os._exit(0 if passed else 1)
    return 1


def finalize_pilot(records, contact_log, audit, passed, fail_reasons, out_dir: Path) -> int:  # pragma: no cover - capture output
    """Write the seven ALLOWED pilot artifacts (pilot_ prefix). No checkpoints/weights/wandb/rollout
    metrics/benchmark tables/model outputs/action-probe outputs/dataset files — capture outputs only."""
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = recorded_mode_manifest_schema()
    manifest["mode"] = "pilot_capture"
    manifest["examples"] = records
    manifest["leakage_audit"] = audit
    manifest["instances"] = sorted({r.get("instance_id") for r in records if r.get("instance_id")})
    manifest["pilot_pass"] = passed
    manifest["pilot_fail_reasons"] = fail_reasons
    manifest["allowed_pilot_artifacts"] = list(ALLOWED_PILOT_ARTIFACTS)
    manifest["forbidden_pilot_outputs"] = list(FORBIDDEN_PILOT_OUTPUTS)
    (out_dir / "pilot_manifest.json").write_text(json.dumps(manifest, indent=2))
    (out_dir / "pilot_image_index.json").write_text(json.dumps(
        [{"decision_frame_id": r.get("decision_frame_id"), "goal_image_id": r.get("goal_image_id"),
          "decision_rgb_path": r.get("decision_rgb_path"), "goal_rgb_path": r.get("goal_rgb_path"),
          "decision_rgb_nonempty": r.get("decision_rgb_nonempty"),
          "goal_rgb_nonempty": r.get("goal_rgb_nonempty")} for r in records], indent=2))
    (out_dir / "pilot_action_label_table.json").write_text(json.dumps(
        [{"decision_frame_id": r.get("decision_frame_id"), "branch": r.get("branch"),
          "action_class": r.get("action_class"), "route_family": r.get("route_family"),
          "policy_driven": False} for r in records], indent=2))
    (out_dir / "pilot_contact_log.json").write_text(json.dumps(contact_log, indent=2))
    (out_dir / "pilot_provenance_table.json").write_text(json.dumps(
        [{"instance_id": r.get("instance_id"), "decision_frame_id": r.get("decision_frame_id"),
          "goal_image_id": r.get("goal_image_id"), "decision_xy": r.get("decision_xy"),
          "goal_xy": r.get("goal_xy"), "provenance": r.get("provenance")} for r in records], indent=2))
    (out_dir / "pilot_leakage_audit_report.json").write_text(json.dumps(audit, indent=2))
    (out_dir / "pilot_recording_report.md").write_text(
        f"# H8 Synthetic Fork — Tiny Pilot Recording Report\n\n"
        f"**Status: PILOT CAPTURE — `{CLAIM_BOUNDARY}`.** Scripted, policy-free capture; no policy/model "
        f"inference, no training, no rollout metrics, no action-probe. `CL_BOUND_XY` unchanged "
        f"({CL_BOUND_XY}).\n\n"
        f"- **PILOT: {'PASS' if passed else 'FAIL/DEFER'}**  fail_reasons: {fail_reasons}\n"
        f"- examples: {audit.get('n_examples')}  instances: {audit.get('n_instances')}\n"
        f"- leakage_safe: {audit.get('leakage_safe')}  meets_min_scale: {audit.get('meets_min_scale')} "
        f"(a tiny pilot is EXPECTED below min scale — reported limitation, not a certified dataset)\n"
        f"- leakage-audit reasons/limitations: {audit.get('reasons')}\n\n"
        f"Claim boundary: {CLAIM_BOUNDARY}; harness/schema validation pilot only; not a dataset; not "
        f"hospital/real-scene/benchmark/full-ImageNav evidence; no SOTA; no promotion; no autonomy; not "
        f"training authorization; CL_BOUND_XY unchanged.\n")
    return 0


# ── CLI ───────────────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="H8 synthetic fork recorded-mode harness (capture is gated)")
    ap.add_argument("--mode", choices=["validate-config", "dry-run", "dataset-dry-run", "capture"],
                    default="validate-config",
                    help="validate-config (default, no Isaac) | dry-run (schema only) | dataset-dry-run "
                         "(validate the full dataset capture config + emit dataset dry-run artifacts; no "
                         "Isaac) | capture (the gated recorded-mode capture — separate approval)")
    ap.add_argument("--out-dir", default=None,
                    help="output dir; defaults per mode (dry-run -> DRYRUN_DIR, dataset-dry-run -> "
                         "DATASET_DRYRUN_DIR)")
    ap.add_argument("--config", default=None,
                    help="pilot capture config (YAML); required for --mode capture, optional to "
                         "validate under --mode validate-config")
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

    # dataset-config dry-run: validate the full dataset capture config + emit the five dry-run
    # artifacts. CONFIG/SCHEMA/AUDIT ONLY — no Isaac, no capture, no images, no datasets.
    if args.mode == "dataset-dry-run":
        if not args.config:
            print("dataset-dry-run requires --config <dataset yaml>; refusing.", file=sys.stderr)
            return 2
        out_dir = Path(args.out_dir) if args.out_dir else DATASET_DRYRUN_DIR
        try:
            all_pass, paths = write_dataset_dry_run_artifacts(args.config, out_dir)
        except Exception as e:
            print(json.dumps({"dataset_dry_run": False, "error": str(e)}, indent=2), file=sys.stderr)
            return 2
        print(json.dumps({"mode": "dataset-dry-run", "claim_boundary": CLAIM_BOUNDARY,
                          "config": str(args.config), "all_checks_pass": all_pass,
                          "artifacts": [p.name for p in paths], "out_dir": str(out_dir)}, indent=2))
        return 0 if all_pass else 1

    # capture: route by EXPLICIT config mode inside run_capture (pilot vs dataset). Do NOT run the
    # pilot-only pre-validation here — that would wrongly reject a dataset config before routing.
    if args.mode == "capture":
        if not args.config:
            print("capture requires --config <capture yaml>; refusing.", file=sys.stderr)
            return 2
        return run_capture(args)

    ok, issues, summary = validate_config()
    # if a pilot config is supplied, load + fail-closed validate it too (no Isaac)
    pilot = {}
    if args.config:
        try:
            cfg = load_pilot_config(args.config)
            p_ok, p_issues = validate_pilot_config(cfg)
        except Exception as e:
            p_ok, p_issues = False, [f"pilot config load error: {e}"]
        pilot = {"pilot_config": str(args.config), "pilot_config_valid": p_ok,
                 "pilot_config_issues": p_issues}
        ok = ok and p_ok
        issues = issues + p_issues
    print(json.dumps({"mode": args.mode, "claim_boundary": CLAIM_BOUNDARY, "config_valid": ok,
                      "issues": issues, **summary, **pilot}, indent=2))
    if not ok:
        print("config invalid — refusing to proceed.", file=sys.stderr)
        return 1

    if args.mode == "validate-config":
        return 0
    if args.mode == "dry-run":
        out_dir = Path(args.out_dir) if args.out_dir else DRYRUN_DIR
        if args.emit_schema:
            paths = write_dry_run_artifacts(out_dir)
            print(f"dry-run artifacts written to {out_dir}: {[p.name for p in paths]}")
        else:
            print("dry-run OK (no files written; pass --emit-schema to write the dry-run artifacts)")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
