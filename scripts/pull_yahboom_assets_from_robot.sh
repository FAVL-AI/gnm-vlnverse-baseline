#!/usr/bin/env bash
# scripts/pull_yahboom_assets_from_robot.sh
# ─────────────────────────────────────────────────────────────────────────────
# Pull Yahboom M3 Pro ROS 2 workspace URDF/mesh files from the real robot
# via scp, then search for URDF/xacro/meshes.
#
# Usage:
#   bash scripts/pull_yahboom_assets_from_robot.sh yahboom@192.168.x.x
#   bash scripts/pull_yahboom_assets_from_robot.sh yahboom@192.168.x.x --port 22
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROBOT_HOST="${1:-}"
SSH_PORT="${2:-22}"
DEST_DIR="${REPO_ROOT}/external/yahboom/robot_ws_src"
ASSET_DIR="${REPO_ROOT}/assets/robots/yahboom_m3_pro"

if [[ -z "${ROBOT_HOST}" ]]; then
  echo "Usage: bash scripts/pull_yahboom_assets_from_robot.sh yahboom@<ROBOT_IP>"
  echo "  Example: bash scripts/pull_yahboom_assets_from_robot.sh yahboom@192.168.1.100"
  exit 1
fi

echo "========================================"
echo "  FleetSafe — Pull Yahboom Assets"
echo "  From: ${ROBOT_HOST}"
echo "  Into: ${DEST_DIR}"
echo "========================================"
echo ""

mkdir -p "${DEST_DIR}"
mkdir -p "${ASSET_DIR}"

# ── Candidate ROS 2 workspace paths on the robot ──────────────────────────
ROBOT_WS_CANDIDATES=(
  "~/ros2_ws/src"
  "~/colcon_ws/src"
  "~/yahboom_ws/src"
  "~/catkin_ws/src"
  "/opt/ros/*/share/yahboom*"
)

echo "--- Searching for URDF/xacro on robot ---"
echo "  Checking robot paths: ${ROBOT_WS_CANDIDATES[*]}"
echo ""

# First, try to list URDF/xacro files on the robot
FOUND_PATHS=""
FOUND_PATHS=$(ssh -p "${SSH_PORT}" "${ROBOT_HOST}" \
  "find ~/ros2_ws/src ~/colcon_ws/src ~/yahboom_ws/src /opt/ros \
   \( -iname '*.urdf' -o -iname '*.xacro' -o -iname '*.stl' -o -iname '*.dae' \) \
   2>/dev/null | head -50" 2>/dev/null || true)

if [[ -z "${FOUND_PATHS}" ]]; then
  echo "[WARN] No URDF/xacro found in standard ROS workspace paths on ${ROBOT_HOST}"
  echo "  Try:"
  echo "    ssh ${ROBOT_HOST} 'find / -iname \"*.urdf\" 2>/dev/null | head -20'"
  echo "  Or check if a yahboom_description package exists:"
  echo "    ssh ${ROBOT_HOST} 'ros2 pkg list | grep yahboom'"
else
  echo "  Found on robot:"
  echo "${FOUND_PATHS}" | head -20 | sed 's/^/  /'
fi

echo ""

# ── Pull ROS workspace src ─────────────────────────────────────────────────
echo "--- Pulling ROS 2 workspace src directories ---"
SCP_OK=false

for ws in "ros2_ws/src" "colcon_ws/src" "yahboom_ws/src"; do
  echo "  Trying ${ROBOT_HOST}:~/${ws} ..."
  if scp -P "${SSH_PORT}" -r "${ROBOT_HOST}:~/${ws}" "${DEST_DIR}/${ws//\//_}" 2>/dev/null; then
    echo "  [OK]  Pulled ~/${ws} → ${DEST_DIR}/${ws//\//_}"
    SCP_OK=true
  else
    echo "  [--]  ~/${ws} not found or not accessible."
  fi
done

if ! $SCP_OK; then
  echo ""
  echo "[WARN] Could not pull any workspace. Try manually:"
  echo "  scp -r ${ROBOT_HOST}:~/ros2_ws/src ${DEST_DIR}/"
  echo ""
  echo "  Or copy package.xml path:"
  echo "  ssh ${ROBOT_HOST} 'find / -name package.xml | xargs grep -l yahboom 2>/dev/null'"
fi

echo ""

# ── Search pulled files ────────────────────────────────────────────────────
echo "--- Searching pulled files ---"
URDF_COUNT=$(find "${DEST_DIR}" -iname "*.urdf" 2>/dev/null | wc -l)
XACRO_COUNT=$(find "${DEST_DIR}" -iname "*.xacro" 2>/dev/null | wc -l)
STL_COUNT=$(find "${DEST_DIR}" -iname "*.stl" 2>/dev/null | wc -l)

printf "  URDF:   %d\n" "${URDF_COUNT}"
printf "  Xacro:  %d\n" "${XACRO_COUNT}"
printf "  STL:    %d\n" "${STL_COUNT}"

if [[ ${URDF_COUNT} -gt 0 ]] || [[ ${XACRO_COUNT} -gt 0 ]]; then
  echo ""
  echo "  Found URDF/Xacro files:"
  find "${DEST_DIR}" \( -iname "*.urdf" -o -iname "*.xacro" \) 2>/dev/null | head -10 | sed 's/^/    /'
  echo ""
  echo "  Next step — import to Isaac Sim:"
  BEST=$(find "${DEST_DIR}" -iname "*.urdf" 2>/dev/null | head -1)
  if [[ -n "${BEST}" ]]; then
    echo "    bash scripts/import_yahboom_m3_urdf_to_isaac.sh \"${BEST}\""
  fi
else
  echo ""
  echo "[BLOCKED] No URDF/Xacro found after pulling from robot."
  echo "  Check whether yahboom_description or similar package is installed."
fi

echo ""
echo "  Re-run asset search:"
echo "    bash scripts/setup_yahboom_m3_assets.sh --skip-clone"
