"""Extract /camera/image_raw frames from a rosbag2 into a PPM sequence.

Run with the SYSTEM python after sourcing ROS 2 Humble (rosbag2_py):
    python3 scripts/robots/extract_bag_frames.py <bag_dir> <out_dir> [every_n]

PPM (P6) needs no imaging libraries; assemble to mp4 separately, e.g.:
    <isaac-env-ffmpeg> -framerate 5 -i frame_%03d.ppm -pix_fmt yuv420p out.mp4
"""

import sys
from pathlib import Path

import rosbag2_py
from rclpy.serialization import deserialize_message
from sensor_msgs.msg import Image


def main():
    bag, out = Path(sys.argv[1]), Path(sys.argv[2])
    every_n = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    out.mkdir(parents=True, exist_ok=True)
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(bag), storage_id="sqlite3"),
                rosbag2_py.ConverterOptions("", ""))
    n_seen = n_saved = 0
    while reader.has_next():
        topic, data, _ = reader.read_next()
        if topic != "/camera/image_raw":
            continue
        if n_seen % every_n == 0:
            msg = deserialize_message(data, Image)
            assert msg.encoding == "rgb8", msg.encoding
            p = out / f"frame_{n_saved:03d}.ppm"
            with open(p, "wb") as f:
                f.write(f"P6\n{msg.width} {msg.height}\n255\n".encode())
                f.write(bytes(msg.data))
            n_saved += 1
        n_seen += 1
    print(f"saved {n_saved} frames from {n_seen} images -> {out}")


if __name__ == "__main__":
    main()
