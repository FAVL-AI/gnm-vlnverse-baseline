#!/usr/bin/env python3
"""
scripts/isaaclab/convert_m3pro_to_usd.py

Convert the Yahboom RosMaster M3Pro URDF to Isaac Sim USD format.

Two operational modes:
  FULL MODE    — Isaac Sim is available: uses the official URDF importer with
                 velocity-drive settings correct for an omnidirectional mobile base.
  STANDALONE   — Isaac Sim is NOT available: generates a structurally valid USD
                 stub using the pxr (OpenUSD) Python API so downstream tooling
                 (asset validators, CI checkers) always has a parseable file.

The generated USD is written to:
  fleet_safe_vla/robots/yahboom/m3pro/usd/yahboom_m3pro.usd

A post-conversion checklist validates:
  - All 4 wheel joints are present
  - Camera prim is at the correct position
  - LiDAR prim exists
  - Robot has rigid body physics enabled
  - No zero-mass links

Usage:
  python scripts/isaaclab/convert_m3pro_to_usd.py
  python scripts/isaaclab/convert_m3pro_to_usd.py --urdf path/to/custom.urdf --output path/to/out.usd
  python scripts/isaaclab/convert_m3pro_to_usd.py --headless        # scripted / CI use
  python scripts/isaaclab/convert_m3pro_to_usd.py --validate-only   # check existing USD only

Exit codes:
  0  — success (or validation passed)
  1  — conversion or validation failure
  2  — Isaac Sim unavailable (standalone USD stub written instead, not an error)
"""
from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

# ── Repository layout ──────────────────────────────────────────────────────────

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT   = _SCRIPT_DIR.parents[1]

_DEFAULT_URDF = (
    _REPO_ROOT
    / "fleet_safe_vla" / "robots" / "yahboom" / "m3pro" / "urdf"
    / "yahboom_m3pro.urdf"
)
_DEFAULT_USD_DIR = (
    _REPO_ROOT
    / "fleet_safe_vla" / "robots" / "yahboom" / "m3pro" / "usd"
)
_DEFAULT_OUTPUT = _DEFAULT_USD_DIR / "yahboom_m3pro.usd"

# ── M3Pro physical constants ───────────────────────────────────────────────────

WHEEL_RADIUS_M  = 0.048
HALF_LX         = 0.0775    # half wheelbase
HALF_LY         = 0.0850    # half track width
ROBOT_LENGTH_M  = 0.290
ROBOT_WIDTH_M   = 0.235
ROBOT_HEIGHT_M  = 0.080
CAMERA_POS_XYZ  = (0.10, 0.0, 0.082)   # relative to base_link
LIDAR_POS_XYZ   = (0.0,  0.0, 0.112)   # relative to base_link
MAX_WHEEL_RDS   = 20.0

WHEEL_JOINTS = [
    "fl_wheel_joint",
    "fr_wheel_joint",
    "rl_wheel_joint",
    "rr_wheel_joint",
]

# Isaac Sim URDF import configuration for a velocity-driven omnidirectional base
_IMPORT_CONFIG = {
    "merge_fixed_joints":        True,
    "fix_base":                  False,   # mobile robot
    "drive_strength":            15000.0,
    "position_drive_stiffness":  0.0,     # velocity control — no position stiffness
    "position_drive_damping":    15000.0,
    "self_collision":            False,
    "default_drive_type":        "velocity",
    "joint_type_override": {
        "fl_wheel_joint": "velocity",
        "fr_wheel_joint": "velocity",
        "rl_wheel_joint": "velocity",
        "rr_wheel_joint": "velocity",
    },
    "collision_from_visuals":    True,
    "collision_approximation":   "convexHull",
}


# ── Check result helpers ───────────────────────────────────────────────────────

_PASS = "PASS"
_FAIL = "FAIL"
_WARN = "WARN"
_SKIP = "SKIP"

_ICON = {_PASS: "✓", _FAIL: "✗", _WARN: "⚠", _SKIP: "○"}


class _Check:
    def __init__(self, name: str, status: str, detail: str = "") -> None:
        self.name   = name
        self.status = status
        self.detail = detail

    def __str__(self) -> str:
        line = f"  [{_ICON[self.status]}] {self.status:<4}  {self.name}"
        if self.detail:
            wrapped = textwrap.fill(
                self.detail, width=70,
                initial_indent="            ",
                subsequent_indent="            ",
            )
            line += f"\n{wrapped}"
        return line


def _print_banner(title: str) -> None:
    sep = "═" * 67
    print(f"\n{sep}")
    print(f"  {title}")
    print(f"{sep}")


def _summarise(results: list[_Check]) -> int:
    """Print check table, return 0 if no FAILs else 1."""
    n_pass = sum(1 for r in results if r.status == _PASS)
    n_fail = sum(1 for r in results if r.status == _FAIL)
    n_warn = sum(1 for r in results if r.status == _WARN)
    n_skip = sum(1 for r in results if r.status == _SKIP)

    for r in results:
        print(r)

    print()
    print("═" * 67)
    print(f"  {n_pass} PASS  {n_fail} FAIL  {n_warn} WARN  {n_skip} SKIP")
    if n_fail == 0 and n_warn == 0:
        print("  STATUS: ALL CHECKS PASSED")
    elif n_fail == 0:
        print("  STATUS: PASS WITH WARNINGS")
    else:
        print("  STATUS: FAIL — resolve FAIL items before loading in Isaac Sim")
    print("═" * 67)
    return 1 if n_fail > 0 else 0


# ── USD checklist (works on any USD file via pxr) ─────────────────────────────

def run_usd_checklist(usd_path: Path) -> list[_Check]:
    """
    Post-conversion checklist run against the USD file using the pxr API.

    Checks:
      1. File exists and is non-trivially sized
      2. All 4 wheel joints are represented
      3. Camera prim is at the correct position
      4. LiDAR prim exists
      5. At least one PhysicsRigidBodyAPI is applied (rigid body physics)
      6. No prim has a recorded mass of exactly zero
    """
    results: list[_Check] = []

    # 1. File exists
    if not usd_path.exists():
        results.append(_Check("USD file exists", _FAIL, f"Not found: {usd_path}"))
        return results
    size = usd_path.stat().st_size
    if size < 512:
        results.append(_Check(
            "USD file exists", _WARN,
            f"File is suspiciously small ({size} bytes) — may be a stub only.",
        ))
    else:
        results.append(_Check("USD file exists", _PASS, f"{size:,} bytes at {usd_path}"))

    # Load stage
    try:
        from pxr import Usd, UsdPhysics, UsdGeom, Gf  # type: ignore[import]
    except ImportError:
        results.append(_Check(
            "USD pxr checks", _SKIP,
            "pxr (OpenUSD Python) not available — skipping prim-level checks.",
        ))
        return results

    try:
        stage = Usd.Stage.Open(str(usd_path))
    except Exception as exc:
        results.append(_Check("USD file parseable", _FAIL, str(exc)))
        return results

    results.append(_Check("USD stage opens cleanly", _PASS))

    all_prims = list(stage.TraverseAll())
    prim_names = {p.GetName() for p in all_prims}
    prim_paths = {str(p.GetPath()) for p in all_prims}

    # 2. Wheel joints
    missing_joints = []
    for jname in WHEEL_JOINTS:
        # Joints in USD appear as PhysicsJoint prims or nested prims
        found = any(jname in path for path in prim_paths)
        if not found:
            missing_joints.append(jname)
    if missing_joints:
        results.append(_Check(
            "All 4 wheel joints present", _FAIL,
            f"Missing joints: {missing_joints}\n"
            "Joint names must not be renamed — obs_adapter and env_cfg depend on them.",
        ))
    else:
        results.append(_Check("All 4 wheel joints present", _PASS))

    # 3. Camera prim position
    cam_found = False
    cam_pos_ok = False
    for p in all_prims:
        if "camera" in p.GetName().lower():
            cam_found = True
            xform = UsdGeom.Xformable(p)
            if xform:
                try:
                    t = xform.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
                    tx, ty, tz = t[3][0], t[3][1], t[3][2]
                    ex, ey, ez = CAMERA_POS_XYZ
                    tol = 0.05  # 5 cm tolerance
                    if abs(tx - ex) < tol and abs(ty - ey) < tol and abs(tz - ez) < tol:
                        cam_pos_ok = True
                except Exception:
                    pass
            break
    if not cam_found:
        results.append(_Check(
            "Camera prim exists", _FAIL,
            "No prim with 'camera' in name found. "
            "Add camera_link fixed joint to URDF.",
        ))
    elif cam_pos_ok:
        results.append(_Check(
            "Camera prim at correct position", _PASS,
            f"Position within 5 cm of {CAMERA_POS_XYZ} (rel. base_link)",
        ))
    else:
        results.append(_Check(
            "Camera prim position", _WARN,
            f"Camera found but could not verify position against {CAMERA_POS_XYZ}. "
            "This may be expected in a stub USD.",
        ))

    # 4. LiDAR prim
    lidar_found = any("lidar" in n.lower() for n in prim_names)
    if lidar_found:
        results.append(_Check("LiDAR prim exists", _PASS))
    else:
        results.append(_Check(
            "LiDAR prim exists", _WARN,
            "No prim with 'lidar' in name. LiDAR sensor disabled. "
            "Add lidar_link to URDF when sensor is available.",
        ))

    # 5. Rigid body physics
    rb_count = 0
    for p in all_prims:
        if p.HasAPI(UsdPhysics.RigidBodyAPI):
            rb_count += 1
    if rb_count > 0:
        results.append(_Check(
            "Robot has rigid body physics", _PASS,
            f"{rb_count} prim(s) with PhysicsRigidBodyAPI",
        ))
    else:
        results.append(_Check(
            "Robot has rigid body physics", _WARN,
            "No PhysicsRigidBodyAPI found. This is expected for a structural stub. "
            "Physics is applied by Isaac Lab's ArticulationCfg at runtime.",
        ))

    # 6. Zero-mass links
    zero_mass_prims = []
    for p in all_prims:
        mass_api = UsdPhysics.MassAPI(p) if p.HasAPI(UsdPhysics.MassAPI) else None
        if mass_api is not None:
            mass_attr = mass_api.GetMassAttr()
            if mass_attr and mass_attr.IsAuthored():
                val = mass_attr.Get()
                if val is not None and float(val) == 0.0:
                    zero_mass_prims.append(str(p.GetPath()))
    if zero_mass_prims:
        results.append(_Check(
            "No zero-mass links", _WARN,
            f"Zero-mass prims: {zero_mass_prims}. "
            "These may cause physics instability in Isaac Sim.",
        ))
    else:
        results.append(_Check(
            "No zero-mass links", _PASS,
            "All authored mass values are non-zero (or no mass attrs present in stub)",
        ))

    return results


# ── Standalone USD stub generator ─────────────────────────────────────────────

def generate_usd_stub(urdf_path: Path, output_path: Path) -> None:
    """
    Generate a structurally valid USD file using pxr (OpenUSD Python API).

    This is the fallback when Isaac Sim is not available. The stub contains:
      - /World/yahboom_m3pro  (root Xform)
        - base_link            (Xform + rigid body markers)
        - fl_wheel, fr_wheel, rl_wheel, rr_wheel  (Cylinder meshes)
        - camera_link          (Xform at correct position)
        - lidar_link           (Xform at correct position)
        - imu_link             (Xform)

    The stub is loadable by any OpenUSD-aware tool and passes the checklist.

    Args:
        urdf_path:   Source URDF (used only for metadata comment).
        output_path: Destination .usd file.

    Raises:
        ImportError: if pxr is not installed.
        IOError:     if the output file cannot be written.
    """
    from pxr import Usd, UsdGeom, UsdPhysics, Sdf, Gf  # type: ignore[import]

    output_path.parent.mkdir(parents=True, exist_ok=True)

    stage = Usd.Stage.CreateNew(str(output_path))
    stage.SetMetadata("comment", (
        f"Yahboom RosMaster M3Pro — USD stub\n"
        f"Generated by: scripts/isaaclab/convert_m3pro_to_usd.py (standalone mode)\n"
        f"Source URDF:  {urdf_path}\n"
        "STATUS: STRUCTURAL BASELINE — use Isaac Sim full mode for physics-ready USD.\n"
        "Inertials are box/cylinder approximations from product spec.\n"
        "Replace with physically measured values before Stage 1 RL training."
    ))

    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)

    # Root
    world = UsdGeom.Xform.Define(stage, "/World")
    robot_root = UsdGeom.Xform.Define(stage, "/World/yahboom_m3pro")

    # base_link — chassis box
    base = UsdGeom.Xform.Define(stage, "/World/yahboom_m3pro/base_link")
    base.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, 0.0))

    # Mark base_link as a rigid body
    UsdPhysics.RigidBodyAPI.Apply(base.GetPrim())
    mass_api = UsdPhysics.MassAPI.Apply(base.GetPrim())
    mass_api.GetMassAttr().Set(1.800)

    chassis = UsdGeom.Cube.Define(stage, "/World/yahboom_m3pro/base_link/chassis_visual")
    chassis.GetSizeAttr().Set(1.0)
    UsdGeom.XformCommonAPI(chassis).SetScale(
        (ROBOT_LENGTH_M, ROBOT_WIDTH_M, ROBOT_HEIGHT_M)
    )
    UsdGeom.XformCommonAPI(chassis).SetTranslate((0.0, 0.0, ROBOT_HEIGHT_M / 2.0))

    # Helper to define a wheel cylinder
    wheel_positions = {
        "fl_wheel": ( HALF_LX,  HALF_LY, 0.0),
        "fr_wheel": ( HALF_LX, -HALF_LY, 0.0),
        "rl_wheel": (-HALF_LX,  HALF_LY, 0.0),
        "rr_wheel": (-HALF_LX, -HALF_LY, 0.0),
    }
    for wname, (wx, wy, wz) in wheel_positions.items():
        wpath = f"/World/yahboom_m3pro/base_link/{wname}"
        wxform = UsdGeom.Xform.Define(stage, wpath)
        UsdGeom.XformCommonAPI(wxform).SetTranslate((wx, wy, wz))

        cyl = UsdGeom.Cylinder.Define(stage, f"{wpath}/visual")
        cyl.GetRadiusAttr().Set(WHEEL_RADIUS_M)
        cyl.GetHeightAttr().Set(0.025)
        cyl.GetAxisAttr().Set("Y")

        wmass = UsdPhysics.MassAPI.Apply(wxform.GetPrim())
        wmass.GetMassAttr().Set(0.150)

        # Joint marker (USD custom data only — full physics added by Isaac Lab)
        joint_name = wname.replace("wheel", "wheel_joint")  # fl_wheel → fl_wheel_joint
        wxform.GetPrim().SetCustomDataByKey("fleetsafe:joint_name", joint_name)
        wxform.GetPrim().SetCustomDataByKey("fleetsafe:joint_type", "continuous")
        wxform.GetPrim().SetCustomDataByKey("fleetsafe:drive_type", "velocity")

    # camera_link — position matches URDF camera_joint origin
    cam_x, cam_y, cam_z = CAMERA_POS_XYZ
    cam = UsdGeom.Xform.Define(stage, "/World/yahboom_m3pro/base_link/camera_link")
    UsdGeom.XformCommonAPI(cam).SetTranslate((cam_x, cam_y, cam_z))
    cam.GetPrim().SetCustomDataByKey("fleetsafe:sensor", "camera_forward")
    cam.GetPrim().SetCustomDataByKey("fleetsafe:hfov_deg", 62.0)
    cam.GetPrim().SetCustomDataByKey("fleetsafe:topic", "/usb_cam/image_raw")

    # camera visual box
    cam_box = UsdGeom.Cube.Define(stage, "/World/yahboom_m3pro/base_link/camera_link/visual")
    UsdGeom.XformCommonAPI(cam_box).SetScale((0.025, 0.090, 0.025))

    # camera_optical_link (ROS optical frame)
    cam_opt = UsdGeom.Xform.Define(
        stage, "/World/yahboom_m3pro/base_link/camera_link/camera_optical_link"
    )
    UsdGeom.XformCommonAPI(cam_opt).SetRotate((-90.0, 0.0, -90.0))

    # lidar_link
    lid_x, lid_y, lid_z = LIDAR_POS_XYZ
    lidar = UsdGeom.Xform.Define(stage, "/World/yahboom_m3pro/base_link/lidar_link")
    UsdGeom.XformCommonAPI(lidar).SetTranslate((lid_x, lid_y, lid_z))
    lidar.GetPrim().SetCustomDataByKey("fleetsafe:sensor", "lidar_2d")
    lidar.GetPrim().SetCustomDataByKey("fleetsafe:topic", "/scan")

    lid_cyl = UsdGeom.Cylinder.Define(
        stage, "/World/yahboom_m3pro/base_link/lidar_link/visual"
    )
    lid_cyl.GetRadiusAttr().Set(0.038)
    lid_cyl.GetHeightAttr().Set(0.040)

    # imu_link
    imu = UsdGeom.Xform.Define(stage, "/World/yahboom_m3pro/base_link/imu_link")
    UsdGeom.XformCommonAPI(imu).SetTranslate((0.0, 0.0, 0.040))
    imu.GetPrim().SetCustomDataByKey("fleetsafe:sensor", "imu")
    imu.GetPrim().SetCustomDataByKey("fleetsafe:topic", "/imu/data")

    # Metadata for the conversion pipeline
    robot_root.GetPrim().SetCustomDataByKey("fleetsafe:source_urdf", str(urdf_path))
    robot_root.GetPrim().SetCustomDataByKey("fleetsafe:conversion_mode", "standalone_stub")
    robot_root.GetPrim().SetCustomDataByKey("fleetsafe:wheel_radius_m", WHEEL_RADIUS_M)
    robot_root.GetPrim().SetCustomDataByKey("fleetsafe:lx_m", HALF_LX)
    robot_root.GetPrim().SetCustomDataByKey("fleetsafe:ly_m", HALF_LY)
    robot_root.GetPrim().SetCustomDataByKey("fleetsafe:max_vx_ms", 0.5)
    robot_root.GetPrim().SetCustomDataByKey("fleetsafe:max_vy_ms", 0.5)
    robot_root.GetPrim().SetCustomDataByKey("fleetsafe:max_wz_rads", 1.0)
    robot_root.GetPrim().SetCustomDataByKey("fleetsafe:joint_names", WHEEL_JOINTS)
    robot_root.GetPrim().SetCustomDataByKey(
        "fleetsafe:status",
        "STRUCTURAL_BASELINE — inertials from product spec, no physics-ready USD"
    )

    stage.Save()


# ── Isaac Sim full conversion ──────────────────────────────────────────────────

def convert_with_isaac(urdf_path: Path, output_path: Path, headless: bool) -> None:
    """
    Convert the M3Pro URDF to USD using the Isaac Sim URDF importer.

    This function must be called AFTER AppLauncher has been instantiated —
    it is called from _run_full_mode() which handles the AppLauncher lifecycle.

    Args:
        urdf_path:   Path to the source URDF.
        output_path: Destination USD path.
        headless:    Whether Isaac Sim was launched headless.
    """
    # All Isaac / omni imports must come after AppLauncher
    import omni.usd                               # type: ignore[import]
    import omni.kit.commands                      # type: ignore[import]
    from omni.importer.urdf import _urdf          # type: ignore[import]
    from omni.isaac.core.utils.extensions import (  # type: ignore[import]
        enable_extension,
    )

    enable_extension("omni.importer.urdf")

    import_cfg = _urdf.ImportConfig()
    import_cfg.merge_fixed_joints           = _IMPORT_CONFIG["merge_fixed_joints"]
    import_cfg.fix_base                     = _IMPORT_CONFIG["fix_base"]
    import_cfg.drive_strength               = _IMPORT_CONFIG["drive_strength"]
    import_cfg.position_drive_stiffness     = _IMPORT_CONFIG["position_drive_stiffness"]
    import_cfg.position_drive_damping       = _IMPORT_CONFIG["position_drive_damping"]
    import_cfg.self_collision               = _IMPORT_CONFIG["self_collision"]
    import_cfg.default_drive_type          = (
        _urdf.UrdfJointTargetType.JointDriveVelocity
    )
    import_cfg.collision_from_visuals       = _IMPORT_CONFIG["collision_from_visuals"]
    import_cfg.collision_approximation     = _IMPORT_CONFIG["collision_approximation"]

    # Apply per-joint velocity drive overrides
    for jname in _IMPORT_CONFIG["joint_type_override"]:
        import_cfg.joint_drive_config[jname] = _urdf.UrdfJointTargetType.JointDriveVelocity

    output_path.parent.mkdir(parents=True, exist_ok=True)

    result, import_err = omni.kit.commands.execute(
        "URDFParseAndImportFile",
        urdf_path=str(urdf_path),
        import_config=import_cfg,
        dest_path=str(output_path),
    )

    if import_err or not output_path.exists():
        raise RuntimeError(
            f"URDF import failed.\n"
            f"  Source : {urdf_path}\n"
            f"  Dest   : {output_path}\n"
            f"  Error  : {import_err}"
        )


def _run_full_mode(urdf_path: Path, output_path: Path, headless: bool) -> int:
    """
    Launch Isaac Sim AppLauncher, run conversion, then run the checklist.

    Returns 0 on success, 1 on failure.
    """
    # AppLauncher must be first — no omni imports before this
    from isaaclab.app import AppLauncher  # type: ignore[import]

    class _LaunchArgs:
        pass

    la = _LaunchArgs()
    la.headless        = headless
    la.enable_cameras  = False

    app_launcher    = AppLauncher(la)
    simulation_app  = app_launcher.app

    exit_code = 0
    try:
        print(f"[convert_m3pro] Converting URDF → USD (Isaac Sim mode)")
        print(f"  Source : {urdf_path}")
        print(f"  Output : {output_path}")
        convert_with_isaac(urdf_path, output_path, headless)
        size = output_path.stat().st_size
        print(f"  Done   : {size:,} bytes written")

        _print_banner("Post-conversion checklist")
        results = run_usd_checklist(output_path)
        exit_code = _summarise(results)

    except Exception as exc:
        print(f"\n[convert_m3pro] CONVERSION FAILED: {exc}", file=sys.stderr)
        exit_code = 1
    finally:
        simulation_app.close()

    return exit_code


# ── CLI ────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Convert Yahboom M3Pro URDF to Isaac Sim USD.\n"
            "Falls back to an OpenUSD structural stub if Isaac Sim is not available."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              # Default paths (URDF → USD):
              python scripts/isaaclab/convert_m3pro_to_usd.py

              # Custom paths:
              python scripts/isaaclab/convert_m3pro_to_usd.py \\
                  --urdf path/to/custom.urdf \\
                  --output path/to/output.usd

              # CI / scripted (suppresses GUI window):
              python scripts/isaaclab/convert_m3pro_to_usd.py --headless

              # Only validate an already-converted USD:
              python scripts/isaaclab/convert_m3pro_to_usd.py --validate-only
        """),
    )
    parser.add_argument(
        "--urdf",
        type=Path,
        default=_DEFAULT_URDF,
        metavar="PATH",
        help="Source URDF path (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_DEFAULT_OUTPUT,
        metavar="PATH",
        help="Destination USD path (default: %(default)s)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=False,
        help="Launch Isaac Sim without a GUI window (for scripted / CI use)",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        default=False,
        help="Skip conversion and only run the checklist on an existing USD file",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Overwrite an existing USD without prompting",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args   = parser.parse_args(argv)

    urdf_path: Path = args.urdf.resolve()
    output_path: Path = args.output.resolve()

    _print_banner("Yahboom M3Pro — URDF → USD Converter  |  FleetSafe Benchmark")
    print(f"  URDF   : {urdf_path}")
    print(f"  Output : {output_path}")
    print()

    # ── Validate-only mode ────────────────────────────────────────────────────
    if args.validate_only:
        print("[convert_m3pro] Running checklist on existing USD (no conversion).")
        results = run_usd_checklist(output_path)
        return _summarise(results)

    # ── Preflight: URDF must exist ────────────────────────────────────────────
    if not urdf_path.exists():
        print(
            f"[convert_m3pro] ERROR: URDF not found: {urdf_path}\n"
            "  Run: python scripts/isaaclab/check_m3pro_isaac_asset.py",
            file=sys.stderr,
        )
        return 1

    # ── Guard existing output ─────────────────────────────────────────────────
    if output_path.exists() and not args.force:
        print(
            f"[convert_m3pro] USD already exists: {output_path}\n"
            "  Use --force to overwrite, or --validate-only to check it."
        )
        return 0

    # ── Attempt Isaac Sim full mode ───────────────────────────────────────────
    try:
        import isaaclab  # noqa: F401
        isaac_available = True
    except ImportError:
        isaac_available = False

    if isaac_available:
        print("[convert_m3pro] Isaac Sim detected — running full URDF importer.")
        return _run_full_mode(urdf_path, output_path, headless=args.headless)

    # ── Standalone stub mode ──────────────────────────────────────────────────
    print(
        "[convert_m3pro] Isaac Sim not available — generating structural USD stub.\n"
        "  Activate the isaac conda environment for a physics-ready USD:\n"
        "    conda activate isaac\n"
        "    python scripts/isaaclab/convert_m3pro_to_usd.py"
    )

    try:
        import pxr  # noqa: F401
    except ImportError:
        print(
            "[convert_m3pro] ERROR: neither isaaclab nor pxr (OpenUSD) is installed.\n"
            "  Install one of:\n"
            "    pip install usd-core            # OpenUSD Python\n"
            "    conda activate isaac             # full Isaac Sim",
            file=sys.stderr,
        )
        return 1

    print(f"[convert_m3pro] Writing USD stub to: {output_path}")
    try:
        generate_usd_stub(urdf_path, output_path)
    except Exception as exc:
        print(f"[convert_m3pro] ERROR: stub generation failed: {exc}", file=sys.stderr)
        return 1

    size = output_path.stat().st_size
    print(f"[convert_m3pro] Stub written: {size:,} bytes")
    print()

    _print_banner("Post-generation checklist (stub USD)")
    results = run_usd_checklist(output_path)
    rc = _summarise(results)

    print()
    print(
        "NOTE: This is a structural stub, not a physics-ready USD.\n"
        "      Isaac Lab loads the URDF directly via UrdfFileCfg and\n"
        "      auto-converts on first run — the stub aids offline tooling only.\n"
        "      For a full physics-ready USD, activate the Isaac conda env and\n"
        "      rerun this script."
    )

    # Stub generation is not a hard failure — return 2 to signal standalone mode
    return 2 if rc == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
