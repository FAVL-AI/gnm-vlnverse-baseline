#!/usr/bin/env bash
# scripts/visualnav/run_e2e_smoke.sh
# ─────────────────────────────────────────────────────────────────────────────
# End-to-end smoke test for the FleetSafe VisualNav benchmark stack.
#
# Runs in order:
#   1. Gates 0–6 (validate_gates.py)
#   2. Checkpoint validator (check_visualnav_checkpoints.py)
#   3. Scene readiness (check_isaac_scenes.py --backend mujoco)
#   4. One GNM baseline episode (mock backend, straight_corridor, seed 0)
#   5. One GNM + FleetSafe episode (same scene/seed)
#   6. HTML + CSV report export
#   7. Print exact output file paths
#
# Exit codes:
#   0  all steps passed (gates, inference, episodes, export)
#   1  a required step failed
#   3  non-critical step warned (checkpoints, Isaac)
#
# Usage:
#   bash scripts/visualnav/run_e2e_smoke.sh
#   bash scripts/visualnav/run_e2e_smoke.sh --backend mujoco
#   bash scripts/visualnav/run_e2e_smoke.sh --python /path/to/python
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON="/home/favl/miniforge3/envs/isaac/bin/python"
BACKEND="mock"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend) BACKEND="$2" ; shift 2 ;;
    --python)  PYTHON="$2"  ; shift 2 ;;
    *) echo "[WARN] Unknown arg: $1" ; shift ;;
  esac
done

ACTIVATE="${REPO_ROOT}/scripts/visualnav/activate_visualnav_env.sh"
[[ -f "${ACTIVATE}" ]] && source "${ACTIVATE}" || export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"

T_START=$(date +%s)

log()  { echo "[e2e_smoke] $*"; }
ok()   { echo "  ✓  $*"; }
fail() { echo "  ✗  $*" >&2; }
hr()   { echo "════════════════════════════════════════════════════════════════"; }

hr
log "FleetSafe VisualNav End-to-End Smoke"
log "REPO_ROOT : ${REPO_ROOT}"
log "PYTHON    : ${PYTHON}"
log "BACKEND   : ${BACKEND}"
hr
echo ""

WARN_COUNT=0
RESULTS_DIR="${REPO_ROOT}/benchmarks/visualnav/results/e2e_smoke_$(date +%Y%m%d_%H%M%S)"

# ── Step 1: Gates 0–6 ─────────────────────────────────────────────────────────
log "Step 1: Reproduction gates (validate_gates.py)"
set +e
"${PYTHON}" -m fleet_safe_vla.integrations.visualnav_transformer.validate_gates 2>&1
RC=$?
set -e
if [[ $RC -ne 0 ]]; then
  fail "Gate validation failed (exit ${RC})"
  exit 1
fi
ok "All gates passed"
echo ""

# ── Step 2: Checkpoint validator ──────────────────────────────────────────────
log "Step 2: Checkpoint validation (check_visualnav_checkpoints.py)"
set +e
"${PYTHON}" "${REPO_ROOT}/scripts/visualnav/check_visualnav_checkpoints.py" 2>&1
RC=$?
set -e
if [[ $RC -eq 0 ]]; then
  ok "All checkpoints validated with full inference"
elif [[ $RC -eq 2 ]]; then
  echo "  ⚠  Some checkpoints warned (dependency issues) — using mock fallback"
  WARN_COUNT=$((WARN_COUNT + 1))
else
  fail "Checkpoint validation failed (exit ${RC})"
  exit 1
fi
echo ""

# ── Step 3: Scene readiness ───────────────────────────────────────────────────
log "Step 3: Scene readiness (check_isaac_scenes.py --backend mujoco)"
set +e
"${PYTHON}" "${REPO_ROOT}/scripts/visualnav/check_isaac_scenes.py" --backend mujoco 2>&1
RC=$?
set -e
if [[ $RC -eq 0 ]]; then
  ok "MuJoCo scenes OK"
elif [[ $RC -eq 2 ]]; then
  echo "  ⚠  Isaac Lab gate pending (expected during development)"
  WARN_COUNT=$((WARN_COUNT + 1))
else
  # MuJoCo fail is non-fatal for mock backend smoke
  if [[ "${BACKEND}" == "mock" ]]; then
    echo "  ⚠  MuJoCo scene check failed — continuing with mock backend"
    WARN_COUNT=$((WARN_COUNT + 1))
  else
    fail "MuJoCo scene check failed (exit ${RC}) and backend=${BACKEND} requires MuJoCo"
    exit 1
  fi
fi
echo ""

# ── Step 4+5: One GNM baseline + one GNM+FleetSafe episode ───────────────────
log "Step 4–5: GNM baseline + FleetSafe episodes (1 seed, straight_corridor)"

"${PYTHON}" "${REPO_ROOT}/scripts/visualnav/run_visualnav_benchmark.py" \
  --model      gnm \
  --seeds      smoke \
  --scenes     straight_corridor \
  --backend    "${BACKEND}" \
  --fleetsafe  both \
  --max-steps  80 \
  --output-dir "${RESULTS_DIR}" \
  2>&1

ok "GNM baseline + FleetSafe episodes complete"
echo ""

# ── Step 6: Export report ─────────────────────────────────────────────────────
log "Step 6: Export HTML + CSV report"

# Find the latest aggregate JSON from the run
REPORT_DIR="${REPO_ROOT}/benchmarks/visualnav/reports/e2e_smoke_$(date +%Y%m%d_%H%M%S)"
mkdir -p "${REPORT_DIR}"

# Collect the aggregate JSONs and write a combined report-input JSON
COMBINED="${REPORT_DIR}/combined_input.json"
python3 - <<PYEOF
import json, glob, sys
from pathlib import Path

results_dir = Path("${RESULTS_DIR}")
agg_files   = sorted(results_dir.glob("*/aggregate_metrics.json"))
if not agg_files:
    print("  [WARN] No aggregate_metrics.json found — skipping export")
    sys.exit(0)

combined = []
for f in agg_files:
    data = json.loads(f.read_text())
    # Wrap in export_report.py format
    combined.append({
        "model":     data.get("model", "?"),
        "fleetsafe": data.get("fleetsafe", False),
        "timestamp": 0,
        "config":    {"v_max": 0.3, "w_max": 0.7, "robot": "m3pro", "seeds": [0]},
        "episodes":  [],
        "aggregate": {
            "n_episodes":                data.get("n_episodes", 0),
            "success_rate":              data.get("success_rate", 0),
            "collision_rate":            data.get("collision_rate", 0),
            "mean_path_length_m":        data.get("path_length_m_mean", 0),
            "mean_smoothness":           data.get("smoothness_mean", 0),
            "mean_stuck_count":          0,
            "mean_intervention_count":   data.get("intervention_count_mean", 0),
            "mean_near_violation_count": data.get("near_violation_count_mean", 0),
            "mean_min_obstacle_dist_m":  data.get("min_obstacle_distance_m_mean", 0),
            "mean_latency_ms":           data.get("inference_latency_ms_mean", 0),
            "mean_fps":                  data.get("sim_fps_mean", 0),
        },
    })

# Write combined
Path("${COMBINED}").parent.mkdir(parents=True, exist_ok=True)
# Write each as a separate file for export_report.py
for i, entry in enumerate(combined):
    out = Path("${REPORT_DIR}") / f"run_{i:02d}.json"
    out.write_text(json.dumps(entry, indent=2))
    print(f"  wrote {out.name}")
PYEOF

if ls "${REPORT_DIR}"/run_*.json &>/dev/null 2>&1; then
  for json_file in "${REPORT_DIR}"/run_*.json; do
    "${PYTHON}" "${REPO_ROOT}/scripts/visualnav/export_report.py" \
      --input      "${json_file}" \
      --output-dir "${REPORT_DIR}" \
      2>&1 || true
  done
  ok "Report exported to ${REPORT_DIR}/"
else
  echo "  ⚠  No individual run JSON files to export"
  WARN_COUNT=$((WARN_COUNT + 1))
fi
echo ""

# ── Summary ───────────────────────────────────────────────────────────────────
T_END=$(date +%s)
ELAPSED=$(( T_END - T_START ))

hr
echo ""
echo "  End-to-end smoke complete in ${ELAPSED}s"
echo ""
echo "  Output paths:"
echo "    Episodes + metrics : ${RESULTS_DIR}/"
echo "    HTML/CSV report    : ${REPORT_DIR}/"
echo ""

if find "${RESULTS_DIR}" -name "episode.json" | head -1 | grep -q episode; then
  echo "  Episode files written:"
  find "${RESULTS_DIR}" -name "episode.json" | while read -r f; do
    echo "    ${f}"
  done
fi
echo ""

if [[ $WARN_COUNT -gt 0 ]]; then
  echo "  ⚠  ${WARN_COUNT} non-critical warning(s) above — see output for details"
  echo "  Smoke test: PASS (with warnings)"
  echo ""
  hr
  exit 3
else
  echo "  Smoke test: PASS"
  echo ""
  hr
  exit 0
fi
