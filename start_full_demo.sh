#!/usr/bin/env bash
set -Eeuo pipefail

echo "=== FleetSafe Supervisor Demo Launcher ==="

ROOT="$HOME/robotics/FleetSafe-VisualNav-Benchmark"
LOGDIR="$ROOT/logs/full_demo_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOGDIR"

cd "$ROOT"

echo "Logs: $LOGDIR"
echo ""

# ── Locate conda.sh ───────────────────────────────────────────────────────────

CONDA_SH=""
for d in "$HOME/miniforge3" "$HOME/miniconda3" "$HOME/anaconda3"; do
    if [ -f "$d/etc/profile.d/conda.sh" ]; then
        CONDA_SH="$d/etc/profile.d/conda.sh"
        break
    fi
done

if [ -z "$CONDA_SH" ] && command -v conda >/dev/null 2>&1; then
    CONDA_SH="$(conda info --base)/etc/profile.d/conda.sh"
fi

if [ ! -f "$CONDA_SH" ]; then
    echo "❌ conda.sh not found — check your Conda installation"
    echo "   find \$HOME -path '*/etc/profile.d/conda.sh' 2>/dev/null"
    exit 1
fi

echo "Conda: $CONDA_SH"
source "$CONDA_SH"
conda activate isaac

echo "Python:    $(which python)"
echo "Version:   $(python --version)"
echo "Conda env: $CONDA_DEFAULT_ENV"
echo ""

# ── Kill old processes ────────────────────────────────────────────────────────

echo "Stopping old demo processes..."
pkill -9 -f "uvicorn" 2>/dev/null || true
pkill -9 -f "run_supervisor_demo_isaac.py" 2>/dev/null || true
pkill -9 -f "next dev" 2>/dev/null || true
pkill -9 -f "next-server" 2>/dev/null || true
pkill -9 -f "turbopack" 2>/dev/null || true
pkill -9 -f "node.*next" 2>/dev/null || true
pkill -9 -f "kit" 2>/dev/null || true

if command -v lsof >/dev/null 2>&1; then
    lsof -ti:3000 | xargs -r kill -9 2>/dev/null || true
    lsof -ti:3001 | xargs -r kill -9 2>/dev/null || true
    lsof -ti:8000 | xargs -r kill -9 2>/dev/null || true
fi

sleep 3

# ── Backend ───────────────────────────────────────────────────────────────────

echo "Starting Backend..."
touch "$ROOT/command-center/backend/__init__.py"

nohup bash -lc "
source '$CONDA_SH'
conda activate isaac
cd '$ROOT/command-center'
PYTHONPATH='$ROOT/command-center' python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
" > "$LOGDIR/backend.log" 2>&1 &

BACKEND_PID=$!
echo "$BACKEND_PID" > "$LOGDIR/backend.pid"
echo "Backend PID: $BACKEND_PID"
sleep 3

if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "❌ Backend died immediately. Last log:"
    tail -n 60 "$LOGDIR/backend.log"
    exit 1
fi

# ── Frontend ──────────────────────────────────────────────────────────────────

echo "Starting Frontend..."
nohup bash -lc "
cd '$ROOT/command-center/frontend'
npm run dev -- --port 3000
" > "$LOGDIR/frontend.log" 2>&1 &

FRONTEND_PID=$!
echo "$FRONTEND_PID" > "$LOGDIR/frontend.pid"
echo "Frontend PID: $FRONTEND_PID"
sleep 5

if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
    echo "❌ Frontend died immediately. Last log:"
    tail -n 60 "$LOGDIR/frontend.log"
    exit 1
fi

# ── Isaac launcher script (runs inside a dedicated terminal) ──────────────────

ISAAC_LAUNCHER="$LOGDIR/launch_isaac.sh"

cat > "$ISAAC_LAUNCHER" << EOF2
#!/usr/bin/env bash
set -Eeuo pipefail

echo "=== FleetSafe Isaac Sim Demo ==="
echo "Log: $LOGDIR/isaac.log"
echo ""

source "$CONDA_SH"
conda activate isaac

cd "$ROOT"

echo "Python:    \$(which python)"
echo "Version:   \$(python --version)"
echo "Conda env: \$CONDA_DEFAULT_ENV"
echo ""
echo "Starting Isaac Sim..."
echo ""

python scripts/demo/run_supervisor_demo_isaac.py \\
    --model vint \\
    --scene hospital_corridor \\
    --fleetsafe \\
    --stream \\
    --no-headless \\
    --max-steps 100000 2>&1 | tee "$LOGDIR/isaac.log"

STATUS=\${PIPESTATUS[0]}
echo ""
echo "Isaac exited with status: \$STATUS"
echo "Full log: $LOGDIR/isaac.log"
echo ""
read -rp "Press Enter to close this window..."
exit \$STATUS
EOF2

chmod +x "$ISAAC_LAUNCHER"

echo "Starting Isaac Sim in its own terminal..."

if command -v gnome-terminal >/dev/null 2>&1; then
    gnome-terminal --title="FleetSafe Isaac Sim" -- bash "$ISAAC_LAUNCHER"
elif command -v xterm >/dev/null 2>&1; then
    xterm -T "FleetSafe Isaac Sim" -geometry 160x50 -e bash "$ISAAC_LAUNCHER" &
else
    echo "⚠️  No gnome-terminal or xterm found — running Isaac in background"
    nohup bash "$ISAAC_LAUNCHER" > "$LOGDIR/isaac_bg.log" 2>&1 &
    echo "$!" > "$LOGDIR/isaac.pid"
fi

sleep 8

# ── Dashboard ─────────────────────────────────────────────────────────────────

echo "Opening Dashboard..."
bash "${REPO_ROOT:-$(cd "$(dirname "$0")" && pwd)}/scripts/open_dashboard.sh" \
  "http://localhost:3000/dashboard/demo"

echo ""
echo "✅ Launcher complete. Wait 60-90 s for Isaac to fully boot."
echo ""
echo "  Dashboard:    http://localhost:3000/dashboard/demo"
echo "  Backend log:  $LOGDIR/backend.log"
echo "  Frontend log: $LOGDIR/frontend.log"
echo "  Isaac log:    $LOGDIR/isaac.log"
echo ""
echo "If Isaac closes, the Isaac terminal shows the real error."
echo "To stop everything: ./stop_full_demo.sh"
