"""
H1 Humanoid MuJoCo Locomotion Environment — Fleet-Safe-VLA-OS.

Uses the `mujoco` Python bindings directly (NOT dm_control) for maximum
compatibility and minimal overhead. Works without GPU.

The H1 MJCF model is inlined as a string so the environment is self-contained
and importable without any asset files on disk.

Observation space (45 dims):
  [0:3]   base angular velocity (rad/s)
  [3:6]   projected gravity vector (normalized)
  [6:9]   velocity command (vx, vy, yaw_rate)
  [9:27]  joint positions relative to default (18 DOF, arms excluded from control)
  [27:45] joint velocities (18 DOF)

Action space (18 dims):
  Target joint positions (PD control, 10 leg + 8 arm joints)

Smoke test:
    env = H1MuJoCoEnv()
    obs = env.reset()
    action = env.action_space.sample()
    obs, rew, done, info = env.step(action)
    env.close()
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np

# Gymnasium (preferred) or gym (legacy)
try:
    import gymnasium as gym
    from gymnasium import spaces
    GYM_VERSION = "gymnasium"
except ImportError:
    import gym
    from gym import spaces
    GYM_VERSION = "gym"

# ── Inline MJCF (compact, physics-correct subset of full h1.xml) ─────────────
# We use the asset file if present, otherwise fall back to an inline model.

_ASSET_PATH = Path(__file__).parent.parent.parent / "assets" / "robots" / "mjcf" / "h1.xml"

_INLINE_MJCF = """<?xml version="1.0" encoding="utf-8"?>
<mujoco model="h1_inline">
  <compiler angle="radian" autolimits="true"/>
  <option timestep="0.005" gravity="0 0 -9.81" iterations="50" solver="Newton"/>
  <default>
    <joint limited="true" damping="5.0" frictionloss="0.5" armature="0.01"/>
    <geom friction="0.8 0.02 0.001" condim="4" contype="1" conaffinity="1"/>
    <motor ctrllimited="true" ctrlrange="-300 300"/>
  </default>
  <asset>
    <texture type="skybox" builtin="gradient" rgb1=".3 .5 .7" rgb2="0 0 0" width="32" height="512"/>
    <texture name="ground" type="2d" builtin="checker" width="512" height="512"
             rgb1=".2 .3 .4" rgb2=".1 .2 .3"/>
    <material name="ground" texture="ground" texrepeat="5 5"/>
  </asset>
  <worldbody>
    <light name="sun" pos="0 0 5" dir="0 0 -1" directional="true"/>
    <geom name="floor" type="plane" size="20 20 0.1" material="ground" condim="6"/>
    <body name="pelvis" pos="0 0 1.05">
      <freejoint name="root"/>
      <inertial pos="0 0 0" mass="10.0" diaginertia="0.1 0.1 0.07"/>
      <geom name="pelvis" type="box" size="0.125 0.09 0.075" rgba=".2 .2 .2 1"/>
      <site name="imu_site" pos="0 0 0" size="0.01"/>
      <body name="torso_link" pos="0 0 0.15">
        <inertial pos="0 0 0.15" mass="15.0" diaginertia="0.2 0.18 0.08"/>
        <geom type="box" size="0.11 0.08 0.175" pos="0 0 0.15" rgba=".9 .9 .9 1"/>
        <!-- Left arm -->
        <body name="left_upper_arm" pos="0 0.2 0.28">
          <inertial pos="0 0 -0.135" mass="2.0" diaginertia="0.01 0.01 0.001"/>
          <geom type="cylinder" size="0.03 0.135" pos="0 0 -0.135" rgba=".2 .2 .2 1"/>
          <joint name="left_shoulder_pitch" axis="0 1 0" range="-3.14 3.14" damping="1.0" ctrlrange="-40 40"/>
          <body name="left_upper_arm_roll" pos="0 0 -0.27">
            <inertial pos="0 0 0" mass="0.5" diaginertia="0.001 0.001 0.001"/>
            <geom type="cylinder" size="0.025 0.02" rgba="0 .4 .8 1"/>
            <joint name="left_shoulder_roll" axis="1 0 0" range="-1.57 1.57" damping="1.0" ctrlrange="-40 40"/>
            <body name="left_lower_arm" pos="0 0 0">
              <inertial pos="0 0 -0.135" mass="1.5" diaginertia="0.007 0.007 0.001"/>
              <geom type="cylinder" size="0.025 0.135" pos="0 0 -0.135" rgba=".2 .2 .2 1"/>
              <joint name="left_elbow" axis="0 1 0" range="-1.57 1.57" damping="1.0" ctrlrange="-40 40"/>
              <body name="left_hand" pos="0 0 -0.27">
                <inertial pos="0 0 0" mass="0.5" diaginertia="0.001 0.001 0.001"/>
                <geom type="box" size="0.03 0.04 0.015" rgba=".2 .2 .2 1"/>
                <joint name="left_wrist" axis="0 0 1" range="-1.57 1.57" damping="0.5" ctrlrange="-10 10"/>
              </body>
            </body>
          </body>
        </body>
        <!-- Right arm -->
        <body name="right_upper_arm" pos="0 -0.2 0.28">
          <inertial pos="0 0 -0.135" mass="2.0" diaginertia="0.01 0.01 0.001"/>
          <geom type="cylinder" size="0.03 0.135" pos="0 0 -0.135" rgba=".2 .2 .2 1"/>
          <joint name="right_shoulder_pitch" axis="0 1 0" range="-3.14 3.14" damping="1.0" ctrlrange="-40 40"/>
          <body name="right_upper_arm_roll" pos="0 0 -0.27">
            <inertial pos="0 0 0" mass="0.5" diaginertia="0.001 0.001 0.001"/>
            <geom type="cylinder" size="0.025 0.02" rgba="0 .4 .8 1"/>
            <joint name="right_shoulder_roll" axis="1 0 0" range="-1.57 1.57" damping="1.0" ctrlrange="-40 40"/>
            <body name="right_lower_arm" pos="0 0 0">
              <inertial pos="0 0 -0.135" mass="1.5" diaginertia="0.007 0.007 0.001"/>
              <geom type="cylinder" size="0.025 0.135" pos="0 0 -0.135" rgba=".2 .2 .2 1"/>
              <joint name="right_elbow" axis="0 1 0" range="-1.57 1.57" damping="1.0" ctrlrange="-40 40"/>
              <body name="right_hand" pos="0 0 -0.27">
                <inertial pos="0 0 0" mass="0.5" diaginertia="0.001 0.001 0.001"/>
                <geom type="box" size="0.03 0.04 0.015" rgba=".2 .2 .2 1"/>
                <joint name="right_wrist" axis="0 0 1" range="-1.57 1.57" damping="0.5" ctrlrange="-10 10"/>
              </body>
            </body>
          </body>
        </body>
      </body>
      <!-- Left leg -->
      <body name="left_hip_yaw_link" pos="0 0.09 -0.05">
        <inertial pos="0 0 0" mass="1.5" diaginertia="0.003 0.003 0.002"/>
        <geom type="cylinder" size="0.04 0.03" rgba="0 .4 .8 1"/>
        <joint name="left_hip_yaw" axis="0 0 1" range="-0.785 0.785"/>
        <body name="left_hip_roll_link" pos="0 0 0">
          <inertial pos="0 0 0" mass="2.0" diaginertia="0.004 0.004 0.003"/>
          <geom type="cylinder" size="0.04 0.03" rgba="0 .4 .8 1"/>
          <joint name="left_hip_roll" axis="1 0 0" range="-0.523 0.523"/>
          <body name="left_thigh_link" pos="0 0 0">
            <inertial pos="0 0 -0.175" mass="5.0" diaginertia="0.05 0.05 0.005"/>
            <geom type="box" size="0.035 0.03 0.175" pos="0 0 -0.175" rgba=".2 .2 .2 1"/>
            <joint name="left_hip_pitch" axis="0 1 0" range="-1.57 1.57"/>
            <body name="left_shank_link" pos="0 0 -0.35">
              <inertial pos="0 0 -0.175" mass="3.5" diaginertia="0.03 0.03 0.003"/>
              <geom type="box" size="0.03 0.025 0.175" pos="0 0 -0.175" rgba=".2 .2 .2 1"/>
              <joint name="left_knee" axis="0 1 0" range="-0.087 2.443"/>
              <body name="left_ankle_link" pos="0 0 -0.35">
                <inertial pos="0.05 0 -0.03" mass="1.5" diaginertia="0.003 0.005 0.005"/>
                <geom type="box" size="0.11 0.05 0.03" pos="0.05 0 -0.03" rgba=".7 .7 .7 1"
                      friction="1.0 0.005 0.0001"/>
                <site name="left_foot_site" pos="0.05 0 -0.06" size="0.01"/>
                <joint name="left_ankle" axis="0 1 0" range="-0.785 0.785" damping="1.0"/>
              </body>
            </body>
          </body>
        </body>
      </body>
      <!-- Right leg -->
      <body name="right_hip_yaw_link" pos="0 -0.09 -0.05">
        <inertial pos="0 0 0" mass="1.5" diaginertia="0.003 0.003 0.002"/>
        <geom type="cylinder" size="0.04 0.03" rgba="0 .4 .8 1"/>
        <joint name="right_hip_yaw" axis="0 0 1" range="-0.785 0.785"/>
        <body name="right_hip_roll_link" pos="0 0 0">
          <inertial pos="0 0 0" mass="2.0" diaginertia="0.004 0.004 0.003"/>
          <geom type="cylinder" size="0.04 0.03" rgba="0 .4 .8 1"/>
          <joint name="right_hip_roll" axis="1 0 0" range="-0.523 0.523"/>
          <body name="right_thigh_link" pos="0 0 0">
            <inertial pos="0 0 -0.175" mass="5.0" diaginertia="0.05 0.05 0.005"/>
            <geom type="box" size="0.035 0.03 0.175" pos="0 0 -0.175" rgba=".2 .2 .2 1"/>
            <joint name="right_hip_pitch" axis="0 1 0" range="-1.57 1.57"/>
            <body name="right_shank_link" pos="0 0 -0.35">
              <inertial pos="0 0 -0.175" mass="3.5" diaginertia="0.03 0.03 0.003"/>
              <geom type="box" size="0.03 0.025 0.175" pos="0 0 -0.175" rgba=".2 .2 .2 1"/>
              <joint name="right_knee" axis="0 1 0" range="-0.087 2.443"/>
              <body name="right_ankle_link" pos="0 0 -0.35">
                <inertial pos="0.05 0 -0.03" mass="1.5" diaginertia="0.003 0.005 0.005"/>
                <geom type="box" size="0.11 0.05 0.03" pos="0.05 0 -0.03" rgba=".7 .7 .7 1"
                      friction="1.0 0.005 0.0001"/>
                <site name="right_foot_site" pos="0.05 0 -0.06" size="0.01"/>
                <joint name="right_ankle" axis="0 1 0" range="-0.785 0.785" damping="1.0"/>
              </body>
            </body>
          </body>
        </body>
      </body>
    </body>
  </worldbody>
  <actuator>
    <motor name="left_hip_yaw_m"    joint="left_hip_yaw"    ctrlrange="-200 200"/>
    <motor name="left_hip_roll_m"   joint="left_hip_roll"   ctrlrange="-200 200"/>
    <motor name="left_hip_pitch_m"  joint="left_hip_pitch"  ctrlrange="-200 200"/>
    <motor name="left_knee_m"       joint="left_knee"       ctrlrange="-300 300"/>
    <motor name="left_ankle_m"      joint="left_ankle"      ctrlrange="-40 40"/>
    <motor name="right_hip_yaw_m"   joint="right_hip_yaw"   ctrlrange="-200 200"/>
    <motor name="right_hip_roll_m"  joint="right_hip_roll"  ctrlrange="-200 200"/>
    <motor name="right_hip_pitch_m" joint="right_hip_pitch" ctrlrange="-200 200"/>
    <motor name="right_knee_m"      joint="right_knee"      ctrlrange="-300 300"/>
    <motor name="right_ankle_m"     joint="right_ankle"     ctrlrange="-40 40"/>
    <motor name="left_shoulder_pitch_m"  joint="left_shoulder_pitch"  ctrlrange="-40 40"/>
    <motor name="left_shoulder_roll_m"   joint="left_shoulder_roll"   ctrlrange="-40 40"/>
    <motor name="left_elbow_m"           joint="left_elbow"           ctrlrange="-40 40"/>
    <motor name="left_wrist_m"           joint="left_wrist"           ctrlrange="-10 10"/>
    <motor name="right_shoulder_pitch_m" joint="right_shoulder_pitch" ctrlrange="-40 40"/>
    <motor name="right_shoulder_roll_m"  joint="right_shoulder_roll"  ctrlrange="-40 40"/>
    <motor name="right_elbow_m"          joint="right_elbow"          ctrlrange="-40 40"/>
    <motor name="right_wrist_m"          joint="right_wrist"          ctrlrange="-10 10"/>
  </actuator>
  <sensor>
    <gyro       name="imu_gyro"  site="imu_site"/>
    <accelerometer name="imu_acc" site="imu_site"/>
    <framequat  name="imu_quat"  objtype="site" objname="imu_site"/>
    <touch      name="left_foot_touch"  site="left_foot_site"/>
    <touch      name="right_foot_touch" site="right_foot_site"/>
  </sensor>
</mujoco>
"""


# ── Joint defaults (standing pose) ───────────────────────────────────────────
# Order matches actuator order: legs (10) + arms (8)
_DEFAULT_JOINT_POS = np.array([
    # Left leg: hip_yaw, hip_roll, hip_pitch, knee, ankle
    0.0, 0.0, -0.4, 0.8, -0.4,
    # Right leg
    0.0, 0.0, -0.4, 0.8, -0.4,
    # Left arm: shoulder_pitch, shoulder_roll, elbow, wrist
    0.0, 0.0, 0.0, 0.0,
    # Right arm
    0.0, 0.0, 0.0, 0.0,
], dtype=np.float32)

# PD gains for position control
_KP = np.array([
    200, 200, 200, 300, 40,   # left leg
    200, 200, 200, 300, 40,   # right leg
    40,  40,  40,  10,        # left arm
    40,  40,  40,  10,        # right arm
], dtype=np.float32)

_KD = np.array([
    5.0, 5.0, 5.0, 8.0, 1.0,  # left leg
    5.0, 5.0, 5.0, 8.0, 1.0,  # right leg
    1.0, 1.0, 1.0, 0.5,        # left arm
    1.0, 1.0, 1.0, 0.5,        # right arm
], dtype=np.float32)

_N_ACTUATORS = 18
_OBS_DIM = 45   # 3 ang_vel + 3 proj_grav + 3 cmd + 18 qpos + 18 qvel
_ACT_DIM = _N_ACTUATORS


class H1MuJoCoEnv:
    """
    H1 humanoid locomotion environment using MuJoCo Python bindings.

    Conforms to the OpenAI Gym/Gymnasium step() interface:
        obs, reward, terminated, truncated, info  (gymnasium)
        obs, reward, done, info                   (gym legacy)

    The environment uses PD control: action = target joint positions.
    Torques = Kp*(q_des - q) - Kd*qd

    Args:
        xml_path: path to MJCF model file. If None, uses inline model.
        render_mode: None | "human" | "rgb_array"
        max_episode_steps: episode length
        seed: random seed
        control_decimation: physics steps per control step (dt_ctrl = dt_physics * decimation)
        command_vel: (vx, vy, yaw_rate) target velocities (m/s, m/s, rad/s)
    """

    metadata = {"render_modes": ["human", "rgb_array"]}

    def __init__(
        self,
        xml_path: str | None = None,
        render_mode: str | None = None,
        max_episode_steps: int = 1000,
        seed: int = 0,
        control_decimation: int = 4,  # 50 Hz control at 200 Hz physics
        command_vel: tuple[float, float, float] = (0.5, 0.0, 0.0),
    ) -> None:
        import mujoco  # noqa: PLC0415 — import here so module loads without mujoco installed

        self._mujoco = mujoco
        self.render_mode = render_mode
        self.max_episode_steps = max_episode_steps
        self.control_decimation = control_decimation
        self.command_vel = np.array(command_vel, dtype=np.float32)
        self._rng = np.random.default_rng(seed)
        self._step_count = 0

        # Load model
        if xml_path is not None and os.path.isfile(xml_path):
            self._model = mujoco.MjModel.from_xml_path(xml_path)
        elif _ASSET_PATH.is_file():
            self._model = mujoco.MjModel.from_xml_path(str(_ASSET_PATH))
        else:
            self._model = mujoco.MjModel.from_xml_string(_INLINE_MJCF)

        self._data = mujoco.MjData(self._model)

        # Verify actuator count
        assert self._model.nu == _N_ACTUATORS, (
            f"Expected {_N_ACTUATORS} actuators, got {self._model.nu}"
        )

        # Cache joint indices (skip freejoint: 7 qpos, 6 qvel)
        self._qpos_slice = slice(7, 7 + _N_ACTUATORS)
        self._qvel_slice = slice(6, 6 + _N_ACTUATORS)

        # Observation/action spaces
        obs_high = np.full(_OBS_DIM, np.inf, dtype=np.float32)
        self.observation_space = spaces.Box(-obs_high, obs_high, dtype=np.float32)

        # Action space: target positions, bounded by joint ranges
        # Extract joint position limits for actuated joints
        act_low  = np.array([self._model.jnt_range[i + 1, 0] for i in range(_N_ACTUATORS)], dtype=np.float32)
        act_high = np.array([self._model.jnt_range[i + 1, 1] for i in range(_N_ACTUATORS)], dtype=np.float32)
        self.action_space = spaces.Box(act_low, act_high, dtype=np.float32)

        # Renderer
        self._viewer = None
        self._renderer = None
        if render_mode == "human":
            self._init_viewer()

    # ── Public interface ──────────────────────────────────────────────────────

    def reset(
        self,
        seed: int | None = None,
        options: dict | None = None,
    ) -> np.ndarray | tuple[np.ndarray, dict]:
        if seed is not None:
            self._rng = np.random.default_rng(seed)

        mujoco = self._mujoco
        mujoco.mj_resetData(self._model, self._data)

        # Set initial pose (standing)
        self._data.qpos[3:7] = [0, 0, 0, 1]  # quaternion w=1
        self._data.qpos[self._qpos_slice] = _DEFAULT_JOINT_POS.copy()

        # Small random perturbation for domain randomization
        noise = self._rng.uniform(-0.02, 0.02, _N_ACTUATORS).astype(np.float32)
        self._data.qpos[self._qpos_slice] += noise

        # Randomize velocity command slightly
        cmd_noise = self._rng.uniform(-0.1, 0.1, 3).astype(np.float32)
        self._cmd = self.command_vel + cmd_noise

        mujoco.mj_forward(self._model, self._data)
        self._step_count = 0
        self._last_action = _DEFAULT_JOINT_POS.copy()

        obs = self._get_obs()

        if GYM_VERSION == "gymnasium":
            return obs, {}
        return obs

    def step(
        self, action: np.ndarray
    ) -> tuple[np.ndarray, float, bool, dict] | tuple[np.ndarray, float, bool, bool, dict]:
        """
        Step the environment.

        Args:
            action: target joint positions (18 dims)

        Returns:
            obs, reward, terminated, truncated, info (gymnasium)
            obs, reward, done, info                  (gym legacy)
        """
        mujoco = self._mujoco
        action = np.clip(action, self.action_space.low, self.action_space.high)

        # PD control loop (decimated)
        for _ in range(self.control_decimation):
            q = self._data.qpos[self._qpos_slice]
            qd = self._data.qvel[self._qvel_slice]
            torques = _KP * (action - q) - _KD * qd
            # Clamp to actuator limits
            ctrl_low  = self._model.actuator_ctrlrange[:, 0]
            ctrl_high = self._model.actuator_ctrlrange[:, 1]
            self._data.ctrl[:] = np.clip(torques, ctrl_low, ctrl_high)
            mujoco.mj_step(self._model, self._data)

        self._step_count += 1
        self._last_action = action.copy()

        obs = self._get_obs()
        reward = self._compute_reward(action)
        terminated = self._is_terminated()
        truncated = self._step_count >= self.max_episode_steps
        info = self._get_info()

        if render_mode := self.render_mode:
            if render_mode == "human":
                self._render_human()

        if GYM_VERSION == "gymnasium":
            return obs, reward, terminated, truncated, info
        return obs, reward, (terminated or truncated), info

    def close(self) -> None:
        if self._viewer is not None:
            self._viewer.close()
            self._viewer = None
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None

    def render(self) -> np.ndarray | None:
        if self.render_mode == "rgb_array":
            return self._render_rgb()
        elif self.render_mode == "human":
            self._render_human()
        return None

    def seed(self, seed: int | None = None) -> list[int]:
        self._rng = np.random.default_rng(seed)
        return [seed or 0]

    # ── Observation / reward ──────────────────────────────────────────────────

    def _get_obs(self) -> np.ndarray:
        """Compute 45-dim proprioceptive observation."""
        # Angular velocity from gyro sensor
        gyro_idx = self._mujoco.mj_name2id(self._model, self._mujoco.mjtObj.mjOBJ_SENSOR, "imu_gyro")
        if gyro_idx >= 0:
            ang_vel = self._data.sensordata[gyro_idx * 3: gyro_idx * 3 + 3].copy()
        else:
            ang_vel = self._data.qvel[3:6].copy()

        # Gravity projection: rotate [0,0,-1] into base frame
        quat = self._data.qpos[3:7]  # [x, y, z, w] — MuJoCo stores w last... actually [w, x, y, z]
        # MuJoCo convention: qpos[3:7] = [qw, qx, qy, qz]
        proj_grav = self._project_gravity(quat)

        # Joint states (18 DOF)
        q_rel = (self._data.qpos[self._qpos_slice] - _DEFAULT_JOINT_POS).astype(np.float32)
        qd = self._data.qvel[self._qvel_slice].astype(np.float32)

        obs = np.concatenate([
            ang_vel.astype(np.float32),   # 3
            proj_grav.astype(np.float32), # 3
            self._cmd.astype(np.float32), # 3
            q_rel,                         # 18
            qd,                            # 18
        ])
        assert obs.shape == (_OBS_DIM,), f"Obs dim mismatch: {obs.shape}"
        return obs

    def _project_gravity(self, quat_wxyz: np.ndarray) -> np.ndarray:
        """Rotate world gravity [0,0,-1] into base frame using MuJoCo quaternion [w,x,y,z]."""
        w, x, y, z = quat_wxyz
        # Rotate gravity world→base using inverse rotation
        grav_world = np.array([0.0, 0.0, -1.0])
        # Apply q^{-1}: conjugate = [w, -x, -y, -z]
        # Rodrigues rotation: v' = v + 2w(q×v) + 2(q×(q×v))
        qvec = np.array([x, y, z])
        t = 2.0 * np.cross(qvec, grav_world)
        return grav_world + w * t + np.cross(qvec, t)

    def _compute_reward(self, action: np.ndarray) -> float:
        """
        Reward composition:
          + velocity tracking (primary)
          + upright orientation
          - action rate (smoothness)
          - energy (torque * velocity)
          + alive bonus
        """
        # Base velocity (from freejoint qvel)
        base_vel = self._data.qvel[:3]
        vx_track = -abs(base_vel[0] - self._cmd[0])
        vy_track = -abs(base_vel[1] - self._cmd[1])

        # Upright: penalize tilt
        quat = self._data.qpos[3:7]
        grav = self._project_gravity(quat)
        upright = grav[2]  # -1 when upright, 0 when sideways

        # Action rate
        action_rate = -np.sum((action - self._last_action) ** 2) * 0.01

        # Energy: |torque * qvel|
        q = self._data.qpos[self._qpos_slice]
        qd = self._data.qvel[self._qvel_slice]
        torques = _KP * (action - q) - _KD * qd
        energy = -np.sum(np.abs(torques * qd)) * 2.5e-5

        # Alive bonus
        alive = 1.0 if not self._is_terminated() else 0.0

        reward = (
            1.5 * np.exp(-abs(base_vel[0] - self._cmd[0]) / 0.5)  # vx tracking
            + 1.0 * np.exp(-abs(base_vel[1] - self._cmd[1]) / 0.5)  # vy tracking
            + 2.0 * upright      # upright orientation
            + action_rate        # smoothness
            + energy             # energy efficiency
            + 0.5 * alive        # alive bonus
        )
        return float(reward)

    def _is_terminated(self) -> bool:
        """Terminate if robot falls or tilts excessively."""
        base_height = self._data.qpos[2]
        if base_height < 0.5:
            return True
        # Check tilt
        quat = self._data.qpos[3:7]
        proj_grav = self._project_gravity(quat)
        tilt = np.arccos(np.clip(-proj_grav[2], -1.0, 1.0))
        if tilt > 0.8:
            return True
        return False

    def _get_info(self) -> dict[str, Any]:
        """Return diagnostic info dict."""
        base_height = float(self._data.qpos[2])
        base_vel = self._data.qvel[:3].copy()
        return {
            "base_height_m": base_height,
            "base_vel_xyz": base_vel.astype(np.float32),
            "step": self._step_count,
            "cmd_vel": self._cmd.copy(),
            "left_foot_contact": bool(
                self._get_foot_contact("left_foot_site")
            ),
            "right_foot_contact": bool(
                self._get_foot_contact("right_foot_site")
            ),
        }

    def _get_foot_contact(self, site_name: str) -> float:
        """Return contact force magnitude at foot site."""
        try:
            sensor_name = site_name.replace("_site", "_touch")
            sid = self._mujoco.mj_name2id(
                self._model, self._mujoco.mjtObj.mjOBJ_SENSOR, sensor_name
            )
            if sid >= 0:
                return float(self._data.sensordata[sid])
        except Exception:
            pass
        return 0.0

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _init_viewer(self) -> None:
        try:
            import mujoco.viewer
            self._viewer = mujoco.viewer.launch_passive(self._model, self._data)
        except Exception:
            self._viewer = None

    def _render_human(self) -> None:
        if self._viewer is not None:
            try:
                self._viewer.sync()
            except Exception:
                pass

    def _render_rgb(self) -> np.ndarray | None:
        try:
            if self._renderer is None:
                self._renderer = self._mujoco.Renderer(self._model, height=480, width=640)
            self._renderer.update_scene(self._data, camera="fixed")
            return self._renderer.render()
        except Exception:
            return None

    # ── Context manager ───────────────────────────────────────────────────────

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def __repr__(self) -> str:
        return (
            f"H1MuJoCoEnv("
            f"obs={_OBS_DIM}, act={_ACT_DIM}, "
            f"step={self._step_count}/{self.max_episode_steps})"
        )


# ── Smoke test (run as script) ────────────────────────────────────────────────

if __name__ == "__main__":
    print("Running H1MuJoCoEnv smoke test...")
    env = H1MuJoCoEnv()
    result = env.reset()
    if isinstance(result, tuple):
        obs, info = result
    else:
        obs = result

    print(f"  obs shape: {obs.shape}, obs[:5]: {obs[:5]}")
    print(f"  action_space: {env.action_space}")

    total_reward = 0.0
    for i in range(10):
        action = env.action_space.sample()
        result = env.step(action)
        if len(result) == 5:
            obs, rew, terminated, truncated, info = result
            done = terminated or truncated
        else:
            obs, rew, done, info = result
        total_reward += rew
        print(f"  step {i+1}: rew={rew:.3f}, done={done}, height={info['base_height_m']:.3f}")
        if done:
            break

    env.close()
    print(f"Smoke test PASSED. Total reward: {total_reward:.3f}")
