#!/bin/bash
# Fleet-Safe-VLA-OS — Keyboard teleop for the real Yahboom M3Pro
#
# Uses ros2 teleop_twist_keyboard (or the FleetSafe dashboard if preferred).
# Commands go to /cmd_vel which the M3Pro driver consumes.
#
# Safety note:
#   Max linear  = 0.15 m/s  (conservative for first contact)
#   Max angular = 0.5 rad/s
#   Increase only after verifying the floor is clear.
#
# Usage:
#   ./scripts/real_robot/teleop_m3pro.sh                 # keyboard teleop
#   ./scripts/real_robot/teleop_m3pro.sh --max-speed 0.3 # higher speed
#   ./scripts/real_robot/teleop_m3pro.sh --zero          # publish zero and exit
#
# Dashboard teleop (preferred for monitoring):
#   ./scripts/real_robot/run_m3pro_ros2_bridge.sh
#   http://localhost:8080/yahboom → Real M3Pro → WASD

set -euo pipefail

MAX_LIN="${MAX_LINEAR:-0.15}"
MAX_ANG="${MAX_ANGULAR:-0.5}"
ZERO_ONLY=false

for arg in "$@"; do
    case "$arg" in
        --max-speed=*) MAX_LIN="${arg#--max-speed=}" ;;
        --max-speed)   shift; MAX_LIN="$1" ;;
        --zero)        ZERO_ONLY=true ;;
    esac
done

# ── Source ROS2 ───────────────────────────────────────────────────────────────
source /opt/ros/humble/setup.bash 2>/dev/null || {
    echo "[ERROR] ROS2 Humble not found."
    exit 1
}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WS_INSTALL="${REPO_ROOT}/ros2_ws/install/setup.bash"
[[ -f "$WS_INSTALL" ]] && source "$WS_INSTALL" || true

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"

echo "============================================================"
echo "  Fleet-Safe  |  M3Pro Keyboard Teleop"
echo "  /cmd_vel target  |  max_lin=${MAX_LIN}m/s  max_ang=${MAX_ANG}rad/s"
echo "  ROS_DOMAIN_ID=$ROS_DOMAIN_ID"
echo "============================================================"
echo ""

# ── Zero cmd_vel and exit ─────────────────────────────────────────────────────
if $ZERO_ONLY; then
    echo "[teleop] Publishing zero cmd_vel..."
    ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist \
        '{"linear": {"x": 0.0, "y": 0.0, "z": 0.0}, "angular": {"x": 0.0, "y": 0.0, "z": 0.0}}'
    echo "[teleop] Zero sent."
    exit 0
fi

# ── Check /cmd_vel topic is reachable ─────────────────────────────────────────
ACTIVE=$(timeout 3 ros2 topic list 2>/dev/null || echo "")
if ! echo "$ACTIVE" | grep -qF "/cmd_vel"; then
    echo "[WARN] /cmd_vel topic not found in ros2 topic list."
    echo "  Start robot bringup first:"
    echo "    ssh yahboom@<robot_ip>"
    echo "    ros2 launch yahboom_bringup bringup.launch.py"
    echo ""
    read -rp "  Continue anyway? [y/N] " ans
    [[ "$ans" =~ ^[Yy] ]] || exit 1
fi

echo "  Controls (teleop_twist_keyboard):"
echo "    i = forward    , = backward"
echo "    j = left        l = right"
echo "    k = stop"
echo "    q/z = increase/decrease max speed"
echo ""
echo "  Ctrl+C to stop and publish zero cmd_vel."
echo ""

# Trap to zero out cmd_vel on exit
cleanup() {
    echo ""
    echo "[teleop] Stopping robot (publishing zero cmd_vel)..."
    ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist \
        '{"linear": {"x": 0.0, "y": 0.0, "z": 0.0}, "angular": {"x": 0.0, "y": 0.0, "z": 0.0}}' \
        2>/dev/null || true
    echo "[teleop] Stopped."
}
trap cleanup EXIT

# ── Launch teleop_twist_keyboard ──────────────────────────────────────────────
# M3Pro is holonomic: enable strafing (y-axis)
if command -v ros2 &>/dev/null; then
    ros2 run teleop_twist_keyboard teleop_twist_keyboard \
        --ros-args \
        -p "speed:=${MAX_LIN}" \
        -p "turn:=${MAX_ANG}" \
        -r __ns:=/ \
        2>/dev/null || {
        echo "[WARN] teleop_twist_keyboard not found."
        echo "  Install: sudo apt install ros-humble-teleop-twist-keyboard"
        echo ""
        echo "  Alternative: use the FleetSafe dashboard WASD controls:"
        echo "    ./scripts/real_robot/run_m3pro_ros2_bridge.sh"
        echo "    http://localhost:8080/yahboom"
        exit 1
    }
fi
