#!/usr/bin/env bash
# check_voice_module.sh — Discover voice/A-MIC hardware and ROS2 topics on Jetson.
# Run this script ON the Jetson (or via SSH):
#   ssh jetson@172.20.10.14 'bash -s' < scripts/robot/check_voice_module.sh
# Or:
#   bash scripts/robot/check_voice_module.sh  (if running locally on Jetson)
set -euo pipefail

echo "╔══════════════════════════════════════════════════════╗"
echo "║       FleetSafe VLN — Voice Module Discovery        ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── USB audio devices ─────────────────────────────────────────────────────────
echo "── USB devices (audio/mic) ──────────────────────────"
lsusb 2>/dev/null | grep -iE "audio|mic|sound|headset|speaker|yahboom|amr|amic" || echo "  (none matching audio/mic)"
echo ""

# ── ALSA capture devices ──────────────────────────────────────────────────────
echo "── ALSA capture devices (arecord -l) ────────────────"
arecord -l 2>/dev/null || echo "  (arecord not available or no capture devices)"
echo ""

# ── PulseAudio / PipeWire sources ─────────────────────────────────────────────
echo "── PulseAudio sources ───────────────────────────────"
pactl list short sources 2>/dev/null | grep -v monitor || echo "  (pactl not available or no sources)"
echo ""

# ── ROS2 topics ───────────────────────────────────────────────────────────────
echo "── ROS2 voice/ASR/audio topics ─────────────────────"

_ros_setup() {
    source /opt/ros/humble/setup.bash 2>/dev/null || true
    # Yahboom workspace
    if [ -f "$HOME/yahboomcar_ws/install/setup.bash" ]; then
        source "$HOME/yahboomcar_ws/install/setup.bash" 2>/dev/null || true
    fi
    export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-30}"
    export ROS_LOCALHOST_ONLY=0
}

_ros_setup
if command -v ros2 &>/dev/null; then
    ros2 topic list -t 2>/dev/null \
        | grep -iE "voice|speech|audio|mic|asr|iat|xf|wake|command|text|amr|amic" \
        || echo "  (no matching topics found)"
else
    echo "  (ros2 command not found — source ROS2 first)"
fi
echo ""

# ── ROS2 nodes ────────────────────────────────────────────────────────────────
echo "── ROS2 nodes (voice/speech/audio) ─────────────────"
if command -v ros2 &>/dev/null; then
    ros2 node list 2>/dev/null \
        | grep -iE "voice|speech|audio|mic|asr|iat|xf|wake|amr|amic" \
        || echo "  (no matching nodes found)"
fi
echo ""

# ── Yahboom workspace voice files ─────────────────────────────────────────────
echo "── Yahboom workspace voice-related files ────────────"
YBWS="${HOME}/yahboomcar_ws"
if [ -d "$YBWS" ]; then
    find "$YBWS/src" -type f 2>/dev/null \
        | grep -iE "voice|speech|audio|mic|asr|iat|xf|wake|pcm|alsa|pyaudio|amr|amic" \
        | head -30 \
        || echo "  (none found)"
else
    echo "  ($YBWS not found)"
fi
echo ""

# ── /dev audio devices ────────────────────────────────────────────────────────
echo "── /dev audio/sound devices ─────────────────────────"
ls /dev/snd/ 2>/dev/null || echo "  (none)"
ls /dev/audio* 2>/dev/null || true
echo ""

# ── Recommendations ───────────────────────────────────────────────────────────
echo "── Next steps ───────────────────────────────────────"
echo "  To test a voice topic (replace TOPIC_NAME):"
echo "    ros2 topic echo /TOPIC_NAME"
echo ""
echo "  To manually simulate a voice command:"
echo '    ros2 topic pub --once /fleetsafe/instruction_voice std_msgs/msg/String \'
echo '      "{data: '\''go forward slowly and stop near the door'\''}"'
echo ""
echo "  To run the VLN demo from the RTX desktop:"
echo "    make vln-demo-dry"
echo ""
echo "Done."
