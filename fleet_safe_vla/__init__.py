"""
Fleet-Safe-VLA-OS: Production-grade multi-simulator robotics research platform.

Provides:
  - H1 humanoid locomotion environments (Isaac Lab, MuJoCo, Gazebo)
  - Fleet safety layer with Control Barrier Functions
  - Sim2Real pipeline with ONNX export and ROS2 deployment
  - Benchmarking suite (fleet_safe_benchmark_v0)
  - Web-based robot state viewer

Builds on top of robot-lab (https://github.com/user/robot-lab) which must
be installed before using Isaac Lab or sim2real modules.
"""

__version__ = "0.1.0"
__author__ = "FAVL-AI"
