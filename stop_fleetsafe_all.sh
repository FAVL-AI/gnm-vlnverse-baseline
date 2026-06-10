#!/usr/bin/env bash
# FleetSafe — stop all running services cleanly.
set -euo pipefail

log() { echo "[$(date '+%H:%M:%S')] $*"; }

log "Stopping FleetSafe services..."

pkill -TERM -f "uvicorn backend.main"      2>/dev/null && log "  backend stopped"  || true
pkill -TERM -f "next dev|next-server"      2>/dev/null && log "  frontend stopped" || true
pkill -TERM -f "turbopack"                 2>/dev/null || true
pkill -TERM -f "node.*next"                2>/dev/null || true
pkill -TERM -f "run_supervisor_demo_isaac" 2>/dev/null && log "  Isaac stopped"    || true
pkill -TERM -f "ros2 launch fleet_safe"    2>/dev/null && log "  Gazebo stopped"   || true

sleep 1

# Force-kill anything still holding the ports
if command -v lsof >/dev/null 2>&1; then
    for port in 3000 8000; do
        pids="$(lsof -ti:"$port" 2>/dev/null || true)"
        if [[ -n "$pids" ]]; then
            echo "$pids" | xargs kill -9 2>/dev/null || true
            log "  Force-killed port $port"
        fi
    done
fi

log "All FleetSafe services stopped."

pkill -f "make m3pro-gazebo" 2>/dev/null || true
pkill -f "ros2 launch fleet_safe_bringup" 2>/dev/null || true
pkill -f "ros_gz_sim" 2>/dev/null || true
pkill -f "parameter_bridge" 2>/dev/null || true
pkill -f "robot_state_publisher" 2>/dev/null || true
pkill -f "ign gazebo" 2>/dev/null || true
pkill -f "gz sim" 2>/dev/null || true
pkill -f "run_supervisor_demo_isaac.py" 2>/dev/null || true
pkill -f "SimulationApp" 2>/dev/null || true
pkill -f "kit" 2>/dev/null || true