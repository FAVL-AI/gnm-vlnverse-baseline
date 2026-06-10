#!/bin/bash
# Fleet-Safe-VLA-OS — Yahboom Isaac Sim Telemetry Bridge
#
# Runs Isaac Sim headlessly as the simulation backend and streams robot
# telemetry to the FleetSafe operator dashboard over WebSocket.
#
# Usage:
#   ./scripts/isaaclab/run_yahboom_bridge.sh                  # headless (default)
#   ./scripts/isaaclab/run_yahboom_bridge.sh --gui            # with Isaac Sim GUI
#   ./scripts/isaaclab/run_yahboom_bridge.sh --robot m3pro    # M3Pro (URDF pending)
#   ./scripts/isaaclab/run_yahboom_bridge.sh --ws-port 8766   # custom WS port
#
# Then open the FleetSafe dashboard:
#   ./scripts/web/start_robot_viewer.sh
#   # Open: http://localhost:8080/yahboom
#
# Isaac Sim GUI debug mode (separate):
#   ./scripts/isaaclab/view_yahboom.sh --robot x3
#
# Telemetry flow:
#   Isaac Sim (this script, port 8765) → FleetSafe app (port 8080) → Browser

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "============================================================"
echo "  Fleet-Safe-VLA-OS  |  Yahboom Isaac Telemetry Bridge"
echo "  Isaac Sim : 5.1.0.0  |  Isaac Lab : 0.54.3"
echo "  WS Bridge : ws://localhost:8765"
echo "  Dashboard : http://localhost:8080/yahboom"
echo "============================================================"
echo ""

# ── Activate isaac conda environment ─────────────────────────────────────────
CONDA_INIT="${HOME}/miniforge3/etc/profile.d/conda.sh"
if [[ ! -f "$CONDA_INIT" ]]; then
    echo "[ERROR] conda not found at $CONDA_INIT"
    exit 1
fi
# shellcheck source=/dev/null
source "$CONDA_INIT"
conda activate isaac

# ── Accept Isaac Sim EULA ────────────────────────────────────────────────────
export OMNI_KIT_ACCEPT_EULA=Y

# ── Suppress nucleus connection (offline/local mode) ─────────────────────────
export OMNI_SERVER_SEARCH_TIMEOUT=1
export OMNI_CACHE_PATH="${REPO_ROOT}/.omni_cache"

# ── Python path ───────────────────────────────────────────────────────────────
export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"

PYTHON="${CONDA_PREFIX}/bin/python"

echo "[INFO] Starting bridge (Isaac Sim headless)..."
echo "[INFO] USD cache loaded from data/usd_cache/ — startup is fast."
echo "[INFO] Open dashboard: http://localhost:8080/yahboom"
echo ""

"$PYTHON" "${SCRIPT_DIR}/run_yahboom_bridge.py" "$@"
