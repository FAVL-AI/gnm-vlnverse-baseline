#!/usr/bin/env bash
# scripts/visualnav/run_baseline_isaac.sh
# ─────────────────────────────────────────────────────────────────────────────
# Run one model (GNM, ViNT, or NoMaD) as a BASELINE (no FleetSafe) against
# the benchmark matrix defined in configs/visualnav/isaac_benchmark.yaml.
#
# Output: benchmarks/visualnav/results/<model>_baseline_<timestamp>.json
#
# Usage:
#   bash scripts/visualnav/run_baseline_isaac.sh --model gnm
#   bash scripts/visualnav/run_baseline_isaac.sh --model vint --seeds 0,1
#   bash scripts/visualnav/run_baseline_isaac.sh --model nomad --scenes open_corridor
#   bash scripts/visualnav/run_baseline_isaac.sh --model gnm --smoke-test
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON="/home/favl/miniforge3/envs/isaac/bin/python"   # default; override with --python

MODEL=""
SEEDS=""
SCENES=""
SMOKE_TEST=false
MAX_STEPS=500
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --model)      MODEL="$2" ; shift 2 ;;
    --seeds)      SEEDS="$2" ; shift 2 ;;
    --scenes)     SCENES="$2" ; shift 2 ;;
    --smoke-test) SMOKE_TEST=true ; shift ;;
    --max-steps)  MAX_STEPS="$2" ; shift 2 ;;
    --python)     PYTHON="$2" ; shift 2 ;;
    *)            EXTRA_ARGS+=("$1") ; shift ;;
  esac
done

if [[ -z "$MODEL" ]]; then
  echo "[ERROR] --model is required.  Choices: gnm | vint | nomad"
  echo "Usage: bash $0 --model gnm"
  exit 1
fi

echo "════════════════════════════════════════════════════════════════"
echo "  FleetSafe VisualNav Baseline Benchmark"
echo "  Model    : ${MODEL}"
echo "  Seeds    : ${SEEDS:-default from config}"
echo "  Scenes   : ${SCENES:-default from config}"
echo "  Backend  : MuJoCo (M3Pro MJCF)"
echo "════════════════════════════════════════════════════════════════"
echo ""

# ── Gate 0: upstream repo ─────────────────────────────────────────────────────
VNT_DIR="${REPO_ROOT}/third_party/visualnav-transformer"
if [[ ! -d "${VNT_DIR}" ]]; then
  echo "[ERROR] Upstream repo not cloned."
  echo "  Run: bash scripts/visualnav/setup_visualnav.sh"
  exit 1
fi

# ── Gate 1: checkpoint ────────────────────────────────────────────────────────
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

# ── Build python args ─────────────────────────────────────────────────────────
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUT_DIR="${REPO_ROOT}/benchmarks/visualnav/results"
OUT_FILE="${OUT_DIR}/${MODEL}_baseline_${TIMESTAMP}.json"
mkdir -p "${OUT_DIR}"

PYTHON_ARGS=(
  "${REPO_ROOT}/scripts/visualnav/_run_benchmark.py"
  "--model"       "${MODEL}"
  "--checkpoint"  "${CKPT_PATH}"
  "--config"      "${REPO_ROOT}/configs/visualnav/isaac_benchmark.yaml"
  "--output"      "${OUT_FILE}"
  "--fleetsafe"   "false"
  "--max-steps"   "${MAX_STEPS}"
)
[[ -n "${SEEDS}"  ]] && PYTHON_ARGS+=(  "--seeds"  "${SEEDS}" )
[[ -n "${SCENES}" ]] && PYTHON_ARGS+=( "--scenes" "${SCENES}" )
$SMOKE_TEST && PYTHON_ARGS+=( "--smoke-test" )
PYTHON_ARGS+=( "${EXTRA_ARGS[@]}" )

# ── Run ───────────────────────────────────────────────────────────────────────
echo "[INFO] Running benchmark..."
echo "  PYTHONPATH=${REPO_ROOT}:${VNT_DIR}/train"
echo "  Output: ${OUT_FILE}"
echo ""

PYTHONPATH="${REPO_ROOT}:${VNT_DIR}/train:${PYTHONPATH:-}" \
  "${PYTHON}" "${PYTHON_ARGS[@]}"

echo ""
echo "[INFO] Done. Results at: ${OUT_FILE}"
echo ""
echo "  Export report:"
echo "    ${PYTHON} scripts/visualnav/export_report.py \\"
echo "      --input ${OUT_FILE} \\"
echo "      --output-dir benchmarks/visualnav/reports/"
