#!/bin/bash
# FleetSafe — Install robot-side helper files to the Jetson over SSH.
#
# Tries hotspot IP, then Tailscale IP automatically.
# If the robot is off, prints a friendly message — no scary stack traces.
#
# Run from the RTX desktop.  Copies:
#   ~/fleetsafe_robot.env
#   ~/fleetsafe_robot_tools/start_robot_stack.sh
#   ~/fleetsafe_robot_tools/status_robot_stack.sh
#   ~/fleetsafe_robot_tools/stop_robot_motion.sh
#
# Usage:
#   ./scripts/robot/install_robot_tools.sh
#   ./scripts/robot/install_robot_tools.sh --ip 100.91.232.55
# shellcheck disable=SC2034
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=/dev/null
source "${REPO_ROOT}/config/fleetsafe_real_robot.env"

SSH_OPTS=(-o StrictHostKeyChecking=no -o ConnectTimeout=8 -o LogLevel=ERROR)
# Note: BatchMode=yes is intentionally omitted so password auth still works.
# For non-interactive use, set up SSH key auth:  ssh-copy-id ${ROBOT_USER}@${ROBOT_HOTSPOT_IP}

# ── Parse --ip override ───────────────────────────────────────────────────────
OVERRIDE_IP=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --ip) OVERRIDE_IP="$2"; shift 2 ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

# ── Resolve which IP to use ───────────────────────────────────────────────────
resolve_robot_ip() {
    # Use BatchMode=yes only for the connectivity probe (fail fast, no prompt)
    local probe_opts=("${SSH_OPTS[@]}" -o BatchMode=yes)
    if [[ -n "${OVERRIDE_IP}" ]]; then
        if ssh "${probe_opts[@]}" "${ROBOT_USER}@${OVERRIDE_IP}" "exit 0" 2>/dev/null; then
            echo "${OVERRIDE_IP}"
            return 0
        fi
        # Fall back to non-BatchMode in case key auth not configured
        if ssh "${SSH_OPTS[@]}" "${ROBOT_USER}@${OVERRIDE_IP}" "exit 0" 2>/dev/null; then
            echo "${OVERRIDE_IP}"
            return 0
        fi
        echo ""
        return 1
    fi

    for candidate in "${ROBOT_HOTSPOT_IP}" "${ROBOT_TAILSCALE_IP}"; do
        if ssh "${probe_opts[@]}" "${ROBOT_USER}@${candidate}" "exit 0" 2>/dev/null; then
            echo "${candidate}"
            return 0
        fi
    done
    # Retry without BatchMode (allows password prompt in interactive shells)
    for candidate in "${ROBOT_HOTSPOT_IP}" "${ROBOT_TAILSCALE_IP}"; do
        if ssh "${SSH_OPTS[@]}" "${ROBOT_USER}@${candidate}" "exit 0" 2>/dev/null; then
            echo "${candidate}"
            return 0
        fi
    done
    echo ""
    return 1
}

echo "============================================================"
echo "  FleetSafe  |  Install Robot Tools"
echo "  User        : ${ROBOT_USER}"
echo "  Hotspot IP  : ${ROBOT_HOTSPOT_IP}"
echo "  Tailscale IP: ${ROBOT_TAILSCALE_IP}"
[[ -n "${OVERRIDE_IP}" ]] && echo "  Override IP : ${OVERRIDE_IP}"
echo "============================================================"
echo ""
echo "Checking robot SSH connectivity..."

ROBOT_IP_RESOLVED=$(resolve_robot_ip)

if [[ -z "${ROBOT_IP_RESOLVED}" ]]; then
    echo ""
    echo "  Robot is currently offline or unreachable."
    echo "  This is okay if the robot is powered off."
    echo ""
    echo "  To proceed:"
    echo "    1. Power on the robot"
    echo "    2. Wait 60-90 seconds for Jetson boot"
    echo "    3. Confirm network: hotspot (${ROBOT_HOTSPOT_IP}) or Tailscale (${ROBOT_TAILSCALE_IP})"
    echo "    4. Rerun:"
    echo "         ./scripts/robot/install_robot_tools.sh"
    echo "         # or: make robot-install"
    echo ""
    echo "  While the robot is off, you can still prepare the offline bundle:"
    echo "    make robot-bundle"
    echo "    # Copy manually when robot is on:"
    echo "    #   scp dist/fleetsafe_robot_tools.tar.gz ${ROBOT_USER}@${ROBOT_HOTSPOT_IP}:~/"
    echo "    #   ssh ${ROBOT_USER}@${ROBOT_HOTSPOT_IP}"
    echo "    #   tar -xzf ~/fleetsafe_robot_tools.tar.gz -C ~/"
    exit 3
fi

ROBOT="${ROBOT_USER}@${ROBOT_IP_RESOLVED}"
echo "  Connected via ${ROBOT_IP_RESOLVED}"
echo ""

# ── Assemble env file ─────────────────────────────────────────────────────────
ROBOT_ENV=$(cat <<'ENVEOF'
# FleetSafe robot-side environment — Yahboom ROSMASTER-M3Pro
FLEETSAFE_MCU_DEV=/dev/myserial
FLEETSAFE_MCU_BAUD=2000000
FLEETSAFE_ROS_DOMAIN=30
FLEETSAFE_RTX_IP=172.20.10.2
ENVEOF
)

# ── Assemble start_robot_stack.sh ─────────────────────────────────────────────
START_SCRIPT=$(cat <<'STARTEOF'
#!/bin/bash
# FleetSafe — Start full robot stack on Yahboom ROSMASTER-M3Pro (Jetson Orin NX)
#
# Starts in order:
#   1. micro_ros_agent  — MCU bridge → /odom_raw, /cmd_vel, /imu/data_raw
#   2. yahboomcar bringup — /YB_Node, /scan0, /scan1
#
# Topics expected after start:
#   /YB_Node  /scan0  /scan1  /odom_raw  /cmd_vel  /camera/color/image_raw
set -uo pipefail

source ~/fleetsafe_robot.env 2>/dev/null || true
source /opt/ros/humble/setup.bash
source ~/yahboomcar_ws/install/setup.bash 2>/dev/null || true
[[ -f ~/mircoROS_agent/install/setup.bash ]] && source ~/mircoROS_agent/install/setup.bash || true

export ROS_DOMAIN_ID="${FLEETSAFE_ROS_DOMAIN:-30}"
export ROS_LOCALHOST_ONLY=0

MCU_DEV="${FLEETSAFE_MCU_DEV:-/dev/myserial}"
MCU_BAUD="${FLEETSAFE_MCU_BAUD:-2000000}"
LOGDIR="$HOME/fleetsafe_robot_tools/logs"
mkdir -p "$LOGDIR"

echo "============================================================"
echo "  FleetSafe Robot Stack  |  $(hostname)"
echo "  ROS_DOMAIN_ID : ${ROS_DOMAIN_ID}"
echo "  MCU device    : ${MCU_DEV} @ ${MCU_BAUD} baud"
echo "============================================================"
echo ""

# ── Kill stale processes ──────────────────────────────────────────────────────
echo "Stopping stale processes..."
pkill -f micro_ros_agent        || true
pkill -f "ros2 launch yahboom"  || true
sleep 1

# ── 1. micro_ros_agent (MCU bridge) ──────────────────────────────────────────
if [[ -e "$MCU_DEV" ]]; then
    echo "Starting micro_ros_agent on ${MCU_DEV} @ ${MCU_BAUD} baud..."
    nohup micro_ros_agent serial \
        --dev "$MCU_DEV" -b "$MCU_BAUD" -v4 \
        > "${LOGDIR}/micro_ros_agent.log" 2>&1 &
    echo "  micro_ros_agent PID: $!"
    sleep 3
else
    echo "[WARN] MCU device ${MCU_DEV} not found."
    echo "       /odom_raw and base /cmd_vel will not be available."
    echo "       Check USB cable: ls /dev/tty* /dev/myserial"
fi

# ── 2. yahboomcar bringup (/YB_Node, /scan0, /scan1, camera) ─────────────────
LAUNCH_FOUND=0
for LAUNCH_FILE in \
    "$HOME/yahboomcar_ws/src/yahboomcar_bringup/launch/yahboomcar_bringup.launch.py" \
    "$HOME/yahboomcar_ws/src/yahboomcar_bringup/launch/bringup.launch.py" \
    "$HOME/yahboomcar_ws/src/yahboomcar_bringup/launch/m3pro.launch.py" \
    "$HOME/yahboomcar_ws/src/yahboomcar_bringup/launch/yahboomcar_X3.launch.py"
do
    if [[ -f "$LAUNCH_FILE" ]]; then
        echo "Starting yahboomcar bringup: $(basename "$LAUNCH_FILE")"
        nohup ros2 launch "$LAUNCH_FILE" \
            > "${LOGDIR}/yahboomcar_bringup.log" 2>&1 &
        echo "  bringup PID: $!"
        LAUNCH_FOUND=1
        break
    fi
done

if [[ "$LAUNCH_FOUND" -eq 0 ]]; then
    echo "[WARN] No yahboomcar bringup launch file found."
    echo "       Searched: ~/yahboomcar_ws/src/yahboomcar_bringup/launch/"
    echo "       /YB_Node, /scan0, /scan1 will not appear."
    echo "       To find your launch file:"
    echo "         find ~/yahboomcar_ws -name '*.launch.py' 2>/dev/null"
    echo "       Then start manually:"
    echo "         ros2 launch <pkg> <launch>.launch.py &"
fi

echo ""
echo "Waiting 8 s for nodes to register..."
sleep 8

echo ""
echo "--- ros2 node list ---"
timeout 5 ros2 node list 2>/dev/null || echo "(no nodes yet)"

echo ""
echo "--- FleetSafe-required topics ---"
for T in /YB_Node /cmd_vel /odom_raw /scan0 /scan1 /camera/color/image_raw; do
    if timeout 3 ros2 topic list 2>/dev/null | grep -qx "$T" 2>/dev/null; then
        echo "  [OK]  $T"
    else
        echo "  [--]  $T  (not yet visible)"
    fi
done

echo ""
echo "Logs:"
echo "  micro_ros_agent : ${LOGDIR}/micro_ros_agent.log"
[[ "$LAUNCH_FOUND" -eq 1 ]] && echo "  bringup         : ${LOGDIR}/yahboomcar_bringup.log" || true
echo ""
echo "Stack started.  Full status: ~/fleetsafe_robot_tools/status_robot_stack.sh"
STARTEOF
)

# ── Assemble status_robot_stack.sh ────────────────────────────────────────────
STATUS_SCRIPT=$(cat <<'STATUSEOF'
#!/bin/bash
# FleetSafe — Show robot stack status (run on Jetson)
set -uo pipefail

source ~/fleetsafe_robot.env 2>/dev/null || true
source /opt/ros/humble/setup.bash
source ~/yahboomcar_ws/install/setup.bash 2>/dev/null || true
[[ -f ~/mircoROS_agent/install/setup.bash ]] && source ~/mircoROS_agent/install/setup.bash || true

export ROS_DOMAIN_ID="${FLEETSAFE_ROS_DOMAIN:-30}"
export ROS_LOCALHOST_ONLY=0

echo "============================================================"
echo "  FleetSafe Robot Status  |  $(hostname)"
echo "  ROS_DOMAIN_ID : ${ROS_DOMAIN_ID}"
echo "============================================================"

echo ""
echo "--- Network ---"
hostname
ip -4 addr show | grep "inet " | awk '{print $2}' | sort

echo ""
echo "--- Processes ---"
echo -n "  micro_ros_agent : "
pgrep -a micro_ros_agent 2>/dev/null || echo "(not running)"
echo -n "  yahboomcar      : "
pgrep -fa "ros2 launch yahboom" 2>/dev/null || echo "(not running)"

echo ""
echo "--- Required topics ---"
TOPICS=$(timeout 5 ros2 topic list 2>/dev/null || true)
for T in /YB_Node /cmd_vel /odom_raw /scan0 /scan1 /camera/color/image_raw /imu/data_raw; do
    if echo "$TOPICS" | grep -qx "$T" 2>/dev/null; then
        echo "  [OK]  $T"
    else
        echo "  [--]  $T"
    fi
done

echo ""
echo "--- Nodes ---"
timeout 5 ros2 node list 2>/dev/null || echo "(none)"

echo ""
echo "--- /odom_raw Hz (4 s window) ---"
timeout 6 ros2 topic hz /odom_raw --window 10 2>/dev/null | grep -E "rate|min|max" | head -3 || echo "(no data)"

echo ""
echo "--- /scan0 Hz (4 s window) ---"
timeout 6 ros2 topic hz /scan0 --window 10 2>/dev/null | grep -E "rate|min|max" | head -3 || echo "(no data)"

echo ""
echo "--- Logs (last 5 lines) ---"
LOGDIR="$HOME/fleetsafe_robot_tools/logs"
for LOG in "${LOGDIR}/micro_ros_agent.log" "${LOGDIR}/yahboomcar_bringup.log"; do
    if [[ -f "$LOG" ]]; then
        echo "  ${LOG}:"
        tail -5 "$LOG" | sed 's/^/    /'
    fi
done

echo ""
echo "Done."
STATUSEOF
)

# ── Assemble stop_robot_motion.sh ─────────────────────────────────────────────
STOP_SCRIPT=$(cat <<'STOPEOF'
#!/bin/bash
# FleetSafe — Publish zero velocity to /cmd_vel for 3 seconds (safety stop)
set -euo pipefail

source ~/fleetsafe_robot.env 2>/dev/null || true
source /opt/ros/humble/setup.bash
source ~/yahboomcar_ws/install/setup.bash 2>/dev/null || true
[[ -f ~/mircoROS_agent/install/setup.bash ]] && source ~/mircoROS_agent/install/setup.bash || true

export ROS_DOMAIN_ID="${FLEETSAFE_ROS_DOMAIN:-30}"
export ROS_LOCALHOST_ONLY=0

echo "FleetSafe SAFETY STOP — zero velocity for 3 s on domain ${ROS_DOMAIN_ID}"

ZERO='{"linear": {"x": 0.0, "y": 0.0, "z": 0.0}, "angular": {"x": 0.0, "y": 0.0, "z": 0.0}}'
END=$(( $(date +%s) + 3 ))
while [[ $(date +%s) -lt $END ]]; do
    ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist "${ZERO}" 2>/dev/null || true
    sleep 0.1
done
echo "Zero velocity stop complete."
STOPEOF
)

# ── Upload to robot ───────────────────────────────────────────────────────────
echo "Creating ~/fleetsafe_robot_tools on robot..."
ssh "${SSH_OPTS[@]}" "${ROBOT}" "mkdir -p ~/fleetsafe_robot_tools"

echo "Uploading ~/fleetsafe_robot.env..."
printf '%s\n' "${ROBOT_ENV}" | ssh "${SSH_OPTS[@]}" "${ROBOT}" "cat > ~/fleetsafe_robot.env"

echo "Uploading ~/fleetsafe_robot_tools/start_robot_stack.sh..."
printf '%s\n' "${START_SCRIPT}" | ssh "${SSH_OPTS[@]}" "${ROBOT}" \
    "cat > ~/fleetsafe_robot_tools/start_robot_stack.sh && chmod +x ~/fleetsafe_robot_tools/start_robot_stack.sh"

echo "Uploading ~/fleetsafe_robot_tools/status_robot_stack.sh..."
printf '%s\n' "${STATUS_SCRIPT}" | ssh "${SSH_OPTS[@]}" "${ROBOT}" \
    "cat > ~/fleetsafe_robot_tools/status_robot_stack.sh && chmod +x ~/fleetsafe_robot_tools/status_robot_stack.sh"

echo "Uploading ~/fleetsafe_robot_tools/stop_robot_motion.sh..."
printf '%s\n' "${STOP_SCRIPT}" | ssh "${SSH_OPTS[@]}" "${ROBOT}" \
    "cat > ~/fleetsafe_robot_tools/stop_robot_motion.sh && chmod +x ~/fleetsafe_robot_tools/stop_robot_motion.sh"

echo ""
echo "Installation complete  →  ${ROBOT}"
echo ""
echo "On the robot (ssh ${ROBOT}):"
echo "  ~/fleetsafe_robot_tools/start_robot_stack.sh"
echo "  ~/fleetsafe_robot_tools/status_robot_stack.sh"
echo "  ~/fleetsafe_robot_tools/stop_robot_motion.sh"
