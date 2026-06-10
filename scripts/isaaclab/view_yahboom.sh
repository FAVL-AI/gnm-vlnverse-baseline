#!/bin/bash
# Fleet-Safe-VLA-OS — Yahboom Isaac Sim GUI Viewer
#
# Launches Isaac Sim with a visible GUI showing a Yahboom robot on a
# ground plane.  Physics runs but no control is applied.
#
# Robot models:
#   --robot x3      RosMaster X3    (differential drive)  [available]
#   --robot m3pro   RosMaster M3Pro (mecanum / holonomic)  [URDF pending]
#
# Requirements:
#   - conda env 'isaac': Isaac Sim 5.1.0.0 + Isaac Lab 0.54.3
#   - NVIDIA GPU with CUDA (RTX 4080 SUPER confirmed)
#
# Usage:
#   ./scripts/isaaclab/view_yahboom.sh                    # X3 (default)
#   ./scripts/isaaclab/view_yahboom.sh --robot x3
#   ./scripts/isaaclab/view_yahboom.sh --robot m3pro      # needs URDF first
#   ./scripts/isaaclab/view_yahboom.sh --device cpu       # CPU fallback (slow)
#   ./scripts/isaaclab/view_yahboom.sh --livestream 1     # remote stream

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "============================================================"
echo "  Fleet-Safe-VLA-OS  |  Yahboom  |  Isaac Sim GUI Viewer"
echo "  Isaac Sim : 5.1.0.0  |  Isaac Lab : 0.54.3"
echo "  Env       : isaac (conda)"
echo "  Repo      : $REPO_ROOT"
echo "============================================================"
echo ""

# ── Activate isaac conda environment ────────────────────────────────────────
CONDA_INIT="${HOME}/miniforge3/etc/profile.d/conda.sh"
if [[ ! -f "$CONDA_INIT" ]]; then
    echo "[ERROR] conda not found at $CONDA_INIT"
    echo "  Adjust CONDA_INIT in this script if conda is installed elsewhere."
    exit 1
fi
# shellcheck source=/dev/null
source "$CONDA_INIT"
conda activate isaac

# ── Accept Isaac Sim EULA ────────────────────────────────────────────────────
export OMNI_KIT_ACCEPT_EULA=Y

# ── Suppress Omniverse nucleus connection attempts (offline/local mode) ──────
export OMNI_SERVER_SEARCH_TIMEOUT=1
export OMNI_CACHE_PATH="${REPO_ROOT}/.omni_cache"

# ── Python path: repo root so fleet_safe_vla package is importable ───────────
export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"

# ── Run viewer ───────────────────────────────────────────────────────────────
PYTHON="${CONDA_PREFIX}/bin/python"

echo "[INFO] Starting Isaac Sim GUI..."
echo "[INFO] First run converts URDF → USD (cached at data/usd_cache/)"
echo "[INFO] Subsequent runs load from USD cache (faster startup)."
echo ""

"$PYTHON" "${SCRIPT_DIR}/view_yahboom.py" "$@"
