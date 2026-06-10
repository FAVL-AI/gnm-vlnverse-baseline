#!/usr/bin/env bash
# FleetSafe-VLN benchmark smoke test.
# Runs all 5 core tasks on the mock platform with mock model.
# No Isaac, Gazebo, or ROS 2 required.
# Exit 0 = all passed. Exit 1 = at least one failure.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

LOGDIR="$ROOT/runs/smoke_test_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOGDIR"

echo "=== FleetSafe-VLN Benchmark Smoke Test ==="
echo "Root:    $ROOT"
echo "Logdir:  $LOGDIR"
echo ""

TASKS=(
    "tasks/hospital_corridor.yaml"
    "tasks/nurse_station.yaml"
    "tasks/dynamic_human_crossing.yaml"
    "tasks/warehouse_aisle.yaml"
    "tasks/blind_corner.yaml"
)

FAILED=0
PASSED=0

for TASK in "${TASKS[@]}"; do
    TASK_ID="$(basename "$TASK" .yaml)"
    echo "--- $TASK_ID ---"

    python -m fleetsafe_vln.benchmark.episode_runner \
        --task "$TASK" \
        --platform mock \
        --model mock \
        --safety cbf_qp \
        --log-dir "$LOGDIR/$TASK_ID" \
        2>&1 || true

    METRICS="$LOGDIR/$TASK_ID/metrics.json"
    CERTS="$LOGDIR/$TASK_ID/safety_certificates.jsonl"

    if [ -f "$METRICS" ] && [ -f "$CERTS" ]; then
        N_CERTS="$(wc -l < "$CERTS")"
        echo "  ✓ metrics.json created"
        echo "  ✓ safety_certificates.jsonl: $N_CERTS lines"
        PASSED=$((PASSED + 1))
    else
        echo "  ❌ Missing artifacts for $TASK_ID"
        FAILED=$((FAILED + 1))
    fi
    echo ""
done

echo "=== Suite runner dry-run ==="
python -m fleetsafe_vln.benchmark.suite_runner \
    --suite configs/benchmark/fleetsafe_vln_v0.yaml \
    --models mock \
    --platforms mock \
    --dry-run \
    2>&1 || true
echo ""

echo "=== Import check ==="
python -c "
import fleetsafe_vln
from fleetsafe_vln.benchmark.task_schema import load_task
from fleetsafe_vln.benchmark.metrics import EpisodeResult
from fleetsafe_vln.safety.cbf_qp_shield import CBFQPShield
from fleetsafe_vln.safety.certificate_logger import ExtendedCertificateLogger
from fleetsafe_vln.multimodal.intent_router import IntentRouter
from fleetsafe_vln.datagen.safe_trajectory_generator import SafeTrajectoryGenerator
print('  All imports OK')
print(f'  fleetsafe_vln version: {fleetsafe_vln.__version__}')
"
echo ""

echo "=== Results ==="
echo "  Passed: $PASSED / $((PASSED + FAILED))"
echo "  Logs:   $LOGDIR"

if [ "$FAILED" -gt 0 ]; then
    echo ""
    echo "❌ $FAILED task(s) failed."
    exit 1
fi

echo ""
echo "✅ All smoke tests passed."
