#!/usr/bin/env bash
# preflight_live_motion.sh — Sensor gate before enabling live /cmd_vel output.
#
# Verifies that the Jetson is reachable and all robot sensors are publishing
# live data before run_vln_desktop.sh --enable-motion starts the controller.
# Invoked automatically by run_vln_desktop.sh; also callable directly.
#
#   bash scripts/live/preflight_live_motion.sh
#   SAFETY_RADIUS=0.30 bash scripts/live/preflight_live_motion.sh
#   make vln-live-preflight
#
# Hard-fail checks (ALL must pass; exits 1 on any failure):
#   1. ROS_DOMAIN_ID is set
#   2. Jetson SSH reachable (fleetsafe-jetson or fallback to explicit IP)
#   3. Robot base node visible (/YB_Node or any *_node/*base* pattern)
#   4. Primary scan topic(s): publisher count >= 1 AND data within 5 s
#   5. Secondary scan topic (if layout has two): publisher count >= 1 AND data
#   6. Odometry topic: publisher count >= 1 AND data within 5 s
#   7. /cmd_vel has >= 1 subscriber (robot base accepting velocity commands)
#   8. LiDAR effective clearance >= SAFETY_RADIUS (via inspect_lidar_clearance.py)
#
# Advisory (warn, never block):
#   9. /camera/color/image_raw publisher count
#
# Does NOT require the VLN controller to be running.
#
# Env:
#   SAFETY_RADIUS          (default 0.30)
#   ROS_DOMAIN_ID          (default 30)
#   FLEETSAFE_SCAN_TOPICS  override detected scan topics (e.g. /scan0,/scan1)
#   FLEETSAFE_ODOM_TOPIC   override detected odom topic
# shellcheck disable=SC2034
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

# ── Source config ──────────────────────────────────────────────────────────────
# shellcheck source=/dev/null
source "${REPO_ROOT}/config/fleetsafe_real_robot.env" 2>/dev/null || true

# ── ROS2 environment ───────────────────────────────────────────────────────────
if ! command -v ros2 &>/dev/null; then
    set +u
    # shellcheck source=/dev/null
    source /opt/ros/humble/setup.bash 2>/dev/null || {
        echo "[PREFLIGHT FAIL] ROS2 not found — source /opt/ros/humble/setup.bash first."
        exit 1
    }
    set -u
fi

SAFETY_RADIUS="${SAFETY_RADIUS:-0.30}"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-30}"
export ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-0}"

PASS=0
FAIL=0

_pass() { echo "  [PASS] $*"; PASS=$((PASS + 1)); }
_fail() { echo "  [FAIL] $*"; FAIL=$((FAIL + 1)); }
_warn() { echo "  [WARN] $*"; }
_info() { echo "  [INFO] $*"; }

echo ""
echo "════════════════════════════════════════════════════════════════════"
echo "  FleetSafe-VLN  |  Live Motion Sensor Preflight"
echo "  ROS_DOMAIN_ID  : ${ROS_DOMAIN_ID}"
echo "  Safety radius  : ${SAFETY_RADIUS} m"
echo "════════════════════════════════════════════════════════════════════"
echo ""

# ── 1. ROS_DOMAIN_ID set ───────────────────────────────────────────────────────
echo "── 1. ROS_DOMAIN_ID ─────────────────────────────────────────────────────"
if [[ -n "${ROS_DOMAIN_ID:-}" ]]; then
    _pass "ROS_DOMAIN_ID=${ROS_DOMAIN_ID}"
    if [[ "${ROS_DOMAIN_ID}" != "30" ]]; then
        _warn "Expected 30 for M3Pro live robot — got ${ROS_DOMAIN_ID}"
    fi
else
    _fail "ROS_DOMAIN_ID is not set"
fi
echo ""

# ── 2. Jetson SSH reachability ─────────────────────────────────────────────────
echo "── 2. Jetson SSH reachability ────────────────────────────────────────────"
_SSH_OPTS=(-o ConnectTimeout=5 -o BatchMode=yes -o LogLevel=ERROR -o StrictHostKeyChecking=no)
_JETSON_HOST=""

if ssh "${_SSH_OPTS[@]}" fleetsafe-jetson "exit 0" 2>/dev/null; then
    _JETSON_HOST="fleetsafe-jetson"
elif ssh "${_SSH_OPTS[@]}" "${ROBOT_USER:-jetson}@${ROBOT_HOTSPOT_IP:-172.20.10.14}" "exit 0" 2>/dev/null; then
    _JETSON_HOST="${ROBOT_USER:-jetson}@${ROBOT_HOTSPOT_IP:-172.20.10.14}"
elif [[ -n "${ROBOT_TAILSCALE_IP:-}" ]] && \
     ssh "${_SSH_OPTS[@]}" "${ROBOT_USER:-jetson}@${ROBOT_TAILSCALE_IP}" "exit 0" 2>/dev/null; then
    _JETSON_HOST="${ROBOT_USER:-jetson}@${ROBOT_TAILSCALE_IP}"
fi

if [[ -n "$_JETSON_HOST" ]]; then
    _pass "Jetson reachable via ${_JETSON_HOST}"
else
    _fail "Jetson unreachable — cannot confirm robot stack is running"
    _info "Fix: power on Jetson, confirm SSH works: ssh fleetsafe-jetson 'hostname'"
fi
echo ""

# ── Detect scan and odom topics (or use env overrides) ────────────────────────
echo "── Topic detection ──────────────────────────────────────────────────────"
set +u
# shellcheck source=/dev/null
source <(bash "${REPO_ROOT}/scripts/live/detect_scan_topics.sh" 2>/dev/null) || true
set -u
SCAN_TOPICS="${FLEETSAFE_SCAN_TOPICS:-/scan0,/scan1}"
ODOM_TOPIC="${FLEETSAFE_ODOM_TOPIC:-/odom_raw}"
_info "Scan topics : ${SCAN_TOPICS}"
_info "Odom topic  : ${ODOM_TOPIC}"
echo ""

# Convert comma-separated scan topics into an array
IFS=',' read -ra _SCAN_ARRAY <<< "$SCAN_TOPICS"

# ── Publisher count + data receipt helper ──────────────────────────────────────
_check_sensor_topic() {
    local topic="$1"

    local info pub_ct
    info=$(timeout 5 ros2 topic info "$topic" 2>/dev/null || true)
    if [[ -z "$info" ]]; then
        _fail "${topic}: not in ROS graph (no publishers)"
        return 1
    fi
    pub_ct=$(echo "$info" | grep -oP '(?<=Publisher count: )\d+' | head -1 || echo "0")
    if [[ "${pub_ct:-0}" -lt 1 ]]; then
        _fail "${topic}: Publisher count=${pub_ct:-0} — Jetson not publishing"
        return 1
    fi

    # Confirm at least one message arrives within 5 s using best_effort QoS to
    # match the sensor_data profile used by Yahboom/Orbbec drivers.
    if timeout 5 ros2 topic echo --once \
            --qos-reliability best_effort --qos-durability volatile \
            "$topic" > /dev/null 2>&1; then
        _pass "${topic}: Publisher count=${pub_ct}, data received within 5 s"
        return 0
    else
        _fail "${topic}: Publisher count=${pub_ct} but no data in 5 s (stalled publisher?)"
        return 1
    fi
}

# ── 3. Robot base node ─────────────────────────────────────────────────────────
echo "── 3. Robot base node ───────────────────────────────────────────────────"
NODES=$(timeout 6 ros2 node list 2>/dev/null || true)
if echo "$NODES" | grep -qE "YB_Node|yahboom|base_node|robot_base"; then
    _pass "Robot base node visible: $(echo "$NODES" | grep -oE '/YB_Node|/yahboom[^[:space:]]*|/base_node|/robot_base' | head -1)"
else
    _fail "No robot base node found in ros2 node list"
    _info "Fix: make robot-start-yahboom"
fi
echo ""

# ── 4. Primary scan topic ──────────────────────────────────────────────────────
echo "── 4. Primary scan topic (${_SCAN_ARRAY[0]}) ────────────────────────────"
_check_sensor_topic "${_SCAN_ARRAY[0]}"
echo ""

# ── 5. Secondary scan topic (if layout has two) ───────────────────────────────
if [[ "${#_SCAN_ARRAY[@]}" -ge 2 ]]; then
    echo "── 5. Secondary scan topic (${_SCAN_ARRAY[1]}) ──────────────────────────"
    _check_sensor_topic "${_SCAN_ARRAY[1]}"
    echo ""
fi

# ── 6. Odometry topic ─────────────────────────────────────────────────────────
echo "── 6. Odometry topic (${ODOM_TOPIC}) ────────────────────────────────────"
_check_sensor_topic "${ODOM_TOPIC}"
echo ""

# ── 7. /cmd_vel subscriber (robot base accepting commands) ────────────────────
echo "── 7. /cmd_vel subscriber (robot base ready) ────────────────────────────"
CMD_VEL_INFO=$(timeout 5 ros2 topic info /cmd_vel 2>/dev/null || true)
if [[ -z "$CMD_VEL_INFO" ]]; then
    _fail "/cmd_vel not in ROS graph — robot base driver not running"
    _info "Fix: make robot-start-yahboom"
else
    CMD_VEL_SUB=$(echo "$CMD_VEL_INFO" | grep -oP '(?<=Subscription count: )\d+' | head -1 || echo "0")
    if [[ "${CMD_VEL_SUB:-0}" -ge 1 ]]; then
        _pass "/cmd_vel Subscription count=${CMD_VEL_SUB} — base driver subscribed"
    else
        _fail "/cmd_vel Subscription count=0 — robot base not subscribed to /cmd_vel"
        _info "Make sure the yahboomcar base driver is fully initialised on the Jetson."
    fi
fi
echo ""

# ── 8. LiDAR effective clearance ──────────────────────────────────────────────
echo "── 8. LiDAR effective clearance >= ${SAFETY_RADIUS} m ──────────────────"
INSPECTOR="${REPO_ROOT}/scripts/live/inspect_lidar_clearance.py"
if [[ ! -f "$INSPECTOR" ]]; then
    _fail "inspect_lidar_clearance.py not found at ${INSPECTOR}"
else
    # Pass the detected scan topics to the inspector
    IFS=',' read -ra _SCAN_TOPICS_LIST <<< "$SCAN_TOPICS"
    _TMP=$(mktemp /tmp/fleetsafe_preflight_XXXXXX)
    /usr/bin/python3 "$INSPECTOR" \
        --topics "${_SCAN_TOPICS_LIST[@]}" \
        --safety-radius "$SAFETY_RADIUS" \
        --timeout 6 \
        > "$_TMP" 2>&1
    _LIDAR_EXIT=$?
    sed 's/^/   /' "$_TMP"
    rm -f "$_TMP"
    case "$_LIDAR_EXIT" in
        0) _pass "LiDAR effective clearance >= ${SAFETY_RADIUS} m" ;;
        1) _fail "LiDAR clearance < ${SAFETY_RADIUS} m — move robot to open space first" ;;
        2) _fail "No LiDAR data — scan topics must be publishing before enabling motion" ;;
        *) _fail "LiDAR inspector exited ${_LIDAR_EXIT}" ;;
    esac
fi
echo ""

# ── 9. Camera (advisory only — not a hard block) ──────────────────────────────
echo "── 9. /camera/color/image_raw (advisory) ────────────────────────────────"
CAM_INFO=$(timeout 5 ros2 topic info /camera/color/image_raw 2>/dev/null || true)
if [[ -n "$CAM_INFO" ]]; then
    CAM_PUB=$(echo "$CAM_INFO" | grep -oP '(?<=Publisher count: )\d+' | head -1 || echo "0")
    if [[ "${CAM_PUB:-0}" -ge 1 ]]; then
        _warn "/camera/color/image_raw: Publisher count=${CAM_PUB} [advisory — tracked in cert as camera_seen]"
    else
        _warn "/camera/color/image_raw: Publisher count=0 — camera offline"
        _info "Start Orbbec camera on Jetson: make robot-start-yahboom"
        _info "Note: motion proceeds; certificate records camera_seen=false"
    fi
else
    _warn "/camera/color/image_raw not in ROS graph — camera offline [advisory]"
fi
echo ""

# ── Summary ───────────────────────────────────────────────────────────────────
echo "════════════════════════════════════════════════════════════════════"
echo "  Preflight result: ${PASS} passed  ${FAIL} failed"
echo ""

if [[ "$FAIL" -gt 0 ]]; then
    echo "  PREFLIGHT FAILED — live motion is BLOCKED."
    echo ""
    echo "  Required fixes:"
    echo ""
    echo "    Jetson unreachable     →  power on, run: ssh fleetsafe-jetson hostname"
    echo "    No base node           →  make robot-start-yahboom"
    echo "    Scan topics missing    →  wait for bringup; check: make robot-status-yahboom"
    echo "    Odom missing           →  check micro_ros_agent on Jetson"
    echo "    /cmd_vel no subscriber →  start yahboomcar base driver"
    echo "    LiDAR clearance low    →  move robot to open space (>= ${SAFETY_RADIUS} m)"
    echo ""
    echo "  Diagnostics:"
    echo "    make robot-discover-yahboom   # what is running on Jetson"
    echo "    make robot-status-yahboom     # Hz, publisher counts"
    echo "    make vln-lidar-inspect        # live clearance reading"
    echo "════════════════════════════════════════════════════════════════════"
    exit 1
else
    echo "  ALL SENSOR CHECKS PASSED — safe to enable live motion."
    echo ""
    echo "  Next step:"
    echo "    CONFIRM_ENABLE_MOTION=YES make vln-desktop-live"
    echo "════════════════════════════════════════════════════════════════════"
    exit 0
fi
