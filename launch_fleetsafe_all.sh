#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT="$HOME/robotics/FleetSafe-VisualNav-Benchmark"
LOGDIR="$PROJECT/logs/fleetsafe"
RUNDIR="$PROJECT/.fleetsafe_run"
mkdir -p "$LOGDIR" "$RUNDIR"

START_GAZEBO=0
START_ISAAC=0
OPEN_BROWSER=1

for arg in "$@"; do
  case "$arg" in
    --gazebo) START_GAZEBO=1 ;;
    --isaac) START_ISAAC=1 ;;
    --no-browser) OPEN_BROWSER=0 ;;
    --help|-h)
      echo "Usage: ./launch_fleetsafe_all.sh [--gazebo] [--isaac] [--no-browser]"
      exit 0
      ;;
  esac
done

if [ -f "$HOME/miniforge3/etc/profile.d/conda.sh" ]; then
  CONDA_SH="$HOME/miniforge3/etc/profile.d/conda.sh"
elif [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
  CONDA_SH="$HOME/miniconda3/etc/profile.d/conda.sh"
elif [ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]; then
  CONDA_SH="$HOME/anaconda3/etc/profile.d/conda.sh"
else
  echo "❌ Could not find conda.sh"
  exit 1
fi

log() {
  echo "[$(date +%H:%M:%S)] $*"
}

wait_url() {
  local url="$1"
  local name="$2"
  local timeout="${3:-30}"

  for _ in $(seq 1 "$timeout"); do
    if curl -sf "$url" >/dev/null 2>&1; then
      log "$name is up"
      return 0
    fi
    sleep 1
  done

  log "❌ $name failed to respond: $url"
  return 1
}

open_gui_terminal() {
  local title="$1"
  local cmd="$2"

  if command -v gnome-terminal >/dev/null 2>&1; then
    gnome-terminal --title="$title" -- bash -lc "$cmd; echo; echo '[$title exited]'; exec bash"
  elif command -v xterm >/dev/null 2>&1; then
    xterm -T "$title" -e bash -lc "$cmd; echo; echo '[$title exited]'; exec bash" &
  else
    log "⚠️ No gnome-terminal/xterm found. Running $title in background."
    nohup bash -lc "$cmd" > "$LOGDIR/${title// /_}.log" 2>&1 &
  fi
}

log "Clearing stale FleetSafe processes and ports..."
./stop_fleetsafe_all.sh 2>/dev/null || true

if command -v lsof >/dev/null 2>&1; then
  lsof -ti:3000 | xargs -r kill -9 2>/dev/null || true
  lsof -ti:3001 | xargs -r kill -9 2>/dev/null || true
  lsof -ti:8000 | xargs -r kill -9 2>/dev/null || true
fi

sleep 2

log "Starting backend on port 8000..."
nohup bash -lc "
  cd '$PROJECT/command-center'
  source '$CONDA_SH'
  conda activate isaac
  exec python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
" > "$LOGDIR/backend.log" 2>&1 &
echo $! > "$RUNDIR/backend.pid"

wait_url "http://localhost:8000/health" "Backend" 30 || {
  tail -80 "$LOGDIR/backend.log" || true
  exit 1
}

log "Starting frontend on port 3000..."
nohup bash -lc "
  cd '$PROJECT/command-center/frontend'
  exec npm run dev -- --port 3000
" > "$LOGDIR/frontend.log" 2>&1 &
echo $! > "$RUNDIR/frontend.pid"

wait_url "http://localhost:3000" "Frontend" 45 || {
  tail -80 "$LOGDIR/frontend.log" || true
  exit 1
}

if [ "$START_GAZEBO" = "1" ]; then
  log "Opening Gazebo M3Pro hospital GUI..."
  open_gui_terminal "Gazebo M3Pro Hospital" "
    cd '$PROJECT'
    export DISPLAY=\${DISPLAY:-:0}
    ign gazebo -v 4 -r '$PROJECT/ros2_ws/src/fleet_safe_bringup/worlds/hospital_corridor.sdf' \
      2>&1 | tee '$LOGDIR/gazebo.log'
  "
fi

if [ "$START_ISAAC" = "1" ]; then
  log "Opening Isaac Sim FleetSafe GUI..."
  open_gui_terminal "Isaac Sim FleetSafe" "
    cd '$PROJECT'
    export DISPLAY=\${DISPLAY:-:0}
    source '$CONDA_SH'
    conda activate isaac
    python -u scripts/demo/run_supervisor_demo_isaac.py \
      --model vint \
      --scene hospital_corridor \
      --fleetsafe \
      --stream \
      --no-headless \
      --max-steps 100000 \
      2>&1 | tee '$LOGDIR/isaac.log'
  "
fi

sleep 3

if [ "$OPEN_BROWSER" = "1" ]; then
  log "Opening FleetSafe dashboard..."
  bash "$(cd "$(dirname "$0")" && pwd)/scripts/open_dashboard.sh" \
    "http://localhost:3000/dashboard/demo"
fi

cat <<MSG

╔══════════════════════════════════════════════════════╗
║        FleetSafe LaunchPad — started                 ║
╠══════════════════════════════════════════════════════╣
║  Dashboard   http://localhost:3000/dashboard/demo    ║
║  API docs    http://localhost:8000/docs              ║
║  Health      http://localhost:8000/health            ║
╠══════════════════════════════════════════════════════╣
║  Logs        $LOGDIR
║  Status      ./fleetsafe-status.sh
║  Stop        ./stop_fleetsafe_all.sh
╚══════════════════════════════════════════════════════╝

MSG
