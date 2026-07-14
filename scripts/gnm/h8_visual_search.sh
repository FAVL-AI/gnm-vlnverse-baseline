#!/usr/bin/env bash
source /opt/ros/humble/setup.bash
REPO=/home/favl/robotics/gnm-vlnverse-baseline; cd "$REPO"
BR=scripts/robots/m3pro_ros2_bringup.py
RD=assets/experiments/hospital_h8_map_extension/visual_gap/routes
PY=$HOME/miniforge3/envs/isaac/bin/python
LED=assets/experiments/hospital_h8_map_extension/visual_gap/search_ledger.csv
[ -f "$LED" ] || echo "zone,episode,spawn,rc,started,ended" > "$LED"
ZONES=("searchW1|1.0,0.1,3.14159" "searchW2|-2.0,-0.2,3.14159")
wc(){ for _ in $(seq 1 60); do ps -eo pid,cmd|grep 'isaac/bin/python -u'|grep m3pro_ros2_bringup|grep -v 'bash -c'|grep -v grep>/dev/null||return 0; sleep 5; done; }
for e in "${ZONES[@]}"; do
  z="${e%%|*}"; sp="${e##*|}"; rt="$RD/h8mx_${z}.json"; ep="h8mx_${z}"
  av=$(df --output=avail -BG /home/favl|tail -1|tr -dc 0-9); [ "${av:-0}" -ge 100 ]||{ echo "ABORT disk";break;}
  wc; st=$(date -Iseconds); echo "[search] === $z spawn=$sp $st ==="
  timeout 1200 "$PY" -u "$BR" --scene hospital --scene-gate --camera-raise 0.12 --spawn-pose "$sp" \
    --gnm-control --route-follow "$rt" --holonomic-base --collision-report --episode \
    --episode-name "$ep" --goal-id h2_weave_J --steps 4000
  echo "$z,$ep,\"$sp\",$?,$st,$(date -Iseconds)" >> "$LED"; echo "[search] $z done"
done
echo "[search] DONE"
