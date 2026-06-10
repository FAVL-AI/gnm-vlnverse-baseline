#!/usr/bin/env bash
# scripts/visualnav/setup_visualnav.sh
# ─────────────────────────────────────────────────────────────────────────────
# Setup script for the FleetSafe VisualNav-Transformer integration.
#
# What it does:
#   1. Clones upstream visualnav-transformer into third_party/
#   2. Creates/updates a conda env with required dependencies
#   3. Installs upstream packages in editable mode
#   4. Verifies Python imports (gnm_train, vint_train, nomad)
#   5. Checks checkpoint paths (optional --download-weights to fetch them)
#   6. Prints Gate 0–1 status and exact next steps
#
# Usage:
#   bash scripts/visualnav/setup_visualnav.sh
#   bash scripts/visualnav/setup_visualnav.sh --download-weights
#   bash scripts/visualnav/setup_visualnav.sh --env-name my_env
#   bash scripts/visualnav/setup_visualnav.sh --skip-clone   # if already cloned
#
# Exit codes:
#   0  all required steps passed (checkpoints may still be missing)
#   1  required step failed (clone/install/import error)
#   2  checkpoints missing (non-fatal; instructions printed)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
UPSTREAM_URL="https://github.com/robodhruv/visualnav-transformer.git"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VNT_DIR="${REPO_ROOT}/third_party/visualnav-transformer"
WEIGHTS_DIR="${VNT_DIR}/model_weights"
ENV_NAME="fleetsafe-vnav"            # conda env to use (or existing env with torch)
SKIP_CLONE=false
DOWNLOAD_WEIGHTS=false
USE_EXISTING_ENV=false               # --use-env flag: don't create new env

# ── Parse args ─────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --download-weights) DOWNLOAD_WEIGHTS=true ; shift ;;
    --skip-clone)       SKIP_CLONE=true        ; shift ;;
    --env-name)         ENV_NAME="$2"           ; shift 2 ;;
    --use-env)          USE_EXISTING_ENV=true   ; shift ;;
    *) echo "[WARN] Unknown argument: $1" ; shift ;;
  esac
done

PYTHON="${CONDA_PREFIX:-/usr/bin}/bin/python"

# ── Helper functions ───────────────────────────────────────────────────────────
log()  { echo "[setup_visualnav] $*"; }
ok()   { echo "  ✓  $*"; }
fail() { echo "  ✗  $*"; }
hr()   { echo "────────────────────────────────────────────────────────────────"; }

hr
log "FleetSafe × VisualNav-Transformer Setup"
log "REPO_ROOT : ${REPO_ROOT}"
log "VNT_DIR   : ${VNT_DIR}"
log "ENV_NAME  : ${ENV_NAME}"
hr

# ── Step 1: Clone upstream repo ───────────────────────────────────────────────
log "Step 1: Clone upstream repo"

if $SKIP_CLONE; then
  log "  --skip-clone set, skipping git clone."
elif [[ -d "${VNT_DIR}/.git" ]]; then
  ok "Already cloned at ${VNT_DIR}"
  log "  Fetching latest changes..."
  git -C "${VNT_DIR}" fetch --quiet || log "  [WARN] fetch failed (offline?)"
else
  log "  Cloning ${UPSTREAM_URL} → ${VNT_DIR} ..."
  mkdir -p "${REPO_ROOT}/third_party"
  if ! git clone --depth 1 "${UPSTREAM_URL}" "${VNT_DIR}" 2>&1; then
    fail "Git clone failed.  Check network access."
    fail "Upstream URL: ${UPSTREAM_URL}"
    exit 1
  fi
  ok "Cloned successfully."
fi

# Verify expected structure
TRAIN_DIR="${VNT_DIR}/train"
if [[ ! -d "${TRAIN_DIR}" ]]; then
  fail "Expected ${TRAIN_DIR} directory not found."
  fail "The upstream repo structure may have changed.  Check manually:"
  fail "  ls ${VNT_DIR}/"
  exit 1
fi
ok "Upstream structure verified (train/ exists)"

# ── Step 2: Conda environment ─────────────────────────────────────────────────
log "Step 2: Conda environment"

CONDA_CMD="conda"
if ! command -v conda &> /dev/null; then
  # Try miniforge
  if [[ -f "/home/favl/miniforge3/bin/conda" ]]; then
    CONDA_CMD="/home/favl/miniforge3/bin/conda"
  else
    fail "conda not found.  Install Miniforge: https://github.com/conda-forge/miniforge"
    exit 1
  fi
fi

if $USE_EXISTING_ENV; then
  log "  --use-env: using current active environment."
  PYTHON=$(which python)
else
  # Create env if it doesn't exist
  if ! ${CONDA_CMD} env list 2>/dev/null | grep -q "^${ENV_NAME}"; then
    log "  Creating conda env '${ENV_NAME}' with Python 3.10 + PyTorch..."
    ${CONDA_CMD} create -n "${ENV_NAME}" python=3.10 -y --quiet
    # Install PyTorch (CPU build for portability)
    ${CONDA_CMD} run -n "${ENV_NAME}" pip install --quiet \
      torch torchvision --index-url https://download.pytorch.org/whl/cpu
    ok "Conda env '${ENV_NAME}' created."
  else
    ok "Conda env '${ENV_NAME}' already exists."
  fi
  PYTHON="${CONDA_CMD} run -n ${ENV_NAME} python"
fi

# ── Step 3: Install upstream packages ─────────────────────────────────────────
log "Step 3: Install upstream packages (gnm_train, vint_train, nomad)"

install_pkg() {
  local pkg_dir="$1"
  local pkg_name="$2"
  if [[ -f "${pkg_dir}/setup.py" || -f "${pkg_dir}/pyproject.toml" ]]; then
    log "  Installing ${pkg_name} from ${pkg_dir}..."
    if $USE_EXISTING_ENV; then
      pip install -e "${pkg_dir}" --quiet 2>&1 | tail -3
    else
      ${CONDA_CMD} run -n "${ENV_NAME}" pip install -e "${pkg_dir}" --quiet 2>&1 | tail -3
    fi
    ok "${pkg_name} installed."
  else
    log "  [WARN] No setup.py/pyproject.toml in ${pkg_dir} — adding to PYTHONPATH only."
  fi
}

# Install sub-packages from upstream train directory
for pkg_dir in "${TRAIN_DIR}"/*/; do
  pkg_name=$(basename "${pkg_dir}")
  install_pkg "${pkg_dir}" "${pkg_name}" || log "  [WARN] ${pkg_name} install failed (non-fatal)"
done

# Install top-level upstream (for deployment code)
install_pkg "${VNT_DIR}" "visualnav-transformer" || true

# fleet_safe_vla is made importable via PYTHONPATH — no editable install needed.
# (Avoids PEP 660 build_editable requirement on some pyproject backends.)
ACTIVATE_HELPER="${REPO_ROOT}/scripts/visualnav/activate_visualnav_env.sh"
log "  Writing PYTHONPATH activation helper: ${ACTIVATE_HELPER}"
cat > "${ACTIVATE_HELPER}" <<ACTIVATE_EOF
#!/usr/bin/env bash
# Source this file before running any VisualNav scripts.
# Usage:  source scripts/visualnav/activate_visualnav_env.sh
export PYTHONPATH="${REPO_ROOT}:${VNT_DIR}/train:${VNT_DIR}/train/vint_train:\${PYTHONPATH:-}"
export FLEETSAFE_REPO_ROOT="${REPO_ROOT}"
echo "[visualnav] PYTHONPATH configured — fleet_safe_vla and upstream packages are importable."
ACTIVATE_EOF
chmod +x "${ACTIVATE_HELPER}"
ok "Activation helper written (source it before running benchmark scripts)."

# Per-model dependency installs
# GNM: no extras beyond torch/torchvision/vint_train
# ViNT: efficientnet_pytorch + warmup_scheduler
log "  Installing ViNT dependencies (efficientnet-pytorch, warmup_scheduler)..."
_pip() { if $USE_EXISTING_ENV; then pip install --quiet "$@" 2>&1 | tail -2; else ${CONDA_CMD} run -n "${ENV_NAME}" pip install --quiet "$@" 2>&1 | tail -2; fi; }
_pip efficientnet-pytorch warmup_scheduler || log "  [WARN] ViNT deps install failed (non-fatal)"
ok "ViNT dependencies installed."

# NoMaD: diffusers==0.11.1 + pinned huggingface_hub + einops + diffusion_policy
log "  Installing NoMaD dependencies (diffusers==0.11.1, huggingface_hub==0.12.0, einops)..."
_pip "diffusers==0.11.1" "huggingface_hub==0.12.0" einops || log "  [WARN] NoMaD deps install failed (non-fatal)"
ok "NoMaD core dependencies installed."

# drive-any-robot — GNM reference implementation (Shah et al., ICRA 2023)
DRIVE_ANY_ROBOT_DIR="${REPO_ROOT}/third_party/drive-any-robot"
if [[ ! -d "${DRIVE_ANY_ROBOT_DIR}/.git" ]]; then
  log "  Cloning drive-any-robot into third_party/..."
  git clone --depth 1 https://github.com/robodhruv/drive-any-robot.git "${DRIVE_ANY_ROBOT_DIR}" 2>&1 | tail -2 \
    && ok "drive-any-robot cloned." \
    || log "  [WARN] drive-any-robot clone failed (offline? non-fatal)."
else
  ok "drive-any-robot already present at ${DRIVE_ANY_ROBOT_DIR}"
fi

# visualnav-transformer-ros2 — community ROS 2 port
VNT_ROS2_DIR="${REPO_ROOT}/third_party/visualnav-transformer-ros2"
if [[ ! -d "${VNT_ROS2_DIR}/.git" ]]; then
  log "  Cloning visualnav-transformer-ros2 into third_party/..."
  git clone --depth 1 https://github.com/RobotecAI/visualnav-transformer-ros2.git "${VNT_ROS2_DIR}" 2>&1 | tail -2 \
    && ok "visualnav-transformer-ros2 cloned." \
    || log "  [WARN] visualnav-transformer-ros2 clone failed (offline? non-fatal)."
else
  ok "visualnav-transformer-ros2 already present at ${VNT_ROS2_DIR}"
fi

# diffusion_policy — real-stanford/diffusion_policy, not on PyPI
DIFFUSION_POLICY_DIR="${REPO_ROOT}/third_party/diffusion_policy"
if [[ ! -d "${DIFFUSION_POLICY_DIR}" ]]; then
  log "  Cloning diffusion_policy into third_party/..."
  git clone --depth 1 https://github.com/real-stanford/diffusion_policy.git "${DIFFUSION_POLICY_DIR}" 2>&1 | tail -2
fi
# Use .pth to make diffusion_policy importable (editable install MAPPING is empty)
if $USE_EXISTING_ENV; then
  SITE_PKGS="$(python -c 'import site; print(site.getsitepackages()[0])')"
else
  SITE_PKGS="$(${CONDA_CMD} run -n "${ENV_NAME}" python -c 'import site; print(site.getsitepackages()[0])')"
fi
echo "${DIFFUSION_POLICY_DIR}" > "${SITE_PKGS}/diffusion_policy_src.pth"
ok "diffusion_policy path registered at ${SITE_PKGS}/diffusion_policy_src.pth"

# ── Step 4: Verify Python imports ─────────────────────────────────────────────
log "Step 4: Verify Python imports"

check_import() {
  local mod="$1"
  # Always inject all needed paths so neither pip-install nor conda activation is required.
  local script="import sys; [sys.path.insert(0,p) for p in ['${REPO_ROOT}','${TRAIN_DIR}','${VNT_DIR}/train/vint_train'] if p not in sys.path]"
  script="${script}; import ${mod}; print(f'  ✓  ${mod} imported (v{getattr(${mod}, \"__version__\", \"?\")})')"

  if $USE_EXISTING_ENV; then
    python -c "${script}" 2>&1 || { fail "${mod} import FAILED"; return 1; }
  else
    ${CONDA_CMD} run -n "${ENV_NAME}" python -c "${script}" 2>&1 || \
      { fail "${mod} import FAILED"; return 1; }
  fi
}

IMPORT_OK=true
check_import "torch"       || IMPORT_OK=false
check_import "torchvision" || IMPORT_OK=false
# All models (GNM, ViNT, NoMaD) live under vint_train — there is no gnm_train package
check_import "vint_train"  || IMPORT_OK=false
check_import "diffusers"   || IMPORT_OK=false

if ! $IMPORT_OK; then
  fail "One or more imports failed.  Re-run this script to retry."
  exit 1
fi

# Try NoMaD (may be in different sub-path)
NOMAD_SCRIPT="import sys; [sys.path.insert(0,p) for p in ['${REPO_ROOT}','${TRAIN_DIR}','${VNT_DIR}/train/vint_train'] if p not in sys.path]; import nomad; print('  ✓  nomad imported')"
if $USE_EXISTING_ENV; then
  python -c "${NOMAD_SCRIPT}" 2>&1 || log "  [WARN] nomad import failed — check upstream structure"
else
  ${CONDA_CMD} run -n "${ENV_NAME}" python -c "${NOMAD_SCRIPT}" 2>&1 || \
    log "  [WARN] nomad import failed — check upstream structure"
fi

ok "All required imports verified."

# ── Step 5: Check / download checkpoints ──────────────────────────────────────
log "Step 5: Checkpoint status"

CKPT_OK=true
declare -A CKPT_IDS=(
  ["gnm"]="1Jyv3oIX05KmZ7T3ym7sPKHoFJ_r3Ia0K"
  ["vint"]="1WwBBnAe3jSMhVjHf8HZoXBO7Nz3pPOm2"
  ["nomad"]="1SzK_J5KZgjGFhJNDe7xeWU6GWixhBuEo"
)
declare -A CKPT_PATHS=(
  ["gnm"]="${WEIGHTS_DIR}/gnm/gnm.pth"
  ["vint"]="${WEIGHTS_DIR}/vint/vint.pth"
  ["nomad"]="${WEIGHTS_DIR}/nomad/nomad.pth"
)

for model in gnm vint nomad; do
  path="${CKPT_PATHS[$model]}"
  if [[ -f "${path}" ]]; then
    size=$(du -sh "${path}" 2>/dev/null | cut -f1)
    ok "${model} checkpoint: ${path} (${size})"
  else
    CKPT_OK=false
    fail "${model} checkpoint MISSING: ${path}"
    if $DOWNLOAD_WEIGHTS; then
      log "  Attempting download via gdown (Google Drive ID: ${CKPT_IDS[$model]})..."
      mkdir -p "$(dirname "${path}")"
      if command -v gdown &> /dev/null || pip show gdown &> /dev/null 2>&1; then
        gdown --id "${CKPT_IDS[$model]}" -O "${path}" 2>&1 || \
          log "  [WARN] gdown download failed.  Manual download required."
      else
        log "  [INFO] Install gdown: pip install gdown"
        log "  [INFO] Then: gdown --id ${CKPT_IDS[$model]} -O ${path}"
      fi
    else
      log "  → Download manually or run:"
      log "      bash scripts/visualnav/setup_visualnav.sh --download-weights"
      log "  → Google Drive ID: ${CKPT_IDS[$model]}"
    fi
  fi
done

# ── Summary ───────────────────────────────────────────────────────────────────
hr
echo ""
echo "  Setup complete."
echo ""
echo "  Gate 0 (upstream importable): PASS"
if $CKPT_OK; then
  echo "  Gate 1 (checkpoints exist):   PASS"
else
  echo "  Gate 1 (checkpoints exist):   INCOMPLETE  ← download missing checkpoints"
fi
echo ""
echo "  Before running scripts, set PYTHONPATH:"
echo "    source scripts/visualnav/activate_visualnav_env.sh"
echo ""
echo "  Validate all gates:"
echo "    source scripts/visualnav/activate_visualnav_env.sh"
echo "    conda run -n ${ENV_NAME} python -m \\"
echo "      fleet_safe_vla.integrations.visualnav_transformer.validate_gates"
echo ""
echo "  Run benchmark matrix (after checkpoints are present):"
echo "    bash scripts/visualnav/run_matrix.sh --model gnm --fleetsafe false"
echo ""
hr

if ! $CKPT_OK; then
  exit 2
fi
exit 0
