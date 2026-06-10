#!/usr/bin/env bash
# start_vln_stack.sh — Start the FleetSafe VLN stack (RTX desktop side).
#
# This script starts the VLN supervisor in DRY-RUN mode by default.
# Pass --enable-motion to allow actual robot commands (requires safety preflight).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

# Load VLN config
VLN_ENV="config/fleetsafe_vln.env"
REAL_ENV="config/fleetsafe_real_robot.env"

[ -f "$VLN_ENV" ]  && source "$VLN_ENV"
[ -f "$REAL_ENV" ] && source "$REAL_ENV"

# Parse flags
ENABLE_MOTION=0
for arg in "$@"; do
    [ "$arg" = "--enable-motion" ] && ENABLE_MOTION=1
done

# Source ROS2
source /opt/ros/humble/setup.bash 2>/dev/null || true

echo "╔══════════════════════════════════════════════════════╗"
echo "║         FleetSafe VLN Stack — Starting              ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "  ROS_DOMAIN_ID : ${ROS_DOMAIN_ID:-30}"
echo "  Robot IP      : ${FLEETSAFE_ROBOT_HOST:-172.20.10.14}"
echo "  RGB topic     : ${VLN_RGB_TOPIC:-/camera/color/image_raw}"
echo "  cmd_vel topic : ${VLN_CMD_TOPIC:-/cmd_vel}"
echo "  Model         : ${VLN_DEFAULT_MODEL:-gnm}"
echo "  Motion        : $([ $ENABLE_MOTION -eq 1 ] && echo 'LIVE (--enable-motion)' || echo 'DRY-RUN (default)')"
echo "  Dashboard     : ${VLN_DASHBOARD_URL:-http://172.20.10.2:8000}"
echo ""

# ── Pre-flight: verify camera topic ──────────────────────────────────────────
RGB_TOPIC="${VLN_RGB_TOPIC:-/camera/color/image_raw}"
if command -v ros2 &>/dev/null; then
    if ros2 topic list 2>/dev/null | grep -q "^${RGB_TOPIC}$"; then
        echo "[VLN] Camera topic verified: $RGB_TOPIC"
    else
        echo "[VLN] WARNING: $RGB_TOPIC not found — ensure robot camera is running."
    fi
fi

# ── Optional: start camera viewer ────────────────────────────────────────────
if ! pgrep -f "ros_camera_bmp_server" > /dev/null 2>&1; then
    echo "[VLN] Starting camera viewer at http://127.0.0.1:${FLEETSAFE_VIEWER_PORT:-8081}"
    /usr/bin/python3 scripts/viewers/ros_camera_bmp_server.py \
        --topic "$RGB_TOPIC" \
        --port "${FLEETSAFE_VIEWER_PORT:-8081}" &
    sleep 1
fi

# ── Start VLN demo ────────────────────────────────────────────────────────────
MOTION_FLAG=""
[ $ENABLE_MOTION -eq 1 ] && MOTION_FLAG="--publish"

echo "[VLN] Launching VLN instruction demo..."
echo "[VLN] Type instructions below or use:"
echo "        make vln-send TEXT=\"go to the nurse station\""
echo ""

python3 scripts/vln/run_vln_instruction_demo.py \
    --source stdin \
    --backbone "${VLN_DEFAULT_MODEL:-gnm}" \
    --cmd-topic "${VLN_CMD_TOPIC:-/cmd_vel}" \
    --odom-topic "${VLN_ODOM_TOPIC:-/odom_raw}" \
    --scan-topics ${VLN_SCAN_TOPICS:-"/scan0 /scan1"} \
    --certificate-out "${VLN_CERT_DIR:-results/certificates}/vln_demo_$(date +%Y%m%d_%H%M%S).jsonl" \
    $MOTION_FLAG \
    "$@"
