#!/usr/bin/env bash
# vln_live_preflight.sh — Hard-fail preflight checklist before enabling live motion.
#
# ALL checks must pass; any failure exits non-zero.
# Run via:  make vln-live-preflight
#
# Checks (in order):
#   1. ROS_DOMAIN_ID = 30
#   2. /YB_Node visible (Jetson robot stack running)
#   3. /scan0 Hz >= 1 Hz
#   4. /scan1 Hz >= 1 Hz
#   5. /odom_raw Hz >= 1 Hz
#   6. /camera/color/image_raw present in topic list
#   7. LiDAR effective clearance >= safety_radius (via lidar_sanitizer)
#   8. /fleetsafe/instruction_text has >= 1 subscriber (VLN controller running)
#   9. Dry-run instruction -> latest certificate has camera_seen=True
#
# Env overrides:
#   SAFETY_RADIUS   (default 0.30)
#   ROS_DOMAIN_ID   (default 30)
# shellcheck disable=SC2034
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

if ! command -v ros2 &>/dev/null; then
    set +u
    # shellcheck source=/dev/null
    source /opt/ros/humble/setup.bash 2>/dev/null || {
        echo "[PREFLIGHT FAIL] ROS2 not found. Source /opt/ros/humble/setup.bash first."
        exit 1
    }
    set -u
fi

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-30}"
export ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-0}"
SAFETY_RADIUS="${SAFETY_RADIUS:-0.30}"

# ── Detect scan / odom topics (or use env overrides) ──────────────────────────
set +u
# shellcheck source=/dev/null
source <(bash "${REPO_ROOT}/scripts/live/detect_scan_topics.sh" 2>/dev/null) || true
set -u
_SCAN_TOPICS="${FLEETSAFE_SCAN_TOPICS:-/scan0,/scan1}"
_ODOM_TOPIC="${FLEETSAFE_ODOM_TOPIC:-/odom_raw}"
IFS=',' read -ra _SCAN_ARRAY <<< "$_SCAN_TOPICS"

PASS=0
FAIL=0

_pass() { echo "  [PASS] $*"; PASS=$((PASS + 1)); }
_fail() { echo "  [FAIL] $*"; FAIL=$((FAIL + 1)); }
_info() { echo "  [INFO] $*"; }

echo ""
echo "════════════════════════════════════════════════════════════════════"
echo "  FleetSafe-VLN  |  Live Motion Preflight"
echo "  ROS_DOMAIN_ID  : ${ROS_DOMAIN_ID}"
echo "  Safety radius  : ${SAFETY_RADIUS} m  (env SAFETY_RADIUS to override)"
echo "════════════════════════════════════════════════════════════════════"
echo ""

# ── 1. ROS domain ─────────────────────────────────────────────────────────────
echo "── 1. ROS domain ────────────────────────────────────────────────────────"
if [[ "${ROS_DOMAIN_ID}" == "30" ]]; then
    _pass "ROS_DOMAIN_ID=30"
else
    _fail "ROS_DOMAIN_ID=${ROS_DOMAIN_ID} (must be 30 for live robot)"
fi
echo ""

# ── 2. /YB_Node ───────────────────────────────────────────────────────────────
echo "── 2. Jetson robot base node ────────────────────────────────────────────"
NODES=$(timeout 6 ros2 node list 2>/dev/null || true)
if echo "$NODES" | grep -q "YB_Node"; then
    _pass "/YB_Node visible — yahboomcar stack is running"
else
    _fail "/YB_Node not found"
    _info "  Fix: make robot-start  (or ssh jetson and run start_robot_stack.sh)"
fi
echo ""

# ── 3-5. Topic Hz ─────────────────────────────────────────────────────────────
echo "── 3-5. Sensor topic Hz (min 1 Hz required) ─────────────────────────────"
echo "   Scan topics : ${_SCAN_TOPICS}"
echo "   Odom topic  : ${_ODOM_TOPIC}"
echo ""

_check_hz() {
    local topic="$1"
    local min_hz="$2"
    local hz
    hz=$(timeout 8 ros2 topic hz "$topic" --window 5 2>/dev/null \
         | grep -oP '(?<=average rate: )\S+' | head -1 || true)
    if [[ -z "$hz" ]]; then
        _fail "${topic}: no data received (not publishing)"
        return
    fi
    if awk "BEGIN{exit !($hz+0 >= $min_hz)}"; then
        _pass "${topic}: ${hz} Hz (>= ${min_hz} Hz)"
    else
        _fail "${topic}: ${hz} Hz  (< ${min_hz} Hz required)"
    fi
}

for _t in "${_SCAN_ARRAY[@]}"; do
    _check_hz "$_t" 1
done
_check_hz "$_ODOM_TOPIC" 1
echo ""

# ── 6. Camera topic present ────────────────────────────────────────────────────
echo "── 6. Camera topic ──────────────────────────────────────────────────────"
TOPICS=$(timeout 5 ros2 topic list 2>/dev/null || true)
if echo "$TOPICS" | grep -qx "/camera/color/image_raw"; then
    _pass "/camera/color/image_raw is in topic list"
else
    _fail "/camera/color/image_raw missing"
    _info "  Fix: check Orbbec camera USB cable and driver on Jetson"
fi
echo ""

# ── 7. LiDAR effective clearance ──────────────────────────────────────────────
echo "── 7. LiDAR effective clearance >= safety_radius ────────────────────────"
INSPECTOR="${REPO_ROOT}/scripts/live/inspect_lidar_clearance.py"
if [[ ! -f "$INSPECTOR" ]]; then
    _fail "inspect_lidar_clearance.py not found at ${INSPECTOR}"
else
    _TMP=$(mktemp /tmp/fleetsafe_preflight_lidar_XXXXXX)
    /usr/bin/python3 "$INSPECTOR" \
        --topics "${_SCAN_ARRAY[@]}" \
        --safety-radius "$SAFETY_RADIUS" \
        --timeout 5 \
        > "$_TMP" 2>&1
    _LIDAR_EXIT=$?
    sed 's/^/   /' "$_TMP"
    rm -f "$_TMP"
    case "$_LIDAR_EXIT" in
        0) _pass "LiDAR effective clearance >= ${SAFETY_RADIUS} m" ;;
        1) _fail "LiDAR effective clearance < ${SAFETY_RADIUS} m — move robot away from obstacles" ;;
        2) _fail "No LiDAR data received — /scan0 and /scan1 must be publishing" ;;
        *) _fail "LiDAR inspector returned exit code ${_LIDAR_EXIT}" ;;
    esac
fi
echo ""

# ── 8. VLN controller subscribed ──────────────────────────────────────────────
echo "── 8. VLN controller subscription ──────────────────────────────────────"
_SUB_INFO=$(timeout 5 ros2 topic info /fleetsafe/instruction_text 2>/dev/null || true)
if [[ -z "$_SUB_INFO" ]]; then
    _fail "/fleetsafe/instruction_text not found — VLN controller not running"
    _info "  Fix: make vln-desktop  (in a separate terminal, then rerun preflight)"
else
    _SUB_CT=$(echo "$_SUB_INFO" | grep -oP '(?<=Subscription count: )\d+' || echo "0")
    if [[ "${_SUB_CT:-0}" -ge 1 ]]; then
        _pass "/fleetsafe/instruction_text has ${_SUB_CT} subscriber(s)"
    else
        _fail "/fleetsafe/instruction_text Subscription count=0 — controller not yet subscribed"
        _info "  Fix: wait a few seconds for controller to fully start, then rerun"
    fi
fi
echo ""

# ── 9. Dry-run instruction → camera_seen=True in cert ────────────────────────
echo "── 9. Dry-run instruction → camera_seen check ───────────────────────────"
if [[ "${_SUB_CT:-0}" -lt 1 ]]; then
    _fail "Skipping dry-run check — controller not subscribed (fix check 8 first)"
else
    _info "Publishing preflight dry-run instruction..."
    ros2 topic pub --once /fleetsafe/instruction_text std_msgs/msg/String \
        "{data: 'preflight check go forward'}" 2>/dev/null || {
        _fail "Could not publish preflight instruction"
    }
    sleep 2

    LATEST_CERT=$(ls -t results/certificates/*/vln_certificates_m3pro.jsonl 2>/dev/null | head -1 || true)
    if [[ -z "$LATEST_CERT" ]] || [[ ! -s "$LATEST_CERT" ]]; then
        _fail "No certificate found after dry-run instruction"
        _info "  This means the controller is not writing evidence files."
        _info "  Check controller logs and ensure results/certificates/ is writable."
    else
        _LAST_JSON=$(tail -n 1 "$LATEST_CERT")
        _CAM_SEEN=$(/usr/bin/python3 -c \
            "import sys,json; d=json.loads(sys.argv[1]); print(d.get('camera_seen','?'))" \
            "$_LAST_JSON" 2>/dev/null || echo "?")
        _DECISION=$(/usr/bin/python3 -c \
            "import sys,json; d=json.loads(sys.argv[1]); print(d.get('decision','?'))" \
            "$_LAST_JSON" 2>/dev/null || echo "?")
        if [[ "$_CAM_SEEN" == "True" ]]; then
            _pass "Latest certificate: camera_seen=True  decision=${_DECISION}"
        else
            _fail "Latest certificate: camera_seen=${_CAM_SEEN}  decision=${_DECISION}"
            _info "  Camera frames are not reaching the VLN controller."
            _info "  Run: make vln-camera-check"
        fi
    fi
fi
echo ""

# ── Summary ───────────────────────────────────────────────────────────────────
echo "════════════════════════════════════════════════════════════════════"
echo "  Preflight summary: ${PASS} passed  ${FAIL} failed"
echo ""

if [[ "$FAIL" -gt 0 ]]; then
    echo "  PREFLIGHT FAILED — do NOT enable live motion."
    echo ""
    echo "  Common fixes:"
    echo "    /YB_Node missing         → make robot-start"
    echo "    Sensor Hz = 0            → make robot-status (check bringup logs)"
    echo "    LiDAR clearance low      → move robot to open space"
    echo "    Controller not subscribed → make vln-desktop (separate terminal)"
    echo "    camera_seen=False        → make vln-camera-check"
    echo "════════════════════════════════════════════════════════════════════"
    exit 1
else
    echo "  ALL CHECKS PASSED — system is ready for live motion."
    echo ""
    echo "  Next step:"
    echo "    make vln-live-motion-proof"
    echo "════════════════════════════════════════════════════════════════════"
    exit 0
fi
