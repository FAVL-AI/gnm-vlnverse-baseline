"""
m3pro_gazebo.launch.py — Yahboom M3Pro in Gazebo Harmonic.

Launches:
  - Gazebo Harmonic (gz sim) with hospital_corridor.sdf world
  - robot_state_publisher with M3Pro URDF (sim mode: diff-drive plugin)
  - ros_gz_bridge for clock / cmd_vel / odom / tf / scan / camera / imu
  - Joint state bridge
  - (Optional) RViz2

Prerequisites:
    sudo apt install ros-humble-ros-gz ros-humble-xacro

Usage:
    source /opt/ros/humble/setup.bash
    source ~/robotics/FleetSafe-VisualNav-Benchmark/ros2_ws/install/setup.bash
    ros2 launch fleet_safe_bringup m3pro_gazebo.launch.py

    # Custom world or spawn pose:
    ros2 launch fleet_safe_bringup m3pro_gazebo.launch.py world:=hospital_corridor x:=0.0 y:=0.0
    ros2 launch fleet_safe_bringup m3pro_gazebo.launch.py gui:=false   # headless

    # Teleoperate (in another terminal):
    ros2 run teleop_twist_keyboard teleop_twist_keyboard

    # Record dataset bag:
    ros2 bag record /camera/image_raw /odom /cmd_vel -o recordings/hospital_run_01

    # Build topomap from bag:
    python scripts/visualnav/build_topomap.py --from-bag recordings/hospital_run_01 --name hospital_01
"""
from pathlib import Path

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    LogInfo,
    TimerAction,
)
from launch.conditions import IfCondition
from launch.substitutions import (
    Command,
    FindExecutable,
    LaunchConfiguration,
    PathJoinSubstitution,
)
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


_PKG_BRINGUP     = FindPackageShare("fleet_safe_bringup")
_PKG_DESCRIPTION = FindPackageShare("fleet_safe_description")


def generate_launch_description() -> LaunchDescription:

    # ── Arguments ─────────────────────────────────────────────────────────────
    args = [
        DeclareLaunchArgument(
            "world", default_value="hospital_corridor",
            description="World name (without .sdf) in fleet_safe_bringup/worlds/"),
        DeclareLaunchArgument(
            "robot_name", default_value="m3pro",
            description="Gazebo model name"),
        DeclareLaunchArgument("use_sim_time", default_value="true"),
        DeclareLaunchArgument("x",   default_value="0.0",  description="Spawn X"),
        DeclareLaunchArgument("y",   default_value="0.0",  description="Spawn Y"),
        DeclareLaunchArgument("z",   default_value="0.10", description="Spawn Z"),
        DeclareLaunchArgument("yaw", default_value="0.0",  description="Spawn yaw (rad)"),
        DeclareLaunchArgument(
            "gui", default_value="true",
            description="Launch Gazebo with GUI (false = headless for benchmark)"),
        DeclareLaunchArgument(
            "rviz", default_value="false",
            description="Launch RViz2 alongside Gazebo"),
    ]

    use_sim_time = LaunchConfiguration("use_sim_time")
    world        = LaunchConfiguration("world")
    robot_name   = LaunchConfiguration("robot_name")

    # ── Robot description (xacro with sim=true → adds Gazebo plugins) ─────────
    urdf_xacro = PathJoinSubstitution([
        _PKG_DESCRIPTION, "urdf", "yahboom_m3pro.urdf.xacro",
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
            "use_sim_time":      use_sim_time,
        }],
    )

    # ── Gazebo Harmonic ────────────────────────────────────────────────────────
    world_sdf = PathJoinSubstitution([_PKG_BRINGUP, "worlds", world])

    gz_sim = ExecuteProcess(
        cmd=[
            "gz", "sim", "--verbose", "0",
            "-r",          # auto-run on start
            world_sdf,
        ],
        additional_env={"GZ_SIM_RESOURCE_PATH": ""},
        output="screen",
    )

    # Spawn M3Pro into the running Gazebo instance (delay 3 s for gz to load)
    spawn_robot = TimerAction(
        period=3.0,
        actions=[Node(
            package="ros_gz_sim",
            executable="create",
            arguments=[
                "-name",  robot_name,
                "-topic", "/robot_description",
                "-x",     LaunchConfiguration("x"),
                "-y",     LaunchConfiguration("y"),
                "-z",     LaunchConfiguration("z"),
                "-Y",     LaunchConfiguration("yaw"),
            ],
            output="screen",
        )],
    )

    # ── Gazebo ↔ ROS2 bridge ──────────────────────────────────────────────────
    # Format: <gz_topic>@<ros_type>[<gz_type>  ([ = Gazebo→ROS, ] = ROS→Gazebo)
    gz_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        name="gz_bridge",
        arguments=[
            # Simulation clock (required for use_sim_time to work)
            "/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock",
            # Drive command (ROS → Gazebo)
            "/cmd_vel@geometry_msgs/msg/Twist]gz.msgs.Twist",
            # Odometry (Gazebo → ROS)
            "/odom@nav_msgs/msg/Odometry[gz.msgs.Odometry",
            # TF from diff-drive plugin
            "/tf@tf2_msgs/msg/TFMessage[gz.msgs.Pose_V",
            # Joint states
            "/joint_states@sensor_msgs/msg/JointState[gz.msgs.Model",
            # LiDAR (Gazebo → ROS)
            "/scan@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan",
            # Camera image (Gazebo → ROS)
            "/camera/image_raw@sensor_msgs/msg/Image[gz.msgs.Image",
            # Camera info
            "/camera/camera_info@sensor_msgs/msg/CameraInfo[gz.msgs.CameraInfo",
            # IMU
            "/imu/data@sensor_msgs/msg/Imu[gz.msgs.IMU",
        ],
        remappings=[
            # odom → also available on /odom for nav stack
        ],
        output="screen",
    )

    # ── (Optional) RViz2 ──────────────────────────────────────────────────────
    rviz_node = Node(
        package="rviz2",
        executable="rviz2",
        name="rviz2",
        condition=IfCondition(LaunchConfiguration("rviz")),
        arguments=["-d", PathJoinSubstitution([_PKG_BRINGUP, "config", "m3pro_nav.rviz"])],
        parameters=[{"use_sim_time": use_sim_time}],
        output="screen",
    )

    return LaunchDescription(
        args + [
            LogInfo(msg=[
                "[FleetSafe] Launching M3Pro in Gazebo Harmonic | world=", world,
                " | gui=", LaunchConfiguration("gui"),
            ]),
            robot_state_publisher,
            gz_sim,
            gz_bridge,
            spawn_robot,
            rviz_node,
            TimerAction(period=5.0, actions=[LogInfo(msg=(
                "[FleetSafe] M3Pro ready.\n"
                "  Drive: ros2 run teleop_twist_keyboard teleop_twist_keyboard\n"
                "  Record: ros2 bag record /camera/image_raw /odom /cmd_vel "
                "-o recordings/hospital_run_01\n"
                "  Benchmark: make benchmark-ros2"
            ))]),
        ]
    )
