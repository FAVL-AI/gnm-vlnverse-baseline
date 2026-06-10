#!/usr/bin/env bash
# FleetSafe — show status of all services, ports, and recent logs.
set -euo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGDIR="$PROJECT/logs/fleetsafe"

GREEN='\033[0;32m' RED='\033[0;31m' YELLOW='\033[1;33m' NC='\033[0m'

ok()   { echo -e "  ${GREEN}✔${NC}  $*"; }
fail() { echo -e "  ${RED}✘${NC}  $*"; }
warn() { echo -e "  ${YELLOW}!${NC}  $*"; }

check_port() {
    local port=$1 label=$2
    if curl -sf "http://localhost:$port" >/dev/null 2>&1 \
       || curl -sf "http://localhost:$port/docs" >/dev/null 2>&1; then
        ok "$label  →  http://localhost:$port"
        return 0
    else
        fail "$label  →  port $port not responding"
        return 1
    fi
}

check_proc() {
    local pattern=$1 label=$2
    if pgrep -f "$pattern" >/dev/null 2>&1; then
        local pid; pid="$(pgrep -f "$pattern" | head -1)"
        ok "$label  (PID $pid)"
    else
        fail "$label  (not running)"
    fi
}

echo ""
echo "═══════════════════════════════════════════"
echo "   FleetSafe Status  —  $(date '+%Y-%m-%d %H:%M:%S')"
echo "═══════════════════════════════════════════"

echo ""
echo "── Processes ─────────────────────────────"
check_proc "uvicorn backend.main"      "Backend    (uvicorn)"
check_proc "next dev|next-server"      "Frontend   (Next.js)"
check_proc "run_supervisor_demo_isaac" "Isaac Sim"  || true
check_proc "ros2 launch fleet_safe"    "Gazebo"     || true

echo ""
echo "── Ports ─────────────────────────────────"
check_port 8000 "API  (FastAPI)"
check_port 3000 "UI   (Next.js)"

echo ""
echo "── Disk / Logs ───────────────────────────"
if [[ -d "$LOGDIR" ]]; then
    for f in backend frontend isaac gazebo; do
        logf="$LOGDIR/$f.log"
        if [[ -f "$logf" ]]; then
            sz="$(du -sh "$logf" 2>/dev/null | cut -f1)"
            age="$(stat -c '%y' "$logf" 2>/dev/null | cut -d. -f1)"
            ok "$f.log  ($sz, modified $age)"
        fi
    done
else
    warn "Log directory not found: $LOGDIR"
fi

echo ""
echo "── Recent backend errors ─────────────────"
if [[ -f "$LOGDIR/backend.log" ]]; then
    grep -i "error\|exception\|traceback" "$LOGDIR/backend.log" 2>/dev/null \
        | tail -5 || echo "  (none)"
else
    warn "No backend log yet"
fi

echo ""
echo "── Recent frontend errors ────────────────"
if [[ -f "$LOGDIR/frontend.log" ]]; then
    grep -i "error\|failed" "$LOGDIR/frontend.log" 2>/dev/null \
        | grep -v "^>" | tail -5 || echo "  (none)"
else
    warn "No frontend log yet"
fi

echo ""
echo "  Logs dir: $LOGDIR"
echo "  Launch:   ./launch_fleetsafe_all.sh"
echo "  Stop:     ./stop_fleetsafe_all.sh"
echo ""
