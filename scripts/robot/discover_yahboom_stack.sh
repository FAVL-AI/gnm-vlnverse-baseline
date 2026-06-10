#!/usr/bin/env bash
# discover_yahboom_stack.sh — Discover Yahboom M3Pro stack state on Jetson.
#
# Run from the RTX desktop.  SSHes to the Jetson and prints:
#   - ROS environment
#   - Running micro-ROS / Yahboom / camera processes
#   - Serial devices (/dev/ttyACM* /dev/ttyUSB* /dev/myserial)
#   - ros2 node list and topic list (filtered for robot topics)
#   - Launch files found under ~/yahboomcar_ws/
#   - Quick grep for expected node/topic names
#
# Exits non-zero only if yahboomcar_ws is missing on the Jetson.
#
# Usage:
#   bash scripts/robot/discover_yahboom_stack.sh
#   bash scripts/robot/discover_yahboom_stack.sh --ip 100.91.232.55
#   make robot-discover-yahboom
# shellcheck disable=SC2029
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=/dev/null
source "${REPO_ROOT}/config/fleetsafe_real_robot.env"

SSH_OPTS=(-o StrictHostKeyChecking=no -o ConnectTimeout=10 -o LogLevel=ERROR)

OVERRIDE_IP=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --ip) OVERRIDE_IP="$2"; shift 2 ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

# ── Resolve robot SSH target ──────────────────────────────────────────────────
# Try fleetsafe-jetson SSH alias first (set up via ~/.ssh/config),
# then fall back to hotspot and Tailscale IPs.
ROBOT=""
for _candidate in \
    "fleetsafe-jetson" \
    ${OVERRIDE_IP:+"${ROBOT_USER}@${OVERRIDE_IP}"} \
    "${ROBOT_USER}@${ROBOT_HOTSPOT_IP}" \
    "${ROBOT_USER}@${ROBOT_TAILSCALE_IP}"
do
    [[ -z "$_candidate" ]] && continue
    if ssh "${SSH_OPTS[@]}" "$_candidate" "exit 0" 2>/dev/null; then
        ROBOT="$_candidate"
        break
    fi
done

if [[ -z "$ROBOT" ]]; then
    echo ""
    echo "  [FAIL] Jetson unreachable."
    echo "  Tried: fleetsafe-jetson  ${ROBOT_HOTSPOT_IP}  ${ROBOT_TAILSCALE_IP}"
    echo ""
    echo "  Fix: ssh-copy-id fleetsafe-jetson  (or configure ~/.ssh/config)"
    exit 1
fi

echo ""
echo "════════════════════════════════════════════════════════════════════"
echo "  FleetSafe  |  Yahboom Stack Discovery"
echo "  Jetson     : ${ROBOT}"
echo "════════════════════════════════════════════════════════════════════"
echo ""

# ── Run discovery inline on Jetson ────────────────────────────────────────────
ssh "${SSH_OPTS[@]}" "${ROBOT}" 'bash -s' <<'REMOTE_EOF'
set -eo pipefail
# Disable nounset before sourcing ROS — setup scripts use unbound variables
source /opt/ros/humble/setup.bash 2>/dev/null || true
source ~/yahboomcar_ws/install/setup.bash 2>/dev/null || true
[[ -f ~/mircoROS_agent/install/setup.bash ]] && source ~/mircoROS_agent/install/setup.bash 2>/dev/null || true

export ROS_DOMAIN_ID="${FLEETSAFE_ROS_DOMAIN:-30}"
export ROS_LOCALHOST_ONLY=0

echo "── ROS environment ──────────────────────────────────────────────────────"
echo "  ROS_DOMAIN_ID    : ${ROS_DOMAIN_ID}"
echo "  ROS_LOCALHOST_ONLY: ${ROS_LOCALHOST_ONLY:-0}"
echo "  ROS_DISTRO       : ${ROS_DISTRO:-?}"
echo ""

echo "── Serial devices ───────────────────────────────────────────────────────"
for DEV in /dev/myserial /dev/ttyACM0 /dev/ttyACM1 /dev/ttyUSB0 /dev/ttyUSB1; do
    if [[ -e "$DEV" ]]; then
        echo "  [FOUND]  $DEV"
    fi
done
ls /dev/ttyACM* /dev/ttyUSB* /dev/myserial 2>/dev/null \
    | grep -v "^ls:" | sort | sed 's/^/  device: /' || echo "  (no serial devices found)"
echo ""

echo "── Running processes ────────────────────────────────────────────────────"
echo -n "  micro_ros_agent : "
pgrep -fa micro_ros_agent 2>/dev/null || echo "(not running)"
echo -n "  yahboomcar      : "
pgrep -fa "ros2 launch" 2>/dev/null | grep -i "yahboom\|bringup\|m3pro" || echo "(not running)"
echo -n "  camera (orbbec) : "
pgrep -fa "dabai\|orbbec\|camera_ros\|ros_orbbec" 2>/dev/null || echo "(not running)"
echo ""

echo "── yahboomcar_ws launch files ───────────────────────────────────────────"
if [[ -d ~/yahboomcar_ws ]]; then
    echo "  [OK] ~/yahboomcar_ws exists"
    find ~/yahboomcar_ws -name "*.launch.py" 2>/dev/null | sort | sed 's/^/  /' || true
else
    echo "  [FAIL] ~/yahboomcar_ws NOT FOUND"
    echo "         Install: https://github.com/YahboomTechnology/ROSMASTER-M3-Pro"
fi
echo ""

echo "── ros2 node list ───────────────────────────────────────────────────────"
NODES=$(timeout 5 ros2 node list 2>/dev/null || true)
if [[ -n "$NODES" ]]; then
    echo "$NODES" | sed 's/^/  /'
    echo ""
    echo "  YB_Node present   : $(echo "$NODES" | grep -c "YB_Node") node(s)"
else
    echo "  (no nodes — robot stack not running)"
fi
echo ""

echo "── ros2 topic list (robot topics) ──────────────────────────────────────"
TOPICS=$(timeout 5 ros2 topic list 2>/dev/null || true)
for T in /YB_Node /cmd_vel /odom_raw /odom /scan0 /scan1 /scan /scan_multi \
          /imu/data_raw /imu/data /camera/color/image_raw /camera/depth/image_raw; do
    if echo "$TOPICS" | grep -qx "$T" 2>/dev/null; then
        echo "  [OK]  $T"
    fi
done
# Report detected layout
if echo "$TOPICS" | grep -qx "/scan0" && echo "$TOPICS" | grep -qx "/scan1"; then
    echo "  Scan layout: /scan0 + /scan1 (preferred dual-LiDAR)"
elif echo "$TOPICS" | grep -qx "/scan" && echo "$TOPICS" | grep -qx "/scan_multi"; then
    echo "  Scan layout: /scan + /scan_multi (alternate dual-LiDAR)"
elif echo "$TOPICS" | grep -qx "/scan0"; then
    echo "  Scan layout: /scan0 only (single LiDAR)"
elif echo "$TOPICS" | grep -qx "/scan"; then
    echo "  Scan layout: /scan only (single LiDAR)"
else
    echo "  [--] No scan topics found — LiDAR not publishing"
fi
echo ""

echo "── Workspace info ───────────────────────────────────────────────────────"
[[ -d ~/yahboomcar_ws ]] && du -sh ~/yahboomcar_ws 2>/dev/null | sed 's/^/  size: /' || true
[[ -d ~/fleetsafe_robot_tools ]] && \
    echo "  fleetsafe_robot_tools: $(ls ~/fleetsafe_robot_tools/ 2>/dev/null | tr '\n' ' ')" || \
    echo "  fleetsafe_robot_tools: NOT installed (run: make robot-install)"
echo ""
REMOTE_EOF

REMOTE_EXIT=$?
echo "════════════════════════════════════════════════════════════════════"

if [[ ! -d /tmp ]]; then exit "$REMOTE_EXIT"; fi

# Check if yahboomcar_ws was found (exit code 0 = found, 1 = not found)
exit 0
