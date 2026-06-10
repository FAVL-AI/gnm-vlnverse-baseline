#!/usr/bin/env bash
# Install FleetSafe desktop launchers to ~/Desktop and ~/.local/share/applications.
set -euo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ICON_DIR="$PROJECT/command-center/frontend/public/icons"
APPS_DIR="$HOME/.local/share/applications"
DESKTOP_DIR="$HOME/Desktop"

mkdir -p "$APPS_DIR" "$DESKTOP_DIR"

# ── icon helper ──────────────────────────────────────────────────────────────
# Use the SVG icon if present, fall back to a system icon name.
_icon() {
    local name="$1"
    local svg="$ICON_DIR/${name}.svg"
    local png="$ICON_DIR/${name}.png"
    if   [[ -f "$png" ]]; then echo "$png"
    elif [[ -f "$svg" ]]; then echo "$svg"
    else echo "utilities-terminal"
    fi
}

# ── write .desktop file ──────────────────────────────────────────────────────
_write_desktop() {
    local id="$1" name="$2" comment="$3" exec_cmd="$4" icon="$5" categories="${6:-Utility;}"

    local content="[Desktop Entry]
Version=1.0
Type=Application
Name=$name
Comment=$comment
Exec=bash -c '$exec_cmd'
Icon=$icon
Terminal=true
Categories=$categories
StartupNotify=true
"
    echo "$content" > "$APPS_DIR/${id}.desktop"
    chmod 644 "$APPS_DIR/${id}.desktop"

    if [[ -d "$DESKTOP_DIR" ]]; then
        cp "$APPS_DIR/${id}.desktop" "$DESKTOP_DIR/${id}.desktop"
        chmod +x "$DESKTOP_DIR/${id}.desktop"
        # Mark as trusted if gio is available
        gio set "$DESKTOP_DIR/${id}.desktop" "metadata::trusted" true 2>/dev/null || true
    fi

    echo "  ✔  $name"
}

echo ""
echo "Installing FleetSafe desktop launchers..."
echo ""

_write_desktop \
    "fleetsafe-launch" \
    "FleetSafe — Launch" \
    "Start backend, frontend, and dashboard" \
    "cd $PROJECT && ./launch_fleetsafe_all.sh; read -rp 'Press Enter to close'" \
    "$(_icon fleetsafe)" \
    "Science;Robotics;"

_write_desktop \
    "fleetsafe-stop" \
    "FleetSafe — Stop" \
    "Stop all FleetSafe services" \
    "cd $PROJECT && ./stop_fleetsafe_all.sh; read -rp 'Press Enter to close'" \
    "$(_icon fleetsafe-stop)" \
    "Science;Robotics;"

_write_desktop \
    "fleetsafe-status" \
    "FleetSafe — Status" \
    "Show running services, ports, and log tail" \
    "cd $PROJECT && ./fleetsafe-status.sh; read -rp 'Press Enter to close'" \
    "$(_icon fleetsafe-status)" \
    "Science;Robotics;"

_write_desktop \
    "fleetsafe-dashboard" \
    "FleetSafe — Dashboard" \
    "Open the FleetSafe command-center in browser" \
    "bash $PROJECT/scripts/open_dashboard.sh http://localhost:3000/dashboard/demo" \
    "$(_icon fleetsafe-dashboard)" \
    "Science;Robotics;"

_write_desktop \
    "fleetsafe-gazebo" \
    "FleetSafe — Launch + Gazebo" \
    "Start all services including Gazebo/ROS2 bridge" \
    "cd $PROJECT && ./launch_fleetsafe_all.sh --gazebo; read -rp 'Press Enter to close'" \
    "$(_icon fleetsafe)" \
    "Science;Robotics;"

_write_desktop \
    "fleetsafe-isaac" \
    "FleetSafe — Launch + Isaac" \
    "Start all services including Isaac Sim GUI" \
    "cd $PROJECT && ./launch_fleetsafe_all.sh --isaac; read -rp 'Press Enter to close'" \
    "$(_icon fleetsafe)" \
    "Science;Robotics;"

# Refresh GNOME/KDE app database
update-desktop-database "$APPS_DIR" 2>/dev/null || true

echo ""
echo "Done. Launchers installed to:"
echo "  $APPS_DIR/"
echo "  $DESKTOP_DIR/"
echo ""
echo "If icons appear as question marks on the Desktop, right-click → Allow Launching."
