#!/usr/bin/env bash
# scripts/gnm/collect_gnm_data.sh
# ─────────────────────────────────────────────────────────────────────────────
# Collect a GNM training episode from Isaac Sim or the Yahboom M3 Pro.
#
# Records:
#   /camera/image_raw   — RGB frames (main GNM input)
#   /odom               — Robot pose and velocity
#   /tf                 — Coordinate transforms
#   /cmd_vel            — Commands issued
#
# Output:
#   data/gnm_isaac_hospital_corridor/run_NNN/
#     bag/               ROS 2 bag
#     images/            Extracted PNG frames
#     odom.csv           Odometry log
#     cmd_vel.csv        Command log
#     topomap/           Goal images for GNM topological navigation
#     metadata.json      Scene, robot, camera, and run settings
#     safety_certificates.jsonl   FleetSafe safety state per step
#
# Usage:
#   bash scripts/gnm/collect_gnm_data.sh
#   bash scripts/gnm/collect_gnm_data.sh --robot real   # use M3 Pro
#   bash scripts/gnm/collect_gnm_data.sh --scene warehouse_aisle
#   bash scripts/gnm/collect_gnm_data.sh --run-id 005
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ROBOT="sim"
SCENE="hospital_corridor"
RUN_ID=""
DURATION=120    # seconds to record

while [[ $# -gt 0 ]]; do
  case "$1" in
    --robot)    ROBOT="$2";    shift 2 ;;
    --scene)    SCENE="$2";    shift 2 ;;
    --run-id)   RUN_ID="$2";   shift 2 ;;
    --duration) DURATION="$2"; shift 2 ;;
    *) echo "[WARN] Unknown arg: $1"; shift ;;
  esac
done

# ── Output directory ──────────────────────────────────────────────────────────
BASE_DIR="${REPO_ROOT}/data/gnm_isaac_${SCENE}"
if [[ -z "${RUN_ID}" ]]; then
  N=1
  while [[ -d "${BASE_DIR}/run_$(printf '%03d' ${N})" ]]; do N=$((N+1)); done
  RUN_ID="$(printf '%03d' ${N})"
fi

RUN_DIR="${BASE_DIR}/run_${RUN_ID}"
BAG_DIR="${RUN_DIR}/bag"
IMG_DIR="${RUN_DIR}/images"
TOPO_DIR="${RUN_DIR}/topomap"

mkdir -p "${BAG_DIR}" "${IMG_DIR}" "${TOPO_DIR}"

echo "=== FleetSafe GNM Data Collection ==="
echo "  Robot:  ${ROBOT}"
echo "  Scene:  ${SCENE}"
echo "  Run:    run_${RUN_ID}"
echo "  Output: ${RUN_DIR}"
echo ""

# ── Write metadata ─────────────────────────────────────────────────────────────
cat > "${RUN_DIR}/metadata.json" <<METAEOF
{
  "run_id": "${RUN_ID}",
  "scene": "${SCENE}",
  "robot": "${ROBOT}",
  "camera_topic": "/camera/image_raw",
  "odom_topic": "/odom",
  "cmd_vel_topic": "/cmd_vel",
  "image_size": [320, 240],
  "control_hz": 4.0,
  "collection_date": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "notes": ""
}
METAEOF

# ── ROS 2 check ───────────────────────────────────────────────────────────────
if ! command -v ros2 >/dev/null 2>&1; then
  if [[ -f "/opt/ros/humble/setup.bash" ]]; then
    source /opt/ros/humble/setup.bash
    echo "[gnm_collect] Sourced ROS 2 Humble from /opt/ros/humble"
  else
    echo "❌ ROS 2 not found. Source your ROS 2 workspace first:"
    echo "   source /opt/ros/humble/setup.bash"
    exit 1
  fi
fi

if [[ -f "${HOME}/ros2_ws/install/setup.bash" ]]; then
  source "${HOME}/ros2_ws/install/setup.bash"
fi

# ── Check topics ──────────────────────────────────────────────────────────────
echo "Checking ROS 2 topics (5 s timeout)..."
TOPICS_OK=true
for TOPIC in /camera/image_raw /odom /cmd_vel; do
  if timeout 5 ros2 topic hz "${TOPIC}" --once 2>/dev/null | grep -q "average rate"; then
    echo "  ✓ ${TOPIC}"
  else
    echo "  ⚠ ${TOPIC} — not publishing (check Isaac bridge or robot)"
    TOPICS_OK=false
  fi
done

if ! $TOPICS_OK; then
  echo ""
  echo "⚠️  Some topics are missing. Continuing anyway (bag may be incomplete)."
  echo "   To check Isaac bridge: ros2 topic list"
fi

# ── Record ROS bag ─────────────────────────────────────────────────────────────
echo ""
echo "Recording for ${DURATION}s to ${BAG_DIR}..."
echo "Press Ctrl+C to stop early."
echo ""

timeout "${DURATION}" ros2 bag record \
  /camera/image_raw \
  /odom \
  /tf \
  /cmd_vel \
  -o "${BAG_DIR}/gnm_${SCENE}_run_${RUN_ID}" \
  2>&1 || true

echo ""
echo "Recording complete."

# ── Extract images from bag ────────────────────────────────────────────────────
echo ""
echo "Extracting images from bag..."
python3 - <<PYEOF 2>/dev/null || echo "  [WARN] Image extraction skipped (rclpy or cv_bridge not available)"
import sys
sys.path.insert(0, "${REPO_ROOT}")
import os, pathlib

bag_path = pathlib.Path("${BAG_DIR}")
img_dir  = pathlib.Path("${IMG_DIR}")
img_dir.mkdir(exist_ok=True)

try:
    from rosbags.rosbag2 import Reader
    from rosbags.typesys import Stores, get_typestore

    typestore = get_typestore(Stores.ROS2_HUMBLE)
    bags = sorted(bag_path.glob("gnm_*/"))
    if not bags:
        print("  No bag found yet.")
    else:
        with Reader(bags[0]) as reader:
            count = 0
            for connection, timestamp, rawdata in reader.messages():
                if connection.topic == "/camera/image_raw":
                    msg = typestore.deserialize_cdr(rawdata, connection.msgtype)
                    import numpy as np
                    frame = np.frombuffer(msg.data, dtype=np.uint8).reshape(
                        msg.height, msg.width, -1
                    )[:, :, :3]
                    import cv2
                    cv2.imwrite(str(img_dir / f"frame_{count:06d}.png"), frame[:, :, ::-1])
                    count += 1
                    if count % 50 == 0:
                        print(f"  Extracted {count} frames...")
        print(f"  ✓ Extracted {count} frames to {img_dir}")
except ImportError:
    print("  [INFO] rosbags not installed — skipping image extraction")
    print("         pip install rosbags  to enable")
PYEOF

# ── Convert to GNM format ──────────────────────────────────────────────────────
echo ""
echo "Converting to GNM/VisualNav format..."
if command -v python3 >/dev/null && python3 -c "import fleet_safe_vla" 2>/dev/null; then
  python3 "${REPO_ROOT}/scripts/visualnav/ros2_to_vnt_converter.py" \
    --bag-dir "${BAG_DIR}" \
    --output-dir "${RUN_DIR}" \
    2>&1 | tail -10 || echo "  [WARN] Conversion failed — run manually after recording"
else
  echo "  [INFO] FleetSafe env not active — skipping auto-conversion"
  echo "         Run manually: python scripts/visualnav/ros2_to_vnt_converter.py --bag-dir ${BAG_DIR} --output-dir ${RUN_DIR}"
fi

echo ""
echo "✅ Collection complete."
echo ""
echo "Run directory:"
echo "  ${RUN_DIR}"
echo ""
echo "Next steps:"
echo "  1. Review images:     ls ${IMG_DIR}"
echo "  2. Check odom/cmd:    ls ${RUN_DIR}/*.csv"
echo "  3. Prepare training:  python scripts/visualnav/convert_to_vnt_format.py --input ${RUN_DIR}"
echo "  4. Fine-tune GNM:     bash scripts/gnm/train_gnm.sh --data ${RUN_DIR}"
echo "  5. Smoke test:        python -m fleetsafe_vln.benchmark.episode_runner --platform isaac --task tasks/hospital_corridor.yaml --model gnm --safety log_only --log-dir runs/gnm_smoke_$(date +%Y%m%d)"
