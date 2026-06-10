#!/usr/bin/env bash
# scripts/gnm/train_gnm.sh
# ─────────────────────────────────────────────────────────────────────────────
# Fine-tune or retrain GNM on FleetSafe-collected data.
#
# Step order:
#   1. Convert collected data to GNM/VisualNav dataset format (if not done)
#   2. Split into train / val / test
#   3. Run fine-tuning using upstream gnm_train or vint_train scripts
#   4. Save checkpoint to third_party/visualnav-transformer/model_weights/gnm_fleetsafe.pth
#
# Usage:
#   bash scripts/gnm/train_gnm.sh --data data/gnm_isaac_hospital_corridor
#   bash scripts/gnm/train_gnm.sh --data data/gnm_fleetsafe --epochs 30
#   bash scripts/gnm/train_gnm.sh --dry-run   # print plan, do not train
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DATA_DIR=""
EPOCHS=20
DRY_RUN=false
CHECKPOINT_OUT="${REPO_ROOT}/third_party/visualnav-transformer/model_weights/gnm_fleetsafe.pth"
DATASET_DIR="${REPO_ROOT}/data/gnm_fleetsafe"
VNT_DIR="${REPO_ROOT}/third_party/visualnav-transformer"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --data)       DATA_DIR="$2"; shift 2 ;;
    --epochs)     EPOCHS="$2";   shift 2 ;;
    --output)     CHECKPOINT_OUT="$2"; shift 2 ;;
    --dry-run)    DRY_RUN=true;  shift ;;
    *) echo "[WARN] Unknown arg: $1"; shift ;;
  esac
done

echo "=== FleetSafe GNM Fine-Tuning ==="
echo "  Data:       ${DATA_DIR:-not specified — using ${DATASET_DIR}}"
echo "  Epochs:     ${EPOCHS}"
echo "  Checkpoint: ${CHECKPOINT_OUT}"
echo "  Dry run:    ${DRY_RUN}"
echo ""

source "${REPO_ROOT}/scripts/visualnav/activate_visualnav_env.sh" 2>/dev/null || \
  export PYTHONPATH="${REPO_ROOT}:${VNT_DIR}/train:${VNT_DIR}/train/vint_train:${PYTHONPATH:-}"

# ── Step 1: Convert data if needed ────────────────────────────────────────────
if [[ -n "${DATA_DIR}" && -d "${DATA_DIR}" ]]; then
  echo "[1/4] Converting ${DATA_DIR} to GNM format..."
  if ! $DRY_RUN; then
    python3 "${REPO_ROOT}/scripts/visualnav/convert_to_vnt_format.py" \
      --input "${DATA_DIR}" \
      --output "${DATASET_DIR}" \
      2>&1 | tail -10 || echo "  [WARN] Conversion failed — check manually"
  fi
fi

# ── Step 2: Verify dataset structure ─────────────────────────────────────────
echo "[2/4] Dataset structure:"
if [[ -d "${DATASET_DIR}" ]]; then
  echo "  train/: $(ls ${DATASET_DIR}/train 2>/dev/null | wc -l) items"
  echo "  val/:   $(ls ${DATASET_DIR}/val   2>/dev/null | wc -l) items"
  echo "  test/:  $(ls ${DATASET_DIR}/test  2>/dev/null | wc -l) items"
else
  echo "  ⚠️  Dataset dir not found: ${DATASET_DIR}"
  echo "  Run: bash scripts/gnm/collect_gnm_data.sh first"
fi

# ── Step 3: Find training script ──────────────────────────────────────────────
echo "[3/4] Locating GNM training script..."
TRAIN_SCRIPT=""
for candidate in \
    "${VNT_DIR}/train/gnm_train/train.py" \
    "${VNT_DIR}/train/vint_train/train.py" \
    "${VNT_DIR}/train/train.py"; do
  if [[ -f "${candidate}" ]]; then
    TRAIN_SCRIPT="${candidate}"
    echo "  Found: ${candidate}"
    break
  fi
done

if [[ -z "${TRAIN_SCRIPT}" ]]; then
  echo "  ⚠️  No training script found."
  echo "  Run: bash scripts/visualnav/setup_visualnav.sh  to clone upstream code"
  if $DRY_RUN; then exit 0; fi
  exit 1
fi

# ── Step 4: Run training ───────────────────────────────────────────────────────
echo "[4/4] Running GNM fine-tuning..."
echo "  Script:  ${TRAIN_SCRIPT}"
echo "  Dataset: ${DATASET_DIR}"
echo "  Epochs:  ${EPOCHS}"
echo ""

if $DRY_RUN; then
  echo "[DRY RUN] Would execute:"
  echo "  python3 ${TRAIN_SCRIPT} \\"
  echo "    --data-folder ${DATASET_DIR} \\"
  echo "    --epochs ${EPOCHS} \\"
  echo "    --model gnm \\"
  echo "    --checkpoint-path ${CHECKPOINT_OUT}"
  echo ""
  echo "✅ Dry run complete — no training executed."
  exit 0
fi

mkdir -p "$(dirname "${CHECKPOINT_OUT}")"

python3 "${TRAIN_SCRIPT}" \
  --data-folder "${DATASET_DIR}" \
  --epochs "${EPOCHS}" \
  --model gnm \
  --checkpoint-path "${CHECKPOINT_OUT}" \
  2>&1 | tee "${REPO_ROOT}/logs/gnm_train_$(date +%Y%m%d_%H%M%S).log"

echo ""
echo "✅ GNM fine-tuning complete."
echo "   Checkpoint: ${CHECKPOINT_OUT}"
echo ""
echo "Next step:"
echo "  python -m fleetsafe_vln.benchmark.episode_runner \\"
echo "    --platform isaac \\"
echo "    --task tasks/hospital_corridor.yaml \\"
echo "    --model gnm \\"
echo "    --safety cbf_qp \\"
echo "    --log-dir runs/gnm_finetuned_eval"
