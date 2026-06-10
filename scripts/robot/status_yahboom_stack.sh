#!/usr/bin/env bash
# status_yahboom_stack.sh — Show live status of Yahboom M3Pro robot stack.
#
# Run from the RTX desktop.  SSHes to the Jetson and shows:
#   - ros2 node list + topic list -t
#   - scan layout detection
#   - Hz for detected scan and odom topics
#   - publisher/subscriber counts for /cmd_vel and /camera/color/image_raw
#   - last 80 log lines from each tmux session
#   - Whether FleetSafe VLN controller is running on the desktop
#
# Usage:
#   bash scripts/robot/status_yahboom_stack.sh
#   make robot-status-yahboom
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
    echo "  [FAIL] Jetson unreachable — run: make robot-check"
    exit 1
fi

echo ""
echo "════════════════════════════════════════════════════════════════════"
echo "  FleetSafe  |  Yahboom Stack Status"
echo "  Jetson     : ${ROBOT}"
echo "════════════════════════════════════════════════════════════════════"
echo ""

# ── Jetson-side checks ────────────────────────────────────────────────────────
ssh "${SSH_OPTS[@]}" "${ROBOT}" 'bash -s' <<'REMOTE_EOF'
set -eo pipefail
set +u
source /opt/ros/humble/setup.bash 2>/dev/null || true
source "$HOME/yahboomcar_ws/install/setup.bash" 2>/dev/null || true
source "$HOME/mircoROS_agent/install/setup.bash" 2>/dev/null || true
set -u 2>/dev/null || true

export ROS_DOMAIN_ID="${FLEETSAFE_ROS_DOMAIN:-30}"
export ROS_LOCALHOST_ONLY=0

LOGDIR="$HOME/fleetsafe_robot_tools/logs"

echo "── Processes ────────────────────────────────────────────────────────────"
echo -n "  micro_ros_agent : "
pgrep -fa "micro_ros_agent\|MicroXRCEAgent" 2>/dev/null || echo "(not running)"
echo -n "  yahboomcar/base : "
pgrep -fa "ros2 launch" 2>/dev/null | grep -i "yahboom\|bringup\|M3Pro\|demo" || echo "(not running)"
echo -n "  camera (orbbec) : "
pgrep -fa "dabai\|orbbec\|camera_ros\|ros_orbbec" 2>/dev/null || echo "(not running / in bringup)"
echo ""

echo "── Session status ───────────────────────────────────────────────────────"
if command -v tmux &>/dev/null; then
    tmux ls 2>/dev/null | sed 's/^/  /' || echo "  (no tmux sessions)"
else
    echo "  (tmux not installed — checking nohup PID files)"
    for _pid_file in "$LOGDIR"/micro_ros.pid "$LOGDIR"/yahboom_base.pid \
                     "$LOGDIR"/yahboom_lidar.pid "$LOGDIR"/orbbec_camera.pid; do
        _name="$(basename "$_pid_file" .pid)"
        if [[ -f "$_pid_file" ]]; then
            _pid=$(cat "$_pid_file" 2>/dev/null || echo "")
            if [[ -n "$_pid" ]] && kill -0 "$_pid" 2>/dev/null; then
                echo "  [RUNNING]  fleetsafe_${_name}  PID=${_pid}"
            else
                echo "  [STOPPED]  fleetsafe_${_name}  (PID=${_pid:-?} not found)"
            fi
        else
            echo "  [NOT STARTED]  fleetsafe_${_name}"
        fi
    done
fi
echo ""

echo "── ros2 node list ───────────────────────────────────────────────────────"
NODES=$(timeout 5 ros2 node list 2>/dev/null || true)
if [[ -n "$NODES" ]]; then
    echo "$NODES" | sed 's/^/  /'
else
    echo "  (no nodes — robot stack not running)"
fi
echo ""

echo "── ros2 topic list -t (robot topics) ───────────────────────────────────"
TOPICS=$(timeout 5 ros2 topic list 2>/dev/null || true)
for T in /cmd_vel /odom_raw /odom /scan0 /scan1 /scan /scan_multi \
          /imu/data_raw /camera/color/image_raw /camera/depth/image_raw \
          /fleetsafe/certificate; do
    if echo "$TOPICS" | grep -qx "$T" 2>/dev/null; then
        TYPE=$(timeout 3 ros2 topic info "$T" 2>/dev/null | grep "Type:" | head -1 | awk '{print $2}' || echo "?")
        printf "  [OK]  %-40s  %s\n" "$T" "$TYPE"
    fi
done
echo ""

echo "── Scan layout detection ────────────────────────────────────────────────"
if echo "$TOPICS" | grep -qx "/scan0" && echo "$TOPICS" | grep -qx "/scan1"; then
    SCAN_LAYOUT="/scan0,/scan1"
elif echo "$TOPICS" | grep -qx "/scan" && echo "$TOPICS" | grep -qx "/scan_multi"; then
    SCAN_LAYOUT="/scan,/scan_multi"
elif echo "$TOPICS" | grep -qx "/scan0"; then
    SCAN_LAYOUT="/scan0"
elif echo "$TOPICS" | grep -qx "/scan"; then
    SCAN_LAYOUT="/scan"
else
    SCAN_LAYOUT="(none detected)"
fi
echo "  Scan topics: ${SCAN_LAYOUT}"

ODOM_TOPIC="/odom_raw"
echo "$TOPICS" | grep -qx "/odom_raw" || { echo "$TOPICS" | grep -qx "/odom" && ODOM_TOPIC="/odom"; } 2>/dev/null || true
echo "  Odom topic : ${ODOM_TOPIC}"
echo ""

echo "── /cmd_vel publisher / subscriber counts ───────────────────────────────"
CMD_INFO=$(timeout 4 ros2 topic info /cmd_vel 2>/dev/null || true)
if [[ -n "$CMD_INFO" ]]; then
    echo "$CMD_INFO" | grep -E "Type|Publisher|Subscriber" | sed 's/^/  /'
else
    echo "  /cmd_vel not in ROS graph"
fi
echo ""

echo "── /camera/color/image_raw publisher count ──────────────────────────────"
CAM_INFO=$(timeout 4 ros2 topic info /camera/color/image_raw 2>/dev/null || true)
if [[ -n "$CAM_INFO" ]]; then
    echo "$CAM_INFO" | grep -E "Type|Publisher|Subscriber" | sed 's/^/  /'
else
    echo "  /camera/color/image_raw not in ROS graph"
fi
echo ""

echo "── Hz measurements (5 s window) ─────────────────────────────────────────"
for T in $(echo "$SCAN_LAYOUT" | tr ',' ' ') "$ODOM_TOPIC"; do
    [[ "$T" == "(none"* ]] && continue
    printf "  %-30s " "${T}:"
    HZ=$(timeout 7 ros2 topic hz "$T" --window 5 2>/dev/null \
         | grep -oP '(?<=average rate: )\S+' | head -1 || true)
    if [[ -n "$HZ" ]]; then
        echo "${HZ} Hz"
    else
        echo "(no data)"
    fi
done
echo ""

echo "── Session log tails (last 80 lines each) ───────────────────────────────"
for _sess in fleetsafe_micro_ros fleetsafe_yahboom_base fleetsafe_yahboom_lidar fleetsafe_orbbec_camera; do
    case "$_sess" in
        fleetsafe_micro_ros)     _log="${LOGDIR}/micro_ros.log"      ; _pid_f="${LOGDIR}/micro_ros.pid"      ;;
        fleetsafe_yahboom_base)  _log="${LOGDIR}/yahboom_base.log"   ; _pid_f="${LOGDIR}/yahboom_base.pid"   ;;
        fleetsafe_yahboom_lidar) _log="${LOGDIR}/yahboom_lidar.log"  ; _pid_f="${LOGDIR}/yahboom_lidar.pid"  ;;
        fleetsafe_orbbec_camera) _log="${LOGDIR}/orbbec_camera.log"  ; _pid_f="${LOGDIR}/orbbec_camera.pid"  ;;
    esac

    # Determine running state: tmux → nohup pid → not started
    _STATE="[NOT STARTED]"
    if command -v tmux &>/dev/null && tmux has-session -t "$_sess" 2>/dev/null; then
        _STATE="[RUNNING - tmux]"
    elif [[ -f "$_pid_f" ]]; then
        _PID=$(cat "$_pid_f" 2>/dev/null || echo "")
        if [[ -n "$_PID" ]] && kill -0 "$_PID" 2>/dev/null; then
            _STATE="[RUNNING - nohup PID=${_PID}]"
        else
            _STATE="[STOPPED - nohup PID=${_PID:-?}]"
        fi
    fi

    echo ""
    echo "  ╔══ ${_sess} ══════════════════════════════════════════════"
    echo "  ║ ${_STATE}"
    if [[ -f "$_log" ]]; then
        echo "  ║ Log: ${_log}"
        tail -80 "$_log" | sed 's/^/  ║ /'
    else
        echo "  ║ (no log file yet)"
    fi
    echo "  ╚═══════════════════════════════════════════════════════════"
done
echo ""
REMOTE_EOF

# ── Desktop-side checks ───────────────────────────────────────────────────────
echo "── VLN Controller (desktop) ─────────────────────────────────────────────"
if pgrep -f "run_vln_m3pro.py" > /dev/null 2>&1; then
    echo "  [OK]  run_vln_m3pro.py is running (PID: $(pgrep -f run_vln_m3pro.py | head -1))"
else
    echo "  [--]  run_vln_m3pro.py not running"
    echo "        Start: make vln-desktop"
fi
echo ""
echo "════════════════════════════════════════════════════════════════════"
