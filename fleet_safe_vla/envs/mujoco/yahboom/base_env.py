"""
Base MuJoCo environment for Yahboom RosMaster X3.

Shared physics, observation production, and episode infrastructure.
All four task envs inherit from this.

Observation contract: same 36-dim vector as real robot (via YahboomObsAdapter).
Action contract: [vx (m/s), wz (rad/s)] clipped to safety limits.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from fleet_safe_vla.robots.yahboom.controllers.obs_adapter import (
    YahboomObsAdapter,
    cmd_vel_to_wheel_speeds,
    wheel_speeds_to_cmd_vel,
)

# Path to MJCF asset
_MJCF_PATH = Path(__file__).parents[4] / "robots/yahboom/mjcf/yahboom_x3.xml"

# Safety limits (from safety_limits.yaml)
MAX_LINEAR_MS  = 0.5
MAX_ANGULAR_RS = 1.0
WHEELBASE_M    = 0.245
WHEEL_R_M      = 0.048


class YahboomMuJoCoBase:
    """
    Gym-compatible MuJoCo environment for the Yahboom X3.

    Subclasses override:
      - _compute_reward(obs, action, info) -> float
      - _is_terminated(obs, info) -> bool
      - _reset_task()  — place goals/obstacles
      - _task_info()   — extra info dict fields
    """

    metadata = {"render_modes": ["rgb_array"], "render_fps": 25}

    def __init__(
        self,
        max_episode_steps: int = 500,
        control_hz: float = 10.0,
        xml_string: str | None = None,
        seed: int | None = None,
    ):
        self.max_episode_steps = max_episode_steps
        self.control_hz = control_hz
        self._sim_dt = 0.004
        self._decimation = max(1, round(1.0 / (control_hz * self._sim_dt)))

        # Load model
        if xml_string is not None:
            self._model = mujoco.MjModel.from_xml_string(xml_string)
        elif _MJCF_PATH.exists():
            self._model = mujoco.MjModel.from_xml_path(str(_MJCF_PATH))
        else:
            self._model = mujoco.MjModel.from_xml_string(self._get_inline_xml())

        self._data = mujoco.MjData(self._model)
        self._obs_adapter = YahboomObsAdapter()
        self._rng = np.random.default_rng(seed)

        # Gym spaces
        import gymnasium as gym
        self.observation_space = gym.spaces.Box(
            low=-np.inf, high=np.inf,
            shape=(YahboomObsAdapter.OBS_DIM,), dtype=np.float32,
        )
        self.action_space = gym.spaces.Box(
            low=np.array([-MAX_LINEAR_MS, -MAX_ANGULAR_RS], dtype=np.float32),
            high=np.array([MAX_LINEAR_MS,  MAX_ANGULAR_RS], dtype=np.float32),
            dtype=np.float32,
        )

        self._step_count = 0
        self._last_cmd = np.zeros(2, dtype=np.float32)
        self._episode_start_time = time.monotonic()

    # ── Public API ─────────────────────────────────────────────────────────── #

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        if seed is not None:
            self._rng = np.random.default_rng(seed)

        mujoco.mj_resetData(self._model, self._data)
        self._obs_adapter.reset()
        self._step_count = 0
        self._last_cmd = np.zeros(2, dtype=np.float32)
        self._episode_start_time = time.monotonic()

        # Randomize starting position slightly
        # z=0.066: body center height so wheels just touch floor
        self._data.qpos[0] += self._rng.uniform(-0.1, 0.1)
        self._data.qpos[1] += self._rng.uniform(-0.1, 0.1)
        # preserve default z from XML (0.066) — do NOT override
        yaw = self._rng.uniform(-0.2, 0.2)
        self._data.qpos[3:7] = [np.cos(yaw/2), 0, 0, np.sin(yaw/2)]  # quat w,x,y,z

        self._reset_task()
        mujoco.mj_forward(self._model, self._data)

        obs = self._get_obs()
        self._last_obs = obs
        return obs, self._task_info()

    def step(self, action: np.ndarray):
        action = np.clip(action, self.action_space.low, self.action_space.high)
        vx, wz = float(action[0]), float(action[1])
        self._last_cmd = action.astype(np.float32)

        dt = 1.0 / self.control_hz          # 0.1 s per control step
        x, y, yaw = self.get_robot_pose()

        # Unicycle kinematic integration — bypasses actuator instability
        x_new   = x + vx * np.cos(yaw) * dt
        y_new   = y + vx * np.sin(yaw) * dt
        yaw_new = yaw + wz * dt

        # Update base pose
        self._data.qpos[0] = x_new
        self._data.qpos[1] = y_new
        # qpos[2] (z) unchanged — keep XML default 0.066
        self._data.qpos[3:7] = [np.cos(yaw_new / 2), 0.0, 0.0, np.sin(yaw_new / 2)]

        # Wheel joint angles (drives jointpos/jointvel sensor readings)
        v_l, v_r = cmd_vel_to_wheel_speeds(vx, wz, WHEELBASE_M, WHEEL_R_M)
        self._data.qpos[7] = self._data.qpos[7] + v_l * dt
        self._data.qpos[8] = self._data.qpos[8] + v_r * dt

        # Generalized velocities (drives odom reading)
        self._data.qvel[0] = vx * np.cos(yaw_new)
        self._data.qvel[1] = vx * np.sin(yaw_new)
        self._data.qvel[2] = 0.0
        self._data.qvel[3] = 0.0
        self._data.qvel[4] = 0.0
        self._data.qvel[5] = wz
        self._data.qvel[6] = v_l
        self._data.qvel[7] = v_r

        # Forward kinematics only — no physics integration
        mujoco.mj_forward(self._model, self._data)

        obs = self._get_obs()
        self._last_obs = obs
        info = self._task_info()
        reward = self._compute_reward(obs, action, info)
        terminated = self._is_terminated(obs, info)
        self._step_count += 1
        truncated = self._step_count >= self.max_episode_steps

        return obs, float(reward), terminated, truncated, info

    def teleport_to(self, x: float, y: float, yaw: float = 0.0) -> None:
        """Move robot to world position without a physics step (scene initialization)."""
        self._data.qpos[0] = x
        self._data.qpos[1] = y
        self._data.qpos[3:7] = [np.cos(yaw / 2), 0.0, 0.0, np.sin(yaw / 2)]
        mujoco.mj_forward(self._model, self._data)
        self._last_obs = self._get_obs()

    def close(self):
        pass  # MuJoCo model/data are GC'd

    def render(self) -> np.ndarray | None:
        return None

    # ── Observation ────────────────────────────────────────────────────────── #

    def _get_obs(self) -> np.ndarray:
        imu = self._read_imu()
        joints = self._read_joints()
        odom = self._read_odom()
        return self._obs_adapter.update(imu=imu, joints=joints, odom=odom, cmd_vel=self._last_cmd)

    def _read_imu(self) -> dict:
        # Kinematic IMU: mj_forward doesn't compute qacc so accelerometer sensor
        # is meaningless. Approximate gravity projection + angular rate from qvel.
        qw, qx, qy, qz = self._data.qpos[3:7]
        wz = float(self._data.qvel[5])
        # On flat ground the body-frame accelerometer reads gravity (-z in world → +z_body)
        return {
            "ax": 0.0, "ay": 0.0, "az": -9.81,
            "wx": 0.0, "wy": 0.0, "wz": wz,
            "qx": float(qx), "qy": float(qy), "qz": float(qz), "qw": float(qw),
        }

    def _read_joints(self) -> dict:
        lpos = self._data.sensor("left_wheel_pos").data[0]
        rpos = self._data.sensor("right_wheel_pos").data[0]
        lvel = self._data.sensor("left_wheel_vel_sensor").data[0]
        rvel = self._data.sensor("right_wheel_vel_sensor").data[0]
        return {"left_pos": lpos, "right_pos": rpos, "left_vel": lvel, "right_vel": rvel,
                "left_eff": 0.0, "right_eff": 0.0}

    def _read_odom(self) -> dict:
        pos  = self._data.qpos[:3]
        quat = self._data.qpos[3:7]  # [w, x, y, z] in MuJoCo freejoint
        vel  = self._data.qvel[:3]
        vx, vy = float(vel[0]), float(vel[1])
        vyaw = float(vel[5]) if len(vel) > 5 else 0.0
        return {
            "x": float(pos[0]), "y": float(pos[1]), "z": float(pos[2]),
            "qx": float(quat[1]), "qy": float(quat[2]),
            "qz": float(quat[3]), "qw": float(quat[0]),
            "vx": vx, "vy": vy, "vyaw": vyaw,
        }

    def get_robot_pose(self) -> tuple[float, float, float]:
        """Return (x, y, yaw) of the robot base."""
        x, y = float(self._data.qpos[0]), float(self._data.qpos[1])
        quat = self._data.qpos[3:7]  # [w,x,y,z]
        yaw = float(2 * np.arctan2(quat[3], quat[0]))
        return x, y, yaw

    # ── Subclass interface ─────────────────────────────────────────────────── #

    def _reset_task(self): pass
    def _task_info(self) -> dict: return {"step": self._step_count}
    def _compute_reward(self, obs, action, info) -> float: return 0.0
    def _is_terminated(self, obs, info) -> bool: return False

    # ── Inline MJCF fallback (identical to the file) ──────────────────────── #

    @staticmethod
    def _get_inline_xml() -> str:
        """
        Inline MJCF used when yahboom_x3.xml is not present.

        VLN perception contract: the <camera name="camera"> is the ONLY
        observation source for GNM/ViNT/NoMaD.  It looks forward along +X.
        Global state (odom x/y, obstacle positions) reaches only the CBF filter.
        """
        return """
<mujoco model="yahboom_x3">
  <option timestep="0.004" gravity="0 0 -9.81"/>
  <asset>
    <texture name="floor_tex" type="2d" builtin="checker"
             width="512" height="512" rgb1="0.72 0.70 0.66" rgb2="0.80 0.78 0.74"/>
    <material name="floor_mat" texture="floor_tex" texrepeat="8 8" reflectance="0.08"/>
    <material name="wall_mat"  rgba="0.74 0.72 0.68 1.0"/>
    <material name="ceil_mat"  rgba="0.84 0.83 0.81 1.0"/>
    <material name="person_mat" rgba="0.25 0.45 0.75 1.0"/>
  </asset>
  <worldbody>
    <light name="ambient" pos="0 0 3" dir="0 0 -1" diffuse="0.7 0.7 0.7"
           castshadow="false" directional="true"/>
    <light name="strip_0" pos="0 0 2.5" dir="0 0 -1" diffuse="0.5 0.5 0.45"
           castshadow="false"/>
    <geom name="floor" type="plane" size="12 3 0.1" material="floor_mat"
          contype="1" conaffinity="1"/>
    <geom name="wall_left"  type="box" size="12 0.05 1.25"
          pos="0  1.5 1.25" material="wall_mat"  contype="0" conaffinity="0"/>
    <geom name="wall_right" type="box" size="12 0.05 1.25"
          pos="0 -1.5 1.25" material="wall_mat"  contype="0" conaffinity="0"/>
    <geom name="ceiling"    type="box" size="12 3 0.05"
          pos="0 0 2.55"     material="ceil_mat"  contype="0" conaffinity="0"/>
    <body name="base_link" pos="0 0 0.048">
      <freejoint name="root"/>
      <inertial mass="2.1" pos="0 0 0" diaginertia="0.010 0.014 0.020"/>
      <geom name="chassis" type="box" size="0.14 0.11 0.04" pos="0 0 0.04"/>
      <site name="imu"   pos="0 0 0.05"/>
      <site name="lidar" pos="0 0 0.105"/>
      <!-- Forward-facing egocentric camera: pos matches URDF camera_joint.
           xyaxes: camera-x=robot-right, camera-y=up → looks in robot +X. -->
      <camera name="camera" pos="0.10 0 0.082"
              xyaxes="0 -1 0 0 0 1" fovy="62"/>
      <body name="left_wheel_link" pos="0 0.1225 0">
        <joint name="left_wheel_joint" type="hinge" axis="0 1 0" damping="0.001"/>
        <inertial mass="0.12" pos="0 0 0" diaginertia="0.00014 0.00014 0.00024"/>
        <geom name="left_wheel"  type="cylinder" size="0.048 0.0125" euler="1.5708 0 0"
              friction="0.8 0.005 0.0001"/>
      </body>
      <body name="right_wheel_link" pos="0 -0.1225 0">
        <joint name="right_wheel_joint" type="hinge" axis="0 1 0" damping="0.001"/>
        <inertial mass="0.12" pos="0 0 0" diaginertia="0.00014 0.00014 0.00024"/>
        <geom name="right_wheel" type="cylinder" size="0.048 0.0125" euler="1.5708 0 0"
              friction="0.8 0.005 0.0001"/>
      </body>
      <geom name="caster_f" type="sphere" size="0.018" pos="0.10 0 -0.030" friction="0.01"/>
      <geom name="caster_r" type="sphere" size="0.018" pos="-0.10 0 -0.030" friction="0.01"/>
    </body>
    <geom name="obs_0" type="cylinder" size="0.10 0.80" pos="99 0 0.80" material="person_mat" contype="1" conaffinity="1"/>
    <geom name="obs_1" type="cylinder" size="0.10 0.80" pos="99 0 0.80" material="person_mat" contype="1" conaffinity="1"/>
    <geom name="obs_2" type="cylinder" size="0.10 0.80" pos="99 0 0.80" material="person_mat" contype="1" conaffinity="1"/>
    <geom name="obs_3" type="cylinder" size="0.10 0.80" pos="99 0 0.80" material="person_mat" contype="1" conaffinity="1"/>
    <geom name="obs_4" type="cylinder" size="0.10 0.80" pos="99 0 0.80" material="person_mat" contype="1" conaffinity="1"/>
    <geom name="obs_5" type="cylinder" size="0.10 0.80" pos="99 0 0.80" material="person_mat" contype="1" conaffinity="1"/>
    <geom name="obs_6" type="cylinder" size="0.10 0.80" pos="99 0 0.80" material="person_mat" contype="1" conaffinity="1"/>
    <geom name="obs_7" type="cylinder" size="0.10 0.80" pos="99 0 0.80" material="person_mat" contype="1" conaffinity="1"/>
    <geom name="obs_8" type="cylinder" size="0.10 0.80" pos="99 0 0.80" material="person_mat" contype="1" conaffinity="1"/>
    <geom name="obs_9" type="cylinder" size="0.10 0.80" pos="99 0 0.80" material="person_mat" contype="1" conaffinity="1"/>
  </worldbody>
  <actuator>
    <velocity name="left_wheel_vel"  joint="left_wheel_joint"  kv="0.05" ctrlrange="-15 15"/>
    <velocity name="right_wheel_vel" joint="right_wheel_joint" kv="0.05" ctrlrange="-15 15"/>
  </actuator>
  <sensor>
    <accelerometer name="accel" site="imu"/>
    <gyro          name="gyro"  site="imu"/>
    <framequat     name="orientation" objtype="site" objname="imu"/>
    <jointpos name="left_wheel_pos"  joint="left_wheel_joint"/>
    <jointpos name="right_wheel_pos" joint="right_wheel_joint"/>
    <jointvel name="left_wheel_vel_sensor"  joint="left_wheel_joint"/>
    <jointvel name="right_wheel_vel_sensor" joint="right_wheel_joint"/>
  </sensor>
</mujoco>"""
