#!/bin/bash
# H7-Hospital RAISED-MOUNT re-record campaign. Identical to the original H7 pilot
# except the front camera is raised +0.12 m (level horizon kept) via --camera-raise
# to remove the robot-body lower-third occlusion. Same 8 routes, same split, same
# scene-identity gate (fail-closed), same collision reporting, same steps/goal.
# Episode prefix h7r_ keeps bags / gate manifests / trajectories separate from the
# committed original H7 pilot (nothing overwritten). Disciplined hygiene: disk guard
# (>=100G), bounded per-episode timeout with rc capture, EXACT-PID orphan-recorder
# cleanup (never pkill -f patterns), stale-DDS shm removal only when no ROS/Isaac live.
# Usage: hospital_h7_raise_record_campaign.sh [base_name ...]  (default: all 8)
set +u
source /opt/ros/humble/setup.bash

REPO=/home/favl/robotics/gnm-vlnverse-baseline
BR=$REPO/scripts/robots/m3pro_ros2_bringup.py
RD=$REPO/assets/experiments/hospital_h7_collection/routes
PY=$HOME/miniforge3/envs/isaac/bin/python
RAISE=0.12
REPORTS=$REPO/assets/experiments/hospital_h7_raise_collection/reports
LEDGER=$REPORTS/h7r_campaign_ledger.csv
mkdir -p "$REPORTS"
[ -f "$LEDGER" ] || echo "episode_name,route_id,rc,camera_raise_m,started,ended" > "$LEDGER"

DEFAULT="reception_01 reception_02 corridor_01 corridor_02 turn_01 turn_02 waiting_01 waiting_02"
BASES="${*:-$DEFAULT}"

clean_dds () {
  local pids
  pids=$(pgrep -f "ros2 bag record")
  if [ -n "$pids" ]; then
    echo "[campaign] cleaning orphan recorders: $pids"
    kill $pids 2>/dev/null; sleep 3; kill -9 $pids 2>/dev/null
  fi
  if ! pgrep -f "m3pro_ros2_bringup" >/dev/null && ! pgrep -f "ros2 bag record" >/dev/null; then
    rm -f /dev/shm/fastrtps_* /dev/shm/sem.fastrtps_* 2>/dev/null
  fi
}

for base in $BASES; do
  route="$RD/h7_${base}.json"
  ep="h7r_${base}"
  if [ ! -f "$route" ]; then echo "[campaign] MISSING route $route — skip $ep"; continue; fi
  avail=$(df --output=avail -BG /home/favl | tail -1 | tr -dc 0-9)
  if [ "${avail:-0}" -lt 100 ]; then
    echo "[campaign] DISK LOW ${avail}G (<100G) — aborting before $ep"; break
  fi
  clean_dds
  started=$(date -Iseconds)
  echo "===== EPISODE $ep START ($started, disk ${avail}G, camera_raise ${RAISE}m) ====="
  timeout 1800 "$PY" -u "$BR" --scene hospital --scene-gate --camera-raise "$RAISE" \
    --gnm-control --route-follow "$route" --holonomic-base --collision-report \
    --episode --episode-name "$ep" --goal-id h2_weave_J --steps 6000
  rc=$?
  ended=$(date -Iseconds)
  echo "===== EPISODE $ep EXIT rc=$rc ($ended) ====="
  echo "$ep,h7_${base},$rc,$RAISE,$started,$ended" >> "$LEDGER"
  clean_dds
  if [ "$rc" -ne 0 ]; then
    echo "[campaign] ABORT: $ep exited rc=$rc (systemic — gate/timeout/crash). Stopping."
    break
  fi
  sleep 5
done
echo "[campaign] DONE"
