#!/bin/bash
# H7-Hospital 8-episode pilot recording campaign. Each episode: real hospital.usd,
# scene-identity gate (fail-closed), scripted route-follow, collision reporting,
# rosbag + trajectory. Disciplined between-episode hygiene: disk guard (>=100G),
# bounded per-episode timeout with rc capture, EXACT-PID orphan-recorder cleanup
# (never pkill -f patterns), stale-DDS shm removal only when no ROS/Isaac procs.
set +u
source /opt/ros/humble/setup.bash

REPO=/home/favl/robotics/gnm-vlnverse-baseline
BR=$REPO/scripts/robots/m3pro_ros2_bringup.py
RD=$REPO/assets/experiments/hospital_h7_collection/routes
PY=$HOME/miniforge3/envs/isaac/bin/python
REPORTS=$REPO/assets/experiments/hospital_h7_collection/reports
LEDGER=$REPORTS/h7_campaign_ledger.csv
mkdir -p "$REPORTS"
echo "episode_name,route_id,rc,started,ended" > "$LEDGER"

EPISODES="h7_reception_01 h7_reception_02 h7_corridor_01 h7_corridor_02 h7_turn_01 h7_turn_02 h7_waiting_01 h7_waiting_02"

clean_dds () {
  # exact-PID kill of any orphan bag recorder (timeout kills python, not its child)
  local pids
  pids=$(pgrep -f "ros2 bag record")
  if [ -n "$pids" ]; then
    echo "[campaign] cleaning orphan recorders: $pids"
    kill $pids 2>/dev/null; sleep 3; kill -9 $pids 2>/dev/null
  fi
  # remove stale fastrtps shm ONLY when nothing ROS/Isaac is alive
  if ! pgrep -f "m3pro_ros2_bringup" >/dev/null && ! pgrep -f "ros2 bag record" >/dev/null; then
    rm -f /dev/shm/fastrtps_* /dev/shm/sem.fastrtps_* 2>/dev/null
  fi
}

for ep in $EPISODES; do
  avail=$(df --output=avail -BG /home/favl | tail -1 | tr -dc 0-9)
  if [ "${avail:-0}" -lt 100 ]; then
    echo "[campaign] DISK LOW ${avail}G (<100G) — aborting before $ep"; break
  fi
  clean_dds
  started=$(date -Iseconds)
  echo "===== EPISODE $ep START ($started, disk ${avail}G) ====="
  timeout 1800 "$PY" -u "$BR" --scene hospital --scene-gate --gnm-control \
    --route-follow "$RD/$ep.json" --holonomic-base --collision-report \
    --episode --episode-name "$ep" --goal-id h2_weave_J --steps 6000
  rc=$?
  ended=$(date -Iseconds)
  echo "===== EPISODE $ep EXIT rc=$rc ($ended) ====="
  echo "$ep,$ep,$rc,$started,$ended" >> "$LEDGER"
  clean_dds
  # rc!=0 = scene-gate fail (5) / timeout (124) / crash = systemic -> STOP the campaign.
  # rc==0 episodes that recorded a CONTACT are excluded post-hoc from metadata, not here.
  if [ "$rc" -ne 0 ]; then
    echo "[campaign] ABORT: $ep exited rc=$rc (systemic — gate/timeout/crash). Stopping."
    break
  fi
  sleep 5
done
echo "[campaign] DONE"
