#!/bin/bash
# Fleet-Safe-VLA-OS — Yahboom M3Pro Isaac Lab RL Evaluation
#
# Evaluates a trained checkpoint in Isaac Lab.
# Always runs asset validation before launching Isaac Sim.
#
# Usage:
#   ./scripts/isaaclab/eval_yahboom.sh --stage 1 --checkpoint logs/isaaclab/yahboom_m3pro/stage1/model_1999.pt
#   ./scripts/isaaclab/eval_yahboom.sh --stage 1 --latest          # auto-find latest Stage 1 checkpoint
#   ./scripts/isaaclab/eval_yahboom.sh --stage 1 --record-video    # save MP4
#   ./scripts/isaaclab/eval_yahboom.sh --stage 3 --num-envs 16 --gui
#
# Output:
#   Telemetry printed to console and streamed to FleetSafe dashboard
#   (if run_yahboom_bridge.sh is running in another terminal).
#
#   Video (--record-video):  logs/isaaclab/yahboom_m3pro/eval/stage<N>_<ts>.mp4

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

STAGE=1
CHECKPOINT=""
FIND_LATEST=false
RECORD_VIDEO=false
NUM_ENVS=16
HEADLESS="true"
EXTRA_ARGS=()

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --stage)        STAGE="$2";       shift 2 ;;
        --stage=*)      STAGE="${1#--stage=}"; shift ;;
        --checkpoint)   CHECKPOINT="$2";  shift 2 ;;
        --checkpoint=*) CHECKPOINT="${1#--checkpoint=}"; shift ;;
        --latest)       FIND_LATEST=true; shift ;;
        --record-video) RECORD_VIDEO=true; HEADLESS="false"; shift ;;
        --gui)          HEADLESS="false"; shift ;;
        --num-envs)     NUM_ENVS="$2";    shift 2 ;;
        --num-envs=*)   NUM_ENVS="${1#--num-envs=}"; shift ;;
        *)              EXTRA_ARGS+=("$1"); shift ;;
    esac
done

echo "============================================================"
echo "  Fleet-Safe-VLA-OS  |  Yahboom M3Pro Isaac Lab Evaluation"
echo "  Stage      : $STAGE"
echo "  Num envs   : $NUM_ENVS"
echo "  Headless   : $HEADLESS"
echo "  Video      : $RECORD_VIDEO"
echo "============================================================"
echo ""

# ── Asset validation ──────────────────────────────────────────────────────────
M3PRO_URDF="${REPO_ROOT}/fleet_safe_vla/robots/yahboom/urdf/yahboom_m3pro.urdf"
if [[ ! -f "$M3PRO_URDF" ]]; then
    echo "[ERROR] M3Pro URDF missing — cannot run evaluation."
    echo "  Run: ./scripts/isaaclab/train_yahboom.sh --stage 0"
    exit 1
fi

# ── Map stage → task name ─────────────────────────────────────────────────────
case "$STAGE" in
    1) TASK="FleetSafe-M3Pro-VelTracking-v0"   ;;
    2) TASK="FleetSafe-M3Pro-WaypointNav-v0"   ;;
    3) TASK="FleetSafe-M3Pro-Obstacles-v0"     ;;
    4) TASK="FleetSafe-M3Pro-FleetSafe-v0"     ;;
    5) TASK="FleetSafe-M3Pro-Mimic-v0"         ;;
    *)
        echo "[ERROR] Unknown stage: $STAGE  (valid: 1–5)"
        exit 1 ;;
esac

LOG_DIR="${REPO_ROOT}/logs/isaaclab/yahboom_m3pro/stage${STAGE}"

# ── Resolve checkpoint ────────────────────────────────────────────────────────
if $FIND_LATEST; then
    # Find the most recently modified checkpoint in the stage log dir
    if [[ ! -d "$LOG_DIR" ]]; then
        echo "[ERROR] No Stage $STAGE log directory found: $LOG_DIR"
        echo "  Run training first: ./scripts/isaaclab/train_yahboom.sh --stage $STAGE"
        exit 1
    fi
    CHECKPOINT=$(find "$LOG_DIR" -name "model_*.pt" -printf "%T@ %p\n" 2>/dev/null \
                 | sort -n | tail -1 | awk '{print $2}')
    if [[ -z "$CHECKPOINT" ]]; then
        echo "[ERROR] No checkpoints found in $LOG_DIR"
        exit 1
    fi
    echo "[INFO] Auto-selected checkpoint: $CHECKPOINT"
fi

if [[ -z "$CHECKPOINT" ]]; then
    echo "[ERROR] No checkpoint specified."
    echo "  Options:"
    echo "    $0 --stage $STAGE --latest"
    echo "    $0 --stage $STAGE --checkpoint logs/isaaclab/yahboom_m3pro/stage${STAGE}/model_<N>.pt"
    exit 1
fi

if [[ ! -f "$CHECKPOINT" ]]; then
    echo "[ERROR] Checkpoint not found: $CHECKPOINT"
    exit 1
fi

EVAL_LOG="${REPO_ROOT}/logs/isaaclab/yahboom_m3pro/eval"
mkdir -p "$EVAL_LOG"

echo "[INFO] Task       : $TASK"
echo "[INFO] Checkpoint : $CHECKPOINT"
echo "[INFO] Eval log   : $EVAL_LOG"
echo ""

# ── Activate isaac env ────────────────────────────────────────────────────────
CONDA_INIT="${HOME}/miniforge3/etc/profile.d/conda.sh"
[[ ! -f "$CONDA_INIT" ]] && { echo "[ERROR] conda not found"; exit 1; }
# shellcheck source=/dev/null
source "$CONDA_INIT"
conda activate isaac

export OMNI_KIT_ACCEPT_EULA=Y
export OMNI_SERVER_SEARCH_TIMEOUT=1
export OMNI_CACHE_PATH="${REPO_ROOT}/.omni_cache"
export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"

PYTHON="${CONDA_PREFIX}/bin/python"

# ── Locate eval script ────────────────────────────────────────────────────────
EVAL_PY="${SCRIPT_DIR}/eval_yahboom.py"
if [[ ! -f "$EVAL_PY" ]]; then
    echo "[ERROR] eval_yahboom.py not found: $EVAL_PY"
    echo "  This evaluation entry-point needs to be created (see README_TRAINING.md)."
    echo "  It should follow the pattern of fleet_safe_vla/envs/isaaclab/eval.py"
    exit 1
fi

# ── Build command ─────────────────────────────────────────────────────────────
CMD=("$PYTHON" "$EVAL_PY"
     "task=$TASK"
     "checkpoint=$CHECKPOINT"
     "num_envs=$NUM_ENVS"
     "headless=$HEADLESS"
     "log_dir=$EVAL_LOG"
)

$RECORD_VIDEO && CMD+=("video=true" "video_length=200" "video_interval=1")
CMD+=("${EXTRA_ARGS[@]}")

echo "[INFO] Command:"
echo "  ${CMD[*]}"
echo ""

# ── Tip: stream telemetry to dashboard ───────────────────────────────────────
if ! fuser 8765/tcp &>/dev/null 2>&1; then
    echo "[TIP] Isaac bridge not running. For live dashboard telemetry, run in another terminal:"
    echo "  ./scripts/isaaclab/run_yahboom_bridge.sh --headless"
    echo ""
fi

exec "${CMD[@]}"
