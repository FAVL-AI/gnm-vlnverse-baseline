"""
H1 Gazebo Harmonic Bringup Launch File — Fleet-Safe-VLA-OS.

Launches:
  - Gazebo Harmonic (gz_sim) with H1 model
  - robot_state_publisher
  - ros2_control_node with effort joint interface
  - joint_state_broadcaster
  - Command bridge for /cmd_vel → Gazebo ApplyBodyWrench

Prerequisites:
    - ROS2 Humble installed at /opt/ros/humble
    - Gazebo Harmonic: sudo apt install ros-humble-ros-gz*
    - xacro: sudo apt install ros-humble-xacro

Usage:
    source /opt/ros/humble/setup.bash
    ros2 launch fleet_safe_bringup h1_gazebo.launch.py
    # Optional params:
    ros2 launch fleet_safe_bringup h1_gazebo.launch.py use_sim_time:=true world:=empty
"""
from pathlib import Path

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    IncludeLaunchDescription,
    LogInfo,
    TimerAction,
)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import (
    Command,
    FindExecutable,
    LaunchConfiguration,
    PathJoinSubstitution,
)
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


# ── Package paths ─────────────────────────────────────────────────────────────
_PKG_BRINGUP     = FindPackageShare("fleet_safe_bringup")
_PKG_DESCRIPTION = FindPackageShare("fleet_safe_description")
_PKG_CONTROL     = FindPackageShare("fleet_safe_control")


def generate_launch_description() -> LaunchDescription:
    """Generate the full H1 Gazebo launch description."""

    # ── Declare launch arguments ──────────────────────────────────────────────
    args = [
        DeclareLaunchArgument("use_sim_time", default_value="true",
                              description="Use Gazebo simulation time"),
        DeclareLaunchArgument("world", default_value="empty",
                              description="Gazebo world name (empty | rough_terrain)"),
        DeclareLaunchArgument("robot_name", default_value="h1",
                              description="Robot model name in Gazebo"),
        DeclareLaunchArgument("x_pose", default_value="0.0"),
        DeclareLaunchArgument("y_pose", default_value="0.0"),
        DeclareLaunchArgument("z_pose", default_value="1.05"),
        DeclareLaunchArgument("gui", default_value="true",
                              description="Launch Gazebo with GUI"),
        DeclareLaunchArgument("rviz", default_value="false",
                              description="Launch RViz2"),
    ]

    use_sim_time = LaunchConfiguration("use_sim_time")
    world        = LaunchConfiguration("world")
    robot_name   = LaunchConfiguration("robot_name")
    gui          = LaunchConfiguration("gui")

    # ── URDF / robot description ──────────────────────────────────────────────
    urdf_xacro = PathJoinSubstitution([
        _PKG_DESCRIPTION, "urdf", "h1.urdf.xacro"
    ])
    robot_description = Command([
        FindExecutable(name="xacro"), " ",
        urdf_xacro,
        " use_sim:=true",
        " robot_name:=", robot_name,
    ])

    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        name="robot_state_publisher",
        output="screen",
        parameters=[{
            "robot_description": robot_description,
            "use_sim_time": use_sim_time,
        }],
    )

    # ── Gazebo Harmonic ────────────────────────────────────────────────────────
    gz_sim = ExecuteProcess(
        cmd=[
            "gz", "sim", "--verbose", "0",
            "-r",  # run on start
            PathJoinSubstitution([_PKG_BRINGUP, "worlds", world]),
        ],
        output="screen",
    )

    # Spawn H1 into Gazebo
    spawn_robot = Node(
        package="ros_gz_sim",
        executable="create",
        arguments=[
            "-name",  robot_name,
            "-topic", "/robot_description",
            "-x",     LaunchConfiguration("x_pose"),
            "-y",     LaunchConfiguration("y_pose"),
            "-z",     LaunchConfiguration("z_pose"),
        ],
        output="screen",
    )

    # ── ros2_control ──────────────────────────────────────────────────────────
    control_config = PathJoinSubstitution([
        _PKG_CONTROL, "config", "h1_controllers.yaml"
    ])
    ros2_control_node = Node(
        package="controller_manager",
        executable="ros2_control_node",
        parameters=[
            {"robot_description": robot_description},
            control_config,
            {"use_sim_time": use_sim_time},
        ],
        output="screen",
    )

    # Spawner nodes (with delay to allow controller_manager to start)
    joint_state_broadcaster = TimerAction(
        period=3.0,
        actions=[Node(
            package="controller_manager",
            executable="spawner",
            arguments=["joint_state_broadcaster"],
            output="screen",
        )],
    )
    effort_controller = TimerAction(
        period=4.0,
        actions=[Node(
            package="controller_manager",
            executable="spawner",
            arguments=["joint_group_effort_controller"],
            output="screen",
        )],
    )

    # ── Gazebo ↔ ROS2 bridge ──────────────────────────────────────────────────
    gz_ros_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        arguments=[
            "/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock",
            "/joint_states@sensor_msgs/msg/JointState[gz.msgs.Model",
            "/imu/data@sensor_msgs/msg/Imu[gz.msgs.IMU",
            "/cmd_vel@geometry_msgs/msg/Twist]gz.msgs.Twist",
        ],
        output="screen",
    )

    # ── RViz2 (optional) ──────────────────────────────────────────────────────
    rviz_node = Node(
        package="rviz2",
        executable="rviz2",
        name="rviz2",
        condition=IfCondition(LaunchConfiguration("rviz")),
        output="screen",
    )

    # ── Fleet-Safe deployment node ────────────────────────────────────────────
    # Launches in demo mode if policy file not found
    fleet_safe_node = TimerAction(
        period=6.0,
        actions=[LogInfo(msg="FleetSafe control node: start manually when ready")],
    )

    return LaunchDescription(
        args + [
            LogInfo(msg="[fleet_safe_bringup] Launching H1 in Gazebo Harmonic"),
            robot_state_publisher,
            gz_sim,
            gz_ros_bridge,
            TimerAction(period=2.0, actions=[spawn_robot]),
            ros2_control_node,
            joint_state_broadcaster,
            effort_controller,
            rviz_node,
            fleet_safe_node,
        ]
    )
