#!/bin/bash
# FleetSafe — Safety stop: publish zero velocity to /cmd_vel for 3 seconds.
# Only use this when the robot is live and needs an immediate motion stop.
# ROS_DOMAIN_ID=30 (live robot).
#
# Usage: ./scripts/live/stop_robot_zero.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=/dev/null
source "${REPO_ROOT}/config/fleetsafe_real_robot.env"
# shellcheck source=/dev/null
source /opt/ros/humble/setup.bash

export ROS_DOMAIN_ID="${FLEETSAFE_LIVE_DOMAIN}"

echo "============================================================"
echo "  FleetSafe  |  SAFETY STOP — publishing zero velocity"
echo "  ROS_DOMAIN_ID : ${ROS_DOMAIN_ID}  (LIVE)"
echo "  Topic         : /cmd_vel"
echo "  Duration      : 3 seconds"
echo "============================================================"

ZERO_MSG='{"linear": {"x": 0.0, "y": 0.0, "z": 0.0}, "angular": {"x": 0.0, "y": 0.0, "z": 0.0}}'
END=$(( $(date +%s) + 3 ))
while [[ $(date +%s) -lt $END ]]; do
    ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist "${ZERO_MSG}" 2>/dev/null || true
    sleep 0.1
done

echo "Zero velocity stop complete."
