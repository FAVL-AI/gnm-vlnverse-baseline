#!/usr/bin/env bash
# H6 conversion driver: convert the 16 RECORDED_OK H6 rosbag episodes into
# Isaac-Hospital-ImageNav-v0 GNM format (front-camera). Uses the existing
# per-episode converter with the H4/H5 frame stride (12) so H6 is directly
# comparable. Conversion needs Python 3.10 (ROS 2 Humble ABI) with ROS sourced;
# training/eval later use the gnm_train env (numpy 2.x, reads the pickles).
#
# Writes a per-episode convert ledger (jsonl) and validates each output
# (>=1 frame + traj_data.pkl + goal.png + metadata.json). Recording/collection
# is the source of truth; this only transcodes. No training here.
# NOTE: no `set -u` — ROS 2 Humble setup.bash references unbound vars
# (AMENT_TRACE_SETUP_FILES ...) and would abort the script on source.
cd /home/favl/robotics/gnm-vlnverse-baseline
source /opt/ros/humble/setup.bash 2>/dev/null
PY=/usr/bin/python3.10
STRIDE=12
COL=assets/experiments/hospital_h2_collection_20260709
LEDGER="$COL/h6_convert_ledger.jsonl"
: > "$LEDGER"

DIRS=$(~/miniforge3/envs/isaac/bin/python -c "import json;[print(r['episode_dir']) for r in json.load(open('$COL/h6_recording_ledger.json')) if r.get('status')=='RECORDED_OK']")

n=0; ok=0; total=$(echo "$DIRS" | wc -w)
echo "[h6-convert] start converting $total episodes stride=$STRIDE (py3.10 + ROS Humble)"
for EP in $DIRS; do
  n=$((n+1)); base=$(basename "$EP")
  OUT="datasets/isaac_hospital_imagenav_v0/unassigned/$base"
  echo "[h6-convert] ($n/$total) $base"
  rm -rf "$OUT"
  timeout 600 "$PY" scripts/datasets/convert_hospital_rosbags_to_gnm.py "$EP" "$STRIDE" >/dev/null 2>&1
  rc=$?
  njpg=$(ls "$OUT"/*.jpg 2>/dev/null | wc -l)
  pkl=$([ -f "$OUT/traj_data.pkl" ] && echo 1 || echo 0)
  goal=$([ -f "$OUT/goal.png" ] && echo 1 || echo 0)
  meta=$([ -f "$OUT/metadata.json" ] && echo 1 || echo 0)
  if [ "$njpg" -gt 0 ] && [ "$pkl" = 1 ] && [ "$goal" = 1 ] && [ "$meta" = 1 ] && [ "$rc" = 0 ]; then
    complete=true; ok=$((ok+1)); else complete=false; fi
  printf '{"episode":"%s","rc":%s,"n_jpg":%s,"pkl":%s,"goal":%s,"meta":%s,"complete":%s}\n' \
    "$base" "$rc" "$njpg" "$pkl" "$goal" "$meta" "$complete" >> "$LEDGER"
  echo "[h6-convert]   rc=$rc n_jpg=$njpg pkl=$pkl goal=$goal meta=$meta complete=$complete"
done
echo "[h6-convert] DONE $ok/$total complete -> $LEDGER"
[ "$ok" = "$total" ] && exit 0 || exit 3
