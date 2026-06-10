#!/usr/bin/env bash
# scripts/gnm/01_setup_env.sh
# ─────────────────────────────────────────────────────────────────────────────
# Step 1 of 7: Set up the Python environment for GNM training.
#
# What this script does
# ─────────────────────
#   1. Creates a conda environment called "gnm_train" (Python 3.10)
#   2. Installs PyTorch with CUDA 12.1 support
#   3. Installs all dependencies from requirements.txt
#   4. Installs the gnm_vlnverse package in editable mode
#   5. Verifies the installation (import + GPU check)
#
# Why two environments?
# ─────────────────────
#   Isaac Sim 4.5 bundles its OWN Python 3.10 and cannot share packages with
#   a normal conda env.  We keep them separate to avoid version clashes.
#
#     gnm_train  ← this script creates this env (PyTorch training)
#     isaac_sim  ← Isaac Sim's bundled Python (sensor capture / simulation)
#
# Requirements
# ────────────
#   - Conda or Miniconda installed
#   - CUDA 12.1 drivers (for GPU training)
#   - ~6 GB free disk space
#
# Usage
# ─────
#   bash scripts/gnm/01_setup_env.sh
#   bash scripts/gnm/01_setup_env.sh --cpu-only      # no GPU, slower training
#   bash scripts/gnm/01_setup_env.sh --env my_name   # custom env name
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_NAME="gnm_train"
CPU_ONLY=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)      ENV_NAME="$2"; shift 2 ;;
    --cpu-only) CPU_ONLY=true; shift ;;
    *) echo "[WARN] Unknown arg: $1"; shift ;;
  esac
done

# ── Colours ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓ $*${NC}"; }
warn() { echo -e "${YELLOW}  ⚠ $*${NC}"; }
fail() { echo -e "${RED}  ✗ $*${NC}"; }

echo ""
echo "════════════════════════════════════════════════════"
echo " FleetSafe GNM-VLNVerse — Environment Setup"
echo "════════════════════════════════════════════════════"
echo " Repo:     ${REPO_ROOT}"
echo " Env name: ${ENV_NAME}"
echo " CPU only: ${CPU_ONLY}"
echo ""

# ── Check conda ───────────────────────────────────────────────────────────────
echo "[1/5] Checking conda..."
if ! command -v conda >/dev/null 2>&1; then
  fail "conda not found. Install Miniconda from:"
  echo "     https://docs.conda.io/en/latest/miniconda.html"
  exit 1
fi
CONDA_VERSION=$(conda --version)
ok "conda found: ${CONDA_VERSION}"

# ── Create environment ────────────────────────────────────────────────────────
echo ""
echo "[2/5] Creating conda environment '${ENV_NAME}' (Python 3.10)..."
if conda env list | grep -q "^${ENV_NAME} "; then
  warn "Environment '${ENV_NAME}' already exists — skipping creation"
  warn "To recreate: conda env remove -n ${ENV_NAME} && bash $0"
else
  conda create -y -n "${ENV_NAME}" python=3.10 pip
  ok "Environment '${ENV_NAME}' created"
fi

# ── Install PyTorch ───────────────────────────────────────────────────────────
echo ""
echo "[3/5] Installing PyTorch..."
if $CPU_ONLY; then
  warn "Installing CPU-only PyTorch (training will be slow)"
  conda run -n "${ENV_NAME}" pip install \
    torch==2.2.2 torchvision==0.17.2 torchaudio==2.2.2 \
    --index-url https://download.pytorch.org/whl/cpu
else
  echo "  Installing PyTorch with CUDA 12.1 support..."
  conda run -n "${ENV_NAME}" pip install \
    torch==2.2.2 torchvision==0.17.2 torchaudio==2.2.2 \
    --index-url https://download.pytorch.org/whl/cu121
fi

# Check CUDA availability
CUDA_CHECK=$(conda run -n "${ENV_NAME}" python -c "
import torch
if torch.cuda.is_available():
    print(f'CUDA {torch.version.cuda} — {torch.cuda.get_device_name(0)}')
else:
    print('CPU only')
" 2>/dev/null || echo "check failed")
ok "PyTorch: ${CUDA_CHECK}"

# ── Install remaining dependencies ────────────────────────────────────────────
echo ""
echo "[4/5] Installing dependencies from requirements.txt..."
REQ_FILE="${REPO_ROOT}/requirements.txt"
if [[ ! -f "${REQ_FILE}" ]]; then
  fail "requirements.txt not found: ${REQ_FILE}"
  exit 1
fi
# Skip torch/torchaudio/torchvision lines (installed above with correct index URL).
# Strip inline comments (everything after #) before passing to pip.
DEPS=$(grep -v "^torch" "${REQ_FILE}" \
  | grep -v "^#" \
  | grep -v "^$" \
  | sed 's/#.*//' \
  | sed 's/[[:space:]]*$//' \
  | grep -v "^$" \
  | tr '\n' ' ')
# Also drop the pinned numpy==1.26.4 line — PyTorch 2.2 already pulled in numpy 2.x
DEPS=$(echo "${DEPS}" | sed 's/numpy==[^ ]*/numpy/g')
# shellcheck disable=SC2086
conda run -n "${ENV_NAME}" pip install ${DEPS}
ok "All dependencies installed"

# ── Install gnm_vlnverse package ──────────────────────────────────────────────
echo ""
echo "[5/5] Installing gnm_vlnverse package..."
conda run -n "${ENV_NAME}" pip install -e "${REPO_ROOT}"
ok "gnm_vlnverse installed"

# ── Verification ──────────────────────────────────────────────────────────────
echo ""
echo "── Verification ──────────────────────────────────────────────────────────"
conda run -n "${ENV_NAME}" python - <<'PYEOF'
import sys
print(f"  Python: {sys.version.split()[0]}")

import torch
print(f"  torch:  {torch.__version__}")
print(f"  CUDA:   {'available (' + torch.cuda.get_device_name(0) + ')' if torch.cuda.is_available() else 'not available'}")

import torchvision, timm, cv2, numpy, wandb, yaml
print(f"  torchvision: {torchvision.__version__}")
print(f"  timm:        {timm.__version__}")
print(f"  opencv:      {cv2.__version__}")
print(f"  numpy:       {numpy.__version__}")
print(f"  wandb:       {wandb.__version__}")

from gnm_vlnverse.models import GNM
model = GNM(context_size=5, action_dim=2)
n = sum(p.numel() for p in model.parameters()) / 1e6
print(f"  GNM model:   {n:.1f}M parameters — OK")

from gnm_vlnverse.evaluation.metrics import compute_all_metrics
print(f"  metrics:     imported OK")
PYEOF

echo ""
echo "════════════════════════════════════════════════════"
echo -e " ${GREEN}Environment '${ENV_NAME}' is ready!${NC}"
echo "════════════════════════════════════════════════════"
echo ""
echo " Activate with:"
echo "   conda activate ${ENV_NAME}"
echo ""
echo " Next step:"
echo "   bash scripts/gnm/02_generate_data.sh"
echo ""
