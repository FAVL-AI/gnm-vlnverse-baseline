#!/usr/bin/env bash
# scripts/run_iamgoodnavigator_smoke_test.sh
# ─────────────────────────────────────────────────────────────────────────────
# Smoke test for the IAmGoodNavigator integration.
#
# Phase 1 (always) — import and introspection tests
# Phase 2 (if Isaac topics live) — run a demo episode
#
# Usage:
#   bash scripts/run_iamgoodnavigator_smoke_test.sh
#   bash scripts/run_iamgoodnavigator_smoke_test.sh --scene warehouse_aisle
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCENE="hospital_corridor"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --scene) SCENE="$2"; shift 2 ;;
    *) echo "[WARN] Unknown arg: $1"; shift ;;
  esac
done

LOGDIR="${REPO_ROOT}/runs/iang_smoke_$(date +%Y%m%d_%H%M%S)"
mkdir -p "${LOGDIR}"

source "${REPO_ROOT}/scripts/visualnav/activate_visualnav_env.sh" 2>/dev/null || \
  export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"

echo "========================================"
echo "  FleetSafe — IAmGoodNavigator Smoke Test"
echo "========================================"
echo "  Scene:   ${SCENE}"
echo "  Log dir: ${LOGDIR}"
echo ""

PASS_COUNT=0
FAIL_COUNT=0

# ── Phase 1: Import and introspection ─────────────────────────────────────
echo "--- Phase 1: Import and introspection ---"
python3 - <<PYEOF
import sys
sys.path.insert(0, "${REPO_ROOT}")

from fleetsafe_vln.datagen.iamgoodnavigator_adapter import (
    is_available, setup_status, find_downloaded_scenes, list_demo_tasks,
)

status = setup_status()
tasks = list_demo_tasks()

print(f"  is_available():      {is_available()}")
print(f"  downloaded scenes:   {status['scene_count']}")
print(f"  demo tasks listed:   {len(tasks)}")
print(f"  ready_for_demo:      {status['ready_for_demo']}")
if tasks:
    print(f"  first task id:       {tasks[0]['task_id']}")
print("  [PASS] introspection")
PYEOF
PASS_COUNT=$((PASS_COUNT + 1))

echo ""

# ── Phase 2: Live Isaac demo (requires Isaac Sim + ROS 2) ─────────────────
echo "--- Phase 2: Live Isaac Sim demo ---"

ISAAC_TOPICS_OK=0
if command -v ros2 >/dev/null 2>&1; then
  python3 - <<PYEOF || ISAAC_TOPICS_OK=$?
import sys
sys.path.insert(0, "${REPO_ROOT}")
from fleetsafe_vln.sim.isaac_adapter import check_ros2_topics, print_topic_report
all_ok, status = check_ros2_topics(timeout_s=5.0)
print_topic_report(status)
sys.exit(0 if all_ok else 2)
PYEOF
else
  ISAAC_TOPICS_OK=2
fi

if [[ "${ISAAC_TOPICS_OK}" -eq 0 ]]; then
  EP_DIR="${LOGDIR}/iang_${SCENE}"
  echo "  Isaac topics live. Running IAmGoodNavigator demo..."
  python3 - <<PYEOF
import sys, json
sys.path.insert(0, "${REPO_ROOT}")
from fleetsafe_vln.datagen.iamgoodnavigator_adapter import run_demo_episode
result = run_demo_episode("${SCENE}", "${EP_DIR}", timeout_s=90.0)
print(json.dumps(result, indent=2))
if not result.get("success"):
    sys.exit(1)
PYEOF
  PASS_COUNT=$((PASS_COUNT + 1))
  echo "  [PASS] live demo episode"
else
  echo "  Isaac Sim not live — skipping live demo phase."
  echo "  Start Isaac Sim + ROS 2 bridge and re-run to test Phase 2."
fi

echo ""
echo "========================================"
echo "  Results: ${PASS_COUNT} passed, ${FAIL_COUNT} failed"
echo "========================================"

if [[ "${FAIL_COUNT}" -gt 0 ]]; then
  echo "  Check imports: python -c 'from fleetsafe_vln.datagen.iamgoodnavigator_adapter import is_available'"
  exit 1
fi

echo "Smoke test passed."
