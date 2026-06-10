#!/bin/bash
# Fleet-Safe-VLA-OS — Yahboom M3Pro Isaac Lab RL Training
#
# DO NOT RUN until M3Pro assets pass Stage 0 validation.
# This script will fail with a clear asset checklist if the URDF is missing.
#
# Usage:
#   ./scripts/isaaclab/train_yahboom.sh --stage 0            # asset validation only
#   ./scripts/isaaclab/train_yahboom.sh --stage 1            # vel tracking (requires URDF)
#   ./scripts/isaaclab/train_yahboom.sh --stage 2            # waypoint nav
#   ./scripts/isaaclab/train_yahboom.sh --stage 3            # obstacle avoidance
#   ./scripts/isaaclab/train_yahboom.sh --stage 4            # Fleet-Safe CBF
#   ./scripts/isaaclab/train_yahboom.sh --stage 5            # mimic / imitation
#
#   # With extra Isaac Lab args:
#   ./scripts/isaaclab/train_yahboom.sh --stage 1 --num-envs 512
#   ./scripts/isaaclab/train_yahboom.sh --stage 1 --resume --checkpoint logs/...
#   ./scripts/isaaclab/train_yahboom.sh --stage 1 --headless false   # show GUI
#
# Training stages:
#   Stage 0 — Asset validation (no GPU, runs in <5 s)
#   Stage 1 — Random cmd_vel tracking on flat ground
#             obs=39  act=3  envs=1024  ~2-3h RTX 4080 SUPER
#   Stage 2 — Waypoint navigation + goal reward
#             obs=42  act=3  envs=1024  ~3-4h  (warm-starts Stage 1)
#   Stage 3 — Obstacle avoidance + lidar obs
#             obs=402 act=3  envs=2048  ~6-8h  (warm-starts Stage 2)
#   Stage 4 — Fleet-Safe CBF safety layer
#             obs=405 act=3  envs=1024  ~3h    (fine-tune Stage 3)
#   Stage 5 — Imitation/mimic from real ROS2 bags  [INFRASTRUCTURE PENDING]
#
# Log output: logs/isaaclab/yahboom_m3pro/stage<N>/
# Checkpoints saved every 100 iterations.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

STAGE=0
NUM_ENVS=""
RESUME=false
CHECKPOINT=""
HEADLESS="true"
EXTRA_ARGS=()

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --stage)         STAGE="$2";      shift 2 ;;
        --stage=*)       STAGE="${1#--stage=}"; shift ;;
        --num-envs)      NUM_ENVS="$2";   shift 2 ;;
        --num-envs=*)    NUM_ENVS="${1#--num-envs=}"; shift ;;
        --resume)        RESUME=true;     shift ;;
        --checkpoint)    CHECKPOINT="$2"; shift 2 ;;
        --checkpoint=*)  CHECKPOINT="${1#--checkpoint=}"; shift ;;
        --headless)      HEADLESS="$2";   shift 2 ;;
        --headless=*)    HEADLESS="${1#--headless=}"; shift ;;
        *)               EXTRA_ARGS+=("$1"); shift ;;
    esac
done

echo "============================================================"
echo "  Fleet-Safe-VLA-OS  |  Yahboom M3Pro Isaac Lab Training"
echo "  Stage   : $STAGE"
echo "  Headless: $HEADLESS"
[[ -n "$NUM_ENVS" ]] && echo "  Envs    : $NUM_ENVS"
echo "============================================================"
echo ""

# ── Stage 0: asset validation (no Isaac Sim needed) ──────────────────────────
M3PRO_URDF="${REPO_ROOT}/fleet_safe_vla/robots/yahboom/m3pro/urdf/yahboom_m3pro.urdf"
M3PRO_MJCF="${REPO_ROOT}/fleet_safe_vla/robots/yahboom/m3pro/mjcf/yahboom_m3pro.xml"
OBS_ADAPTER="${REPO_ROOT}/fleet_safe_vla/robots/yahboom/controllers/obs_adapter_m3pro.py"
CONTRACT="${REPO_ROOT}/fleet_safe_vla/robots/yahboom/config/robot_contract_m3pro.yaml"

echo "=== Stage 0: Asset Validation ==="
ASSETS_OK=true

check_asset() {
    local path="$1" label="$2" required="$3"
    if [[ -f "$path" ]]; then
        echo "  ✓  $label"
    elif [[ "$required" == "required" ]]; then
        echo "  ✗  $label  ← REQUIRED (training will not start)"
        ASSETS_OK=false
    else
        echo "  ?  $label  ← not yet created (needed for Stage $required)"
    fi
}

check_asset "$M3PRO_URDF"    "yahboom_m3pro.urdf         (robot body + joints)"      "required"
check_asset "$M3PRO_MJCF"    "yahboom_m3pro.xml          (MuJoCo validation)"        "2"
check_asset "$OBS_ADAPTER"   "obs_adapter_m3pro.py       (mecanum kinematics)"       "required"

# USD cache (auto-generated on first Isaac Sim run — not user-created)
USD_CACHE="${REPO_ROOT}/fleet_safe_vla/robots/yahboom/m3pro/usd"
if [[ -d "$USD_CACHE" ]]; then
    echo "  ✓  USD cache                 ($USD_CACHE)"
else
    echo "  ─  USD cache                 (auto-generated on first Isaac Sim run)"
fi

echo ""
echo "  Contract : $CONTRACT"
echo ""

if [[ "$STAGE" -eq 0 ]]; then
    if $ASSETS_OK; then
        echo "  All required assets found."
        echo "  Ready to train Stage 1:"
        echo "    $0 --stage 1"
    else
        echo "  Asset validation FAILED."
        echo ""
        echo "  To create M3Pro assets, see:"
        echo "    $CONTRACT"
        echo ""
        echo "  Quickstart checklist:"
        echo "  1. Build the URDF from Yahboom CAD:"
        echo "     → fleet_safe_vla/robots/yahboom/m3pro/urdf/yahboom_m3pro.urdf"
        echo "     4 joints: fl/fr/rl/rr_wheel_joint (type=continuous)"
        echo ""
        echo "  2. Implement mecanum inverse kinematics:"
        echo "     → fleet_safe_vla/robots/yahboom/controllers/obs_adapter_m3pro.py  (already exists)"
        echo "     Formula: fl=(vx-vy-(lx+ly)*wz)/r  [see contract YAML]"
        echo ""
        echo "  3. Re-run Stage 0 to re-validate:"
        echo "     $0 --stage 0"
    fi
    exit 0
fi

# ── Stages 1–5 require URDF ───────────────────────────────────────────────────
if ! $ASSETS_OK; then
    echo ""
    echo "[ERROR] Required assets are missing. Cannot start Isaac Lab training."
    echo "  Run Stage 0 first to see the asset checklist:"
    echo "    $0 --stage 0"
    exit 1
fi

# ── Stage 2+ requires MJCF for MuJoCo validation ─────────────────────────────
if [[ "$STAGE" -ge 2 ]]; then
    if [[ ! -f "$M3PRO_MJCF" ]]; then
        echo ""
        echo "[ERROR] Stage $STAGE requires the M3Pro MJCF (MuJoCo validation)."
        echo "  Missing: $M3PRO_MJCF"
        echo ""
        echo "  Validate the MJCF first:"
        echo "    python scripts/yahboom/validate_m3pro_mjcf.py"
        echo "  Then re-run Stage 0:"
        echo "    $0 --stage 0"
        exit 1
    fi
fi

# ── Map stage → task name ─────────────────────────────────────────────────────
case "$STAGE" in
    1) TASK="FleetSafe-M3Pro-VelTracking-v0"   ;;
    2) TASK="FleetSafe-M3Pro-WaypointNav-v0"   ;;
    3) TASK="FleetSafe-M3Pro-Obstacles-v0"     ;;
    4) TASK="FleetSafe-M3Pro-FleetSafe-v0"     ;;
    5) TASK="FleetSafe-M3Pro-Mimic-v0"         ;;
    *)
        echo "[ERROR] Unknown stage: $STAGE  (valid: 0–5)"
        exit 1 ;;
esac

LOG_DIR="${REPO_ROOT}/logs/isaaclab/yahboom_m3pro/stage${STAGE}"

echo "[INFO] Task     : $TASK"
echo "[INFO] Log dir  : $LOG_DIR"
echo ""

# ── Stage 5: additional check for ROS2 bags ───────────────────────────────────
if [[ "$STAGE" -eq 5 ]]; then
    BAGS_DIR="${REPO_ROOT}/data/episodes/real"
    echo "[WARN] Stage 5 requires real ROS2 bag files in: $BAGS_DIR"
    echo "       Collect them with: ./scripts/real_robot/record_episode.sh"
    echo "       The BC/mimic training infrastructure is NOT YET implemented."
    echo "       This stage will fail inside Isaac Lab until it is built."
    echo ""
fi

# ── Activate isaac conda env ──────────────────────────────────────────────────
CONDA_INIT="${HOME}/miniforge3/etc/profile.d/conda.sh"
if [[ ! -f "$CONDA_INIT" ]]; then
    echo "[ERROR] conda not found at $CONDA_INIT"
    exit 1
fi
# shellcheck source=/dev/null
source "$CONDA_INIT"
conda activate isaac

export OMNI_KIT_ACCEPT_EULA=Y
export OMNI_SERVER_SEARCH_TIMEOUT=1
export OMNI_CACHE_PATH="${REPO_ROOT}/.omni_cache"
export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"

PYTHON="${CONDA_PREFIX}/bin/python"

# ── Build command ─────────────────────────────────────────────────────────────
TRAIN_PY="${SCRIPT_DIR}/train_yahboom.py"
if [[ ! -f "$TRAIN_PY" ]]; then
    echo "[ERROR] train_yahboom.py not found: $TRAIN_PY"
    echo "  This training entry-point needs to be created (see README_TRAINING.md)."
    echo "  It should follow the pattern of fleet_safe_vla/envs/isaaclab/train.py"
    exit 1
fi

CMD=("$PYTHON" "$TRAIN_PY"
     "task=$TASK"
     "headless=$HEADLESS"
     "log_dir=$LOG_DIR"
)

[[ -n "$NUM_ENVS" ]]   && CMD+=("num_envs=$NUM_ENVS")
$RESUME                && CMD+=("resume=true")
[[ -n "$CHECKPOINT" ]] && CMD+=("checkpoint=$CHECKPOINT")
CMD+=("${EXTRA_ARGS[@]}")

echo "[INFO] Command:"
echo "  ${CMD[*]}"
echo ""
echo "[INFO] Starting Isaac Sim (first run takes ~3 min for USD conversion)..."
echo ""

exec "${CMD[@]}"
