#!/bin/bash
# FleetSafe — Record real robot bag on ROS_DOMAIN_ID=30
#
# Records all key M3Pro topics to data/real_robot_bags/m3pro_full_motion_TIMESTAMP.
# Run manually from the RTX desktop when you want to capture an episode.
#
# Usage: ./scripts/live/record_real_robot_bag.sh
# Stop:  Ctrl-C
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=/dev/null
source "${REPO_ROOT}/config/fleetsafe_real_robot.env"
# shellcheck source=/dev/null
source /opt/ros/humble/setup.bash

export ROS_DOMAIN_ID="${FLEETSAFE_LIVE_DOMAIN}"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BAG_NAME="m3pro_full_motion_${TIMESTAMP}"
BAG_PATH="${REPO_ROOT}/${FLEETSAFE_BAG_DIR}/${BAG_NAME}"

mkdir -p "${REPO_ROOT}/${FLEETSAFE_BAG_DIR}"

echo "============================================================"
echo "  FleetSafe  |  Real Robot Bag Recording"
echo "  ROS_DOMAIN_ID : ${ROS_DOMAIN_ID}  (LIVE — do NOT replay here)"
echo "  Output        : ${BAG_PATH}"
echo "============================================================"
echo ""
echo "Recording topics:"
echo "  ${FLEETSAFE_TOPIC_RGB}"
echo "  ${FLEETSAFE_TOPIC_DEPTH}"
echo "  ${FLEETSAFE_TOPIC_CAM_INFO_COLOR}"
echo "  ${FLEETSAFE_TOPIC_CAM_INFO_DEPTH}"
echo "  ${FLEETSAFE_TOPIC_ODOM}"
echo "  ${FLEETSAFE_TOPIC_IMU}"
echo "  ${FLEETSAFE_TOPIC_SCAN0}"
echo "  ${FLEETSAFE_TOPIC_SCAN1}"
echo "  ${FLEETSAFE_TOPIC_CMDVEL}"
echo ""
echo "Press Ctrl-C to stop recording."
echo ""

ros2 bag record \
    -o "${BAG_PATH}" \
    "${FLEETSAFE_TOPIC_RGB}" \
    "${FLEETSAFE_TOPIC_DEPTH}" \
    "${FLEETSAFE_TOPIC_CAM_INFO_COLOR}" \
    "${FLEETSAFE_TOPIC_CAM_INFO_DEPTH}" \
    "${FLEETSAFE_TOPIC_ODOM}" \
    "${FLEETSAFE_TOPIC_IMU}" \
    "${FLEETSAFE_TOPIC_SCAN0}" \
    "${FLEETSAFE_TOPIC_SCAN1}" \
    "${FLEETSAFE_TOPIC_CMDVEL}"

echo ""
echo "Bag saved to: ${BAG_PATH}"
