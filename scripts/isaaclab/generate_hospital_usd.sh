#!/usr/bin/env bash
# scripts/isaaclab/generate_hospital_usd.sh
#
# Generate hospital_world.usd from the procedural scene.
# Run once; the file is then loaded by run_hospital.sh automatically.
#
# Usage:
#   ./scripts/isaaclab/generate_hospital_usd.sh
#   ./scripts/isaaclab/generate_hospital_usd.sh --output /path/to/custom.usd

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# ── Check conda environment ───────────────────────────────────────────────────
if [[ -z "${CONDA_DEFAULT_ENV}" ]] || [[ "${CONDA_DEFAULT_ENV}" != "isaac" ]]; then
    echo ""
    echo "[generate_hospital_usd.sh] ERROR: Isaac conda environment not active."
    echo "  Run: conda activate isaac"
    echo "  Then re-run: ./scripts/isaaclab/generate_hospital_usd.sh"
    echo ""
    exit 1
fi

# ── Accept Isaac Sim EULA automatically ──────────────────────────────────────
export OMNI_KIT_ACCEPT_EULA=Y

# ── Suppress unnecessary Nucleus chatter ─────────────────────────────────────
export OMNI_SERVER_SEARCH_TIMEOUT=1
export OMNI_CACHE_PATH="${REPO_ROOT}/.omni_cache"

# ── Python path ───────────────────────────────────────────────────────────────
export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"

PYTHON="${CONDA_PREFIX}/bin/python"

# ── Banner ────────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  FleetSafe VisualNav  |  USD Asset Generator  |  Isaac Sim"
echo "════════════════════════════════════════════════════════════════"
echo "  Repo   : ${REPO_ROOT}"
echo "  Python : ${PYTHON}"
echo "  Conda  : ${CONDA_DEFAULT_ENV}"
echo "  Output : fleet_safe_vla/envs/isaaclab/hospital/assets/hospital_world.usd"
echo "════════════════════════════════════════════════════════════════"
echo ""

cd "${REPO_ROOT}"
exec "${PYTHON}" "${SCRIPT_DIR}/generate_hospital_usd.py" "$@"
