#!/usr/bin/env bash
# scripts/start_vlnverse_scene_demo.sh
# ─────────────────────────────────────────────────────────────────────────────
# VLNVerse-style FleetSafe Scene Demo launcher.
#
# Phase A: ensure backend + frontend are running (or start them)
# Phase B: run three episodes (baseline / log_only / cbf_qp) sequentially
# Phase C: write comparison summary
#
# Usage:
#   bash scripts/start_vlnverse_scene_demo.sh
#   bash scripts/start_vlnverse_scene_demo.sh --task tasks/VLNVerse_scene.yaml
#   bash scripts/start_vlnverse_scene_demo.sh --platform isaac
#   bash scripts/start_vlnverse_scene_demo.sh --model gnm
#   bash scripts/start_vlnverse_scene_demo.sh --no-dashboard   # skip backend/frontend
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TASK="tasks/VLNVerse_scene.yaml"
PLATFORM="mock"
MODEL="gnm"
NO_DASHBOARD=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --task)         TASK="$2";     shift 2 ;;
    --platform)     PLATFORM="$2"; shift 2 ;;
    --model)        MODEL="$2";    shift 2 ;;
    --no-dashboard) NO_DASHBOARD=true; shift ;;
    *) echo "[WARN] Unknown arg: $1"; shift ;;
  esac
done

# ── Timestamps and directories ────────────────────────────────────────────
TS="$(date +%Y%m%d_%H%M%S)"
LOGDIR="${REPO_ROOT}/logs/vlnverse_scene_demo_${TS}"
RUNDIR="${REPO_ROOT}/runs/vlnverse_demo_${TS}"
mkdir -p "${LOGDIR}" "${RUNDIR}"

# ── PYTHONPATH ────────────────────────────────────────────────────────────
export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"
source "${REPO_ROOT}/scripts/visualnav/activate_visualnav_env.sh" 2>/dev/null || true

echo "========================================"
echo "  FleetSafe VLNVerse Scene Demo"
echo "========================================"
echo "  Task:      ${TASK}"
echo "  Platform:  ${PLATFORM}"
echo "  Model:     ${MODEL}"
echo "  Logs:      ${LOGDIR}"
echo "  Run data:  ${RUNDIR}"
echo ""

PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0

# ── Helper: safely read one metric from metrics.json ─────────────────────
read_metric() {
  local file="$1" key="$2" default="$3"
  python3 -c "
import json, sys
try:
    d = json.load(open('${file}'))
    v = d.get('${key}', '${default}')
    if isinstance(v, float):
        print(f'{v:.3f}')
    elif isinstance(v, bool):
        print('✓' if v else '✗')
    else:
        print(v)
except Exception:
    print('${default}')
" 2>/dev/null || echo "${default}"
}

# ── Helper: check one episode result ─────────────────────────────────────
check_result() {
  local label="$1"
  local ep_dir="$2"
  local mf="${ep_dir}/metrics.json"

  if [[ ! -f "${mf}" ]]; then
    printf "  [FAIL] %-25s  metrics.json not found\n" "${label}"
    FAIL_COUNT=$((FAIL_COUNT + 1))
    return 0
  fi

  local success spl cert cbf
  success=$(read_metric "${mf}" "success"                   "✗")
  spl=$(    read_metric "${mf}" "spl"                       "0.000")
  cert=$(   read_metric "${mf}" "certificate_validity_rate" "0.000")
  cbf=$(    read_metric "${mf}" "cbf_intervention_count"    "0")

  printf "  [PASS] %-25s  success=%s  spl=%s  cert=%s  cbf=%s\n" \
    "${label}" "${success}" "${spl}" "${cert}" "${cbf}"
  PASS_COUNT=$((PASS_COUNT + 1))
}

# ═══════════════════════════════════════════════════════════════════════════
# Phase A — Dashboard services
# ═══════════════════════════════════════════════════════════════════════════
BACKEND_STARTED=false
FRONTEND_STARTED=false

if ! $NO_DASHBOARD; then
  echo "--- Phase A: Dashboard services ---"

  # Backend
  if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
    echo "  [OK]  Backend already running on :8000"
  else
    echo "  Starting backend on :8000..."
    cd "${REPO_ROOT}/command-center"
    export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"
    python -m uvicorn backend.main:app \
      --host 0.0.0.0 --port 8000 \
      --log-level warning \
      > "${LOGDIR}/backend.log" 2>&1 &
    BACKEND_PID=$!
    echo "  Backend PID: ${BACKEND_PID}"
    cd "${REPO_ROOT}"
    BACKEND_STARTED=true

    # Wait for backend to be ready (up to 15 s)
    echo -n "  Waiting for backend"
    for _ in $(seq 1 15); do
      sleep 1
      if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
        echo " ready."
        break
      fi
      echo -n "."
    done
    if ! curl -sf http://localhost:8000/health >/dev/null 2>&1; then
      echo ""
      echo "  [WARN] Backend did not become ready in 15 s. Check ${LOGDIR}/backend.log"
    fi
  fi

  # Frontend
  if curl -sf http://localhost:3000 >/dev/null 2>&1; then
    echo "  [OK]  Frontend already running on :3000"
  else
    echo "  Starting frontend on :3000..."
    cd "${REPO_ROOT}/command-center/frontend"
    npm install --silent 2>/dev/null || true
    npm run dev \
      > "${LOGDIR}/frontend.log" 2>&1 &
    FRONTEND_PID=$!
    echo "  Frontend PID: ${FRONTEND_PID} (may take ~30 s)"
    cd "${REPO_ROOT}"
    FRONTEND_STARTED=true
  fi

  echo ""
  echo "--- Phase A: Endpoint verification ---"
  for url in \
    "http://localhost:8000/health" \
    "http://localhost:8000/api/status" \
    "http://localhost:8000/api/demo/status"; do
    if curl -sf "${url}" >/dev/null 2>&1; then
      printf "  [OK]  %s\n" "${url}"
    else
      printf "  [WARN] %s  (not reachable yet)\n" "${url}"
    fi
  done
  echo ""
fi

# ═══════════════════════════════════════════════════════════════════════════
# Phase B — Run three safety configs
# ═══════════════════════════════════════════════════════════════════════════
echo "--- Phase B: Running VLNVerse comparison configs ---"

CONFIGS=("none"     "log_only" "cbf_qp")
LABELS=( "baseline" "log_only" "cbf_qp")

for i in "${!CONFIGS[@]}"; do
  SAFETY="${CONFIGS[$i]}"
  LABEL="${LABELS[$i]}"
  EP_DIR="${RUNDIR}/${SAFETY}"
  EP_LOG="${LOGDIR}/episode_${SAFETY}.log"

  echo ""
  printf "  Config: %s (%s)\n" "${LABEL}" "${SAFETY}"

  python3 -m fleetsafe_vln.benchmark.episode_runner \
    --task "${TASK}" \
    --platform "${PLATFORM}" \
    --model "${MODEL}" \
    --safety "${SAFETY}" \
    --log-dir "${EP_DIR}" \
    > "${EP_LOG}" 2>&1 && EP_EXIT=0 || EP_EXIT=$?

  # Always show last few lines regardless of exit code
  tail -4 "${EP_LOG}" | sed 's/^/    /'

  # exit 0 = navigation succeeded; exit 1 = ran but robot didn't reach goal
  # both are valid outcomes — artifacts should be present either way
  # only treat as SKIP/FAIL if metrics.json is completely missing (crash/import error)
  if [[ ${EP_EXIT} -gt 1 ]]; then
    printf "  [SKIP] %-25s  episode_runner crashed (exit %d) — see %s\n" \
      "${LABEL}" "${EP_EXIT}" "${EP_LOG}"
    SKIP_COUNT=$((SKIP_COUNT + 1))
  else
    check_result "${LABEL}" "${EP_DIR}"
  fi
done

# ═══════════════════════════════════════════════════════════════════════════
# Phase C — Comparison summary
# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "--- Phase C: Comparison summary ---"

python3 - <<PYEOF
import json
from pathlib import Path

configs = ["none", "log_only", "cbf_qp"]
labels  = ["baseline", "log_only", "cbf_qp"]
rundir  = Path("${RUNDIR}")

def fmt(d, key, default="—", fmt_spec=None):
    v = d.get(key)
    if v is None:
        return default
    if isinstance(v, bool):
        return "✓" if v else "✗"
    if isinstance(v, float) and fmt_spec:
        return format(v, fmt_spec)
    return str(v)

print(f"  {'config':<12}  {'success':>7}  {'spl':>5}  {'cert':>6}  {'cbf':>5}  {'nav_err':>7}")
print(f"  {'-'*12}  {'-'*7}  {'-'*5}  {'-'*6}  {'-'*5}  {'-'*7}")
for cfg, label in zip(configs, labels):
    mf = rundir / cfg / "metrics.json"
    if not mf.exists():
        print(f"  {label:<12}  {'(no metrics.json)':>7}")
        continue
    d = json.loads(mf.read_text())
    print(
        f"  {label:<12}  "
        f"{fmt(d, 'success', '?'):>7}  "
        f"{fmt(d, 'spl', '—', '.3f'):>5}  "
        f"{fmt(d, 'certificate_validity_rate', '—', '.3f'):>6}  "
        f"{fmt(d, 'cbf_intervention_count', '—'):>5}  "
        f"{fmt(d, 'navigation_error', '—', '.2f'):>7}"
    )
PYEOF

echo ""
echo "========================================"
printf "  Results: %d passed, %d failed, %d skipped\n" \
  "${PASS_COUNT}" "${FAIL_COUNT}" "${SKIP_COUNT}"
echo "  Logs:     ${LOGDIR}"
echo "  Run data: ${RUNDIR}"
echo "========================================"

if [[ $((FAIL_COUNT + SKIP_COUNT)) -gt 0 ]]; then
  echo ""
  echo "  Troubleshooting:"
  echo "    pip install -e ."
  echo "    python -c 'from fleetsafe_vln.backbones.gnm_adapter import GNMAdapter'"
  echo "    cat ${LOGDIR}/episode_none.log"
fi

echo ""
echo "Next — capture evidence:"
echo "  bash scripts/capture_vlnverse_evidence.sh --run-dir ${RUNDIR}"
echo ""
echo "  Dashboard: http://localhost:3000/dashboard"
