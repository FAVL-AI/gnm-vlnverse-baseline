#!/bin/bash
# Launch H1 in Gazebo Harmonic with Fleet-Safe ROS2 stack
# Usage: ./scripts/ros2_gazebo/launch.sh [world:=empty] [gui:=true]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ROS2_WS="$REPO_ROOT/ros2_ws"

echo "=== Fleet-Safe-VLA-OS ROS2/Gazebo Launch ==="
echo "ROS2 workspace: $ROS2_WS"

# Source ROS2
if [ -f /opt/ros/humble/setup.bash ]; then
    source /opt/ros/humble/setup.bash
else
    echo "ERROR: ROS2 Humble not found at /opt/ros/humble"
    exit 1
fi

# Build workspace if not built
if [ ! -d "$ROS2_WS/install" ]; then
    echo "Building ROS2 workspace..."
    cd "$ROS2_WS"
    colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release
fi

# Source workspace
source "$ROS2_WS/install/setup.bash"

# Set Python path for fleet_safe_vla
export PYTHONPATH="$REPO_ROOT:$PYTHONPATH"

# Launch
cd "$REPO_ROOT"
ros2 launch fleet_safe_bringup h1_gazebo.launch.py "$@"
