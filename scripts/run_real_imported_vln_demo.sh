#!/usr/bin/env bash
# scripts/run_real_imported_vln_demo.sh
# ─────────────────────────────────────────────────────────────────────────────
# One-command real imported VLN demo.
# Fails loudly if any required real asset is missing.
#
# Steps:
#   1. setup_iamgoodnavigator.sh
#   2. setup_vlntube.sh
#   3. setup_yahboom_m3_assets.sh
#   4. VLNVerse indexer
#   5. VLNTube indexer
#   6. Start backend (if not running)
#   7. Start frontend (if not running)
#   8. Launch IAmGoodNavigator episode fine 0 (if Isaac Sim available)
#   9. set_first_person_camera.py (if Isaac available)
#  10. Open /dashboard/vln-hub
#  11. Capture evidence
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_URL="http://localhost:8000"
FRONTEND_URL="http://localhost:3000"
export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"

SKIP_ISAAC=false
SKIP_EPISODE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-isaac)   SKIP_ISAAC=true;   shift ;;
    --skip-episode) SKIP_EPISODE=true; shift ;;
    *) echo "[WARN] Unknown arg: $1"; shift ;;
  esac
done

ABORT=false

fail_loudly() {
  echo ""
  echo "╔══════════════════════════════════════════════════════════════════╗"
  echo "║  [BLOCKED] $1"
  echo "╚══════════════════════════════════════════════════════════════════╝"
  echo ""
  ABORT=true
}

echo "========================================"
echo "  FleetSafe — Real Imported VLN Demo"
echo "========================================"
echo ""

# ── Step 1: IAmGoodNavigator setup ────────────────────────────────────────
echo "=== Step 1: IAmGoodNavigator ==="
bash "${REPO_ROOT}/scripts/setup_iamgoodnavigator.sh" 2>&1
echo ""

# Check result
IANG_STATUS="${REPO_ROOT}/datasets/vlnverse/iamgoodnavigator_status.json"
if [[ ! -f "${IANG_STATUS}" ]]; then
  fail_loudly "iamgoodnavigator_status.json not written by setup script"
fi

# ── Step 2: VLNTube setup ─────────────────────────────────────────────────
echo "=== Step 2: VLNTube ==="
bash "${REPO_ROOT}/scripts/setup_vlntube.sh" 2>&1
echo ""

# ── Step 3: Yahboom assets ────────────────────────────────────────────────
echo "=== Step 3: Yahboom M3 Pro Assets ==="
bash "${REPO_ROOT}/scripts/setup_yahboom_m3_assets.sh" 2>&1
echo ""

# Check Yahboom status
ASSET_REPORT="${REPO_ROOT}/assets/robots/yahboom_m3_pro/asset_report.json"
if [[ -f "${ASSET_REPORT}" ]]; then
  HAS_URDF=$(python3 -c "import json; d=json.loads(open('${ASSET_REPORT}').read()); print(str(d.get('has_urdf',False)).lower())" 2>/dev/null || echo "false")
  if [[ "${HAS_URDF}" == "false" ]]; then
    fail_loudly "Yahboom M3 URDF not found. Pull from robot: bash scripts/pull_yahboom_assets_from_robot.sh yahboom@<IP>"
  fi
fi

# ── Step 4: VLNVerse indexer ──────────────────────────────────────────────
echo "=== Step 4: VLNVerse indexer ==="
python3 -m fleetsafe_vln.benchmark.vlnverse_indexer 2>&1 | tail -5
echo ""

# ── Step 5: VLNTube indexer ───────────────────────────────────────────────
echo "=== Step 5: VLNTube indexer ==="
python3 -m fleetsafe_vln.datagen.vlntube_indexer 2>&1 | tail -5
echo ""

# ── Early abort if blockers ───────────────────────────────────────────────
if $ABORT; then
  echo "╔══════════════════════════════════════════════════════════════════╗"
  echo "║  Demo aborted due to missing required assets.                    ║"
  echo "║  Resolve the blocking issues above and re-run.                   ║"
  echo "║                                                                  ║"
  echo "║  Missing asset report written to:                                ║"
  echo "║    assets/robots/yahboom_m3_pro/asset_report.json               ║"
  echo "║    datasets/vlnverse/iamgoodnavigator_status.json               ║"
  echo "╚══════════════════════════════════════════════════════════════════╝"
  exit 2
fi

# ── Step 6: Backend ───────────────────────────────────────────────────────
echo "=== Step 6: Backend ==="
if curl -sf "${BACKEND_URL}/health" >/dev/null 2>&1; then
  echo "[OK]  Backend already running at ${BACKEND_URL}"
else
  echo "  Starting backend..."
  (
    cd "${REPO_ROOT}/command-center"
    python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
    echo $! > /tmp/fleetsafe_backend.pid
  )
  # Wait for startup
  for i in {1..15}; do
    sleep 1
    if curl -sf "${BACKEND_URL}/health" >/dev/null 2>&1; then
      echo "[OK]  Backend started."
      break
    fi
    if [[ $i -eq 15 ]]; then
      echo "[WARN] Backend did not start in 15s. Continuing anyway."
    fi
  done
fi
echo ""

# ── Step 7: Frontend ──────────────────────────────────────────────────────
echo "=== Step 7: Frontend ==="
if curl -sf "${FRONTEND_URL}" >/dev/null 2>&1; then
  echo "[OK]  Frontend already running at ${FRONTEND_URL}"
else
  echo "  Starting frontend..."
  (
    cd "${REPO_ROOT}/command-center/frontend"
    npm run dev -- --port 3000 &
    echo $! > /tmp/fleetsafe_frontend.pid
  )
  echo "[OK]  Frontend starting (may take 10-15s)."
fi
echo ""

# ── Step 8: IAmGoodNavigator episode ─────────────────────────────────────
if ! $SKIP_EPISODE && ! $SKIP_ISAAC; then
  echo "=== Step 8: IAmGoodNavigator Episode fine 0 ==="

  IANG_DEMO="${REPO_ROOT}/external/IAmGoodNavigator/demo.py"
  if [[ ! -f "${IANG_DEMO}" ]]; then
    echo "[WARN] demo.py not found at ${IANG_DEMO}"
    echo "  Skipping episode launch."
    echo "  Run manually when Isaac Sim is open:"
    echo "    bash scripts/run_iamgoodnavigator_episode.sh fine 0"
  else
    echo "  Launching episode (requires Isaac Sim)..."
    bash "${REPO_ROOT}/scripts/run_iamgoodnavigator_episode.sh" fine 0 2>&1 || \
      echo "[WARN] Episode launch failed or Isaac not available. Continuing."
  fi
  echo ""
else
  echo "=== Step 8: [SKIP] Episode (--skip-episode or --skip-isaac) ==="
  echo ""
fi

# ── Step 9: Set first-person camera ──────────────────────────────────────
if ! $SKIP_ISAAC; then
  echo "=== Step 9: First-person camera ==="
  ISAAC_PY=""
  for pattern in "${HOME}/.local/share/ov/pkg/isaac_sim-*/python.sh" "/isaac-sim/python.sh" "${HOME}/isaac-sim/python.sh"; do
    for f in $pattern; do
      if [[ -f "${f}" ]]; then ISAAC_PY="${f}"; break 2; fi
    done
  done

  if [[ -n "${ISAAC_PY}" ]]; then
    "${ISAAC_PY}" "${REPO_ROOT}/scripts/isaac/set_first_person_camera.py" 2>&1 || \
      echo "[WARN] Camera script failed — set manually: Perspective → Cameras → FloatingCamera"
  else
    echo "[WARN] Isaac Sim not found."
    echo "  Set camera manually: Perspective → Cameras → FloatingCamera"
    # Write a placeholder camera report showing instructions
    python3 - <<PYEOF
import json
from datetime import datetime, timezone
from pathlib import Path
report = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "selected_camera": None,
    "camera_mode": "not_set",
    "is_first_person": False,
    "bird_eye_rejected": True,
    "camera_instructions": "In Isaac Sim: Perspective → Cameras → FloatingCamera",
    "isaac_available": False,
}
Path("${REPO_ROOT}/runs/current_camera_report.json").parent.mkdir(parents=True, exist_ok=True)
Path("${REPO_ROOT}/runs/current_camera_report.json").write_text(json.dumps(report, indent=2))
PYEOF
  fi
  echo ""
fi

# ── Step 10: Open dashboard ───────────────────────────────────────────────
echo "=== Step 10: Open Dashboard ==="
bash "${REPO_ROOT}/scripts/open_dashboard.sh" "${FRONTEND_URL}/dashboard/vln-hub" 2>/dev/null || \
  echo "  Dashboard: ${FRONTEND_URL}/dashboard/vln-hub"
echo ""

# ── Step 11: Capture evidence ─────────────────────────────────────────────
echo "=== Step 11: Evidence capture ==="
bash "${REPO_ROOT}/scripts/capture_live_evidence.sh" 2>&1
echo ""

echo "========================================"
echo "  Real imported VLN demo complete."
echo "  Dashboard: ${FRONTEND_URL}/dashboard/vln-hub"
echo "  Check: bash scripts/run_real_imported_vln_demo_check.sh"
echo "========================================"
