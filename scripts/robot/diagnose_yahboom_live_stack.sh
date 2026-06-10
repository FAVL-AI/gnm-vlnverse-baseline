#!/usr/bin/env bash
# diagnose_yahboom_live_stack.sh — Deep diagnostic of Yahboom M3Pro live stack.
#
# SSHes to fleetsafe-jetson and collects everything needed to identify the
# correct launch files, verify sensor connectivity, and diagnose startup issues.
#
# Output sections:
#   1. System / ROS environment
#   2. Serial devices and USB bus
#   3. Running processes
#   4. Launch file discovery + mobile-base scoring
#   5. ROS package list (filtered)
#   6. ROS graph: node list, topic list, topic info
#   7. Topic data quality (Hz, message receipt)
#   8. Recommendations
#
# Usage:
#   bash scripts/robot/diagnose_yahboom_live_stack.sh
#   make robot-diagnose-yahboom
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

# ── Resolve SSH target ────────────────────────────────────────────────────────
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
    echo "  [FAIL] Jetson unreachable"
    exit 1
fi

echo ""
echo "════════════════════════════════════════════════════════════════════"
echo "  FleetSafe  |  Yahboom Stack Deep Diagnostic"
echo "  Jetson     : ${ROBOT}"
echo "════════════════════════════════════════════════════════════════════"
echo ""

ssh "${SSH_OPTS[@]}" "${ROBOT}" 'bash -s' <<'REMOTE_EOF'
set -eo pipefail
set +u
source /opt/ros/humble/setup.bash                      2>/dev/null || true
source "$HOME/yahboomcar_ws/install/setup.bash"        2>/dev/null || true
source "$HOME/mircoROS_agent/install/setup.bash"       2>/dev/null || true
source "$HOME/M3Pro_ws/install/setup.bash"             2>/dev/null || true
set -u 2>/dev/null || true
export ROS_DOMAIN_ID="${FLEETSAFE_ROS_DOMAIN:-30}"
export ROS_LOCALHOST_ONLY=0

# ── 1. System / ROS environment ───────────────────────────────────────────────
echo "── 1. System / ROS environment ─────────────────────────────────────────"
echo "  hostname       : $(hostname)"
echo "  ROS_DOMAIN_ID  : ${ROS_DOMAIN_ID}"
echo "  ROS_DISTRO     : ${ROS_DISTRO:-?}"
echo "  ROS_LOCALHOST_ONLY: ${ROS_LOCALHOST_ONLY:-0}"
echo "  tmux           : $(command -v tmux 2>/dev/null || echo NOT INSTALLED)"
echo "  micro_ros_agent: $(command -v micro_ros_agent 2>/dev/null || echo not in PATH)"
echo "  ros2 pkg micro_ros_agent: $(ros2 pkg prefix micro_ros_agent 2>/dev/null && echo OK || echo NOT FOUND)"
echo ""

# ── 2. Serial devices ─────────────────────────────────────────────────────────
echo "── 2. Serial devices ───────────────────────────────────────────────────"
echo "  MCU (micro-ROS): ttyUSB* ttyACM* /dev/myserial"
ls /dev/ttyUSB* /dev/ttyACM* /dev/myserial 2>/dev/null | sed 's/^/    /' || echo "    (none found)"
echo ""
echo "  LiDAR (Jetson hw UART): ttyTHS1 ttyTHS2"
ls /dev/ttyTHS* 2>/dev/null | sed 's/^/    /' || echo "    (none found — M3Pro LiDARs should be here)"
echo ""
echo "  /dev/serial/by-id/:"
ls /dev/serial/by-id/ 2>/dev/null | sed 's/^/    /' || echo "    (none found)"
echo ""
echo "  lsusb:"
lsusb 2>/dev/null | sed 's/^/    /' || echo "    (lsusb not available)"
echo ""

# ── 3. Running processes ──────────────────────────────────────────────────────
echo "── 3. Running processes ────────────────────────────────────────────────"
echo -n "  micro_ros_agent : "
pgrep -fa "micro_ros_agent\|MicroXRCEAgent" 2>/dev/null || echo "(not running)"
echo -n "  ros2 launch     : "
pgrep -fa "ros2 launch" 2>/dev/null || echo "(not running)"
echo -n "  lidar/laser     : "
pgrep -fa "laser\|lidar\|tmini\|tof_driver" 2>/dev/null || echo "(none)"
echo -n "  camera          : "
pgrep -fa "orbbec\|dabai\|camera_ros" 2>/dev/null || echo "(none)"
echo ""
echo "  tmux sessions:"
tmux ls 2>/dev/null | sed 's/^/    /' || echo "    (no tmux sessions)"
echo ""

# ── 4. Launch file discovery + mobile-base scoring ────────────────────────────
echo "── 4. Launch file discovery + scoring ──────────────────────────────────"
echo "   M3Pro nav pipeline scoring:"
echo "   +15=ekf/robot_localization, +10=imu_filter, +10=laser_merge/ira_laser_tools"
echo "   +20=YB_Node/RobotBase (legacy bringup), +10=odom_raw"
echo "   -30=MoveIt/arm, -25=planning/warehouse"
echo "   NOTE: YB_Node comes from micro-ROS (STM32), NOT from launch files."
echo ""

# Scoring function — recognises both legacy (YB_Node) and current (slam_mapping) bringups
_score_base() {
    local f="$1" c s=0
    c=$(cat "$f" 2>/dev/null || echo "")
    # Navigation pipeline (M3Pro slam_mapping/bringup.launch.py)
    echo "$c" | grep -qi "ekf\|robot_localization"                                && s=$((s+15))
    echo "$c" | grep -qi "imu_filter\|imu_tools\|imu_filter_madgwick"             && s=$((s+10))
    echo "$c" | grep -qi "laser_merge\|ira_laser_tools\|laserscan_multi"          && s=$((s+10))
    # Legacy mobile-base indicators
    echo "$c" | grep -qi "YB_Node\|RobotBase\|base_controller\|yahboom_base"      && s=$((s+20))
    echo "$c" | grep -qi "\bodom_raw\b"                                           && s=$((s+10))
    echo "$c" | grep -qi "cmd_vel"                                                && s=$((s+5))
    echo "$c" | grep -qi "micro_ros\|serial.*mcu\|stm32"                         && s=$((s+5))
    # Hard exclude: MoveIt/arm configs
    echo "$c" | grep -qi "moveit\|MoveItCpp\|move_group\|MoveGroupInterface"      && s=$((s-30))
    echo "$c" | grep -qi "planning_scene\|spawn_controllers\|warehouse_db\|setup_assistant\|static_virtual_joint" \
                                                                                  && s=$((s-25))
    echo $s
}

_score_lidar() {
    local f="$1" c s=0
    c=$(cat "$f" 2>/dev/null || echo "")
    echo "$c" | grep -qi "\bscan0\b\|\bscan1\b"                                  && s=$((s+20))
    echo "$c" | grep -qi "laser_driver\|lidar\|tof\|tmini\|multi_merger"         && s=$((s+15))
    echo "$c" | grep -qi "scan_multi\|merger"                                    && s=$((s+10))
    echo "$c" | grep -qi "laser\|scan"                                           && s=$((s+5))
    echo "$c" | grep -qi "moveit\|arm\|move_group"                               && s=$((s-20))
    echo $s
}

ALL_LAUNCHES=$(find "$HOME/yahboomcar_ws" "$HOME/M3Pro_ws" \
    -name "*.launch.py" 2>/dev/null | sort || true)

BEST_BASE_SCORE=-999; BEST_BASE_FILE=""
BEST_LIDAR_SCORE=-999; BEST_LIDAR_FILE=""

echo "  BASE LAUNCH CANDIDATES:"
while IFS= read -r lf; do
    [[ -z "$lf" ]] && continue
    bs=$(_score_base "$lf")
    ls=$(_score_lidar "$lf")
    if [[ $bs -gt 0 ]]; then
        printf "  %+4d  [BASE]  %s\n" "$bs" "$lf"
        if [[ $bs -gt $BEST_BASE_SCORE ]]; then
            BEST_BASE_SCORE=$bs; BEST_BASE_FILE="$lf"
        fi
    elif [[ $bs -lt 0 ]]; then
        printf "  %+4d  [EXCL]  %s\n" "$bs" "$lf"
    fi
    if [[ $ls -gt 0 && $bs -ge 0 ]]; then
        if [[ $ls -gt $BEST_LIDAR_SCORE ]]; then
            BEST_LIDAR_SCORE=$ls; BEST_LIDAR_FILE="$lf"
        fi
    fi
done <<< "$ALL_LAUNCHES"

echo ""
echo "  LIDAR LAUNCH CANDIDATES (separate lidar launch files):"
while IFS= read -r lf; do
    [[ -z "$lf" ]] && continue
    ls=$(_score_lidar "$lf")
    if [[ $ls -gt 5 ]]; then
        printf "  %+4d  [LIDAR] %s\n" "$ls" "$lf"
        if [[ $ls -gt $BEST_LIDAR_SCORE ]]; then
            BEST_LIDAR_SCORE=$ls; BEST_LIDAR_FILE="$lf"
        fi
    fi
done <<< "$ALL_LAUNCHES"

echo ""
echo "  ── Recommendations ──────────────────────────────────────────────"
if [[ -n "$BEST_BASE_FILE" ]]; then
    echo "  Best BASE  (score=$BEST_BASE_SCORE): ${BEST_BASE_FILE}"
    echo "  Override:  export FLEETSAFE_YAHBOOM_BASE_LAUNCH=${BEST_BASE_FILE}"
else
    echo "  [WARN] No mobile-base launch file found with positive score."
    echo "         Try: grep -rl 'YB_Node\|cmd_vel\|odom_raw' ~/yahboomcar_ws/src/"
fi
if [[ -n "$BEST_LIDAR_FILE" ]]; then
    echo "  Best LIDAR (score=$BEST_LIDAR_SCORE): ${BEST_LIDAR_FILE}"
    echo "  Override:  export FLEETSAFE_YAHBOOM_LIDAR_LAUNCH=${BEST_LIDAR_FILE}"
fi
echo ""

# ── 5. Key keyword grep across all source files ────────────────────────────────
echo "── 5. Source code keyword search ───────────────────────────────────────"
for kw in YB_Node cmd_vel odom_raw scan0 scan1 micro_ros ttyUSB ttyACM; do
    hits=$(grep -rl "$kw" "$HOME/yahboomcar_ws/src/" "$HOME/M3Pro_ws/src/" 2>/dev/null | head -5 || true)
    if [[ -n "$hits" ]]; then
        echo "  '$kw' found in:"
        echo "$hits" | sed 's/^/    /'
    else
        echo "  '$kw' NOT found in src/"
    fi
done
echo ""

# ── 6. ROS packages matching mobile-base keywords ────────────────────────────
echo "── 6. Installed ROS packages (mobile-base keywords) ─────────────────────"
ros2 pkg list 2>/dev/null | grep -iE "yahboom|m3pro|base|laser|lidar|car|driver|robot|serial|micro" | sed 's/^/  /' || echo "  (none / ros2 not running)"
echo ""

# ── 7. ROS graph ─────────────────────────────────────────────────────────────
echo "── 7. ROS graph ────────────────────────────────────────────────────────"
echo "  ros2 node list:"
timeout 6 ros2 node list 2>/dev/null | sed 's/^/    /' || echo "    (no nodes)"
echo ""
echo "  ros2 topic list -t:"
timeout 6 ros2 topic list -t 2>/dev/null | sed 's/^/    /' || echo "    (no topics)"
echo ""

echo "  Topic info for key topics:"
for T in /cmd_vel /odom_raw /odom /scan0 /scan1 /scan /scan_multi; do
    INFO=$(timeout 5 ros2 topic info "$T" 2>/dev/null || true)
    if [[ -n "$INFO" ]]; then
        printf "\n  %s:\n" "$T"
        echo "$INFO" | sed 's/^/    /'
    fi
done
echo ""

# ── 8. Topic data quality ─────────────────────────────────────────────────────
echo "── 8. Topic data quality (5 s window each) ──────────────────────────────"
TOPICS=$(timeout 5 ros2 topic list 2>/dev/null || true)
for T in /scan0 /scan1 /scan /scan_multi /odom_raw /odom /cmd_vel \
          /camera/color/image_raw; do
    echo "$TOPICS" | grep -qx "$T" || continue
    printf "  %-35s " "${T}:"
    HZ=$(timeout 7 ros2 topic hz "$T" --window 5 \
             --qos-reliability best_effort --qos-durability volatile \
             2>/dev/null | grep -oP '(?<=average rate: )\S+' | head -1 || true)
    if [[ -n "$HZ" ]]; then
        echo "${HZ} Hz"
    else
        # Try without QoS flags as fallback
        HZ2=$(timeout 7 ros2 topic hz "$T" --window 5 2>/dev/null \
              | grep -oP '(?<=average rate: )\S+' | head -1 || true)
        [[ -n "$HZ2" ]] && echo "${HZ2} Hz (reliable QoS)" || echo "[NO DATA]"
    fi
done
echo ""

# ── 9. micro_ros_agent log tail ───────────────────────────────────────────────
echo "── 9. micro_ros_agent log (last 40 lines) ───────────────────────────────"
AGENT_LOG="$HOME/fleetsafe_robot_tools/logs/micro_ros.log"
if [[ -f "$AGENT_LOG" ]]; then
    echo "  Log: ${AGENT_LOG}"
    tail -40 "$AGENT_LOG" | sed 's/^/  /'
else
    echo "  Log not found at ${AGENT_LOG}"
    echo "  Check: pgrep -fa micro_ros_agent"
fi
echo ""

# ── 10. Recommendations summary ──────────────────────────────────────────────
echo "── 10. Recommendations ─────────────────────────────────────────────────"
TOPICS2=$(timeout 5 ros2 topic list 2>/dev/null || true)
NODES2=$(timeout 5 ros2 node list 2>/dev/null || true)

_ok()  { echo "  [OK]  $*"; }
_warn(){ echo "  [!]   $*"; }

echo "$NODES2" | grep -q "YB_Node" && _ok "/YB_Node present (micro-ROS connected)" || \
    _warn "No /YB_Node — micro_ros_agent not connected to STM32 firmware"
echo "$TOPICS2" | grep -qx "/cmd_vel" && _ok "/cmd_vel present" || \
    _warn "/cmd_vel missing (needs /YB_Node)"
echo "$TOPICS2" | grep -qx "/odom_raw" && _ok "/odom_raw present" || \
    _warn "/odom_raw missing — micro_ros_agent not connected (check log for 'Create session')"
echo "$TOPICS2" | grep -qx "/scan0" && _ok "/scan0 present" || \
    _warn "/scan0 missing — start ldlidar_stl_ros2_node on ttyTHS1 with topic_name:=scan0"
echo "$TOPICS2" | grep -qx "/scan1" && _ok "/scan1 present" || \
    _warn "/scan1 missing — start ldlidar_stl_ros2_node on ttyTHS2 with topic_name:=scan1"
echo "$TOPICS2" | grep -qx "/camera/color/image_raw" && _ok "/camera/color/image_raw present" || \
    _warn "/camera/color/image_raw missing"

# Check for two micro_ros_agent instances (causes port contention)
_AGENT_COUNT=$(pgrep -c -f "micro_ros_agent\|MicroXRCEAgent" 2>/dev/null || echo 0)
if [[ "$_AGENT_COUNT" -gt 1 ]]; then
    _warn "MULTIPLE micro_ros_agent processes ($_AGENT_COUNT) — port contention prevents STM32 connection!"
    _warn "Fix: kill all, then start ONLY the Yahboom binary:"
    _warn "  pkill -f micro_ros_agent"
    _warn "  ~/mircoROS_agent/install/micro_ros_agent/lib/micro_ros_agent/micro_ros_agent serial --dev /dev/serial/by-id/... -b 921600 -v4"
fi

command -v tmux &>/dev/null || \
    _warn "tmux not installed — make robot-install-jetson-deps"

echo ""
echo "  M3Pro architecture notes:"
echo "    /YB_Node, /odom_raw, /imu/data_raw, /cmd_vel come from micro-ROS (STM32 firmware)"
echo "    slam_mapping/bringup.launch.py provides: EKF + IMU filter + scan merger"
echo "    LiDAR hardware drivers (ldlidar_stl_ros2_node) run on ttyTHS1/ttyTHS2"
echo "    Topic pipeline: /scan0 + /scan1 → merger → /scan_multi → filter → /scan"
echo ""
echo "  Override env vars (add to config/fleetsafe_real_robot.env):"
echo "    FLEETSAFE_YAHBOOM_BASE_LAUNCH=/home/jetson/M3Pro_ws/install/slam_mapping/..."
echo "    FLEETSAFE_LIDAR_1_PORT=/dev/ttyTHS1"
echo "    FLEETSAFE_LIDAR_2_PORT=/dev/ttyTHS2"
echo "    FLEETSAFE_LIDAR_PRODUCT=LDLiDAR_LD19   # or LDLiDAR_STL27L"
echo "    FLEETSAFE_LIDAR_BAUD=230400             # or 921600 for STL27L"
echo "    FLEETSAFE_MICRO_ROS_SERIAL=/dev/serial/by-id/..."
echo ""
REMOTE_EOF
