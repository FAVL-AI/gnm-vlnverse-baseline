#!/bin/bash
# Fleet-Safe H1 Isaac Lab Training Script
# Usage: ./scripts/isaaclab/train.sh task=FleetSafe-H1-RoughLocomotion-v0 num_envs=4096
#
# Additional args are passed directly to the train.py script:
#   ./scripts/isaaclab/train.sh task=FleetSafe-H1-RoughLocomotion-v0 headless=true
#   ./scripts/isaaclab/train.sh task=FleetSafe-H1-FlatLocomotion-v0 num_envs=2048

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== Fleet-Safe-VLA-OS Isaac Lab Training ==="
echo "Repo: $REPO_ROOT"
echo "Args: $@"

# Activate conda environment
source ~/miniforge3/etc/profile.d/conda.sh
conda activate isaac

# Isaac Sim EULA acceptance
export OMNI_KIT_ACCEPT_EULA=Y

# Set Python path to include repo
export PYTHONPATH="$REPO_ROOT:$PYTHONPATH"

# Run training
cd "$REPO_ROOT"
"${CONDA_PREFIX:-$HOME/miniforge3/envs/isaac}/bin/python" fleet_safe_vla/envs/isaaclab/train.py "$@"
