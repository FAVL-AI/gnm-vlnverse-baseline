#!/bin/bash
# H7r diagnostic evaluation matrix. EVERY run forces --data-root explicitly (locked
# methodology: never trust checkpoint-embedded data_root for cross-corpus /
# incumbent-vs-candidate comparison). Track A. Writes each metrics_summary.json into
# training/eval/ under a clear name. DIAGNOSTIC ONLY — no promotion.
set -e
REPO=/home/favl/robotics/gnm-vlnverse-baseline
PY=$HOME/miniforge3/envs/gnm_train/bin/python
EVAL=$REPO/scripts/gnm/06_evaluate.py
INC=checkpoints/hospital_front_rgb_finetune/best.pt          # H1 retained incumbent
CAND=checkpoints/h7r_hospital_pilot_finetune/best.pt         # H7r candidate
H6=checkpoints/h6_hard_families_finetune/best.pt             # H6 procedural (OOD reference)
OUT=$REPO/assets/experiments/hospital_h7_raise_collection/training/eval
mkdir -p "$OUT"

run () { # name ckpt dataroot split
  local name=$1 ckpt=$2 dr=$3 sp=$4
  echo "===== eval $name : $(basename $(dirname $ckpt)) on $dr [$sp] ====="
  WANDB_MODE=offline "$PY" "$EVAL" --ckpt "$ckpt" --data-root "$dr" --split "$sp" \
    --track A --output-dir "$OUT/run_$name" 2>&1 | grep -iE "SR|OSR|SPL|NE|nDTW|data=|n_episodes|episodes|WARN" | tail -6
  cp "$OUT/run_$name/metrics_summary.json" "$OUT/h7r_eval_$name.json"
}

# ---- PRIMARY comparison: H7r held-out test (n=2) ----
run inc_test    "$INC"  datasets/isaac_hospital_h7r test
run cand_test   "$CAND" datasets/isaac_hospital_h7r test
run h6ref_test  "$H6"   datasets/isaac_hospital_h7r test    # procedural H6 model on hospital = OOD reference

# ---- SANITY (H7r train/val — reporting only, NOT claims) ----
run cand_val    "$CAND" datasets/isaac_hospital_h7r val
run cand_train  "$CAND" datasets/isaac_hospital_h7r train
run inc_val     "$INC"  datasets/isaac_hospital_h7r val

# ---- OOD DIAGNOSTIC (prior held-out H4, labelled out-of-domain) ----
run cand_ood_h4 "$CAND" datasets/isaac_hospital_h4 test
run inc_ood_h4  "$INC"  datasets/isaac_hospital_h4 test

echo "H7R_EVAL_MATRIX_DONE -> $OUT"
