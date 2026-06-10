#!/bin/bash
# Fleet-Safe-VLA-OS — Real Yahboom M3Pro ROS2 → FleetSafe WebSocket Bridge
#
# Subscribes to the physical M3Pro ROS2 topics and streams telemetry
# to the FleetSafe dashboard at ws://0.0.0.0:8766 (20 Hz JSON).
#
# Robot IP:
#   ASK4/LAN DHCP address is preferred — run discover_yahboom.sh first.
#   192.168.8.88 is the robot's hotspot/AP fallback (--hotspot mode).
#   This script bridges ROS2 DDS topics, not raw TCP to the robot IP.
#
# Usage (two terminals):
#   Terminal 1 — Real robot bridge:
#     ./scripts/real_robot/run_m3pro_ros2_bridge.sh
#
#   Terminal 2 — FleetSafe web app:
#     ./scripts/web/start_robot_viewer.sh
#
#   Browser: http://localhost:8080/yahboom   → select "Real M3Pro" source
#
# ROS2 network:
#   The M3Pro must be on the same network segment (or Tailscale).
#   ROS_DOMAIN_ID must match between the robot and this machine (default: 0).
#
# Telemetry flow:
#   M3Pro hardware → ROS2 DDS → /odom /joint_states /scan /imu
#     → this bridge (ws://0.0.0.0:8766) → FleetSafe web app → browser
#
# To test without a physical robot:
#   ros2 bag play <bag_file>   # replay a recorded M3Pro session
#   Or: ros2 topic pub /odom nav_msgs/msg/Odometry ...

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "============================================================"
echo "  Fleet-Safe-VLA-OS  |  M3Pro ROS2 Telemetry Bridge"
echo "  Topics  : /odom  /joint_states  /scan  /imu/data"
echo "  WS      : ws://localhost:8766"
echo "  Dashboard: http://localhost:8080/yahboom → Real M3Pro tab"
echo "============================================================"
echo ""

# ── Source ROS2 Humble ────────────────────────────────────────────────────────
ROS_SETUP="/opt/ros/humble/setup.bash"
if [[ ! -f "$ROS_SETUP" ]]; then
    echo "[ERROR] ROS2 Humble not found at $ROS_SETUP"
    echo "  Install: https://docs.ros.org/en/humble/Installation.html"
    exit 1
fi
# shellcheck source=/dev/null
source "$ROS_SETUP"

# ── Source workspace overlay (if built) ──────────────────────────────────────
WS_INSTALL="${REPO_ROOT}/ros2_ws/install/setup.bash"
if [[ -f "$WS_INSTALL" ]]; then
    # shellcheck source=/dev/null
    source "$WS_INSTALL"
    echo "[INFO] Workspace overlay: $WS_INSTALL"
else
    echo "[INFO] No workspace overlay found. Run: cd ros2_ws && colcon build"
fi

# ── ROS_DOMAIN_ID ─────────────────────────────────────────────────────────────
# Must match the robot's ROS_DOMAIN_ID. Default 0 works if both are default.
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
echo "[INFO] ROS_DOMAIN_ID=$ROS_DOMAIN_ID"
echo ""

# ── Python path ───────────────────────────────────────────────────────────────
export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"

# ── Run bridge ────────────────────────────────────────────────────────────────
echo "[INFO] Starting M3Pro ROS2 bridge..."
echo "[INFO] Open dashboard: http://localhost:8080/yahboom"
echo "[INFO] Select 'Real M3Pro' source in the dashboard."
echo ""

python3 "${SCRIPT_DIR}/run_m3pro_ros2_bridge.py" "$@"
