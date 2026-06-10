#!/usr/bin/env bash
# scripts/run_interactive_iamgoodnavigator_recording.sh
# Interactive wrapper for IAmGoodNavigator episode recording.
# Prints clear instructions before launching, then checks output afterwards.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

TASK="${1:-fine}"
INDEX="${2:-0}"
WORK_DIR="${REPO_ROOT}/runs/iamgoodnavigator/${TASK}_${INDEX}"
IMPORT_DIR="${REPO_ROOT}/datasets/vlnverse/imported/iamgoodnavigator/${TASK}_${INDEX}"

echo "========================================"
echo "  FleetSafe — Interactive VLN Recording"
echo "  task=${TASK}  index=${INDEX}"
echo "========================================"
echo ""
echo "  ┌─────────────────────────────────────────────────────────────────┐"
echo "  │  IMPORTANT: When Isaac Sim opens                                │"
echo "  │                                                                  │"
echo "  │  1. Do NOT close Isaac.                                         │"
echo "  │  2. Go to: Perspective → Cameras → FloatingCamera               │"
echo "  │  3. Let the demo navigate (or interact if prompted).            │"
echo "  │  4. Capture screenshots for evidence while it runs.             │"
echo "  │  5. Return to THIS terminal and press ENTER when done.          │"
echo "  │                                                                  │"
echo "  │  Evidence screenshot commands (run in a second terminal):       │"
echo "  │    gnome-screenshot -f evidence/fleetsafe_vlnverse_plus/        │"
echo "  │                       01_isaac_floatingcamera_scene.png         │"
echo "  └─────────────────────────────────────────────────────────────────┘"
echo ""

# ── Source ROS 2 ─────────────────────────────────────────────────────────────
source /opt/ros/humble/setup.bash 2>/dev/null || true

# ── Activate isaac conda env if available ────────────────────────────────────
CONDA_BASE="${CONDA_PREFIX_1:-$(conda info --base 2>/dev/null || echo '/home/favl/miniforge3')}"
CONDA_BASE="${CONDA_BASE%/envs/*}"
if [[ -f "${CONDA_BASE}/etc/profile.d/conda.sh" ]]; then
    source "${CONDA_BASE}/etc/profile.d/conda.sh" 2>/dev/null || true
    conda activate isaac 2>/dev/null || true
fi

# ── Launch episode ────────────────────────────────────────────────────────────
echo "  Launching: bash scripts/run_iamgoodnavigator_episode.sh ${TASK} ${INDEX}"
echo "  ─────────────────────────────────────────────────────────────────"
echo ""
bash scripts/run_iamgoodnavigator_episode.sh "${TASK}" "${INDEX}"
RC=$?

echo ""
echo "  ─────────────────────────────────────────────────────────────────"
echo "  Episode script exited (code ${RC})."
echo ""

# ── Inspect output ────────────────────────────────────────────────────────────
echo "  Checking output..."
echo ""

TRAJ_COUNT=$(find "${WORK_DIR}" -name "*.csv" -o -name "trajectory*.json" -o -name "*traj*.json" 2>/dev/null | wc -l)
IMG_COUNT=$(find "${WORK_DIR}" -name "*.jpg" -o -name "*.png" 2>/dev/null | wc -l)
TRAJ_COUNT="${TRAJ_COUNT// /}"
IMG_COUNT="${IMG_COUNT// /}"

echo "  Trajectory files: ${TRAJ_COUNT}"
echo "  Image files:      ${IMG_COUNT}"
echo ""

if [[ -f "${IMPORT_DIR}/episode_meta.json" ]]; then
    EP_STATUS=$(python3 -c "import json; d=json.load(open('${IMPORT_DIR}/episode_meta.json')); print(d.get('status','unknown'))" 2>/dev/null || echo "unknown")
    EV_VALID=$(python3 -c "import json; d=json.load(open('${IMPORT_DIR}/episode_meta.json')); print(str(d.get('evidence_valid',False)).lower())" 2>/dev/null || echo "false")
    echo "  episode_meta.json:"
    echo "    status=${EP_STATUS}"
    echo "    evidence_valid=${EV_VALID}"
fi

STATUS_FILE="${WORK_DIR}/output_status.json"

if [[ "${TRAJ_COUNT}" -gt 0 || "${IMG_COUNT}" -gt 0 ]]; then
    echo ""
    echo "  [OK]  Recording produced output."
    python3 -c "
import json
from datetime import datetime, timezone
from pathlib import Path
Path('${STATUS_FILE}').write_text(json.dumps({
    'status': 'completed',
    'trajectory_files': ${TRAJ_COUNT},
    'image_files': ${IMG_COUNT},
    'generated_at': datetime.now(timezone.utc).isoformat(),
}, indent=2))
"
else
    echo "  [INFO] No trajectory/image output produced."
    echo "  This is a known upstream limitation of the IAmGoodNavigator demo"
    echo "  when run outside the full Isaac Sim interactive pipeline."
    echo ""
    echo "  The trajectory CSV may be written after the demo completes the"
    echo "  navigation path. Check ${WORK_DIR}/ for any *.csv files."
    python3 -c "
import json
from datetime import datetime, timezone
from pathlib import Path
Path('${STATUS_FILE}').write_text(json.dumps({
    'status': 'completed_no_output',
    'trajectory_files': 0,
    'image_files': 0,
    'generated_at': datetime.now(timezone.utc).isoformat(),
    'message': 'Episode ran, but upstream demo produced no trajectory/image files. Manual recording output still required.',
}, indent=2))
"
fi

echo ""
echo "  Output dir: ${WORK_DIR}/"
ls -la "${WORK_DIR}/" 2>/dev/null | grep -v "^\." | tail -10

echo ""
echo "  To update acceptance check:"
echo "    bash scripts/check_fleetsafe_vlnverse_plus_demo.sh"
