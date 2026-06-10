#!/bin/bash
# Fleet-Safe-VLA-OS — Discover Yahboom RosMaster M3Pro on the network
#
# Strategy (in order):
#   1. Tailscale — if installed, show tailscale peer IPs
#   2. ARP table — scan for Yahboom MAC prefixes (Espressif / Realtek)
#   3. mDNS      — avahi-browse for _ssh._tcp
#   4. nmap      — ping-scan the current subnet and 192.168.8.0/24
#   5. Fallback  — print 192.168.8.88 (hotspot/AP mode)
#
# 192.168.8.88 is the robot's hotspot fallback IP only.
# In normal (ASK4/client) mode the robot gets a DHCP address.
#
# Usage:
#   ./scripts/real_robot/discover_yahboom.sh            # auto-discover
#   ./scripts/real_robot/discover_yahboom.sh --hotspot  # print 192.168.8.88
#   ./scripts/real_robot/discover_yahboom.sh --quiet    # print IP only (for scripting)
#
# Output:
#   Prints candidate IPs. The first non-hotspot IP is the preferred address.
#   Set the result in your shell:  YAHBOOM_IP=$(./discover_yahboom.sh --quiet)

set -euo pipefail

HOTSPOT_IP="192.168.8.88"
HOTSPOT_SUBNET="192.168.8.0/24"
QUIET=false
HOTSPOT_MODE=false

for arg in "$@"; do
    case "$arg" in
        --hotspot) HOTSPOT_MODE=true ;;
        --quiet)   QUIET=true ;;
    esac
done

log()  { $QUIET || echo "$@"; }
warn() { $QUIET || echo "[WARN] $@"; }

if $HOTSPOT_MODE; then
    log ""
    log "[discover] --hotspot flag set. Using hardcoded hotspot/AP address."
    log "[discover] Robot must be in AP mode (not connected to a router)."
    log ""
    echo "$HOTSPOT_IP"
    exit 0
fi

log ""
log "============================================================"
log "  Fleet-Safe  |  Yahboom M3Pro Network Discovery"
log "  Preferred: ASK4/LAN DHCP  |  Fallback: $HOTSPOT_IP (hotspot)"
log "============================================================"
log ""

FOUND_IPS=()

# ── 1. Tailscale ─────────────────────────────────────────────────────────────
if command -v tailscale &>/dev/null; then
    log "[1/4] Checking Tailscale..."
    TS_OUT=$(tailscale status 2>/dev/null || true)
    if echo "$TS_OUT" | grep -qi "yahboom\|rosmaster\|m3pro\|robot"; then
        TS_IPS=$(echo "$TS_OUT" | grep -Ei "yahboom|rosmaster|m3pro|robot" | awk '{print $1}')
        for ip in $TS_IPS; do
            log "  [Tailscale] Found: $ip"
            FOUND_IPS+=("$ip")
        done
    else
        log "  [Tailscale] No robot peer found. Run 'tailscale status' for all peers."
        # Show all peers for manual inspection
        $QUIET || echo "$TS_OUT" | head -15 | sed 's/^/    /'
    fi
else
    log "[1/4] Tailscale not installed. Skipping."
fi

# ── 2. ARP table ─────────────────────────────────────────────────────────────
log ""
log "[2/4] Scanning ARP table for Yahboom MAC prefixes..."
# Yahboom RosMaster typically uses ESP32 (Espressif 3c:61:05 / 24:6f:28 / dc:54:75)
# or Rockchip/ARM SBC with Realtek WiFi (00:e0:4c)
YAHBOOM_MAC_PREFIXES="3c:61:05|24:6f:28|dc:54:75|30:ae:a4|b4:e6:2d|00:e0:4c"
ARP_HITS=$(arp -an 2>/dev/null | grep -iE "$YAHBOOM_MAC_PREFIXES" || true)
if [[ -n "$ARP_HITS" ]]; then
    while IFS= read -r line; do
        ip=$(echo "$line" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' | head -1)
        mac=$(echo "$line" | grep -oE '([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}' | head -1)
        log "  [ARP] Found: $ip  (MAC: $mac)"
        FOUND_IPS+=("$ip")
    done <<< "$ARP_HITS"
else
    log "  [ARP] No known Yahboom MAC prefixes in ARP table."
    log "  [ARP] Make sure the robot and this PC are on the same network."
fi

# ── 3. mDNS (avahi) ──────────────────────────────────────────────────────────
log ""
log "[3/4] Checking mDNS (_ssh._tcp)..."
if command -v avahi-browse &>/dev/null; then
    MDNS=$(timeout 5 avahi-browse -t -r _ssh._tcp 2>/dev/null | grep -Ei "yahboom|rosmaster|m3pro|robot" || true)
    if [[ -n "$MDNS" ]]; then
        while IFS= read -r line; do
            ip=$(echo "$line" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' | head -1)
            [[ -n "$ip" ]] && { log "  [mDNS] Found: $ip"; FOUND_IPS+=("$ip"); }
        done <<< "$MDNS"
    else
        log "  [mDNS] No Yahboom hostname found via Avahi."
    fi
else
    log "  [mDNS] avahi-browse not installed. Install: sudo apt install avahi-utils"
fi

# ── 4. nmap ping-scan ────────────────────────────────────────────────────────
log ""
log "[4/4] nmap ping-scan (current subnet + $HOTSPOT_SUBNET)..."
if command -v nmap &>/dev/null; then
    # Current default-route subnet
    DEFAULT_IFACE=$(ip route show default 2>/dev/null | awk '/default/ {print $5}' | head -1)
    CURRENT_SUBNET=$(ip -4 addr show "$DEFAULT_IFACE" 2>/dev/null | awk '/inet / {print $2}' | head -1)

    SUBNETS=("$HOTSPOT_SUBNET")
    [[ -n "$CURRENT_SUBNET" && "$CURRENT_SUBNET" != "$HOTSPOT_SUBNET" ]] && SUBNETS+=("$CURRENT_SUBNET")

    for subnet in "${SUBNETS[@]}"; do
        log "  Scanning $subnet ..."
        # Fast ping scan — no port scan
        NMAP_OUT=$(timeout 20 nmap -sn -T4 --open "$subnet" 2>/dev/null | grep "Nmap scan report" | grep -v "$(hostname)" || true)
        if [[ -n "$NMAP_OUT" ]]; then
            while IFS= read -r line; do
                ip=$(echo "$line" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' | head -1)
                [[ -n "$ip" ]] && log "  [nmap] Reachable: $ip  ← verify this is the robot"
            done <<< "$NMAP_OUT"
        else
            log "  [nmap] No hosts found on $subnet"
        fi
    done
else
    log "  nmap not installed. Install: sudo apt install nmap"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
log ""
log "============================================================"
if [[ ${#FOUND_IPS[@]} -gt 0 ]]; then
    BEST="${FOUND_IPS[0]}"
    log "  Best candidate (non-hotspot): $BEST"
    log ""
    log "  To connect:"
    log "    ./scripts/real_robot/ssh_yahboom.sh $BEST"
    log "    YAHBOOM_IP=$BEST ./scripts/real_robot/check_m3pro_topics.sh"
    log ""
    log "  All candidates:"
    for ip in "${FOUND_IPS[@]}"; do log "    $ip"; done
    if $QUIET; then echo "$BEST"; fi
else
    log "  No robot found automatically."
    log ""
    log "  Options:"
    log "   a) Robot in client mode: check router DHCP leases"
    log "   b) Robot in AP mode:  ./scripts/real_robot/ssh_yahboom.sh --hotspot"
    log "                         (connects to $HOTSPOT_IP)"
    log "   c) Tailscale:         tailscale up && tailscale status"
    log "   d) Manual:            YAHBOOM_IP=<ip> ./scripts/real_robot/ssh_yahboom.sh"
    if $QUIET; then echo "$HOTSPOT_IP"; fi
fi
log "============================================================"
log ""
