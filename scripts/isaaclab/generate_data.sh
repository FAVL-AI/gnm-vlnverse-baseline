#!/bin/bash
# Generate synthetic episode data from MuJoCo (no Isaac GPU needed for quick runs).
# For Isaac Lab GPU: swap the python script below to fleet_safe_vla/envs/isaaclab/generate_data.py
# Usage: ./scripts/isaaclab/generate_data.sh task=FleetSafe-Yahboom-SafePath-v0 episodes=100

set -e
EPISODES=${1:-100}
TASK=${2:-safe_path}
OUTPUT=${3:-data/episodes/sim}
SEED=${4:-42}
BACKBONE=${5:-D_fleet_safe}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source ~/miniforge3/etc/profile.d/conda.sh && conda activate isaac 2>/dev/null || true
PYTHON="${CONDA_PREFIX:-$HOME/miniforge3/envs/isaac}/bin/python"

echo "=== Fleet-Safe Yahboom Data Generator ==="
echo "Task: $TASK | Episodes: $EPISODES | Backbone: $BACKBONE | Output: $OUTPUT"

export PYTHONPATH="$REPO_ROOT:$PYTHONPATH"

"$PYTHON" - <<EOF
import sys, numpy as np
sys.path.insert(0, "$REPO_ROOT")

from fleet_safe_vla.envs.mujoco.yahboom.safe_path_env import YahboomSafePathEnv
from fleet_safe_vla.envs.mujoco.yahboom.recovery_env import YahboomRecoveryEnv
from fleet_safe_vla.policies.nominal.nominal_planner import NominalGoToGoalPlanner
from fleet_safe_vla.fleet_safety.yahboom_cbf import YahboomCBFFilter, YahboomCBFConfig
from fleet_safe_vla.data_recorder.episode_recorder import DatasetGenerator

task = "$TASK"
env_cls = YahboomRecoveryEnv if task == "recovery" else YahboomSafePathEnv

planner = NominalGoToGoalPlanner()
cbf = YahboomCBFFilter(YahboomCBFConfig()) if "$BACKBONE" == "D_fleet_safe" else None

gen = DatasetGenerator(
    env_factory=lambda seed: env_cls(seed=seed, max_episode_steps=300),
    policy_fn=planner,
    cbf_filter=cbf,
    output_dir="$OUTPUT",
    n_episodes=$EPISODES,
    seed=$SEED,
    verbose=True,
)
dirs = gen.run()
print(f"Generated {len(dirs)} episodes in $OUTPUT")
EOF
