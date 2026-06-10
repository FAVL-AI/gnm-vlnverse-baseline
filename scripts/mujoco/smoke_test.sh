#!/bin/bash
# MuJoCo smoke test — no GPU needed
# Usage: ./scripts/mujoco/smoke_test.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== Fleet-Safe MuJoCo Smoke Test ==="

# Activate isaac conda env
source ~/miniforge3/etc/profile.d/conda.sh 2>/dev/null || true
conda activate isaac 2>/dev/null || true
PYTHON="${CONDA_PREFIX:-$HOME/miniforge3/envs/isaac}/bin/python"
[[ -x "$PYTHON" ]] || PYTHON="$(which python3)"

export PYTHONPATH="$REPO_ROOT:$PYTHONPATH"

"$PYTHON" -c "
from fleet_safe_vla.envs.mujoco.h1_mujoco_env import H1MuJoCoEnv
import numpy as np

print('Creating H1MuJoCoEnv...')
env = H1MuJoCoEnv(max_episode_steps=100)

print('Resetting...')
result = env.reset(seed=42)
if isinstance(result, tuple):
    obs, info = result
else:
    obs = result

print(f'  obs shape: {obs.shape}')
assert obs.shape == (45,), f'Expected obs (45,), got {obs.shape}'

print('Running 10 steps with random actions...')
total_reward = 0.0
for i in range(10):
    action = env.action_space.sample()
    result = env.step(action)
    if len(result) == 5:
        obs, rew, terminated, truncated, info = result
        done = terminated or truncated
    else:
        obs, rew, done, info = result
    total_reward += rew
    print(f'  step {i+1}: rew={rew:.3f}, height={info[\"base_height_m\"]:.3f}')
    if done:
        print(f'  Episode ended at step {i+1}')
        break

env.close()
print(f'MuJoCo smoke test PASSED. Total reward: {total_reward:.3f}')
"
