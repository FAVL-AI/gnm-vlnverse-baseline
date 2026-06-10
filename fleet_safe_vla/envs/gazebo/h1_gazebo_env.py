"""
H1 Gazebo Locomotion Environment — Fleet-Safe-VLA-OS.

OpenAI Gym / Gymnasium-compatible wrapper that communicates with Gazebo Harmonic
via ROS2 Humble topics. Handles the case where rclpy is not installed by raising
a clear ImportError only when the environment is actually instantiated.

Architecture:
  - JointStateSubscriber: subscribes to /joint_states (50 Hz)
  - IMUSubscriber: subscribes to /imu/data (100 Hz)
  - JointCommandPublisher: publishes to /joint_group_effort_controller/commands
  - ResetServiceClient: calls /reset_simulation service

Prerequisites:
    source /opt/ros/humble/setup.bash
    ros2 launch fleet_safe_bringup h1_gazebo.launch.py

Env observations and actions match H1MuJoCoEnv for easy cross-sim transfer.
"""
from __future__ import annotations

import threading
import time
from typing import Any

import numpy as np

# Lazy import guard — allows module-level import without ROS2 installed
_RCLPY_AVAILABLE: bool = False
try:
    import rclpy  # noqa: F401
    _RCLPY_AVAILABLE = True
except ImportError:
    pass

try:
    import gymnasium as gym
    from gymnasium import spaces
    _GYM_VERSION = "gymnasium"
except ImportError:
    import gym
    from gym import spaces
    _GYM_VERSION = "gym"

# Joint order — matches actuator order in URDF / MuJoCo env
JOINT_NAMES = [
    "left_hip_yaw", "left_hip_roll", "left_hip_pitch", "left_knee", "left_ankle",
    "right_hip_yaw", "right_hip_roll", "right_hip_pitch", "right_knee", "right_ankle",
    "left_shoulder_pitch", "left_shoulder_roll", "left_elbow", "left_wrist",
    "right_shoulder_pitch", "right_shoulder_roll", "right_elbow", "right_wrist",
]

_N_JOINTS = len(JOINT_NAMES)  # 18
_OBS_DIM = 45

_DEFAULT_JOINT_POS = np.array([
    0.0, 0.0, -0.4, 0.8, -0.4,
    0.0, 0.0, -0.4, 0.8, -0.4,
    0.0, 0.0, 0.0, 0.0,
    0.0, 0.0, 0.0, 0.0,
], dtype=np.float32)


class _ROSBridge:
    """
    Thin ROS2 bridge that runs a background spin thread.
    Only instantiated when H1GazeboEnv is actually created.
    """

    def __init__(self, node_name: str = "fleet_safe_gazebo_env") -> None:
        import rclpy
        from rclpy.node import Node
        from sensor_msgs.msg import JointState, Imu
        from std_msgs.msg import Float64MultiArray

        rclpy.init(args=None)
        self._node = Node(node_name)
        self._lock = threading.Lock()

        # State storage
        self._joint_pos = np.zeros(_N_JOINTS, dtype=np.float32)
        self._joint_vel = np.zeros(_N_JOINTS, dtype=np.float32)
        self._ang_vel   = np.zeros(3, dtype=np.float32)
        self._quat_wxyz = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        self._has_joint_state = False
        self._has_imu = False

        # Subscriptions
        self._js_sub = self._node.create_subscription(
            JointState, "/joint_states", self._js_callback, 10
        )
        self._imu_sub = self._node.create_subscription(
            Imu, "/imu/data", self._imu_callback, 10
        )

        # Publisher for effort commands
        self._cmd_pub = self._node.create_publisher(
            Float64MultiArray,
            "/joint_group_effort_controller/commands",
            10,
        )

        # Spin in background thread
        self._spin_thread = threading.Thread(
            target=self._spin, daemon=True, name="rclpy_spin"
        )
        self._spin_thread.start()

    def _spin(self) -> None:
        import rclpy
        rclpy.spin(self._node)

    def _js_callback(self, msg) -> None:
        """Map incoming JointState to ordered joint arrays."""
        with self._lock:
            name_to_idx = {n: i for i, n in enumerate(JOINT_NAMES)}
            for i, name in enumerate(msg.name):
                if name in name_to_idx:
                    j = name_to_idx[name]
                    if i < len(msg.position):
                        self._joint_pos[j] = msg.position[i]
                    if i < len(msg.velocity):
                        self._joint_vel[j] = msg.velocity[i]
            self._has_joint_state = True

    def _imu_callback(self, msg) -> None:
        with self._lock:
            o = msg.orientation
            av = msg.angular_velocity
            self._quat_wxyz = np.array([o.w, o.x, o.y, o.z], dtype=np.float32)
            self._ang_vel = np.array([av.x, av.y, av.z], dtype=np.float32)
            self._has_imu = True

    def get_state(self) -> dict[str, np.ndarray]:
        with self._lock:
            return {
                "joint_pos": self._joint_pos.copy(),
                "joint_vel": self._joint_vel.copy(),
                "ang_vel":   self._ang_vel.copy(),
                "quat_wxyz": self._quat_wxyz.copy(),
                "has_joint_state": self._has_joint_state,
                "has_imu": self._has_imu,
            }

    def send_torques(self, torques: np.ndarray) -> None:
        from std_msgs.msg import Float64MultiArray
        msg = Float64MultiArray()
        msg.data = torques.tolist()
        self._cmd_pub.publish(msg)

    def shutdown(self) -> None:
        import rclpy
        self._node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


class H1GazeboEnv:
    """
    OpenAI Gym-compatible H1 environment backed by Gazebo Harmonic.

    Requires:
        - ROS2 Humble + rclpy
        - Gazebo Harmonic with H1 model loaded
        - /joint_states and /imu/data topics active

    Raises ImportError if rclpy is not installed at instantiation time.

    Usage:
        env = H1GazeboEnv()
        obs = env.reset()
        obs, rew, done, info = env.step(env.action_space.sample())
        env.close()
    """

    def __init__(
        self,
        command_vel: tuple[float, float, float] = (0.5, 0.0, 0.0),
        max_episode_steps: int = 1000,
        obs_timeout_s: float = 5.0,
        control_hz: float = 50.0,
        seed: int = 0,
    ) -> None:
        if not _RCLPY_AVAILABLE:
            raise ImportError(
                "rclpy is required for H1GazeboEnv. "
                "Source ROS2 Humble: source /opt/ros/humble/setup.bash "
                "and ensure you are running in a ROS2-enabled Python environment."
            )

        self._cmd = np.array(command_vel, dtype=np.float32)
        self.max_episode_steps = max_episode_steps
        self._obs_timeout = obs_timeout_s
        self._control_dt = 1.0 / control_hz
        self._rng = np.random.default_rng(seed)
        self._step_count = 0
        self._last_action = _DEFAULT_JOINT_POS.copy()

        self._bridge = _ROSBridge()

        # Observation / action spaces (same as MuJoCo env)
        obs_high = np.full(_OBS_DIM, np.inf, dtype=np.float32)
        self.observation_space = spaces.Box(-obs_high, obs_high, dtype=np.float32)

        # Action bounds: target joint positions
        joint_limits_low  = np.array([-0.785, -0.523, -1.57, -0.087, -0.785,
                                       -0.785, -0.523, -1.57, -0.087, -0.785,
                                       -3.14, -1.57, -1.57, -1.57,
                                       -3.14, -1.57, -1.57, -1.57], dtype=np.float32)
        joint_limits_high = np.array([ 0.785,  0.523,  1.57,  2.443, 0.785,
                                        0.785,  0.523,  1.57,  2.443, 0.785,
                                        3.14,  1.57,  1.57,  1.57,
                                        3.14,  1.57,  1.57,  1.57], dtype=np.float32)
        self.action_space = spaces.Box(joint_limits_low, joint_limits_high, dtype=np.float32)

        # PD gains (same as MuJoCo env)
        self._kp = np.array([200, 200, 200, 300, 40, 200, 200, 200, 300, 40,
                              40, 40, 40, 10, 40, 40, 40, 10], dtype=np.float32)
        self._kd = np.array([5, 5, 5, 8, 1, 5, 5, 5, 8, 1,
                              1, 1, 1, 0.5, 1, 1, 1, 0.5], dtype=np.float32)

        self._wait_for_observation()

    # ── Public interface ──────────────────────────────────────────────────────

    def reset(self, seed: int | None = None, options: dict | None = None):
        if seed is not None:
            self._rng = np.random.default_rng(seed)

        # Send zero torques to stop motion
        self._bridge.send_torques(np.zeros(_N_JOINTS, dtype=np.float32))
        time.sleep(0.2)

        self._step_count = 0
        self._last_action = _DEFAULT_JOINT_POS.copy()

        obs = self._get_obs()
        if _GYM_VERSION == "gymnasium":
            return obs, {}
        return obs

    def step(self, action: np.ndarray):
        action = np.clip(action, self.action_space.low, self.action_space.high)

        # Get current state
        state = self._bridge.get_state()
        q  = state["joint_pos"]
        qd = state["joint_vel"]

        # PD torques
        torques = self._kp * (action - q) - self._kd * qd
        torque_limits = np.array([200, 200, 200, 300, 40, 200, 200, 200, 300, 40,
                                   40, 40, 40, 10, 40, 40, 40, 10], dtype=np.float32)
        torques = np.clip(torques, -torque_limits, torque_limits)
        self._bridge.send_torques(torques)

        # Wait one control step
        time.sleep(self._control_dt)

        self._step_count += 1
        self._last_action = action.copy()

        obs = self._get_obs()
        reward = self._compute_reward(action)
        terminated = self._is_terminated()
        truncated = self._step_count >= self.max_episode_steps
        info = self._get_info(state)

        if _GYM_VERSION == "gymnasium":
            return obs, reward, terminated, truncated, info
        return obs, reward, (terminated or truncated), info

    def close(self) -> None:
        if hasattr(self, "_bridge"):
            self._bridge.shutdown()

    # ── Internals ─────────────────────────────────────────────────────────────

    def _wait_for_observation(self) -> None:
        deadline = time.time() + self._obs_timeout
        while time.time() < deadline:
            state = self._bridge.get_state()
            if state["has_joint_state"] and state["has_imu"]:
                return
            time.sleep(0.05)
        raise TimeoutError(
            f"No observation received within {self._obs_timeout}s. "
            "Is Gazebo running? Check: ros2 topic echo /joint_states"
        )

    def _get_obs(self) -> np.ndarray:
        state = self._bridge.get_state()
        q_rel = state["joint_pos"] - _DEFAULT_JOINT_POS
        grav = self._project_gravity(state["quat_wxyz"])
        obs = np.concatenate([
            state["ang_vel"],   # 3
            grav,               # 3
            self._cmd,          # 3
            q_rel,              # 18
            state["joint_vel"], # 18
        ]).astype(np.float32)
        return obs

    def _project_gravity(self, quat_wxyz: np.ndarray) -> np.ndarray:
        w, x, y, z = quat_wxyz
        grav_world = np.array([0.0, 0.0, -1.0])
        qvec = np.array([x, y, z])
        t = 2.0 * np.cross(qvec, grav_world)
        return (grav_world + w * t + np.cross(qvec, t)).astype(np.float32)

    def _compute_reward(self, action: np.ndarray) -> float:
        state = self._bridge.get_state()
        q  = state["joint_pos"]
        qd = state["joint_vel"]
        torques = self._kp * (action - q) - self._kd * qd

        # Gravity from IMU
        grav = self._project_gravity(state["quat_wxyz"])
        upright = float(grav[2])  # -1 = upright, approaches 0 if tilting

        action_rate = -float(np.sum((action - self._last_action) ** 2)) * 0.01
        energy = -float(np.sum(np.abs(torques * qd))) * 2.5e-5

        return float(
            2.0 * upright
            + action_rate
            + energy
            + 0.5  # alive
        )

    def _is_terminated(self) -> bool:
        state = self._bridge.get_state()
        grav = self._project_gravity(state["quat_wxyz"])
        tilt = np.arccos(np.clip(-grav[2], -1.0, 1.0))
        return float(tilt) > 0.8

    def _get_info(self, state: dict) -> dict[str, Any]:
        return {
            "joint_pos": state["joint_pos"].copy(),
            "joint_vel": state["joint_vel"].copy(),
            "ang_vel": state["ang_vel"].copy(),
            "step": self._step_count,
        }

    # ── Context manager ───────────────────────────────────────────────────────

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
