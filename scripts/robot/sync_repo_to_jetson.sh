#!/usr/bin/env bash
# sync_repo_to_jetson.sh — Push a runtime copy of the repo to the Jetson.
#
# This is NOT a git clone.  The Jetson gets a flat rsync copy of the repo
# so that scripts (especially run_vln_m3pro.py) can be run there if needed.
# All development, git history, and large data stay on the RTX desktop.
#
# What is excluded:
#   .git/               — git history (not needed on Jetson)
#   data/real_robot_bags/  — recorded bags (stay on desktop)
#   results/            — benchmark outputs (stay on desktop)
#   logs/               — log files
#   .next/              — Next.js build cache
#   node_modules/       — frontend dependencies
#   __pycache__/        — Python bytecode
#   *.db3               — ROS2 bag data
#
# Usage:
#   bash scripts/robot/sync_repo_to_jetson.sh
#   make robot-sync-repo

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

JETSON_USER="${JETSON_USER:-jetson}"
JETSON_HOST="${JETSON_HOST:-172.20.10.14}"
JETSON_DEST="${JETSON_DEST:-~/robotics/FleetSafe-VisualNav-Benchmark}"
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes"

echo ""
echo "════════════════════════════════════════════════════════════════════"
echo "  FleetSafe  |  Sync repo to Jetson"
echo "  Source : ${REPO_ROOT}/"
echo "  Dest   : ${JETSON_USER}@${JETSON_HOST}:${JETSON_DEST}/"
echo ""
echo "  NOTE: This is NOT a git clone — just a runtime copy for scripts."
echo "        All git history, data, and results stay on the desktop."
echo "════════════════════════════════════════════════════════════════════"
echo ""

# ── Reachability check ────────────────────────────────────────────────────────
if ! ssh $SSH_OPTS "${JETSON_USER}@${JETSON_HOST}" "echo ok" &>/dev/null; then
    echo "[FAIL] Cannot reach ${JETSON_USER}@${JETSON_HOST}"
    echo "       Check: ping ${JETSON_HOST}"
    echo "       Check: ssh ${JETSON_USER}@${JETSON_HOST}"
    exit 1
fi

# ── rsync ─────────────────────────────────────────────────────────────────────
rsync -avz --progress \
    --exclude=".git" \
    --exclude="data/real_robot_bags" \
    --exclude="data/gnm_datasets" \
    --exclude="data/training_episodes" \
    --exclude="data/training_episodes_with_images" \
    --exclude="results" \
    --exclude="logs" \
    --exclude=".next" \
    --exclude="node_modules" \
    --exclude="__pycache__" \
    --exclude="*.db3" \
    --exclude="*.pyc" \
    --exclude=".mypy_cache" \
    --exclude=".ruff_cache" \
    --exclude="IsaacLabAssets" \
    --exclude="paper/*.pdf" \
    "${REPO_ROOT}/" \
    "${JETSON_USER}@${JETSON_HOST}:${JETSON_DEST}/"

echo ""
echo "[OK] rsync complete."
echo ""

# ── Verify key files exist on Jetson ─────────────────────────────────────────
echo "── Verifying key files on Jetson ────────────────────────────────────"
CHECKS=(
    "scripts/real_robot/run_vln_m3pro.py"
    "scripts/live/check_vln_stack.sh"
    "scripts/live/send_vln_instruction.sh"
    "fleet_safe_vla/vln/__init__.py"
)

ALL_OK=1
for f in "${CHECKS[@]}"; do
    if ssh $SSH_OPTS "${JETSON_USER}@${JETSON_HOST}" \
        "test -f '${JETSON_DEST}/${f}'" 2>/dev/null; then
        echo "  [OK]  ${f}"
    else
        echo "  [MISS] ${f}"
        ALL_OK=0
    fi
done

echo ""
if [[ "$ALL_OK" -eq 1 ]]; then
    echo "[OK] All key files present on Jetson."
else
    echo "[WARN] Some files missing — rsync may have been partial."
fi

echo ""
echo "  To run the VLN controller on the Jetson directly:"
echo "    ssh ${JETSON_USER}@${JETSON_HOST}"
echo "    cd ${JETSON_DEST}"
echo "    source /opt/ros/humble/setup.bash"
echo "    export ROS_DOMAIN_ID=30 ROS_LOCALHOST_ONLY=0"
echo "    /usr/bin/python3 scripts/real_robot/run_vln_m3pro.py --backbone auto"
echo ""
echo "  Recommended: run the controller on the RTX desktop instead"
echo "  (more compute, same ROS domain, Jetson only exposes sensor topics)."
echo ""
