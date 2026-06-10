"""
view_yahboom.py — Yahboom Isaac Sim GUI viewer (Fleet-Safe-VLA-OS)

Selectable robot via --robot flag:
  --robot x3     RosMaster X3 (differential drive, 2 wheels)  [available]
  --robot m3pro  RosMaster M3Pro (mecanum, 4 wheels)          [URDF pending]

Loads the chosen robot URDF into Isaac Sim with a visible GUI, ground plane,
dome light, and a fixed overview camera.  Physics runs at 100 Hz; no RL or
control logic is applied.

Usage (via shell wrapper — preferred):
    ./scripts/isaaclab/view_yahboom.sh
    ./scripts/isaaclab/view_yahboom.sh --robot m3pro

Direct usage (isaac env must be active):
    conda activate isaac
    export OMNI_KIT_ACCEPT_EULA=Y
    python scripts/isaaclab/view_yahboom.py [--robot {x3,m3pro}]
    python scripts/isaaclab/view_yahboom.py --robot x3 --device cuda:0  (AppLauncher owns --device)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ── Step 1: AppLauncher FIRST — no omni/isaaclab imports before this ─────────
try:
    from isaaclab.app import AppLauncher
except ModuleNotFoundError:
    print(
        "[ERROR] 'isaaclab' not found.\n"
        "  Activate the isaac conda environment:\n"
        "    conda activate isaac\n"
        "  Then re-run this script."
    )
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parents[2]

# ── Robot definitions ─────────────────────────────────────────────────────────
_ROBOTS: dict[str, dict] = {
    "x3": {
        "label": "RosMaster X3 (differential drive)",
        "urdf": REPO_ROOT / "fleet_safe_vla/robots/yahboom/urdf/yahboom_x3.urdf",
        "usd_cache": REPO_ROOT / "data/usd_cache/yahboom_x3",
        "prim": "/World/Yahboom_X3",
        "drive_joints": ["left_wheel_joint", "right_wheel_joint"],
        "spawn_pos": (0.0, 0.0, 0.0),
    },
    "m3pro": {
        "label": "RosMaster M3Pro (mecanum / holonomic)",
        "urdf": REPO_ROOT / "fleet_safe_vla/robots/yahboom/urdf/yahboom_m3pro.urdf",
        "usd_cache": REPO_ROOT / "data/usd_cache/yahboom_m3pro",
        "prim": "/World/Yahboom_M3Pro",
        "drive_joints": ["fl_wheel_joint", "fr_wheel_joint", "rl_wheel_joint", "rr_wheel_joint"],
        "spawn_pos": (0.0, 0.0, 0.0),
        # M3Pro URDF not yet created — viewer will raise an actionable error.
        # Required assets listed in:
        #   fleet_safe_vla/robots/yahboom/config/robot_contract_m3pro.yaml
    },
}

# ── Argument parsing ──────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Yahboom Isaac Sim GUI viewer")
parser.add_argument(
    "--robot",
    type=str,
    default="x3",
    choices=list(_ROBOTS.keys()),
    help="Which Yahboom model to view (default: x3)",
)
AppLauncher.add_app_launcher_args(parser)  # adds --device, --headless, etc.
args_cli = parser.parse_args()

# Force GUI — this viewer is always interactive
args_cli.headless = False

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

# ── Step 2: ALL Isaac Lab / omni imports AFTER AppLauncher ────────────────────
import isaaclab.sim as sim_utils  # noqa: E402
from isaaclab.actuators import ImplicitActuatorCfg  # noqa: E402
from isaaclab.assets import Articulation, ArticulationCfg  # noqa: E402
from isaaclab.sim import SimulationContext  # noqa: E402
from isaaclab.sim.converters import UrdfConverterCfg  # noqa: E402
from isaaclab.sim.spawners.from_files import UrdfFileCfg  # noqa: E402


# ── Scene construction ────────────────────────────────────────────────────────

def _build_robot_cfg(robot_def: dict) -> ArticulationCfg:
    """Return ArticulationCfg for the chosen Yahboom model."""
    usd_cache = robot_def["usd_cache"]
    usd_cache.mkdir(parents=True, exist_ok=True)

    # Wheel joints: zero-velocity target with damping keeps wheels still
    # under gravity while allowing free response to ground contact forces.
    wheel_drive = UrdfConverterCfg.JointDriveCfg(
        target_type="velocity",
        gains=UrdfConverterCfg.JointDriveCfg.PDGainsCfg(
            stiffness=0.0,
            damping=2.0,
        ),
    )

    joint_pos_defaults = {j: 0.0 for j in robot_def["drive_joints"]}

    return ArticulationCfg(
        prim_path=robot_def["prim"],
        spawn=UrdfFileCfg(
            asset_path=str(robot_def["urdf"]),
            usd_dir=str(usd_cache),
            fix_base=False,
            merge_fixed_joints=True,
            self_collision=False,
            joint_drive=wheel_drive,
        ),
        init_state=ArticulationCfg.InitialStateCfg(
            pos=robot_def["spawn_pos"],
            joint_pos=joint_pos_defaults,
        ),
        actuators={
            "wheels": ImplicitActuatorCfg(
                joint_names_expr=[".*wheel.*"],
                effort_limit_sim=1.0,
                velocity_limit_sim=20.0,
                stiffness=0.0,
                damping=0.1,
            )
        },
    )


def design_scene(robot_def: dict) -> Articulation:
    """Add ground plane, lights, and the selected Yahboom robot to /World."""
    # Ground plane
    gnd = sim_utils.GroundPlaneCfg()
    gnd.func("/World/GroundPlane", gnd)

    # Dome light — bright neutral for visibility
    dome = sim_utils.DomeLightCfg(intensity=2500.0, color=(0.92, 0.92, 1.0))
    dome.func("/World/DomeLight", dome)

    # Directional key light for soft shadows
    key = sim_utils.DistantLightCfg(intensity=1500.0, color=(1.0, 0.95, 0.85))
    key.func("/World/KeyLight", key, translation=(3.0, 3.0, 5.0))

    robot_cfg = _build_robot_cfg(robot_def)
    return Articulation(cfg=robot_cfg)


# ── Pre-flight check ──────────────────────────────────────────────────────────

def _check_urdf(robot_def: dict) -> None:
    """Exit with actionable message if the URDF is missing."""
    urdf = robot_def["urdf"]
    if urdf.exists():
        return

    model = args_cli.robot
    print(f"\n[ERROR] URDF not found for --robot {model}")
    print(f"  Expected: {urdf}\n")

    if model == "m3pro":
        print("  The M3Pro URDF has not been created yet.")
        print("  Required assets and specifications are documented at:")
        print(f"  {REPO_ROOT}/fleet_safe_vla/robots/yahboom/config/robot_contract_m3pro.yaml\n")
        print("  To create the M3Pro URDF:")
        print("  1. Obtain mechanical drawings / CAD from Yahboom (RosMaster M3Pro)")
        print("  2. Build a URDF with 4 mecanum joints: fl/fr/rl/rr_wheel_joint")
        print("  3. Save to: fleet_safe_vla/robots/yahboom/urdf/yahboom_m3pro.urdf")
        print("  4. Re-run this viewer with --robot m3pro\n")
        print("  In the meantime, run the X3 viewer to confirm the Isaac Sim setup:")
        print("    ./scripts/isaaclab/view_yahboom.sh --robot x3\n")
    else:
        print(f"  The {model.upper()} URDF is missing from the expected location.")
        print("  Check fleet_safe_vla/robots/yahboom/urdf/ for available models.\n")

    simulation_app.close()
    sys.exit(1)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    robot_def = _ROBOTS[args_cli.robot]

    print("\n============================================================")
    print(f"  Fleet-Safe  |  Yahboom Isaac Sim Viewer  |  {robot_def['label']}")
    print("============================================================")
    print(f"  URDF   : {robot_def['urdf']}")
    print(f"  Cache  : {robot_def['usd_cache']}")
    print(f"  Device : {args_cli.device}")
    print("============================================================\n")

    _check_urdf(robot_def)

    # 100 Hz physics; render every 2 steps → 50 fps
    sim_cfg = sim_utils.SimulationCfg(
        dt=0.01,
        device=args_cli.device,
        render_interval=2,
    )
    sim = SimulationContext(sim_cfg)

    # Isometric-ish camera: upper-right, looking down at robot
    sim.set_camera_view(eye=[1.0, -0.8, 0.6], target=[0.0, 0.0, 0.1])

    robot = design_scene(robot_def)

    sim.reset()
    print("[INFO] Scene ready. Close the GUI window (or Ctrl+C) to exit.\n")

    sim_dt = sim.get_physics_dt()
    step = 0

    while simulation_app.is_running():
        # No control commands — robot rests on ground, wheels spin freely
        robot.write_data_to_sim()
        sim.step()
        step += 1
        robot.update(sim_dt)

        if step % 200 == 0:
            pos = robot.data.root_pos_w[0].tolist()
            vel = robot.data.root_lin_vel_w[0].tolist()
            print(
                f"[INFO] step={step:6d} | "
                f"pos=[{pos[0]:.3f}, {pos[1]:.3f}, {pos[2]:.3f}] | "
                f"vel=[{vel[0]:.3f}, {vel[1]:.3f}, {vel[2]:.3f}]"
            )


if __name__ == "__main__":
    main()
    simulation_app.close()
