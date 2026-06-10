"""
ROS2 launch file for the real Yahboom RosMaster robot (X3 or M3Pro).

Launches:
  - robot_state_publisher (URDF)
  - Fleet-Safe safety policy node
  - Fleet-Safe episode runner

Usage:
  ros2 launch fleet_safe_yahboom_bringup real_robot.launch.py
  ros2 launch fleet_safe_yahboom_bringup real_robot.launch.py robot:=m3pro
  ros2 launch fleet_safe_yahboom_bringup real_robot.launch.py use_sim_time:=false record:=true

Robot IP:
  Prefer ASK4/LAN DHCP address.
  192.168.8.88 is the hotspot/AP fallback — only use with --hotspot flag
  in the discovery/SSH scripts, not here.

ROS_DOMAIN_ID:
  Must match the robot's ROS_DOMAIN_ID.  Default: 0.
  export ROS_DOMAIN_ID=5 before launching if the robot uses a different ID.
"""
from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

_REPO_ROOT = Path(__file__).parents[4]
_URDF_X3   = _REPO_ROOT / "fleet_safe_vla/robots/yahboom/urdf/yahboom_x3.urdf"
_URDF_M3PRO= _REPO_ROOT / "fleet_safe_vla/robots/yahboom/urdf/yahboom_m3pro.urdf"


def _urdf_for_robot(robot: str) -> str:
    if robot == "m3pro":
        if not _URDF_M3PRO.exists():
            print(
                f"\n[ERROR] M3Pro URDF not found: {_URDF_M3PRO}\n"
                "  See: fleet_safe_vla/robots/yahboom/config/robot_contract_m3pro.yaml\n"
            )
            return ""
        return _URDF_M3PRO.read_text()
    if _URDF_X3.exists():
        return _URDF_X3.read_text()
    return ""


def generate_launch_description():
    robot_arg = DeclareLaunchArgument(
        "robot", default_value="m3pro",
        description="Robot model: x3 | m3pro  (default: m3pro — actual hardware)",
    )

    # Evaluate robot type at generate time (not at launch time) for URDF loading
    # LaunchConfiguration is a string, so we pass it as a Python-evaluated param
    import sys
    _robot = "m3pro"  # default; overridden by CLI at runtime via the arg above
    # Note: full runtime substitution for URDF text requires OpaqueFunction;
    # for simplicity we load both and let robot_state_publisher pick via param.

    return LaunchDescription([
        robot_arg,
        DeclareLaunchArgument("use_sim_time", default_value="false"),
        DeclareLaunchArgument("record",       default_value="false"),
        DeclareLaunchArgument("policy",       default_value=""),
        DeclareLaunchArgument("serial_port",  default_value="/dev/yahboom"),

        LogInfo(msg=[
            "Launching Fleet-Safe Yahboom bringup | robot=",
            LaunchConfiguration("robot"),
            " | use_sim_time=",
            LaunchConfiguration("use_sim_time"),
        ]),

        # Robot state publisher — use M3Pro URDF if available, else X3
        Node(
            package="robot_state_publisher",
            executable="robot_state_publisher",
            name="robot_state_publisher",
            parameters=[{
                "robot_description": (
                    _URDF_M3PRO.read_text() if _URDF_M3PRO.exists()
                    else _URDF_X3.read_text() if _URDF_X3.exists()
                    else ""
                ),
                "use_sim_time": LaunchConfiguration("use_sim_time"),
            }],
        ),

        # Fleet-Safe safety node (filters /cmd_vel before hardware)
        # M3Pro: safety limits from robot_contract_m3pro.yaml
        Node(
            package="fleet_safe_safety_policy",
            executable="safety_node",
            name="fleet_safe_safety",
            parameters=[{
                "max_linear_ms":   0.5,   # m/s  (hard limit per contract)
                "max_angular_rs":  1.0,   # rad/s
                "d_safe_m":        0.30,  # obstacle clearance
                "estop_dist_m":    0.15,  # emergency stop distance
            }],
            remappings=[
                ("/cmd_vel_raw",   "/cmd_vel_nominal"),
                ("/cmd_vel",       "/cmd_vel"),
                ("/scan",          "/scan"),
            ],
        ),

        # Episode runner
        Node(
            package="fleet_safe_episode_runner",
            executable="episode_runner",
            name="fleet_safe_runner",
            parameters=[{
                "policy":     LaunchConfiguration("policy"),
                "record":     LaunchConfiguration("record"),
                "output_dir": "/tmp/fleet_safe_data",
            }],
        ),
    ])
