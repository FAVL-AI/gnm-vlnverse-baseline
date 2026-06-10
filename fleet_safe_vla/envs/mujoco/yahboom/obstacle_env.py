"""
FleetSafe-Yahboom-ObstacleAvoidance-v0

Dense obstacle field navigation — no explicit goal, just survive
as long as possible while making forward progress.

Metrics: time alive, total distance, safety cost, near-miss count.
"""
from __future__ import annotations

import mujoco
import numpy as np

from fleet_safe_vla.envs.mujoco.yahboom.base_env import YahboomMuJoCoBase

MIN_OBS_DIST   = 0.30
NEAR_MISS_DIST = 0.45
OBS_RADIUS     = 0.10
N_OBS          = 12


class YahboomObstacleEnv(YahboomMuJoCoBase):
    """
    Dense random cylinder field. Episode ends if robot collides (< 0 clearance).
    Reward: forward progress + alive bonus - safety cost.
    """

    def __init__(
        self,
        n_obstacles: int = N_OBS,
        fixed_positions: list[tuple[float, float]] | None = None,
        **kwargs,
    ):
        self._n_obstacles = max(n_obstacles, len(fixed_positions) if fixed_positions else 0)
        self._fixed_positions = fixed_positions
        self._obs_positions: np.ndarray = np.zeros((self._n_obstacles, 2))
        self._cumulative_safety_cost = 0.0
        self._near_miss_count = 0
        self._total_distance = 0.0
        self._last_xy: np.ndarray | None = None
        xml = self._build_obs_xml(self._n_obstacles)
        super().__init__(xml_string=xml, **kwargs)

    def _build_obs_xml(self, n_obs: int) -> str:
        """
        Build the scene MJCF.

        Obstacles are full-height cylinders (0.80 m tall, blue-grey) to resemble
        people in a hospital corridor.  They start off-screen (x=100) and are
        repositioned each episode via model.geom_pos in _reset_task().

        The <camera name="camera"> inside base_link is the ONLY observation source
        for GNM/ViNT/NoMaD (egocentric, forward-facing, 62° HFOV).
        Obstacle world positions are used exclusively by the CBF-QP safety filter.
        """
        obs_geoms = "\n    ".join(
            f'<geom name="obs_{i}" type="cylinder" size="{OBS_RADIUS} 0.80" '
            f'pos="100 {i * 3} 0.80" contype="1" conaffinity="1" '
            f'rgba="0.25 0.45 0.75 1.0"/>'
            for i in range(n_obs)
        )
        return f"""
<mujoco model="yahboom_obstacle">
  <option timestep="0.004" gravity="0 0 -9.81"/>
  <asset>
    <texture name="floor_tex" type="2d" builtin="checker"
             width="512" height="512" rgb1="0.72 0.70 0.66" rgb2="0.80 0.78 0.74"/>
    <material name="floor_mat" texture="floor_tex" texrepeat="8 8" reflectance="0.08"/>
    <material name="wall_mat"  rgba="0.74 0.72 0.68 1.0"/>
    <material name="ceil_mat"  rgba="0.84 0.83 0.81 1.0"/>
  </asset>
  <worldbody>
    <light name="ambient" pos="0 0 3" dir="0 0 -1" diffuse="0.7 0.7 0.7"
           castshadow="false" directional="true"/>
    <light name="strip_0" pos="0 0 2.5" dir="0 0 -1" diffuse="0.5 0.5 0.45"
           castshadow="false"/>
    <geom name="floor"      type="plane" size="12 3 0.1" material="floor_mat"
          contype="1" conaffinity="1"/>
    <geom name="wall_left"  type="box" size="12 0.05 1.25"
          pos="0  1.5 1.25" material="wall_mat" contype="0" conaffinity="0"/>
    <geom name="wall_right" type="box" size="12 0.05 1.25"
          pos="0 -1.5 1.25" material="wall_mat" contype="0" conaffinity="0"/>
    <geom name="ceiling"    type="box" size="12 3 0.05"
          pos="0 0 2.55"    material="ceil_mat" contype="0" conaffinity="0"/>
    {obs_geoms}
    <body name="base_link" pos="0 0 0.048">
      <freejoint name="root"/>
      <inertial mass="2.1" pos="0 0 0" diaginertia="0.010 0.014 0.020"/>
      <geom name="chassis" type="box" size="0.14 0.11 0.04" pos="0 0 0.04"/>
      <site name="imu"   pos="0 0 0.05"/>
      <site name="lidar" pos="0 0 0.105"/>
      <!-- Egocentric forward-facing camera: pos=URDF camera_link, looks in +X -->
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

    def _reset_task(self):
        self._cumulative_safety_cost = 0.0
        self._near_miss_count = 0
        self._total_distance = 0.0
        x0, y0, _ = self.get_robot_pose()
        self._last_xy = np.array([x0, y0])

        if self._fixed_positions is not None:
            positions = [list(p) for p in self._fixed_positions[:self._n_obstacles]]
        else:
            positions = []
            attempts = 0
            while len(positions) < self._n_obstacles and attempts < 1000:
                attempts += 1
                px = self._rng.uniform(-5, 5)
                py = self._rng.uniform(-5, 5)
                if np.sqrt(px**2 + py**2) < 0.7:   # clear start zone
                    continue
                if any(np.linalg.norm(np.array([px, py]) - np.array(p)) < 0.35 for p in positions):
                    continue
                positions.append([px, py])

        self._obs_positions = np.array(positions[:self._n_obstacles])
        for i, (px, py) in enumerate(self._obs_positions):
            gid = mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_GEOM, f"obs_{i}")
            if gid >= 0:
                self._model.geom_pos[gid] = [px, py, 0.25]
        mujoco.mj_forward(self._model, self._data)

    def _nearest_dist(self) -> float:
        x, y, _ = self.get_robot_pose()
        if len(self._obs_positions) == 0:
            return 99.0
        dists = np.linalg.norm(self._obs_positions - np.array([x, y]), axis=1)
        return float(np.min(dists)) - OBS_RADIUS

    def _compute_reward(self, obs, action, info) -> float:
        x, y, _ = self.get_robot_pose()
        xy = np.array([x, y])
        step_dist = float(np.linalg.norm(xy - self._last_xy)) if self._last_xy is not None else 0.0
        self._total_distance += step_dist
        self._last_xy = xy

        min_d = self._nearest_dist()
        safety_cost = 1.0 if min_d < MIN_OBS_DIST else 0.0
        near_miss   = 1.0 if min_d < NEAR_MISS_DIST else 0.0
        self._cumulative_safety_cost += safety_cost
        if near_miss and min_d >= MIN_OBS_DIST:
            self._near_miss_count += 1

        r_alive    = 0.1
        r_progress = 1.0 * float(action[0])  # forward speed reward
        r_safety   = -5.0 * safety_cost

        return r_alive + r_progress + r_safety

    def _is_terminated(self, obs, info) -> bool:
        return self._nearest_dist() < 0.0   # actual collision

    def _task_info(self) -> dict:
        x, y, _ = self.get_robot_pose()
        return {
            "step": self._step_count,
            "robot_xy": [x, y],
            "min_obstacle_dist_m": self._nearest_dist(),
            "cumulative_safety_cost": self._cumulative_safety_cost,
            "near_miss_count": self._near_miss_count,
            "total_distance_m": self._total_distance,
            "collision": self._nearest_dist() < 0.0,
            "task": "obstacle_avoidance",
        }
