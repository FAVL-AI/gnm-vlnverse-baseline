#!/usr/bin/env bash
# discover_voice_resources.sh — Full voice resource audit, saves log file.
# Run on Jetson: bash scripts/robot/discover_voice_resources.sh
set -euo pipefail

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_DIR="logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/robot_voice_discovery_${TIMESTAMP}.txt"

exec > >(tee "$LOG") 2>&1

echo "FleetSafe VLN — Voice Resource Discovery"
echo "Timestamp: $TIMESTAMP"
echo "Host: $(hostname)"
echo ""

source /opt/ros/humble/setup.bash 2>/dev/null || true
[ -f "$HOME/yahboomcar_ws/install/setup.bash" ] && \
    source "$HOME/yahboomcar_ws/install/setup.bash" 2>/dev/null || true
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-30}"
export ROS_LOCALHOST_ONLY=0

echo "=== ROS2 packages (voice/speech/audio) ==="
ros2 pkg list 2>/dev/null \
    | grep -iE "voice|speech|audio|mic|asr|iat|xf|amr|wake" || echo "(none)"

echo ""
echo "=== ROS2 topics (voice/speech/audio) ==="
ros2 topic list -t 2>/dev/null \
    | grep -iE "voice|speech|audio|mic|asr|wake|command|text|iat|xf" || echo "(none)"

echo ""
echo "=== ROS2 nodes (voice/audio) ==="
ros2 node list 2>/dev/null \
    | grep -iE "voice|speech|mic|asr|iat|xf|wake|amr|amic" || echo "(none)"

echo ""
echo "=== Yahboom workspace voice files ==="
YBWS="${HOME}/yahboomcar_ws"
if [ -d "$YBWS" ]; then
    find "$YBWS/src" -type f 2>/dev/null \
        | grep -iE "voice|speech|audio|mic|asr|iat|xf|wake|pcm|alsa|pyaudio|amr|amic" \
        | head -60 || echo "(none)"
else
    echo "(yahboomcar_ws not found)"
fi

echo ""
echo "=== Publisher/subscriber grep (voice/ASR keywords in Python files) ==="
if [ -d "$YBWS" ]; then
    grep -rniE "voice|speech|asr|mic|audio|iat|xf|wake" \
        "$YBWS/src" --include="*.py" \
        | grep -iE "create_publisher|create_subscription|topic_name|pub|sub" \
        | head -40 || echo "(none)"
fi

echo ""
echo "=== USB audio devices ==="
lsusb 2>/dev/null | grep -iE "audio|mic|sound|headset" || echo "(none)"

echo ""
echo "=== ALSA capture devices ==="
arecord -l 2>/dev/null || echo "(arecord not available)"

echo ""
echo "=== /dev/snd ==="
ls /dev/snd/ 2>/dev/null || echo "(none)"

echo ""
echo "=== PulseAudio/PipeWire sources ==="
pactl list short sources 2>/dev/null | grep -v monitor || echo "(pactl not available)"

echo ""
echo "Discovery complete. Log saved: $LOG"
echo ""
echo "Next: inspect $LOG and look for voice topic names."
echo "Then run: make robot-voice-discover"
