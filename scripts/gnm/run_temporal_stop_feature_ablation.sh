#!/usr/bin/env bash
set -euo pipefail

echo "=============================================="
echo " Temporal Stop-Head Feature-Set Ablation"
echo "=============================================="

CKPT="/home/favl/robotics/FleetSafe-VisualNav-Benchmark/checkpoints/gnm_base/best.pt"
CFG="configs/gnm/gnm_base.yaml"
DATA_ROOT="datasets/vlntube"
BASE_OUT="results/bo_reviewer_packet/temporal_stop_feature_ablation"

mkdir -p "${BASE_OUT}"

echo "Checkpoint: ${CKPT}"
echo "Config:     ${CFG}"
echo "Data root:  ${DATA_ROOT}"
echo "Output:     ${BASE_OUT}"
echo ""

run_id=0
total=4

for feature_set in dist_only waypoint_only dist_waypoint full_temporal; do
  run_id=$((run_id + 1))
  out_dir="${BASE_OUT}/${feature_set}"

  echo "----------------------------------------------"
  echo "[${run_id}/${total}] feature_set=${feature_set}"
  echo "out_dir=${out_dir}"
  echo "----------------------------------------------"

  if [ -f "${out_dir}/22_temporal_stop_head.csv" ]; then
    echo "[SKIP] completed feature_set=${feature_set}"
    echo ""
    continue
  fi

  python3 scripts/gnm/train_temporal_stop_head.py \
    --ckpt "${CKPT}" \
    --cfg "${CFG}" \
    --data-root "${DATA_ROOT}" \
    --train-split train \
    --eval-split val \
    --device cpu \
    --seq-len 8 \
    --window 3 \
    --feature-set "${feature_set}" \
    --stable-k 3 \
    --epochs 120 \
    --batch-size 256 \
    --seed 7 \
    --out-dir "${out_dir}"

  echo "[DONE] feature_set=${feature_set}"
  echo ""
done

echo "=============================================="
echo " Feature-set ablation runs complete"
echo "=============================================="
