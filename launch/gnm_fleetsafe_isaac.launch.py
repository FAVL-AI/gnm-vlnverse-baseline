"""ROS 2 launch file for the FleetSafe-GNM Isaac Sim pipeline.

Starts four groups of nodes:
  1. Isaac bridge — NVIDIA ROS 2 bridge publishing sensor topics from Isaac Sim.
  2. GNM policy node — reads camera and goal, publishes raw velocity command.
  3. FleetSafe shield node — checks raw command, publishes safe command.
  4. Logger / dashboard (optional) — records structured episode log.

This file is safe to import in non-ROS CI environments: it guards all
ros2 launch imports and exits gracefully if they are not available.

TODOs before live use:
  - Replace 'TODO_isaac_ros_bridge' with the actual Isaac ROS 2 bridge package name.
  - Replace 'TODO_gnm_ros_node' with the actual GNM policy node package and executable.
  - Replace 'TODO_fleetsafe_ros_node' with the actual FleetSafe shield node package.
  - Set correct parameter file paths for each node.
  - Verify topic remappings match configs/gnm_fleetsafe_isaac.yaml.
"""

import sys

try:
    from launch import LaunchDescription
    from launch.actions import DeclareLaunchArgument, LogInfo
    from launch.substitutions import LaunchConfiguration
    from launch_ros.actions import Node
    _ROS2_AVAILABLE = True
except ImportError:
    _ROS2_AVAILABLE = False


def generate_launch_description():
    if not _ROS2_AVAILABLE:
        print(
            "[gnm_fleetsafe_isaac.launch.py] ROS 2 launch packages not available.\n"
            "  This file requires a ROS 2 installation with launch_ros.\n"
            "  In CI/offline mode this file is imported but not executed.",
            file=sys.stderr,
        )
        return None

    config_arg = DeclareLaunchArgument(
        "config",
        default_value="configs/gnm_fleetsafe_isaac.yaml",
        description="Path to gnm_fleetsafe_isaac.yaml config file.",
    )

    dry_run_arg = DeclareLaunchArgument(
        "dry_run",
        default_value="true",
        description="If true, nodes log expected behaviour without live computation.",
    )

    config_path = LaunchConfiguration("config")

    isaac_bridge_node = Node(
        package="TODO_isaac_ros_bridge",
        executable="isaac_ros_bridge_node",
        name="isaac_bridge",
        parameters=[config_path],
        remappings=[
            ("camera/image_raw", "/camera/image_raw"),
            ("odom", "/odom"),
            ("scan", "/scan"),
            ("cmd_vel", "/cmd_vel"),
        ],
        output="screen",
    )

    gnm_policy_node = Node(
        package="TODO_gnm_ros_node",
        executable="gnm_policy_node",
        name="gnm_policy",
        parameters=[config_path],
        remappings=[
            ("camera/image_raw", "/camera/image_raw"),
            ("odom", "/odom"),
            ("cmd_vel_raw", "/gnm/cmd_vel_raw"),
        ],
        output="screen",
    )

    fleetsafe_shield_node = Node(
        package="TODO_fleetsafe_ros_node",
        executable="fleetsafe_shield_node",
        name="fleetsafe_shield",
        parameters=[config_path],
        remappings=[
            ("cmd_vel_raw", "/gnm/cmd_vel_raw"),
            ("scan", "/scan"),
            ("odom", "/odom"),
            ("cmd_vel_safe", "/fleetsafe/cmd_vel_safe"),
            ("cmd_vel", "/cmd_vel"),
        ],
        output="screen",
    )

    logger_node = Node(
        package="TODO_gnm_ros_node",
        executable="episode_logger_node",
        name="episode_logger",
        parameters=[config_path],
        remappings=[
            ("camera/image_raw", "/camera/image_raw"),
            ("odom", "/odom"),
            ("scan", "/scan"),
            ("gnm_cmd_vel_raw", "/gnm/cmd_vel_raw"),
            ("fleetsafe_cmd_vel_safe", "/fleetsafe/cmd_vel_safe"),
            ("cmd_vel", "/cmd_vel"),
        ],
        output="screen",
    )

    return LaunchDescription([
        config_arg,
        dry_run_arg,
        LogInfo(msg="Starting FleetSafe-GNM Isaac ROS 2 pipeline."),
        LogInfo(msg=["Config: ", config_path]),
        isaac_bridge_node,
        gnm_policy_node,
        fleetsafe_shield_node,
        logger_node,
    ])
