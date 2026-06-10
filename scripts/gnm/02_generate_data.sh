#!/usr/bin/env bash
# scripts/gnm/02_generate_data.sh
# ─────────────────────────────────────────────────────────────────────────────
# Step 2 of 7: Generate GNM training data from VLNTube.
#
# What is VLNTube?
# ─────────────────
# VLNTube is the data generation pipeline for VLNVerse.  It creates navigation
# episodes inside Isaac Sim using:
#   - scene_graph.summarizer  → builds semantic map of the scene
#   - vistube                 → records visual trajectories from A* planning
#   - instube                 → generates language instructions (Gemini)
#   - datatube                → packages everything for training
#
# What data comes out?
# ────────────────────
#   datasets/vlntube/<split>/<episode_id>/
#     *.jpg           — numbered RGB frames (96×96 after conversion)
#     traj_data.pkl   — positions + yaws as numpy arrays
#     instruction.txt — language instruction (for Track B)
#     scene_graph.json
#
# This script either:
#   a) Invokes VLNTube if VLNVerse + Isaac Sim are configured
#   b) Downloads the pre-generated dataset from Hugging Face (recommended
#      for first-time setup)
#
# Usage
# ─────
#   bash scripts/gnm/02_generate_data.sh                     # HF download
#   bash scripts/gnm/02_generate_data.sh --generate          # live VLNTube
#   bash scripts/gnm/02_generate_data.sh --generate --scenes hospital_v1,hospital_v2
#   bash scripts/gnm/02_generate_data.sh --smoke-test        # 20 episodes only
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MODE="download"          # "download" | "generate"
SMOKE_TEST=false
SCENES="hospital_v1,hospital_v2,office_v1,office_v2,warehouse_v1"
OUTPUT_DIR="${REPO_ROOT}/datasets/vlntube"
HF_REPO="frankleroyvan/fleetsafe-gnm-vlnverse"   # Hugging Face dataset

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

while [[ $# -gt 0 ]]; do
  case "$1" in
    --generate)   MODE="generate"; shift ;;
    --smoke-test) SMOKE_TEST=true; shift ;;
    --scenes)     SCENES="$2"; shift 2 ;;
    --output)     OUTPUT_DIR="$2"; shift 2 ;;
    *) echo "[WARN] Unknown arg: $1"; shift ;;
  esac
done

echo ""
echo "════════════════════════════════════════════════════"
echo " FleetSafe GNM-VLNVerse — Data Generation"
echo "════════════════════════════════════════════════════"
echo " Mode:    ${MODE}"
echo " Output:  ${OUTPUT_DIR}"
echo " Scenes:  ${SCENES}"
echo " Smoke:   ${SMOKE_TEST}"
echo ""

mkdir -p "${OUTPUT_DIR}"/{train,val,test}

if [[ "${MODE}" == "download" ]]; then
  # ── Download pre-generated dataset from Hugging Face ─────────────────────
  echo "[HF download] Fetching dataset from ${HF_REPO}..."
  echo ""

  if python3 -c "import huggingface_hub" 2>/dev/null; then
    # Note: SMOKE_TEST is a bash bool (true/false); Python needs True/False.
    SMOKE_PY="False"
    if $SMOKE_TEST; then SMOKE_PY="True"; fi

    python3 - <<PYEOF
from pathlib import Path
from huggingface_hub import snapshot_download

repo_id    = "${HF_REPO}"
local_dir  = Path("${OUTPUT_DIR}")
smoke_test = ${SMOKE_PY}

print(f"  Downloading {repo_id} -> {local_dir}")
print("  This may take a few minutes on first run (cached afterwards).")
print("")

import sys
try:
    from huggingface_hub.utils import RepositoryNotFoundError
    snapshot_download(
        repo_id=repo_id,
        repo_type="dataset",
        local_dir=str(local_dir),
        allow_patterns=["train/*", "val/*", "test/*", "README.md"]
            if not smoke_test else ["val/*", "test/*"],
    )
except Exception as e:
    print(f"  ERROR: {e}")
    print("")
    print("  The HF dataset does not exist yet or is private.")
    print(f"  Upload data with: huggingface-cli upload-large-folder {repo_id} {local_dir} --repo-type dataset")
    print("  Or generate data locally with: bash scripts/gnm/02_generate_data.sh --generate")
    sys.exit(1)

total_eps = 0
for split in ["train", "val", "test"]:
    split_dir = local_dir / split
    if split_dir.exists():
        n = sum(1 for d in split_dir.iterdir() if d.is_dir())
        print(f"  {split:6s}: {n:5d} episodes")
        total_eps += n

print("")
if total_eps == 0:
    print("  ERROR: download appeared to succeed but 0 episodes found.")
    print("  The HF dataset may be empty or the repo ID is wrong.")
    print(f"  Expected: {repo_id}")
    sys.exit(1)
print(f"  Download complete. ({total_eps} episodes total)")
PYEOF
  else
    echo -e "${YELLOW}  huggingface_hub not installed.${NC}"
    echo "  Install with: pip install huggingface_hub"
    echo ""
    echo "  Alternative: generate data with --generate flag"
    echo "  Alternative: manually place episodes in ${OUTPUT_DIR}/{train,val,test}/"
    echo ""
    echo "  Creating placeholder directories so subsequent steps can run..."
    for SPLIT in train val test; do
      mkdir -p "${OUTPUT_DIR}/${SPLIT}/placeholder_000"
      echo '{"placeholder": true}' > "${OUTPUT_DIR}/${SPLIT}/placeholder_000/source_episode.json"
    done
    echo ""
    echo -e "${YELLOW}  WARNING: placeholder data only — results will be meaningless.${NC}"
  fi

else
  # ── Generate data using VLNTube + Isaac Sim ───────────────────────────────
  echo "[VLNTube] Generating trajectories with Isaac Sim..."
  echo ""

  # Honour $ISAAC_PYTHON env var if set, then auto-detect in priority order:
  #   1. Omniverse Launcher installs (python.sh wrapper)
  #   2. pip-installed Isaac Sim in named conda envs (isaac, isaacsim)
  #   3. Active conda environment
  if [[ -z "${ISAAC_PYTHON:-}" ]]; then
    for P in \
      "${HOME}/.local/share/ov/pkg/isaac-sim-4.5.0/python.sh" \
      "${HOME}/.local/share/ov/pkg/isaac_sim-4.5.0/python.sh" \
      "/opt/isaac-sim/python.sh"; do
      if [[ -f "$P" ]]; then ISAAC_PYTHON="$P"; break; fi
    done
  fi

  # pip-install fallback: check conda envs that have isaacsim installed
  if [[ -z "${ISAAC_PYTHON:-}" ]]; then
    for ENV_NAME in isaac isaacsim; do
      CANDIDATE="${HOME}/miniforge3/envs/${ENV_NAME}/bin/python"
      if [[ -f "$CANDIDATE" ]]; then
        if "${CANDIDATE}" -c "import isaacsim" 2>/dev/null; then
          ISAAC_PYTHON="$CANDIDATE"
          echo "  ✓ Found pip-installed Isaac Sim in conda env: ${ENV_NAME}"
          break
        fi
      fi
    done
  fi

  # Active conda env fallback
  if [[ -z "${ISAAC_PYTHON:-}" && -n "${CONDA_PREFIX:-}" ]]; then
    CANDIDATE="${CONDA_PREFIX}/bin/python"
    if "${CANDIDATE}" -c "import isaacsim" 2>/dev/null; then
      ISAAC_PYTHON="$CANDIDATE"
      echo "  ✓ Found pip-installed Isaac Sim in active conda env"
    fi
  fi

  if [[ -z "${ISAAC_PYTHON:-}" ]]; then
    echo "  ✗ Isaac Sim not found."
    echo "    Option A (Launcher): install Isaac Sim 4.5.0 from https://developer.nvidia.com/isaac-sim"
    echo "    Option B (pip):      conda activate isaac && pip install isaacsim==5.1.0.0 --extra-index-url https://pypi.nvidia.com"
    echo "    Option C (manual):   export ISAAC_PYTHON=/path/to/python"
    exit 1
  fi
  echo "  ✓ Isaac Python: ${ISAAC_PYTHON}"

  # ── Preflight: verify scene asset / split overlap ─────────────────────────
  echo ""
  echo "  Preflight: checking scene-split overlap..."
  python3 "${REPO_ROOT}/scripts/gnm/check_scene_overlap.py" --top 5 2>&1 | sed 's/^/    /'
  USABLE=$(python3 - <<'PYEOF'
import sys
sys.path.insert(0, '.')
from scripts.gnm.check_scene_overlap import collect_usd_scenes
print(len(collect_usd_scenes()))
PYEOF
  )
  if [[ "${USABLE}" == "0" ]]; then
    echo ""
    echo "  ✗ No usable scenes found.  Download a scene first:"
    echo "    python3 -c \""
    echo "      from huggingface_hub import snapshot_download"
    echo "      snapshot_download('Eyz/VLNVerse_scene', repo_type='dataset',"
    echo "          allow_patterns=['kujiale_0092/*'],"
    echo "          local_dir='datasets/vlntube/envs')\""
    exit 1
  fi
  echo "  ✓ ${USABLE} usable scene(s) found"
  echo ""

  IFS=',' read -ra SCENE_LIST <<< "${SCENES}"
  MAX_EPISODES=10000
  if $SMOKE_TEST; then
    MAX_EPISODES=20
    echo "  Smoke test: generating ${MAX_EPISODES} episodes total"
  fi

  # vlntube_runner.py processes one split at a time (not one scene at a time).
  # --scenes filters which scenes to render within that split.
  # fine_val_unseen / fine_test are held-out splits; render them for evaluation.
  for SPLIT_NAME in fine_train fine_val fine_val_unseen fine_test; do
    echo ""
    echo "  Split: ${SPLIT_NAME}  scenes: ${SCENES}"
    "${ISAAC_PYTHON}" "${REPO_ROOT}/scripts/gnm/vlntube_runner.py" \
      --split "${SPLIT_NAME}" \
      --scenes "${SCENES}" \
      --output "${OUTPUT_DIR}" \
      --max-episodes "${MAX_EPISODES}" \
      2>&1 | tail -5 || echo "  [WARN] VLNTube run failed for ${SPLIT_NAME}"
  done
fi

# ── Dataset statistics ─────────────────────────────────────────────────────────
echo ""
echo "── Dataset Statistics ────────────────────────────────────────────────────"
python3 - <<'PYEOF'
import pickle, pathlib, math

output_dir = pathlib.Path("datasets/vlntube")
total_frames = 0
for split in ["train", "val", "test"]:
    split_dir = output_dir / split
    if not split_dir.exists():
        print(f"  {split:6s}: not found")
        continue
    dirs  = [d for d in split_dir.iterdir() if d.is_dir()]
    frames = 0
    for d in dirs:
        p = d / "traj_data.pkl"
        if p.exists():
            try:
                data = pickle.load(open(p, "rb"))
                frames += len(data["position"])
            except Exception:
                pass
    total_frames += frames
    hours = frames / (5 * 3600)
    print(f"  {split:6s}: {len(dirs):5d} episodes  |  {frames:7d} frames  |  {hours:.1f}h @ 5Hz")

print(f"  {'TOTAL':6s}: {total_frames:7d} frames")
PYEOF

echo ""
echo "Next step:"
echo "   python scripts/gnm/03_compute_action_std.py"
echo ""
