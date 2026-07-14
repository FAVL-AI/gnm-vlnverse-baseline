#!/usr/bin/env bash
# H8 map-extension RECOVERY drive-validation (in-envelope only; CL_BOUND_XY unchanged).
# val_A retry (honest, same spawn) + two mid-west probes to locate the drivable boundary and
# recover a clean val/train zone set. Validation-only: no H8-S collection, no training.
# Discipline: disk guard >=100G, bounded per-episode timeout, EXACT-PID cleanup (no pkill -f).
source /opt/ros/humble/setup.bash
REPO=/home/favl/robotics/gnm-vlnverse-baseline
cd "$REPO"
BR=scripts/robots/m3pro_ros2_bringup.py
RD=assets/experiments/hospital_h8_map_extension/drive_validation/routes
PY=$HOME/miniforge3/envs/isaac/bin/python
RAISE=0.12
LEDGER=assets/experiments/hospital_h8_map_extension/drive_validation/recovery_ledger.csv
[ -f "$LEDGER" ] || echo "zone,episode_name,spawn_pose,rc,started,ended" > "$LEDGER"

ZONES=(
  "val_A_retry|-3.8,0.1,0"
  "midwest_A|-2.8,-0.2,0"
  "midwest_B|-3.4,-0.2,0"
)

wait_clear() {
  for _ in $(seq 1 60); do
    if ! ps -eo pid,cmd | grep 'isaac/bin/python -u' | grep 'm3pro_ros2_bringup' \
         | grep -v 'bash -c' | grep -v grep >/dev/null; then return 0; fi
    sleep 5
  done
}

for entry in "${ZONES[@]}"; do
  zone="${entry%%|*}"; spawn="${entry##*|}"
  route="$RD/h8mx_${zone}.json"; ep="h8mx_val_${zone}"
  [ -f "$route" ] || { echo "[recover] MISSING $route — skip"; continue; }
  avail=$(df --output=avail -BG /home/favl | tail -1 | tr -dc 0-9)
  [ "${avail:-0}" -ge 100 ] || { echo "[recover] ABORT disk ${avail}G<100G"; break; }
  wait_clear
  started=$(date -Iseconds)
  echo "[recover] === $zone spawn=$spawn disk=${avail}G $started ==="
  timeout 1200 "$PY" -u "$BR" --scene hospital --scene-gate --camera-raise "$RAISE" \
    --spawn-pose "$spawn" --gnm-control --route-follow "$route" --holonomic-base \
    --collision-report --episode --episode-name "$ep" --goal-id h2_weave_J --steps 4000
  rc=$?
  echo "$zone,$ep,\"$spawn\",$rc,$started,$(date -Iseconds)" >> "$LEDGER"
  echo "[recover] $zone rc=$rc"
done
echo "[recover] DONE"
