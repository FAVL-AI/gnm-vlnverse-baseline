#!/bin/bash
# H8 paired-branch minimal recording campaign (2 designs x 2 branches = 4 episodes).
# Records REAL /camera/image_raw in hospital.usd with the scene-identity gate fail-closed
# and the raised camera mount (+0.12 m). Each design's two branch routes share a decision
# point o_d (waypoint index 1); o_d is captured from route A's decision-index frame and
# paired with both recorded goal images at gate time. NO training. Discipline mirrors the
# H7r campaign: disk guard (>=100G), bounded per-episode timeout with rc capture, EXACT-PID
# orphan-recorder cleanup (never `pkill -f` broad patterns), stale-DDS shm removal only when
# no ROS/Isaac live. Episode prefix h8_ keeps bags/trajectories separate from H7/H7r.
# Usage: hospital_h8_paired_branch_record.sh [route_basename ...]
set +u
source /opt/ros/humble/setup.bash

REPO=/home/favl/robotics/gnm-vlnverse-baseline
BR=$REPO/scripts/robots/m3pro_ros2_bringup.py
RD=$REPO/assets/experiments/hospital_h8_paired_branch_prototype/routes
PY=$HOME/miniforge3/envs/isaac/bin/python
RAISE=0.12
REPORTS=$REPO/assets/experiments/hospital_h8_paired_branch_prototype/reports
LEDGER=$REPORTS/h8_record_ledger.csv
mkdir -p "$REPORTS"
[ -f "$LEDGER" ] || echo "episode_name,route_id,rc,camera_raise_m,started,ended" > "$LEDGER"

DEFAULT="d1_routeA_turn_up d1_routeB_straight d2_routeA_fwdleft d2_routeB_fwdright"
BASES="${*:-$DEFAULT}"

clean_dds () {
  local pids
  pids=$(pgrep -f "ros2 bag record")
  if [ -n "$pids" ]; then
    echo "[campaign] cleaning orphan recorders (exact pids): $pids"
    kill $pids 2>/dev/null; sleep 3; kill -9 $pids 2>/dev/null
  fi
  if ! pgrep -f "m3pro_ros2_bringup" >/dev/null && ! pgrep -f "ros2 bag record" >/dev/null; then
    rm -f /dev/shm/fastrtps_* /dev/shm/sem.fastrtps_* 2>/dev/null
  fi
}

for base in $BASES; do
  route="$RD/h8_${base}.json"
  ep="h8_${base}"
  if [ ! -f "$route" ]; then echo "[campaign] MISSING route $route — skip $ep"; continue; fi
  avail=$(df --output=avail -BG /home/favl | tail -1 | tr -dc 0-9)
  if [ "${avail:-0}" -lt 100 ]; then
    echo "[campaign] DISK LOW ${avail}G (<100G) — aborting before $ep"; break
  fi
  clean_dds
  started=$(date -Iseconds)
  echo "===== EPISODE $ep START ($started, disk ${avail}G, camera_raise ${RAISE}m) ====="
  timeout 1200 "$PY" -u "$BR" --scene hospital --scene-gate --camera-raise "$RAISE" \
    --gnm-control --route-follow "$route" --holonomic-base --collision-report \
    --episode --episode-name "$ep" --goal-id h2_weave_J --steps 4000
  rc=$?
  ended=$(date -Iseconds)
  echo "===== EPISODE $ep EXIT rc=$rc ($ended) ====="
  echo "$ep,h8_${base},$rc,$RAISE,$started,$ended" >> "$LEDGER"
  clean_dds
  if [ "$rc" -ne 0 ] && [ "$rc" -ne 124 ]; then
    echo "[campaign] NOTE: $ep exited rc=$rc (non-timeout). Continuing to next; will assess in gate."
  fi
done
echo "[campaign] done. ledger: $LEDGER"
