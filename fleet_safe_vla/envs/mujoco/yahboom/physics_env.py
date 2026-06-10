"""
YahboomPhysicsEnv — physics-based MuJoCo env for dynamic realism validation.

Uses motor actuators + substep-rate PID velocity controller (250 Hz) to
overcome the kv·dt/I instability that breaks velocity actuators.

NOT used in the benchmark (benchmark uses kinematic base_env.step()).
Used exclusively for physics characterisation, actuator system-ID, and
domain-randomisation calibration sweeps.

Design choices:
- implicitfast integrator: unconditionally stable for stiff contacts
- Motor actuators (direct torque) rather than velocity actuators
- PID runs at each physics substep — integral term eliminates steady-state error
  due to ground friction (≈0.22 Nm) that a pure-P controller cannot overcome
- Chassis geom set non-collidable so it can't scrape the floor during bounces
- Contact parameters tuned for stable differential-drive at 10 Hz control rate
"""
from __future__ import annotations

import mujoco
import numpy as np

from fleet_safe_vla.envs.mujoco.yahboom.base_env import (
    YahboomMuJoCoBase,
    WHEELBASE_M,
    WHEEL_R_M,
)
from fleet_safe_vla.robots.yahboom.controllers.obs_adapter import cmd_vel_to_wheel_speeds

_TORQUE_LIMIT_NM = 3.0    # max motor torque


class _WheelPID:
    """Substep-rate PID velocity controller for a single wheel joint."""

    def __init__(self, kp: float, ki: float, kd: float, dt: float,
                 torque_limit: float = _TORQUE_LIMIT_NM):
        self.kp, self.ki, self.kd = kp, ki, kd
        self.dt = dt
        self._limit = torque_limit
        self._integral = 0.0
        self._prev_error = 0.0

    def compute(self, target: float, actual: float) -> float:
        error = target - actual
        self._integral += error * self.dt
        # Anti-windup: clamp integral contribution
        self._integral = float(np.clip(self._integral, -self._limit / max(self.ki, 1e-9),
                                       self._limit / max(self.ki, 1e-9)))
        d_error = (error - self._prev_error) / self.dt
        self._prev_error = error
        tau = self.kp * error + self.ki * self._integral + self.kd * d_error
        return float(np.clip(tau, -self._limit, self._limit))

    def reset(self) -> None:
        self._integral = 0.0
        self._prev_error = 0.0


class YahboomPhysicsEnv(YahboomMuJoCoBase):
    """
    Physics-based Yahboom env for dynamic realism validation.

    Parameters
    ----------
    friction : float
        Wheel-floor sliding friction coefficient (0.3 – 2.0).
    robot_mass : float
        Base body mass in kg.
    wheel_mass : float
        Per-wheel mass in kg.
    pid_kp, pid_ki, pid_kd : float
        PID gains for substep-rate wheel velocity controller.
    """

    def __init__(
        self,
        friction: float = 0.8,
        robot_mass: float = 2.1,
        wheel_mass: float = 0.12,
        pid_kp: float = 0.04,
        pid_ki: float = 0.05,
        pid_kd: float = 0.0,
        debug: bool = False,  # Add debug parameter
        **kwargs,
    ):
        self.friction = friction
        self.robot_mass = robot_mass
        self.wheel_mass = wheel_mass
        self.pid_kp = pid_kp
        self.pid_ki = pid_ki
        self.pid_kd = pid_kd

        self.debug = debug  # Assign debug parameter

        xml = self._build_physics_xml(friction, robot_mass, wheel_mass)
        super().__init__(xml_string=xml, **kwargs)

        self._pid_l = _WheelPID(pid_kp, pid_ki, pid_kd, self._sim_dt)
        self._pid_r = _WheelPID(pid_kp, pid_ki, pid_kd, self._sim_dt)

        # Track last commanded wheel targets for sensor reads
        self._v_l_target = 0.0
        self._v_r_target = 0.0

    # ── Physics step (overrides kinematic step in base_env) ─────────────────── #

    def step(self, action: np.ndarray):
        action = np.clip(action, self.action_space.low, self.action_space.high)
        vx, wz = float(action[0]), float(action[1])
        self._last_cmd = action.astype(np.float32)

        v_l, v_r = cmd_vel_to_wheel_speeds(vx, wz, WHEELBASE_M, WHEEL_R_M)
        self._v_l_target = v_l
        self._v_r_target = v_r

        # PID runs at physics rate (not just control rate)
        for _ in range(self._decimation):
            omega_l = float(self._data.qvel[6])
            omega_r = float(self._data.qvel[7])
            self._data.ctrl[0] = self._pid_l.compute(v_l, omega_l)
            self._data.ctrl[1] = self._pid_r.compute(v_r, omega_r)
            mujoco.mj_step(self._model, self._data)

        obs = self._get_obs()
        info = self._task_info()
        info.update(self._physics_info())
        reward = self._compute_reward(obs, action, info)
        terminated = self._is_terminated(obs, info)
        self._step_count += 1
        truncated = self._step_count >= self.max_episode_steps

        return obs, float(reward), terminated, truncated, info

    def reset(self, *, seed=None, options=None):
        obs, info = super().reset(seed=seed, options=options)
        self._pid_l.reset()
        self._pid_r.reset()
        self._v_l_target = 0.0
        self._v_r_target = 0.0

        # Diagnostic: Print contact geom names after reset
        if self.debug:
            contacts_reset = [(self._model.geom(g1).name, self._model.geom(g2).name) for g1, g2 in zip(self._data.contact.geom1, self._data.contact.geom2)]
            print("Contacts after reset:", contacts_reset)

        # Let physics settle (robot dropped onto floor)
        for _ in range(50):
            mujoco.mj_step(self._model, self._data)

        # Diagnostic: Print contact geom names after 50 steps
        if self.debug:
            contacts_50_steps = [(self._model.geom(g1).name, self._model.geom(g2).name) for g1, g2 in zip(self._data.contact.geom1, self._data.contact.geom2)]
            print("Contacts after 50 steps:", contacts_50_steps)

        return self._get_obs(), self._task_info()

    # ── IMU from actual physics sensors ─────────────────────────────────────── #

    def _read_imu(self) -> dict:
        accel = self._data.sensor("accel").data.copy()
        gyro  = self._data.sensor("gyro").data.copy()
        quat  = self._data.sensor("orientation").data.copy()  # [w,x,y,z]
        return {
            "ax": float(accel[0]), "ay": float(accel[1]), "az": float(accel[2]),
            "wx": float(gyro[0]),  "wy": float(gyro[1]),  "wz": float(gyro[2]),
            "qx": float(quat[1]), "qy": float(quat[2]),
            "qz": float(quat[3]), "qw": float(quat[0]),
        }

    # ── Physics diagnostics ──────────────────────────────────────────────────── #

    def body_velocity(self) -> tuple[float, float, float]:
        """Return (vx_body, vy_body, wz) in the body frame."""
        x, y, yaw = self.get_robot_pose()
        vx_world = float(self._data.qvel[0])
        vy_world = float(self._data.qvel[1])
        vx_body = vx_world * np.cos(yaw) + vy_world * np.sin(yaw)
        vy_body = -vx_world * np.sin(yaw) + vy_world * np.cos(yaw)
        wz = float(self._data.qvel[5])
        return float(vx_body), float(vy_body), wz

    def slip_ratios(self) -> tuple[float, float]:
        """Return (slip_L, slip_R) ∈ [0, 1].  0=perfect rolling, 1=full spin."""
        vx_body, _, _ = self.body_velocity()
        omega_l = float(self._data.qvel[6])
        omega_r = float(self._data.qvel[7])
        v_surf_l = omega_l * WHEEL_R_M
        v_surf_r = omega_r * WHEEL_R_M

        def _slip(v_surface: float) -> float:
            denom = abs(v_surface)
            if denom < 1e-4:
                return 0.0
            return float(np.clip(abs(v_surface - vx_body) / denom, 0.0, 1.0))

        return _slip(v_surf_l), _slip(v_surf_r)

    def _physics_info(self) -> dict:
        slip_l, slip_r = self.slip_ratios()
        vx_b, vy_b, wz = self.body_velocity()
        x, y, _ = self.get_robot_pose()
        return {
            "body_vx": vx_b,
            "body_vy": vy_b,
            "body_wz": wz,
            "slip_ratio_l": slip_l,
            "slip_ratio_r": slip_r,
            "wheel_omega_l": float(self._data.qvel[6]),
            "wheel_omega_r": float(self._data.qvel[7]),
            "robot_xy": [x, y],
        }

    # ── Parameterised MJCF ───────────────────────────────────────────────────── #

    @staticmethod
    def _build_physics_xml(friction: float, robot_mass: float, wheel_mass: float) -> str:
        wh_I = 0.5 * wheel_mass * WHEEL_R_M**2   # solid cylinder Izz
        wh_I_xy = 0.25 * wheel_mass * WHEEL_R_M**2 + wheel_mass * 0.0125**2 / 3
        f = friction
        return f"""
<mujoco model="yahboom_physics">
  <option timestep="0.004" gravity="0 0 -9.81" integrator="implicitfast"
          iterations="50" solver="Newton"/>
  <default>
    <!-- Near-rigid contact (timeconst = 1 step) prevents micro-bouncing -->
    <geom solref="0.005 1" solimp="0.99 0.995 0.001 0.5 2"/>
  </default>
  <worldbody>
    <geom name="floor" type="plane" size="20 20 0.1"
          friction="{f} 0.005 0.0001" contype="1" conaffinity="1"/>
    <body name="base_link" pos="0 0 0.066">
      <freejoint name="root"/>
      <inertial mass="{robot_mass}" pos="0 0 0" diaginertia="0.010 0.014 0.020"/>
      <geom name="chassis" type="box" size="0.14 0.11 0.04" pos="0 0 0"
            contype="0" conaffinity="0"/>
      <site name="imu" pos="0 0 0"/>
      <body name="left_wheel_link" pos="0 0.1225 -0.04">  # Ensure wheel is below chassis
        <joint name="left_wheel_joint" type="hinge" axis="0 1 0" damping="0.002"/>
        <inertial mass="{wheel_mass}" pos="0 0 0"
                  diaginertia="{wh_I_xy:.6f} {wh_I_xy:.6f} {wh_I:.6f}"/>
        <geom name="left_wheel" type="sphere" size="{WHEEL_R_M}"
              friction="{f} 0.005 0.0001"
              contype="1" conaffinity="1"/>
      </body>
      <body name="right_wheel_link" pos="0 -0.1225 -0.04">  # Ensure wheel is below chassis
        <joint name="right_wheel_joint" type="hinge" axis="0 1 0" damping="0.002"/>
        <inertial mass="{wheel_mass}" pos="0 0 0"
                  diaginertia="{wh_I_xy:.6f} {wh_I_xy:.6f} {wh_I:.6f}"/>
        <geom name="right_wheel" type="sphere" size="{WHEEL_R_M}"
              friction="{f} 0.005 0.0001"
              contype="1" conaffinity="1"/>
      </body>
      <geom name="caster_f" type="sphere" size="0.015" pos="0.10 0 -0.045" contype="1" conaffinity="1"/>
            friction="0.01" contype="1" conaffinity="1"/>
      <geom name="caster_r" type="sphere" size="0.015" pos="-0.10 0 -0.045" contype="1" conaffinity="1"/>
            friction="0.01" contype="1" conaffinity="1"/>
    </body>
  </worldbody>
  <actuator>
    <motor name="left_wheel_motor"  joint="left_wheel_joint"
           gear="1.0" ctrlrange="-{_TORQUE_LIMIT_NM} {_TORQUE_LIMIT_NM}"/>
    <motor name="right_wheel_motor" joint="right_wheel_joint"
           gear="1.0" ctrlrange="-{_TORQUE_LIMIT_NM} {_TORQUE_LIMIT_NM}"/>
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
