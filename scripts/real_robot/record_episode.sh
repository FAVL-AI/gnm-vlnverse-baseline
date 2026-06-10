#!/bin/bash
# Record one episode on the real Yahboom robot.
# Usage: ./scripts/real_robot/record_episode.sh robot=yahboom task=safe_path

set -e

TASK=${1:-safe_path}
RECORD=true
OUTPUT_DIR=${OUTPUT_DIR:-"data/episodes/real"}

echo "=== Fleet-Safe Real Robot Episode Recorder ==="
echo "Task: $TASK | Record: $RECORD | Output: $OUTPUT_DIR"

# Source ROS2
source /opt/ros/humble/setup.bash
WS_INSTALL="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/ros2_ws/install"
[[ -f "$WS_INSTALL/setup.bash" ]] && source "$WS_INSTALL/setup.bash" || true

# Launch the full real robot stack in background
ros2 launch fleet_safe_yahboom_bringup real_robot.launch.py \
    record:="$RECORD" \
    policy:="" \
    &
LAUNCH_PID=$!
trap "kill $LAUNCH_PID 2>/dev/null" EXIT

sleep 3   # wait for nodes to start

# Wait for episode to complete (watch /fleet_safe/episode_status)
echo "[recorder] Waiting for episode completion..."
timeout 120 ros2 topic echo --once /fleet_safe/episode_status 2>/dev/null || true

echo "[recorder] Episode complete. Data in: $OUTPUT_DIR"
