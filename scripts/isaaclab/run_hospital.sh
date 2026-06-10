#!/usr/bin/env bash
# scripts/isaaclab/run_hospital.sh
#
# Launch the FleetSafe hospital benchmark in Isaac Sim with optional
# pedestrian scenarios and sensor degradation.
#
# Scene options (--scene):
#   hospital_corridor          Default — main corridor
#   hospital_waiting_room      Waiting room congestion
#   hospital_narrow_passage    Narrow passage (tight CBF test)
#   hospital_crowded_junction  Multi-path junction
#   hospital_elevator_lobby    Elevator lobby (door / hold test)
#   hospital_reception         Reception desk area
#
# Pedestrian scenario (--scenario):
#   crossing        Human crossing trajectory
#   occlusion       Occlusion emergence
#   congestion      Multi-person congestion
#   yield           Yield behaviour test
#   corridor_rush   Corridor rush hour
#   none            No agents (default)
#
# Sensor degradation (--degrade):
#   Comma-separated list of faults to inject:
#   motion_blur=<0-100>  low_light=<0-100>  lidar_dropout=<0-50>
#   packet_loss=<0-30>   latency_jitter=<0-200>  depth_corruption
#   Example: --degrade "motion_blur=30,low_light=50,lidar_dropout=10"
#
# Usage:
#   ./scripts/isaaclab/run_hospital.sh
#   ./scripts/isaaclab/run_hospital.sh --scene hospital_narrow_passage
#   ./scripts/isaaclab/run_hospital.sh --scene hospital_corridor --scenario crossing
#   ./scripts/isaaclab/run_hospital.sh --scenario congestion --degrade "motion_blur=40,low_light=60"
#   ./scripts/isaaclab/run_hospital.sh --steps 2000 --headless
#   ./scripts/isaaclab/run_hospital.sh --capture              # save screenshot + photoreal_status
#   ./scripts/isaaclab/run_hospital.sh --headless --capture --steps 100  # fast CI capture
#   ./scripts/isaaclab/run_hospital.sh --no-usd --capture    # force procedural, still capture
#   ./scripts/isaaclab/run_hospital.sh --livestream 1         # remote WebRTC stream

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# ── Parse --headless before banner (AppLauncher must own --headless) ──────────
HEADLESS=0
for arg in "$@"; do
    [[ "$arg" == "--headless" ]] && HEADLESS=1
done

# ── Check conda environment ───────────────────────────────────────────────────
if [[ -z "${CONDA_DEFAULT_ENV}" ]] || [[ "${CONDA_DEFAULT_ENV}" != "isaac" ]]; then
    echo ""
    echo "[run_hospital.sh] ERROR: Isaac conda environment not active."
    echo "  Run: conda activate isaac"
    echo "  Then re-run: ./scripts/isaaclab/run_hospital.sh"
    echo ""
    exit 1
fi

# ── Accept Isaac Sim EULA automatically ──────────────────────────────────────
export OMNI_KIT_ACCEPT_EULA=Y

# ── Suppress unnecessary Nucleus chatter ─────────────────────────────────────
export OMNI_SERVER_SEARCH_TIMEOUT=1
export OMNI_CACHE_PATH="${REPO_ROOT}/.omni_cache"

# ── Python path ───────────────────────────────────────────────────────────────
export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"

PYTHON="${CONDA_PREFIX}/bin/python"

# ── Banner ────────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  FleetSafe VisualNav  |  Hospital Benchmark  |  Isaac Sim"
echo "════════════════════════════════════════════════════════════════"
echo "  Repo      : ${REPO_ROOT}"
echo "  Isaac     : $("${PYTHON}" -c 'import isaaclab; print(isaaclab.__version__)' 2>/dev/null || echo 'version unknown')"
echo "  Conda     : ${CONDA_DEFAULT_ENV}"
echo "  Headless  : ${HEADLESS}"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "  Scenes    : hospital_corridor | hospital_waiting_room"
echo "              hospital_narrow_passage | hospital_crowded_junction"
echo "              hospital_elevator_lobby | hospital_reception"
echo ""
echo "  Scenarios : none | crossing | occlusion | congestion"
echo "              yield | corridor_rush"
echo ""
echo "  Degrade   : motion_blur=<0-100>  low_light=<0-100>"
echo "              lidar_dropout=<0-50>  packet_loss=<0-30>"
echo "              latency_jitter=<0-200>  depth_corruption"
echo "════════════════════════════════════════════════════════════════"
echo ""

cd "${REPO_ROOT}"
exec "${PYTHON}" "${SCRIPT_DIR}/run_hospital.py" "$@"
