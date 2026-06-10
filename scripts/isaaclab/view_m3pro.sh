#!/usr/bin/env bash
# scripts/isaaclab/view_m3pro.sh
#
# Launch the Yahboom M3Pro Isaac Sim GUI viewer.
#
# Usage:
#   ./scripts/isaaclab/view_m3pro.sh
#   ./scripts/isaaclab/view_m3pro.sh --scene cluttered_static
#   ./scripts/isaaclab/view_m3pro.sh --scene narrow_passage --fleetsafe
#   ./scripts/isaaclab/view_m3pro.sh --steps 1000
#
# Requires:
#   conda activate isaac
#   export OMNI_KIT_ACCEPT_EULA=Y  (set automatically below if not set)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# ── Check conda environment ───────────────────────────────────────────────────
if [[ -z "${CONDA_DEFAULT_ENV}" ]] || [[ "${CONDA_DEFAULT_ENV}" != "isaac" ]]; then
    echo ""
    echo "[view_m3pro.sh] ERROR: Isaac conda environment not active."
    echo "  Run: conda activate isaac"
    echo "  Then re-run: ./scripts/isaaclab/view_m3pro.sh"
    echo ""
    exit 1
fi

# ── Accept Isaac Sim EULA automatically ──────────────────────────────────────
export OMNI_KIT_ACCEPT_EULA=Y

# ── Check URDF exists before launching Isaac ─────────────────────────────────
URDF="${REPO_ROOT}/fleet_safe_vla/robots/yahboom/m3pro/urdf/yahboom_m3pro.urdf"
if [[ ! -f "${URDF}" ]]; then
    echo ""
    echo "[view_m3pro.sh] ERROR: M3Pro URDF not found."
    echo "  Expected: ${URDF}"
    echo ""
    echo "  Run the asset checker first:"
    echo "    python scripts/isaaclab/check_m3pro_isaac_asset.py"
    echo ""
    exit 1
fi

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  FleetSafe VisualNav  |  Yahboom M3Pro Isaac Sim Viewer"
echo "════════════════════════════════════════════════════════════════"
echo "  URDF   : ${URDF}"
echo "  Isaac  : $(python -c 'import isaaclab; print(isaaclab.__version__)' 2>/dev/null || echo 'version unknown')"
echo "  Conda  : ${CONDA_DEFAULT_ENV}"
echo "════════════════════════════════════════════════════════════════"
echo ""

# ── Pre-flight: run asset check ───────────────────────────────────────────────
echo "[view_m3pro.sh] Running asset pre-flight check ..."
python "${REPO_ROOT}/scripts/isaaclab/check_m3pro_isaac_asset.py" --no-isaac || {
    echo "[view_m3pro.sh] WARNING: Some asset checks failed (see above)."
    echo "  Proceeding with viewer — Isaac Sim may report additional errors."
    echo ""
}

# ── Launch Isaac viewer ───────────────────────────────────────────────────────
echo "[view_m3pro.sh] Launching Isaac Sim viewer ..."
echo ""

cd "${REPO_ROOT}"
python scripts/isaaclab/view_m3pro.py "$@"
