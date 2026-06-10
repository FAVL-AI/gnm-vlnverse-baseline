"""
H1 Hardware Bringup Launch — Fleet-Safe-VLA-OS.

Launches the fleet-safe stack on real H1 hardware:
  - robot_state_publisher (from URDF on disk)
  - H1 actuator driver node (via Unitree SDK bridge)
  - IMU driver node
  - FleetSafe deployment node (policy + safety stack)
  - Fleet risk monitor
  - Web viewer for remote monitoring

SAFETY NOTICE:
  This launch file enables real robot control.
  Ensure the emergency stop is accessible before launching.
  The safety filter starts in RAMPING_UP state and takes ~1s to engage.

Prerequisites:
    - source /opt/ros/humble/setup.bash
    - conda activate isaac
    - Unitree H1 powered on and connected via Ethernet
    - Policy ONNX file at $POLICY_PATH (set env var)

Usage:
    POLICY_PATH=deployed/h1_policy.onnx \\
    ros2 launch fleet_safe_bringup h1_hardware.launch.py
"""
import os
from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo, TimerAction
from launch.substitutions import LaunchConfiguration, EnvironmentVariable
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


_PKG_DESCRIPTION = FindPackageShare("fleet_safe_description")


def generate_launch_description() -> LaunchDescription:
    args = [
        DeclareLaunchArgument("policy_path",
                              default_value=EnvironmentVariable("POLICY_PATH",
                                                               default_value=""),
                              description="Path to ONNX policy file"),
        DeclareLaunchArgument("robot_id", default_value="0",
                              description="Robot ID for fleet monitoring"),
        DeclareLaunchArgument("cmd_vel_x", default_value="0.0",
                              description="Initial forward velocity command (m/s)"),
        DeclareLaunchArgument("latency_ms", default_value="20.0",
                              description="Expected actuator latency (ms)"),
        DeclareLaunchArgument("use_web_viewer", default_value="true",
                              description="Start web viewer on port 8080"),
    ]

    policy_path    = LaunchConfiguration("policy_path")
    robot_id       = LaunchConfiguration("robot_id")
    use_web_viewer = LaunchConfiguration("use_web_viewer")

    # Robot state publisher
    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        name="robot_state_publisher",
        parameters=[{"use_sim_time": False}],
        output="screen",
    )

    # Safety status publisher (standalone monitor)
    safety_monitor = Node(
        package="fleet_safe_control",
        executable="safety_monitor",
        name="safety_monitor",
        output="screen",
        parameters=[{
            "robot_id": robot_id,
            "max_tilt_rad": 0.8,
            "min_base_height_m": 0.5,
        }],
    )

    # FleetSafe deployment node
    deploy_node = TimerAction(
        period=2.0,
        actions=[Node(
            package="fleet_safe_control",
            executable="deploy_node",
            name="fleet_safe_deploy",
            output="screen",
            parameters=[{
                "policy_path": policy_path,
                "robot_id": robot_id,
                "latency_ms": LaunchConfiguration("latency_ms"),
            }],
        )],
    )

    return LaunchDescription(
        args + [
            LogInfo(msg="[fleet_safe_bringup] H1 HARDWARE bringup — check e-stop!"),
            robot_state_publisher,
            safety_monitor,
            deploy_node,
        ]
    )
