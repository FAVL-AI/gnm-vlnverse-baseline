#!/usr/bin/env bash
# Record a Yahboom M3 Pro rosbag2 episode from Isaac Sim.
#
# Usage:
#   bash collect_yahboom_episode.sh [--episode-name NAME] [--duration SECONDS]
#                                   [--dry-run] [--strict]
#
# Flags:
#   --episode-name  Name of the episode directory (default: episode_001)
#   --duration      Recording duration in seconds (default: 60)
#   --dry-run       Print what would run; skip live recording. Exits 0.
#   --strict        Exit non-zero if ROS 2 unavailable or topic gate fails.
#                   Without --strict, exits 0 when Isaac Sim is absent.
#
# The topic gate (verify_yahboom_live_topics.py --strict) runs before recording
# starts. If it fails, recording is refused. This cannot be bypassed except by
# --dry-run.
#
# Output:
#   datasets/gnm_fleetsafe_rosbags/<episode_name>/rosbag/  (rosbag2 files)
#   datasets/gnm_fleetsafe_rosbags/<episode_name>/episode_metadata.json

set -euo pipefail

EPISODE_NAME="episode_001"
DURATION=60
DRY_RUN=false
STRICT=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --episode-name) EPISODE_NAME="$2"; shift 2 ;;
    --duration)     DURATION="$2";     shift 2 ;;
    --dry-run)      DRY_RUN=true;      shift ;;
    --strict)       STRICT=true;       shift ;;
    *) echo "[WARN] Unknown argument: $1"; shift ;;
  esac
done

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
EPISODE_DIR="$ROOT/datasets/gnm_fleetsafe_rosbags/$EPISODE_NAME"
BAG_DIR="$EPISODE_DIR/rosbag"
METADATA_FILE="$EPISODE_DIR/episode_metadata.json"
GATE_SCRIPT="$ROOT/scripts/gnm/verify_yahboom_live_topics.py"

CANONICAL_TOPICS=(
  "/camera/image_raw"
  "/odom"
  "/tf"
  "/scan"
  "/cmd_vel"
)

echo "============================================================"
echo " Yahboom M3 Pro Isaac Rosbag2 Episode Collector  [v2.4]"
echo "============================================================"
echo "Episode name : $EPISODE_NAME"
echo "Duration     : ${DURATION}s"
echo "Output dir   : $EPISODE_DIR"
echo "Dry-run      : $DRY_RUN"
echo "Strict       : $STRICT"
echo "============================================================"
echo ""

mkdir -p "$EPISODE_DIR"

# Build JSON array of topics.
TOPICS_JSON="["
for i in "${!CANONICAL_TOPICS[@]}"; do
  TOPICS_JSON+="\"${CANONICAL_TOPICS[$i]}\""
  [[ $i -lt $((${#CANONICAL_TOPICS[@]} - 1)) ]] && TOPICS_JSON+=", "
done
TOPICS_JSON+="]"

write_metadata() {
  local bag_recorded="$1"
  cat > "$METADATA_FILE" <<EOF
{
  "episode_name": "$EPISODE_NAME",
  "robot": "Yahboom ROSMASTER M3 Pro",
  "simulator": "isaac_sim",
  "milestone": "v2.4",
  "canonical_topics": $TOPICS_JSON,
  "duration_seconds": $DURATION,
  "bag_dir": "$BAG_DIR",
  "bag_recorded": $bag_recorded,
  "next_step": "python3 scripts/gnm/validate_yahboom_episode.py --episode-path $EPISODE_DIR",
  "notes": [
    "Isaac Sim must be running with Yahboom USD stage loaded.",
    "All five canonical topics must publish non-zero messages.",
    "Drive the robot in Isaac Sim during recording.",
    "Validate the bag before converting to GNM format."
  ],
  "dry_run": $DRY_RUN
}
EOF
}

if $DRY_RUN; then
  write_metadata false
  echo "[DRY-RUN] Episode metadata written to: $METADATA_FILE"
  echo ""
  echo "[DRY-RUN] Skipping topic gate and live recording."
  echo "[DRY-RUN] In live mode, the recording sequence is:"
  echo ""
  echo "  1. python3 $GATE_SCRIPT --strict"
  echo "     (must exit 0 before recording starts)"
  echo ""
  echo "  2. ros2 bag record \\"
  for topic in "${CANONICAL_TOPICS[@]}"; do
    echo "       $topic \\"
  done
  echo "       --output $BAG_DIR \\"
  echo "       --max-bag-duration $DURATION"
  echo ""
  echo "  3. python3 scripts/gnm/validate_yahboom_episode.py \\"
  echo "       --episode-path $EPISODE_DIR"
  echo ""
  echo "[OK] Dry-run complete."
  exit 0
fi

# Source ROS 2 if available.
for setup_file in \
    /opt/ros/humble/setup.bash \
    /opt/ros/jazzy/setup.bash \
    /opt/ros/iron/setup.bash; do
  if [[ -f "$setup_file" ]]; then
    set +u
    # shellcheck source=/dev/null
    source "$setup_file" 2>/dev/null || true
    set -u
    echo "[INFO] Sourced ROS 2 from: $setup_file"
    break
  fi
done

if ! command -v ros2 &>/dev/null; then
  write_metadata false
  echo "[INFO] ros2 command not found."
  echo "[INFO] Episode metadata written (bag_recorded: false)."
  echo "[INFO] Install ROS 2, start Isaac Sim, and re-run without --dry-run"
  echo "[INFO] to record a real episode."
  if $STRICT; then
    echo ""
    echo "[FAIL] --strict mode: ROS 2 is required."
    exit 1
  fi
  echo "[OK] Exiting 0 (non-strict mode)."
  exit 0
fi

# Hard gate: verify canonical topics before recording.
echo "------------------------------------------------------------"
echo " Topic gate check (mandatory before recording)"
echo "------------------------------------------------------------"
echo ""

if ! python3 "$GATE_SCRIPT" --strict; then
  echo ""
  echo "[FAIL] Topic gate failed. Recording refused."
  echo "[FAIL] Fix the topic gate before attempting to record."
  echo ""
  echo "[HINT] Steps to fix:"
  echo "  1. Confirm Isaac Sim is open and in Play mode."
  echo "  2. Confirm the Yahboom USD stage is loaded (not Nova Carter)."
  echo "  3. Confirm ROS 2 Bridge extension is enabled."
  echo "  4. Confirm all five OmniGraph nodes are connected and topic names match."
  echo "  5. Re-run: python3 $GATE_SCRIPT --strict"
  exit 1
fi

echo ""
echo "[OK] Topic gate passed. Starting recording."
echo ""
echo "------------------------------------------------------------"
echo " Recording episode: $EPISODE_NAME  (${DURATION}s)"
echo "------------------------------------------------------------"
echo ""
echo "Drive the robot in Isaac Sim toward a goal during recording."
echo "The episode must show navigable movement, not the robot standing still."
echo ""

ros2 bag record \
  "${CANONICAL_TOPICS[@]}" \
  --output "$BAG_DIR" \
  --max-bag-duration "$DURATION"

echo ""
echo "[OK] Recording complete."

write_metadata true
echo "[OK] Episode metadata written to: $METADATA_FILE"

echo ""
echo "------------------------------------------------------------"
echo " Next step: validate the episode"
echo "------------------------------------------------------------"
echo ""
echo "  python3 scripts/gnm/validate_yahboom_episode.py \\"
echo "    --episode-path $EPISODE_DIR"
echo ""
echo "All five topics must have message_count > 0 before v2.5 conversion."
