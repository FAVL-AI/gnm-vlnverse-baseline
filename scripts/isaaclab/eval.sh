#!/bin/bash
# Fleet-Safe H1 Isaac Lab Evaluation Script
# Usage: ./scripts/isaaclab/eval.sh task=FleetSafe-H1-RoughLocomotion-v0 checkpoint=logs/best.pt

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== Fleet-Safe-VLA-OS Isaac Lab Evaluation ==="

source ~/miniforge3/etc/profile.d/conda.sh
conda activate isaac
export OMNI_KIT_ACCEPT_EULA=Y
export PYTHONPATH="$REPO_ROOT:$PYTHONPATH"

cd "$REPO_ROOT"
"${CONDA_PREFIX:-$HOME/miniforge3/envs/isaac}/bin/python" fleet_safe_vla/envs/isaaclab/eval.py "$@"
