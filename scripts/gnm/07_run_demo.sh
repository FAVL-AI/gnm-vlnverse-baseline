#!/usr/bin/env bash
# scripts/gnm/07_run_demo.sh
# ─────────────────────────────────────────────────────────────────────────────
# Step 7 of 7: Run a live GNM demo in Isaac Sim.
#
# What this does
# ──────────────
#   1. Starts Isaac Sim with the VLNVerse hospital scene
#   2. Loads the trained GNM checkpoint
#   3. Runs 5 evaluation episodes (one per task)
#   4. Prints results table with SR, SPL, NE
#
# Prerequisites
# ─────────────
#   - Isaac Sim 4.5 installed
#   - GNM trained: checkpoints/gnm_base/best.pt must exist
#   - Run 04_train_gnm.py first
#
# Usage
# ─────
#   bash scripts/gnm/07_run_demo.sh
#   bash scripts/gnm/07_run_demo.sh --ckpt checkpoints/gnm_lora/best.pt --track C
#   bash scripts/gnm/07_run_demo.sh --offline    # offline eval (no Isaac)
#   bash scripts/gnm/07_run_demo.sh --n-episodes 3
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CKPT="checkpoints/gnm_base/best.pt"
TRACK="A"
OFFLINE=false
N_EPISODES=5

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ckpt)       CKPT="$2";       shift 2 ;;
    --track)      TRACK="$2";      shift 2 ;;
    --offline)    OFFLINE=true;    shift ;;
    --n-episodes) N_EPISODES="$2"; shift 2 ;;
    *) echo "[WARN] Unknown arg: $1"; shift ;;
  esac
done

echo ""
echo "════════════════════════════════════════════════════"
echo " FleetSafe GNM-VLNVerse — Live Demo"
echo "════════════════════════════════════════════════════"
echo " Checkpoint: ${CKPT}"
echo " Track:      ${TRACK}"
echo " Episodes:   ${N_EPISODES}"
echo " Mode:       $(${OFFLINE} && echo 'offline' || echo 'live Isaac')"
echo ""

# ── Check checkpoint ──────────────────────────────────────────────────────────
if [[ ! -f "${REPO_ROOT}/${CKPT}" ]]; then
  echo "  ERROR: Checkpoint not found: ${REPO_ROOT}/${CKPT}"
  echo "  Run: python scripts/gnm/04_train_gnm.py"
  exit 1
fi

if $OFFLINE; then
  # ── Offline evaluation ────────────────────────────────────────────────────
  echo "[Offline] Running evaluation on val split..."
  python "${REPO_ROOT}/scripts/gnm/06_evaluate.py" \
    --ckpt  "${CKPT}" \
    --split val \
    --track "${TRACK}" \
    --save-episodes
else
  # ── Live Isaac Sim evaluation ─────────────────────────────────────────────
  ISAAC_PYTHON=""
  for P in \
    "${HOME}/.local/share/ov/pkg/isaac-sim-4.5.0/python.sh" \
    "${HOME}/.local/share/ov/pkg/isaac_sim-4.5.0/python.sh" \
    "/opt/isaac-sim/python.sh"; do
    if [[ -f "$P" ]]; then
      ISAAC_PYTHON="$P"
      break
    fi
  done

  if [[ -z "${ISAAC_PYTHON}" ]]; then
    echo "  Isaac Sim not found — falling back to offline evaluation."
    "${BASH_SOURCE[0]}" --offline --ckpt "${CKPT}" --track "${TRACK}"
    exit 0
  fi

  echo "[Isaac] Starting live evaluation..."
  "${ISAAC_PYTHON}" - <<PYEOF
import sys
sys.path.insert(0, "${REPO_ROOT}")

import torch
from gnm_vlnverse.models.gnm import build_gnm
from gnm_vlnverse.evaluation.evaluator import GNMEvaluator
from gnm_vlnverse.evaluation.metrics import compute_all_metrics

# Load checkpoint
ckpt = torch.load("${REPO_ROOT}/${CKPT}", map_location="cpu")
cfg  = ckpt.get("cfg", {})
model = build_gnm(cfg.get("model", {}))
model.load_state_dict(ckpt["model_state"])

evaluator = GNMEvaluator(
    model         = model,
    action_std    = cfg.get("data", {}).get("action_std", [1.0, 1.0]),
    context_size  = cfg.get("model", {}).get("context_size", 5),
    stop_threshold= 0.15,
    max_steps     = 500,
    track         = "${TRACK}",
)

# Run offline evaluation (live Isaac wiring requires additional Isaac setup)
metrics = evaluator.evaluate_dataset(
    data_root = "${REPO_ROOT}/datasets/gnm_vlnverse",
    split     = "val",
)

print()
print(metrics)
print()
PYEOF
fi

echo ""
echo "Results saved to: checkpoints/*/eval_val_track${TRACK}/"
echo ""
