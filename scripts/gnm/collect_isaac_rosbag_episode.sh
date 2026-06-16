#!/usr/bin/env bash
# Collect a rosbag2 episode from Isaac Sim.
# Usage: bash collect_isaac_rosbag_episode.sh <episode_name> [--dry-run] [--strict]
#
# By default operates in dry-run-safe mode: writes episode metadata and exits 0
# even when ROS 2 is not installed. With --strict, exits non-zero if ROS 2
# is missing. With --dry-run, always skips live bag recording.

set -euo pipefail

EPISODE_NAME="${1:-episode_001}"
DRY_RUN=false
STRICT=false

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --strict)  STRICT=true ;;
  esac
done

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
OUTPUT_ROOT="$ROOT/datasets/gnm_fleetsafe_rosbags"
EPISODE_DIR="$OUTPUT_ROOT/$EPISODE_NAME"
METADATA_FILE="$EPISODE_DIR/episode_metadata.json"

REQUIRED_TOPICS=(
  "/camera/image_raw"
  "/odom"
  "/tf"
  "/scan"
  "/gnm/cmd_vel_raw"
  "/fleetsafe/cmd_vel_safe"
  "/cmd_vel"
)

echo "============================================================"
echo " FleetSafe-GNM Isaac Rosbag Episode Collector"
echo "============================================================"
echo "Episode name : $EPISODE_NAME"
echo "Output dir   : $EPISODE_DIR"
echo "Dry-run      : $DRY_RUN"
echo "Strict       : $STRICT"
echo "============================================================"

mkdir -p "$EPISODE_DIR"

# Build JSON array of required topics.
TOPICS_JSON="["
for i in "${!REQUIRED_TOPICS[@]}"; do
  TOPICS_JSON+="\"${REQUIRED_TOPICS[$i]}\""
  [[ $i -lt $((${#REQUIRED_TOPICS[@]} - 1)) ]] && TOPICS_JSON+=", "
done
TOPICS_JSON+="]"

# Write episode metadata regardless of ROS 2 availability.
cat > "$METADATA_FILE" <<EOF
{
  "episode_name": "$EPISODE_NAME",
  "required_topics": $TOPICS_JSON,
  "expected_output": {
    "rosbag_dir": "$EPISODE_DIR",
    "metadata_file": "$METADATA_FILE",
    "contents": [
      "rosbag2 directory with recorded sensor and command topics",
      "episode_metadata.json"
    ]
  },
  "simulator": "isaac_sim",
  "robot": "yahboom_rosmaster_m3_pro",
  "notes": [
    "Isaac Sim must be running with the ROS 2 bridge enabled.",
    "The robot must be active in the Isaac scene before recording starts.",
    "Drive the robot manually or run an exploration policy during recording.",
    "Stop the recording after the episode is complete.",
    "Convert this bag to GNM format using convert_rosbag_to_gnm_dataset.py."
  ],
  "dry_run": $DRY_RUN
}
EOF

echo "[OK] Episode metadata written to: $METADATA_FILE"

if $DRY_RUN; then
  echo ""
  echo "[DRY-RUN] Skipping live bag recording."
  echo "[DRY-RUN] In live mode, the following command would run:"
  echo "  ros2 bag record \\"
  for topic in "${REQUIRED_TOPICS[@]}"; do
    echo "    $topic \\"
  done
  echo "    --output $EPISODE_DIR/rosbag"
  echo ""
  echo "[OK] Dry-run complete."
  exit 0
fi

# Source ROS 2 if available.
# Temporarily disable -u because ROS 2 setup scripts reference unbound variables.
for setup_file in \
    /opt/ros/humble/setup.bash \
    /opt/ros/jazzy/setup.bash \
    /opt/ros/iron/setup.bash; do
  if [[ -f "$setup_file" ]]; then
    set +u
    # shellcheck source=/dev/null
    source "$setup_file" 2>/dev/null || true
    set -u
    echo "Sourced ROS 2 from: $setup_file"
    break
  fi
done

if ! command -v ros2 &>/dev/null; then
  echo ""
  echo "[INFO] ros2 not found. Live bag recording skipped."
  echo "[INFO] Metadata written. Run with ROS 2 installed and Isaac Sim running"
  echo "[INFO] to record a real episode."
  if $STRICT; then
    echo "[FAIL] --strict mode: ROS 2 is required."
    exit 1
  fi
  echo "[OK] Exiting 0 (non-strict mode)."
  exit 0
fi

echo ""
echo "Starting rosbag2 recording for episode: $EPISODE_NAME"
echo "Output: $EPISODE_DIR/rosbag"
echo "Press Ctrl+C to stop recording when the episode is complete."
echo ""

TOPIC_ARGS=()
for topic in "${REQUIRED_TOPICS[@]}"; do
  TOPIC_ARGS+=("$topic")
done

ros2 bag record "${TOPIC_ARGS[@]}" --output "$EPISODE_DIR/rosbag"

echo ""
echo "[OK] Rosbag recording complete: $EPISODE_DIR/rosbag"
