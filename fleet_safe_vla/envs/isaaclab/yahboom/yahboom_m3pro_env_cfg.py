"""
yahboom_m3pro_env_cfg.py — Isaac Lab Manager-Based RL environment config
                            for the Yahboom RosMaster M3Pro (holonomic / mecanum)

This file defines *configuration dataclasses only*.  No simulation objects are
created at import time — instantiation happens inside the Isaac Sim process
(after AppLauncher boots).

PREREQUISITE — this config will raise AssetNotFoundError at instantiation if
the M3Pro URDF is missing.  Run Stage 0 validation first:

    ./scripts/isaaclab/train_yahboom.sh --stage 0

Isaac Lab version: 0.54.3
Robot contract:    fleet_safe_vla/robots/yahboom/config/robot_contract_m3pro.yaml

Observation space (flat RL vector, 39 dims — see ObsCfg below):
  base_lin_vel       [3]   body-frame linear velocity (vx, vy, vz)
  base_ang_vel       [3]   body-frame angular velocity (wx, wy, wz)
  projected_gravity  [3]   gravity projection (tilt detection)
  yaw                [1]   robot yaw in radians
  velocity_commands  [3]   commanded (vx_cmd, vy_cmd, wz_cmd) from CommandManager
  joint_pos          [4]   fl/fr/rl/rr wheel positions (rad, unwrapped)
  joint_vel          [4]   fl/fr/rl/rr wheel velocities (rad/s)
  goal_vec           [3]   goal in robot frame: (dx, dy, dist)
  cmd_vel_history    [15]  last 5 actions × [vx, vy, wz]
  ── lidar_scan      [0]   placeholder — activated in Stage 3 (shape=[360])
  ── safety_state    [3]   CBF barrier, min_obstacle_dist, estop — Stage 4
  TOTAL              39    (flat; lidar+safety added in later stages)

Action space (3 dims, normalised [-1, 1]):
  [vx_norm, vy_norm, wz_norm]
  Scaled to: vx ∈ [-0.5, 0.5] m/s, vy ∈ [-0.5, 0.5] m/s, wz ∈ [-1.0, 1.0] rad/s
  Then converted to 4-wheel velocity targets via inverse mecanum kinematics.
"""
from __future__ import annotations

import math
from dataclasses import MISSING
from pathlib import Path

# ── Guard against import outside the isaac conda env ─────────────────────────
# These imports fail outside the env — callers should handle ImportError.
try:
    from isaaclab.utils import configclass
    import isaaclab.sim as sim_utils
    from isaaclab.assets import ArticulationCfg
    from isaaclab.actuators import ImplicitActuatorCfg
    from isaaclab.envs import ManagerBasedRLEnvCfg
    from isaaclab.managers import (
        ActionTermCfg,
        CommandTermCfg,
        CurriculumTermCfg,
        EventTermCfg,
        ObservationGroupCfg,
        ObservationTermCfg,
        RewardTermCfg,
        TerminationTermCfg,
    )
    from isaaclab.scene import InteractiveSceneCfg
    from isaaclab.sim import SimulationCfg
    from isaaclab.sim.spawners.from_files import UrdfFileCfg
    from isaaclab.sim.converters import UrdfConverterCfg
    import isaaclab.envs.mdp as mdp
    _ISAACLAB_AVAILABLE = True
except ImportError:
    _ISAACLAB_AVAILABLE = False


REPO_ROOT = Path(__file__).resolve().parents[4]

# ── Asset paths ───────────────────────────────────────────────────────────────
M3PRO_URDF      = REPO_ROOT / "fleet_safe_vla/robots/yahboom/m3pro/urdf/yahboom_m3pro.urdf"
M3PRO_USD_CACHE = REPO_ROOT / "fleet_safe_vla/robots/yahboom/m3pro/usd"
CONTRACT_YAML   = REPO_ROOT / "fleet_safe_vla/robots/yahboom/config/robot_contract_m3pro.yaml"


class AssetNotFoundError(RuntimeError):
    """Raised when required simulation assets are missing."""


def _assert_assets_exist():
    """Called at instantiation time — fails fast before Isaac Sim wastes time."""
    if not M3PRO_URDF.exists():
        raise AssetNotFoundError(
            f"\n\n[M3Pro Env] M3Pro URDF not found: {M3PRO_URDF}\n\n"
            "  This environment cannot run until the M3Pro URDF is created.\n"
            "  Required assets are documented in:\n"
            f"    {CONTRACT_YAML}\n\n"
            "  Asset checklist:\n"
            "    [ ] fleet_safe_vla/robots/yahboom/m3pro/urdf/yahboom_m3pro.urdf\n"
            "    [ ] fleet_safe_vla/robots/yahboom/m3pro/mjcf/yahboom_m3pro.xml\n"
            "    [✓] fleet_safe_vla/robots/yahboom/controllers/obs_adapter_m3pro.py\n\n"
            "  Run Stage 0 validation after creating assets:\n"
            "    ./scripts/isaaclab/train_yahboom.sh --stage 0\n"
        )


# ── Geometry constants (from robot_contract_m3pro.yaml) ───────────────────────
WHEEL_RADIUS_M  = 0.048    # m   — verify against physical hardware
WHEELBASE_M     = 0.155    # m   — front-rear axle distance
TRACK_WIDTH_M   = 0.170    # m   — left-right wheel centre distance
HALF_LX         = WHEELBASE_M  / 2.0
HALF_LY         = TRACK_WIDTH_M / 2.0

# Velocity limits
MAX_VX_MS   = 0.5     # m/s
MAX_VY_MS   = 0.5     # m/s
MAX_WZ_RDS  = 1.0     # rad/s
MAX_WHEEL_RDS = 20.0  # rad/s — safety cap on individual wheel targets

# Episode + control
CONTROL_HZ   = 10.0
SIM_HZ       = 100.0
DECIMATION   = int(SIM_HZ / CONTROL_HZ)   # = 10 sim steps per policy step
SIM_DT       = 1.0 / SIM_HZ               # = 0.01 s
EPISODE_LEN_S = 20.0
EPISODE_STEPS = int(EPISODE_LEN_S * CONTROL_HZ)   # = 200 steps


# ── Robot articulation config ─────────────────────────────────────────────────

def _build_m3pro_cfg() -> "ArticulationCfg":
    """Construct ArticulationCfg — only call after AppLauncher has booted."""
    _assert_assets_exist()
    M3PRO_USD_CACHE.mkdir(parents=True, exist_ok=True)

    wheel_drive = UrdfConverterCfg.JointDriveCfg(
        target_type="velocity",
        gains=UrdfConverterCfg.JointDriveCfg.PDGainsCfg(stiffness=0.0, damping=2.0),
    )

    return ArticulationCfg(
        prim_path="{ENV_REGEX_NS}/Robot",
        spawn=UrdfFileCfg(
            asset_path=str(M3PRO_URDF),
            usd_dir=str(M3PRO_USD_CACHE),
            fix_base=False,
            merge_fixed_joints=True,
            self_collision=False,
            joint_drive=wheel_drive,
        ),
        init_state=ArticulationCfg.InitialStateCfg(
            pos=(0.0, 0.0, 0.05),   # slight ground clearance
            joint_pos={j: 0.0 for j in ("fl_wheel_joint", "fr_wheel_joint",
                                         "rl_wheel_joint", "rr_wheel_joint")},
        ),
        actuators={
            "wheels": ImplicitActuatorCfg(
                joint_names_expr=[".*wheel.*"],
                effort_limit_sim=2.0,
                velocity_limit_sim=MAX_WHEEL_RDS,
                stiffness=0.0,
                damping=0.5,
            )
        },
    )


# ── Observation manager ───────────────────────────────────────────────────────

if _ISAACLAB_AVAILABLE:

    @configclass
    class ObsCfg:
        """Observation groups for Stage 1–2.  Lidar / safety added in later stages."""

        @configclass
        class PolicyObs(ObservationGroupCfg):
            """Flat RL vector seen by the policy — 39 dims."""

            # [3] body-frame linear velocity
            base_lin_vel = ObservationTermCfg(
                func=mdp.base_lin_vel,
                noise=mdp.GaussianNoiseCfg(std=0.05),
            )
            # [3] body-frame angular velocity
            base_ang_vel = ObservationTermCfg(
                func=mdp.base_ang_vel,
                noise=mdp.GaussianNoiseCfg(std=0.02),
            )
            # [3] gravity vector in body frame (tilt detection)
            projected_gravity = ObservationTermCfg(
                func=mdp.projected_gravity,
                noise=mdp.GaussianNoiseCfg(std=0.01),
            )
            # [3] velocity command from CommandManager
            velocity_commands = ObservationTermCfg(
                func=mdp.generated_commands,
                params={"command_name": "vel_cmd"},
            )
            # [4] wheel joint positions (unwrapped radians)
            joint_pos = ObservationTermCfg(
                func=mdp.joint_pos_rel,
                noise=mdp.GaussianNoiseCfg(std=0.01),
            )
            # [4] wheel joint velocities
            joint_vel = ObservationTermCfg(
                func=mdp.joint_vel_rel,
                noise=mdp.GaussianNoiseCfg(std=0.1),
            )
            # [3] last applied action (acts as 1-step cmd history)
            last_action = ObservationTermCfg(func=mdp.last_action)

            concatenate_terms = True
            enable_corruption  = True  # domain randomisation noise applied above

        policy: PolicyObs = PolicyObs()

    # ── Action manager ────────────────────────────────────────────────────────

    @configclass
    class ActionCfg:
        """
        Normalised 3-DoF velocity command → inverse mecanum → 4-wheel targets.

        The actual kinematics conversion is performed in
        fleet_safe_vla/envs/isaaclab/yahboom/m3pro_env.py (not yet created).
        This cfg records intent; the action term implementation is MISSING.
        """
        # Placeholder: will be replaced with M3ProVelocityActionCfg once
        # fleet_safe_vla/envs/isaaclab/yahboom/m3pro_env.py exists.
        #
        # Intended interface:
        #   joint_velocities = M3ProVelocityActionCfg(
        #       asset_name="robot",
        #       joint_names=["fl_wheel_joint","fr_wheel_joint","rl_wheel_joint","rr_wheel_joint"],
        #       scale=[MAX_VX_MS, MAX_VY_MS, MAX_WZ_RDS],  # normalised → physical
        #   )
        pass

    # ── Command manager ───────────────────────────────────────────────────────

    @configclass
    class CommandsCfg:
        """Random velocity commands sampled each episode (Stage 1–2)."""

        vel_cmd: CommandTermCfg = CommandTermCfg(
            func=mdp.UniformVelocityCommand,
            resampling_time_range=(4.0, 8.0),   # resample every 4–8 s
            params={
                "asset_name":   "robot",
                "ranges": mdp.UniformVelocityCommand.Ranges(
                    lin_vel_x=(-MAX_VX_MS, MAX_VX_MS),
                    lin_vel_y=(-MAX_VY_MS, MAX_VY_MS),   # holonomic strafe
                    ang_vel_z=(-MAX_WZ_RDS, MAX_WZ_RDS),
                    heading=(-math.pi, math.pi),
                ),
            },
            debug_vis=True,
        )

    # ── Reward manager ────────────────────────────────────────────────────────

    @configclass
    class RewardCfg:
        """
        Stage 1 baseline rewards.  Weights tuned for 10 Hz control, 20-step
        episode.  All terms are additive; scale factors are in reward_scale units
        per step.  Negative weights → penalties.

        Reference:   robot_contract_m3pro.yaml  §safety, §control
        Safety note: CBF reward term is a PLACEHOLDER — wired in Stage 4.
        """

        # ── Tracking rewards (positive) ───────────────────────────────────
        # Exponential tracking: reward = exp(-error² / sigma²)

        track_vx = RewardTermCfg(
            func=mdp.track_lin_vel_xy_exp,
            weight=2.0,
            params={"command_name": "vel_cmd", "std": 0.25},
        )
        track_vy = RewardTermCfg(
            func=mdp.track_lin_vel_xy_exp,
            weight=1.5,    # slightly lower — strafe is secondary
            params={"command_name": "vel_cmd", "std": 0.25},
        )
        track_wz = RewardTermCfg(
            func=mdp.track_ang_vel_z_exp,
            weight=1.0,
            params={"command_name": "vel_cmd", "std": 0.25},
        )

        # ── Stability penalties (negative) ────────────────────────────────

        lin_vel_z_l2 = RewardTermCfg(
            func=mdp.lin_vel_z_l2,
            weight=-0.5,   # penalise bouncing
        )
        ang_vel_xy_l2 = RewardTermCfg(
            func=mdp.ang_vel_xy_l2,
            weight=-0.05,  # penalise pitch/roll oscillation
        )
        flat_orientation = RewardTermCfg(
            func=mdp.flat_orientation_l2,
            weight=-1.0,
        )

        # ── Smoothness penalty (negative) ─────────────────────────────────
        action_rate = RewardTermCfg(
            func=mdp.action_rate_l2,
            weight=-0.01,
        )

        # ── Safety margin penalty (Stage 4 placeholder) ───────────────────
        # TODO Stage 4: replace weight=0.0 with weight=-5.0 and wire CBF
        #   safety_margin = RewardTermCfg(
        #       func=fleetsafe_mdp.cbf_safety_margin,
        #       weight=-5.0,
        #       params={"min_dist_m": 0.30, "estop_dist_m": 0.15},
        #   )
        # ── Obstacle penalty (Stage 3 placeholder) ────────────────────────
        # TODO Stage 3: enable when lidar obs is active
        #   obstacle_proximity = RewardTermCfg(
        #       func=fleetsafe_mdp.lidar_min_dist_penalty,
        #       weight=-2.0,
        #       params={"min_safe_dist_m": 0.30},
        #   )

    # ── Termination manager ───────────────────────────────────────────────────

    @configclass
    class TerminationCfg:
        """Episode termination conditions."""

        time_out = TerminationTermCfg(
            func=mdp.time_out,
            time_out=True,
        )
        # Terminate if robot tips over (|tilt| > 45°)
        base_orientation = TerminationTermCfg(
            func=mdp.bad_orientation,
            params={"limit_angle": math.radians(45.0)},
        )

    # ── Event / randomisation manager ────────────────────────────────────────

    @configclass
    class EventCfg:
        """Domain randomisation events applied at reset and interval."""

        # Reset robot to a random pose each episode
        reset_robot_state = EventTermCfg(
            func=mdp.reset_root_state_uniform,
            mode="reset",
            params={
                "asset_name": "robot",
                "pose_range": {
                    "x": (-1.5, 1.5), "y": (-1.5, 1.5),
                    "z": (0.04, 0.06),
                    "yaw": (-math.pi, math.pi),
                },
                "velocity_range": {
                    "x": (-0.1, 0.1), "y": (-0.1, 0.1),
                    "z": (0.0, 0.0),
                },
            },
        )
        # Reset joint velocities to near-zero
        reset_joint_state = EventTermCfg(
            func=mdp.reset_joints_by_offset,
            mode="reset",
            params={
                "asset_name":    "robot",
                "position_range": (-0.01, 0.01),
                "velocity_range": (-0.5, 0.5),
            },
        )
        # Push perturbation — applied every 5–10 s to test robustness
        push_robot = EventTermCfg(
            func=mdp.push_by_setting_velocity,
            mode="interval",
            interval_range_s=(5.0, 10.0),
            params={
                "asset_name":    "robot",
                "velocity_range": {
                    "x": (-0.3, 0.3), "y": (-0.3, 0.3),
                    "z": (0.0, 0.0),
                },
            },
        )

    # ── Scene config ──────────────────────────────────────────────────────────

    @configclass
    class M3ProSceneCfg(InteractiveSceneCfg):
        """Minimal flat-ground scene for Stages 1–2 (no obstacles yet)."""

        ground = sim_utils.GroundPlaneCfg()
        dome_light = sim_utils.DomeLightCfg(intensity=2000.0, color=(0.9, 0.9, 1.0))

        # Robot articulation — populated by _build_m3pro_cfg() at instantiation
        # (deferred to avoid calling _assert_assets_exist at import time)
        robot: ArticulationCfg = MISSING

    # ── Top-level environment config ──────────────────────────────────────────

    @configclass
    class M3ProEnvCfg(ManagerBasedRLEnvCfg):
        """
        Isaac Lab ManagerBasedRL environment config for Yahboom M3Pro.

        Status: SCAFFOLD — requires M3Pro URDF to instantiate.
        Training stage: 1 (random cmd_vel tracking, flat ground).
        To use a later stage, inherit and override the relevant managers.

        Instantiation will call _assert_assets_exist() and raise
        AssetNotFoundError if fleet_safe_vla/robots/yahboom/m3pro/urdf/yahboom_m3pro.urdf
        is missing.
        """

        # Simulator
        sim: SimulationCfg = SimulationCfg(dt=SIM_DT, device="cuda:0")

        # Scene
        scene: M3ProSceneCfg = M3ProSceneCfg(num_envs=1024, env_spacing=4.0)

        # Managers
        observations: ObsCfg       = ObsCfg()
        actions:      ActionCfg    = ActionCfg()
        commands:     CommandsCfg  = CommandsCfg()
        rewards:      RewardCfg    = RewardCfg()
        terminations: TerminationCfg = TerminationCfg()
        events:       EventCfg     = EventCfg()

        # Episode
        episode_length_s: float = EPISODE_LEN_S
        decimation:       int   = DECIMATION

        def __post_init__(self):
            super().__post_init__()
            # Inject M3Pro articulation (deferred so import is safe)
            self.scene.robot = _build_m3pro_cfg()

else:
    # Stub classes for documentation purposes when Isaac Lab is not available
    class ObsCfg: pass        # noqa: E701
    class ActionCfg: pass     # noqa: E701
    class CommandsCfg: pass   # noqa: E701
    class RewardCfg: pass     # noqa: E701
    class TerminationCfg: pass # noqa: E701
    class EventCfg: pass      # noqa: E701
    class M3ProSceneCfg: pass # noqa: E701
    class M3ProEnvCfg: pass   # noqa: E701


# ── Stage variants (inherit and override) ────────────────────────────────────
# These are placeholders — fill in when advancing to each stage.

# Stage 2: waypoint navigation — add goal_vec obs, sparse goal reward
# class M3ProEnvCfg_Stage2(M3ProEnvCfg): ...

# Stage 3: obstacle avoidance — add lidar obs + obstacle penalty
# class M3ProEnvCfg_Stage3(M3ProEnvCfg_Stage2): ...

# Stage 4: Fleet-Safe CBF layer — add safety_state obs + CBF reward
# class M3ProEnvCfg_Stage4(M3ProEnvCfg_Stage3): ...

# Stage 5: imitation / mimic from real ROS2 demos
# class M3ProEnvCfg_Stage5(M3ProEnvCfg_Stage4): ...
