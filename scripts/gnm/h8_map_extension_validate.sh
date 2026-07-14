#!/usr/bin/env bash
# H8 map-extension DRIVE VALIDATION campaign (in-envelope zones only, 1 pass each).
# Validation-only: spawn at candidate isaac-world pose (=bringup coord, NO navmap offset),
# scene-gate fail-closed, raised mount 0.12, bounded GNM-control drive, collision-report.
# Does NOT change CL_BOUND_XY. Far-west zones (|x|>6) are deferred, not run.
# Discipline: disk guard >=100G, bounded per-episode timeout, EXACT-PID cleanup (no pkill -f).
source /opt/ros/humble/setup.bash
REPO=/home/favl/robotics/gnm-vlnverse-baseline
cd "$REPO"
BR=scripts/robots/m3pro_ros2_bringup.py
RD=assets/experiments/hospital_h8_map_extension/drive_validation/routes
PY=$HOME/miniforge3/envs/isaac/bin/python
RAISE=0.12
LEDGER=assets/experiments/hospital_h8_map_extension/drive_validation/validation_ledger.csv
[ -f "$LEDGER" ] || echo "zone,episode_name,spawn_pose,rc,started,ended" > "$LEDGER"

# zone|spawn_pose (east_A already validated in a prior trial; not re-run here)
ZONES=(
  "west_C|-5.3,0.1,0"
  "val_A|-3.8,0.1,0"
  "lobby|-1.0,-0.2,0"
  "east_B|2.6,0.1,0"
  "lookalike_test|3.0,0.1,0"
)

wait_clear() {  # exact-process check, self-match-proof
  for _ in $(seq 1 60); do
    if ! ps -eo pid,cmd | grep 'isaac/bin/python -u' | grep 'm3pro_ros2_bringup' \
         | grep -v 'bash -c' | grep -v grep >/dev/null; then return 0; fi
    sleep 5
  done
  return 0
}

for entry in "${ZONES[@]}"; do
  zone="${entry%%|*}"; spawn="${entry##*|}"
  route="$RD/h8mx_${zone}_val.json"
  ep="h8mx_val_${zone}"
  if [ ! -f "$route" ]; then echo "[campaign] MISSING route $route — skip $zone"; continue; fi
  avail=$(df --output=avail -BG /home/favl | tail -1 | tr -dc 0-9)
  if [ "${avail:-0}" -lt 100 ]; then echo "[campaign] ABORT: disk ${avail}G <100G"; break; fi
  wait_clear
  started=$(date -Iseconds)
  echo "[campaign] === $zone spawn=$spawn disk=${avail}G $started ==="
  timeout 1200 "$PY" -u "$BR" --scene hospital --scene-gate --camera-raise "$RAISE" \
    --spawn-pose "$spawn" --gnm-control --route-follow "$route" --holonomic-base \
    --collision-report --episode --episode-name "$ep" --goal-id h2_weave_J --steps 4000
  rc=$?
  ended=$(date -Iseconds)
  echo "$zone,$ep,\"$spawn\",$rc,$started,$ended" >> "$LEDGER"
  echo "[campaign] $zone rc=$rc"
done
echo "[campaign] DONE"
