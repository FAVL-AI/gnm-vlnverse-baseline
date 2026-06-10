#!/bin/bash
# FleetSafe — Check live robot topics on ROS_DOMAIN_ID=30 (Yahboom M3Pro)
# Usage: ./scripts/live/check_robot_topics.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=/dev/null
source "${REPO_ROOT}/config/fleetsafe_real_robot.env"
# shellcheck source=/dev/null
source /opt/ros/humble/setup.bash

export ROS_DOMAIN_ID="${FLEETSAFE_LIVE_DOMAIN}"

echo "============================================================"
echo "  FleetSafe  |  Live Robot Topic Check"
echo "  ROS_DOMAIN_ID : ${ROS_DOMAIN_ID}  (live — read-only)"
echo "  Robot         : ${FLEETSAFE_ROBOT_SSH_HOST}"
echo "============================================================"
echo ""

echo "--- ros2 node list ---"
timeout 5 ros2 node list 2>/dev/null || echo "(no nodes visible — is robot stack running?)"
echo ""

echo "--- ros2 topic list ---"
timeout 5 ros2 topic list 2>/dev/null || echo "(no topics visible)"
echo ""

echo "--- /cmd_vel topic info ---"
timeout 5 ros2 topic info /cmd_vel 2>/dev/null || echo "(not found)"
echo ""

echo "--- /camera/color/image_raw  hz (3 s) ---"
timeout 5 ros2 topic hz /camera/color/image_raw --window 10 2>/dev/null | head -5 || echo "(no data)"
echo ""

echo "--- /odom_raw  hz (3 s) ---"
timeout 5 ros2 topic hz /odom_raw --window 10 2>/dev/null | head -5 || echo "(no data)"
echo ""

echo "--- /scan0  hz (3 s) ---"
timeout 5 ros2 topic hz /scan0 --window 10 2>/dev/null | head -5 || echo "(no data)"
echo ""

echo "Done."
