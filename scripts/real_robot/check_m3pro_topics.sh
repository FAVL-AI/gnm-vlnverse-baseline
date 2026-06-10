#!/bin/bash
# Fleet-Safe-VLA-OS — Verify ROS2 topics from the real Yahboom M3Pro
#
# Sources ROS2 Humble and checks that the expected M3Pro topics are active.
# Run this AFTER the robot is powered on and on the same network.
#
# Usage:
#   ./scripts/real_robot/check_m3pro_topics.sh
#   ROS_DOMAIN_ID=5 ./scripts/real_robot/check_m3pro_topics.sh
#   ./scripts/real_robot/check_m3pro_topics.sh --hz   # also measure topic Hz

set -euo pipefail

MEASURE_HZ=false
for arg in "$@"; do
    [[ "$arg" == "--hz" ]] && MEASURE_HZ=true
done

# ── Source ROS2 ───────────────────────────────────────────────────────────────
source /opt/ros/humble/setup.bash 2>/dev/null || {
    echo "[ERROR] ROS2 Humble not found at /opt/ros/humble/setup.bash"
    exit 1
}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WS_INSTALL="${REPO_ROOT}/ros2_ws/install/setup.bash"
[[ -f "$WS_INSTALL" ]] && source "$WS_INSTALL" || true

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"

echo "============================================================"
echo "  Fleet-Safe  |  M3Pro ROS2 Topic Check"
echo "  ROS_DOMAIN_ID: $ROS_DOMAIN_ID"
echo "  ROS_DISTRO:    $ROS_DISTRO"
echo "============================================================"
echo ""

# ── Expected M3Pro topics (from robot_contract_m3pro.yaml) ───────────────────
declare -A TOPICS=(
    ["/odom"]="nav_msgs/msg/Odometry"
    ["/joint_states"]="sensor_msgs/msg/JointState"
    ["/scan"]="sensor_msgs/msg/LaserScan"
    ["/imu/data"]="sensor_msgs/msg/Imu"
    ["/cmd_vel"]="geometry_msgs/msg/Twist"
    ["/camera/color/image_raw"]="sensor_msgs/msg/Image"
    ["/fleet_safe/estop"]="std_msgs/msg/Bool"
    ["/fleet_safe/status"]="fleet_safe_msgs/msg/SafetyStatus"
    ["/tf"]="tf2_msgs/msg/TFMessage"
)

echo "Listing active ROS2 topics (timeout 5s)..."
ACTIVE=$(timeout 5 ros2 topic list 2>/dev/null || echo "")
if [[ -z "$ACTIVE" ]]; then
    echo ""
    echo "[ERROR] No ROS2 topics found."
    echo "  Check:"
    echo "  1. Is the robot powered on and connected?"
    echo "  2. Are you on the same network / Tailscale?"
    echo "  3. Does ROS_DOMAIN_ID=$ROS_DOMAIN_ID match the robot?"
    echo "  4. Is a ROS2 node running on the robot?"
    echo "     (ssh into the robot and run: ros2 launch yahboom_bringup bringup.launch.py)"
    exit 1
fi

echo ""
echo "Topic status:"
echo "  ✓ = active   ✗ = not found   ? = optional"
echo ""

REQUIRED=("/odom" "/joint_states" "/scan" "/imu/data" "/cmd_vel")
OPTIONAL=("/camera/color/image_raw" "/fleet_safe/estop" "/fleet_safe/status" "/tf")

ALL_REQUIRED_OK=true

for topic in "${REQUIRED[@]}"; do
    if echo "$ACTIVE" | grep -qF "$topic"; then
        echo "  ✓  $topic  [${TOPICS[$topic]:-}]"
    else
        echo "  ✗  $topic  MISSING — required by the FleetSafe bridge"
        ALL_REQUIRED_OK=false
    fi
done

echo ""
for topic in "${OPTIONAL[@]}"; do
    if echo "$ACTIVE" | grep -qF "$topic"; then
        echo "  ✓  $topic  [${TOPICS[$topic]:-}]  (optional)"
    else
        echo "  ?  $topic  not active  (optional)"
    fi
done

echo ""

# ── Hz measurement (optional) ─────────────────────────────────────────────────
if $MEASURE_HZ; then
    echo "Measuring topic rates (3 seconds each)..."
    echo ""
    for topic in "${REQUIRED[@]}"; do
        if echo "$ACTIVE" | grep -qF "$topic"; then
            HZ=$(timeout 5 ros2 topic hz "$topic" 2>/dev/null | grep "^average" | head -1 | awk '{print $3}' || echo "?")
            echo "  $topic  →  ${HZ} Hz"
        fi
    done
    echo ""
fi

# ── Summary ───────────────────────────────────────────────────────────────────
if $ALL_REQUIRED_OK; then
    echo "  All required topics active. Bridge should connect cleanly."
    echo ""
    echo "  Start the FleetSafe bridge:"
    echo "    ./scripts/real_robot/run_m3pro_ros2_bridge.sh"
else
    echo "  Some required topics are missing."
    echo "  On the robot, verify bringup is running:"
    echo "    ros2 launch yahboom_bringup bringup.launch.py"
    echo "  Or check the Yahboom manual for the correct launch file."
fi
echo ""
