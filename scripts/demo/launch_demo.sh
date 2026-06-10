#!/usr/bin/env bash
# FleetSafe Demo Launcher
# Starts the full demo stack: FastAPI backend + Next.js frontend + browser.
# Usage:
#   ./scripts/demo/launch_demo.sh          # mock mode (instant, no Isaac)
#   ./scripts/demo/launch_demo.sh --isaac  # real Isaac Sim (WebRTC streaming)

set -e
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FRONTEND="$REPO/command-center/frontend"
BACKEND="$REPO/command-center/backend"
DEMO_URL="http://localhost:3000/dashboard/demo"
BACKEND_URL="http://localhost:8000/api/health"
ISAAC_URL="http://localhost:8211"

ISAAC_MODE=false
for arg in "$@"; do
  [[ "$arg" == "--isaac" ]] && ISAAC_MODE=true
done

echo "=============================="
echo " FleetSafe Demo Launcher"
echo "=============================="
echo " Repo:     $REPO"
echo " Mode:     $([[ $ISAAC_MODE == true ]] && echo 'Isaac Sim (WebRTC)' || echo 'Mock (instant)')"
echo ""

# ── Kill old instances ────────────────────────────────────────────────────────
echo "[1/4] Stopping any old demo processes..."
pkill -f "uvicorn main:app" 2>/dev/null || true
pkill -f "next dev\|next-server" 2>/dev/null || true
pkill -f "run_supervisor_demo_isaac" 2>/dev/null || true
sleep 1

# ── Backend ───────────────────────────────────────────────────────────────────
echo "[2/4] Starting FastAPI backend on port 8000..."
cd "$BACKEND/.."
python -m uvicorn backend.main:app \
    --host 0.0.0.0 --port 8000 \
    --log-level warning \
    > /tmp/fleetsafe_backend.log 2>&1 &
BACKEND_PID=$!
echo "     PID $BACKEND_PID  →  logs: /tmp/fleetsafe_backend.log"

# Wait for backend to be ready
for i in $(seq 1 20); do
  sleep 0.5
  if curl -sf "$BACKEND_URL" > /dev/null 2>&1; then
    echo "     ✓ Backend ready"
    break
  fi
  [[ $i -eq 20 ]] && echo "     ⚠ Backend may still be starting..."
done

# ── Frontend ──────────────────────────────────────────────────────────────────
echo "[3/4] Starting Next.js frontend on port 3000..."
cd "$FRONTEND"
npm run dev \
    > /tmp/fleetsafe_frontend.log 2>&1 &
FRONTEND_PID=$!
echo "     PID $FRONTEND_PID  →  logs: /tmp/fleetsafe_frontend.log"

# Wait for frontend
sleep 4
for i in $(seq 1 12); do
  sleep 1
  if curl -sf "http://localhost:3000" > /dev/null 2>&1; then
    echo "     ✓ Frontend ready"
    break
  fi
  [[ $i -eq 12 ]] && echo "     ⚠ Frontend may still be compiling..."
done

# ── Isaac (optional) ──────────────────────────────────────────────────────────
if [[ $ISAAC_MODE == true ]]; then
  echo "[4/4] Launching Isaac Sim (GUI window + WebRTC stream)..."
  echo "     Isaac GUI window will open on your desktop (~60s to boot)"
  echo "     WebRTC also available at $ISAAC_URL once running"
  CONDA_PYTHON="$HOME/miniforge3/envs/isaac/bin/python"
  if [[ ! -f "$CONDA_PYTHON" ]]; then
    echo "     ⚠ Isaac conda env not found at $CONDA_PYTHON"
    echo "     Run: conda create -n isaac ... first"
  else
    cd "$REPO"
    "$CONDA_PYTHON" scripts/demo/run_supervisor_demo_isaac.py \
        --model vint \
        --scene hospital_corridor \
        --fleetsafe \
        --stream \
        --max-steps 2000 \
        > /tmp/fleetsafe_isaac.log 2>&1 &
    ISAAC_PID=$!
    echo "     PID $ISAAC_PID  →  logs: /tmp/fleetsafe_isaac.log"
  fi
else
  echo "[4/4] Mock mode — Isaac not required."
  echo "     Start from the dashboard: $DEMO_URL → click Start"
fi

# ── Open browser ──────────────────────────────────────────────────────────────
echo ""
echo "=============================="
echo " Opening demo in browser..."
echo " $DEMO_URL"
echo "=============================="
sleep 1
bash "$(cd "$(dirname "$0")/../.." && pwd)/scripts/open_dashboard.sh" "$DEMO_URL"

echo ""
echo " Logs:"
echo "   Backend : /tmp/fleetsafe_backend.log"
echo "   Frontend: /tmp/fleetsafe_frontend.log"
[[ $ISAAC_MODE == true ]] && echo "   Isaac   : /tmp/fleetsafe_isaac.log"
echo ""
echo " Stop all: pkill -f 'uvicorn|next dev|run_supervisor_demo'"
echo ""
echo " Press Ctrl+C to exit this launcher (stack keeps running in background)"
wait
