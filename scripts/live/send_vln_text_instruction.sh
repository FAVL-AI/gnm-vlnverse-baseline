#!/usr/bin/env bash
# send_vln_text_instruction.sh — Publish a text instruction to the VLN stack.
#
# Usage:
#   bash scripts/live/send_vln_text_instruction.sh "go to the nurse station"
#   make vln-send TEXT="go to the nurse station"
set -euo pipefail

INSTRUCTION="${1:-}"
if [ -z "$INSTRUCTION" ]; then
    echo "Usage: $0 \"<instruction text>\""
    echo "       make vln-send TEXT=\"go to the nurse station\""
    exit 1
fi

# Source ROS2 if available
source /opt/ros/humble/setup.bash 2>/dev/null || true

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-30}"
export ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-0}"

TOPIC="${VLN_TEXT_TOPIC:-/fleetsafe/instruction_text}"

echo "[VLN] Publishing to $TOPIC"
echo "[VLN] Instruction: $INSTRUCTION"
echo "[VLN] ROS_DOMAIN_ID=$ROS_DOMAIN_ID"

if command -v ros2 &>/dev/null; then
    ros2 topic pub --once "$TOPIC" std_msgs/msg/String \
        "{data: '${INSTRUCTION//\'/\'\\\'\'}'}'"
    echo "[VLN] Published."
else
    echo "[VLN] ros2 not available — ROS2 not sourced."
    echo "[VLN] Source /opt/ros/humble/setup.bash first."
    exit 2
fi
