#!/usr/bin/env bash
# scripts/import_yahboom_m3_urdf_to_isaac.sh
# Attempt headless Isaac Sim URDF→USD conversion for Yahboom M3 Pro.
# Falls back gracefully with manual instructions if Isaac Python is unavailable.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

URDF_PATH="${REPO_ROOT}/assets/robots/yahboom_m3_pro/yahboom_m3pro.urdf"
USD_PATH="${REPO_ROOT}/assets/robots/yahboom_m3_pro/yahboom_m3pro.usd"
STATUS_PATH="${REPO_ROOT}/assets/robots/yahboom_m3_pro/isaac_import_status.json"
SCRIPT="${REPO_ROOT}/scripts/isaac/import_yahboom_m3_urdf.py"

echo "========================================"
echo "  FleetSafe — Yahboom URDF → USD Import"
echo "========================================"
echo "  URDF: ${URDF_PATH}"
echo "  USD:  ${USD_PATH}"
echo ""

if [[ ! -f "${URDF_PATH}" ]]; then
    echo "[FAIL] URDF not found: ${URDF_PATH}"
    echo "  Run: bash scripts/setup_yahboom_m3_assets.sh"
    exit 1
fi

if [[ -f "${USD_PATH}" ]]; then
    echo "[OK]  USD already exists: ${USD_PATH}"
    echo "  $(ls -lh "${USD_PATH}" | awk '{print $5, $9}')"
    python3 -c "
import json; from datetime import datetime, timezone; from pathlib import Path
p=Path('${STATUS_PATH}')
p.write_text(json.dumps({'status':'already_exists','urdf_exists':True,'usd_exists':True,'usd_path':'${USD_PATH}','generated_at':datetime.now(timezone.utc).isoformat()},indent=2))
"
    exit 0
fi

# ── Detect Isaac Python ──────────────────────────────────────────────────────
CONDA_BASE="${CONDA_PREFIX_1:-$(conda info --base 2>/dev/null || echo '/home/favl/miniforge3')}"
CONDA_BASE="${CONDA_BASE%/envs/*}"
ISAAC_PYTHON="${CONDA_BASE}/envs/isaac/bin/python"

if [[ ! -f "${ISAAC_PYTHON}" ]]; then
    ISAAC_PYTHON="$(which python3)"
fi

echo "  Python: ${ISAAC_PYTHON}"
echo ""

# ── Source ROS 2 in subshell so set -u errors don't abort this script ────────
ROS_SETUP=""
if [[ -f /opt/ros/humble/setup.bash ]]; then
    ROS_SETUP="source /opt/ros/humble/setup.bash"
fi

# ── Run import script ────────────────────────────────────────────────────────
echo "  Running headless Isaac URDF import..."
bash -c "${ROS_SETUP:+${ROS_SETUP} &&} '${ISAAC_PYTHON}' '${SCRIPT}'" 2>&1 || true

echo ""
if [[ -f "${USD_PATH}" ]]; then
    echo "[OK]  USD created: ${USD_PATH}"
    echo "  $(ls -lh "${USD_PATH}" | awk '{print $5, $9}')"
    exit 0
else
    echo "[INFO] Automatic import did not produce USD."
    if [[ -f "${STATUS_PATH}" ]]; then
        echo "  Status:"
        python3 -c "import json; d=json.load(open('${STATUS_PATH}')); print('  ' + d.get('message',''))" 2>/dev/null || true
    fi
    echo ""
    echo "  Manual import instructions:"
    echo "  See: docs/YAHBOOM_URDF_TO_USD_IMPORT.md"
    exit 0
fi
