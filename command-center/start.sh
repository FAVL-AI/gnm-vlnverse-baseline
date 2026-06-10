#!/usr/bin/env bash
# FleetSafe Command Center — one-command local dev launcher
#
# Usage:
#   ./command-center/start.sh          # starts backend + frontend
#   ./command-center/start.sh --api    # backend only
#   ./command-center/start.sh --ui     # frontend only
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

API_ONLY=false
UI_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --api) API_ONLY=true; shift ;;
        --ui)  UI_ONLY=true;  shift ;;
        *) shift ;;
    esac
done

# ── Activate conda env ────────────────────────────────────────────────────────
if command -v conda &>/dev/null; then
    source ~/miniforge3/etc/profile.d/conda.sh 2>/dev/null || true
    conda activate isaac 2>/dev/null || conda activate base 2>/dev/null || true
fi
export PYTHONPATH="$REPO_ROOT:$PYTHONPATH"

# ── Install Python deps ───────────────────────────────────────────────────────
echo "[fleetsafe-cc] Checking Python dependencies…"
pip install -q -r "$BACKEND_DIR/requirements.txt"

# ── Start backend ─────────────────────────────────────────────────────────────
if ! $UI_ONLY; then
    echo "[fleetsafe-cc] Starting FastAPI backend on http://localhost:8000"
    cd "$SCRIPT_DIR"
    python -m uvicorn backend.main:app \
        --host 0.0.0.0 --port 8000 --reload \
        --log-level info &
    BACKEND_PID=$!
    echo "[fleetsafe-cc] Backend PID: $BACKEND_PID"
fi

# ── Install & start frontend ──────────────────────────────────────────────────
if ! $API_ONLY; then
    echo "[fleetsafe-cc] Starting Next.js frontend on http://localhost:3000"
    cd "$FRONTEND_DIR"
    npm install --silent
    npm run dev &
    FRONTEND_PID=$!
    echo "[fleetsafe-cc] Frontend PID: $FRONTEND_PID"
fi

echo ""
echo "  FleetSafe Command Center"
echo "  Landing:   http://localhost:3000"
echo "  Dashboard: http://localhost:3000/dashboard"
echo "  API docs:  http://localhost:8000/api/docs"
echo ""
echo "  Press Ctrl+C to stop all services."
echo ""

trap 'echo ""; echo "Stopping…"; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0' INT TERM
wait
