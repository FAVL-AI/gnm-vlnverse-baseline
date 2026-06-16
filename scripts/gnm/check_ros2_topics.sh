#!/usr/bin/env bash
# Check whether required ROS 2 topics are available.
# In dry-run/CI mode (no ROS 2 installed), exits 0 and explains what was skipped.
# With --strict, exits non-zero if ROS 2 is missing or required topics are absent.

set -euo pipefail

STRICT=false
for arg in "$@"; do
  case "$arg" in
    --strict) STRICT=true ;;
  esac
done

REQUIRED_TOPICS=(
  "/camera/image_raw"
  "/odom"
  "/tf"
  "/scan"
  "/cmd_vel"
)

echo "============================================================"
echo " FleetSafe-GNM ROS 2 Topic Checker"
echo "============================================================"

ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
echo "ROS_DOMAIN_ID: $ROS_DOMAIN_ID"

# Source ROS 2 if a setup file is available.
# Temporarily disable -u because ROS 2 setup scripts reference unbound variables.
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

# Check whether the ros2 CLI is available.
if ! command -v ros2 &>/dev/null; then
  echo ""
  echo "[INFO] ros2 command not found."
  echo "[INFO] Live ROS 2 topic checks were skipped."
  echo "[INFO] To run live checks, install ROS 2 (Humble or Jazzy) and ensure the"
  echo "[INFO] Isaac Sim ROS 2 bridge is running."
  echo ""
  echo "Required topics that would be checked:"
  for topic in "${REQUIRED_TOPICS[@]}"; do
    echo "  $topic"
  done
  echo ""
  if $STRICT; then
    echo "[FAIL] --strict mode: ROS 2 is required but not installed."
    exit 1
  fi
  echo "[OK] Dry-run/CI mode: exiting 0 (ROS 2 not required in CI)."
  exit 0
fi

echo ""
echo "ROS 2 is available."
echo "Active topics:"
ros2 topic list 2>/dev/null || true
echo ""

MISSING=()
for topic in "${REQUIRED_TOPICS[@]}"; do
  if ros2 topic list 2>/dev/null | grep -qF "$topic"; then
    echo "[OK] Found: $topic"
  else
    echo "[MISSING] $topic"
    MISSING+=("$topic")
  fi
done

echo ""
if [[ ${#MISSING[@]} -eq 0 ]]; then
  echo "[OK] All required topics are present."
  exit 0
else
  echo "[WARN] Missing topics:"
  for t in "${MISSING[@]}"; do
    echo "  $t"
  done
  if $STRICT; then
    echo "[FAIL] --strict mode: required topics are missing."
    exit 1
  fi
  echo "[INFO] Non-strict mode: missing topics are acceptable if Isaac Sim is not running."
  exit 0
fi
