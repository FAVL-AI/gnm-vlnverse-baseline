#!/usr/bin/env bash
# setup_m3pro_gazebo.sh — Clone and build Yahboom M3Pro ROS2 packages for Gazebo.
#
# This sets up the official ROSMASTER-M3PRO ROS2 repository alongside our
# FleetSafe workspace so we can use Gazebo for offline testing.
#
# What it does:
#   1. Clone github.com/YahboomTechnology/ROSMASTER-M3PRO into a workspace
#   2. Install ROS2 Humble dependencies
#   3. Build with colcon
#   4. Print the launch command
#
# Usage:
#   bash scripts/ros2_gazebo/setup_m3pro_gazebo.sh
#   bash scripts/ros2_gazebo/setup_m3pro_gazebo.sh --ws ~/m3pro_ws

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

WS_DIR="${1:-$HOME/m3pro_ws}"

echo ""
echo "============================================================"
echo "  Yahboom M3Pro — Gazebo / ROS2 Setup"
echo "============================================================"
echo "  Workspace : $WS_DIR"
echo "  Repo      : $REPO_ROOT"
echo ""

# ── Check ROS2 ────────────────────────────────────────────────────────────────
if ! command -v ros2 &>/dev/null; then
    echo "ERROR: ROS2 not found. Install ROS2 Humble first:"
    echo "  https://docs.ros.org/en/humble/Installation.html"
    exit 1
fi
ROS_DISTRO="${ROS_DISTRO:-humble}"
echo "  ROS2 distro: $ROS_DISTRO"

# ── Clone repo ────────────────────────────────────────────────────────────────
mkdir -p "$WS_DIR/src"

YAHBOOM_DIR="$WS_DIR/src/ROSMASTER-M3PRO"
if [ -d "$YAHBOOM_DIR" ]; then
    echo "  [SKIP] ROSMASTER-M3PRO already cloned at $YAHBOOM_DIR"
    echo "         Run 'git pull' in that directory to update."
else
    echo "  Cloning YahboomTechnology/ROSMASTER-M3PRO…"
    git clone https://github.com/YahboomTechnology/ROSMASTER-M3PRO.git "$YAHBOOM_DIR"
    echo "  Cloned ✓"
fi

# ── Install ROS2 dependencies ─────────────────────────────────────────────────
echo ""
echo "  Installing ROS2 dependencies (requires sudo)…"
cd "$WS_DIR"
rosdep update 2>/dev/null || true
rosdep install --from-paths src --ignore-src -r -y \
    --rosdistro "$ROS_DISTRO" 2>/dev/null || {
    echo "  [WARN] rosdep install failed — continuing anyway"
}

# Common dependencies not always caught by rosdep:
PKGS=(
    "ros-${ROS_DISTRO}-gazebo-ros-pkgs"
    "ros-${ROS_DISTRO}-gazebo-ros2-control"
    "ros-${ROS_DISTRO}-joint-state-publisher"
    "ros-${ROS_DISTRO}-joint-state-publisher-gui"
    "ros-${ROS_DISTRO}-robot-state-publisher"
    "ros-${ROS_DISTRO}-xacro"
    "ros-${ROS_DISTRO}-nav2-bringup"
    "ros-${ROS_DISTRO}-navigation2"
    "ros-${ROS_DISTRO}-slam-toolbox"
)
for pkg in "${PKGS[@]}"; do
    if ! dpkg -l "$pkg" &>/dev/null; then
        echo "    apt install $pkg"
        sudo apt install -y "$pkg" 2>/dev/null || echo "    [WARN] Could not install $pkg"
    fi
done

# ── Build ─────────────────────────────────────────────────────────────────────
echo ""
echo "  Building workspace…"
cd "$WS_DIR"
source "/opt/ros/${ROS_DISTRO}/setup.bash"
colcon build --symlink-install 2>&1 | tail -20

echo ""
echo "============================================================"
echo "  Build complete!  Source before use:"
echo ""
echo "    source /opt/ros/${ROS_DISTRO}/setup.bash"
echo "    source $WS_DIR/install/setup.bash"
echo ""
echo "  Launch Gazebo simulation:"
echo ""
echo "    ros2 launch yahboomcar_gazebo yahboom_world.launch.py"
echo ""
echo "  Check available topics after launch:"
echo "    ros2 topic list | grep -E '/cmd_vel|/camera|/odom|/scan'"
echo ""
echo "  Teleoperate robot in Gazebo:"
echo "    ros2 run teleop_twist_keyboard teleop_twist_keyboard"
echo ""
echo "  Record a route for topomap:"
echo "    ros2 bag record /usb_cam/image_raw /odom /cmd_vel -o recordings/gazebo_route"
echo ""
echo "  Build topomap from bag:"
echo "    python $REPO_ROOT/scripts/visualnav/build_topomap.py \\"
echo "        --from-bag recordings/gazebo_route \\"
echo "        --name hospital_route_gazebo"
echo "============================================================"
