"""Convert one Isaac-hospital rosbag episode into Isaac-Hospital-ImageNav-v0
format (front-camera GNM-style episode).

Run with the SYSTEM python after sourcing ROS 2 Humble:
    python3 scripts/datasets/convert_hospital_rosbags_to_gnm.py <traj_dir> [every_n]

Frames come from the bag's /camera/image_raw; pose/yaw/action labels come
from the trajectory.jsonl aligned by order (both are the same rollout).
Output: datasets/isaac_hospital_imagenav_v0/<split_unassigned>/<episode>/
    0..N-1 .jpg, traj_data.pkl {position (N,2), yaw (N,)}, metadata.json,
    goal.png (copied from the goal registry), checksums.sha256

Camera regime: Yahboom FRONT RGB — never mixed with Kujiale top-down data.
"""

import hashlib
import io
import json
import math
import pickle
import sys
from pathlib import Path

import numpy as np
import rosbag2_py
from PIL import Image as PILImage
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import Image

REPO = Path(__file__).resolve().parents[2]
traj_dir = Path(sys.argv[1]).resolve()
every_n = int(sys.argv[2]) if len(sys.argv) > 2 else 12

meta = json.loads((traj_dir / "episode_metadata.json").read_text())
bag = REPO / meta["rosbag_path"] if not Path(meta["rosbag_path"]).is_absolute() \
    else Path(meta["rosbag_path"])
rows = [json.loads(l) for l in (traj_dir / "trajectory.jsonl").open()]
rows = [r for r in rows if r.get("robot_position_x") is not None]

ep = meta.get("episode_id", traj_dir.name)
out = REPO / "datasets/isaac_hospital_imagenav_v0/unassigned" / ep
out.mkdir(parents=True, exist_ok=True)

reader = rosbag2_py.SequentialReader()
reader.open(rosbag2_py.StorageOptions(uri=str(bag), storage_id="sqlite3"),
            rosbag2_py.ConverterOptions("", ""))
frames = []
n_seen = 0
while reader.has_next():
    topic, data, _ = reader.read_next()
    if topic != "/camera/image_raw":
        continue
    if n_seen % every_n == 0:
        msg = deserialize_message(data, Image)
        img = PILImage.frombytes("RGB", (msg.width, msg.height),
                                 bytes(msg.data))
        img.save(out / f"{len(frames)}.jpg", quality=90)
        frames.append(None)
    n_seen += 1

# align poses to frames by even sampling over the logged rollout rows
idx = np.linspace(0, len(rows) - 1, len(frames)).astype(int)
pos = np.array([[rows[i]["robot_position_x"], rows[i]["robot_position_y"]]
                for i in idx], dtype=np.float32)
yaw = np.array([rows[i].get("robot_yaw_rad") or
                math.atan2(rows[min(i+1, len(rows)-1)]["robot_position_y"]
                           - rows[i]["robot_position_y"],
                           rows[min(i+1, len(rows)-1)]["robot_position_x"]
                           - rows[i]["robot_position_x"])
                for i in idx], dtype=np.float32)
actions = [[rows[i].get("actual_linear_velocity_cmd"),
            rows[i].get("actual_angular_velocity_cmd")] for i in idx]
pickle.dump({"position": pos, "yaw": yaw}, open(out / "traj_data.pkl", "wb"))

goal_png = REPO / "assets/experiments/goals" / str(meta.get("goal_id")) / "goal_image.png"
if goal_png.exists():
    PILImage.open(goal_png).convert("RGB").save(out / "goal.png")

json.dump({"dataset": "Isaac-Hospital-ImageNav-v0",
           "camera": "Yahboom front RGB (Isaac Sim)",
           "episode_id": ep, "goal_id": meta.get("goal_id"),
           "source_bag": str(meta["rosbag_path"]),
           "source_trajectory": str(traj_dir.relative_to(REPO)),
           "n_frames": len(frames), "frame_stride": every_n,
           "actions_cmd_vel": actions,
           "final_d2g_m": meta.get("final_distance_to_goal_m"),
           "collisions": meta.get("total_collision_count"),
           "checkpoint": meta.get("policy_checkpoint"),
           "claim": "internal simulation dataset; not real-robot evidence"},
          open(out / "metadata.json", "w"), indent=2)
sha = "\n".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}"
                for p in sorted(out.iterdir())
                if p.name != "checksums.sha256")
(out / "checksums.sha256").write_text(sha + "\n")
print(f"converted {ep}: {len(frames)} frames, goal={meta.get('goal_id')}")
