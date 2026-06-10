#!/usr/bin/env bash
# scripts/visualnav/run_fleetsafe_isaac.sh
# ─────────────────────────────────────────────────────────────────────────────
# Run one model (GNM, ViNT, or NoMaD) WRAPPED WITH FleetSafe against the
# same scenes and seeds as the baseline, enabling head-to-head comparison.
#
# Critically: identical seeds ensure the same episode randomness, so
# baseline vs FleetSafe differences are caused only by safety interventions.
#
# Output: benchmarks/visualnav/results/<model>_fleetsafe_<timestamp>.json
#
# Usage:
#   bash scripts/visualnav/run_fleetsafe_isaac.sh --model gnm
#   bash scripts/visualnav/run_fleetsafe_isaac.sh --model vint --cbf-d-safe 0.30
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON="/home/favl/miniforge3/envs/isaac/bin/python"

MODEL=""
SEEDS=""
SCENES=""
SMOKE_TEST=false
MAX_STEPS=500
CBF_D_SAFE="0.30"   # safety radius in metres
CBF_ESTOP="0.15"    # emergency-stop distance
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --model)       MODEL="$2"      ; shift 2 ;;
    --seeds)       SEEDS="$2"      ; shift 2 ;;
    --scenes)      SCENES="$2"     ; shift 2 ;;
    --smoke-test)  SMOKE_TEST=true ; shift   ;;
    --max-steps)   MAX_STEPS="$2"  ; shift 2 ;;
    --cbf-d-safe)  CBF_D_SAFE="$2" ; shift 2 ;;
    --cbf-estop)   CBF_ESTOP="$2"  ; shift 2 ;;
    --python)      PYTHON="$2"     ; shift 2 ;;
    *)             EXTRA_ARGS+=("$1") ; shift ;;
  esac
done

if [[ -z "$MODEL" ]]; then
  echo "[ERROR] --model is required.  Choices: gnm | vint | nomad"
  echo "Usage: bash $0 --model gnm"
  exit 1
fi

echo "════════════════════════════════════════════════════════════════"
echo "  FleetSafe VisualNav + Safety Benchmark"
echo "  Model         : ${MODEL}"
echo "  FleetSafe     : ENABLED (CBF-QP wrapper)"
echo "  CBF d_safe    : ${CBF_D_SAFE} m"
echo "  CBF estop     : ${CBF_ESTOP} m"
echo "  Seeds         : ${SEEDS:-default from config}"
echo "  Scenes        : ${SCENES:-default from config}"
echo "════════════════════════════════════════════════════════════════"
echo ""

VNT_DIR="${REPO_ROOT}/third_party/visualnav-transformer"
if [[ ! -d "${VNT_DIR}" ]]; then
  echo "[ERROR] Upstream repo not cloned."
  echo "  Run: bash scripts/visualnav/setup_visualnav.sh"
  exit 1
fi

CKPT_MAP_gnm="${VNT_DIR}/model_weights/gnm/gnm.pth"
CKPT_MAP_vint="${VNT_DIR}/model_weights/vint/vint.pth"
CKPT_MAP_nomad="${VNT_DIR}/model_weights/nomad/nomad.pth"
CKPT_PATH_VAR="CKPT_MAP_${MODEL}"
CKPT_PATH="${!CKPT_PATH_VAR}"

if [[ ! -f "${CKPT_PATH}" ]]; then
  echo "[ERROR] Checkpoint not found: ${CKPT_PATH}"
  echo "  Download: bash scripts/visualnav/setup_visualnav.sh --download-weights"
  exit 1
fi

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUT_DIR="${REPO_ROOT}/benchmarks/visualnav/results"
OUT_FILE="${OUT_DIR}/${MODEL}_fleetsafe_${TIMESTAMP}.json"
mkdir -p "${OUT_DIR}"

PYTHON_ARGS=(
  "${REPO_ROOT}/scripts/visualnav/_run_benchmark.py"
  "--model"       "${MODEL}"
  "--checkpoint"  "${CKPT_PATH}"
  "--config"      "${REPO_ROOT}/configs/visualnav/isaac_benchmark.yaml"
  "--output"      "${OUT_FILE}"
  "--fleetsafe"   "true"
  "--cbf-d-safe"  "${CBF_D_SAFE}"
  "--cbf-estop"   "${CBF_ESTOP}"
  "--max-steps"   "${MAX_STEPS}"
)
[[ -n "${SEEDS}"  ]] && PYTHON_ARGS+=(  "--seeds"  "${SEEDS}" )
[[ -n "${SCENES}" ]] && PYTHON_ARGS+=( "--scenes" "${SCENES}" )
$SMOKE_TEST && PYTHON_ARGS+=( "--smoke-test" )
PYTHON_ARGS+=( "${EXTRA_ARGS[@]}" )

echo "[INFO] Running FleetSafe-wrapped benchmark..."
echo "  Output: ${OUT_FILE}"
echo ""

PYTHONPATH="${REPO_ROOT}:${VNT_DIR}/train:${PYTHONPATH:-}" \
  "${PYTHON}" "${PYTHON_ARGS[@]}"

echo ""
echo "[INFO] Done. Results at: ${OUT_FILE}"
echo ""
echo "  Compare with baseline:"
echo "    ${PYTHON} scripts/visualnav/export_report.py \\"
echo "      --input benchmarks/visualnav/results/ \\"
echo "      --output-dir benchmarks/visualnav/reports/"
