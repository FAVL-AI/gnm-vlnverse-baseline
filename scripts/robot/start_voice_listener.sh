#!/usr/bin/env bash
# start_voice_listener.sh — Start the voice/A-MIC listener on Jetson.
#
# Behavior:
#   1. Check for existing ROS2 voice/ASR topic.
#   2. If found, bridge it to /fleetsafe/instruction_voice.
#   3. If not found, print instructions for manual simulation.
#   4. NEVER sends /cmd_vel. Voice creates instructions only.
#
# Run on Jetson or via SSH.
set -euo pipefail

source /opt/ros/humble/setup.bash 2>/dev/null || true
[ -f "$HOME/yahboomcar_ws/install/setup.bash" ] && \
    source "$HOME/yahboomcar_ws/install/setup.bash" 2>/dev/null || true

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-30}"
export ROS_LOCALHOST_ONLY=0

echo "[VLN Voice] Starting voice listener — ROS_DOMAIN_ID=${ROS_DOMAIN_ID}"
echo "[VLN Voice] WARNING: This script does NOT send cmd_vel."
echo "[VLN Voice] Voice creates language instructions only."
echo ""

# ── Search for existing voice topics ─────────────────────────────────────────
VOICE_TOPICS=(
    "/voice_text"
    "/speech_text"
    "/asr_text"
    "/iat_text"
    "/voice_cmd"
    "/voice_command"
    "/mic/text"
    "/wake_word"
    "/xfyun/asr"
)

FOUND_TOPIC=""
if command -v ros2 &>/dev/null; then
    for t in "${VOICE_TOPICS[@]}"; do
        if ros2 topic list 2>/dev/null | grep -q "^${t}$"; then
            FOUND_TOPIC="$t"
            echo "[VLN Voice] Found voice topic: $t"
            break
        fi
    done
fi

if [ -n "$FOUND_TOPIC" ]; then
    echo "[VLN Voice] Bridging $FOUND_TOPIC → /fleetsafe/instruction_voice"
    echo "[VLN Voice] Press Ctrl+C to stop."
    # Relay: echo each message to our instruction topic
    ros2 topic echo --no-arr "$FOUND_TOPIC" std_msgs/msg/String 2>/dev/null \
    | while IFS= read -r line; do
        # Strip 'data: ' prefix from ros2 topic echo output
        msg=$(echo "$line" | sed "s/^data: //")
        if [ -n "$msg" ]; then
            ros2 topic pub --once /fleetsafe/instruction_voice std_msgs/msg/String \
                "{data: '$msg'}" 2>/dev/null || true
        fi
    done
else
    echo "[VLN Voice] No live voice topic detected."
    echo ""
    echo "[VLN Voice] ─── Manual simulation mode ─────────────────────────"
    echo "[VLN Voice] Send a test instruction (from RTX desktop or Jetson):"
    echo ""
    echo '  ros2 topic pub --once /fleetsafe/instruction_voice \'
    echo '    std_msgs/msg/String \'
    echo '    "{data: '\''go forward slowly and stop near the door'\''}"'
    echo ""
    echo "  Or use the Makefile:"
    echo '    make vln-send TEXT="go to the nurse station"'
    echo ""
    echo "[VLN Voice] Listening for /fleetsafe/instruction_voice messages..."
    echo "[VLN Voice] Press Ctrl+C to stop."
    # Just echo what arrives on the instruction topic
    ros2 topic echo /fleetsafe/instruction_voice std_msgs/msg/String 2>/dev/null || \
        echo "[VLN Voice] Topic not yet active — start publishing from the RTX desktop."
fi
