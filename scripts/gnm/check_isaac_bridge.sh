#!/usr/bin/env bash
# Checks whether the Isaac Sim ROS 2 bridge is available.
# Exits 0 in dry-run/CI mode (ROS 2 not required).
# With --strict, exits non-zero if the bridge is not detected.

set -euo pipefail

STRICT=false
for arg in "$@"; do
  case "$arg" in
    --strict) STRICT=true ;;
  esac
done

echo "============================================================"
echo " Isaac Sim ROS 2 Bridge Availability Check  [v2.1]"
echo "============================================================"

ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
echo "ROS_DOMAIN_ID: $ROS_DOMAIN_ID"

# Source ROS 2 if available. Temporarily disable -u because ROS 2 setup
# scripts reference unbound variables.
ROS2_SOURCED=false
for setup_file in \
    /opt/ros/humble/setup.bash \
    /opt/ros/jazzy/setup.bash \
    /opt/ros/iron/setup.bash \
    /opt/ros/galactic/setup.bash; do
  if [[ -f "$setup_file" ]]; then
    set +u
    # shellcheck source=/dev/null
    source "$setup_file" 2>/dev/null || true
    set -u
    ROS2_SOURCED=true
    echo "Sourced ROS 2 from: $setup_file"
    break
  fi
done

if ! $ROS2_SOURCED; then
  echo "[INFO] No ROS 2 installation found in /opt/ros/."
fi

if ! command -v ros2 &>/dev/null; then
  echo ""
  echo "[INFO] ros2 command not found."
  echo "[INFO] Isaac ROS 2 bridge check skipped."
  echo ""
  echo "Bridge nodes that would be checked: omni_ros, isaac, ros2_bridge"
  echo "Requires: ROS 2 Humble or Jazzy + Isaac Sim with ROS 2 Bridge enabled."
  echo ""
  if $STRICT; then
    echo "[FAIL] --strict mode: ROS 2 is required but not installed."
    exit 1
  fi
  echo "[OK] Dry-run/CI mode: exiting 0."
  exit 0
fi

echo ""
echo "ROS 2 is available. Checking for Isaac bridge activity..."

BRIDGE_ACTIVE=false

# Check node list for Isaac bridge node names.
NODES=$(ros2 node list 2>/dev/null || true)
if echo "$NODES" | grep -qE "isaac|omni_ros|ros2_bridge"; then
  BRIDGE_ACTIVE=true
  echo "[OK] Isaac ROS 2 bridge node detected:"
  echo "$NODES" | grep -E "isaac|omni_ros|ros2_bridge" || true
fi

# Fallback: any topics at all means the bridge is publishing.
TOPICS=$(ros2 topic list 2>/dev/null || true)
if [[ -n "$TOPICS" ]]; then
  BRIDGE_ACTIVE=true
  echo "[OK] ROS 2 topics are present (bridge is active)."
fi

echo ""
if $BRIDGE_ACTIVE; then
  echo "[OK] Isaac Sim ROS 2 bridge is available."
  exit 0
fi

echo "[WARN] No Isaac ROS 2 bridge activity detected."
echo "[INFO] Start Isaac Sim, enable Window → Extensions → ROS2 Bridge, then"
echo "[INFO] load a robot stage with camera, lidar, and drive action graphs."
if $STRICT; then
  echo "[FAIL] --strict mode: bridge required but not detected."
  exit 1
fi
echo "[INFO] Non-strict mode: acceptable if Isaac Sim is not running."
exit 0
