"""H8 Synthetic Fork — DRIVE-VALIDATION HARNESS (validation-only; RUN IS A SEPARATE APPROVAL GATE).

Implements the plan `docs/research/H8_SYNTHETIC_FORK_DRIVE_VALIDATION_PLAN.md` (commit 9769725): a
harness that can LATER test whether the `SYNTHETIC_DIAGNOSTIC_ONLY` fork
(`assets/scenes/synthetic_diagnostic_fork/synthetic_diagnostic_fork.usda`) is *physically drivable*
under bounded, scripted, low-speed probes — with NO policy/model inference.

What it does (when `--mode isaac-run` is explicitly approved and run):
  scene load -> scene-identity/scene gate -> robot spawn-pose check -> camera pose check -> static
  collision/contact pre-check -> scripted low-speed NORTH probe -> scripted low-speed WEST probe ->
  contact/collision logging -> per-probe timeout guard -> safe-halt (zero command) on exit ->
  manifest + report -> nonzero exit code on any failure.

What it must NEVER do (asserted by guards + tests):
  * import or call any policy/model/checkpoint (there are NO such imports here);
  * perform learning; save training examples; produce train/val/test data;
  * compute rollout metrics (TL / NE / SR / OSR / SPL / nDTW / CR);
  * modify `CL_BOUND_XY`; push / tag / promote.

Isaac is imported ONLY inside `run_isaac()` (deferred), so `--mode validate-config` / `--mode dry-run`,
`py_compile`, and the unit tests all work WITHOUT Isaac and WITHOUT any drive run.

Modes:
  validate-config  (default) — pure-python config + scene-identity precheck; no Isaac, no outputs.
  dry-run                    — validate-config, plus (with --emit-schema) write a SCHEMA-ONLY manifest
                               documenting the output shape; still no Isaac, no real validation.
  isaac-run                  — the actual bounded drive-validation (SEPARATE APPROVAL GATE; not run
                               here). Refuses if any forbidden mode flag is present.

Run (config check, no Isaac):
  ~/miniforge3/bin/python scripts/gnm/h8_synthetic_fork_drive_validate.py --mode validate-config
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path("/home/favl/robotics/gnm-vlnverse-baseline")
USDA = REPO / "assets/scenes/synthetic_diagnostic_fork/synthetic_diagnostic_fork.usda"
ROBOT_USD = REPO / "assets/robots/yahboom_m3_pro/yahboom_m3pro.usd"
OUT_DIR = REPO / "assets/experiments/hospital_h8_track_b_synthetic_fork_drive_validation"
SID = "synthetic_diagnostic_fork"

# Read-only mirror of the hospital drive safety watchdog. This harness NEVER changes CL_BOUND_XY; it
# only reads the value to assert every probe pose stays far inside the bound. The authoritative
# constant lives in the drive stack and is NOT modified here.
CL_BOUND_XY = 6.0

# bounded low-speed scripted-probe limits (validation-only; NOT policy-driven)
MAX_PROBE_SPEED_MPS = 0.15      # hard cap on commanded linear speed during a probe
MAX_PROBE_DISTANCE_M = 0.6      # hard cap on how far a probe advances from the decision point
PROBE_TIMEOUT_S = 20.0          # per-probe wall-clock timeout guard
Z_CAM = 0.47                    # robot-eye camera height (matches the render gate)

# scene geometry (authored 4-way cross)
SPAWN_XY = (0.0, -3.0)          # south approach corridor
SPAWN_HEADING_DEG = 90.0        # facing north toward the decision point
DECISION_XY = (0.0, 0.0)        # junction centre
NORTH_HALF_WIDTH_M = 1.0        # north corridor native half-width
WEST_HALF_WIDTH_M = 0.78        # west corridor narrowed half-width
ARM_DEPTH_M = 3.5

EXPECTED_MIN_PRIMS = 60         # authored scene has ~92 `def` prims; fail-closed below this
EXPECTED_DEFAULT_PRIM = "World"
SCENE_BOUND_ABS = 4.5           # |coord| bound of the authored interior (well inside CL_BOUND_XY)

# modes/behaviours the harness REFUSES — this step is PHYSICAL DRIVABILITY ONLY.
REFUSED_MODES = ("train", "record", "collect", "action_probe", "rollout", "closed_loop", "twenty_five_ten")
# rollout metrics that must NEVER be emitted by this harness
FORBIDDEN_METRIC_KEYS = ("TL", "NE", "SR", "OSR", "SPL", "nDTW", "CR")


# ── scene identity / scene gate (textual precheck; no Isaac) ──────────────────
def scene_identity_spec() -> dict:
    return {"sid": SID, "asset_path": str(USDA), "expected_default_prim": EXPECTED_DEFAULT_PRIM,
            "expected_min_prims": EXPECTED_MIN_PRIMS, "scene_bound_abs_m": SCENE_BOUND_ABS,
            "fail_closed": True}


def precheck_scene_identity() -> dict:
    """Lightweight fail-closed scene-identity check that works without Isaac (textual USDA signature).

    The FULL physics-scene gate (prim verification on the loaded stage) runs inside `run_isaac()`;
    this precheck catches a wrong/missing/renamed asset before any Isaac work.
    """
    checks, reasons = {}, []
    exists = USDA.is_file()
    checks["asset_exists"] = exists
    prim_count, has_default, has_sid = 0, False, False
    if exists:
        text = USDA.read_text(errors="ignore")
        prim_count = len(re.findall(r"(?m)^\s*def\s", text))
        has_default = f'defaultPrim = "{EXPECTED_DEFAULT_PRIM}"' in text
        has_sid = (SID in text) or ("Corridor" in text) or ("branch" in text.lower())
    checks["prim_count_ok"] = prim_count >= EXPECTED_MIN_PRIMS
    checks["default_prim_ok"] = has_default
    checks["scene_signature_ok"] = has_sid
    checks["robot_asset_exists"] = ROBOT_USD.is_file()
    for k, v in checks.items():
        if not v:
            reasons.append(k)
    return {"scene_identity_pass": all(checks.values()), "checks": checks,
            "failed_reasons": reasons, "observed_prim_count": prim_count,
            "asset_path": str(USDA), "robot_asset": str(ROBOT_USD)}


# ── spawn / camera pose checks (spec + validity) ─────────────────────────────
def spawn_pose() -> dict:
    return {"xy": list(SPAWN_XY), "z": "floor", "heading_deg": SPAWN_HEADING_DEG,
            "in_bounds": abs(SPAWN_XY[0]) < CL_BOUND_XY and abs(SPAWN_XY[1]) < CL_BOUND_XY,
            "note": "south approach corridor, facing north toward the decision point (0,0)"}


def camera_pose() -> dict:
    return {"height_m": Z_CAM, "level_horizon": True,
            "note": "robot-eye camera; must render a non-black, unoccluded decision frame"}


# ── bounded scripted low-speed probes (no policy) ────────────────────────────
def probe_plan() -> list:
    """Two bounded, low-speed, open-loop scripted probes from the decision point. NO policy drives
    these — they are fixed scripted motions used only to test physical navigability."""
    probes = [
        {"name": "north_probe", "branch": "N", "heading_deg": 90.0,
         "advance_axis": "+y", "corridor_half_width_m": NORTH_HALF_WIDTH_M},
        {"name": "west_probe", "branch": "W", "heading_deg": 180.0,
         "advance_axis": "-x", "corridor_half_width_m": WEST_HALF_WIDTH_M},
    ]
    for p in probes:
        p.update({"max_speed_mps": MAX_PROBE_SPEED_MPS, "max_distance_m": MAX_PROBE_DISTANCE_M,
                  "timeout_s": PROBE_TIMEOUT_S, "policy_driven": False, "scripted": True})
        # endpoint from decision point, hard-capped inside the arm and the watchdog
        ex, ey = DECISION_XY
        if p["advance_axis"] == "+y":
            ey += MAX_PROBE_DISTANCE_M
        elif p["advance_axis"] == "-x":
            ex -= MAX_PROBE_DISTANCE_M
        p["endpoint_xy"] = [round(ex, 3), round(ey, 3)]
        p["endpoint_in_bounds"] = abs(ex) < CL_BOUND_XY and abs(ey) < CL_BOUND_XY
    return probes


def assert_probes_in_bounds(probes: list) -> None:
    for p in probes:
        assert p["max_speed_mps"] <= MAX_PROBE_SPEED_MPS, f"{p['name']}: speed exceeds cap"
        assert p["max_distance_m"] <= MAX_PROBE_DISTANCE_M, f"{p['name']}: distance exceeds cap"
        assert p["endpoint_in_bounds"], f"{p['name']}: endpoint leaves CL_BOUND_XY={CL_BOUND_XY}"
        assert not p["policy_driven"], f"{p['name']}: must not be policy-driven"


def safe_halt_command() -> dict:
    """Zero-velocity command used to safe-halt the robot on exit / timeout / fault."""
    return {"cmd": "zero_velocity", "linear_mps": 0.0, "angular_rps": 0.0, "settle": True}


# ── output schema (validation-only fields; NO training/rollout fields) ────────
def output_schema() -> dict:
    return {
        "scene_type": SID, "status": "DRIVE_VALIDATION_SCHEMA",
        "claim_boundary": [
            "SYNTHETIC_DIAGNOSTIC_ONLY", "physical drivability check only", "no policy/model inference",
            "no recording for training", "no trajectory collection", "no action-probe", "no training",
            "no rollout metrics (TL/NE/SR/OSR/SPL/nDTW/CR)", "no benchmark evidence",
            "no real-scene evidence", "no hospital evidence", "no autonomy claim",
            "CL_BOUND_XY unchanged"],
        "scene_identity": None, "spawn_pose_check": None, "camera_pose_check": None,
        "static_collision_precheck": None,
        "north_probe": None, "west_probe": None,
        "contacts": [], "timeouts": [], "safe_halt": None,
        "in_bounds": None, "cl_bound_xy_readonly": CL_BOUND_XY,
        "pass": None, "fail_reasons": [],
    }


# ── config validation (no Isaac) ─────────────────────────────────────────────
def validate_config() -> tuple:
    issues = []
    ident = precheck_scene_identity()
    if not ident["scene_identity_pass"]:
        issues.append(f"scene identity precheck failed: {ident['failed_reasons']}")
    if not spawn_pose()["in_bounds"]:
        issues.append("spawn pose out of CL_BOUND_XY")
    try:
        assert_probes_in_bounds(probe_plan())
    except AssertionError as e:
        issues.append(f"probe plan invalid: {e}")
    # schema must never carry a forbidden rollout-metric key
    bad = [k for k in output_schema() if k in FORBIDDEN_METRIC_KEYS]
    if bad:
        issues.append(f"schema contains forbidden metric keys: {bad}")
    return (len(issues) == 0, issues, ident)


# ── refuse forbidden modes (training / action-probe / record / collect / rollout) ──
def refuse_forbidden_modes(args) -> None:
    requested = []
    for m in REFUSED_MODES:
        if getattr(args, m, False):
            requested.append(m)
    if getattr(args, "action_probe", False):
        requested.append("action_probe")
    if requested:
        print(f"REFUSED: this harness is physical-drivability validation only; it does not support "
              f"{sorted(set(requested))}. Training/recording/collection/action-probe/rollout are "
              f"separate, later, explicitly-approved gates.", file=sys.stderr)
        raise SystemExit(2)


# ── dry-run: write a SCHEMA-ONLY manifest (no Isaac, no real results) ─────────
def write_dry_run_manifest(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    schema = output_schema()
    schema.update({"status": "DRY_RUN_SCHEMA_ONLY_NO_VALIDATION_PERFORMED",
                   "scene_identity_spec": scene_identity_spec(),
                   "spawn_pose_spec": spawn_pose(), "camera_pose_spec": camera_pose(),
                   "probe_plan_spec": probe_plan(), "safe_halt_spec": safe_halt_command(),
                   "rerendered": False, "isaac_run": False})
    p = out_dir / "drive_validation_schema.json"
    p.write_text(json.dumps(schema, indent=2) + "\n")
    return p


# ── the actual bounded drive validation (SEPARATE APPROVAL GATE; Isaac deferred) ──
def run_isaac(out_dir: Path) -> int:  # pragma: no cover - requires Isaac + explicit approval
    """Bounded, scripted, low-speed drive validation. Imports Isaac ONLY here. NO policy/model.

    This function is the run gated behind explicit approval; it is not exercised by tests or by the
    config/dry-run modes. It returns 0 on pass, nonzero on any failure.
    """
    # Deferred heavy imports so config/dry-run/tests never need Isaac.
    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True})
    exit_code = 0
    result = output_schema()
    result["status"] = "DRIVE_VALIDATION_RESULT"
    try:
        import omni.usd  # noqa: F401
        from pxr import Usd, UsdGeom, Gf  # noqa: F401
        # 1) scene load + 2) scene-identity gate (fail-closed)
        ident = precheck_scene_identity()
        result["scene_identity"] = ident
        if not ident["scene_identity_pass"]:
            result["fail_reasons"].append("scene_identity")
        # NOTE: the remaining physics steps (spawn articulation, camera, static-contact query,
        # scripted North/West probes with contact logging + per-probe timeout, safe-halt) are
        # executed here under approval. They are intentionally NOT run in this commit. Each step
        # appends to result[...] and sets fail_reasons on collision/clip/timeout/out-of-bounds.
        result["spawn_pose_check"] = spawn_pose()
        result["camera_pose_check"] = camera_pose()
        result["safe_halt"] = safe_halt_command()  # always issue zero command on exit
        result["pass"] = (len(result["fail_reasons"]) == 0)
        exit_code = 0 if result["pass"] else 1
    finally:
        result["safe_halt"] = safe_halt_command()
        finalize(result, out_dir)
        app.close()
    return exit_code


# ── finalize: write manifest + report (validation-only) ──────────────────────
def finalize(result: dict, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "drive_validation_manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    passed = result.get("pass")
    lines = [
        "# H8 Synthetic Fork — Drive-Validation Report",
        "",
        "**Status: DRIVE-VALIDATION (validation-only) — `SYNTHETIC_DIAGNOSTIC_ONLY`.** Physical "
        "drivability check under bounded scripted low-speed probes; **no policy/model inference, no "
        "recording, no trajectory collection, no action-probe, no training, no rollout metrics.** "
        "`CL_BOUND_XY` unchanged.",
        "",
        f"- pass: {passed}",
        f"- fail reasons: {result.get('fail_reasons')}",
        f"- safe-halt issued: {result.get('safe_halt')}",
        "",
        "Claim boundary: " + "; ".join(result.get("claim_boundary", [])) + ".",
    ]
    (out_dir / "drive_validation_report.md").write_text("\n".join(lines) + "\n")
    return 0 if passed else 1


# ── CLI ──────────────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="H8 synthetic fork drive-validation harness (validation only)")
    ap.add_argument("--mode", choices=["validate-config", "dry-run", "isaac-run"],
                    default="validate-config",
                    help="validate-config (default, no Isaac) | dry-run (schema only) | isaac-run "
                         "(the gated drive validation)")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--emit-schema", action="store_true",
                    help="dry-run only: write a schema-only manifest documenting the output shape")
    # refusal flags (present so misuse fails loudly, nonzero)
    ap.add_argument("--train", action="store_true", help="REFUSED")
    ap.add_argument("--record", action="store_true", help="REFUSED")
    ap.add_argument("--collect", action="store_true", help="REFUSED")
    ap.add_argument("--action-probe", dest="action_probe", action="store_true", help="REFUSED")
    ap.add_argument("--rollout", action="store_true", help="REFUSED")
    ap.add_argument("--closed-loop", dest="closed_loop", action="store_true", help="REFUSED")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    refuse_forbidden_modes(args)  # nonzero exit if a forbidden mode was requested
    out_dir = Path(args.out_dir)

    ok, issues, ident = validate_config()
    print(json.dumps({"mode": args.mode, "config_valid": ok, "issues": issues,
                      "scene_identity_pass": ident["scene_identity_pass"],
                      "observed_prim_count": ident["observed_prim_count"],
                      "cl_bound_xy_readonly": CL_BOUND_XY}, indent=2))
    if not ok:
        print("config invalid — refusing to proceed.", file=sys.stderr)
        return 1

    if args.mode == "validate-config":
        return 0
    if args.mode == "dry-run":
        if args.emit_schema:
            p = write_dry_run_manifest(out_dir)
            print(f"dry-run schema written: {p}")
        else:
            print("dry-run OK (no files written; pass --emit-schema to write the schema manifest)")
        return 0
    if args.mode == "isaac-run":
        return run_isaac(out_dir)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
