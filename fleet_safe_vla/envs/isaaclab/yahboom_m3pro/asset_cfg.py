"""
fleet_safe_vla/envs/isaaclab/yahboom_m3pro/asset_cfg.py

Isaac Lab articulation configuration for the Yahboom RosMaster M3Pro.

STATUS: STRUCTURAL BASELINE — inertials are box/cylinder approximations from
product specifications. Replace with physically measured values before any
sim-to-real transfer claim. See ASSET_IMPORT_PLAN.md.

All Isaac Lab imports are guarded by try/except so this module is importable
without the isaac conda environment (required for CI).
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]

# ── Asset paths ───────────────────────────────────────────────────────────────

M3PRO_URDF       = REPO_ROOT / "fleet_safe_vla/robots/yahboom/m3pro/urdf/yahboom_m3pro.urdf"
M3PRO_USD_DIR    = REPO_ROOT / "fleet_safe_vla/robots/yahboom/m3pro/usd"
CONTRACT_YAML    = REPO_ROOT / "fleet_safe_vla/robots/yahboom/config/robot_contract_m3pro.yaml"

# ── Geometry constants (from robot_contract_m3pro.yaml + URDF) ────────────────

WHEEL_RADIUS_M   = 0.048    # m  — verify with calipers
WHEELBASE_M      = 0.155    # m  — front↔rear axle centre distance
TRACK_WIDTH_M    = 0.170    # m  — left↔right wheel centre distance
HALF_LX          = WHEELBASE_M  / 2.0
HALF_LY          = TRACK_WIDTH_M / 2.0
ROBOT_RADIUS_M   = 0.15     # bounding circle for CBF-QP

# Velocity limits
MAX_VX_MS        = 0.5      # m/s
MAX_VY_MS        = 0.5      # m/s
MAX_WZ_RDS       = 1.0      # rad/s
MAX_WHEEL_RDS    = 20.0     # rad/s

# Joint names — DO NOT RENAME (obs_adapter, env_cfg, safety_node use these)
WHEEL_JOINTS     = ["fl_wheel_joint", "fr_wheel_joint", "rl_wheel_joint", "rr_wheel_joint"]
CAMERA_FRAME     = "camera_link"
LIDAR_FRAME      = "lidar_link"
IMU_FRAME        = "imu_link"


class AssetNotFoundError(RuntimeError):
    """Raised when required simulation assets are missing."""


def assert_assets_exist() -> None:
    """Raise AssetNotFoundError with actionable message if URDF is missing."""
    if not M3PRO_URDF.exists():
        raise AssetNotFoundError(
            f"\n\n[M3Pro Isaac] URDF not found: {M3PRO_URDF}\n\n"
            "  The M3Pro URDF exists — this error should not occur in a clean checkout.\n"
            "  Run: python scripts/isaaclab/check_m3pro_isaac_asset.py\n"
            "  For full asset documentation:\n"
            f"    {REPO_ROOT}/fleet_safe_vla/robots/yahboom/m3pro/ASSET_IMPORT_PLAN.md\n"
        )


def missing_asset_warnings() -> list[str]:
    """
    Return list of human-readable warnings about assets that are not yet
    publication-grade. These are logged in every viewer session.
    """
    warnings: list[str] = []

    if not M3PRO_URDF.exists():
        warnings.append(
            f"URDF missing: {M3PRO_URDF.relative_to(REPO_ROOT)}"
        )

    usd_candidate = M3PRO_USD_DIR / "yahboom_m3pro" / "yahboom_m3pro.usd"
    if not usd_candidate.exists():
        warnings.append(
            "USD cache not yet generated — will be created on first Isaac Sim run. "
            f"Expected: {usd_candidate.relative_to(REPO_ROOT)}"
        )

    warnings.append(
        "INERTIALS: box/cylinder approximations from product spec. "
        "Replace with physically measured values before Stage 1 RL. "
        "~30% velocity tracking error expected until corrected."
    )

    warnings.append(
        "MESH GEOMETRY: primitive geometry only (box/cylinder). "
        "No STL/DAE mesh files. Sufficient for kinematics and CBF evaluation."
    )

    return warnings


# ── Isaac Lab config factory ──────────────────────────────────────────────────
# Wrapped in try/except so module is importable outside Isaac env.

try:
    from isaaclab.assets import ArticulationCfg
    from isaaclab.actuators import ImplicitActuatorCfg
    from isaaclab.sim.converters import UrdfConverterCfg
    from isaaclab.sim.spawners.from_files import UrdfFileCfg
    _ISAACLAB_AVAILABLE = True
except ImportError:
    _ISAACLAB_AVAILABLE = False


def build_m3pro_articulation_cfg(
    prim_path: str = "/World/Yahboom_M3Pro",
    spawn_pos: tuple[float, float, float] = (0.0, 0.0, 0.055),
) -> "ArticulationCfg":
    """
    Return an ArticulationCfg for the M3Pro.

    Raises ImportError if isaaclab is not installed.
    Raises AssetNotFoundError if URDF is missing.
    """
    if not _ISAACLAB_AVAILABLE:
        raise ImportError(
            "isaaclab is not installed. Activate the isaac conda environment:\n"
            "  conda activate isaac"
        )
    assert_assets_exist()
    M3PRO_USD_DIR.mkdir(parents=True, exist_ok=True)

    wheel_drive = UrdfConverterCfg.JointDriveCfg(
        target_type="velocity",
        gains=UrdfConverterCfg.JointDriveCfg.PDGainsCfg(stiffness=0.0, damping=2.0),
    )

    return ArticulationCfg(
        prim_path=prim_path,
        spawn=UrdfFileCfg(
            asset_path=str(M3PRO_URDF),
            usd_dir=str(M3PRO_USD_DIR),
            fix_base=False,
            merge_fixed_joints=True,
            self_collision=False,
            joint_drive=wheel_drive,
        ),
        init_state=ArticulationCfg.InitialStateCfg(
            pos=spawn_pos,
            joint_pos={j: 0.0 for j in WHEEL_JOINTS},
        ),
        actuators={
            "wheels": ImplicitActuatorCfg(
                joint_names_expr=[".*wheel.*"],
                effort_limit_sim=1.0,
                velocity_limit_sim=MAX_WHEEL_RDS,
                stiffness=0.0,
                damping=0.1,
            )
        },
    )
