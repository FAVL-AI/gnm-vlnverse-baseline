#!/bin/bash
# Fleet-Safe-VLA-OS — Remote screen access to Yahboom M3Pro SBC
#
# Three methods (in preference order):
#   1. RustDesk — if installed on both ends
#   2. VNC via SSH tunnel — x11vnc on robot, vncviewer here
#   3. X11 forwarding over SSH (for GUI apps only)
#
# IP discovery:
#   Prefers ASK4/LAN/DHCP.  Use --hotspot for 192.168.8.88.
#
# Usage:
#   ./scripts/real_robot/remote_screen_yahboom.sh              # auto IP
#   ./scripts/real_robot/remote_screen_yahboom.sh --hotspot    # hotspot IP
#   ./scripts/real_robot/remote_screen_yahboom.sh --method vnc # force VNC
#   ./scripts/real_robot/remote_screen_yahboom.sh --method x11 # X11 forward
#   YAHBOOM_IP=192.168.1.105 ./scripts/real_robot/remote_screen_yahboom.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOTSPOT_IP="192.168.8.88"
YAHBOOM_USER="${YAHBOOM_USER:-yahboom}"
YAHBOOM_PORT="${YAHBOOM_PORT:-22}"
VNC_PORT=5900
METHOD="${METHOD:-auto}"
HOTSPOT_MODE=false
TARGET_IP=""

for arg in "$@"; do
    case "$arg" in
        --hotspot)       HOTSPOT_MODE=true ;;
        --method)        shift; METHOD="$arg" ;;
        --method=*)      METHOD="${arg#--method=}" ;;
        --*)             ;;
        *)               TARGET_IP="$arg" ;;
    esac
done

# ── Resolve IP ────────────────────────────────────────────────────────────────
if $HOTSPOT_MODE; then
    TARGET_IP="$HOTSPOT_IP"
elif [[ -z "$TARGET_IP" && -n "${YAHBOOM_IP:-}" ]]; then
    TARGET_IP="$YAHBOOM_IP"
elif [[ -z "$TARGET_IP" ]]; then
    TARGET_IP=$("$SCRIPT_DIR/discover_yahboom.sh" --quiet 2>/dev/null || echo "")
    [[ -z "$TARGET_IP" ]] && TARGET_IP="$HOTSPOT_IP"
fi

SSH_OPTS=(-o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new -p "$YAHBOOM_PORT")

echo "============================================================"
echo "  Fleet-Safe  |  Remote Screen — Yahboom M3Pro"
echo "  Robot IP: $TARGET_IP"
echo "  Method:   $METHOD"
echo "============================================================"
echo ""

# ── Method: auto — pick best available ───────────────────────────────────────
if [[ "$METHOD" == "auto" ]]; then
    if command -v rustdesk &>/dev/null; then
        METHOD="rustdesk"
    elif command -v vncviewer &>/dev/null || command -v xtightvncviewer &>/dev/null; then
        METHOD="vnc"
    else
        METHOD="x11"
    fi
    echo "[remote] Auto-selected method: $METHOD"
    echo ""
fi

# ── Method: RustDesk ─────────────────────────────────────────────────────────
if [[ "$METHOD" == "rustdesk" ]]; then
    echo "[RustDesk] Looking up robot's RustDesk ID via SSH..."
    RUSTDESK_ID=$(ssh "${SSH_OPTS[@]}" "${YAHBOOM_USER}@${TARGET_IP}" \
        "rustdesk --get-id 2>/dev/null || cat ~/.config/RustDesk/RustDesk.toml 2>/dev/null | grep id | head -1" 2>/dev/null || true)
    if [[ -n "$RUSTDESK_ID" ]]; then
        ID=$(echo "$RUSTDESK_ID" | grep -oE '[0-9]+' | head -1)
        echo "[RustDesk] Robot ID: $ID"
        echo "  Opening RustDesk to $ID ..."
        rustdesk "$ID" 2>/dev/null &
    else
        echo "[RustDesk] Could not retrieve robot ID."
        echo "  Manual steps:"
        echo "  1. On the robot: sudo apt install rustdesk && rustdesk"
        echo "  2. Note the 9-digit ID shown in RustDesk"
        echo "  3. On this PC:   rustdesk <ID>"
        echo ""
        echo "  Alternatively, use: $0 --method vnc"
    fi
    exit 0
fi

# ── Method: VNC via SSH tunnel ────────────────────────────────────────────────
if [[ "$METHOD" == "vnc" ]]; then
    LOCAL_VNC_PORT=5901

    echo "[VNC] Ensuring x11vnc is running on robot..."
    ssh "${SSH_OPTS[@]}" "${YAHBOOM_USER}@${TARGET_IP}" \
        "command -v x11vnc &>/dev/null && pgrep x11vnc &>/dev/null || x11vnc -display :0 -forever -shared -bg -nopw -rfbport $VNC_PORT 2>/dev/null" \
        2>/dev/null || {
        echo "[WARN] Could not start x11vnc on robot."
        echo "  On the robot, run:"
        echo "    sudo apt install x11vnc"
        echo "    x11vnc -display :0 -forever -shared -nopw"
    }

    echo "[VNC] Opening SSH tunnel: localhost:$LOCAL_VNC_PORT → ${TARGET_IP}:${VNC_PORT}"
    ssh "${SSH_OPTS[@]}" -fNL "$LOCAL_VNC_PORT:localhost:$VNC_PORT" "${YAHBOOM_USER}@${TARGET_IP}" &
    TUNNEL_PID=$!
    sleep 1

    VIEWER=""
    command -v vncviewer         &>/dev/null && VIEWER="vncviewer"
    command -v xtightvncviewer   &>/dev/null && VIEWER="xtightvncviewer"
    command -v xtigervncviewer   &>/dev/null && VIEWER="xtigervncviewer"

    if [[ -z "$VIEWER" ]]; then
        echo "[VNC] No VNC viewer found. Install: sudo apt install tigervnc-viewer"
        echo "  Tunnel is open at localhost:$LOCAL_VNC_PORT — connect manually."
        kill "$TUNNEL_PID" 2>/dev/null
        exit 1
    fi

    echo "[VNC] Connecting: $VIEWER localhost:$LOCAL_VNC_PORT"
    "$VIEWER" "localhost:$LOCAL_VNC_PORT" 2>/dev/null
    kill "$TUNNEL_PID" 2>/dev/null
    exit 0
fi

# ── Method: X11 forwarding ───────────────────────────────────────────────────
if [[ "$METHOD" == "x11" ]]; then
    echo "[X11] Connecting with X11 forwarding (for GUI apps only)..."
    echo "  On the robot, run: export DISPLAY=:0 && <app>"
    echo ""
    exec ssh "${SSH_OPTS[@]}" -X "${YAHBOOM_USER}@${TARGET_IP}"
fi

echo "[ERROR] Unknown method: $METHOD  (use: rustdesk | vnc | x11)"
exit 1
