#!/usr/bin/env bash
# Source this file before running any VisualNav scripts.
# Usage:  source scripts/visualnav/activate_visualnav_env.sh
export PYTHONPATH="/home/favl/robotics/FleetSafe-VisualNav-Benchmark:/home/favl/robotics/FleetSafe-VisualNav-Benchmark/third_party/visualnav-transformer/train:/home/favl/robotics/FleetSafe-VisualNav-Benchmark/third_party/visualnav-transformer/train/vint_train:${PYTHONPATH:-}"
export FLEETSAFE_REPO_ROOT="/home/favl/robotics/FleetSafe-VisualNav-Benchmark"
echo "[visualnav] PYTHONPATH configured — fleet_safe_vla and upstream packages are importable."
