#!/bin/bash
# Fleet-Safe-VLA-OS — SSH into Yahboom RosMaster M3Pro
#
# Preferred: ASK4/LAN/DHCP address (run discover_yahboom.sh first)
# Fallback:  192.168.8.88 (hotspot/AP mode only — pass --hotspot)
#
# Usage:
#   ./scripts/real_robot/ssh_yahboom.sh                    # auto-detect IP
#   ./scripts/real_robot/ssh_yahboom.sh 192.168.1.105      # explicit IP
#   ./scripts/real_robot/ssh_yahboom.sh --hotspot          # force hotspot IP
#   YAHBOOM_IP=192.168.1.105 ./scripts/real_robot/ssh_yahboom.sh
#
# Default SSH user: yahboom  (change YAHBOOM_USER below or via env)
# Default SSH port: 22

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOTSPOT_IP="192.168.8.88"
YAHBOOM_USER="${YAHBOOM_USER:-yahboom}"
YAHBOOM_PORT="${YAHBOOM_PORT:-22}"
SSH_OPTS=(-o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new)

HOTSPOT_MODE=false
TARGET_IP=""

for arg in "$@"; do
    case "$arg" in
        --hotspot) HOTSPOT_MODE=true ;;
        --*)       ;;  # skip other flags
        *)         TARGET_IP="$arg" ;;
    esac
done

# ── Resolve target IP ─────────────────────────────────────────────────────────
if $HOTSPOT_MODE; then
    TARGET_IP="$HOTSPOT_IP"
    echo "[ssh] Hotspot mode → $TARGET_IP"
elif [[ -z "$TARGET_IP" && -n "${YAHBOOM_IP:-}" ]]; then
    TARGET_IP="$YAHBOOM_IP"
    echo "[ssh] Using YAHBOOM_IP env: $TARGET_IP"
elif [[ -z "$TARGET_IP" ]]; then
    echo "[ssh] No IP specified. Running auto-discovery..."
    TARGET_IP=$("$SCRIPT_DIR/discover_yahboom.sh" --quiet 2>/dev/null || echo "")
    if [[ -z "$TARGET_IP" ]]; then
        echo "[ERROR] Could not discover robot IP."
        echo "  Options:"
        echo "    ./scripts/real_robot/discover_yahboom.sh"
        echo "    ./scripts/real_robot/ssh_yahboom.sh --hotspot"
        echo "    ./scripts/real_robot/ssh_yahboom.sh <ip>"
        exit 1
    fi
    echo "[ssh] Discovered: $TARGET_IP"
fi

# ── Connectivity check ────────────────────────────────────────────────────────
if ! ping -c 1 -W 3 "$TARGET_IP" &>/dev/null; then
    echo "[WARN] Cannot ping $TARGET_IP — robot may be offline or on a different subnet."
    echo "  Try: ./scripts/real_robot/discover_yahboom.sh"
    read -rp "  Connect anyway? [y/N] " ans
    [[ "$ans" =~ ^[Yy] ]] || exit 1
fi

echo ""
echo "  Connecting: ssh ${YAHBOOM_USER}@${TARGET_IP} -p ${YAHBOOM_PORT}"
echo "  (default password: yahboom  — change it after first login)"
echo ""
echo "  Once connected, useful ROS2 commands:"
echo "    source /opt/ros/humble/setup.bash"
echo "    ros2 topic list"
echo "    ros2 launch yahboom_bringup bringup.launch.py"
echo ""

exec ssh "${SSH_OPTS[@]}" -p "$YAHBOOM_PORT" "${YAHBOOM_USER}@${TARGET_IP}" "$@"
