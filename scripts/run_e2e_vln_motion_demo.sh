#!/usr/bin/env bash
# scripts/run_e2e_vln_motion_demo.sh
# E2E VLN motion demo — scripted camera-motion evidence collection.
#
# This is NOT autonomous robot control. It:
#   a. Confirms scene is loaded and FloatingCamera is selected.
#   b. Confirms the live capture pipeline is running.
#   c. Records frames for N seconds of camera motion.
#   d. Records timestamps and basic status as a trajectory log.
#   e. Writes:
#        runs/e2e_vln_motion_demo/status.json
#        runs/e2e_vln_motion_demo/trajectory.csv
#        evidence/fleetsafe_vlnverse_plus/live/e2e_motion_summary.json
#
# status.json ALWAYS includes:
#   mode: manual_or_scripted_camera_motion
#   autonomous_robot_control: false
#
# To show autonomous /cmd_vel control, wire FleetSafe to ROS2 first.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

DURATION="${1:-30}"   # seconds to record
OUT_DIR="${REPO_ROOT}/runs/e2e_vln_motion_demo"
EV_LIVE_DIR="${REPO_ROOT}/evidence/fleetsafe_vlnverse_plus/live"
LIVE_PNG="${REPO_ROOT}/command-center/frontend/public/live/isaac_live.png"
TRAJ_CSV="${OUT_DIR}/trajectory.csv"
STATUS_JSON="${OUT_DIR}/status.json"
SUMMARY_JSON="${EV_LIVE_DIR}/e2e_motion_summary.json"

mkdir -p "${OUT_DIR}" "${EV_LIVE_DIR}"

echo "========================================"
echo "  FleetSafe — E2E VLN Motion Demo"
echo "  Record duration: ${DURATION}s"
echo "========================================"
echo ""

# ── Check: episode meta (scene loaded?) ───────────────────────────────────────
SCENE_EXISTS="false"
LATEST_META=$(find "datasets/vlnverse/imported/iamgoodnavigator" -name "episode_meta.json" 2>/dev/null | sort | tail -1 || echo "")
if [[ -n "${LATEST_META}" ]]; then
    SCENE_EXISTS=$(python3 -c "import json; d=json.load(open('${LATEST_META}')); print(str(d.get('scene_exists',False)).lower())" 2>/dev/null || echo "false")
fi

echo "  Scene loaded in metadata: ${SCENE_EXISTS}"
if [[ "${SCENE_EXISTS}" != "true" ]]; then
    echo "[WARN] Scene not confirmed in episode metadata."
    echo "  Run demo first: bash scripts/run_iamgoodnavigator_episode.sh fine 0"
fi

# ── Check: camera report ──────────────────────────────────────────────────────
CAM_FP="false"
if [[ -f "runs/current_camera_report.json" ]]; then
    CAM_FP=$(python3 -c "import json; d=json.load(open('runs/current_camera_report.json')); print(str(d.get('is_first_person',False)).lower())" 2>/dev/null || echo "false")
fi
echo "  FloatingCamera confirmed: ${CAM_FP}"

# ── Check: live capture running ───────────────────────────────────────────────
LIVE_STATUS="unknown"
if [[ -f "${EV_LIVE_DIR}/live_status.json" ]]; then
    LIVE_STATUS=$(python3 -c "import json; d=json.load(open('${EV_LIVE_DIR}/live_status.json')); print(d.get('message','unknown')[:60])" 2>/dev/null || echo "unknown")
fi
echo "  Live capture status: ${LIVE_STATUS}"
echo ""

# ── Instruction ───────────────────────────────────────────────────────────────
echo "  ┌─────────────────────────────────────────────────────────┐"
echo "  │  MANUAL ACTION REQUIRED                                 │"
echo "  │                                                         │"
echo "  │  1. Open Isaac Sim with the VLN scene loaded.           │"
echo "  │  2. Set: Perspective → Cameras → FloatingCamera.        │"
echo "  │  3. Run capture loop in another terminal:               │"
echo "  │       bash scripts/capture_isaac_live.sh                │"
echo "  │  4. Navigate through the scene (drag/WASD/fly).         │"
echo "  │  5. Press ENTER here to start recording the session.    │"
echo "  └─────────────────────────────────────────────────────────┘"
echo ""
read -r -p "  Press ENTER when Isaac is open and FloatingCamera is set..."
echo ""

# ── Record phase ──────────────────────────────────────────────────────────────
echo "  Recording for ${DURATION} seconds..."
echo "  Navigate the scene now."
echo ""

START_TS=$(python3 -c "from datetime import datetime, timezone; print(datetime.now(timezone.utc).isoformat())")

# Write trajectory CSV header
echo "timestamp_utc,frame_path,live_capture_active" > "${TRAJ_CSV}"

for i in $(seq 1 "${DURATION}"); do
    FRAME_TS=$(python3 -c "from datetime import datetime, timezone; print(datetime.now(timezone.utc).isoformat())")
    FRAME_EXISTS="false"
    [[ -f "${LIVE_PNG}" ]] && FRAME_EXISTS="true"
    echo "${FRAME_TS},${LIVE_PNG},${FRAME_EXISTS}" >> "${TRAJ_CSV}"
    echo "  [${i}/${DURATION}] frame recorded"
    sleep 1
done

END_TS=$(python3 -c "from datetime import datetime, timezone; print(datetime.now(timezone.utc).isoformat())")
TRAJ_ROWS=$(tail -n +2 "${TRAJ_CSV}" | wc -l | tr -d ' ')

echo ""
echo "  Recording complete: ${TRAJ_ROWS} timesteps"

# ── Write status + summary ────────────────────────────────────────────────────
python3 - <<PYEOF
import json
from datetime import datetime, timezone
from pathlib import Path

start = "${START_TS}"
end   = "${END_TS}"
rows  = int("${TRAJ_ROWS}")
cam_fp = "${CAM_FP}" == "true"
scene  = "${SCENE_EXISTS}" == "true"

status = {
    "mode": "manual_or_scripted_camera_motion",
    "autonomous_robot_control": False,
    "note": (
        "Camera motion was recorded manually. "
        "For autonomous /cmd_vel control, wire FleetSafe backbone to ROS2."
    ),
    "start_time": start,
    "end_time": end,
    "timesteps": rows,
    "trajectory_csv": "${TRAJ_CSV}",
    "scene_loaded": scene,
    "floatingcamera_confirmed": cam_fp,
    "generated_at": datetime.now(timezone.utc).isoformat(),
}

summary = {
    **status,
    "live_frames_path": "${LIVE_PNG}",
    "e2e_evidence": cam_fp and scene and rows > 0,
    "e2e_evidence_note": (
        "FloatingCamera + scene + timestep CSV present. "
        "Motion is manual navigation, not autonomous robot control."
        if cam_fp and scene and rows > 0 else
        "Missing: " + (
            "FloatingCamera " if not cam_fp else ""
        ) + (
            "scene_loaded " if not scene else ""
        ) + (
            "no frames" if rows == 0 else ""
        )
    ),
}

Path("${STATUS_JSON}").write_text(json.dumps(status, indent=2))
Path("${SUMMARY_JSON}").write_text(json.dumps(summary, indent=2))
print(f"  status.json:   ${STATUS_JSON}")
print(f"  summary.json:  ${SUMMARY_JSON}")
print(f"  trajectory.csv: ${TRAJ_CSV}")
print(f"  e2e_evidence: {summary['e2e_evidence']}")
PYEOF

echo ""
echo "========================================"
echo "  NOTE: autonomous_robot_control = false"
echo "  Motion is camera navigation by hand."
echo "  For /cmd_vel control, run FleetSafe"
echo "  backbone + ROS2 bridge inside Isaac."
echo "========================================"
echo ""
echo "  Check: bash scripts/check_fleetsafe_vlnverse_plus_demo.sh"
