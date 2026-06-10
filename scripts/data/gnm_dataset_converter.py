#!/usr/bin/env python3
"""
gnm_dataset_converter.py
=========================
Bidirectional converter between GNM training format, FleetSafe episode format,
and ROS2 bag files.

Supported conversions
---------------------
  gnm-to-fleetsafe   GNM traj folder  → FleetSafe episode directory
  fleetsafe-to-gnm   FleetSafe ep dir → GNM traj folder (for fine-tuning)
  ros2-bag-to-gnm    ROS2 .db3 bag    → GNM traj folder
  validate           Check a directory for GNM format compliance

GNM format
----------
Each trajectory is a directory containing:
  - Numbered JPEG images: 0.jpg, 1.jpg, 2.jpg, …
  - traj_data.pkl: {"position": np.array([[x,y],...], shape [T,2]),
                    "yaw": np.array([...], shape [T])}

FleetSafe episode format
------------------------
  ep_NNNN/
    images/step_NNNNN.jpg
    trajectory.csv   (step,x,y,yaw,dist_to_goal,min_obs_dist)
    actions.csv      (step,raw_vx,raw_wz,safe_vx,safe_wz,intervened,inference_ms,cbf_ms)
    metrics.json

Usage
-----
  python scripts/data/gnm_dataset_converter.py gnm-to-fleetsafe \\
      --input  data/gnm_datasets/gostanford2/traj_001 \\
      --output data/training_episodes

  python scripts/data/gnm_dataset_converter.py fleetsafe-to-gnm \\
      --input  data/training_episodes/gnm/hospital_corridor \\
      --output data/gnm_finetune

  python scripts/data/gnm_dataset_converter.py ros2-bag-to-gnm \\
      --bag    /path/to/recording.db3 \\
      --output data/gnm_datasets/yahboom_hospital \\
      --camera-topic /usb_cam/image_raw \\
      --odom-topic   /odom

  python scripts/data/gnm_dataset_converter.py validate \\
      --input  data/gnm_datasets/gostanford2/traj_001
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import pickle
import shutil
import struct
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

# Optional heavy imports are attempted at call time so the CLI can always load.

# ── Yahboom M3Pro mecanum kinematics ─────────────────────────────────────────
WHEEL_RADIUS_M = 0.048          # metres
LX = 0.0775                     # half wheelbase (front-back)
LY = 0.0850                     # half track width (left-right)


def mecanum_ik(vx: float, vy: float, wz: float) -> tuple[float, float, float, float]:
    """
    Mecanum inverse kinematics for Yahboom M3Pro.

    Parameters
    ----------
    vx : forward velocity (m/s)
    vy : lateral velocity (m/s, positive = left)
    wz : yaw rate (rad/s, positive = CCW)

    Returns
    -------
    (w_fl, w_fr, w_rl, w_rr) wheel angular velocities in rad/s.
    """
    k = (LX + LY)
    w_fl = (vx - vy - k * wz) / WHEEL_RADIUS_M
    w_fr = (vx + vy + k * wz) / WHEEL_RADIUS_M
    w_rl = (vx + vy - k * wz) / WHEEL_RADIUS_M
    w_rr = (vx - vy + k * wz) / WHEEL_RADIUS_M
    return w_fl, w_fr, w_rl, w_rr


def mecanum_fk(w_fl: float, w_fr: float, w_rl: float, w_rr: float) -> tuple[float, float, float]:
    """
    Mecanum forward kinematics for Yahboom M3Pro.

    Parameters
    ----------
    w_fl, w_fr, w_rl, w_rr : wheel angular velocities (rad/s)

    Returns
    -------
    (vx, vy, wz) body-frame velocities.
    """
    r = WHEEL_RADIUS_M
    k = LX + LY
    vx = r / 4.0 * (w_fl + w_fr + w_rl + w_rr)
    vy = r / 4.0 * (-w_fl + w_fr + w_rl - w_rr)
    wz = r / (4.0 * k) * (-w_fl + w_fr - w_rl + w_rr)
    return vx, vy, wz


# ── GNM format I/O ────────────────────────────────────────────────────────────

def load_traj_data(traj_dir: Path) -> dict[str, np.ndarray]:
    """
    Load traj_data.pkl from a GNM trajectory directory.

    Returns a dict with at minimum keys 'position' ([T,2]) and 'yaw' ([T]).
    Raises FileNotFoundError if the file does not exist.
    """
    pkl_path = traj_dir / "traj_data.pkl"
    if not pkl_path.exists():
        raise FileNotFoundError(f"traj_data.pkl not found in {traj_dir}")
    data = pickle.loads(pkl_path.read_bytes())
    # Normalise types
    if "position" in data:
        data["position"] = np.asarray(data["position"], dtype=np.float64)
    if "yaw" in data:
        data["yaw"] = np.asarray(data["yaw"], dtype=np.float64)
    return data


def save_traj_data(traj_dir: Path, positions: np.ndarray, yaws: np.ndarray) -> None:
    """
    Save positions and yaws as traj_data.pkl in *traj_dir*.

    Parameters
    ----------
    traj_dir  : output directory (will be created if needed)
    positions : np.ndarray shape [T, 2], dtype float64
    yaws      : np.ndarray shape [T],    dtype float64
    """
    traj_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "position": np.asarray(positions, dtype=np.float64),
        "yaw": np.asarray(yaws, dtype=np.float64),
    }
    (traj_dir / "traj_data.pkl").write_bytes(pickle.dumps(data, protocol=4))


def get_gnm_images(traj_dir: Path) -> list[Path]:
    """
    Return sorted list of image paths in a GNM trajectory directory.

    GNM numbers images as 0.jpg, 1.jpg, …  (sometimes .png).
    """
    jpgs = sorted(traj_dir.glob("*.jpg"), key=lambda p: int(p.stem))
    pngs = sorted(traj_dir.glob("*.png"), key=lambda p: int(p.stem))
    return jpgs if jpgs else pngs


# ── Validation ────────────────────────────────────────────────────────────────

def validate_gnm_format(traj_dir: Path) -> dict:
    """
    Validate that *traj_dir* is a well-formed GNM trajectory folder.

    Returns
    -------
    dict with keys:
      ok (bool)          — True if all checks pass
      n_images (int)     — number of image files found
      has_pkl (bool)     — traj_data.pkl present
      pkl_readable (bool)— pkl loads without error
      position_shape     — shape of position array (or None)
      yaw_shape          — shape of yaw array (or None)
      length_match (bool)— len(images) == len(positions)
      errors (list[str]) — list of error messages
      warnings (list[str])
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not traj_dir.exists():
        return {
            "ok": False,
            "errors": [f"Directory does not exist: {traj_dir}"],
            "warnings": [],
        }

    images = get_gnm_images(traj_dir)
    n_images = len(images)
    if n_images == 0:
        errors.append("No numbered JPG/PNG images found (expected 0.jpg, 1.jpg, …)")

    has_pkl = (traj_dir / "traj_data.pkl").exists()
    pkl_readable = False
    position_shape = None
    yaw_shape = None
    length_match = False

    if not has_pkl:
        errors.append("traj_data.pkl is missing")
    else:
        try:
            data = load_traj_data(traj_dir)
            pkl_readable = True

            if "position" not in data:
                errors.append("traj_data.pkl missing key 'position'")
            else:
                pos = data["position"]
                position_shape = list(pos.shape)
                if pos.ndim != 2 or pos.shape[1] != 2:
                    errors.append(
                        f"'position' should have shape [T,2]; got {pos.shape}"
                    )

            if "yaw" not in data:
                errors.append("traj_data.pkl missing key 'yaw'")
            else:
                yaw = data["yaw"]
                yaw_shape = list(yaw.shape)
                if yaw.ndim != 1:
                    errors.append(f"'yaw' should be 1-D; got shape {yaw.shape}")

            if "position" in data and "yaw" in data:
                T_pos = len(data["position"])
                T_yaw = len(data["yaw"])
                if T_pos != T_yaw:
                    errors.append(
                        f"position length ({T_pos}) != yaw length ({T_yaw})"
                    )
                if n_images > 0 and T_pos != n_images:
                    warnings.append(
                        f"Number of images ({n_images}) != trajectory length ({T_pos}). "
                        "This is allowed but may cause issues at training time."
                    )
                    length_match = T_pos == n_images
                else:
                    length_match = T_pos == n_images

        except Exception as exc:
            errors.append(f"traj_data.pkl read error: {exc}")

    # Check image naming sequence (0, 1, 2, … no gaps)
    if images:
        stems = [int(p.stem) for p in images]
        expected = list(range(len(stems)))
        if stems != expected:
            warnings.append(
                f"Image numbering has gaps or does not start at 0: {stems[:5]}…"
            )

    return {
        "ok": len(errors) == 0,
        "n_images": n_images,
        "has_pkl": has_pkl,
        "pkl_readable": pkl_readable,
        "position_shape": position_shape,
        "yaw_shape": yaw_shape,
        "length_match": length_match,
        "errors": errors,
        "warnings": warnings,
    }


# ── GNM → FleetSafe ───────────────────────────────────────────────────────────

def gnm_to_fleetsafe(
    gnm_traj_dir: Path | str,
    output_dir: Path | str,
    model_name: str = "gnm",
) -> Path:
    """
    Convert a GNM trajectory folder to a FleetSafe episode directory.

    Creates:
      <output_dir>/ep_NNNN/
        images/step_NNNNN.jpg
        trajectory.csv
        actions.csv           (velocities derived from position differences)
        metrics.json

    Parameters
    ----------
    gnm_traj_dir : path to a GNM trajectory folder
                   (must contain traj_data.pkl + numbered images)
    output_dir   : directory under which the episode folder is created.
                   The next available ep_NNNN name is chosen automatically.
    model_name   : label stored in metrics.json (default "gnm")

    Returns
    -------
    Path to the created episode directory.

    Raises
    ------
    FileNotFoundError   if traj_data.pkl or images are missing
    ValueError          if the trajectory data is malformed
    """
    gnm_traj_dir = Path(gnm_traj_dir).resolve()
    output_dir = Path(output_dir).resolve()

    # Validate source
    result = validate_gnm_format(gnm_traj_dir)
    if not result["ok"]:
        raise ValueError(
            f"Invalid GNM format in {gnm_traj_dir}: {result['errors']}"
        )

    data = load_traj_data(gnm_traj_dir)
    images = get_gnm_images(gnm_traj_dir)
    positions: np.ndarray = data["position"]   # [T, 2]
    yaws: np.ndarray = data["yaw"]             # [T]
    T = len(positions)

    # Auto-number episode
    output_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(output_dir.glob("ep_????"))
    ep_idx = len(existing)
    ep_dir = output_dir / f"ep_{ep_idx:04d}"
    ep_dir.mkdir(parents=True, exist_ok=True)
    img_dir = ep_dir / "images"
    img_dir.mkdir(exist_ok=True)

    # Copy images
    for i, src in enumerate(images[:T]):
        dst = img_dir / f"step_{i:05d}.jpg"
        shutil.copy2(src, dst)

    # Compute velocities from position differences (finite differences)
    # Assume uniform 4 Hz sampling (GNM default) — can be overridden
    dt = 0.25  # seconds between frames at 4 Hz

    # trajectory.csv
    traj_rows = ["step,x,y,yaw,dist_to_goal,min_obs_dist"]
    goal = positions[-1]  # use last point as notional goal
    for i in range(T):
        x, y = positions[i]
        yaw = yaws[i]
        dist = float(np.linalg.norm(goal - positions[i]))
        traj_rows.append(f"{i},{x:.6f},{y:.6f},{yaw:.6f},{dist:.6f},99.0")
    (ep_dir / "trajectory.csv").write_text("\n".join(traj_rows) + "\n")

    # actions.csv — derive vx, wz from consecutive positions/yaws
    action_rows = ["step,raw_vx,raw_wz,safe_vx,safe_wz,intervened,inference_ms,cbf_ms"]
    for i in range(T):
        if i + 1 < T:
            dx = positions[i + 1, 0] - positions[i, 0]
            dy = positions[i + 1, 1] - positions[i, 1]
            dist_step = math.hypot(dx, dy)
            vx = dist_step / dt
            dyaw = yaws[i + 1] - yaws[i]
            # Wrap to [-pi, pi]
            dyaw = (dyaw + math.pi) % (2 * math.pi) - math.pi
            wz = dyaw / dt
        else:
            vx, wz = 0.0, 0.0
        action_rows.append(
            f"{i},{vx:.6f},{wz:.6f},{vx:.6f},{wz:.6f},0,0.0,0.0"
        )
    (ep_dir / "actions.csv").write_text("\n".join(action_rows) + "\n")

    # metrics.json
    path_len = float(
        np.sum(np.linalg.norm(np.diff(positions, axis=0), axis=1))
    )
    metrics = {
        "model": model_name,
        "scene": gnm_traj_dir.name,
        "source": str(gnm_traj_dir),
        "conversion": "gnm_to_fleetsafe",
        "success": True,
        "collision": False,
        "steps": T,
        "path_length_m": round(path_len, 4),
        "time_s": round(T * dt, 3),
        "min_obstacle_dist_m": 99.0,
        "intervention_count": 0,
        "intervention_rate": 0.0,
        "dist_to_goal_final": 0.0,
        "image_size": [160, 120],
        "context_size": 5,
        "timestamp": time.time(),
    }
    (ep_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))

    print(f"  gnm-to-fleetsafe: {gnm_traj_dir.name} → {ep_dir}  (T={T})")
    return ep_dir


# ── FleetSafe → GNM ───────────────────────────────────────────────────────────

def _read_trajectory_csv(ep_dir: Path) -> tuple[np.ndarray, np.ndarray]:
    """
    Parse trajectory.csv and return (positions [T,2], yaws [T]).
    """
    csv_path = ep_dir / "trajectory.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"trajectory.csv not found in {ep_dir}")

    positions: list[list[float]] = []
    yaws: list[float] = []

    with csv_path.open() as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            positions.append([float(row["x"]), float(row["y"])])
            yaws.append(float(row["yaw"]))

    return np.array(positions, dtype=np.float64), np.array(yaws, dtype=np.float64)


def fleetsafe_to_gnm(
    episode_dir: Path | str,
    output_dir: Path | str,
    split_frac: float = 0.1,
) -> dict[str, list[Path]]:
    """
    Convert FleetSafe episode(s) to GNM training format.

    Accepts either a single episode directory (ep_NNNN/) or a parent directory
    containing multiple episode folders.  Writes one GNM traj_NNNN/ per episode
    under *output_dir* and creates a train/val split.

    Parameters
    ----------
    episode_dir : FleetSafe episode directory (ep_NNNN/) or parent thereof
    output_dir  : GNM output root; traj_NNNN/ folders are written here
    split_frac  : fraction of trajectories to hold out as val (default 0.1)

    Returns
    -------
    dict with keys 'train' and 'val', each a list of output Path objects.

    Raises
    ------
    FileNotFoundError if episode_dir does not exist
    ValueError        if no valid episodes are found
    """
    episode_dir = Path(episode_dir).resolve()
    output_dir = Path(output_dir).resolve()

    if not episode_dir.exists():
        raise FileNotFoundError(f"Episode directory not found: {episode_dir}")

    # Collect episode directories
    if (episode_dir / "trajectory.csv").exists():
        # Single episode
        ep_dirs = [episode_dir]
    else:
        # Parent — find all ep_NNNN subdirs
        ep_dirs = sorted(episode_dir.rglob("trajectory.csv"))
        ep_dirs = [p.parent for p in ep_dirs]

    if not ep_dirs:
        raise ValueError(f"No FleetSafe episodes found under {episode_dir}")

    print(f"  fleetsafe-to-gnm: {len(ep_dirs)} episode(s) → {output_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Count existing GNM trajs to avoid collisions
    existing = sorted(output_dir.glob("traj_????"))
    traj_offset = len(existing)

    converted: list[Path] = []
    for ep_dir in ep_dirs:
        try:
            positions, yaws = _read_trajectory_csv(ep_dir)
        except (FileNotFoundError, KeyError, ValueError) as exc:
            print(f"  [WARN] Skipping {ep_dir.name}: {exc}")
            continue

        T = len(positions)
        if T < 2:
            print(f"  [WARN] Skipping {ep_dir.name}: trajectory too short ({T} steps)")
            continue

        # Output trajectory dir
        traj_idx = traj_offset + len(converted)
        traj_dir = output_dir / f"traj_{traj_idx:04d}"
        traj_dir.mkdir(parents=True, exist_ok=True)

        # Copy images, renaming to GNM convention (0.jpg, 1.jpg, …)
        img_dir = ep_dir / "images"
        if img_dir.exists():
            src_images = sorted(img_dir.glob("step_*.jpg"))
            for gnm_idx, src in enumerate(src_images[:T]):
                dst = traj_dir / f"{gnm_idx}.jpg"
                shutil.copy2(src, dst)
        else:
            print(f"  [WARN] {ep_dir.name}: images/ directory not found; "
                  "traj_data.pkl will be written without images")

        save_traj_data(traj_dir, positions, yaws)

        # Write a small metadata sidecar for traceability
        meta = {
            "source_episode": str(ep_dir),
            "n_steps": T,
            "conversion": "fleetsafe_to_gnm",
            "timestamp": time.time(),
        }
        metrics_path = ep_dir / "metrics.json"
        if metrics_path.exists():
            try:
                meta["source_metrics"] = json.loads(metrics_path.read_text())
            except Exception:
                pass
        (traj_dir / "meta.json").write_text(json.dumps(meta, indent=2))

        converted.append(traj_dir)

    if not converted:
        raise ValueError("No episodes were successfully converted.")

    # Train / val split
    rng = np.random.default_rng(42)
    indices = rng.permutation(len(converted))
    n_val = max(1, int(len(converted) * split_frac))
    val_indices = set(indices[:n_val].tolist())

    split: dict[str, list[Path]] = {"train": [], "val": []}
    for i, path in enumerate(converted):
        key = "val" if i in val_indices else "train"
        split[key].append(path)

    # Write split manifest
    manifest = {
        "conversion": "fleetsafe_to_gnm",
        "source": str(episode_dir),
        "output": str(output_dir),
        "n_total": len(converted),
        "n_train": len(split["train"]),
        "n_val": len(split["val"]),
        "split_frac": split_frac,
        "train": [str(p) for p in split["train"]],
        "val": [str(p) for p in split["val"]],
        "timestamp": time.time(),
    }
    (output_dir / "split_manifest.json").write_text(json.dumps(manifest, indent=2))

    print(f"  Converted {len(converted)} trajectories: "
          f"{len(split['train'])} train / {len(split['val'])} val")
    return split


# ── ROS2 bag → GNM ────────────────────────────────────────────────────────────

def _try_import_rosbag2() -> Any | None:
    """Attempt to import rosbag2_py; return the module or None."""
    try:
        import rosbag2_py  # type: ignore
        return rosbag2_py
    except ImportError:
        return None


def _try_import_cv_bridge() -> Any | None:
    try:
        from cv_bridge import CvBridge  # type: ignore
        return CvBridge()
    except ImportError:
        return None


def _read_bag_via_sqlite3(
    bag_path: Path,
    camera_topic: str,
    odom_topic: str,
    target_hz: float = 4.0,
) -> tuple[list[tuple[int, bytes]], list[tuple[int, float, float, float]]]:
    """
    Read a ROS2 .db3 bag file directly via sqlite3.

    Returns
    -------
    images : list of (timestamp_ns, jpeg_bytes)
    odoms  : list of (timestamp_ns, x, y, yaw)
    """
    import sqlite3
    import struct as _struct

    db_path = bag_path
    if bag_path.is_dir():
        candidates = list(bag_path.glob("*.db3"))
        if not candidates:
            raise FileNotFoundError(f"No .db3 file found in {bag_path}")
        db_path = candidates[0]

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    # Fetch topic ids
    cur.execute("SELECT id, name FROM topics")
    topics = {name: tid for tid, name in cur.fetchall()}

    cam_id = topics.get(camera_topic)
    odom_id = topics.get(odom_topic)

    if cam_id is None:
        available = list(topics.keys())
        raise KeyError(
            f"Camera topic '{camera_topic}' not found in bag. "
            f"Available topics: {available}"
        )
    if odom_id is None:
        available = list(topics.keys())
        raise KeyError(
            f"Odometry topic '{odom_topic}' not found in bag. "
            f"Available topics: {available}"
        )

    # --- Camera messages -------------------------------------------------------
    cur.execute(
        "SELECT timestamp, data FROM messages WHERE topic_id=? ORDER BY timestamp",
        (cam_id,),
    )
    raw_imgs = cur.fetchall()

    # Sub-sample to target_hz
    if raw_imgs:
        t0 = raw_imgs[0][0]
        t_last_kept = -1e18
        interval_ns = int(1e9 / target_hz)

    images: list[tuple[int, bytes]] = []
    for ts_ns, raw in raw_imgs:
        if ts_ns - t_last_kept < interval_ns:
            continue
        # Decode sensor_msgs/Image serialised by CDR
        # Minimal CDR parser: skip 4-byte header, then read the struct
        try:
            jpeg = _decode_ros_image_to_jpeg(raw)
            if jpeg is not None:
                images.append((ts_ns, jpeg))
                t_last_kept = ts_ns
        except Exception:
            pass

    # --- Odometry messages ----------------------------------------------------
    cur.execute(
        "SELECT timestamp, data FROM messages WHERE topic_id=? ORDER BY timestamp",
        (odom_id,),
    )
    raw_odoms = cur.fetchall()
    conn.close()

    odoms: list[tuple[int, float, float, float]] = []
    for ts_ns, raw in raw_odoms:
        try:
            x, y, yaw = _decode_ros_odom(raw)
            odoms.append((ts_ns, x, y, yaw))
        except Exception:
            pass

    return images, odoms


def _decode_ros_image_to_jpeg(raw: bytes) -> bytes | None:
    """
    Minimally decode a CDR-serialised sensor_msgs/Image to JPEG bytes.

    CDR layout (little-endian, after 4-byte encapsulation header):
      uint32 seq, time stamp (secs+nsecs), uint32 frame_id_len, char[] frame_id,
      uint32 height, uint32 width, uint32 encoding_len, char[] encoding,
      uint8 is_bigendian, uint32 step, uint32 data_len, uint8[] data

    This is a best-effort parser; malformed messages return None.
    """
    try:
        from PIL import Image as PilImage
        import io as _io

        # Skip CDR encapsulation (4 bytes)
        offset = 4

        def read_u32() -> int:
            nonlocal offset
            val = struct.unpack_from("<I", raw, offset)[0]
            offset += 4
            return val

        def read_str() -> str:
            nonlocal offset
            n = read_u32()
            s = raw[offset: offset + n - 1].decode("utf-8", errors="replace")
            offset += n
            return s

        # std_msgs/Header: seq + stamp + frame_id
        _seq = read_u32()
        _secs = read_u32()
        _nsecs = read_u32()
        _frame_id = read_str()

        height = read_u32()
        width = read_u32()
        encoding = read_str()
        _is_bigendian = struct.unpack_from("B", raw, offset)[0]
        offset += 1
        step = read_u32()
        data_len = read_u32()
        img_data = raw[offset: offset + data_len]

        if len(img_data) < height * step:
            return None

        # Convert to PIL
        if encoding in ("rgb8", "RGB8"):
            arr = np.frombuffer(img_data, dtype=np.uint8).reshape(height, width, 3)
            pil = PilImage.fromarray(arr, mode="RGB")
        elif encoding in ("bgr8", "BGR8"):
            arr = np.frombuffer(img_data, dtype=np.uint8).reshape(height, width, 3)
            arr = arr[:, :, ::-1]
            pil = PilImage.fromarray(arr, mode="RGB")
        elif encoding in ("mono8", "8UC1"):
            arr = np.frombuffer(img_data, dtype=np.uint8).reshape(height, width)
            pil = PilImage.fromarray(arr, mode="L").convert("RGB")
        else:
            # Attempt raw JPEG passthrough (compressed image topic)
            if img_data[:2] == b"\xff\xd8":
                return img_data
            return None

        buf = _io.BytesIO()
        pil.save(buf, format="JPEG", quality=90)
        return buf.getvalue()

    except Exception:
        return None


def _decode_ros_odom(raw: bytes) -> tuple[float, float, float]:
    """
    Minimally decode a CDR-serialised nav_msgs/Odometry to (x, y, yaw).

    CDR layout (after 4-byte encapsulation):
      std_msgs/Header (seq, stamp, frame_id)
      string child_frame_id
      geometry_msgs/PoseWithCovariance:
        geometry_msgs/Pose:
          Point (x, y, z) — 3x float64
          Quaternion (x, y, z, w) — 4x float64
        float64[36] covariance
      ... (TwistWithCovariance, ignored)
    """
    offset = 4  # skip CDR header

    def read_u32() -> int:
        nonlocal offset
        val = struct.unpack_from("<I", raw, offset)[0]
        offset += 4
        return val

    def read_str() -> str:
        nonlocal offset
        n = read_u32()
        s = raw[offset: offset + n - 1].decode("utf-8", errors="replace")
        offset += n
        return s

    def read_f64() -> float:
        nonlocal offset
        val = struct.unpack_from("<d", raw, offset)[0]
        offset += 8
        return val

    # Header
    _seq = read_u32()
    _secs = read_u32()
    _nsecs = read_u32()
    read_str()   # frame_id
    read_str()   # child_frame_id

    # Pose.position
    x = read_f64()
    y = read_f64()
    _z = read_f64()

    # Pose.orientation (quaternion)
    qx = read_f64()
    qy = read_f64()
    qz = read_f64()
    qw = read_f64()

    # Yaw from quaternion
    siny_cosp = 2.0 * (qw * qz + qx * qy)
    cosy_cosp = 1.0 - 2.0 * (qy * qy + qz * qz)
    yaw = math.atan2(siny_cosp, cosy_cosp)

    return x, y, yaw


def _sync_by_timestamp(
    images: list[tuple[int, bytes]],
    odoms: list[tuple[int, float, float, float]],
    max_dt_ns: int = 250_000_000,  # 250 ms
) -> list[tuple[bytes, float, float, float]]:
    """
    Synchronise image and odometry streams by nearest timestamp.

    For each image, finds the odometry message with the closest timestamp
    within *max_dt_ns* nanoseconds.

    Returns
    -------
    List of (jpeg_bytes, x, y, yaw) for each matched pair.
    """
    if not images or not odoms:
        return []

    odom_ts = np.array([o[0] for o in odoms], dtype=np.int64)
    matched: list[tuple[bytes, float, float, float]] = []

    for img_ts, jpeg in images:
        idx = int(np.argmin(np.abs(odom_ts - img_ts)))
        dt = abs(odom_ts[idx] - img_ts)
        if dt > max_dt_ns:
            continue
        _, x, y, yaw = odoms[idx]
        matched.append((jpeg, x, y, yaw))

    return matched


def ros2_bag_to_gnm(
    bag_path: Path | str,
    output_dir: Path | str,
    camera_topic: str = "/usb_cam/image_raw",
    odom_topic: str = "/odom",
    target_hz: float = 4.0,
    max_sync_dt_ms: float = 250.0,
) -> Path:
    """
    Convert a ROS2 bag file to a GNM trajectory folder.

    Extraction strategy:
      1. Try rosbag2_py (proper ROS2 Python API) if available.
      2. Fall back to direct sqlite3 parsing of the .db3 file.

    Parameters
    ----------
    bag_path        : path to the .db3 file or the bag directory
    output_dir      : directory where the traj_NNNN/ folder is created
    camera_topic    : ROS2 image topic (sensor_msgs/Image or CompressedImage)
    odom_topic      : ROS2 odometry topic (nav_msgs/Odometry)
    target_hz       : target image extraction rate (Hz); default 4 to match GNM
    max_sync_dt_ms  : maximum time offset (ms) for image↔odom sync

    Returns
    -------
    Path to the created GNM trajectory directory.

    Raises
    ------
    FileNotFoundError   if bag file does not exist
    RuntimeError        if no synchronised image+odom pairs can be extracted
    """
    bag_path = Path(bag_path).resolve()
    output_dir = Path(output_dir).resolve()

    if not bag_path.exists():
        raise FileNotFoundError(f"Bag not found: {bag_path}")

    print(f"  ros2-bag-to-gnm: {bag_path.name}")
    print(f"    camera topic : {camera_topic}")
    print(f"    odom topic   : {odom_topic}")
    print(f"    target Hz    : {target_hz}")

    rosbag2 = _try_import_rosbag2()

    if rosbag2 is not None:
        images, odoms = _read_bag_via_rosbag2_py(
            rosbag2, bag_path, camera_topic, odom_topic, target_hz
        )
    else:
        print("  [INFO] rosbag2_py not available; using sqlite3 parser")
        images, odoms = _read_bag_via_sqlite3(
            bag_path, camera_topic, odom_topic, target_hz
        )

    if not images:
        raise RuntimeError(
            f"No images extracted from '{camera_topic}'. "
            "Check that the topic exists in the bag and the camera_topic argument "
            "matches exactly.  Run: ros2 bag info <bag_path>"
        )
    if not odoms:
        raise RuntimeError(
            f"No odometry extracted from '{odom_topic}'. "
            "Check the odom_topic argument."
        )

    print(f"    raw images  : {len(images)}")
    print(f"    raw odoms   : {len(odoms)}")

    max_dt_ns = int(max_sync_dt_ms * 1e6)
    matched = _sync_by_timestamp(images, odoms, max_dt_ns)

    if not matched:
        raise RuntimeError(
            f"No image–odom pairs could be synchronised within {max_sync_dt_ms} ms. "
            "Check topic timestamps and try increasing --max-sync-dt."
        )

    print(f"    matched pairs: {len(matched)}")

    # Auto-number output trajectory
    output_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(output_dir.glob("traj_????"))
    traj_idx = len(existing)
    traj_dir = output_dir / f"traj_{traj_idx:04d}"
    traj_dir.mkdir(parents=True, exist_ok=True)

    # Write images
    positions: list[list[float]] = []
    yaws: list[float] = []
    for i, (jpeg, x, y, yaw) in enumerate(matched):
        (traj_dir / f"{i}.jpg").write_bytes(jpeg)
        positions.append([x, y])
        yaws.append(yaw)

    save_traj_data(
        traj_dir,
        np.array(positions, dtype=np.float64),
        np.array(yaws, dtype=np.float64),
    )

    # Sidecar metadata
    meta = {
        "source_bag": str(bag_path),
        "camera_topic": camera_topic,
        "odom_topic": odom_topic,
        "target_hz": target_hz,
        "n_frames": len(matched),
        "conversion": "ros2_bag_to_gnm",
        "robot": "yahboom_m3pro",
        "wheel_radius_m": WHEEL_RADIUS_M,
        "lx_m": LX,
        "ly_m": LY,
        "timestamp": time.time(),
    }
    (traj_dir / "meta.json").write_text(json.dumps(meta, indent=2))

    print(f"    Output: {traj_dir}  (T={len(matched)})")
    return traj_dir


def _read_bag_via_rosbag2_py(
    rosbag2: Any,
    bag_path: Path,
    camera_topic: str,
    odom_topic: str,
    target_hz: float,
) -> tuple[list[tuple[int, bytes]], list[tuple[int, float, float, float]]]:
    """
    Extract images and odometry from a ROS2 bag using the rosbag2_py API.
    """
    import rclpy.serialization  # type: ignore
    from rosidl_runtime_py.utilities import get_message  # type: ignore

    storage_options = rosbag2.StorageOptions(uri=str(bag_path), storage_id="sqlite3")
    converter_options = rosbag2.ConverterOptions("", "")

    reader = rosbag2.SequentialReader()
    reader.open(storage_options, converter_options)

    topic_types = {t.name: t.type for t in reader.get_all_topics_and_types()}

    interval_ns = int(1e9 / target_hz)
    last_cam_ts = -10**18

    images: list[tuple[int, bytes]] = []
    odoms: list[tuple[int, float, float, float]] = []

    while reader.has_next():
        topic, raw, ts_ns = reader.read_next()

        if topic == camera_topic:
            if ts_ns - last_cam_ts < interval_ns:
                continue
            try:
                msg_type = get_message(topic_types[topic])
                msg = rclpy.serialization.deserialize_message(raw, msg_type)
                jpeg = _ros_image_msg_to_jpeg(msg)
                if jpeg is not None:
                    images.append((ts_ns, jpeg))
                    last_cam_ts = ts_ns
            except Exception:
                pass

        elif topic == odom_topic:
            try:
                msg_type = get_message(topic_types[topic])
                msg = rclpy.serialization.deserialize_message(raw, msg_type)
                x = msg.pose.pose.position.x
                y = msg.pose.pose.position.y
                q = msg.pose.pose.orientation
                siny = 2.0 * (q.w * q.z + q.x * q.y)
                cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
                yaw = math.atan2(siny, cosy)
                odoms.append((ts_ns, x, y, yaw))
            except Exception:
                pass

    return images, odoms


def _ros_image_msg_to_jpeg(msg: Any) -> bytes | None:
    """Convert a deserialized sensor_msgs/Image or CompressedImage to JPEG bytes."""
    try:
        from PIL import Image as PilImage
        import io as _io

        # CompressedImage
        if hasattr(msg, "format"):
            data = bytes(msg.data)
            if data[:2] == b"\xff\xd8":
                return data
            return None

        # Raw Image
        enc = msg.encoding.lower()
        data = bytes(msg.data)
        h, w = msg.height, msg.width

        if enc in ("rgb8",):
            arr = np.frombuffer(data, dtype=np.uint8).reshape(h, w, 3)
        elif enc in ("bgr8",):
            arr = np.frombuffer(data, dtype=np.uint8).reshape(h, w, 3)[:, :, ::-1]
        elif enc in ("mono8", "8uc1"):
            arr = np.frombuffer(data, dtype=np.uint8).reshape(h, w)
            arr = np.stack([arr] * 3, axis=-1)
        else:
            return None

        buf = _io.BytesIO()
        PilImage.fromarray(arr.astype(np.uint8)).save(buf, format="JPEG", quality=90)
        return buf.getvalue()
    except Exception:
        return None


# ── Batch conversion helpers ──────────────────────────────────────────────────

def batch_gnm_to_fleetsafe(gnm_root: Path, output_dir: Path, model_name: str = "gnm") -> list[Path]:
    """
    Convert all traj_*/ folders under *gnm_root* to FleetSafe episodes.

    Returns a list of created episode directories.
    """
    traj_dirs = sorted(gnm_root.glob("traj_*"))
    if not traj_dirs:
        # Try without prefix
        traj_dirs = [p for p in gnm_root.iterdir() if p.is_dir() and (p / "traj_data.pkl").exists()]

    created: list[Path] = []
    for traj_dir in traj_dirs:
        try:
            ep_dir = gnm_to_fleetsafe(traj_dir, output_dir, model_name)
            created.append(ep_dir)
        except (ValueError, FileNotFoundError) as exc:
            print(f"  [WARN] {traj_dir.name}: {exc}")
    return created


# ── CLI ───────────────────────────────────────────────────────────────────────

def _cmd_gnm_to_fleetsafe(args: argparse.Namespace) -> int:
    inp = Path(args.input).resolve()

    # If input is a root dir with many traj_ subdirs, batch-convert
    traj_dirs = sorted(inp.glob("traj_*"))
    if traj_dirs:
        print(f"  Batch converting {len(traj_dirs)} trajectories ...")
        created = batch_gnm_to_fleetsafe(inp, Path(args.output), args.model_name)
        print(f"  Done: {len(created)} episodes written to {args.output}")
    else:
        ep = gnm_to_fleetsafe(inp, Path(args.output), args.model_name)
        print(f"  Done: {ep}")
    return 0


def _cmd_fleetsafe_to_gnm(args: argparse.Namespace) -> int:
    split = fleetsafe_to_gnm(
        Path(args.input),
        Path(args.output),
        split_frac=args.split_frac,
    )
    print(f"  Done: {len(split['train'])} train / {len(split['val'])} val")
    return 0


def _cmd_ros2_bag_to_gnm(args: argparse.Namespace) -> int:
    out = ros2_bag_to_gnm(
        bag_path=Path(args.bag),
        output_dir=Path(args.output),
        camera_topic=args.camera_topic,
        odom_topic=args.odom_topic,
        target_hz=args.target_hz,
        max_sync_dt_ms=args.max_sync_dt,
    )
    print(f"  Done: {out}")
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    inp = Path(args.input).resolve()

    # Single traj or batch?
    traj_dirs = sorted(inp.glob("traj_*"))
    if not traj_dirs:
        # Try as single trajectory
        traj_dirs = [inp]

    all_ok = True
    for traj_dir in traj_dirs:
        result = validate_gnm_format(traj_dir)
        status = "OK" if result["ok"] else "FAIL"
        print(f"  [{status}] {traj_dir.name}")
        if result.get("errors"):
            for e in result["errors"]:
                print(f"         ERROR: {e}")
        if result.get("warnings"):
            for w in result["warnings"]:
                print(f"         WARN:  {w}")
        if result["ok"]:
            print(
                f"         images={result['n_images']}  "
                f"positions={result.get('position_shape')}  "
                f"yaw={result.get('yaw_shape')}"
            )
        all_ok = all_ok and result["ok"]

    if all_ok:
        print(f"\n  All {len(traj_dirs)} trajectories pass GNM format validation.")
    else:
        print(f"\n  Some trajectories FAILED validation.")
    return 0 if all_ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # gnm-to-fleetsafe
    p1 = sub.add_parser("gnm-to-fleetsafe", help="GNM traj → FleetSafe episode")
    p1.add_argument("--input", required=True,
                    help="GNM trajectory directory (contains traj_data.pkl)")
    p1.add_argument("--output", required=True,
                    help="Output directory for FleetSafe episodes")
    p1.add_argument("--model-name", default="gnm",
                    help="Model label in metrics.json (default: gnm)")

    # fleetsafe-to-gnm
    p2 = sub.add_parser("fleetsafe-to-gnm", help="FleetSafe episode(s) → GNM traj")
    p2.add_argument("--input", required=True,
                    help="FleetSafe episode directory or parent directory")
    p2.add_argument("--output", required=True,
                    help="Output directory for GNM traj_NNNN/ folders")
    p2.add_argument("--split-frac", type=float, default=0.1,
                    help="Val split fraction (default: 0.1)")

    # ros2-bag-to-gnm
    p3 = sub.add_parser("ros2-bag-to-gnm", help="ROS2 bag → GNM traj")
    p3.add_argument("--bag", required=True,
                    help="Path to .db3 bag file or bag directory")
    p3.add_argument("--output", required=True,
                    help="Output directory for GNM traj_NNNN/ folder")
    p3.add_argument("--camera-topic", default="/usb_cam/image_raw",
                    help="Camera topic name (default: /usb_cam/image_raw)")
    p3.add_argument("--odom-topic", default="/odom",
                    help="Odometry topic name (default: /odom)")
    p3.add_argument("--target-hz", type=float, default=4.0,
                    help="Target image extraction rate Hz (default: 4.0)")
    p3.add_argument("--max-sync-dt", type=float, default=250.0,
                    help="Max image–odom sync offset in ms (default: 250)")

    # validate
    p4 = sub.add_parser("validate", help="Check GNM format compliance")
    p4.add_argument("--input", required=True,
                    help="GNM trajectory directory or parent of traj_*/ dirs")

    args = parser.parse_args()

    print()
    print("=" * 64)
    print("  FleetSafe GNM Dataset Converter")
    print("=" * 64)
    print()

    dispatch = {
        "gnm-to-fleetsafe": _cmd_gnm_to_fleetsafe,
        "fleetsafe-to-gnm": _cmd_fleetsafe_to_gnm,
        "ros2-bag-to-gnm": _cmd_ros2_bag_to_gnm,
        "validate": _cmd_validate,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
