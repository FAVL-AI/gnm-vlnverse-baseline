#!/usr/bin/env bash
# watch_vln_outputs.sh — Echo VLN output topics.
#
# Usage:
#   bash scripts/live/watch_vln_outputs.sh parsed       # parsed instruction
#   bash scripts/live/watch_vln_outputs.sh nominal      # u_nom before CBF
#   bash scripts/live/watch_vln_outputs.sh certificate  # safety certificate
#   bash scripts/live/watch_vln_outputs.sh all          # instructions for all three
#
# Each mode runs ros2 topic echo on the corresponding topic (blocking).
# For "all", prints the commands to run in separate terminals.
set -euo pipefail

MODE="${1:-all}"

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

TOPIC_PARSED="/fleetsafe/vln/parsed_instruction"
TOPIC_NOMINAL="/fleetsafe/cmd_vel_nominal"
TOPIC_CERT="/fleetsafe/certificate"

echo "[VLN] ROS_DOMAIN_ID=${ROS_DOMAIN_ID}  mode=${MODE}"
echo ""

case "$MODE" in
    parsed)
        echo "[VLN] Watching ${TOPIC_PARSED}  (Ctrl+C to stop)"
        echo "      Each message shows the parsed action, label, confidence, and constraints."
        echo ""
        exec ros2 topic echo "$TOPIC_PARSED"
        ;;

    nominal)
        echo "[VLN] Watching ${TOPIC_NOMINAL}  (Ctrl+C to stop)"
        echo "      Shows the nominal velocity command (vx, wz) before CBF filtering."
        echo ""
        exec ros2 topic echo "$TOPIC_NOMINAL"
        ;;

    certificate)
        echo "[VLN] Watching ${TOPIC_CERT}  (Ctrl+C to stop)"
        echo "      Shows per-step safety certificate: h_min, qp_status, safe=true/false."
        echo ""
        exec ros2 topic echo "$TOPIC_CERT"
        ;;

    all)
        echo "ros2 topic echo is blocking — run each in its own terminal:"
        echo ""
        echo "  Terminal A — parsed instruction:"
        echo "    bash scripts/live/watch_vln_outputs.sh parsed"
        echo "    # or: make vln-watch-parsed"
        echo ""
        echo "  Terminal B — nominal velocity (pre-CBF):"
        echo "    bash scripts/live/watch_vln_outputs.sh nominal"
        echo "    # or: make vln-watch-nominal"
        echo ""
        echo "  Terminal C — safety certificate:"
        echo "    bash scripts/live/watch_vln_outputs.sh certificate"
        echo "    # or: make vln-watch-cert"
        echo ""
        echo "Topics:"
        echo "  ${TOPIC_PARSED}"
        echo "  ${TOPIC_NOMINAL}"
        echo "  ${TOPIC_CERT}"
        ;;

    *)
        echo "Usage: $0 {parsed|nominal|certificate|all}"
        exit 1
        ;;
esac
