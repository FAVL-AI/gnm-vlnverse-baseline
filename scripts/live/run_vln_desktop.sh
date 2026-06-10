#!/usr/bin/env bash
# run_vln_desktop.sh — Start the FleetSafe VLN controller on the RTX desktop.
#
# The VLN controller runs HERE (desktop).  The Jetson exposes robot topics
# (/scan0, /scan1, /odom_raw, /camera/color/image_raw, /cmd_vel) via DDS
# on ROS_DOMAIN_ID=30.  The controller subscribes to those topics and
# publishes /fleetsafe/cmd_vel_nominal, /fleetsafe/vln/parsed_instruction,
# /fleetsafe/certificate, and (in live mode) /cmd_vel.
#
# Usage:
#   bash scripts/live/run_vln_desktop.sh                   # DRY-RUN, radius 0.30
#   bash scripts/live/run_vln_desktop.sh --safety-radius 0.20   # closer objects
#   bash scripts/live/run_vln_desktop.sh --restart         # kill stale process first
#   CONFIRM_ENABLE_MOTION=YES bash scripts/live/run_vln_desktop.sh --enable-motion
#
# Safety:
#   --enable-motion requires CONFIRM_ENABLE_MOTION=YES in environment.
#   If /scan1 ≈ 0.28 m and safety-radius is 0.30, CBF will e-stop — correct.
#   Use --safety-radius 0.20 only for dry-run demos with nearby objects.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

# ── Defaults ──────────────────────────────────────────────────────────────────
SAFETY_RADIUS="0.30"
BACKBONE="auto"
ENABLE_MOTION=0
DO_RESTART=0

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --safety-radius) SAFETY_RADIUS="$2"; shift 2 ;;
        --backbone)      BACKBONE="$2";      shift 2 ;;
        --enable-motion) ENABLE_MOTION=1;    shift   ;;
        --restart)       DO_RESTART=1;       shift   ;;
        *) echo "[VLN] Unknown argument: $1"; exit 1 ;;
    esac
done

# ── Optional: kill stale controller process ──────────────────────────────────
if [[ "$DO_RESTART" -eq 1 ]]; then
    STALE=$(pgrep -f "run_vln_m3pro.py" || true)
    if [[ -n "$STALE" ]]; then
        echo "[VLN] --restart: killing stale run_vln_m3pro.py (PID $STALE)"
        kill "$STALE" 2>/dev/null || true
        sleep 1
    else
        echo "[VLN] --restart: no stale process found."
    fi
fi

# ── Abort if already running (without --restart) ─────────────────────────────
if pgrep -f "run_vln_m3pro.py" > /dev/null 2>&1; then
    echo "[VLN] ERROR: run_vln_m3pro.py is already running."
    echo "       Use --restart to kill and relaunch, or Ctrl+C the existing session."
    exit 1
fi

# ── Live-motion gate ──────────────────────────────────────────────────────────
MOTION_FLAGS=""
if [[ "$ENABLE_MOTION" -eq 1 ]]; then
    if [[ "${CONFIRM_ENABLE_MOTION:-}" != "YES" ]]; then
        echo ""
        echo "════════════════════════════════════════════════════════════════════"
        echo "  ⚠  REAL MOTION REQUESTED — CONFIRMATION REQUIRED"
        echo ""
        echo "  --enable-motion was passed but CONFIRM_ENABLE_MOTION is not YES."
        echo "  The robot WILL move at up to 0.12 m/s."
        echo ""
        echo "  To confirm:"
        echo "    CONFIRM_ENABLE_MOTION=YES bash scripts/live/run_vln_desktop.sh \\"
        echo "        --enable-motion --safety-radius ${SAFETY_RADIUS}"
        echo ""
        echo "  Checklist before enabling motion:"
        echo "    [ ] Area around robot is clear (≥ 1.5 m in all directions)"
        echo "    [ ] Hardware e-stop is within reach"
        echo "    [ ] LiDAR clearance is above safety-radius (${SAFETY_RADIUS} m)"
        echo "    [ ] make vln-check-stack passes"
        echo "════════════════════════════════════════════════════════════════════"
        echo ""
        exit 1
    fi
    MOTION_FLAGS="--enable-motion"

    # ── Sensor preflight gate ──────────────────────────────────────────────────
    # Hard-fail if any robot sensor is not publishing live data or LiDAR
    # clearance is below the safety radius.  Prevents the stale_lidar /
    # stale_odom e-stop pattern where the controller starts, finds no sensor
    # data, latches an e-stop, and writes refused certificates immediately.
    PREFLIGHT="${REPO_ROOT}/scripts/live/preflight_live_motion.sh"
    if [[ -f "$PREFLIGHT" ]]; then
        echo ""
        echo "[VLN] Running live-motion sensor preflight..."
        echo ""
        if ! SAFETY_RADIUS="${SAFETY_RADIUS}" bash "$PREFLIGHT"; then
            echo ""
            echo "[VLN] Live motion ABORTED — sensor preflight failed."
            echo "      Fix the issues listed above, then retry:"
            echo "        CONFIRM_ENABLE_MOTION=YES make vln-desktop-live"
            exit 1
        fi
        echo ""
    else
        echo "[VLN] WARNING: preflight_live_motion.sh not found — skipping sensor gate"
    fi

    echo ""
    echo "════════════════════════════════════════════════════════════════════"
    echo "  LIVE MOTION ENABLED — robot will move on instructions"
    echo "  safety-radius : ${SAFETY_RADIUS} m"
    echo "  backbone      : ${BACKBONE}"
    echo "  Press Ctrl+C at any time for emergency stop."
    echo "════════════════════════════════════════════════════════════════════"
    echo ""
    sleep 2
else
    echo "[VLN] Mode: DRY-RUN (no /cmd_vel published)"
fi

# ── Deactivate conda if active (avoids Python environment conflicts) ──────────
if [[ -n "${CONDA_DEFAULT_ENV:-}" ]]; then
    echo "[VLN] Deactivating conda env: ${CONDA_DEFAULT_ENV}"
    # shellcheck disable=SC1091
    source "$(conda info --base 2>/dev/null)/etc/profile.d/conda.sh" 2>/dev/null || true
    conda deactivate 2>/dev/null || true
fi

# ── Source ROS2 ───────────────────────────────────────────────────────────────
if ! command -v ros2 &>/dev/null; then
    # Temporarily disable nounset: ROS setup scripts access undefined variables
    # (AMENT_TRACE_SETUP_FILES and others) that trigger set -u errors.
    set +u
    # shellcheck source=/dev/null
    source /opt/ros/humble/setup.bash 2>/dev/null || true
    set -u
fi

export ROS_DOMAIN_ID=30
export ROS_LOCALHOST_ONLY=0

# ── Auto-detect scan and odometry topics ──────────────────────────────────────
# Query ros2 topic list to find which LiDAR layout the Jetson publishes.
# Silently falls back to /scan0,/scan1 if topics are not yet visible.
FLEETSAFE_SCAN_TOPICS="${FLEETSAFE_SCAN_TOPICS:-}"
FLEETSAFE_ODOM_TOPIC="${FLEETSAFE_ODOM_TOPIC:-}"
set +u
# shellcheck source=/dev/null
source <(bash "${REPO_ROOT}/scripts/live/detect_scan_topics.sh" 2>/dev/null) || true
set -u
SCAN_TOPICS_ARG="${FLEETSAFE_SCAN_TOPICS:-/scan0,/scan1}"
ODOM_TOPIC_ARG="${FLEETSAFE_ODOM_TOPIC:-/odom_raw}"
echo "[VLN] Scan topics : ${SCAN_TOPICS_ARG}"
echo "[VLN] Odom topic  : ${ODOM_TOPIC_ARG}"

# ── Output directories ────────────────────────────────────────────────────────
TRACE_DIR="results/vln_runs"
CERT_DIR="results/certificates"
mkdir -p "$TRACE_DIR" "$CERT_DIR"

# ── Banner ────────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════════════════"
echo "  FleetSafe-VLN  |  RTX Desktop Controller"
echo "  ROS_DOMAIN_ID  : ${ROS_DOMAIN_ID}"
echo "  Motion         : $([ "$ENABLE_MOTION" -eq 1 ] && echo 'ENABLED' || echo 'DRY-RUN')"
echo "  Backbone       : ${BACKBONE}"
echo "  Safety radius  : ${SAFETY_RADIUS} m"
echo "  Trace dir      : ${TRACE_DIR}"
echo "  Certs dir      : ${CERT_DIR}"
echo ""
echo "  Jetson topics expected:"
echo "    /scan0  /scan1  /odom_raw  /camera/color/image_raw  /cmd_vel"
echo ""
echo "  Send an instruction in a second terminal:"
echo "    make vln-send TEXT=\"move forward slowly\""
echo "    bash scripts/live/send_vln_instruction.sh move forward slowly"
echo "════════════════════════════════════════════════════════════════════"
echo ""

# ── Launch controller ─────────────────────────────────────────────────────────
exec /usr/bin/python3 scripts/real_robot/run_vln_m3pro.py \
    --backbone      "${BACKBONE}" \
    --safety-radius "${SAFETY_RADIUS}" \
    --scan-topics   "${SCAN_TOPICS_ARG}" \
    --odom-topic    "${ODOM_TOPIC_ARG}" \
    --trace-dir     "${TRACE_DIR}" \
    --cert-dir      "${CERT_DIR}" \
    ${MOTION_FLAGS}
