#!/bin/bash
# Run the Yahboom safety benchmark (all 4 backbones).
# No GPU required — uses MuJoCo.
# Usage: ./scripts/yahboom/run_benchmark.sh [n_episodes] [seed]

set -e
N_EPISODES=${1:-50}
SEED=${2:-42}
TASK=${3:-safe_path}
OUTPUT=${4:-logs/yahboom/benchmark_$(date +%Y%m%d_%H%M%S).json}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source ~/miniforge3/etc/profile.d/conda.sh && conda activate isaac 2>/dev/null || true
PYTHON="${CONDA_PREFIX:-$HOME/miniforge3/envs/isaac}/bin/python"

mkdir -p "$(dirname "$OUTPUT")"
echo "=== Fleet-Safe Yahboom Safety Benchmark ==="
echo "Episodes: $N_EPISODES | Seed: $SEED | Task: $TASK"
echo "Output: $OUTPUT"

export PYTHONPATH="$REPO_ROOT:$PYTHONPATH"

"$PYTHON" - <<EOF
import sys
sys.path.insert(0, "$REPO_ROOT")

from fleet_safe_vla.benchmarks.yahboom_benchmark import YahboomBenchmark

bench = YahboomBenchmark(n_episodes=$N_EPISODES, seed=$SEED, task="$TASK", verbose=True)
results = bench.run()
bench.print_report(results)
bench.save_report(results, "$OUTPUT")
EOF

echo ""
echo "[benchmark] Done. Report: $OUTPUT"
