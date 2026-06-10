"""
yahboom_m3pro_rl_cfg.py — PPO training configuration for Yahboom M3Pro

Uses RSL-RL (the RL library shipped with Isaac Lab 0.54.3).
Separate config classes for each training stage so hyperparameters
can be evolved without breaking earlier stages.

Stage configs:
  M3ProPPOCfg         — Stage 1: random cmd_vel tracking
  M3ProPPOCfg_Stage2  — Stage 2: waypoint navigation  (longer horizon)
  M3ProPPOCfg_Stage3  — Stage 3: obstacle avoidance   (more envs, longer)
  M3ProPPOCfg_Stage4  — Stage 4: Fleet-Safe CBF layer (safety critic)
  M3ProPPOCfg_Stage5  — Stage 5: imitation learning   (BC warm-start)

Reference values:
  env:   M3ProEnvCfg  (yahboom_m3pro_env_cfg.py)
  robot: robot_contract_m3pro.yaml
  hw:    RTX 4080 SUPER  |  28 CPU cores  |  ~32 GB RAM

Usage (after M3Pro URDF exists):
  ./scripts/isaaclab/train_yahboom.sh --stage 1
  ./scripts/isaaclab/eval_yahboom.sh  --stage 1 --checkpoint logs/...
"""
from __future__ import annotations

from dataclasses import field
from pathlib import Path

try:
    from isaaclab.utils import configclass
    from isaaclab_rl.rsl_rl import (   # rsl_rl wrapper shipped with Isaac Lab
        RslRlOnPolicyRunnerCfg,
        RslRlPpoActorCriticCfg,
        RslRlPpoAlgorithmCfg,
    )
    _RSL_AVAILABLE = True
except ImportError:
    _RSL_AVAILABLE = False

REPO_ROOT = Path(__file__).resolve().parents[4]
LOG_DIR   = REPO_ROOT / "logs" / "isaaclab" / "yahboom_m3pro"


# ── Shared actor-critic network ───────────────────────────────────────────────
# M3Pro obs vector: 39 dims (Stage 1).  Grows with lidar/safety in later stages.
# Network is deliberately modest — mobile nav doesn't need H1-scale nets.

if _RSL_AVAILABLE:

    @configclass
    class _M3ProActorCriticCfg(RslRlPpoActorCriticCfg):
        """Shared MLP actor-critic for M3Pro stages 1–3."""
        init_noise_std:   float = 0.5
        actor_hidden_dims:  list = field(default_factory=lambda: [256, 128, 64])
        critic_hidden_dims: list = field(default_factory=lambda: [256, 128, 64])
        activation:         str = "elu"

    @configclass
    class _M3ProPPOAlgCfg(RslRlPpoAlgorithmCfg):
        """PPO hyperparameters — conservative for a slow-speed indoor robot."""
        value_loss_coef:   float = 1.0
        use_clipped_value_loss: bool = True
        clip_param:        float = 0.2
        entropy_coef:      float = 0.005   # low entropy → prefer exploitation early
        num_learning_epochs:  int = 5
        num_mini_batches:     int = 4
        learning_rate:     float = 1e-3
        schedule:          str  = "adaptive"   # auto-adjusts LR via KL divergence
        gamma:             float = 0.99
        lam:               float = 0.95
        desired_kl:        float = 0.01
        max_grad_norm:     float = 1.0

    # ── Stage 1: random cmd_vel tracking ─────────────────────────────────────

    @configclass
    class M3ProPPOCfg(RslRlOnPolicyRunnerCfg):
        """
        Stage 1 — Random velocity command tracking on flat ground.

        Goal: policy learns to execute [vx, vy, wz] commands accurately.
        No obstacles.  No goal waypoints.  Pure velocity tracking.

        Convergence target: track_vx + track_vy + track_wz > 3.5 / step
        Expected wall-clock: ~2–3 hours on RTX 4080 SUPER (1024 envs)
        """
        seed:             int  = 42
        device:           str  = "cuda:0"
        num_steps_per_env: int = 24         # rollout horizon per env
        max_iterations:   int  = 2000       # total PPO updates
        save_interval:    int  = 100
        experiment_name:  str  = "m3pro_stage1_vel_tracking"
        empirical_normalization: bool = True
        run_name:         str  = ""         # auto-generated if empty
        resume:           bool = False
        load_run:         str  = ".*"
        load_checkpoint:  str  = "model_.*.pt"
        logger:           str  = "tensorboard"

        policy:    _M3ProActorCriticCfg = _M3ProActorCriticCfg()
        algorithm: _M3ProPPOAlgCfg      = _M3ProPPOAlgCfg()

    # ── Stage 2: waypoint navigation ─────────────────────────────────────────

    @configclass
    class M3ProPPOCfg_Stage2(M3ProPPOCfg):
        """
        Stage 2 — Navigate to waypoints on flat ground.

        Changes from Stage 1:
          - Longer horizon (30 steps) for multi-step planning
          - More training iterations (3000)
          - Reduced entropy to exploit learned velocity skills
          - Load Stage 1 checkpoint (resume=True recommended)

        Adds to obs: goal_vec [3] → total obs = 42 dims
        Adds reward: goal_reached (sparse +10) + heading_alignment (dense)
        """
        num_steps_per_env: int = 30
        max_iterations:    int = 3000
        experiment_name:   str = "m3pro_stage2_waypoint_nav"
        resume:            bool = True   # warm-start from Stage 1

        @configclass
        class _Stage2Alg(_M3ProPPOAlgCfg):
            entropy_coef: float = 0.002   # lower — exploit Stage 1 skills

        algorithm: _Stage2Alg = _Stage2Alg()

    # ── Stage 3: obstacle avoidance ───────────────────────────────────────────

    @configclass
    class M3ProPPOCfg_Stage3(M3ProPPOCfg_Stage2):
        """
        Stage 3 — Navigate to waypoints while avoiding obstacles.

        Changes from Stage 2:
          - Lidar scan obs activated (adds 360 dims → total obs = 402)
          - Obstacle penalty term enabled in reward
          - Termination on collision added
          - Larger network to process lidar (512-256-128)
          - More envs if VRAM allows (2048)

        TODO: Scene needs static obstacles (boxes, cylinders).
        """
        num_steps_per_env: int = 30
        max_iterations:    int = 5000
        experiment_name:   str = "m3pro_stage3_obstacle_avoidance"

        @configclass
        class _Stage3Actor(_M3ProActorCriticCfg):
            # Wider net to process lidar (360 extra dims)
            actor_hidden_dims:  list = field(default_factory=lambda: [512, 256, 128])
            critic_hidden_dims: list = field(default_factory=lambda: [512, 256, 128])

        policy: _Stage3Actor = _Stage3Actor()

    # ── Stage 4: Fleet-Safe CBF layer ────────────────────────────────────────

    @configclass
    class M3ProPPOCfg_Stage4(M3ProPPOCfg_Stage3):
        """
        Stage 4 — Policy learns to respect Fleet-Safe CBF constraints.

        Changes from Stage 3:
          - Safety state obs added: CBF barrier h, min_dist, estop [3]
          - CBF reward term enabled (-5.0 weight for violations)
          - Lower max speed during training (curriculum)
          - Safety critic optional: separate value head for safety

        This stage can also be used for CBF-guided fine-tuning:
        load a Stage 3 policy and fine-tune with safety penalties.
        """
        max_iterations:  int = 3000
        experiment_name: str = "m3pro_stage4_fleet_safe_cbf"
        resume:          bool = True

        @configclass
        class _Stage4Alg(_M3ProPPOAlgCfg):
            # Lower LR for fine-tuning
            learning_rate: float = 3e-4
            entropy_coef:  float = 0.001

        algorithm: _Stage4Alg = _Stage4Alg()

    # ── Stage 5: Imitation / Mimic from real ROS2 demos ──────────────────────

    @configclass
    class M3ProPPOCfg_Stage5(M3ProPPOCfg_Stage4):
        """
        Stage 5 — Behavior cloning warm-start + PPO fine-tune from real demos.

        Real M3Pro ROS2 bags are collected via:
            ./scripts/real_robot/record_episode.sh

        Then converted to Isaac Lab replay format and used as:
          a) BC pre-training (supervised, offline)
          b) On-policy fine-tuning with reward signal

        Changes from Stage 4:
          - Observation space must match real robot obs_adapter_m3pro.py
          - Actions are [vx, vy, wz] (not wheel targets) to match ROS2 /cmd_vel
          - Mimic loss weight added to PPO objective

        NOTE: Stage 5 infrastructure (data loader, BC loss) is NOT YET
        implemented.  This config is a placeholder for the design intent.
        """
        max_iterations:  int = 2000
        experiment_name: str = "m3pro_stage5_mimic"
        resume:          bool = True

else:
    # Stubs when Isaac Lab / rsl_rl is not importable
    class M3ProPPOCfg: pass             # noqa: E701
    class M3ProPPOCfg_Stage2: pass      # noqa: E701
    class M3ProPPOCfg_Stage3: pass      # noqa: E701
    class M3ProPPOCfg_Stage4: pass      # noqa: E701
    class M3ProPPOCfg_Stage5: pass      # noqa: E701


# ── Task registry (used by train_yahboom.sh / Isaac Lab task resolver) ────────

TASK_REGISTRY: dict[str, tuple] = {
    # task_name → (EnvCfg class, PPOCfg class)
    # Populated once M3Pro assets exist and env classes are implemented.
    #
    # "FleetSafe-M3Pro-VelTracking-v0":  (M3ProEnvCfg,        M3ProPPOCfg),
    # "FleetSafe-M3Pro-WaypointNav-v0":  (M3ProEnvCfg_Stage2, M3ProPPOCfg_Stage2),
    # "FleetSafe-M3Pro-Obstacles-v0":    (M3ProEnvCfg_Stage3, M3ProPPOCfg_Stage3),
    # "FleetSafe-M3Pro-FleetSafe-v0":    (M3ProEnvCfg_Stage4, M3ProPPOCfg_Stage4),
    # "FleetSafe-M3Pro-Mimic-v0":        (M3ProEnvCfg_Stage5, M3ProPPOCfg_Stage5),
}

STAGE_TO_TASK: dict[int, str] = {
    # 1: "FleetSafe-M3Pro-VelTracking-v0",
    # 2: "FleetSafe-M3Pro-WaypointNav-v0",
    # 3: "FleetSafe-M3Pro-Obstacles-v0",
    # 4: "FleetSafe-M3Pro-FleetSafe-v0",
    # 5: "FleetSafe-M3Pro-Mimic-v0",
}
