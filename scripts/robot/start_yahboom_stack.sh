#!/usr/bin/env bash
# start_yahboom_stack.sh — Start Yahboom M3Pro full robot stack on Jetson.
#
# Architecture of the M3Pro stack:
#
#   Session 1 — fleetsafe_micro_ros
#     micro_ros_agent serial → STM32 firmware (micro-ROS)
#     STM32 registers /YB_Node, publishes /odom_raw /imu/data_raw, subscribes /cmd_vel
#     *** Use Yahboom's ~/mircoROS_agent binary first — STM32 firmware was compiled
#     *** against it.  The apt ros-humble-micro-ros-agent may version-mismatch.
#
#   Session 2 — fleetsafe_yahboom_base
#     slam_mapping/bringup.launch.py (or FLEETSAFE_YAHBOOM_BASE_LAUNCH override)
#     Starts: imu_filter_madgwick, laserscan_multi_merger, laser_filter, ekf_filter
#     Merger expects /scan0 and /scan1 from session 3; EKF fuses /odom_raw + /imu/data.
#     NOTE: this launch does NOT start YB_Node — that is entirely micro-ROS.
#
#   Session 3a — fleetsafe_lidar_front
#     ldlidar_stl_ros2_node on ttyTHS1 (first Tmini-plus) → publishes /scan0
#
#   Session 3b — fleetsafe_lidar_rear
#     ldlidar_stl_ros2_node on ttyTHS2 (second Tmini-plus) → publishes /scan1
#     (skipped if second LiDAR port not found)
#
#   Session 4 — fleetsafe_orbbec_camera
#     dabai_dcw2.launch.py → /camera/color/image_raw
#
# LiDAR port detection order (first available wins for port 1, second for port 2):
#   /dev/ttyTHS1, /dev/ttyTHS2   (Jetson hardware UART — M3Pro standard wiring)
#   /dev/ttyUSB1, /dev/ttyUSB2   (USB-serial fallback)
#   /dev/ttyACM0, /dev/ttyACM1
#
# micro_ros_agent priority:
#   1. ~/mircoROS_agent/install/…/micro_ros_agent  (Yahboom build — firmware-matched)
#   2. ros2 run micro_ros_agent                    (apt ros-humble-micro-ros-agent)
#   3. micro_ros_agent binary in PATH
#   4. MicroXRCEAgent binary in PATH
#
# Env var overrides (set in config/fleetsafe_real_robot.env):
#   FLEETSAFE_YAHBOOM_BASE_LAUNCH   absolute path to navigation pipeline launch
#   FLEETSAFE_YAHBOOM_CAMERA_LAUNCH absolute path to camera launch
#   FLEETSAFE_MICRO_ROS_SERIAL      serial device for MCU
#   FLEETSAFE_MICRO_ROS_BAUD        baud rate (default 2000000, per Yahboom M3Pro firmware)
#   FLEETSAFE_LIDAR_1_PORT          override port for first LiDAR
#   FLEETSAFE_LIDAR_2_PORT          override port for second LiDAR
#   FLEETSAFE_LIDAR_PRODUCT         ldlidar product name (default LDLiDAR_LD19)
#   FLEETSAFE_LIDAR_BAUD            ldlidar baud rate (default 230400)
#
# Usage:
#   bash scripts/robot/start_yahboom_stack.sh
#   bash scripts/robot/start_yahboom_stack.sh --ip 100.91.232.55
#   make robot-start-yahboom
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
    echo ""
    echo "  [FAIL] Jetson unreachable."
    echo "  Tried: fleetsafe-jetson  ${ROBOT_HOTSPOT_IP}  ${ROBOT_TAILSCALE_IP}"
    echo "  Fix: configure ~/.ssh/config with Host fleetsafe-jetson"
    exit 1
fi

echo ""
echo "════════════════════════════════════════════════════════════════════"
echo "  FleetSafe  |  Start Yahboom Stack"
echo "  Jetson     : ${ROBOT}"
echo "════════════════════════════════════════════════════════════════════"
echo ""

# Pass override vars (if set) into the remote heredoc
_BASE_OVERRIDE="${FLEETSAFE_YAHBOOM_BASE_LAUNCH:-}"
_CAM_OVERRIDE="${FLEETSAFE_YAHBOOM_CAMERA_LAUNCH:-}"
_SERIAL_OVERRIDE="${FLEETSAFE_MICRO_ROS_SERIAL:-${FLEETSAFE_MICRO_ROS_DEVICE:-}}"
_BAUD_OVERRIDE="${FLEETSAFE_MICRO_ROS_BAUD:-2000000}"
_L1_OVERRIDE="${FLEETSAFE_LIDAR_1_PORT:-}"
_L2_OVERRIDE="${FLEETSAFE_LIDAR_2_PORT:-}"
_LIDAR_PRODUCT="${FLEETSAFE_LIDAR_PRODUCT:-LDLiDAR_LD19}"
_LIDAR_BAUD="${FLEETSAFE_LIDAR_BAUD:-230400}"

ssh "${SSH_OPTS[@]}" "${ROBOT}" \
    BASE_OVR="$_BASE_OVERRIDE" \
    CAM_OVR="$_CAM_OVERRIDE" \
    SERIAL_OVR="$_SERIAL_OVERRIDE" \
    BAUD_OVR="$_BAUD_OVERRIDE" \
    L1_OVR="$_L1_OVERRIDE" \
    L2_OVR="$_L2_OVERRIDE" \
    LIDAR_PRODUCT="$_LIDAR_PRODUCT" \
    LIDAR_BAUD="$_LIDAR_BAUD" \
    'bash -s' <<'REMOTE_EOF'
set -eo pipefail

# source_ros: guards ROS source against nounset errors in ROS setup scripts
source_ros() {
    set +u
    source /opt/ros/humble/setup.bash                            2>/dev/null || true
    source "$HOME/yahboomcar_ws/install/setup.bash"              2>/dev/null || true
    source "$HOME/mircoROS_agent/install/setup.bash"             2>/dev/null || true
    source "$HOME/M3Pro_ws/install/setup.bash"                   2>/dev/null || true
    set -u 2>/dev/null || true
    export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-30}"
    export ROS_LOCALHOST_ONLY=0
}
source_ros

LOGDIR="$HOME/fleetsafe_robot_tools/logs"
mkdir -p "$LOGDIR"

ROS_DOMAIN="${ROS_DOMAIN_ID:-30}"
ROS_INIT="set +u; source /opt/ros/humble/setup.bash 2>/dev/null; source $HOME/yahboomcar_ws/install/setup.bash 2>/dev/null; source $HOME/mircoROS_agent/install/setup.bash 2>/dev/null; source $HOME/M3Pro_ws/install/setup.bash 2>/dev/null; set +e; export ROS_DOMAIN_ID=${ROS_DOMAIN}; export ROS_LOCALHOST_ONLY=0"

# ── tmux availability ─────────────────────────────────────────────────────────
USE_TMUX=0
command -v tmux &>/dev/null && USE_TMUX=1

_start_session() {
    local sess="$1"
    local cmd="$2"
    local log_name="${sess#fleetsafe_}"
    local log="${LOGDIR}/${log_name}.log"
    local pid_file="${LOGDIR}/${log_name}.pid"
    if [[ $USE_TMUX -eq 1 ]]; then
        tmux new-session -d -s "$sess" \
            "bash -c \"${cmd} 2>&1 | tee ${log}; echo '--- session ended ---'; read\""
        echo "  [tmux]  Session : ${sess}"
        echo "          Attach  : tmux attach -t ${sess}"
    else
        nohup bash -c "${cmd}" > "$log" 2>&1 &
        echo "$!" > "$pid_file"
        echo "  [nohup] PID=$(cat "${pid_file}")  (tmux not installed)"
    fi
    echo "          Log     : ${log}"
}

# ── Launch file scoring ───────────────────────────────────────────────────────
# For the M3Pro navigation pipeline (EKF + IMU + laser merger).
# YB_Node never appears in any launch file — it comes from micro-ROS.
_score_base() {
    local f="$1" c s=0
    c=$(cat "$f" 2>/dev/null || echo "")
    # Navigation pipeline indicators
    echo "$c" | grep -qi "ekf\|robot_localization"                                    && s=$((s+15))
    echo "$c" | grep -qi "imu_filter\|imu_tools\|imu_filter_madgwick"                 && s=$((s+10))
    echo "$c" | grep -qi "laser_merge\|ira_laser_tools\|laserscan_multi"              && s=$((s+10))
    echo "$c" | grep -qi "slam_mapping\|slam_toolbox\|cartographer"                   && s=$((s+5))
    # Legacy mobile-base indicators still positive if present
    echo "$c" | grep -qi "YB_Node\|RobotBase\|base_controller\|yahboom_base"          && s=$((s+20))
    echo "$c" | grep -qi "\bodom_raw\b"                                               && s=$((s+10))
    echo "$c" | grep -qi "cmd_vel"                                                    && s=$((s+5))
    echo "$c" | grep -qi "micro_ros\|serial.*mcu\|stm32"                             && s=$((s+5))
    # Hard exclude: MoveIt / arm manipulation configs
    echo "$c" | grep -qi "moveit\|MoveItCpp\|move_group\|MoveGroupInterface"          && s=$((s-30))
    echo "$c" | grep -qi "planning_scene\|spawn_controllers\|warehouse_db\|setup_assistant\|static_virtual_joint" \
                                                                                      && s=$((s-25))
    echo $s
}

echo "════════════════════════════════════════════════════════════════════"
echo "  Yahboom M3Pro Stack Start  |  $(hostname)"
echo "  ROS_DOMAIN_ID : ${ROS_DOMAIN}"
echo "  Log dir       : ${LOGDIR}"
echo "  Session mode  : $([ $USE_TMUX -eq 1 ] && echo 'tmux' || echo 'nohup (tmux not installed)')"
echo "════════════════════════════════════════════════════════════════════"
echo ""

# ── Stop stale processes ──────────────────────────────────────────────────────
echo "── Stopping stale processes ─────────────────────────────────────────────"
if [[ $USE_TMUX -eq 1 ]]; then
    for _sess in fleetsafe_micro_ros fleetsafe_yahboom_base \
                 fleetsafe_lidar_front fleetsafe_lidar_rear \
                 fleetsafe_yahboom_lidar fleetsafe_orbbec_camera; do
        tmux kill-session -t "$_sess" 2>/dev/null && echo "  killed tmux: $_sess" || true
    done
else
    for _pid_file in "$LOGDIR"/micro_ros.pid "$LOGDIR"/yahboom_base.pid \
                     "$LOGDIR"/lidar_front.pid "$LOGDIR"/lidar_rear.pid \
                     "$LOGDIR"/yahboom_lidar.pid "$LOGDIR"/orbbec_camera.pid; do
        if [[ -f "$_pid_file" ]]; then
            _old_pid=$(cat "$_pid_file" 2>/dev/null || true)
            if [[ -n "$_old_pid" ]] && kill -0 "$_old_pid" 2>/dev/null; then
                kill "$_old_pid" 2>/dev/null && echo "  killed PID ${_old_pid} ($(basename "$_pid_file" .pid))" || true
            fi
            rm -f "$_pid_file"
        fi
    done
fi
# Kill known processes regardless of session mode
pkill -f "micro_ros_agent serial"  2>/dev/null && echo "  killed micro_ros_agent"  || true
pkill -f "MicroXRCEAgent serial"   2>/dev/null && echo "  killed MicroXRCEAgent"   || true
pkill -f "ros2 launch"             2>/dev/null && echo "  killed ros2 launch"       || true
pkill -f "ldlidar_stl_ros2_node"   2>/dev/null && echo "  killed ldlidar nodes"     || true
# Kill stale arm/MoveIt processes from demo.launch.py (if still running from boot)
pkill -f "ros2_control_node"       2>/dev/null && echo "  killed stale ros2_control_node (arm demo)" || true
pkill -f "move_group"              2>/dev/null && echo "  killed stale move_group"  || true
sleep 2

# ── Serial device detection (MCU / micro-ROS) ─────────────────────────────────
echo ""
echo "── Serial device detection (MCU) ────────────────────────────────────────"
MCU_DEV=""
if [[ -n "${SERIAL_OVR:-}" && -e "${SERIAL_OVR}" ]]; then
    MCU_DEV="$SERIAL_OVR"
    echo "  Serial device  : ${MCU_DEV}  [override]"
else
    for _c in \
        "/dev/serial/by-id/usb-Silicon_Labs_CP2104_USB_to_UART_Bridge_Controller_02E0E65D-if00-port0" \
        "/dev/myserial" \
        "/dev/ttyUSB0" "/dev/ttyACM0"
    do
        if [[ -e "$_c" ]]; then
            MCU_DEV="$_c"
            echo "  Serial device  : ${MCU_DEV}"
            break
        fi
    done
fi
if [[ -z "$MCU_DEV" ]]; then
    echo "  [WARN] No MCU serial device — /odom_raw /imu/data_raw /YB_Node will not appear."
    echo "         Verify: ls /dev/ttyUSB* /dev/serial/by-id/"
fi
MCU_BAUD="${BAUD_OVR:-2000000}"
echo "  MCU baud rate  : ${MCU_BAUD}"

# ── 1. micro_ros_agent (fleetsafe_micro_ros) ──────────────────────────────────
echo ""
echo "── 1. micro_ros_agent → STM32 → /YB_Node /odom_raw /imu/data_raw ────────"
if [[ -n "$MCU_DEV" ]]; then
    _AGENT_CMD=""
    # Priority: Yahboom's firmware-matched binary first, then apt version, then PATH
    _YAHBOOM_AGENT="$HOME/mircoROS_agent/install/micro_ros_agent/lib/micro_ros_agent/micro_ros_agent"
    if [[ -x "$_YAHBOOM_AGENT" ]]; then
        _AGENT_CMD="$_YAHBOOM_AGENT"
        echo "  Agent: Yahboom mircoROS_agent binary (firmware-matched — preferred)"
    elif ros2 pkg prefix micro_ros_agent >/dev/null 2>&1; then
        _AGENT_CMD="ros2 run micro_ros_agent micro_ros_agent"
        echo "  Agent: ros2 run micro_ros_agent (apt package)"
        echo "  [WARN] STM32 firmware was built with Yahboom agent; apt version may version-mismatch."
        echo "         If /YB_Node never appears, reinstall mircoROS_agent from Yahboom's repo."
    elif command -v micro_ros_agent &>/dev/null; then
        _AGENT_CMD="micro_ros_agent"
        echo "  Agent: micro_ros_agent (PATH)"
    elif command -v MicroXRCEAgent &>/dev/null; then
        _AGENT_CMD="MicroXRCEAgent"
        echo "  Agent: MicroXRCEAgent (PATH)"
    fi

    if [[ -n "$_AGENT_CMD" ]]; then
        _start_session "fleetsafe_micro_ros" \
            "${ROS_INIT}; ${_AGENT_CMD} serial --dev ${MCU_DEV} -b ${MCU_BAUD} -v4"
        echo "  [INFO] /YB_Node should appear within 5-10 s once agent connects to STM32."
        echo "         If /YB_Node never appears after 30 s:"
        echo "           - Power-cycle the robot (STM32 needs reset after cold boot)"
        echo "           - Verify micro-ROS firmware is flashed to STM32"
        echo "           - Try: tail -f ${LOGDIR}/micro_ros.log"
        echo "         Expected log lines: 'Create session', 'Create subscriber'"
    else
        echo "  [WARN] No micro_ros_agent found."
        echo "         Fix: build ~/mircoROS_agent workspace or: sudo apt install -y ros-humble-micro-ros-agent"
    fi
    sleep 4
else
    echo "  [SKIP] No MCU serial device."
fi

# ── 2. Navigation pipeline (fleetsafe_yahboom_base) ───────────────────────────
echo ""
echo "── 2. Navigation pipeline → EKF + IMU filter + laser merger ────────────"
BASE_LAUNCH=""

if [[ -n "${BASE_OVR:-}" ]]; then
    if [[ -f "$BASE_OVR" ]]; then
        BASE_LAUNCH="$BASE_OVR"
        echo "  Launch [override]: ${BASE_LAUNCH}"
    else
        echo "  [WARN] FLEETSAFE_YAHBOOM_BASE_LAUNCH not found: ${BASE_OVR}"
    fi
fi

if [[ -z "$BASE_LAUNCH" ]]; then
    # Known-good paths — slam_mapping/bringup.launch.py is the correct M3Pro nav pipeline.
    # Excludes demo.launch.py / base_bringup.launch.py (MoveIt / stale arm configs).
    ALL_BASE_CANDIDATES=(
        "$HOME/M3Pro_ws/install/slam_mapping/share/slam_mapping/launch/bringup.launch.py"
        "$HOME/M3Pro_ws/src/slam_mapping/launch/bringup.launch.py"
        "$HOME/M3Pro_ws/install/M3Pro_navigation/share/M3Pro_navigation/launch/base_bringup.launch.py"
        "$HOME/M3Pro_ws/src/M3Pro_navigation/launch/base_bringup.launch.py"
        "$HOME/yahboomcar_ws/src/yahboomcar_bringup/launch/yahboomcar_bringup.launch.py"
        "$HOME/yahboomcar_ws/install/yahboomcar_bringup/share/yahboomcar_bringup/launch/yahboomcar_bringup.launch.py"
    )
    # Also search workspaces (may find custom bringup files)
    mapfile -t _WS_LAUNCHES < <(
        find "$HOME/yahboomcar_ws" "$HOME/M3Pro_ws" \
             -name "*.launch.py" 2>/dev/null | \
             grep -v "moveit\|MoveIt\|move_group\|arm\|demo\|warehouse\|setup_assistant\|calibrat\|rviz\|display\|viewer\|mediapipe\|yolo\|slam_view\|save_map\|largemodel\|patrol\|multi_camera\|carto_nav\|navigation2\|localization\|gmapping\|cartographer" | \
             sort || true
    )
    ALL_BASE_CANDIDATES+=("${_WS_LAUNCHES[@]}")

    BEST_SCORE=0
    BEST_FILE=""
    for _lf in "${ALL_BASE_CANDIDATES[@]}"; do
        [[ -f "$_lf" ]] || continue
        _s=$(_score_base "$_lf")
        if [[ $_s -gt 0 ]]; then
            printf "  %+4d  [OK]   %s\n" "$_s" "$_lf"
        elif [[ $_s -lt 0 ]]; then
            printf "  %+4d  [EXCL] %s\n" "$_s" "$_lf"
        fi
        if [[ $_s -gt $BEST_SCORE ]]; then
            BEST_SCORE=$_s
            BEST_FILE="$_lf"
        fi
    done

    [[ -n "$BEST_FILE" ]] && BASE_LAUNCH="$BEST_FILE"
fi

if [[ -n "$BASE_LAUNCH" ]]; then
    echo "  Selected (score=${BEST_SCORE:-override}): $(basename "${BASE_LAUNCH}")"
    echo "  Path: ${BASE_LAUNCH}"
    _start_session "fleetsafe_yahboom_base" "${ROS_INIT}; ros2 launch ${BASE_LAUNCH}"
else
    echo "  [WARN] No navigation pipeline launch found."
    echo "         Expected: slam_mapping/bringup.launch.py"
    echo "         Override: export FLEETSAFE_YAHBOOM_BASE_LAUNCH=/path/to/bringup.launch.py"
fi

# ── 3. LiDAR hardware drivers (scan0 + scan1) ─────────────────────────────────
echo ""
echo "── 3. LiDAR hardware drivers → /scan0  /scan1 ────────────────────────────"
echo "   (ldlidar_stl_ros2_node on ttyTHS1/ttyTHS2 — Jetson hardware UART)"
echo ""

# ttyTHS permission fix: on Yahboom Jetson images the jetson user is NOT in the
# dialout group, so /dev/ttyTHS1 and /dev/ttyTHS2 (crw-rw---- root:dialout) deny
# access.  Fix: create a persistent udev rule and chmod immediately.
echo "── 3a. ttyTHS permission check ──────────────────────────────────────────"
_THS_FIXED=0
for _ths in /dev/ttyTHS1 /dev/ttyTHS2; do
    [[ -e "$_ths" ]] || continue
    if ! test -r "$_ths" 2>/dev/null || ! test -w "$_ths" 2>/dev/null; then
        echo "  [FIX] ${_ths} not writable — applying sudo chmod a+rw"
        sudo chmod a+rw "$_ths" 2>/dev/null && echo "  [OK]  ${_ths} now writable" || \
            echo "  [WARN] chmod failed for ${_ths} — ldlidar may get Permission Denied"
        _THS_FIXED=1
    else
        echo "  [OK]  ${_ths} already writable"
    fi
done
# Create persistent udev rule so this survives reboots (idempotent)
if [[ $_THS_FIXED -eq 1 ]] && [[ ! -f /etc/udev/rules.d/99-yahboom-serial.rules ]]; then
    echo 'KERNEL=="ttyTHS[0-9]*", MODE="0666"' | \
        sudo tee /etc/udev/rules.d/99-yahboom-serial.rules >/dev/null 2>&1 && \
        sudo udevadm control --reload-rules 2>/dev/null && \
        echo "  [FIX] udev rule created — ttyTHS will be world-writable after reboot"
fi
echo ""

LIDAR_PORT_1=""
LIDAR_PORT_2=""

# Apply env var overrides first
[[ -n "${L1_OVR:-}" && -e "${L1_OVR}" ]] && LIDAR_PORT_1="$L1_OVR"
[[ -n "${L2_OVR:-}" && -e "${L2_OVR}" ]] && LIDAR_PORT_2="$L2_OVR"

# Auto-detect remaining ports
if [[ -z "$LIDAR_PORT_1" || -z "$LIDAR_PORT_2" ]]; then
    for _p in /dev/ttyTHS1 /dev/ttyTHS2 /dev/ttyUSB1 /dev/ttyUSB2 /dev/ttyACM0 /dev/ttyACM1; do
        [[ -e "$_p" ]] || continue
        [[ "$_p" == "$MCU_DEV" ]] && continue  # skip the MCU port
        if [[ -z "$LIDAR_PORT_1" ]]; then
            LIDAR_PORT_1="$_p"
        elif [[ -z "$LIDAR_PORT_2" ]]; then
            LIDAR_PORT_2="$_p"
            break
        fi
    done
fi

_LIDAR_PROD="${LIDAR_PRODUCT:-LDLiDAR_LD19}"
_LIDAR_BD="${LIDAR_BAUD:-230400}"

if [[ -n "$LIDAR_PORT_1" ]]; then
    echo "  LiDAR 1: ${LIDAR_PORT_1} (${_LIDAR_PROD} @ ${_LIDAR_BD} baud) → /scan0"
    _LIDAR1_CMD="${ROS_INIT}; ros2 run ldlidar_stl_ros2 ldlidar_stl_ros2_node"
    _LIDAR1_CMD+=" --ros-args"
    _LIDAR1_CMD+=" -p product_name:=${_LIDAR_PROD}"
    _LIDAR1_CMD+=" -p topic_name:=scan0"
    _LIDAR1_CMD+=" -p frame_id:=base_laser_front"
    _LIDAR1_CMD+=" -p port_name:=${LIDAR_PORT_1}"
    _LIDAR1_CMD+=" -p port_baudrate:=${_LIDAR_BD}"
    _LIDAR1_CMD+=" -p laser_scan_dir:=true"
    _LIDAR1_CMD+=" -p enable_angle_crop_func:=false"
    _start_session "fleetsafe_lidar_front" "$_LIDAR1_CMD"
else
    echo "  [WARN] No LiDAR 1 port found (ttyTHS1, ttyUSB1, ttyACM0)."
    echo "         /scan0 will not publish — merger will wait indefinitely."
    echo "         Override: FLEETSAFE_LIDAR_1_PORT=/dev/ttyTHS1"
fi

if [[ -n "$LIDAR_PORT_2" ]]; then
    echo ""
    echo "  LiDAR 2: ${LIDAR_PORT_2} (${_LIDAR_PROD} @ ${_LIDAR_BD} baud) → /scan1"
    _LIDAR2_CMD="${ROS_INIT}; ros2 run ldlidar_stl_ros2 ldlidar_stl_ros2_node"
    _LIDAR2_CMD+=" --ros-args"
    _LIDAR2_CMD+=" -p product_name:=${_LIDAR_PROD}"
    _LIDAR2_CMD+=" -p topic_name:=scan1"
    _LIDAR2_CMD+=" -p frame_id:=base_laser_rear"
    _LIDAR2_CMD+=" -p port_name:=${LIDAR_PORT_2}"
    _LIDAR2_CMD+=" -p port_baudrate:=${_LIDAR_BD}"
    _LIDAR2_CMD+=" -p laser_scan_dir:=false"
    _LIDAR2_CMD+=" -p enable_angle_crop_func:=false"
    _start_session "fleetsafe_lidar_rear" "$_LIDAR2_CMD"
elif [[ -n "$LIDAR_PORT_1" ]]; then
    echo "  [INFO] Only one LiDAR port found. FleetSafe can operate with single-LiDAR (/scan0 only)."
    echo "         Override: FLEETSAFE_LIDAR_2_PORT=/dev/ttyTHS2"
fi

# ── 4. Orbbec camera (fleetsafe_orbbec_camera) ────────────────────────────────
echo ""
echo "── 4. Orbbec camera → /camera/color/image_raw ───────────────────────────"
CAM_LAUNCH=""

if [[ -n "${CAM_OVR:-}" && -f "${CAM_OVR}" ]]; then
    CAM_LAUNCH="$CAM_OVR"
    echo "  Launch [override]: ${CAM_LAUNCH}"
fi

if [[ -z "$CAM_LAUNCH" ]]; then
    for _c in \
        "$HOME/yahboomcar_ws/install/orbbec_camera/share/orbbec_camera/launch/dabai_dcw2.launch.py" \
        "$HOME/ros2_ws/install/orbbec_camera/share/orbbec_camera/launch/dabai_dcw2.launch.py" \
        "$HOME/ros2_ws/src/OrbbecSDK_ROS2/orbbec_camera/launch/dabai_dcw2.launch.py" \
        "$HOME/orbbec_ros2/install/orbbec_camera/share/orbbec_camera/launch/dabai_dcw2.launch.py"
    do
        if [[ -f "$_c" ]]; then
            CAM_LAUNCH="$_c"
            break
        fi
    done
fi

if [[ -n "$CAM_LAUNCH" ]]; then
    echo "  Launch: $(basename "${CAM_LAUNCH}")"
    echo "  Path  : ${CAM_LAUNCH}"
    _start_session "fleetsafe_orbbec_camera" "${ROS_INIT}; ros2 launch ${CAM_LAUNCH}"
else
    echo "  [INFO] dabai_dcw2.launch.py not found."
    echo "         Override: FLEETSAFE_YAHBOOM_CAMERA_LAUNCH=/path/to/dabai_dcw2.launch.py"
fi

# ── Wait and verify ───────────────────────────────────────────────────────────
echo ""
echo "── Waiting 20 s for nodes to register ──────────────────────────────────"
sleep 20

echo ""
echo "── Verification ────────────────────────────────────────────────────────"
PASS=0; FAIL=0
TOPICS=$(timeout 6 ros2 topic list 2>/dev/null || true)
NODES=$(timeout 6 ros2 node list 2>/dev/null || true)

_ok()   { echo "  [OK]  $*"; PASS=$((PASS+1)); }
_miss() { echo "  [--]  $*"; FAIL=$((FAIL+1)); }

echo "$NODES" | grep -q "YB_Node"     && _ok "/YB_Node (STM32 micro-ROS connected)" || _miss "/YB_Node missing — agent not connected to STM32 firmware"
echo "$TOPICS" | grep -qx "/cmd_vel"  && _ok "/cmd_vel"   || _miss "/cmd_vel (needs /YB_Node)"
echo "$TOPICS" | grep -qx "/odom_raw" && _ok "/odom_raw"  || _miss "/odom_raw (needs /YB_Node)"
echo "$TOPICS" | grep -qx "/scan0"    && _ok "/scan0"     || _miss "/scan0 (LiDAR 1 not publishing)"
echo "$TOPICS" | grep -qx "/scan1"    && _ok "/scan1"     || _miss "/scan1 (LiDAR 2 not publishing)"
echo "$TOPICS" | grep -qx "/camera/color/image_raw" && _ok "/camera/color/image_raw" || _miss "/camera/color/image_raw"

echo ""
echo "  Result: ${PASS} OK  ${FAIL} missing"

if [[ "$FAIL" -gt 0 ]]; then
    echo ""
    echo "  ── Failure diagnosis ──────────────────────────────────────────────"
    if ! echo "$NODES" | grep -q "YB_Node"; then
        echo "  /YB_Node missing — check micro_ros_agent log for 'Create session':"
        echo "    tail -30 ${LOGDIR}/micro_ros.log"
        echo "  If log shows no 'Create session' after 30 s:"
        echo "    1. Power-cycle the robot (STM32 needs hardware reset)"
        echo "    2. Check STM32 has micro-ROS firmware flashed"
        echo "    3. Confirm baud (stty -F ${MCU_DEV:-/dev/ttyUSB0} speed)"
    fi
    if ! echo "$TOPICS" | grep -qx "/scan0"; then
        echo "  /scan0 missing — check LiDAR driver log:"
        echo "    tail -30 ${LOGDIR}/lidar_front.log"
        echo "  Confirm LiDAR 1 port: ls /dev/ttyTHS1 /dev/ttyUSB1"
        echo "  Override if needed:  FLEETSAFE_LIDAR_1_PORT=/dev/ttyTHS1"
    fi
    echo ""
    echo "  Override env vars (add to config/fleetsafe_real_robot.env):"
    echo "    FLEETSAFE_YAHBOOM_BASE_LAUNCH=/path/to/bringup.launch.py"
    echo "    FLEETSAFE_LIDAR_1_PORT=/dev/ttyTHS1"
    echo "    FLEETSAFE_LIDAR_2_PORT=/dev/ttyTHS2"
    echo "    FLEETSAFE_LIDAR_PRODUCT=LDLiDAR_LD19   # or LDLiDAR_STL27L"
    echo "    FLEETSAFE_LIDAR_BAUD=230400             # or 921600 for STL27L"
    echo ""
    echo "  Run diagnostics: make robot-diagnose-yahboom"
fi
echo ""
echo "════════════════════════════════════════════════════════════════════"
REMOTE_EOF
