#!/usr/bin/env bash
# scripts/run_live_vln_demo.sh
# Orchestrate a live VLN demo session:
#   1. Confirm backend + frontend are running.
#   2. Start live Isaac capture loop (in background).
#   3. Launch an IAmGoodNavigator episode inside Isaac.
#   4. Print instructions and wait for the user to complete the demo.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

TASK="${1:-fine}"
INDEX="${2:-0}"
BACKEND_URL="http://localhost:8000"
FRONTEND_URL="http://localhost:3000"

echo "========================================"
echo "  FleetSafe — Live VLN Demo"
echo "  task=${TASK}  index=${INDEX}"
echo "========================================"
echo ""

# ── 1. Backend health check ──────────────────────────────────────────────────
echo "--- Checking backend ---"
if curl -s --max-time 3 "${BACKEND_URL}/api/vln-hub/status" >/dev/null 2>&1; then
    echo "[OK]  Backend running at ${BACKEND_URL}"
else
    echo "[WARN] Backend not responding. Start in a new terminal:"
    echo "  cd ${REPO_ROOT}/command-center"
    echo "  python -m uvicorn backend.main:app --reload --port 8000"
fi

# ── 2. Frontend health check ─────────────────────────────────────────────────
echo ""
echo "--- Checking frontend ---"
if curl -s --max-time 3 "${FRONTEND_URL}/dashboard/vln-hub" >/dev/null 2>&1; then
    echo "[OK]  Frontend running at ${FRONTEND_URL}"
else
    echo "[WARN] Frontend not responding. Start in a new terminal:"
    echo "  cd ${REPO_ROOT}/command-center/frontend"
    echo "  npm run dev -- --port 3000"
fi

# ── 3. Start live capture (background) ───────────────────────────────────────
echo ""
echo "--- Starting live capture ---"
LIVE_DIR="${REPO_ROOT}/command-center/frontend/public/live"
mkdir -p "${LIVE_DIR}"

if command -v xdotool &>/dev/null && command -v import &>/dev/null; then
    echo "[OK]  xdotool + imagemagick available — starting capture loop..."
    bash "${REPO_ROOT}/scripts/capture_isaac_live.sh" 1 &
    CAPTURE_PID=$!
    echo "  Capture PID: ${CAPTURE_PID}"
    echo "  Live image: ${FRONTEND_URL}/live/isaac_live.png"
else
    echo "[WARN] xdotool or imagemagick not found."
    echo "  Install: sudo apt install -y xdotool imagemagick"
    echo "  Then run in a second terminal:"
    echo "    bash scripts/capture_isaac_live.sh"
    CAPTURE_PID=""
fi

# ── 4. Launch episode ─────────────────────────────────────────────────────────
echo ""
echo "─────────────────────────────────────────────────────────────────"
echo ""
echo "  ┌─────────────────────────────────────────────────────────┐"
echo "  │  WHEN ISAAC SIM OPENS:                                  │"
echo "  │                                                         │"
echo "  │  1. Set camera: Perspective → Cameras → FloatingCamera  │"
echo "  │  2. Let the demo navigate.                              │"
echo "  │  3. Watch the live image update at:                     │"
echo "  │     ${FRONTEND_URL}/live/isaac_live.png                 │"
echo "  │  4. Open the dashboard:                                 │"
echo "  │     ${FRONTEND_URL}/dashboard/vln-hub                   │"
echo "  │  5. Return here and press ENTER when done.              │"
echo "  └─────────────────────────────────────────────────────────┘"
echo ""
echo "  Launching: bash scripts/run_iamgoodnavigator_episode.sh ${TASK} ${INDEX}"
echo ""

bash scripts/run_iamgoodnavigator_episode.sh "${TASK}" "${INDEX}" || true

# ── 5. Stop capture ───────────────────────────────────────────────────────────
if [[ -n "${CAPTURE_PID:-}" ]]; then
    kill "${CAPTURE_PID}" 2>/dev/null || true
    echo "[OK]  Live capture stopped."
fi

echo ""
echo "--- Done ---"
echo "  Dashboard: ${FRONTEND_URL}/dashboard/vln-hub"
echo "  Check:     bash scripts/check_fleetsafe_vlnverse_plus_demo.sh"
