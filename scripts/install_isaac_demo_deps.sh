#!/usr/bin/env bash
# scripts/install_isaac_demo_deps.sh
# ─────────────────────────────────────────────────────────────────────────────
# Install pinned Python dependencies required by IAmGoodNavigator/Isaac Sim
# into the 'isaac' conda environment.
#
# Isaac Sim ships with its own Python interpreter.  Packages installed here
# must be compatible with numpy==1.26.0 (the Isaac Sim requirement).
#
# Usage:
#   bash scripts/install_isaac_demo_deps.sh
#   bash scripts/install_isaac_demo_deps.sh --env myenv   # override env name
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

TARGET_ENV="isaac"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) TARGET_ENV="$2"; shift 2 ;;
    *) echo "[WARN] Unknown arg: $1"; shift ;;
  esac
done

CONDA_BASE="$(conda info --base 2>/dev/null || echo '/home/favl/miniforge3')"
ENV_PYTHON="${CONDA_BASE}/envs/${TARGET_ENV}/bin/python"

echo "========================================"
echo "  FleetSafe — Install Isaac Demo Deps"
echo "  env: ${TARGET_ENV}"
echo "  python: ${ENV_PYTHON}"
echo "========================================"
echo ""

if [[ ! -f "${ENV_PYTHON}" ]]; then
  echo "[FAIL] conda env '${TARGET_ENV}' not found at ${ENV_PYTHON}"
  echo "  Create it: conda create -n ${TARGET_ENV} python=3.10 -y"
  echo "  Or check:  conda env list"
  exit 1
fi

echo "  Current numpy in ${TARGET_ENV}:"
"${ENV_PYTHON}" -c "import numpy; print('   ', numpy.__version__)" 2>/dev/null || echo "    not installed"
echo ""

echo "--- Installing pinned packages ---"
# Pillow==11.3.0 and pyyaml==6.0.2 are hard requirements from isaacsim-kernel/isaacsim-core.
# Do NOT use --upgrade for unversioned packages inside the isaac env.
"${ENV_PYTHON}" -m pip install \
  "numpy==1.26.0" \
  "pandas==2.2.3" \
  "opencv-python==4.10.0.84" \
  "Pillow==11.3.0" \
  "pyyaml==6.0.2" \
  "tqdm" \
  2>&1

echo ""
echo "--- Verifying installation ---"
ERRORS=0

check_pkg() {
  local pkg="$1" expected="$2"
  local actual
  actual="$("${ENV_PYTHON}" -c "import ${pkg}; print(getattr(${pkg}, '__version__', 'ok'))" 2>/dev/null || echo "MISSING")"
  if [[ "${actual}" == "MISSING" ]]; then
    echo "[FAIL]  ${pkg}: MISSING"
    ERRORS=$((ERRORS+1))
  elif [[ -n "${expected}" ]] && [[ "${actual}" != "${expected}" ]]; then
    echo "[WARN]  ${pkg}: ${actual} (wanted ${expected})"
  else
    echo "[OK]    ${pkg}: ${actual}"
  fi
}

check_pkg numpy  "1.26.0"
check_pkg pandas "2.2.3"
check_pkg cv2    ""
check_pkg PIL    ""
check_pkg yaml   ""
check_pkg tqdm   ""

echo ""
if [[ "${ERRORS}" -gt 0 ]]; then
  echo "[FAIL] ${ERRORS} package(s) failed to install."
  exit 1
else
  echo "[OK]  All dependencies installed in env '${TARGET_ENV}'."
  echo ""
  echo "  Activate before running demo:"
  echo "    conda activate ${TARGET_ENV}"
  echo "    bash scripts/run_iamgoodnavigator_episode.sh fine 0"
fi
