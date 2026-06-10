"""
FleetSafe ROS2 Deployment Node — Fleet-Safe-VLA-OS.

Extends robot-lab's deploy_ros2.py with fleet safety stack:
  - CBF safety filter in the control loop
  - Fleet risk monitor integration
  - Safety status publishing to /fleet_safe/safety_status
  - ONNX policy inference at 50 Hz

Architecture:
    /joint_states  ──→  StateEstimator  ──→  obs (45-dim)  ──→  Policy
    /imu/data      ──┘                                          ↓ u_nom
                                                         CBFFilter
                                                              ↓ u_safe
                                                       SafetyFilter
                                                              ↓ u_final
                   /joint_group_effort_controller/commands  ←──┘
                   /fleet_safe/safety_status  ←── FleetRiskMonitor

Usage:
    source /opt/ros/humble/setup.bash
    conda activate isaac
    python -m fleet_safe_vla.sim2real.deployment.ros2_node \\
        --policy=deployed/h1_policy.onnx \\
        --robot_id=0

Requires: rclpy, onnxruntime, robot-lab
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np

# robot-lab components
from robot_lab.sim2real.safety_filter import SafetyFilter, SafetyConfig
from robot_lab.sim2real.latency_compensation import LatencyCompensator
from robot_lab.sim2real.state_estimator import StateEstimator, StateEstimatorConfig

# fleet-safe components
from fleet_safe_vla.fleet_safety.cbf_filter import CBFSafetyFilter, CBFConfig
from fleet_safe_vla.fleet_safety.risk_monitor import FleetRiskMonitor

_DEFAULT_JOINT_POS = np.array([
    0., 0., -0.4, 0.8, -0.4,
    0., 0., -0.4, 0.8, -0.4,
    0., 0., 0., 0.,
    0., 0., 0., 0.,
], dtype=np.float32)

JOINT_NAMES = [
    "left_hip_yaw", "left_hip_roll", "left_hip_pitch", "left_knee", "left_ankle",
    "right_hip_yaw", "right_hip_roll", "right_hip_pitch", "right_knee", "right_ankle",
    "left_shoulder_pitch", "left_shoulder_roll", "left_elbow", "left_wrist",
    "right_shoulder_pitch", "right_shoulder_roll", "right_elbow", "right_wrist",
]

_N_JOINTS = 18


class FleetSafeDeployNode:
    """
    ROS2 node that runs the full FleetSafe control loop on the H1 robot.

    The node subscribes to sensor topics, runs the policy at 50 Hz,
    applies the safety stack, and publishes torque commands.

    Requires rclpy at instantiation time.
    """

    def __init__(
        self,
        policy_path: str | Path,
        robot_id: int = 0,
        cmd_vel: tuple[float, float, float] = (0.5, 0.0, 0.0),
        control_hz: float = 50.0,
        latency_ms: float = 20.0,
    ) -> None:
        try:
            import rclpy
        except ImportError:
            raise ImportError(
                "rclpy is required. Run: source /opt/ros/humble/setup.bash"
            )

        import rclpy
        from rclpy.node import Node
        from sensor_msgs.msg import JointState, Imu
        from std_msgs.msg import Float64MultiArray
        from builtin_interfaces.msg import Time

        rclpy.init(args=None)
        self._node = Node(f"fleet_safe_deploy_{robot_id}")
        self._robot_id = robot_id
        self._cmd_vel = np.array(cmd_vel, dtype=np.float32)
        self._control_dt = 1.0 / control_hz

        # State
        self._joint_pos = np.zeros(_N_JOINTS, dtype=np.float32)
        self._joint_vel = np.zeros(_N_JOINTS, dtype=np.float32)
        self._imu_quat  = np.array([0., 0., 0., 1.], dtype=np.float32)
        self._imu_gyro  = np.zeros(3, dtype=np.float32)
        self._last_action = _DEFAULT_JOINT_POS.copy()

        # Safety stack
        self._state_estimator = StateEstimator(StateEstimatorConfig(alpha=0.98))
        self._latency_comp = LatencyCompensator(latency_ms=latency_ms)
        self._cbf = CBFSafetyFilter(CBFConfig(max_tilt_rad=0.7, gamma=1.0))
        self._safety_filter = SafetyFilter(SafetyConfig(max_tilt_rad=0.8))
        self._risk_monitor = FleetRiskMonitor(n_robots=1)

        # Policy
        self._policy = self._load_policy(policy_path)

        # ROS2 subscriptions and publishers
        self._js_sub = self._node.create_subscription(
            JointState, "/joint_states", self._js_callback, 10
        )
        self._imu_sub = self._node.create_subscription(
            Imu, "/imu/data", self._imu_callback, 10
        )
        self._cmd_pub = self._node.create_publisher(
            Float64MultiArray,
            "/joint_group_effort_controller/commands",
            10,
        )

        # Import and setup safety status publisher
        try:
            from fleet_safe_msgs.msg import SafetyStatus  # noqa: F401
            self._safety_pub = self._node.create_publisher(
                SafetyStatus,
                "/fleet_safe/safety_status",
                10,
            )
            self._has_safety_msg = True
        except ImportError:
            self._safety_pub = None
            self._has_safety_msg = False

        # Control timer
        self._timer = self._node.create_timer(
            self._control_dt, self._control_callback
        )

        self._node.get_logger().info(
            f"FleetSafeDeployNode started: robot_id={robot_id}, "
            f"policy={policy_path}"
        )

    def _load_policy(self, policy_path: str | Path):
        """Load ONNX policy for inference."""
        try:
            import onnxruntime as ort
            sess = ort.InferenceSession(
                str(policy_path),
                providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
            )
            self._node.get_logger().info(f"Loaded ONNX policy from {policy_path}")
            return sess
        except ImportError:
            self._node.get_logger().warn("onnxruntime not found — using zero policy")
            return None
        except Exception as e:
            self._node.get_logger().error(f"Failed to load policy: {e}")
            return None

    def _js_callback(self, msg) -> None:
        name_to_idx = {n: i for i, n in enumerate(JOINT_NAMES)}
        for i, name in enumerate(msg.name):
            if name in name_to_idx:
                j = name_to_idx[name]
                if i < len(msg.position):
                    self._joint_pos[j] = msg.position[i]
                if i < len(msg.velocity):
                    self._joint_vel[j] = msg.velocity[i]

    def _imu_callback(self, msg) -> None:
        o = msg.orientation
        av = msg.angular_velocity
        self._imu_quat = np.array([o.x, o.y, o.z, o.w], dtype=np.float32)
        self._imu_gyro = np.array([av.x, av.y, av.z], dtype=np.float32)

    def _control_callback(self) -> None:
        """Main 50 Hz control loop."""
        # 1. State estimation
        est = self._state_estimator.update(
            imu_quat=self._imu_quat,
            imu_gyro=self._imu_gyro,
            joint_pos=self._joint_pos,
        )
        proj_grav = est["proj_gravity"]
        ang_vel   = est["base_ang_vel"]
        base_height = float(est["base_height"])

        # 2. Latency compensation
        pred_pos, pred_vel = self._latency_comp.predict_state(
            self._joint_pos, self._joint_vel
        )

        # 3. Build observation
        q_rel = pred_pos - _DEFAULT_JOINT_POS
        obs = np.concatenate([ang_vel, proj_grav, self._cmd_vel, q_rel, pred_vel])
        obs = obs.astype(np.float32)

        # 4. Policy inference
        if self._policy is not None:
            input_name = self._policy.get_inputs()[0].name
            u_nom = self._policy.run(None, {input_name: obs[np.newaxis]})[0][0]
        else:
            u_nom = _DEFAULT_JOINT_POS.copy()

        # 5. CBF filter
        safe_action, cbf_info = self._cbf.filter_action(obs, u_nom)

        # 6. Low-level safety filter
        tilt = float(np.arccos(np.clip(-proj_grav[2], -1.0, 1.0)))
        final_action = self._safety_filter.filter(
            raw_actions=safe_action,
            joint_pos=self._joint_pos,
            joint_vel=self._joint_vel,
            base_tilt=tilt,
            base_height=base_height,
        )

        # 7. PD torque computation
        kp = np.array([200, 200, 200, 300, 40, 200, 200, 200, 300, 40,
                        40,  40,  40,  10,  40,  40,  40,  10], dtype=np.float32)
        kd = np.array([5, 5, 5, 8, 1, 5, 5, 5, 8, 1,
                        1, 1, 1, 0.5, 1, 1, 1, 0.5], dtype=np.float32)
        torques = kp * (final_action - self._joint_pos) - kd * self._joint_vel
        torque_limits = np.array([200, 200, 200, 300, 40, 200, 200, 200, 300, 40,
                                   40, 40, 40, 10, 40, 40, 40, 10], dtype=np.float32)
        torques = np.clip(torques, -torque_limits, torque_limits)

        # 8. Publish torques
        from std_msgs.msg import Float64MultiArray
        msg = Float64MultiArray()
        msg.data = torques.tolist()
        self._cmd_pub.publish(msg)

        # 9. Risk monitor update
        self._risk_monitor.update_robot(
            robot_id=self._robot_id,
            obs=obs,
            cbf_info=cbf_info,
            raw_actions=u_nom,
            joint_pos=self._joint_pos,
            joint_vel=self._joint_vel,
        )
        self._risk_monitor.update_base_height(self._robot_id, base_height)

        # 10. Publish safety status
        if self._has_safety_msg and self._safety_pub is not None:
            self._publish_safety_status(tilt, base_height, cbf_info)

        self._last_action = final_action.copy()

    def _publish_safety_status(
        self,
        tilt_rad: float,
        height_m: float,
        cbf_info: dict,
    ) -> None:
        try:
            from fleet_safe_msgs.msg import SafetyStatus
            from std_msgs.msg import Header
            import builtin_interfaces.msg as bi

            msg = SafetyStatus()
            msg.header = Header()
            msg.header.stamp = self._node.get_clock().now().to_msg()
            msg.state = self._safety_filter.state.name
            msg.base_tilt_rad = float(tilt_rad)
            msg.base_height_m = float(height_m)
            msg.is_safe = bool(self._safety_filter.is_safe)
            msg.last_trigger = "cbf_intervened" if cbf_info.get("intervened") else ""
            self._safety_pub.publish(msg)
        except Exception:
            pass

    def spin(self) -> None:
        """Run the node until interrupted."""
        import rclpy
        try:
            rclpy.spin(self._node)
        except KeyboardInterrupt:
            pass
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        import rclpy
        self._node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description="FleetSafe ROS2 deployment node")
    parser.add_argument("--policy", type=str, required=True, help="Path to ONNX policy")
    parser.add_argument("--robot_id", type=int, default=0)
    parser.add_argument("--cmd_vel", type=float, nargs=3, default=[0.5, 0.0, 0.0])
    parser.add_argument("--latency_ms", type=float, default=20.0)
    args = parser.parse_args()

    node = FleetSafeDeployNode(
        policy_path=args.policy,
        robot_id=args.robot_id,
        cmd_vel=tuple(args.cmd_vel),
        latency_ms=args.latency_ms,
    )
    node.spin()


if __name__ == "__main__":
    main()
