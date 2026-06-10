#!/bin/bash
# FleetSafe — Build an offline installer bundle for the Jetson.
#
# Creates dist/fleetsafe_robot_tools.tar.gz so the robot tools can be
# installed manually when SSH is unavailable (robot off, no network, etc.).
#
# Usage: ./scripts/robot/make_robot_tools_bundle.sh
#
# Manual install on robot:
#   scp dist/fleetsafe_robot_tools.tar.gz jetson@<ROBOT_IP>:~/
#   ssh jetson@<ROBOT_IP>
#   tar -xzf ~/fleetsafe_robot_tools.tar.gz -C ~/
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=/dev/null
source "${REPO_ROOT}/config/fleetsafe_real_robot.env"

DIST_DIR="${REPO_ROOT}/dist"
STAGING_DIR="$(mktemp -d)"
BUNDLE="${DIST_DIR}/fleetsafe_robot_tools.tar.gz"

mkdir -p "${DIST_DIR}"

# ── Generate fleetsafe_robot.env ──────────────────────────────────────────────
cat > "${STAGING_DIR}/fleetsafe_robot.env" <<ENVEOF
# FleetSafe robot-side environment — Yahboom ROSMASTER-M3Pro
FLEETSAFE_MCU_DEV=/dev/myserial
FLEETSAFE_MCU_BAUD=2000000
FLEETSAFE_ROS_DOMAIN=30
FLEETSAFE_RTX_IP=${FLEETSAFE_RTX_IP}
ENVEOF

# ── Generate start_robot_stack.sh ─────────────────────────────────────────────
cat > "${STAGING_DIR}/start_robot_stack.sh" <<'STARTEOF'
#!/bin/bash
# FleetSafe — Start robot stack on Yahboom ROSMASTER-M3Pro (Jetson Orin NX)
set -euo pipefail

source ~/fleetsafe_robot.env
source /opt/ros/humble/setup.bash
source ~/yahboomcar_ws/install/setup.bash
[[ -f ~/mircoROS_agent/install/setup.bash ]] && source ~/mircoROS_agent/install/setup.bash || true

export ROS_DOMAIN_ID="${FLEETSAFE_ROS_DOMAIN}"
export ROS_LOCALHOST_ONLY=0

echo "============================================================"
echo "  FleetSafe Robot Stack  |  $(hostname)"
echo "  ROS_DOMAIN_ID : ${ROS_DOMAIN_ID}"
echo "  MCU device    : ${FLEETSAFE_MCU_DEV}"
echo "============================================================"
echo ""

echo "Stopping old micro_ros_agent (if any)..."
pkill -f micro_ros_agent || true
sleep 1

echo "Starting micro_ros_agent on ${FLEETSAFE_MCU_DEV} @ ${FLEETSAFE_MCU_BAUD} baud..."
nohup micro_ros_agent serial \
    --dev "${FLEETSAFE_MCU_DEV}" \
    -b "${FLEETSAFE_MCU_BAUD}" \
    -v6 \
    > /tmp/micro_ros_agent.log 2>&1 &
AGENT_PID=$!
echo "micro_ros_agent PID: ${AGENT_PID}"

echo "Waiting for agent to initialise (5 s)..."
sleep 5

echo ""
echo "--- ros2 node list ---"
timeout 5 ros2 node list 2>/dev/null || echo "(no nodes yet)"
echo ""
echo "--- ros2 topic list ---"
timeout 5 ros2 topic list 2>/dev/null | grep -E "cmd_vel|odom|scan|imu|camera" || echo "(none yet)"
echo ""
echo "Robot stack started.  Log: /tmp/micro_ros_agent.log"
STARTEOF

# ── Generate status_robot_stack.sh ───────────────────────────────────────────
cat > "${STAGING_DIR}/status_robot_stack.sh" <<'STATUSEOF'
#!/bin/bash
# FleetSafe — Show robot stack status
set -euo pipefail

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
echo "--- Hostname / IPs ---"
hostname
ip -4 addr show | grep "inet " | awk '{print $2}' | sort

echo ""
echo "--- micro_ros_agent process ---"
pgrep -a micro_ros_agent || echo "(not running)"

echo ""
echo "--- ros2 node list ---"
timeout 5 ros2 node list 2>/dev/null || echo "(no nodes)"

echo ""
echo "--- Relevant topics ---"
timeout 5 ros2 topic list 2>/dev/null \
    | grep -E "cmd_vel|odom|imu|scan|camera|image|depth" || echo "(none found)"

echo ""
echo "--- /cmd_vel topic info ---"
timeout 5 ros2 topic info /cmd_vel 2>/dev/null || echo "(not found)"

echo ""
echo "--- /odom_raw  hz (5 s) ---"
timeout 7 ros2 topic hz /odom_raw --window 20 2>/dev/null | head -5 || echo "(no data)"

echo ""
echo "--- /camera/color/image_raw  hz (5 s) ---"
timeout 7 ros2 topic hz /camera/color/image_raw --window 20 2>/dev/null | head -5 || echo "(no data)"

echo ""
echo "Done."
STATUSEOF

# ── Generate stop_robot_motion.sh ─────────────────────────────────────────────
cat > "${STAGING_DIR}/stop_robot_motion.sh" <<'STOPEOF'
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

chmod +x "${STAGING_DIR}"/*.sh

# ── Generate install script ───────────────────────────────────────────────────
cat > "${STAGING_DIR}/install.sh" <<'INSTALLEOF'
#!/bin/bash
# Run on the Jetson to install FleetSafe robot tools
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p ~/fleetsafe_robot_tools
cp "${SCRIPT_DIR}/fleetsafe_robot.env" ~/fleetsafe_robot.env
cp "${SCRIPT_DIR}/start_robot_stack.sh"  ~/fleetsafe_robot_tools/start_robot_stack.sh
cp "${SCRIPT_DIR}/status_robot_stack.sh" ~/fleetsafe_robot_tools/status_robot_stack.sh
cp "${SCRIPT_DIR}/stop_robot_motion.sh"  ~/fleetsafe_robot_tools/stop_robot_motion.sh
chmod +x ~/fleetsafe_robot_tools/*.sh
echo "FleetSafe robot tools installed to ~/fleetsafe_robot_tools/"
echo "Run: ~/fleetsafe_robot_tools/start_robot_stack.sh"
INSTALLEOF
chmod +x "${STAGING_DIR}/install.sh"

# ── Pack tarball with paths rooted at ~ ──────────────────────────────────────
tar -czf "${BUNDLE}" \
    -C "${STAGING_DIR}" \
    fleetsafe_robot.env \
    install.sh \
    start_robot_stack.sh \
    status_robot_stack.sh \
    stop_robot_motion.sh

rm -rf "${STAGING_DIR}"

echo ""
echo "Created ${BUNDLE}"
echo ""
echo "To install manually on robot:"
echo "  scp ${BUNDLE} ${ROBOT_USER}@${ROBOT_HOTSPOT_IP}:~/"
echo "  ssh ${ROBOT_USER}@${ROBOT_HOTSPOT_IP}"
echo "  tar -xzf ~/fleetsafe_robot_tools.tar.gz -C ~/"
echo "  bash ~/install.sh"
