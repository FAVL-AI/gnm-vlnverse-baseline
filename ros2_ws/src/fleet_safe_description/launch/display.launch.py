"""
URDF display launch for fleet_safe_description.
Launches robot_state_publisher + joint_state_publisher_gui + RViz2.
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import Command, FindExecutable, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pkg_desc = FindPackageShare("fleet_safe_description")

    urdf_xacro = PathJoinSubstitution([pkg_desc, "urdf", "h1.urdf.xacro"])
    robot_description = Command([FindExecutable(name="xacro"), " ", urdf_xacro])

    rsp = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        parameters=[{"robot_description": robot_description, "use_sim_time": False}],
        output="screen",
    )

    jsp_gui = Node(
        package="joint_state_publisher_gui",
        executable="joint_state_publisher_gui",
        output="screen",
    )

    rviz = Node(
        package="rviz2",
        executable="rviz2",
        output="screen",
    )

    return LaunchDescription([rsp, jsp_gui, rviz])
