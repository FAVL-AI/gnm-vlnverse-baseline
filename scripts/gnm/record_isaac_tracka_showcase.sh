#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="${1:-paper/showcase/recordings}"
DURATION="${2:-60}"
mkdir -p "$OUT_DIR"
OUT="$OUT_DIR/tracka_isaac_metrics_showcase.mp4"

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg is required. Install it with: sudo apt-get update && sudo apt-get install -y ffmpeg"
  exit 1
fi

DISPLAY_VALUE="${DISPLAY:-:0}"

# Full-screen X11 capture. Start this after Isaac opens and the HUD is visible.
ffmpeg -y \
  -video_size "${VIDEO_SIZE:-1280x720}" \
  -framerate 30 \
  -f x11grab \
  -i "${DISPLAY_VALUE}+${X_OFFSET:-0},${Y_OFFSET:-0}" \
  -t "$DURATION" \
  -c:v libx264 \
  -preset veryfast \
  -pix_fmt yuv420p \
  "$OUT"

echo "Saved recording: $OUT"
