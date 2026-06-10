#!/usr/bin/env python3
"""
ros2_to_vnt_converter.py — Convert ROS2 bags to ViNT/GNM/NoMaD training format.

Converts ROS2 bag files (from Gazebo, Isaac Sim ROS2 bridge, or real M3Pro)
into the official visualnav-transformer training schema:

    dataset_dir/
    ├── traj_0000/
    │   ├── 0.jpg
    │   ├── 1.jpg
    │   └── traj_data.pkl      {"position": [T,2], "yaw": [T]}
    ├── traj_0001/
    │   └── ...
    ├── data_splits/
    │   └── <dataset_name>/
    │       ├── train/traj_names.txt
    │       └── test/traj_names.txt
    └── data_config.yaml

Topic mapping (auto-detected from bag):
    Camera   : /usb_cam/image_raw | /camera/image_raw | /rgb/image_raw
    Odometry : /odom | /odometry/filtered | /diff_drive/odom
    Scan     : /scan (optional — written to separate file, NOT given to VNT)
    Goal     : /goal_pose (optional — marks episode boundaries)

Episode splitting strategies:
  --split-on-goal    New episode each time /goal_pose is received
  --split-distance N New episode every N metres of travel
  --split-time T     New episode every T seconds
  --split-steps N    New episode every N steps (after resampling)

Resampling:
  Timestamps align camera + odometry via nearest-neighbour at fixed dt (default 0.1s).
  Yaw is unwrapped and then re-wrapped to [-π, π].

Usage
-----
  # Single bag → GNM format:
  python scripts/visualnav/ros2_to_vnt_converter.py \\
      --bag recordings/hospital_run_01.db3 \\
      --output data/gnm_hospital_dataset \\
      --dataset-name fleetsafe \\
      --resample-dt 0.1 \\
      --split-distance 15.0 \\
      --eval-fraction 0.1

  # Multiple bags:
  python scripts/visualnav/ros2_to_vnt_converter.py \\
      --bag recordings/*.db3 \\
      --output data/gnm_hospital_dataset \\
      --dataset-name fleetsafe

  # After conversion, fine-tune GNM:
  cd third_party/visualnav-transformer/train
  python train.py \\
      --config vint_train/config/gnm.yaml \\
      --data-folder ../../../data/gnm_hospital_dataset
"""
from __future__ import annotations

import argparse
import csv
import math
import pickle
import random
import struct
import sys
from pathlib import Path
from typing import Any

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

# ── Image resize target (GNM default) ─────────────────────────────────────────
_GNM_IMG_W, _GNM_IMG_H = 85, 64


# ── Quaternion → yaw ──────────────────────────────────────────────────────────

def _quat_to_yaw(qx: float, qy: float, qz: float, qw: float) -> float:
    siny_cosp = 2.0 * (qw * qz + qx * qy)
    cosy_cosp = 1.0 - 2.0 * (qy * qy + qz * qz)
    return math.atan2(siny_cosp, cosy_cosp)


def _wrap_angle(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


# ── ROS2 bag reader ───────────────────────────────────────────────────────────

class BagReader:
    """
    Reads ROS2 sqlite3 bags.  Falls back to rosbag2_py if available.
    """

    def __init__(self, bag_path: Path):
        self.bag_path = bag_path
        self._use_rosbag2 = False
        try:
            import rosbag2_py  # noqa: F401
            self._use_rosbag2 = True
        except ImportError:
            pass

    def read_messages(
        self,
        topics: list[str],
    ):
        """
        Yields (topic, timestamp_ns, raw_bytes) for each matching message.
        raw_bytes can be decoded with the CDR deserialiser for the topic type.
        """
        if self._use_rosbag2:
            yield from self._read_rosbag2(topics)
        else:
            yield from self._read_sqlite3(topics)

    def _read_rosbag2(self, topics: list[str]):
        import rosbag2_py
        reader = rosbag2_py.SequentialReader()
        opts   = rosbag2_py.StorageOptions(
            uri=str(self.bag_path), storage_id="sqlite3"
        )
        copt   = rosbag2_py.ConverterOptions(
            input_serialization_format="cdr",
            output_serialization_format="cdr",
        )
        reader.open(opts, copt)
        type_map = {
            info.name: info.type
            for info in reader.get_all_topics_and_types()
        }
        while reader.has_next():
            topic, data, t_ns = reader.read_next()
            if topic in topics:
                yield topic, t_ns, data

    def _read_sqlite3(self, topics: list[str]):
        """Pure-Python sqlite3 fallback — does not deserialise CDR automatically."""
        import sqlite3
        db = Path(self.bag_path)
        if db.is_dir():
            candidates = list(db.glob("*.db3"))
            if not candidates:
                raise FileNotFoundError(f"No .db3 file in {db}")
            db = candidates[0]

        conn = sqlite3.connect(str(db))
        cur  = conn.cursor()

        cur.execute("SELECT id, name FROM topics")
        topic_ids = {name: tid for tid, name in cur.fetchall() if name in topics}

        if not topic_ids:
            conn.close()
            return

        placeholders = ",".join("?" * len(topic_ids))
        cur.execute(
            f"SELECT topic_id, timestamp, data FROM messages "
            f"WHERE topic_id IN ({placeholders}) ORDER BY timestamp",
            list(topic_ids.values()),
        )
        id_to_name = {v: k for k, v in topic_ids.items()}
        for topic_id, t_ns, data in cur.fetchall():
            yield id_to_name[topic_id], t_ns, bytes(data)
        conn.close()


# ── CDR deserialiser (minimal, Image + Odometry only) ────────────────────────

class _CDR:
    """Minimal CDR deserialiser for sensor_msgs/Image and nav_msgs/Odometry."""

    def __init__(self, data: bytes):
        self.data   = data
        self.offset = 4   # skip 4-byte CDR header

    def _read(self, fmt: str) -> tuple:
        size = struct.calcsize(fmt)
        self.offset = (self.offset + size - 1) & ~(size - 1)  # align
        vals = struct.unpack_from(fmt, self.data, self.offset)
        self.offset += size
        return vals

    def read_uint32(self) -> int: return self._read("<I")[0]
    def read_float64(self) -> float: return self._read("<d")[0]
    def read_float32(self) -> float: return self._read("<f")[0]
    def read_bytes(self, n: int) -> bytes:
        b = self.data[self.offset: self.offset + n]
        self.offset += n
        return b
    def read_string(self) -> str:
        n = self.read_uint32()
        s = self.data[self.offset: self.offset + n]
        self.offset += n
        return s.decode("utf-8", errors="replace").rstrip("\x00")

    def read_time(self) -> float:
        sec  = self._read("<I")[0]
        nsec = self._read("<I")[0]
        return sec + nsec * 1e-9

    @classmethod
    def parse_image(cls, data: bytes) -> dict | None:
        """Parse sensor_msgs/msg/Image CDR bytes."""
        try:
            r = cls(data)
            # header: time stamp + frame_id
            r.read_time()
            frame_id = r.read_string()
            height = r.read_uint32()
            width  = r.read_uint32()
            encoding = r.read_string()
            is_bigendian = r._read("<B")[0]
            step   = r.read_uint32()
            n_data = r.read_uint32()
            img_bytes = r.read_bytes(n_data)
            return {
                "height":    height,
                "width":     width,
                "encoding":  encoding,
                "step":      step,
                "data":      img_bytes,
            }
        except Exception:
            return None

    @classmethod
    def parse_odometry(cls, data: bytes) -> dict | None:
        """Parse nav_msgs/msg/Odometry CDR bytes."""
        try:
            r = cls(data)
            # header
            r.read_time()
            r.read_string()  # frame_id
            r.read_string()  # child_frame_id
            # pose with covariance
            x   = r.read_float64()
            y   = r.read_float64()
            z   = r.read_float64()
            qx  = r.read_float64()
            qy  = r.read_float64()
            qz  = r.read_float64()
            qw  = r.read_float64()
            return {"x": x, "y": y, "qx": qx, "qy": qy, "qz": qz, "qw": qw}
        except Exception:
            return None


# ── Image decoder ─────────────────────────────────────────────────────────────

def _decode_image(raw: dict, target_w: int, target_h: int) -> "np.ndarray | None":
    """Convert raw image dict → RGB numpy array, resized."""
    try:
        import cv2
        h, w    = raw["height"], raw["width"]
        enc     = raw["encoding"].lower()
        data    = np.frombuffer(raw["data"], dtype=np.uint8)

        if enc in ("rgb8",):
            img = data.reshape(h, w, 3)
        elif enc in ("bgr8",):
            img = data.reshape(h, w, 3)
            img = img[:, :, ::-1]
        elif enc in ("mono8",):
            img = np.stack([data.reshape(h, w)] * 3, axis=-1)
        elif enc in ("rgb16", "bgr16"):
            arr = data.view(np.uint16).reshape(h, w, 3)
            img = (arr >> 8).astype(np.uint8)
            if enc == "bgr16":
                img = img[:, :, ::-1]
        else:
            return None

        img = cv2.resize(img, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
        return img

    except ImportError:
        # Fallback: PIL
        try:
            from PIL import Image as PILImage
            import io
            h, w, enc = raw["height"], raw["width"], raw["encoding"]
            data = raw["data"]
            if enc in ("rgb8", "bgr8", "mono8"):
                mode = {"rgb8": "RGB", "bgr8": "RGB", "mono8": "L"}[enc]
                img = PILImage.frombytes(mode, (w, h), bytes(data))
                if enc == "bgr8":
                    r, g, b = img.split()
                    img = PILImage.merge("RGB", (b, g, r))
                if mode == "L":
                    img = img.convert("RGB")
                img = img.resize((target_w, target_h), PILImage.BILINEAR)
                return np.array(img)
        except Exception:
            return None
    except Exception:
        return None


# ── Interpolation ─────────────────────────────────────────────────────────────

def _interpolate_odom(
    odoms: list[dict],
    times: list[float],
    t: float,
) -> dict | None:
    """Linear interpolation of pose at time t."""
    if not times:
        return None
    idx = np.searchsorted(times, t, side="right") - 1
    if idx < 0:
        return odoms[0]
    if idx >= len(times) - 1:
        return odoms[-1]
    t0, t1 = times[idx], times[idx + 1]
    dt = t1 - t0
    if dt < 1e-9:
        return odoms[idx]
    w = (t - t0) / dt
    a, b = odoms[idx], odoms[idx + 1]
    # Yaw interpolation: unwrap to avoid ±π jump
    dyaw = _wrap_angle(b["yaw"] - a["yaw"])
    return {
        "x":   a["x"]   + w * (b["x"]   - a["x"]),
        "y":   a["y"]   + w * (b["y"]   - a["y"]),
        "yaw": _wrap_angle(a["yaw"] + w * dyaw),
    }


# ── Single-bag converter ──────────────────────────────────────────────────────

class BagConverter:
    def __init__(
        self,
        output_dir:     Path,
        resample_dt:    float = 0.10,
        img_size:       tuple[int, int] = (_GNM_IMG_W, _GNM_IMG_H),
        split_distance: float | None = None,
        split_time:     float | None = None,
        split_steps:    int | None   = None,
        min_traj_steps: int          = 10,
        cam_topics:     list[str]    = None,
        odom_topics:    list[str]    = None,
    ):
        self.output_dir     = output_dir
        self.resample_dt    = resample_dt
        self.img_size       = img_size
        self.split_distance = split_distance
        self.split_time     = split_time
        self.split_steps    = split_steps
        self.min_traj_steps = min_traj_steps
        self.cam_topics     = cam_topics or [
            "/usb_cam/image_raw",
            "/camera/image_raw",
            "/rgb/image_raw",
            "/camera/color/image_raw",
        ]
        self.odom_topics = odom_topics or [
            "/odom",
            "/odometry/filtered",
            "/diff_drive/odom",
            "/odom_combined",
        ]

    def convert(self, bag_path: Path, start_traj_idx: int = 0) -> list[str]:
        """Convert bag → trajectories. Returns list of traj dir names."""
        reader = BagReader(bag_path)
        all_topics = self.cam_topics + self.odom_topics

        # First pass: collect all raw messages
        img_events:  list[tuple[float, bytes]] = []
        odom_events: list[tuple[float, bytes]] = []

        print(f"  Reading {bag_path.name} …")
        for topic, t_ns, data in reader.read_messages(all_topics):
            t_s = t_ns * 1e-9
            if topic in self.cam_topics:
                img_events.append((t_s, data))
            elif topic in self.odom_topics:
                odom_events.append((t_s, data))

        print(f"    {len(img_events)} images  |  {len(odom_events)} odom messages")

        if not img_events or not odom_events:
            print("    SKIP: no image or odom data")
            return []

        # Decode odometry
        odoms_raw: list[dict] = []
        odom_times: list[float] = []
        for t_s, data in sorted(odom_events):
            od = _CDR.parse_odometry(data)
            if od:
                odoms_raw.append({
                    "x":   od["x"],
                    "y":   od["y"],
                    "yaw": _quat_to_yaw(od["qx"], od["qy"], od["qz"], od["qw"]),
                })
                odom_times.append(t_s)

        if not odoms_raw:
            print("    SKIP: odometry decode failed")
            return []

        # Sort images
        img_events.sort()
        odom_times_arr = np.array(odom_times)

        # Resample camera timestamps at fixed dt
        t0     = max(img_events[0][0], odom_times[0])
        t_end  = min(img_events[-1][0], odom_times[-1])
        sample_times = np.arange(t0, t_end, self.resample_dt)

        # Match image to each sample time
        img_times = np.array([t for t, _ in img_events])
        img_idx   = np.searchsorted(img_times, sample_times, side="left")
        img_idx   = np.clip(img_idx, 0, len(img_events) - 1)

        # Build synchronised steps
        steps: list[dict] = []
        for i, t_s in enumerate(sample_times):
            od = _interpolate_odom(odoms_raw, odom_times, t_s)
            if od is None:
                continue
            img_bytes = img_events[img_idx[i]][1]
            img_raw   = _CDR.parse_image(img_bytes)
            if img_raw is None:
                continue
            steps.append({"t": t_s, "x": od["x"], "y": od["y"], "yaw": od["yaw"],
                          "img_raw": img_raw})

        print(f"    {len(steps)} resampled steps at dt={self.resample_dt}s")

        # Split into trajectories
        trajs = self._split_steps(steps)
        traj_names: list[str] = []

        for traj_steps in trajs:
            if len(traj_steps) < self.min_traj_steps:
                continue
            traj_name = f"ep_{start_traj_idx:04d}"
            traj_dir  = self.output_dir / traj_name
            traj_dir.mkdir(parents=True, exist_ok=True)

            positions: list[list[float]] = []
            yaws:      list[float]       = []
            W, H = self.img_size

            for i, step in enumerate(traj_steps):
                img = _decode_image(step["img_raw"], W, H)
                if img is None:
                    continue
                _save_jpg(img, traj_dir / f"{i}.jpg")
                positions.append([step["x"], step["y"]])
                yaws.append(step["yaw"])

            if len(positions) < self.min_traj_steps:
                import shutil
                shutil.rmtree(traj_dir, ignore_errors=True)
                continue

            traj_data = {
                "position": np.array(positions, dtype=np.float32),
                "yaw":      np.array(yaws,      dtype=np.float32),
            }
            with open(traj_dir / "traj_data.pkl", "wb") as f:
                pickle.dump(traj_data, f)

            path_m = float(np.sum(np.linalg.norm(
                np.diff(traj_data["position"], axis=0), axis=1
            )))
            print(f"    {traj_name}  T={len(positions)}  path={path_m:.2f}m")
            traj_names.append(traj_name)
            start_traj_idx += 1

        return traj_names

    def _split_steps(self, steps: list[dict]) -> list[list[dict]]:
        """Split a flat step list into trajectory segments."""
        if not steps:
            return []

        trajs: list[list[dict]] = []
        current: list[dict] = [steps[0]]
        traj_start_t = steps[0]["t"]
        accum_dist   = 0.0

        for prev, cur in zip(steps, steps[1:]):
            d = math.hypot(cur["x"] - prev["x"], cur["y"] - prev["y"])
            accum_dist += d

            split = False
            if self.split_distance and accum_dist >= self.split_distance:
                split = True
            if self.split_time and (cur["t"] - traj_start_t) >= self.split_time:
                split = True
            if self.split_steps and len(current) >= self.split_steps:
                split = True

            if split:
                trajs.append(current)
                current       = [cur]
                traj_start_t  = cur["t"]
                accum_dist    = 0.0
            else:
                current.append(cur)

        if current:
            trajs.append(current)
        return trajs


def _save_jpg(img: "np.ndarray", path: Path) -> None:
    try:
        import cv2
        cv2.imwrite(str(path), img[:, :, ::-1])  # RGB → BGR for cv2
    except ImportError:
        try:
            from PIL import Image as PILImage
            PILImage.fromarray(img).save(str(path))
        except Exception:
            pass


# ── Dataset wrapper ───────────────────────────────────────────────────────────

def convert_dataset(
    bag_paths:     list[Path],
    output_dir:    Path,
    dataset_name:  str,
    eval_fraction: float = 0.1,
    resample_dt:   float = 0.10,
    split_distance: float | None = None,
    split_time:    float | None = None,
    split_steps:   int | None   = None,
    seed:          int  = 42,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    converter = BagConverter(
        output_dir     = output_dir,
        resample_dt    = resample_dt,
        split_distance = split_distance,
        split_time     = split_time,
        split_steps    = split_steps,
    )

    all_traj_names: list[str] = []
    traj_idx = 0
    for bag in bag_paths:
        names = converter.convert(bag, start_traj_idx=traj_idx)
        all_traj_names.extend(names)
        traj_idx += len(names)

    # Train/test split
    rng = random.Random(seed)
    shuffled = all_traj_names[:]
    rng.shuffle(shuffled)
    n_test  = max(1, int(len(shuffled) * eval_fraction)) if len(shuffled) > 1 else 0
    n_train = len(shuffled) - n_test
    train_names = shuffled[:n_train]
    test_names  = shuffled[n_train:]

    # Write traj_names.txt
    for split_name, names in [("train", train_names), ("test", test_names)]:
        split_dir = output_dir / "data_splits" / dataset_name / split_name
        split_dir.mkdir(parents=True, exist_ok=True)
        (split_dir / "traj_names.txt").write_text("\n".join(names) + "\n")

    # Write data_config.yaml
    try:
        import yaml
        config = {
            "dataset_name":            dataset_name,
            "data_folder":             str(output_dir.resolve()),
            "train":                   f"data_splits/{dataset_name}/train",
            "test":                    f"data_splits/{dataset_name}/test",
            "end_slack":               3,
            "goals_per_obs":           1,
            "negative_mining":         True,
            "metric_waypoint_spacing": 0.25,
        }
        with open(output_dir / "data_config.yaml", "w") as f:
            yaml.safe_dump(config, f)
    except ImportError:
        pass

    return {
        "n_trajectories": len(all_traj_names),
        "n_train":        n_train,
        "n_test":         n_test,
        "train_names":    train_names,
        "test_names":     test_names,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--bag",  nargs="+", type=Path, required=True,
                    help="ROS2 bag paths (.db3 files or bag directories)")
    ap.add_argument("--output", type=Path, required=True,
                    help="Output GNM dataset directory")
    ap.add_argument("--dataset-name", default="fleetsafe",
                    help="Dataset name for data_splits/ and data_config.yaml")
    ap.add_argument("--resample-dt", type=float, default=0.10,
                    help="Resampling interval in seconds (default: 0.10 = 10 Hz)")
    ap.add_argument("--split-distance", type=float, default=None,
                    help="Start new trajectory every N metres")
    ap.add_argument("--split-time",     type=float, default=None,
                    help="Start new trajectory every T seconds")
    ap.add_argument("--split-steps",    type=int,   default=None,
                    help="Start new trajectory every N resampled steps")
    ap.add_argument("--eval-fraction",  type=float, default=0.10,
                    help="Fraction of trajectories for test split (default: 0.1)")
    ap.add_argument("--seed",           type=int,   default=42)
    ap.add_argument("--cam-topic",  nargs="+", default=None,
                    help="Camera topic(s) to use (auto-detected if not set)")
    ap.add_argument("--odom-topic", nargs="+", default=None,
                    help="Odometry topic(s) to use (auto-detected if not set)")
    args = ap.parse_args()

    # Expand globs
    bag_paths: list[Path] = []
    for b in args.bag:
        if b.exists():
            bag_paths.append(b)
        else:
            import glob
            expanded = sorted(Path(p) for p in glob.glob(str(b)))
            if expanded:
                bag_paths.extend(expanded)
            else:
                print(f"WARNING: no files matching {b}", file=sys.stderr)

    if not bag_paths:
        print("ERROR: no bag files found", file=sys.stderr)
        return 1

    print()
    print("=" * 60)
    print("  ROS2 → ViNT/GNM/NoMaD Dataset Converter")
    print("=" * 60)
    print(f"  Bags        : {len(bag_paths)}")
    print(f"  Output      : {args.output}")
    print(f"  Dataset     : {args.dataset_name}")
    print(f"  Resample dt : {args.resample_dt}s ({1/args.resample_dt:.0f} Hz)")
    if args.split_distance:
        print(f"  Split every : {args.split_distance}m")
    elif args.split_time:
        print(f"  Split every : {args.split_time}s")
    elif args.split_steps:
        print(f"  Split every : {args.split_steps} steps")
    print()

    summary = convert_dataset(
        bag_paths     = bag_paths,
        output_dir    = args.output,
        dataset_name  = args.dataset_name,
        eval_fraction = args.eval_fraction,
        resample_dt   = args.resample_dt,
        split_distance = args.split_distance,
        split_time    = args.split_time,
        split_steps   = args.split_steps,
        seed          = args.seed,
    )

    print()
    print("=" * 60)
    print(f"  Done!")
    print(f"  Trajectories : {summary['n_trajectories']}")
    print(f"  Train        : {summary['n_train']}")
    print(f"  Test         : {summary['n_test']}")
    print()
    print("  To fine-tune GNM from official checkpoint:")
    print("    cd third_party/visualnav-transformer/train")
    print("    python train.py \\")
    print(f"        --config vint_train/config/gnm.yaml \\")
    print(f"        --data-folder {args.output.resolve()}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
