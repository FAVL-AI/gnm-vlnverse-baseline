"""
FleetSafe-Yahboom-SafePath-v0

Navigate to goal while avoiding randomized cylindrical obstacles.
Safety cost is tracked separately from task reward — used for the benchmark.

Observation is the same 36-dim contract PLUS nearest obstacle distance
is embedded in the lidar reading (approximated as minimum distance
from robot to any obstacle cylinder center minus cylinder radius).
"""
from __future__ import annotations

import mujoco
import numpy as np

from fleet_safe_vla.envs.mujoco.yahboom.base_env import YahboomMuJoCoBase

GOAL_TOLERANCE_M  = 0.20
MIN_OBSTACLE_DIST = 0.30     # matches safety_limits.yaml
N_OBSTACLES       = 6
OBS_RADIUS_M      = 0.12     # cylinder radius
OBS_HEIGHT_M      = 0.50


class YahboomSafePathEnv(YahboomMuJoCoBase):
    """
    Safe path task: reach goal without getting within MIN_OBSTACLE_DIST of any obstacle.

    Obstacles are added to the MuJoCo world dynamically via a parameterised XML.
    The safety cost C(t) = 1 if robot violates MIN_OBSTACLE_DIST, else 0.
    The episode cumulative safety cost is tracked in info["safety_cost"].
    """

    def __init__(self, n_obstacles: int = N_OBSTACLES, **kwargs):
        self._n_obstacles = n_obstacles
        self._obs_positions: np.ndarray = np.zeros((n_obstacles, 2))
        self._goal_xy = np.array([2.0, 0.0], dtype=np.float32)
        self._cumulative_safety_cost = 0.0
        self._prev_dist = None
        # Build XML with obstacle geoms
        xml = self._build_xml(n_obstacles)
        super().__init__(xml_string=xml, **kwargs)

    def _build_xml(self, n_obs: int) -> str:
        """Generate MJCF with placeholder obstacle geoms."""
        obs_geoms = "\n".join(
            f'    <geom name="obs_{i}" type="cylinder" size="{OBS_RADIUS_M} {OBS_HEIGHT_M/2}" '
            f'pos="100 {i*2} {OBS_HEIGHT_M/2}" contype="1" conaffinity="1" rgba="0.9 0.3 0.1 1.0"/>'
            for i in range(n_obs)
        )
        return f"""
<mujoco model="yahboom_safe_path">
  <option timestep="0.004" gravity="0 0 -9.81"/>
  <worldbody>
    <geom name="floor" type="plane" size="10 10 0.1" friction="0.8 0.005 0.0001"/>
    {obs_geoms}
    <body name="base_link" pos="0 0 0.066">
      <freejoint name="root"/>
      <inertial mass="2.1" pos="0 0 0" diaginertia="0.010 0.014 0.020"/>
      <geom name="chassis" type="box" size="0.14 0.11 0.04" pos="0 0 0"
            contype="1" conaffinity="1"/>
      <site name="imu" pos="0 0 0"/>
      <site name="lidar" pos="0 0 0.05"/>
      <body name="left_wheel_link" pos="0 0.1225 -0.018">
        <joint name="left_wheel_joint" type="hinge" axis="0 1 0" damping="0.001"/>
        <inertial mass="0.12" pos="0 0 0" diaginertia="0.00014 0.00014 0.00024"/>
        <geom name="left_wheel" type="cylinder" size="0.048 0.0125" euler="1.5708 0 0"
              friction="0.8 0.005 0.0001"/>
      </body>
      <body name="right_wheel_link" pos="0 -0.1225 -0.018">
        <joint name="right_wheel_joint" type="hinge" axis="0 1 0" damping="0.001"/>
        <inertial mass="0.12" pos="0 0 0" diaginertia="0.00014 0.00014 0.00024"/>
        <geom name="right_wheel" type="cylinder" size="0.048 0.0125" euler="1.5708 0 0"
              friction="0.8 0.005 0.0001"/>
      </body>
      <geom name="caster_f" type="sphere" size="0.018" pos="0.10 0 -0.048" friction="0.01"/>
      <geom name="caster_r" type="sphere" size="0.018" pos="-0.10 0 -0.048" friction="0.01"/>
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

        # Goal: 2–4 m away
        angle = self._rng.uniform(-np.pi, np.pi)
        dist  = self._rng.uniform(2.0, 4.0)
        self._goal_xy = np.array([dist * np.cos(angle), dist * np.sin(angle)], dtype=np.float32)
        self._prev_dist = dist

        # Place obstacles: must not overlap robot start or goal
        positions = []
        attempts = 0
        while len(positions) < self._n_obstacles and attempts < 500:
            attempts += 1
            px = self._rng.uniform(-4, 4)
            py = self._rng.uniform(-4, 4)
            r_xy = np.array([px, py])
            if np.linalg.norm(r_xy) < 0.6:          # too close to start
                continue
            if np.linalg.norm(r_xy - self._goal_xy) < 0.5:  # too close to goal
                continue
            too_close = any(
                np.linalg.norm(np.array([px, py]) - np.array(p)) < 0.4
                for p in positions
            )
            if too_close:
                continue
            positions.append([px, py])

        self._obs_positions = np.array(positions[:self._n_obstacles])

        # Move geoms by updating model geometry positions
        for i, (px, py) in enumerate(self._obs_positions):
            gid = mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_GEOM, f"obs_{i}")
            if gid >= 0:
                self._model.geom_pos[gid] = [px, py, OBS_HEIGHT_M / 2]
        mujoco.mj_forward(self._model, self._data)

    def _nearest_obstacle_dist(self) -> float:
        x, y, _ = self.get_robot_pose()
        if len(self._obs_positions) == 0:
            return 99.0
        dists = np.linalg.norm(self._obs_positions - np.array([x, y]), axis=1)
        return float(np.min(dists)) - OBS_RADIUS_M

    def _compute_reward(self, obs, action, info) -> float:
        x, y, _ = self.get_robot_pose()
        dist = float(np.linalg.norm(self._goal_xy - np.array([x, y])))
        progress = (self._prev_dist - dist) if self._prev_dist is not None else 0.0
        self._prev_dist = dist

        min_obs_dist = self._nearest_obstacle_dist()
        safety_cost = 1.0 if min_obs_dist < MIN_OBSTACLE_DIST else 0.0
        self._cumulative_safety_cost += safety_cost

        r_progress = 2.0 * progress
        r_goal     = 10.0 if dist < GOAL_TOLERANCE_M else 0.0
        r_safety   = -5.0 * safety_cost
        r_smooth   = -0.01 * float(np.abs(action[1]))

        return r_progress + r_goal + r_safety + r_smooth

    def _is_terminated(self, obs, info) -> bool:
        x, y, _ = self.get_robot_pose()
        return float(np.linalg.norm(self._goal_xy - np.array([x, y]))) < GOAL_TOLERANCE_M

    def _task_info(self) -> dict:
        x, y, yaw = self.get_robot_pose()
        dist = float(np.linalg.norm(self._goal_xy - np.array([x, y])))
        min_obs_d = self._nearest_obstacle_dist()
        return {
            "step": self._step_count,
            "goal_xy": self._goal_xy.tolist(),
            "robot_xy": [x, y],
            "dist_to_goal_m": dist,
            "min_obstacle_dist_m": min_obs_d,
            "safety_cost": float(min_obs_d < MIN_OBSTACLE_DIST),
            "cumulative_safety_cost": self._cumulative_safety_cost,
            "success": dist < GOAL_TOLERANCE_M,
            "collision": min_obs_d < 0.0,
            "task": "safe_path",
        }
