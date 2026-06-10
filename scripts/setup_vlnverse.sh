#!/usr/bin/env bash
# scripts/setup_vlnverse.sh
# ─────────────────────────────────────────────────────────────────────────────
# Prepare the datasets/vlnverse directory structure and optionally download
# a small sample of VLNVerse data.
#
# VLNVerse is used as a benchmark/data reference. FleetSafe extends it with
# the Yahboom ROSMASTER M3 Pro, GNM adapters, CBF-QP safety shield, and
# ROS 2 / Isaac Sim bridge.
#
# Usage:
#   bash scripts/setup_vlnverse.sh            # create dirs + print instructions
#   bash scripts/setup_vlnverse.sh --sample   # create sample preview stub
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VLNVERSE_ROOT="${REPO_ROOT}/datasets/vlnverse"
SAMPLE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sample) SAMPLE=true; shift ;;
    *) echo "[WARN] Unknown arg: $1"; shift ;;
  esac
done

export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"

echo "========================================"
echo "  FleetSafe — VLNVerse Setup"
echo "========================================"
echo "  Target: ${VLNVERSE_ROOT}"
echo ""

# ── Create directory structure ─────────────────────────────────────────────
echo "--- Creating dataset directories ---"
mkdir -p \
  "${VLNVERSE_ROOT}/scenes" \
  "${VLNVERSE_ROOT}/data" \
  "${VLNVERSE_ROOT}/previews" \
  "${VLNVERSE_ROOT}/metadata"

for d in scenes data previews metadata; do
  count=$(find "${VLNVERSE_ROOT}/${d}" -type f 2>/dev/null | wc -l)
  printf "  %-12s  (%d files)\n" "${d}/" "${count}"
done

echo ""

# ── Sample stub (--sample flag) ────────────────────────────────────────────
if $SAMPLE; then
  echo "--- Creating sample preview stub ---"
  cat > "${VLNVERSE_ROOT}/metadata/sample_info.json" <<'JEOF'
{
  "source": "VLNVerse",
  "note": "This is a sample stub. Download real data from HuggingFace or VLNVerse project.",
  "sample_instructions": [
    "Go down the corridor and turn left at the intersection.",
    "Navigate to the nurse station at the end of the hallway.",
    "Proceed through the double doors and stop near the reception desk.",
    "Turn right past the supply closet and wait by the elevator.",
    "Follow the blue line on the floor to the patient room."
  ],
  "hf_datasets": [
    {"id": "R2R",        "hf_repo": "waymo/r2r",                          "size_gb": 15},
    {"id": "RxR",        "hf_repo": "google-research-datasets/rxr",       "size_gb": 40},
    {"id": "REVERIE",    "hf_repo": "VLN-BERT/REVERIE",                   "size_gb": 8},
    {"id": "GNM-dataset","hf_repo": "robodhruv/go-navigate-move",         "size_gb": 120}
  ]
}
JEOF
  echo "[OK]  Sample metadata written: ${VLNVERSE_ROOT}/metadata/sample_info.json"
  echo ""
fi

# ── Download instructions ──────────────────────────────────────────────────
echo "--- VLNVerse data download instructions ---"
cat <<MSG
  VLNVerse is NOT downloaded automatically to avoid pulling hundreds of GB.

  To download manually:

  Option A — HuggingFace CLI (recommended):
    pip install huggingface-hub
    huggingface-cli download waymo/r2r --repo-type dataset \\
      --local-dir ${VLNVERSE_ROOT}/data/r2r

  Option B — Python:
    from datasets import load_dataset
    ds = load_dataset("waymo/r2r", split="train[:5%]")   # 5% sample

  Option C — Place files manually:
    scenes   → ${VLNVERSE_ROOT}/scenes/
    previews → ${VLNVERSE_ROOT}/previews/
    metadata → ${VLNVERSE_ROOT}/metadata/
    data     → ${VLNVERSE_ROOT}/data/

  After downloading, run the indexer:
    python -m fleetsafe_vln.benchmark.vlnverse_indexer

MSG

# ── Run indexer ────────────────────────────────────────────────────────────
echo "--- Running VLNVerse indexer ---"
python3 -m fleetsafe_vln.benchmark.vlnverse_indexer \
  --root "${VLNVERSE_ROOT}" 2>&1

echo ""
echo "Setup complete."
echo "  Next: python -m fleetsafe_vln.benchmark.vlnverse_indexer"
echo "  Then: open http://localhost:3000/dashboard/vln-hub"
