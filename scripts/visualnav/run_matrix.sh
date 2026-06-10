#!/usr/bin/env bash
# scripts/visualnav/run_matrix.sh
# ─────────────────────────────────────────────────────────────────────────────
# Runs the full benchmark matrix:
#
#   Model × {baseline, fleetsafe} × Scenes × Seeds
#
# Models: GNM, ViNT, NoMaD
# Each model runs TWICE: once as baseline, once wrapped with FleetSafe.
# All runs use the SAME seeds so differences are caused only by the safety layer.
#
# Results are exported to benchmarks/visualnav/results/ as JSON files.
# A consolidated HTML/CSV report is generated at the end.
#
# Usage:
#   bash scripts/visualnav/run_matrix.sh
#   bash scripts/visualnav/run_matrix.sh --models gnm,vint
#   bash scripts/visualnav/run_matrix.sh --smoke-test    # 1 seed, 1 scene
#   bash scripts/visualnav/run_matrix.sh --skip-baseline
#   bash scripts/visualnav/run_matrix.sh --skip-fleetsafe
#
# Exit codes:
#   0  all runs completed (individual failures summarised at end)
#   1  pre-flight checks failed (missing checkpoints / upstream repo)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON="/home/favl/miniforge3/envs/isaac/bin/python"
VNT_DIR="${REPO_ROOT}/third_party/visualnav-transformer"

MODELS=("gnm" "vint" "nomad")
SMOKE_TEST=false
SKIP_BASELINE=false
SKIP_FLEETSAFE=false
SEEDS=""
SCENES=""
MAX_STEPS=500

while [[ $# -gt 0 ]]; do
  case "$1" in
    --models)         IFS=',' read -ra MODELS <<< "$2" ; shift 2 ;;
    --smoke-test)     SMOKE_TEST=true  ; shift ;;
    --skip-baseline)  SKIP_BASELINE=true  ; shift ;;
    --skip-fleetsafe) SKIP_FLEETSAFE=true ; shift ;;
    --seeds)          SEEDS="$2"  ; shift 2 ;;
    --scenes)         SCENES="$2" ; shift 2 ;;
    --max-steps)      MAX_STEPS="$2" ; shift 2 ;;
    --python)         PYTHON="$2" ; shift 2 ;;
    *) echo "[WARN] Unknown arg: $1" ; shift ;;
  esac
done

if $SMOKE_TEST; then
  SEEDS="0"
  SCENES="open_corridor"
  MAX_STEPS=50
  echo "[INFO] Smoke test mode: 1 seed, 1 scene, 50 steps."
fi

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUT_DIR="${REPO_ROOT}/benchmarks/visualnav/results"
REPORT_DIR="${REPO_ROOT}/benchmarks/visualnav/reports"
mkdir -p "${OUT_DIR}" "${REPORT_DIR}"
MATRIX_LOG="${OUT_DIR}/matrix_${TIMESTAMP}.log"

echo "════════════════════════════════════════════════════════════════"
echo "  FleetSafe VisualNav Benchmark Matrix"
echo "  Models    : ${MODELS[*]}"
echo "  Smoke test: ${SMOKE_TEST}"
echo "  Seeds     : ${SEEDS:-from config}"
echo "  Max steps : ${MAX_STEPS}"
echo "  Timestamp : ${TIMESTAMP}"
echo "════════════════════════════════════════════════════════════════"
echo ""

# ── Pre-flight checks ─────────────────────────────────────────────────────────
echo "[PRE-FLIGHT] Checking requirements..."

PREFLIGHT_OK=true

if [[ ! -d "${VNT_DIR}" ]]; then
  echo "  ✗  Upstream repo missing: ${VNT_DIR}"
  echo "     Run: bash scripts/visualnav/setup_visualnav.sh"
  PREFLIGHT_OK=false
fi

declare -A CKPT_PATHS=(
  ["gnm"]="${VNT_DIR}/model_weights/gnm/gnm.pth"
  ["vint"]="${VNT_DIR}/model_weights/vint/vint.pth"
  ["nomad"]="${VNT_DIR}/model_weights/nomad/nomad.pth"
)

MODELS_WITH_CKPTS=()
MODELS_MISSING_CKPTS=()
for model in "${MODELS[@]}"; do
  ckpt="${CKPT_PATHS[$model]}"
  if [[ -f "${ckpt}" ]]; then
    echo "  ✓  ${model} checkpoint: $(du -sh "${ckpt}" | cut -f1)"
    MODELS_WITH_CKPTS+=("${model}")
  else
    echo "  ✗  ${model} checkpoint MISSING: ${ckpt}"
    MODELS_MISSING_CKPTS+=("${model}")
  fi
done

if [[ ${#MODELS_WITH_CKPTS[@]} -eq 0 ]]; then
  echo ""
  echo "[ERROR] No checkpoints available.  Download them first:"
  echo "  bash scripts/visualnav/setup_visualnav.sh --download-weights"
  PREFLIGHT_OK=false
fi

if ! $PREFLIGHT_OK; then
  exit 1
fi

MODELS=("${MODELS_WITH_CKPTS[@]}")
echo ""
echo "[INFO] Running with models: ${MODELS[*]}"
if [[ ${#MODELS_MISSING_CKPTS[@]} -gt 0 ]]; then
  echo "[WARN] Skipping (no checkpoint): ${MODELS_MISSING_CKPTS[*]}"
fi
echo ""

# ── Matrix execution ──────────────────────────────────────────────────────────
RESULTS=()
FAILURES=()

run_one() {
  local model="$1"
  local mode="$2"    # "baseline" or "fleetsafe"
  local script="${REPO_ROOT}/scripts/visualnav/run_${mode}_isaac.sh"
  local label="${model}_${mode}"

  echo "────────────────────────────────────────────────────────────────"
  echo "  Running: ${label}"
  echo "────────────────────────────────────────────────────────────────"

  local args=(
    "--model" "${model}"
    "--max-steps" "${MAX_STEPS}"
  )
  [[ -n "${SEEDS}"  ]] && args+=( "--seeds"  "${SEEDS}"  )
  [[ -n "${SCENES}" ]] && args+=( "--scenes" "${SCENES}" )
  $SMOKE_TEST && args+=( "--smoke-test" )

  if bash "${script}" "${args[@]}" 2>&1 | tee -a "${MATRIX_LOG}"; then
    RESULTS+=("  ✓  ${label}")
    echo ""
  else
    FAILURES+=("  ✗  ${label}")
    echo ""
    echo "[WARN] ${label} FAILED — continuing matrix."
    echo ""
  fi
}

for model in "${MODELS[@]}"; do
  $SKIP_BASELINE  || run_one "${model}" "baseline"
  $SKIP_FLEETSAFE || run_one "${model}" "fleetsafe"
done

# ── Consolidated report ───────────────────────────────────────────────────────
echo "════════════════════════════════════════════════════════════════"
echo "  Matrix complete.  Exporting consolidated report..."
echo "════════════════════════════════════════════════════════════════"
echo ""

PYTHONPATH="${REPO_ROOT}:${VNT_DIR}/train:${PYTHONPATH:-}" \
  "${PYTHON}" "${REPO_ROOT}/scripts/visualnav/export_report.py" \
  --input  "${OUT_DIR}" \
  --output-dir "${REPORT_DIR}" \
  --title "FleetSafe VisualNav Benchmark Matrix ${TIMESTAMP}" \
  2>&1 || echo "[WARN] Report export failed — check export_report.py"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  Run matrix summary"
echo "════════════════════════════════════════════════════════════════"
for r in "${RESULTS[@]:-}"; do echo "${r}"; done
for f in "${FAILURES[@]:-}"; do echo "${f}"; done
echo ""
echo "  Results JSON: ${OUT_DIR}/"
echo "  HTML report : ${REPORT_DIR}/"
echo "  Log         : ${MATRIX_LOG}"
echo ""

if [[ ${#FAILURES[@]} -gt 0 ]]; then
  echo "[WARN] ${#FAILURES[@]} run(s) failed.  See log: ${MATRIX_LOG}"
  exit 1
fi
exit 0
