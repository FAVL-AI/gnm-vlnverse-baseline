#!/usr/bin/env python3
"""
build_topomap.py — Build a GNM-format topological map for the Yahboom M3Pro.

The topological map is a sequence of images sampled from a recorded route.
During navigation, the model estimates distance between the current image and
each node, then uses Dijkstra's algorithm to select the next subgoal.

Three input modes:
  --from-episode   Build from a FleetSafe episode directory (images/step_*.jpg)
  --from-bag       Build from a ROS2 bag file (reads /usb_cam/image_raw)
  --from-camera    Build live from /usb_cam/image_raw (requires ROS2 running)

Output:
  topomaps/{name}/
    0.png, 1.png, 2.png, ...   node images (85×64 px, same as GNM input)
    topomap_meta.json          node count, dt, source info

Usage
-----
  # From a collected FleetSafe episode (recommended — no robot needed):
  python scripts/visualnav/build_topomap.py \\
      --from-episode data/training_episodes/gnm/hospital_corridor/fleetsafe/ep_0000 \\
      --name hospital_route_1 \\
      --dt 1.0

  # From a ROS2 bag recording:
  python scripts/visualnav/build_topomap.py \\
      --from-bag recordings/hospital_route.db3 \\
      --name hospital_route_2

  # Live from camera (teleoperate robot while running):
  python scripts/visualnav/build_topomap.py \\
      --from-camera \\
      --name hospital_route_live \\
      --dt 1.0
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Iterator

import numpy as np
from PIL import Image

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

# GNM image size (width, height)
_GNM_IMG_SIZE = (85, 64)
_DEFAULT_TOPOMAP_DIR = _REPO / "topomaps"


# ── Image sampling helpers ─────────────────────────────────────────────────────

def _sample_episode_images(episode_dir: Path, dt: float, step_dt: float = 0.25) -> list[Image.Image]:
    """
    Sample images from a FleetSafe episode directory.

    episode_dir: path with images/step_NNNNN.jpg
    dt         : seconds between samples (default 1.0)
    step_dt    : control loop period (1/Hz), default 0.25s (4 Hz)
    """
    img_dir  = episode_dir / "images"
    if not img_dir.exists():
        raise FileNotFoundError(f"No images/ folder in {episode_dir}")

    frames = sorted(img_dir.glob("step_*.jpg"))
    if not frames:
        raise FileNotFoundError(f"No step_*.jpg frames in {img_dir}")

    stride = max(1, int(round(dt / step_dt)))
    sampled = frames[::stride]
    print(f"  Episode: {len(frames)} frames → {len(sampled)} nodes (stride={stride}, dt={dt}s)")
    return [Image.open(f).convert("RGB") for f in sampled]


def _sample_bag_images(bag_path: Path, camera_topic: str, dt: float) -> list[Image.Image]:
    """
    Extract images from a ROS2 bag (.db3 or directory).

    Requires rosbag2_py or direct sqlite3 access for .db3 files.
    """
    import sqlite3, io

    bag_path = Path(bag_path)
    db_file = bag_path if bag_path.suffix == ".db3" else next(bag_path.glob("*.db3"), None)
    if db_file is None:
        raise FileNotFoundError(f"No .db3 file found at {bag_path}")

    try:
        conn  = sqlite3.connect(str(db_file))
        cur   = conn.cursor()
        cur.execute("SELECT id FROM topics WHERE name=?", (camera_topic,))
        row   = cur.fetchone()
        if row is None:
            available = [r[0] for r in cur.execute("SELECT name FROM topics").fetchall()]
            raise ValueError(f"Topic {camera_topic!r} not in bag. Available: {available}")
        topic_id = row[0]

        cur.execute(
            "SELECT timestamp, data FROM messages WHERE topic_id=? ORDER BY timestamp",
            (topic_id,)
        )
        rows = cur.fetchall()
        conn.close()
    except Exception as exc:
        raise RuntimeError(f"Could not read bag {db_file}: {exc}") from exc

    if not rows:
        raise ValueError(f"No messages for topic {camera_topic}")

    # Subsample at dt
    images   = []
    last_t   = -float("inf")
    dt_ns    = int(dt * 1e9)
    for ts_ns, raw in rows:
        if ts_ns - last_t < dt_ns:
            continue
        last_t = ts_ns
        try:
            img = _decode_ros_image(raw)
            images.append(img)
        except Exception:
            continue

    print(f"  Bag: {len(rows)} messages → {len(images)} nodes (dt={dt}s)")
    return images


def _decode_ros_image(raw: bytes) -> Image.Image:
    """Decode a serialised sensor_msgs/Image to PIL."""
    # Try to parse the CDR-serialised ROS2 message manually
    # ROS2 CDR header: 4 bytes (0,1,0,0 = little-endian CDR)
    # sensor_msgs/Image fields: header, height, width, encoding, is_bigendian, step, data
    import struct
    offset = 4  # skip CDR header
    # Skip header (seq=4, stamp=8, frame_id=4+N)
    offset += 4  # sec
    offset += 4  # nanosec
    frame_len = struct.unpack_from("<I", raw, offset)[0]; offset += 4
    offset   += frame_len + ((4 - frame_len % 4) % 4)  # frame_id + padding
    height   = struct.unpack_from("<I", raw, offset)[0]; offset += 4
    width    = struct.unpack_from("<I", raw, offset)[0]; offset += 4
    enc_len  = struct.unpack_from("<I", raw, offset)[0]; offset += 4
    encoding = raw[offset:offset+enc_len].decode("utf-8", errors="ignore"); offset += enc_len
    offset  += (4 - enc_len % 4) % 4
    offset  += 1   # is_bigendian
    offset  += 3   # padding
    step     = struct.unpack_from("<I", raw, offset)[0]; offset += 4
    data_len = struct.unpack_from("<I", raw, offset)[0]; offset += 4
    img_data = raw[offset:offset+data_len]

    if "rgb8" in encoding:
        pil = Image.frombytes("RGB", (width, height), img_data)
    elif "bgr8" in encoding:
        arr = np.frombuffer(img_data, np.uint8).reshape(height, width, 3)
        pil = Image.fromarray(arr[:, :, ::-1])
    elif "mono8" in encoding:
        pil = Image.frombytes("L", (width, height), img_data).convert("RGB")
    else:
        # Generic numpy fallback
        arr = np.frombuffer(img_data, np.uint8)
        if len(arr) == height * width * 3:
            pil = Image.fromarray(arr.reshape(height, width, 3))
        else:
            raise ValueError(f"Cannot decode encoding {encoding!r}")

    return pil


def _stream_live_images(
    camera_topic: str,
    dt: float,
    max_nodes: int,
) -> Iterator[Image.Image]:
    """
    Stream images from /usb_cam/image_raw via ROS2.
    Yields one PIL image every dt seconds.  Press Ctrl-C to stop.
    """
    try:
        import rclpy
        from rclpy.node import Node
        from sensor_msgs.msg import Image as RosImage
        from cv_bridge import CvBridge
    except ImportError as exc:
        raise ImportError(
            "ROS2 not available. Use --from-episode or --from-bag instead."
        ) from exc

    collected: list[Image.Image] = []
    bridge = CvBridge()

    class _Collector(Node):
        def __init__(self):
            super().__init__("topomap_collector")
            self._sub = self.create_subscription(
                RosImage, camera_topic, self._cb, 1)
            self._last = -float("inf")
            self._img  = None

        def _cb(self, msg: RosImage):
            now = time.time()
            if now - self._last >= dt:
                self._last = now
                cv_img = bridge.imgmsg_to_cv2(msg, "rgb8")
                pil    = Image.fromarray(cv_img)
                collected.append(pil)
                print(f"  Node {len(collected)}: saved image", end="\r", flush=True)
                if len(collected) >= max_nodes:
                    rclpy.shutdown()

    rclpy.init()
    node = _Collector()
    print(f"Collecting topological map nodes from {camera_topic}...")
    print(f"  Press Ctrl-C or drive {max_nodes} nodes to stop.")
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, Exception):
        pass
    finally:
        rclpy.shutdown()

    print(f"\n  Captured {len(collected)} nodes.")
    return iter(collected)


# ── Main builder ──────────────────────────────────────────────────────────────

def build_topomap(
    images: list[Image.Image],
    name: str,
    output_dir: Path,
    gnm_size: tuple[int, int] = _GNM_IMG_SIZE,
    source: str = "unknown",
) -> Path:
    """
    Save a list of PIL images as a GNM topological map.

    Returns the path to the topomap directory.
    """
    topomap_dir = output_dir / name
    if topomap_dir.exists():
        print(f"  Removing existing topomap: {topomap_dir}")
        shutil.rmtree(topomap_dir)
    topomap_dir.mkdir(parents=True)

    W, H = gnm_size
    for i, img in enumerate(images):
        resized = img.resize((W, H), Image.BILINEAR)
        resized.save(topomap_dir / f"{i}.png")

    meta = {
        "name":        name,
        "num_nodes":   len(images),
        "image_size":  list(gnm_size),
        "source":      source,
        "created_at":  time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with open(topomap_dir / "topomap_meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\n  Topomap saved: {topomap_dir}")
    print(f"  Nodes: {len(images)}  Size: {W}×{H}  Source: {source}")
    print(f"\n  To navigate:")
    print(f"    python scripts/visualnav/navigate_topomap.py \\")
    print(f"        --topomap {topomap_dir} \\")
    print(f"        --model gnm \\")
    print(f"        --fleetsafe")
    return topomap_dir


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--from-episode", type=Path,
                     metavar="EPISODE_DIR",
                     help="FleetSafe episode directory (images/step_*.jpg)")
    src.add_argument("--from-bag", type=Path,
                     metavar="BAG_PATH",
                     help="ROS2 bag file (.db3 or bag directory)")
    src.add_argument("--from-camera", action="store_true",
                     help="Capture live from /usb_cam/image_raw (ROS2 must be running)")

    p.add_argument("--name", type=str, default="topomap",
                   help="Topomap name (default: topomap)")
    p.add_argument("--output-dir", type=Path,
                   default=_DEFAULT_TOPOMAP_DIR,
                   help=f"Output directory (default: {_DEFAULT_TOPOMAP_DIR})")
    p.add_argument("--dt", type=float, default=1.0,
                   help="Seconds between nodes (default: 1.0)")
    p.add_argument("--camera-topic", type=str,
                   default="/usb_cam/image_raw",
                   help="Camera topic for --from-bag / --from-camera")
    p.add_argument("--max-nodes", type=int, default=500,
                   help="Max nodes for live capture (default: 500)")
    p.add_argument("--step-dt", type=float, default=0.25,
                   help="Episode control period in seconds (default: 0.25 = 4 Hz)")
    args = p.parse_args()

    print()
    print("=" * 60)
    print("  GNM Topological Map Builder — FleetSafe")
    print("=" * 60)

    images: list[Image.Image]

    if args.from_episode:
        ep_dir = Path(args.from_episode).resolve()
        if not ep_dir.exists():
            print(f"ERROR: Episode directory not found: {ep_dir}")
            return 1
        print(f"  Source: FleetSafe episode → {ep_dir}")
        images = _sample_episode_images(ep_dir, dt=args.dt, step_dt=args.step_dt)
        source = f"episode:{ep_dir.name}"

    elif args.from_bag:
        bag_path = Path(args.from_bag).resolve()
        if not bag_path.exists():
            print(f"ERROR: Bag not found: {bag_path}")
            return 1
        print(f"  Source: ROS2 bag → {bag_path}")
        images = _sample_bag_images(bag_path, camera_topic=args.camera_topic, dt=args.dt)
        source = f"bag:{bag_path.name}"

    else:  # --from-camera
        print(f"  Source: live camera ({args.camera_topic})")
        images = list(_stream_live_images(
            camera_topic=args.camera_topic,
            dt=args.dt,
            max_nodes=args.max_nodes,
        ))
        source = f"live:{args.camera_topic}"

    if not images:
        print("ERROR: No images collected.")
        return 1

    build_topomap(
        images,
        name=args.name,
        output_dir=args.output_dir,
        source=source,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
