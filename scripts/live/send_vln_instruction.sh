#!/usr/bin/env bash
# send_vln_instruction.sh — Publish a text instruction to the VLN controller.
#
# All arguments are joined as the instruction string.
# If no arguments given, publishes a safe default instruction.
#
# Usage:
#   bash scripts/live/send_vln_instruction.sh
#   bash scripts/live/send_vln_instruction.sh move forward slowly
#   bash scripts/live/send_vln_instruction.sh "go to the nurse station and avoid people"
#   make vln-send TEXT="move forward slowly"
set -euo pipefail

DEFAULT_INSTRUCTION="move forward slowly and keep at least half a meter from obstacles"

# Join all args as the instruction (handles both quoted and unquoted multi-word)
if [[ $# -eq 0 ]]; then
    INSTRUCTION="$DEFAULT_INSTRUCTION"
else
    INSTRUCTION="$*"
fi

# ── Source ROS2 ───────────────────────────────────────────────────────────────
if ! command -v ros2 &>/dev/null; then
    # shellcheck source=/dev/null
    source /opt/ros/humble/setup.bash 2>/dev/null || {
        echo "[VLN] ERROR: ROS2 not found. source /opt/ros/humble/setup.bash first."
        exit 1
    }
fi

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-30}"
export ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-0}"

TOPIC="/fleetsafe/instruction_text"

echo "[VLN] ROS_DOMAIN_ID=${ROS_DOMAIN_ID}"
echo "[VLN] Topic        : ${TOPIC}"
echo "[VLN] Instruction  : ${INSTRUCTION}"
echo ""

# Escape single quotes in instruction for YAML string safety
SAFE_INSTRUCTION="${INSTRUCTION//\'/\\\'}"

ros2 topic pub --once "$TOPIC" std_msgs/msg/String \
    "{data: '${SAFE_INSTRUCTION}'}" \
    && echo "[VLN] Published." \
    || { echo "[VLN] ERROR: ros2 topic pub failed."; exit 2; }
