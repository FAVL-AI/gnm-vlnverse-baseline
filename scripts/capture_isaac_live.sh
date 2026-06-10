#!/usr/bin/env bash
# scripts/capture_isaac_live.sh
# Continuous Isaac Sim window capture for the live dashboard view.
#
# Writes every INTERVAL seconds:
#   command-center/frontend/public/live/isaac_live.png  (served as /live/isaac_live.png)
#   evidence/fleetsafe_vlnverse_plus/live/isaac_live.png
#   evidence/fleetsafe_vlnverse_plus/live/live_status.json
#
# Usage:
#   bash scripts/capture_isaac_live.sh          # 1-second interval (default)
#   bash scripts/capture_isaac_live.sh 0.5      # 0.5-second interval
#
# Prerequisites (Ubuntu):
#   sudo apt install -y xdotool imagemagick
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INTERVAL="${1:-1}"

LIVE_DIR="${REPO_ROOT}/command-center/frontend/public/live"
EV_LIVE_DIR="${REPO_ROOT}/evidence/fleetsafe_vlnverse_plus/live"
FRAME_PATH="${LIVE_DIR}/isaac_live.png"
EV_FRAME_PATH="${EV_LIVE_DIR}/isaac_live.png"
STATUS_FILE="${EV_LIVE_DIR}/live_status.json"

mkdir -p "${LIVE_DIR}" "${EV_LIVE_DIR}"

# ── Detect best capture tool ─────────────────────────────────────────────────
CAPTURE_TOOL=""
if command -v xdotool &>/dev/null && command -v import &>/dev/null; then
    CAPTURE_TOOL="xdotool_import"
elif command -v gnome-screenshot &>/dev/null; then
    CAPTURE_TOOL="gnome-screenshot"
elif command -v scrot &>/dev/null; then
    CAPTURE_TOOL="scrot"
elif command -v spectacle &>/dev/null; then
    CAPTURE_TOOL="spectacle"
fi

if [[ -z "${CAPTURE_TOOL}" ]]; then
    echo "[WARN] No window capture tool found."
    echo "  Install: sudo apt install -y xdotool imagemagick"
    CAPTURE_TOOL="none"
fi

# ── Status writer ────────────────────────────────────────────────────────────
write_status() {
    local window_found="$1"
    local message="$2"
    python3 -c "
import json; from datetime import datetime, timezone; from pathlib import Path
Path('${STATUS_FILE}').write_text(json.dumps({
    'last_frame_time': datetime.now(timezone.utc).isoformat(),
    'window_found': ${window_found},
    'frame_path': '${EV_FRAME_PATH}',
    'capture_tool': '${CAPTURE_TOOL}',
    'message': '$message',
}, indent=2))
" 2>/dev/null || true
}

echo "========================================"
echo "  FleetSafe — Isaac Live Capture"
echo "  Interval: ${INTERVAL}s   Tool: ${CAPTURE_TOOL}"
echo "  Output: ${FRAME_PATH}"
echo "========================================"
echo "  Dashboard: http://localhost:3000/dashboard/vln-hub"
echo "  Direct:    http://localhost:3000/live/isaac_live.png"
echo ""
echo "  Press Ctrl+C to stop."
echo ""

# ── Capture loop ─────────────────────────────────────────────────────────────
while true; do
    WINDOW_FOUND=false
    CAPTURED=false

    case "${CAPTURE_TOOL}" in
        xdotool_import)
            WIN=$(xdotool search --name "Isaac Sim" 2>/dev/null | head -n 1 || echo "")
            if [[ -n "${WIN}" ]]; then
                WINDOW_FOUND=true
                if import -window "${WIN}" "${FRAME_PATH}" 2>/dev/null; then
                    CAPTURED=true
                fi
            fi
            ;;
        gnome-screenshot)
            if gnome-screenshot -f "${FRAME_PATH}" 2>/dev/null; then
                CAPTURED=true
                WINDOW_FOUND=true
            fi
            ;;
        scrot)
            if scrot "${FRAME_PATH}" 2>/dev/null; then
                CAPTURED=true
                WINDOW_FOUND=true
            fi
            ;;
        spectacle)
            if spectacle -b -o "${FRAME_PATH}" 2>/dev/null; then
                CAPTURED=true
                WINDOW_FOUND=true
            fi
            ;;
        none)
            write_status "false" "No capture tool installed — sudo apt install -y xdotool imagemagick"
            echo "[BLOCKED] No capture tool. Install: sudo apt install -y xdotool imagemagick"
            sleep 5
            continue
            ;;
    esac

    NOW=$(date -u +%H:%M:%S)
    if "${CAPTURED}"; then
        cp "${FRAME_PATH}" "${EV_FRAME_PATH}" 2>/dev/null || true
        write_status "true" "Frame captured at ${NOW} UTC"
        echo "[OK] ${NOW} — frame captured (${FRAME_PATH})"
    elif "${WINDOW_FOUND}"; then
        write_status "true" "Isaac window found but capture failed at ${NOW}"
        echo "[WARN] ${NOW} — window found but capture failed"
    else
        write_status "false" "Isaac Sim window not found at ${NOW} — is Isaac open?"
        echo "[WAIT] ${NOW} — Isaac Sim not found"
    fi

    sleep "${INTERVAL}"
done
