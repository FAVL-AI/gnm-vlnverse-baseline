#!/usr/bin/env bash
set -euo pipefail

echo "=============================================="
echo " Temporal Stop-Head Ablation Runner"
echo "=============================================="

CKPT="/home/favl/robotics/FleetSafe-VisualNav-Benchmark/checkpoints/gnm_base/best.pt"
CFG="configs/gnm/gnm_base.yaml"
DATA_ROOT="datasets/vlntube"
BASE_OUT="results/bo_reviewer_packet/temporal_stop_head_ablation"

mkdir -p "${BASE_OUT}"

echo "Checkpoint: ${CKPT}"
echo "Config:     ${CFG}"
echo "Data root:  ${DATA_ROOT}"
echo "Output:     ${BASE_OUT}"
echo ""

run_id=0
total=16

for seq_len in 4 8 12 16; do
  for stable_k in 1 2 3 5; do
    run_id=$((run_id + 1))
    out_dir="${BASE_OUT}/seq${seq_len}_k${stable_k}"

    echo "----------------------------------------------"
    echo "[${run_id}/${total}] seq_len=${seq_len}, stable_k=${stable_k}"
    echo "out_dir=${out_dir}"
    echo "----------------------------------------------"

    python3 scripts/gnm/train_temporal_stop_head.py \
      --ckpt "${CKPT}" \
      --cfg "${CFG}" \
      --data-root "${DATA_ROOT}" \
      --train-split train \
      --eval-split val \
      --device cpu \
      --seq-len "${seq_len}" \
      --stable-k "${stable_k}" \
      --epochs 120 \
      --batch-size 256 \
      --seed 7 \
      --out-dir "${out_dir}"

    echo "[DONE] seq_len=${seq_len}, stable_k=${stable_k}"
    echo ""
  done
done

echo "=============================================="
echo " Ablation runs complete"
echo "=============================================="
