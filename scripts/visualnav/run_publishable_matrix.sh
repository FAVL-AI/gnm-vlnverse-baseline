#!/usr/bin/env bash
# scripts/visualnav/run_publishable_matrix.sh
# ─────────────────────────────────────────────────────────────────────────────
# Publishable FleetSafe × VisualNav benchmark matrix.
#
# Runs all 6 model × mode combinations (GNM, ViNT, NoMaD × baseline, FleetSafe)
# across all 4 canonical scenes at the requested seed density, writes per-episode
# logs, and exports an HTML/CSV comparison report.
#
# ⚠ MOCK BACKEND: --backend mock (default) does NOT produce valid publication
#   results. Use --backend mujoco once the MuJoCo nav env is confirmed working.
#
# Usage:
#   bash scripts/visualnav/run_publishable_matrix.sh              # smoke (mock, 1 seed)
#   bash scripts/visualnav/run_publishable_matrix.sh --seeds dev  # 10 seeds, mock
#   bash scripts/visualnav/run_publishable_matrix.sh --seeds paper --backend mujoco
#   bash scripts/visualnav/run_publishable_matrix.sh --models gnm,vint --seeds dev
#   bash scripts/visualnav/run_publishable_matrix.sh --scenes straight_corridor,cluttered_static
#
# Exit codes:
#   0  all model runs completed
#   1  pre-flight check failed
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON="${CONDA_PREFIX:-/usr/bin}/bin/python"
if [[ ! -x "${PYTHON}" ]]; then
  # Fallback to miniforge isaac env (default dev env for this project)
  PYTHON="/home/favl/miniforge3/envs/isaac/bin/python"
fi

VNT_WEIGHTS="${REPO_ROOT}/third_party/visualnav-transformer/model_weights"

# ── Defaults ──────────────────────────────────────────────────────────────────
MODELS="gnm,vint,nomad"
SEEDS="smoke"
SCENES="all"
BACKEND="mock"
FLEETSAFE="both"
MAX_STEPS=500
CONTROL_HZ=4.0
V_MAX=0.3
VY_MAX=0.3
W_MAX=0.7
OUTPUT_DIR="benchmarks/visualnav/results"

# ── Parse args ─────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --models)      MODELS="$2"     ; shift 2 ;;
    --seeds)       SEEDS="$2"      ; shift 2 ;;
    --scenes)      SCENES="$2"     ; shift 2 ;;
    --backend)     BACKEND="$2"    ; shift 2 ;;
    --fleetsafe)   FLEETSAFE="$2"  ; shift 2 ;;
    --max-steps)   MAX_STEPS="$2"  ; shift 2 ;;
    --output-dir)  OUTPUT_DIR="$2" ; shift 2 ;;
    --python)      PYTHON="$2"     ; shift 2 ;;
    *) echo "[WARN] Unknown arg: $1" ; shift ;;
  esac
done

# ── Helpers ────────────────────────────────────────────────────────────────────
log()  { echo "[run_publishable_matrix] $*"; }
ok()   { echo "  ✓  $*"; }
fail() { echo "  ✗  $*" >&2; }
hr()   { echo "────────────────────────────────────────────────────────────────"; }

hr
log "FleetSafe × VisualNav Publishable Benchmark Matrix"
log "REPO_ROOT : ${REPO_ROOT}"
log "PYTHON    : ${PYTHON}"
log "BACKEND   : ${BACKEND}"
log "MODELS    : ${MODELS}"
log "SEEDS     : ${SEEDS}"
log "SCENES    : ${SCENES}"
log "FLEETSAFE : ${FLEETSAFE}"
hr

# ── Pre-flight checks ─────────────────────────────────────────────────────────
log "Pre-flight checks..."

if [[ ! -x "${PYTHON}" ]]; then
  fail "Python not found: ${PYTHON}"
  fail "Set --python /path/to/python or activate a conda env."
  exit 1
fi
ok "Python: ${PYTHON}"

# Check upstream if not mock
if [[ "${BACKEND}" != "mock" ]]; then
  if [[ ! -d "${REPO_ROOT}/third_party/visualnav-transformer" ]]; then
    fail "Upstream not cloned. Run: bash scripts/visualnav/setup_visualnav.sh"
    exit 1
  fi
  ok "Upstream cloned."

  # Check checkpoints for each requested model
  CKPT_OK=true
  IFS=',' read -ra MODEL_LIST <<< "${MODELS}"
  for model in "${MODEL_LIST[@]}"; do
    ckpt="${VNT_WEIGHTS}/${model}/${model}.pth"
    if [[ ! -f "${ckpt}" ]]; then
      fail "Checkpoint missing: ${ckpt}"
      fail "Run: bash scripts/visualnav/setup_visualnav.sh --download-weights"
      CKPT_OK=false
    else
      ckpt_size=$(du -sh "${ckpt}" | cut -f1)
      ok "${model} checkpoint: ${ckpt} (${ckpt_size})"
    fi
  done
  if ! $CKPT_OK; then
    exit 1
  fi
fi

if [[ "${BACKEND}" == "mock" ]]; then
  echo ""
  echo "  ⚠ MOCK BACKEND: results from this run are NOT valid for publication."
  echo "    Use --backend mujoco for publication-quality evaluation."
  echo ""
fi

# ── Activate PYTHONPATH ────────────────────────────────────────────────────────
ACTIVATE="${REPO_ROOT}/scripts/visualnav/activate_visualnav_env.sh"
if [[ -f "${ACTIVATE}" ]]; then
  # shellcheck source=/dev/null
  source "${ACTIVATE}"
else
  export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"
fi

# ── Run benchmark matrix ───────────────────────────────────────────────────────
log "Starting benchmark matrix..."
T_START=$(date +%s)

IFS=',' read -ra MODEL_LIST <<< "${MODELS}"
FAILED_MODELS=()

for model in "${MODEL_LIST[@]}"; do
  log "Running model: ${model}"
  set +e
  "${PYTHON}" "${REPO_ROOT}/scripts/visualnav/run_visualnav_benchmark.py" \
    --model      "${model}" \
    --seeds      "${SEEDS}" \
    --scenes     "${SCENES}" \
    --backend    "${BACKEND}" \
    --fleetsafe  "${FLEETSAFE}" \
    --max-steps  "${MAX_STEPS}" \
    --control-hz "${CONTROL_HZ}" \
    --v-max      "${V_MAX}" \
    --vy-max     "${VY_MAX}" \
    --w-max      "${W_MAX}" \
    --output-dir "${OUTPUT_DIR}"
  RC=$?
  set -e
  if [[ $RC -ne 0 ]]; then
    fail "Model ${model} failed with exit code ${RC}"
    FAILED_MODELS+=("${model}")
  else
    ok "Model ${model} completed."
  fi
done

T_END=$(date +%s)
ELAPSED=$(( T_END - T_START ))

hr
echo ""
echo "  Matrix complete in ${ELAPSED}s."
if [[ ${#FAILED_MODELS[@]} -gt 0 ]]; then
  echo "  Failed models: ${FAILED_MODELS[*]}"
  echo ""
  exit 1
else
  echo "  All models completed successfully."
fi
echo ""
echo "  Results     → ${REPO_ROOT}/${OUTPUT_DIR}/"
echo "  HTML report → ${REPO_ROOT}/benchmarks/visualnav/reports/"
echo ""
hr
exit 0
