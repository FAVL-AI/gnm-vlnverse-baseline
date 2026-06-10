#!/bin/bash
# FleetSafe — Check robot SSH/ping reachability (works when robot is OFF too).
#
# Prints a clean status table and exits with a meaningful code:
#   0 — at least one SSH connection works
#   2 — ping works but SSH fails (robot up but SSH not ready yet)
#   3 — neither IP responds (robot likely powered off)
#
# Usage: ./scripts/robot/check_robot_connection.sh
# shellcheck disable=SC2034
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=/dev/null
source "${REPO_ROOT}/config/fleetsafe_real_robot.env"

SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=5 -o LogLevel=ERROR)

# ── Test a single IP ──────────────────────────────────────────────────────────
check_ip() {
    local ip="$1" label="$2"
    local ping_ok=FAIL ssh_ok=FAIL

    if ping -c 1 -W 2 "${ip}" >/dev/null 2>&1; then
        ping_ok=OK
    fi

    if [[ "${ping_ok}" == "OK" ]]; then
        if ssh "${SSH_OPTS[@]}" "${ROBOT_USER}@${ip}" "exit 0" 2>/dev/null; then
            ssh_ok=OK
        fi
    fi

    local ping_fmt ssh_fmt
    if [[ "${ping_ok}" == "OK" ]]; then ping_fmt="OK  "; else ping_fmt="FAIL"; fi
    if [[ "${ssh_ok}"  == "OK" ]]; then ssh_fmt="OK  "; else ssh_fmt="FAIL"; fi

    printf "  %-14s %-22s  ping: %s    ssh: %s\n" \
        "${label}" "${ip}" "${ping_fmt}" "${ssh_fmt}"

    # Return results via globals
    eval "${label//-/_}_PING=${ping_ok}"
    eval "${label//-/_}_SSH=${ssh_ok}"
}

echo "============================================================"
echo "  FleetSafe  |  Robot Connection Check"
echo "  User        : ${ROBOT_USER}"
echo "============================================================"
echo ""

check_ip "${ROBOT_HOTSPOT_IP}"  "Hotspot-IP"
check_ip "${ROBOT_TAILSCALE_IP}" "Tailscale-IP"
echo ""

# ── Summarise ─────────────────────────────────────────────────────────────────
if [[ "${Hotspot_IP_SSH:-FAIL}" == "OK" || "${Tailscale_IP_SSH:-FAIL}" == "OK" ]]; then
    if [[ "${Hotspot_IP_SSH:-FAIL}" == "OK" ]]; then
        echo "  Robot reachable via hotspot  (${ROBOT_USER}@${ROBOT_HOTSPOT_IP})"
    fi
    if [[ "${Tailscale_IP_SSH:-FAIL}" == "OK" ]]; then
        echo "  Robot reachable via Tailscale (${ROBOT_USER}@${ROBOT_TAILSCALE_IP})"
    fi
    echo ""
    echo "  Ready.  Run:"
    echo "    ./scripts/robot/install_robot_tools.sh"
    exit 0
fi

if [[ "${Hotspot_IP_PING:-FAIL}" == "OK" || "${Tailscale_IP_PING:-FAIL}" == "OK" ]]; then
    echo "  Ping succeeds but SSH is not yet responding."
    echo "  The Jetson may still be booting.  Wait 30 seconds and retry:"
    echo "    ./scripts/robot/check_robot_connection.sh"
    exit 2
fi

echo "  Robot appears offline or unreachable."
echo ""
echo "  Check:"
echo "    1. Robot powered on"
echo "    2. Jetson boot completed (wait 60-90 s after power-on)"
echo "    3. RTX desktop joined the same hotspot (or Tailscale connected)"
echo "    4. SSH key or password configured for ${ROBOT_USER}@${ROBOT_HOTSPOT_IP}"
echo ""
echo "  While the robot is off, you can prepare the installer bundle:"
echo "    make robot-bundle"
echo "    # then when robot is on:"
echo "    make robot-install"
exit 3
