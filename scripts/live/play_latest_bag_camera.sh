#!/bin/bash
# FleetSafe — Safe local bag playback with camera viewer.
#
# ISOLATION GUARANTEE:
#   ROS_DOMAIN_ID=99 + ROS_LOCALHOST_ONLY=1
#   This playback is completely isolated from the live robot (domain 30).
#   It CANNOT send commands to the robot under any circumstances.
#
# Usage:
#   ./scripts/live/play_latest_bag_camera.sh           # latest bag
#   ./scripts/live/play_latest_bag_camera.sh /path/bag  # specific bag
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=/dev/null
source "${REPO_ROOT}/config/fleetsafe_real_robot.env"
# shellcheck source=/dev/null
source /opt/ros/humble/setup.bash

# ── SAFETY: isolated playback domain ─────────────────────────────────────────
export ROS_DOMAIN_ID="${FLEETSAFE_PLAYBACK_DOMAIN}"
export ROS_LOCALHOST_ONLY=1

if [[ $# -ge 1 ]]; then
    BAG="$1"
else
    BAG_DIR="${REPO_ROOT}/${FLEETSAFE_BAG_DIR}"
    BAG=$(find "${BAG_DIR}" -maxdepth 1 -type d -name "m3pro_full_motion_*" \
          | sort | tail -1)
    if [[ -z "${BAG}" ]]; then
        echo "[ERROR] No m3pro_full_motion_* bags found in ${BAG_DIR}"
        exit 1
    fi
fi

VIEWER="${REPO_ROOT}/scripts/viewers/ros_camera_bmp_server.py"
VIEWER_PORT="${FLEETSAFE_VIEWER_PORT}"
VIEWER_PID=""

cleanup() {
    echo ""
    echo "Stopping camera viewer..."
    [[ -n "${VIEWER_PID}" ]] && kill "${VIEWER_PID}" 2>/dev/null || true
    echo "Playback session ended."
}
trap cleanup EXIT INT TERM

echo "============================================================"
echo "  FleetSafe  |  Safe Bag Playback"
echo ""
echo "  ISOLATION: ROS_DOMAIN_ID=${ROS_DOMAIN_ID}  ROS_LOCALHOST_ONLY=1"
echo "  This playback CANNOT reach the live robot (domain 30)."
echo "  No movement commands will be sent to the robot."
echo ""
echo "  Bag    : ${BAG}"
echo "  Viewer : ${FLEETSAFE_VIEWER_URL}"
echo "============================================================"
echo ""

# ── Start camera viewer ───────────────────────────────────────────────────────
/usr/bin/python3 "${VIEWER}" \
    --topic "${FLEETSAFE_TOPIC_RGB}" \
    --port "${VIEWER_PORT}" &
VIEWER_PID=$!
sleep 1

echo "Camera viewer started at ${FLEETSAFE_VIEWER_URL}"
echo "Opening browser..."
xdg-open "${FLEETSAFE_VIEWER_URL}" 2>/dev/null || true
echo ""
echo "Starting bag playback (looping, rate 10x)..."
echo "Press Ctrl-C to stop."
echo ""

ros2 bag play "${BAG}" --loop --rate 10.0
