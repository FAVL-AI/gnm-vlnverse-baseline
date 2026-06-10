#!/usr/bin/env bash
# scripts/run_gnm_isaac_smoke_test.sh
# ─────────────────────────────────────────────────────────────────────────────
# GNM + FleetSafe smoke test — Manual section 0, step 5 (working step)
#
# Runs in two phases:
#   Phase 1 (always runs)  — mock platform, GNM adapter, cbf_qp safety
#   Phase 2 (if available) — Isaac Sim platform via ROS 2 bridge
#
# Pass condition (per Manual section 10):
#   GNM adapter returns nominal action without crashing
#   CBF shield runs without error
#   metrics.json and safety_certificates.jsonl are written
#   certificate_validity_rate >= 0.90
#
# Usage:
#   bash scripts/run_gnm_isaac_smoke_test.sh
#   bash scripts/run_gnm_isaac_smoke_test.sh --skip-mock
#   bash scripts/run_gnm_isaac_smoke_test.sh --isaac-only
#   bash scripts/run_gnm_isaac_smoke_test.sh --task tasks/warehouse_aisle.yaml
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TASK="tasks/hospital_corridor.yaml"
SKIP_MOCK=false
ISAAC_ONLY=false
CERT_THRESHOLD=0.90

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-mock)   SKIP_MOCK=true;  shift ;;
    --isaac-only)  ISAAC_ONLY=true; SKIP_MOCK=true; shift ;;
    --task)        TASK="$2"; shift 2 ;;
    --cert-threshold) CERT_THRESHOLD="$2"; shift 2 ;;
    *) echo "[WARN] Unknown arg: $1"; shift ;;
  esac
done

LOGDIR="${REPO_ROOT}/runs/gnm_smoke_$(date +%Y%m%d_%H%M%S)"
mkdir -p "${LOGDIR}"

source "${REPO_ROOT}/scripts/visualnav/activate_visualnav_env.sh" 2>/dev/null || \
  export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"

echo "========================================"
echo "  FleetSafe GNM Smoke Test"
echo "========================================"
echo "  Task:           ${TASK}"
echo "  Log dir:        ${LOGDIR}"
echo "  Cert threshold: ${CERT_THRESHOLD}"
echo ""

PASS_COUNT=0
FAIL_COUNT=0

# ── Helper: check a metrics.json for pass/fail ─────────────────────────────────
check_result() {
  local label="$1"
  local log_dir="$2"

  if [[ ! -f "${log_dir}/metrics.json" ]]; then
    echo "  [FAIL] ${label}: metrics.json not found"
    FAIL_COUNT=$((FAIL_COUNT + 1))
    return 1
  fi

  if [[ ! -f "${log_dir}/safety_certificates.jsonl" ]]; then
    echo "  [FAIL] ${label}: safety_certificates.jsonl not found"
    FAIL_COUNT=$((FAIL_COUNT + 1))
    return 1
  fi

  # Check certificate validity rate
  CERT_RATE=$(python3 - <<PYEOF
import json, pathlib, sys
p = pathlib.Path("${log_dir}/metrics.json")
d = json.loads(p.read_text())
rate = d.get("certificate_validity_rate", 0)
print(f"{rate:.4f}")
PYEOF
)

  CERT_OK=$(python3 -c "print('yes' if float('${CERT_RATE}') >= ${CERT_THRESHOLD} else 'no')")

  if [[ "${CERT_OK}" == "yes" ]]; then
    SUCCESS=$(python3 -c "import json; d=json.load(open('${log_dir}/metrics.json')); print('✓' if d.get('success') else '✗')")
    CBF=$(python3 -c "import json; d=json.load(open('${log_dir}/metrics.json')); print(d.get('cbf_intervention_count', 0))")
    echo "  [PASS] ${label}  success=${SUCCESS}  cert=${CERT_RATE}  cbf_interventions=${CBF}"
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    echo "  [FAIL] ${label}: cert_validity=${CERT_RATE} < threshold=${CERT_THRESHOLD}"
    FAIL_COUNT=$((FAIL_COUNT + 1))
    return 1
  fi
}

# ── Phase 1: Mock platform (no Isaac required) ─────────────────────────────────
if ! $SKIP_MOCK; then
  echo "--- Phase 1: Mock platform ---"

  # Test all three safety modes
  for SAFETY in none log_only cbf_qp; do
    EP_DIR="${LOGDIR}/mock_gnm_${SAFETY}"
    python3 -m fleetsafe_vln.benchmark.episode_runner \
      --task "${TASK}" \
      --platform mock \
      --model gnm \
      --safety "${SAFETY}" \
      --log-dir "${EP_DIR}" \
      2>&1 | tail -4 || true
    check_result "mock/gnm/${SAFETY}" "${EP_DIR}" || true
  done

  # Also test that GNMAdapter can be imported and reports its status
  echo ""
  echo "--- GNM adapter status ---"
  python3 - <<PYEOF
import sys
sys.path.insert(0, "${REPO_ROOT}")
from fleetsafe_vln.backbones.gnm_adapter import GNMAdapter
adapter = GNMAdapter()
available = GNMAdapter.is_available()
print(f"  GNMAdapter instantiated  ok=True")
print(f"  GNM checkpoint available: {available}")
if not available:
    print("  (Run 'make gnm-setup' to clone visualnav-transformer and download weights)")
PYEOF
  echo ""
fi

# ── Phase 2: Isaac platform (requires ROS 2 bridge) ────────────────────────────
echo "--- Phase 2: Isaac Sim platform ---"

# Check if ROS 2 is available
if command -v ros2 >/dev/null 2>&1; then
  echo "  ROS 2 found. Checking required topics (5 s timeout)..."

  # Python exits 0 = all topics OK; 2 = topics missing (skip, not failure)
  ISAAC_TOPICS_OK=0
  python3 - <<PYEOF || ISAAC_TOPICS_OK=$?
import sys
sys.path.insert(0, "${REPO_ROOT}")
from fleetsafe_vln.sim.isaac_adapter import check_ros2_topics, REQUIRED_TOPICS, print_topic_report

all_ok, status = check_ros2_topics(timeout_s=5.0)
print_topic_report(status)

if all_ok:
    print("  Topics OK — running Isaac Sim episode.")
    sys.exit(0)
else:
    print("  Isaac Sim not publishing all required topics.")
    print("  Start Isaac Sim + ROS 2 bridge and re-run to test Phase 2.")
    sys.exit(2)
PYEOF

  if [[ "${ISAAC_TOPICS_OK}" -eq 0 ]]; then
    EP_DIR="${LOGDIR}/isaac_gnm_log_only"
    echo ""
    echo "  Running Isaac Sim episode (log_only safety mode)..."
    python3 -m fleetsafe_vln.benchmark.episode_runner \
      --task "${TASK}" \
      --platform isaac \
      --model gnm \
      --safety log_only \
      --log-dir "${EP_DIR}" \
      2>&1 | tail -6 || true
    check_result "isaac/gnm/log_only" "${EP_DIR}" || true
  else
    echo "  Isaac Sim phase skipped (topics not available)."
  fi
else
  echo "  ROS 2 not found. Skipping Isaac Sim phase."
  echo "  Install ROS 2 Humble and start Isaac Sim to enable this phase."
fi

echo ""
echo "========================================"
echo "  Results: ${PASS_COUNT} passed, ${FAIL_COUNT} failed"
echo "  Full logs: ${LOGDIR}"
echo "========================================"
echo ""

if [[ "${FAIL_COUNT}" -gt 0 ]]; then
  echo "Next steps to fix failures:"
  echo "  - Check imports: python -c 'from fleetsafe_vln.backbones.gnm_adapter import GNMAdapter'"
  echo "  - Install deps:  pip install -e . && pip install numpy Pillow"
  echo "  - Setup GNM:     make gnm-setup"
  exit 1
fi

echo "Smoke test passed."
echo ""
echo "Next step — Isaac hospital scene:"
echo "  bash scripts/gnm/collect_gnm_data.sh --scene hospital_corridor"
echo "  python -m fleetsafe_vln.benchmark.episode_runner \\"
echo "    --platform isaac --model gnm --safety cbf_qp \\"
echo "    --task tasks/hospital_corridor.yaml \\"
echo "    --log-dir runs/gnm_isaac_cbf_$(date +%Y%m%d)"
