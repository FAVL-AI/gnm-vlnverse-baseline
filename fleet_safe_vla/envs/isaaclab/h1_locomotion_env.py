"""
FleetSafe-H1-RoughLocomotion-v0 — Isaac Lab Task Registration.

Extends robot-lab's H1LocomotionEnvCfg with Fleet Safety features:
  - Integration with CBF safety layer
  - Fleet-wide risk monitoring hooks
  - Extended PPO hyperparameters for fleet training
  - Multi-robot scenario support

Registered tasks:
  FleetSafe-H1-RoughLocomotion-v0   — fleet-mode rough terrain (training)
  FleetSafe-H1-FlatLocomotion-v0    — fleet-mode flat terrain (debug)
  FleetSafe-H1-Play-v0              — visualization (no randomization)

IMPORTANT: All isaaclab/omni/pxr imports are deferred to class bodies /
function bodies. Only standard library + gymnasium are imported at module
top-level, so this file can be imported without Isaac Sim installed.
"""
from __future__ import annotations

# ── Module-level: ONLY stdlib + gym ─────────────────────────────────────────
import gymnasium as gym

# ── Task registration ─────────────────────────────────────────────────────────

def _make_fleet_safe_env_cfg():
    """
    Deferred factory — imports Isaac Lab only when called.
    This is invoked by gymnasium.make() which happens AFTER AppLauncher.
    """
    # All Isaac Lab imports live here — never at module top-level
    from isaaclab.utils import configclass
    from isaaclab.managers import EventTermCfg as EventTerm, SceneEntityCfg
    import isaaclab.envs.mdp as mdp

    # robot-lab provides the base env config
    from robot_lab.envs.locomotion.h1_locomotion_env import (
        H1LocomotionEnvCfg,
        H1LocomotionPPORunnerCfg,
    )
    from robot_lab.envs.locomotion.rewards import H1RewardsCfg
    from robot_lab.envs.locomotion.observations import H1ObservationsCfg
    from robot_lab.envs.locomotion.terminations import H1TerminationsCfg
    from robot_lab.envs.locomotion.curriculum import H1CurriculumCfg

    # Import rsl_rl config classes
    from isaaclab_rl.rsl_rl import (
        RslRlOnPolicyRunnerCfg,
        RslRlPpoActorCriticCfg,
        RslRlPpoAlgorithmCfg,
    )

    # ── FleetSafe PPO runner config ────────────────────────────────────────

    @configclass
    class FleetSafeH1RunnerCfg(H1LocomotionPPORunnerCfg):
        """
        Fleet-Safe PPO runner config.

        Exact hyperparameters (non-negotiable per task spec):
          num_envs: 4096, horizon_length: 24, minibatches: 4, epochs: 5
          gamma: 0.99, lam: 0.95, clip_param: 0.2, entropy_coef: 0.01, lr: 3e-4
          hidden_dims: [512, 256, 128], activation: elu
        """
        num_steps_per_env: int = 24         # horizon_length
        max_iterations: int = 10000
        save_interval: int = 200
        experiment_name: str = "fleetsafe_h1_rough"

        policy = RslRlPpoActorCriticCfg(
            init_noise_std=1.0,
            actor_hidden_dims=[512, 256, 128],
            critic_hidden_dims=[512, 256, 128],
            activation="elu",
        )
        algorithm = RslRlPpoAlgorithmCfg(
            value_loss_coef=1.0,
            use_clipped_value_loss=True,
            clip_param=0.2,
            entropy_coef=0.01,
            num_learning_epochs=5,       # epochs
            num_mini_batches=4,          # minibatches
            learning_rate=3.0e-4,        # lr
            schedule="adaptive",
            gamma=0.99,
            lam=0.95,
            desired_kl=0.01,
            max_grad_norm=1.0,
        )

    # ── Fleet-Safe environment config ──────────────────────────────────────

    @configclass
    class FleetSafeH1EnvCfg(H1LocomotionEnvCfg):
        """
        FleetSafe-H1-RoughLocomotion environment.

        Extends robot-lab's H1LocomotionEnvCfg with:
          - Fleet-wide safety margin rewards
          - Extended push disturbances (fleet stress test)
          - Conservative recovery terminations
          - num_envs default: 4096
        """
        rewards: H1RewardsCfg = H1RewardsCfg()
        observations: H1ObservationsCfg = H1ObservationsCfg()
        terminations: H1TerminationsCfg = H1TerminationsCfg()
        curriculum: H1CurriculumCfg = H1CurriculumCfg()

        def __post_init__(self) -> None:
            super().__post_init__()

            # Fleet-safe training uses 4096 envs (as per task spec)
            self.scene.num_envs = 4096
            self.episode_length_s = 20.0

            # Slightly more aggressive push disturbances for fleet hardening
            self.events.push_robot = EventTerm(
                func=mdp.push_by_setting_velocity,
                mode="interval",
                interval_range_s=(8.0, 12.0),
                params={
                    "velocity_range": {
                        "x": (-0.6, 0.6),
                        "y": (-0.6, 0.6),
                    },
                },
            )

            # Fleet-specific: randomize payload (30 kg max)
            self.events.payload_mass = EventTerm(
                func=mdp.randomize_rigid_body_mass,
                mode="reset",
                params={
                    "asset_cfg": SceneEntityCfg("robot", body_names="torso_link"),
                    "mass_distribution_params": (0.0, 5.0),  # up to 5 kg extra payload
                    "operation": "add",
                },
            )

    @configclass
    class FleetSafeH1FlatEnvCfg(FleetSafeH1EnvCfg):
        """Flat terrain variant for stage-1 training."""
        def __post_init__(self) -> None:
            super().__post_init__()
            self.scene.terrain.terrain_type = "plane"
            self.scene.terrain.terrain_generator = None
            self.scene.height_scanner = None
            self.curriculum.terrain_levels = None

    @configclass
    class FleetSafeH1PlayEnvCfg(FleetSafeH1EnvCfg):
        """Visualization config — small scene, no randomization."""
        def __post_init__(self) -> None:
            super().__post_init__()
            self.scene.num_envs = 16
            self.scene.env_spacing = 3.5
            self.episode_length_s = 60.0
            self.observations.policy.enable_corruption = False
            self.events.push_robot = None
            self.events.payload_mass = None

    return FleetSafeH1EnvCfg, FleetSafeH1FlatEnvCfg, FleetSafeH1PlayEnvCfg, FleetSafeH1RunnerCfg


# ── Gymnasium task registration ───────────────────────────────────────────────
# These use lazy entry-points so Isaac Lab is not imported at registration time.

gym.register(
    id="FleetSafe-H1-RoughLocomotion-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    kwargs={
        "env_cfg_entry_point": (
            "fleet_safe_vla.envs.isaaclab.h1_locomotion_env:"
            "FleetSafeH1EnvCfg"
        ),
        "rsl_rl_cfg_entry_point": (
            "fleet_safe_vla.envs.isaaclab.h1_locomotion_env:"
            "FleetSafeH1RunnerCfg"
        ),
    },
    disable_env_checker=True,
)

gym.register(
    id="FleetSafe-H1-FlatLocomotion-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    kwargs={
        "env_cfg_entry_point": (
            "fleet_safe_vla.envs.isaaclab.h1_locomotion_env:"
            "FleetSafeH1FlatEnvCfg"
        ),
        "rsl_rl_cfg_entry_point": (
            "fleet_safe_vla.envs.isaaclab.h1_locomotion_env:"
            "FleetSafeH1RunnerCfg"
        ),
    },
    disable_env_checker=True,
)

gym.register(
    id="FleetSafe-H1-Play-v0",
    entry_point="isaaclab.envs:ManagerBasedRLEnv",
    kwargs={
        "env_cfg_entry_point": (
            "fleet_safe_vla.envs.isaaclab.h1_locomotion_env:"
            "FleetSafeH1PlayEnvCfg"
        ),
        "rsl_rl_cfg_entry_point": (
            "fleet_safe_vla.envs.isaaclab.h1_locomotion_env:"
            "FleetSafeH1RunnerCfg"
        ),
    },
    disable_env_checker=True,
)


# ── Lazy config class exports ─────────────────────────────────────────────────
# These names are used by the gymnasium entry_point strings above.
# They are only resolved when gymnasium.make() is called (after AppLauncher).

class _LazyConfigProxy:
    """
    Proxy that builds the real configclass on first attribute access.
    Allows the entry_point strings to resolve before Isaac Lab is imported.
    """
    _configs = None

    @classmethod
    def _ensure(cls):
        if cls._configs is None:
            cls._configs = _make_fleet_safe_env_cfg()

    def __class_getitem__(cls, name):
        cls._ensure()
        return cls._configs


# Expose real names at module level for string-based entry points.
# These will fail gracefully if Isaac Lab is not installed.
class FleetSafeH1EnvCfg:  # type: ignore[no-redef]
    """Entry-point placeholder — resolved after AppLauncher starts Isaac Sim."""
    def __new__(cls, *args, **kwargs):
        _LazyConfigProxy._ensure()
        RealCls = _LazyConfigProxy._configs[0]
        return RealCls(*args, **kwargs)

class FleetSafeH1FlatEnvCfg:  # type: ignore[no-redef]
    def __new__(cls, *args, **kwargs):
        _LazyConfigProxy._ensure()
        RealCls = _LazyConfigProxy._configs[1]
        return RealCls(*args, **kwargs)

class FleetSafeH1PlayEnvCfg:  # type: ignore[no-redef]
    def __new__(cls, *args, **kwargs):
        _LazyConfigProxy._ensure()
        RealCls = _LazyConfigProxy._configs[2]
        return RealCls(*args, **kwargs)

class FleetSafeH1RunnerCfg:  # type: ignore[no-redef]
    def __new__(cls, *args, **kwargs):
        _LazyConfigProxy._ensure()
        RealCls = _LazyConfigProxy._configs[3]
        return RealCls(*args, **kwargs)
