#!/usr/bin/env bash
# GNM fine-tuning wrapper for FleetSafe-GNM Isaac data.
# Usage: bash train_gnm_from_collected_data.sh [--dry-run]
#
# Always starts from the public or previously fine-tuned GNM checkpoint.
# Does not train from random initialization.
# Supports head tuning (fast) or LoRA (better adaptation).
# In dry-run mode, writes a training manifest without running GPU training.

set -euo pipefail

DRY_RUN=false
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
  esac
done

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
CONFIG="$ROOT/configs/gnm_fleetsafe_isaac.yaml"
RESULTS_DIR="$ROOT/results/gnm_fleetsafe_v2"
MANIFEST="$RESULTS_DIR/training_manifest.json"

echo "============================================================"
echo " FleetSafe-GNM Training Wrapper"
echo "============================================================"
echo "Config    : $CONFIG"
echo "Results   : $RESULTS_DIR"
echo "Dry-run   : $DRY_RUN"
echo "============================================================"

mkdir -p "$RESULTS_DIR"

if [[ -f "$CONFIG" ]]; then
  echo "[OK] Config file found: $CONFIG"
else
  echo "[INFO] Config not found at: $CONFIG"
  echo "[INFO] Expected config path: configs/gnm_fleetsafe_isaac.yaml"
  echo "[INFO] Create it or copy the template before running live training."
fi

echo ""
echo "Training strategy:"
echo "  1. Start from public GNM checkpoint (checkpoints/gnm_public_or_finetuned.pt)."
echo "     Download from: https://github.com/robodhruv/visualnav-transformer"
echo "     or use a previously fine-tuned checkpoint."
echo ""
echo "  2. Fine-tuning modes (set in config: gnm.fine_tuning_mode):"
echo "     head_or_lora:"
echo "       - Head tuning: freeze GNM backbone, train only the output head."
echo "         Faster, lower GPU memory, suitable for domain adaptation."
echo "       - LoRA: add trainable low-rank adapters to the GNM encoder."
echo "         Better adaptation to new sensors/environments, more VRAM needed."
echo ""
echo "  3. Dataset: datasets/gnm_fleetsafe_converted/"
echo "     Each episode provides (context_images, goal_image, waypoints, odometry)."
echo "     Collect episodes with: bash scripts/gnm/collect_isaac_rosbag_episode.sh"
echo "     Convert with: python3 scripts/gnm/convert_rosbag_to_gnm_dataset.py"
echo ""

TIMESTAMP="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"

cat > "$MANIFEST" <<EOF
{
  "created_at": "$TIMESTAMP",
  "dry_run": $DRY_RUN,
  "config": "$CONFIG",
  "checkpoint": "checkpoints/gnm_public_or_finetuned.pt",
  "dataset_root": "datasets/gnm_fleetsafe_converted",
  "fine_tuning_mode": "head_or_lora",
  "training_command": [
    "python3 scripts/gnm/04_train_gnm.py",
    "--config configs/gnm_fleetsafe_isaac.yaml",
    "--checkpoint checkpoints/gnm_public_or_finetuned.pt",
    "--dataset-root datasets/gnm_fleetsafe_converted",
    "--output-dir checkpoints/gnm_fleetsafe_finetuned.pt"
  ],
  "lora_command": [
    "python3 scripts/gnm/05_train_lora.py",
    "--config configs/gnm_fleetsafe_isaac.yaml",
    "--checkpoint checkpoints/gnm_public_or_finetuned.pt",
    "--dataset-root datasets/gnm_fleetsafe_converted",
    "--output-dir checkpoints/gnm_fleetsafe_lora.pt"
  ],
  "notes": [
    "Do not train from random initialization.",
    "Always start from a public or previously fine-tuned checkpoint.",
    "Head tuning is the default fast path.",
    "LoRA is optional for better sensor/environment adaptation.",
    "Set CUDA_VISIBLE_DEVICES before running live training.",
    "Dry-run numbers are placeholders; no GPU training was performed."
  ]
}
EOF

echo "[OK] Training manifest written: $MANIFEST"

if $DRY_RUN; then
  echo ""
  echo "[DRY-RUN] GPU training was not run."
  echo "[DRY-RUN] To run live training:"
  echo "  1. Collect Isaac Sim episodes."
  echo "  2. Convert them: python3 scripts/gnm/convert_rosbag_to_gnm_dataset.py ..."
  echo "  3. Download public GNM checkpoint."
  echo "  4. Run: bash scripts/gnm/train_gnm_from_collected_data.sh"
  echo "     (without --dry-run)"
else
  echo ""
  echo "[INFO] Live training requires:"
  echo "  - datasets/gnm_fleetsafe_converted/ with at least one episode"
  echo "  - checkpoints/gnm_public_or_finetuned.pt"
  echo "  - PyTorch with CUDA"
  echo ""
  echo "[INFO] To start actual training, call the train script directly:"
  echo "  python3 scripts/gnm/04_train_gnm.py \\"
  echo "    --config configs/gnm_fleetsafe_isaac.yaml \\"
  echo "    --checkpoint checkpoints/gnm_public_or_finetuned.pt \\"
  echo "    --dataset-root datasets/gnm_fleetsafe_converted"
fi

echo ""
echo "============================================================"
echo "[OK] Training wrapper complete."
echo "============================================================"
