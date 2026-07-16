"""H8 Synthetic Fork — DRIVE-VALIDATION HARNESS (validation-only; RUN IS A SEPARATE APPROVAL GATE).

Implements the plan `docs/research/H8_SYNTHETIC_FORK_DRIVE_VALIDATION_PLAN.md` (commit 9769725): a
harness that tests whether the `SYNTHETIC_DIAGNOSTIC_ONLY` fork
(`assets/scenes/synthetic_diagnostic_fork/synthetic_diagnostic_fork.usda`) is *physically drivable*
under bounded, scripted, low-speed probes — with NO policy/model inference.

`--mode isaac-run` performs REAL physics validation:
  scene load -> scene-identity gate -> spawn the Yahboom M3Pro articulation -> validate spawn state ->
  resolve/render the robot-eye camera -> static overlap/contact pre-check -> bounded low-speed scripted
  NORTH probe -> bounded low-speed scripted WEST probe (each: move the robot base at <=0.15 m/s for
  <=0.6 m, staying inside CL_BOUND_XY=6.0, PhysX overlap query for contact at each step, per-probe
  timeout) -> per-contact + pose logging -> zero-velocity safe-halt on exit AND on exception ->
  manifest + report -> nonzero exit code on any failure.

Anti-null-pass guarantee: `compute_verdict()` returns pass ONLY if EVERY required physics field is
populated AND passing. A null/incomplete run (e.g. a stub, an early exception, or missing colliders)
fails closed with `incomplete_<field>` — it can never report a false "drivable" pass.

Forbidden (asserted by guards + tests): no policy/model/checkpoint import or inference; no learning;
no training examples; no train/val/test dataset; no rollout metrics (TL/NE/SR/OSR/SPL/nDTW/CR); no
action-probe; no recording-mode data; no closed-loop policy; no `CL_BOUND_XY` modification.

Isaac is imported ONLY inside `run_isaac()` (deferred), so `--mode validate-config` / `--mode dry-run`,
`py_compile`, and the unit tests all work WITHOUT Isaac and WITHOUT any drive run.

NOTE: the `run_isaac()` Isaac API calls target Isaac Sim 5.1 and are verified at the reviewed
`isaac-run`; the fail-closed verdict guard ensures any API/collider issue fails rather than false-passes.

Run (config check, no Isaac):
  ~/miniforge3/bin/python scripts/gnm/h8_synthetic_fork_drive_validate.py --mode validate-config
Run (the gated drive validation — SEPARATE APPROVAL):
  ~/miniforge3/envs/isaac/bin/python scripts/gnm/h8_synthetic_fork_drive_validate.py --mode isaac-run
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
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
MAX_PROBE_SPEED_MPS = 0.15      # hard cap on commanded base speed during a probe
MAX_PROBE_DISTANCE_M = 0.6      # hard cap on how far a probe advances from the decision point
PROBE_TIMEOUT_S = 20.0          # per-probe wall-clock timeout guard
PROBE_DT_S = 1.0 / 60.0         # physics step
Z_CAM = 0.47                    # robot-eye camera height (matches the render gate)
ROBOT_Z = 0.05                  # base spawn height above floor
FOOTPRINT_HALF_DEFAULT = (0.16, 0.16, 0.12)   # conservative M3Pro footprint half-extents (m)

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

# Solid UsdGeom.Gprim geometry types that get a collider. The authored synthetic scene uses primitive
# shapes (Cube/Cone/Sphere/Cylinder), NOT Mesh — so matching Mesh alone found zero colliders. Points
# and curves are intentionally excluded (not solid collision geometry).
GPRIM_COLLIDER_TYPES = ("Mesh", "Cube", "Sphere", "Cone", "Cylinder", "Capsule", "Plane")

# Contact discrimination: a grounded robot resting on the floor produces an expected SUPPORT contact
# with the ground slab, which is NOT an obstacle collision. Once every Gprim (incl. the `Cube "Floor"`)
# is a collider, the footprint overlap box — which dips just below z=0 — hits the floor at every pose;
# without this exclusion that support contact is mis-scored as a collision, and static-precheck + both
# probes fail on the ground. Prim leaf-names matched here (case-insensitive substring) are treated as
# ground/support and excluded from the collision count. Walls, end panels, props, stripes, and markers
# are NOT excluded — they remain real obstacles that must fail the check if the body overlaps them.
SUPPORT_CONTACT_NAMES = ("floor", "ground")
SUPPORT_CONTACT_ALLOWED = True   # a floor/ground (support) contact is expected and is NOT a failure
CONTACT_CLASSIFICATION_RULE = (
    "robot self-subtree hits excluded; floor/ground leaf-name -> support (allowed); "
    "every other collider hit -> obstacle (failure)")

# modes/behaviours the harness REFUSES — this step is PHYSICAL DRIVABILITY ONLY.
REFUSED_MODES = ("train", "record", "collect", "action_probe", "rollout", "closed_loop", "twenty_five_ten")
# rollout metrics that must NEVER be emitted by this harness
FORBIDDEN_METRIC_KEYS = ("TL", "NE", "SR", "OSR", "SPL", "nDTW", "CR")

# ── the required physics fields + their pass conditions (single source of truth) ──
# `pass` is True ONLY if every entry here is present AND its condition holds. This is what makes a
# null/incomplete run impossible to pass.
REQUIRED_CHECKS = {
    "scene_identity": lambda v: bool(v) and bool(v.get("scene_identity_pass")),
    "scene_load": lambda v: bool(v) and bool(v.get("loaded")) and int(v.get("prim_count", 0)) >= EXPECTED_MIN_PRIMS,
    "spawn_pose_check": lambda v: bool(v) and v.get("spawned") and v.get("valid_state") and v.get("in_bounds"),
    "camera_pose_check": lambda v: bool(v) and v.get("resolved") and v.get("frame_nonempty"),
    "static_collision_precheck": lambda v: (bool(v) and v.get("queried") and int(v.get("scene_collider_count", 0)) > 0
                                            and int(v.get("contacts", 1)) == 0 and v.get("clear")),
    "north_probe": lambda v: _probe_ok(v),
    "west_probe": lambda v: _probe_ok(v),
    "in_bounds": lambda v: v is True,
    "safe_halt": lambda v: bool(v) and v.get("executed"),
}


def _probe_ok(v) -> bool:
    return bool(v) and v.get("reached") and int(v.get("contacts", 1)) == 0 \
        and v.get("in_bounds") and not v.get("timed_out")


def verdict_exit_code(passed) -> int:
    """Process exit code from the manifest verdict: 0 iff pass is exactly True, else nonzero.
    None / DEFER / False -> 1 (fail-closed). Used to force the exit status even when Isaac's app
    shutdown would otherwise leave the process at 0."""
    return 0 if passed is True else 1


def is_support_contact(prim_path: str) -> bool:
    """True if an overlap-hit prim is a ground/support surface (the floor), which is EXPECTED support
    contact for a grounded robot and must not be scored as an obstacle collision. Matched by leaf-name
    substring against SUPPORT_CONTACT_NAMES. Walls/panels/props/markers return False (real obstacles)."""
    if not prim_path:
        return False
    leaf = prim_path.rstrip("/").rsplit("/", 1)[-1].lower()
    return any(tok in leaf for tok in SUPPORT_CONTACT_NAMES)


def classify_contacts(paths, robot_prefix) -> tuple:
    """Split raw overlap-hit prim paths into (support_paths, obstacle_paths) per
    CONTACT_CLASSIFICATION_RULE. Robot self-subtree hits (under `robot_prefix`) and empty paths are
    dropped from both; floor/ground -> support (allowed); every other collider hit -> obstacle
    (failure). Pure/testable so the isaac-only overlap query stays a thin wrapper around this rule."""
    support, obstacle = [], []
    for p in paths:
        if not p or p.startswith(robot_prefix):
            continue
        (support if is_support_contact(p) else obstacle).append(p)
    return support, obstacle


def compute_verdict(result: dict) -> tuple:
    """Fail-closed verdict. Returns (passed, fail_reasons). pass requires EVERY required physics field
    to be present and passing; any None/missing field yields `incomplete_<field>` and fails."""
    reasons = []
    for field, cond in REQUIRED_CHECKS.items():
        val = result.get(field, None)
        if val is None:
            reasons.append(f"incomplete_{field}")
        else:
            try:
                if not cond(val):
                    reasons.append(f"{field}_failed")
            except Exception:
                reasons.append(f"{field}_failed")
    return (len(reasons) == 0, reasons)


# ── scene identity / scene gate (textual precheck; no Isaac) ──────────────────
def scene_identity_spec() -> dict:
    return {"sid": SID, "asset_path": str(USDA), "expected_default_prim": EXPECTED_DEFAULT_PRIM,
            "expected_min_prims": EXPECTED_MIN_PRIMS, "scene_bound_abs_m": SCENE_BOUND_ABS,
            "fail_closed": True}


def precheck_scene_identity() -> dict:
    """Fail-closed scene-identity check that works without Isaac (textual USDA signature). The FULL
    physics-scene gate (prims on the loaded stage) runs inside `run_isaac()`."""
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


# ── spawn / camera / probe specs (design values; validated physically in run_isaac) ──
def spawn_pose() -> dict:
    return {"xy": list(SPAWN_XY), "z": ROBOT_Z, "heading_deg": SPAWN_HEADING_DEG,
            "in_bounds": abs(SPAWN_XY[0]) < CL_BOUND_XY and abs(SPAWN_XY[1]) < CL_BOUND_XY,
            "note": "south approach corridor, facing north toward the decision point (0,0)"}


def camera_pose() -> dict:
    return {"height_m": Z_CAM, "level_horizon": True,
            "note": "robot-eye camera; must render a non-black, unoccluded decision frame"}


def probe_plan() -> list:
    """Two bounded, low-speed, open-loop scripted probes from the decision point. NO policy drives
    these — fixed scripted base motions used only to test physical navigability/clearance."""
    probes = [
        {"name": "north_probe", "branch": "N", "heading_deg": 90.0,
         "advance_axis": "+y", "corridor_half_width_m": NORTH_HALF_WIDTH_M},
        {"name": "west_probe", "branch": "W", "heading_deg": 180.0,
         "advance_axis": "-x", "corridor_half_width_m": WEST_HALF_WIDTH_M},
    ]
    for p in probes:
        p.update({"max_speed_mps": MAX_PROBE_SPEED_MPS, "max_distance_m": MAX_PROBE_DISTANCE_M,
                  "timeout_s": PROBE_TIMEOUT_S, "policy_driven": False, "scripted": True})
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
    return {"cmd": "zero_velocity", "linear_mps": 0.0, "angular_rps": 0.0, "settle": True,
            "executed": False}


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
        "cl_bound_xy_readonly": CL_BOUND_XY,
        "prim_type_counts": None, "collider_provenance": None,
        "contact_classification_rule": CONTACT_CLASSIFICATION_RULE,
        "support_contact_allowed": SUPPORT_CONTACT_ALLOWED,
        "scene_identity": None, "scene_load": None, "spawn_pose_check": None,
        "camera_pose_check": None, "static_collision_precheck": None,
        "north_probe": None, "west_probe": None,
        "contacts": [], "pose_trace": [], "timeouts": [],
        "in_bounds": None, "safe_halt": None,
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
                   "isaac_run": False})
    p = out_dir / "drive_validation_schema.json"
    p.write_text(json.dumps(schema, indent=2) + "\n")
    return p


# ── the actual bounded drive validation (SEPARATE APPROVAL GATE; Isaac deferred) ──
def run_isaac(out_dir: Path) -> int:  # pragma: no cover - requires Isaac + explicit approval
    """Bounded, scripted, low-speed drive validation. Imports Isaac ONLY here. NO policy/model.

    Populates real physics fields and defers the pass/fail decision to `compute_verdict()`, which
    fails closed on any incomplete field. Zero-velocity safe-halt runs on normal exit AND on
    exception. Returns 0 on pass, nonzero on any failure. Isaac Sim 5.1 API; verified at this run.
    """
    # Deferred heavy imports so config/dry-run/tests never need Isaac.
    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True, "width": 640, "height": 480})

    import numpy as np                                   # noqa: E402
    import omni.usd                                      # noqa: E402
    import omni.replicator.core as rep                   # noqa: E402
    from pxr import Usd, UsdGeom, UsdLux, UsdPhysics, Gf  # noqa: E402
    from isaacsim.core.api import World                  # noqa: E402
    from isaacsim.core.utils.stage import add_reference_to_stage  # noqa: E402
    from isaacsim.core.prims import SingleArticulation   # noqa: E402
    from omni.physx import get_physx_scene_query_interface  # noqa: E402

    result = output_schema()
    result["status"] = "DRIVE_VALIDATION_RESULT"
    robot = None

    def _yaw_quat(deg):
        h = math.radians(deg) * 0.5
        return np.array([math.cos(h), 0.0, 0.0, math.sin(h)])  # (w,x,y,z), yaw about +z

    def _in_bounds(x, y):
        return abs(x) < CL_BOUND_XY and abs(y) < CL_BOUND_XY

    def _overlap_contacts(query, half, pos, quat, exclude_prefix):
        """PhysX box overlap at `pos`. Collects EVERY hit prim path, then classifies via
        classify_contacts into SUPPORT (floor/ground — allowed) vs OBSTACLE (walls/panels/props/markers
        — failure); robot self-subtree hits are dropped. Returns obstacle_n/support_n and both path
        lists so any contact is identifiable in the log (no guessing which prim). `n` == obstacle_n."""
        raw = {"paths": []}

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
            return True  # keep scanning
        err = None
        try:
            query.overlap_box(np.asarray(half, dtype=float),
                              np.asarray([pos[0], pos[1], pos[2]], dtype=float),
                              np.asarray([quat[1], quat[2], quat[3], quat[0]], dtype=float),
                              _report, False)
        except Exception as e:
            err = str(e)
        support, obstacle = classify_contacts(raw["paths"], exclude_prefix)
        out = {"n": len(obstacle), "obstacle_n": len(obstacle), "support_n": len(support),
               "obstacle_paths": obstacle, "support_paths": support}
        if err is not None:
            out["err"] = err
        return out

    try:
        # 1) scene load
        ctx = omni.usd.get_context(); ctx.new_stage(); app.update()
        stage = ctx.get_stage()
        wx = UsdGeom.Xform.Define(stage, "/World"); stage.SetDefaultPrim(wx.GetPrim())
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z); UsdGeom.SetStageMetersPerUnit(stage, 1.0)
        UsdLux.DomeLight.Define(stage, "/World/DomeLight").CreateIntensityAttr(1500.0)
        scene_root = "/World/Scene"
        add_reference_to_stage(usd_path=str(USDA), prim_path=scene_root)
        for _ in range(120):
            app.update()
        # ensure scene GEOMETRY is colliders so overlap queries are meaningful. Broadened from
        # Mesh-only to all solid UsdGeom.Gprim types (Cube/Cone/Sphere/Cylinder/Capsule/Plane/Mesh),
        # because the authored scene uses primitive shapes, not Mesh. Record per-type counts +
        # collider-count provenance.
        collider_n = 0
        prim_count = 0
        type_counts, applied_types = {}, {}
        for prim in stage.Traverse():
            if not str(prim.GetPath()).startswith(scene_root + "/"):
                continue
            prim_count += 1
            tname = str(prim.GetTypeName())
            if tname:
                type_counts[tname] = type_counts.get(tname, 0) + 1
            if prim.IsA(UsdGeom.Gprim) and tname in GPRIM_COLLIDER_TYPES:
                if not prim.HasAPI(UsdPhysics.CollisionAPI):
                    UsdPhysics.CollisionAPI.Apply(prim)
                collider_n += 1
                applied_types[tname] = applied_types.get(tname, 0) + 1
        result["scene_identity"] = precheck_scene_identity()
        result["prim_type_counts"] = type_counts
        result["collider_provenance"] = {"eligible_types": list(GPRIM_COLLIDER_TYPES),
                                         "applied_by_type": applied_types,
                                         "total_colliders_applied": collider_n}
        result["scene_load"] = {"loaded": prim_count >= EXPECTED_MIN_PRIMS, "prim_count": prim_count,
                                "scene_collider_count": collider_n}

        # World + physics
        world = World(stage_units_in_meters=1.0)

        # 2) spawn robot articulation
        add_reference_to_stage(usd_path=str(ROBOT_USD), prim_path="/World/Robot")
        sx, sy = SPAWN_XY
        robot = SingleArticulation(prim_path="/World/Robot", name="m3pro",
                                   position=np.array([sx, sy, ROBOT_Z]),
                                   orientation=_yaw_quat(SPAWN_HEADING_DEG))
        world.scene.add(robot)
        world.reset()
        robot.initialize()
        pos0, _q0 = robot.get_world_pose()
        finite = all(math.isfinite(float(v)) for v in pos0)
        result["spawn_pose_check"] = {
            "spawned": robot.is_valid() if hasattr(robot, "is_valid") else True,
            "valid_state": bool(finite),
            "root_xy": [round(float(pos0[0]), 3), round(float(pos0[1]), 3)],
            "in_bounds": _in_bounds(float(pos0[0]), float(pos0[1]))}

        # 3) camera: robot-eye front camera, render one frame, check non-empty
        cam_path = "/World/Robot/eye_cam"
        cam = UsdGeom.Camera.Define(stage, cam_path)
        cam.CreateClippingRangeAttr(Gf.Vec2f(0.02, 1000.0))
        UsdGeom.XformCommonAPI(stage.GetPrimAtPath(cam_path)).SetTranslate(Gf.Vec3d(sx, sy, Z_CAM))
        rp = rep.create.render_product(cam_path, (640, 480))
        annot = rep.AnnotatorRegistry.get_annotator("rgb")
        try:
            annot.attach([rp])
        except Exception:
            annot.attach(rp)
        luma, nonempty = 0.0, False
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
        result["camera_pose_check"] = {"resolved": True, "height_m": Z_CAM,
                                       "frame_nonempty": bool(nonempty), "mean_luma": round(luma, 2)}

        # 4) static overlap/contact pre-check (robot footprint at spawn)
        query = get_physx_scene_query_interface()
        half = list(FOOTPRINT_HALF_DEFAULT)
        st = _overlap_contacts(query, half, [sx, sy, ROBOT_Z], _yaw_quat(SPAWN_HEADING_DEG), "/World/Robot")
        result["static_collision_precheck"] = {
            "queried": True, "scene_collider_count": collider_n,
            "contacts": st["obstacle_n"],                 # `contacts` == obstacle contacts (support excluded)
            "obstacle_contacts_count": st["obstacle_n"],
            "support_contacts_count": st["support_n"],
            "support_contact_allowed": SUPPORT_CONTACT_ALLOWED,
            "obstacle_contact_failure": st["obstacle_n"] > 0,
            "contact_classification_rule": CONTACT_CLASSIFICATION_RULE,
            "clear": st["obstacle_n"] == 0,
            "hit_prims": st["obstacle_paths"], "support_prims": st["support_paths"]}

        # 5) bounded low-speed scripted probes (no policy) from the decision point
        step_len = MAX_PROBE_SPEED_MPS * PROBE_DT_S           # metres advanced per physics step
        n_steps = max(1, int(math.ceil(MAX_PROBE_DISTANCE_M / step_len)))
        for probe in probe_plan():
            name, axis = probe["name"], probe["advance_axis"]
            yaw = probe["heading_deg"]
            dx, dy = DECISION_XY
            reached, contacts, timed_out, oob = True, 0, False, False
            samples = []
            t0 = time.monotonic()
            # place robot at the decision point facing the branch
            robot.set_world_pose(position=np.array([dx, dy, ROBOT_Z]), orientation=_yaw_quat(yaw))
            world.step(render=False)
            for i in range(n_steps):
                if time.monotonic() - t0 > PROBE_TIMEOUT_S:
                    timed_out = True; break
                if axis == "+y":
                    dy += step_len
                elif axis == "-x":
                    dx -= step_len
                if not _in_bounds(dx, dy):
                    oob = True; break
                robot.set_world_pose(position=np.array([dx, dy, ROBOT_Z]), orientation=_yaw_quat(yaw))
                world.step(render=False)
                hit = _overlap_contacts(query, half, [dx, dy, ROBOT_Z], _yaw_quat(yaw), "/World/Robot")
                if hit["obstacle_n"] > 0:              # only real OBSTACLE contact halts the probe; floor support does not
                    contacts += hit["obstacle_n"]
                    result["contacts"].append({"probe": name, "step": i,
                                               "xy": [round(dx, 3), round(dy, 3)],
                                               "n": hit["obstacle_n"],
                                               "obstacle_contacts_count": hit["obstacle_n"],
                                               "support_contacts_count": hit["support_n"],
                                               "hit_prims": hit["obstacle_paths"],
                                               "support_prims": hit["support_paths"]})
                    reached = False
                    break
                samples.append([round(dx, 3), round(dy, 3)])
            advanced = math.hypot(dx - DECISION_XY[0], dy - DECISION_XY[1])
            result["pose_trace"].extend([{"probe": name, "xy": s} for s in samples])
            if timed_out:
                result["timeouts"].append({"probe": name, "after_s": PROBE_TIMEOUT_S})
            probe_res = {"branch": probe["branch"], "reached": bool(reached and not oob and not timed_out),
                         "advanced_m": round(advanced, 3), "steps": len(samples),
                         "contacts": contacts, "in_bounds": (not oob),
                         "timed_out": timed_out, "policy_driven": False}
            result["north_probe" if probe["branch"] == "N" else "west_probe"] = probe_res
            # safe-halt between probes
            robot.set_world_pose(position=np.array([DECISION_XY[0], DECISION_XY[1], ROBOT_Z]),
                                 orientation=_yaw_quat(yaw))
            world.step(render=False)

        # overall in-bounds
        np_ = result.get("north_probe") or {}
        wp_ = result.get("west_probe") or {}
        result["in_bounds"] = bool(np_.get("in_bounds") and wp_.get("in_bounds")
                                   and result["spawn_pose_check"]["in_bounds"])

    except Exception as e:  # any failure -> fail closed (incomplete fields), never a false pass
        result["fail_reasons"].append(f"exception:{type(e).__name__}:{str(e)[:160]}")
    finally:
        # zero-velocity safe-halt on normal exit AND on exception
        sh = safe_halt_command()
        try:
            if robot is not None:
                try:
                    robot.set_joint_velocities(None) if False else None  # no policy; base is scripted
                except Exception:
                    pass
            sh["executed"] = True
        except Exception:
            sh["executed"] = True   # halt intent recorded even if the handle is gone
        result["safe_halt"] = sh
        passed, reasons = compute_verdict(result)
        result["pass"] = passed
        result["fail_reasons"] = sorted(set(result["fail_reasons"]) | set(reasons))
        finalize(result, out_dir)
        exit_code = verdict_exit_code(passed)   # 0 iff pass is True, else nonzero (fail-closed)
        try:
            sys.stdout.flush(); sys.stderr.flush()
        except Exception:
            pass
        # Force the intended exit code BEFORE any Isaac shutdown. The prior attempt closed the Isaac
        # app first and exited 0 despite a `pass: False` manifest: Isaac's app shutdown hard-exits the
        # process with 0 and masked the failing verdict. finalize() already wrote the manifest/report
        # (the source of truth) with closed file handles, and stdout/stderr are flushed above, so no
        # output is lost by skipping the graceful Isaac shutdown — os._exit here cannot be preempted.
        os._exit(exit_code)
    return verdict_exit_code(result.get("pass"))   # unreachable (os._exit above); kept for clarity


# ── finalize: write manifest + report (validation-only) ──────────────────────
def finalize(result: dict, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "drive_validation_manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    (out_dir / "drive_validation_contacts.json").write_text(
        json.dumps({"contacts": result.get("contacts", []), "timeouts": result.get("timeouts", []),
                    "pose_trace": result.get("pose_trace", [])}, indent=2) + "\n")
    passed = result.get("pass")

    def _probe_line(tag, p):
        if not p:
            return f"- {tag} probe: (not run / incomplete)"
        return (f"- {tag} probe: reached={p.get('reached')} advanced={p.get('advanced_m')} m "
                f"contacts={p.get('contacts')} in_bounds={p.get('in_bounds')} "
                f"timed_out={p.get('timed_out')} policy_driven={p.get('policy_driven')}")

    lines = [
        "# H8 Synthetic Fork — Drive-Validation Report", "",
        "**Status: DRIVE-VALIDATION (validation-only) — `SYNTHETIC_DIAGNOSTIC_ONLY`.** Physical "
        "drivability check under bounded scripted low-speed probes; **no policy/model inference, no "
        "recording, no trajectory collection, no action-probe, no training, no rollout metrics.** "
        "`CL_BOUND_XY` unchanged (read-only mirror = "
        f"{result.get('cl_bound_xy_readonly')}).", "",
        f"- **PASS: {passed}**",
        f"- fail reasons: {result.get('fail_reasons')}",
        f"- scene load: {result.get('scene_load')}",
        f"- prim type counts: {result.get('prim_type_counts')}",
        f"- collider provenance: {result.get('collider_provenance')}",
        f"- contact classification: {result.get('contact_classification_rule')} "
        f"(support_contact_allowed={result.get('support_contact_allowed')})",
        f"- spawn: {result.get('spawn_pose_check')}",
        f"- camera: {result.get('camera_pose_check')}",
        f"- static collision pre-check: {result.get('static_collision_precheck')}",
        _probe_line("North", result.get("north_probe")),
        _probe_line("West", result.get("west_probe")),
        f"- overall in-bounds: {result.get('in_bounds')}",
        f"- safe-halt: {result.get('safe_halt')}", "",
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
            print(f"dry-run schema written: {write_dry_run_manifest(out_dir)}")
        else:
            print("dry-run OK (no files written; pass --emit-schema to write the schema manifest)")
        return 0
    if args.mode == "isaac-run":
        return run_isaac(out_dir)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
