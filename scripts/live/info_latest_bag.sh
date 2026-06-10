#!/bin/bash
# FleetSafe — Show ros2 bag info for the latest m3pro_full_motion bag.
# Usage:
#   ./scripts/live/info_latest_bag.sh              # latest bag
#   ./scripts/live/info_latest_bag.sh /path/to/bag  # specific bag
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=/dev/null
source "${REPO_ROOT}/config/fleetsafe_real_robot.env"
# shellcheck source=/dev/null
source /opt/ros/humble/setup.bash

if [[ $# -ge 1 ]]; then
    BAG="$1"
else
    BAG_DIR="${REPO_ROOT}/${FLEETSAFE_BAG_DIR}"
    BAG=$(find "${BAG_DIR}" -maxdepth 1 -type d -name "m3pro_full_motion_*" \
          | sort | tail -1)
    if [[ -z "${BAG}" ]]; then
        echo "[ERROR] No m3pro_full_motion_* bags found in ${BAG_DIR}"
        exit 1
    fi
fi

echo "============================================================"
echo "  FleetSafe  |  Bag Info"
echo "  Bag: ${BAG}"
echo "============================================================"
echo ""
ros2 bag info "${BAG}"
