#!/usr/bin/env bash
# check_vln_stack.sh — Verify the full FleetSafe-VLN stack is healthy.
#
# Checks:
#   - ROS_DOMAIN_ID = 30
#   - Jetson robot nodes and topics present
#   - VLN controller topics present (subscription count ≥ 1)
#   - Live LiDAR min-range reading (warns if below safety radius)
#
# Usage:
#   bash scripts/live/check_vln_stack.sh
#   make vln-check-stack
set -uo pipefail

# ── Source ROS2 ───────────────────────────────────────────────────────────────
if ! command -v ros2 &>/dev/null; then
    # Temporarily disable nounset: ROS setup scripts access undefined variables
    set +u
    # shellcheck source=/dev/null
    source /opt/ros/humble/setup.bash 2>/dev/null || {
        echo "[FAIL] ROS2 not found. source /opt/ros/humble/setup.bash first."
        exit 1
    }
    set -u
fi

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-30}"
export ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-0}"
SAFETY_RADIUS="${SAFETY_RADIUS:-0.30}"

# ── Detect scan/odom topics ────────────────────────────────────────────────────
REPO_ROOT_STACK="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
set +u
# shellcheck source=/dev/null
source <(bash "${REPO_ROOT_STACK}/scripts/live/detect_scan_topics.sh" 2>/dev/null) || true
set -u
_DETECTED_SCAN="${FLEETSAFE_SCAN_TOPICS:-/scan0,/scan1}"
_DETECTED_ODOM="${FLEETSAFE_ODOM_TOPIC:-/odom_raw}"

PASS=0
FAIL=0
WARN=0

_pass() { echo "  [OK]   $*"; PASS=$((PASS + 1)); }
_fail() { echo "  [FAIL] $*"; FAIL=$((FAIL + 1)); }
_warn() { echo "  [WARN] $*"; WARN=$((WARN + 1)); }
_info() { echo "  [INFO] $*"; }

echo ""
echo "════════════════════════════════════════════════════════════════════"
echo "  FleetSafe-VLN  |  Stack Health Check"
echo "  ROS_DOMAIN_ID  : ${ROS_DOMAIN_ID}"
echo "  Safety radius  : ${SAFETY_RADIUS} m  (env SAFETY_RADIUS to override)"
echo "  Scan topics    : ${_DETECTED_SCAN}"
echo "  Odom topic     : ${_DETECTED_ODOM}"
echo "════════════════════════════════════════════════════════════════════"
echo ""

# ── 1. Domain ID ─────────────────────────────────────────────────────────────
echo "── ROS environment ──────────────────────────────────────────────────"
if [[ "${ROS_DOMAIN_ID}" == "30" ]]; then
    _pass "ROS_DOMAIN_ID=30"
else
    _fail "ROS_DOMAIN_ID=${ROS_DOMAIN_ID} (expected 30)"
fi
echo ""

# ── 2. Robot node ─────────────────────────────────────────────────────────────
echo "── Jetson robot nodes ────────────────────────────────────────────────"
NODES=$(timeout 5 ros2 node list 2>/dev/null || true)
if echo "$NODES" | grep -q "YB_Node"; then
    _pass "/YB_Node visible"
else
    _fail "/YB_Node not found — is the Yahboom base stack running on the Jetson?"
fi
echo ""

# ── 3. Robot sensor topics ────────────────────────────────────────────────────
echo "── Jetson sensor topics ──────────────────────────────────────────────"
TOPICS=$(timeout 5 ros2 topic list 2>/dev/null || true)

# Check detected scan topics + odom + camera + cmd_vel
IFS=',' read -ra _SCAN_CHECK <<< "${_DETECTED_SCAN}"
for topic in "${_SCAN_CHECK[@]}" "${_DETECTED_ODOM}" /camera/color/image_raw /cmd_vel; do
    if echo "$TOPICS" | grep -qx "$topic"; then
        _pass "$topic"
    else
        _fail "$topic  (not found — check Jetson ROS stack)"
    fi
done
echo ""

# ── 3b. Camera Hz check — advisory only, never blocks stack health ────────────
# camera_seen in the certificate is the authoritative controller-level proof.
# This Hz check is a convenience diagnostic; warnings here do not fail the run.
echo "── Camera Hz check  (/camera/color/image_raw, 2 s timeout) [advisory] ───"
_info "  camera_seen in /fleetsafe/certificate is the authoritative proof."
_info "  Hz here is advisory — a warning does NOT block the stack."
_CAM_HZ=$(timeout 3 ros2 topic hz /camera/color/image_raw \
              --qos-profile sensor_data \
              --window 10 2>/dev/null \
          | grep -oP '(?<=average rate: )\S+' | head -1 || true)
if [[ -z "$_CAM_HZ" ]]; then
    _warn "/camera/color/image_raw: no Hz data received (topic absent or QoS mismatch)"
    _info "  If camera is connected, verify BEST_EFFORT QoS; run:"
    _info "    ros2 topic hz /camera/color/image_raw --qos-profile sensor_data"
    _info "  Check camera_seen in latest cert: make vln-camera-check"
else
    if awk "BEGIN{exit !($_CAM_HZ+0 >= 5)}"; then
        _pass "/camera/color/image_raw  rate=${_CAM_HZ} Hz (≥ 5 Hz)"
    else
        _warn "/camera/color/image_raw  rate=${_CAM_HZ} Hz (< 5 Hz)"
        _info "  Low Hz may cause camera_seen=False in certificates (stale > 2 s)."
    fi
fi
echo ""

# ── 4. VLN controller topics ──────────────────────────────────────────────────
echo "── VLN controller topics (must have Subscription count ≥ 1) ─────────"

_check_sub() {
    local topic="$1"
    local info
    info=$(timeout 5 ros2 topic info "$topic" 2>/dev/null || true)
    if [[ -z "$info" ]]; then
        _fail "${topic}  (topic not found — is run_vln_m3pro.py running?)"
        return
    fi
    local sub_count
    sub_count=$(echo "$info" | grep -oP '(?<=Subscription count: )\d+' || echo "0")
    if [[ "${sub_count:-0}" -ge 1 ]]; then
        _pass "${topic}  (Subscription count: ${sub_count})"
    else
        _warn "${topic}  exists but Subscription count=0 — controller not subscribed yet"
    fi
}

_check_pub() {
    local topic="$1"
    if echo "$TOPICS" | grep -qx "$topic"; then
        _pass "${topic}  (publisher present)"
    else
        _warn "${topic}  (not yet published — send an instruction first)"
    fi
}

_check_sub /fleetsafe/instruction_text
_check_pub /fleetsafe/cmd_vel_nominal
_check_pub /fleetsafe/vln/parsed_instruction
_check_pub /fleetsafe/certificate
echo ""

# ── 5. LiDAR clearance (sanitized via lidar_sanitizer.py) ────────────────────
echo "── LiDAR clearance  raw vs effective  (3 s timeout) ─────────────────"
echo "   Runs the same LidarSanitizer used by run_vln_m3pro.py."
echo "   Sensor dead-zone artifacts (≤ range_min + 0.02 m) are discarded."
echo "   Effective clearance = 5th-percentile of valid beams across both scanners."
echo ""

INSPECTOR="${REPO_ROOT_STACK}/scripts/live/inspect_lidar_clearance.py"

if [[ -f "$INSPECTOR" ]]; then
    IFS=',' read -ra _LIDAR_TOPICS <<< "${_DETECTED_SCAN}"
    _TMP_REPORT=$(mktemp /tmp/fleetsafe_lidar_XXXXXX)
    /usr/bin/python3 "$INSPECTOR" \
        --topics "${_LIDAR_TOPICS[@]}" \
        --safety-radius "$SAFETY_RADIUS" \
        --timeout 3 \
        > "$_TMP_REPORT" 2>&1
    _LIDAR_EXIT=$?
    sed 's/^/   /' "$_TMP_REPORT"
    rm -f "$_TMP_REPORT"
    case "$_LIDAR_EXIT" in
        0) _pass "LiDAR effective clearance ≥ safety_radius=${SAFETY_RADIUS} m" ;;
        1) _warn "LiDAR effective clearance < safety_radius=${SAFETY_RADIUS} m — CBF will e-stop (expected near obstacles)" ;;
        2) _warn "No LiDAR data received — is the Jetson stack running?" ;;
        *) _warn "LiDAR inspector returned unexpected exit code ${_LIDAR_EXIT}" ;;
    esac
else
    # Fallback: raw bash parsing (no sanitization)
    _warn "inspect_lidar_clearance.py not found — falling back to raw min-range check"
    _read_lidar_raw() {
        local topic="$1"
        local raw
        raw=$(timeout 4 ros2 topic echo --once "$topic" 2>/dev/null || true)
        if [[ -z "$raw" ]]; then
            _info "${topic}: (no data)"
            return
        fi
        local min_range
        min_range=$(echo "$raw" \
            | grep -oP '[-+]?\d+\.?\d+(?:[eE][-+]?\d+)?' \
            | awk 'BEGIN{m=999} $1+0 > 0.01 && $1+0 < m {m=$1} END{print m}' \
            2>/dev/null || echo "?")
        if [[ "$min_range" != "?" ]]; then
            if awk "BEGIN{exit !($min_range < $SAFETY_RADIUS)}"; then
                _warn "${topic}: raw_min=${min_range} m  (below safety_radius=${SAFETY_RADIUS} m — may be artifact)"
            else
                _pass "${topic}: raw_min=${min_range} m"
            fi
        else
            _info "${topic}: could not parse min range"
        fi
    }
    IFS=',' read -ra _FB_TOPICS <<< "${_DETECTED_SCAN}"
    for _fb_t in "${_FB_TOPICS[@]}"; do
        _read_lidar_raw "$_fb_t"
    done
fi
echo ""

# ── Summary ───────────────────────────────────────────────────────────────────
echo "════════════════════════════════════════════════════════════════════"
echo "  Summary: ${PASS} passed  ${WARN} warnings  ${FAIL} failed"
echo ""

if [[ "$FAIL" -gt 0 ]]; then
    echo "  Fix failures before running make vln-desktop."
    echo ""
    echo "  Common fixes:"
    echo "    No Jetson topics  → ssh jetson@172.20.10.14 and start robot stack"
    echo "    No VLN topics     → run: make vln-desktop  (in another terminal)"
    echo "    LiDAR below radius→ move robot away from obstacles"
    echo ""
    exit 1
elif [[ "$WARN" -gt 0 ]]; then
    echo "  Warnings present — review before enabling motion."
    echo "════════════════════════════════════════════════════════════════════"
    exit 0
else
    echo "  Stack looks healthy. Proceed with:"
    echo "    make vln-send TEXT=\"move forward slowly\""
    echo "════════════════════════════════════════════════════════════════════"
    exit 0
fi
