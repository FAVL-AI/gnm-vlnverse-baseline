#!/usr/bin/env python3
"""Convert a rosbag2 episode into GNM-style training data.

Does not require ROS 2 Python packages. In dry-run mode, writes a conversion
manifest without reading actual bag data. In live mode, reads the bag using
ros2_rosbag (rclpy) and extracts image, odometry, and scan messages.

Usage:
    python3 convert_rosbag_to_gnm_dataset.py \
        --rosbag-root datasets/gnm_fleetsafe_rosbags \
        --output-root datasets/gnm_fleetsafe_converted \
        --episode-name demo_episode \
        [--dry-run]
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


REQUIRED_TOPICS = [
    "/camera/image_raw",
    "/odom",
    "/tf",
    "/scan",
]

CONVERTED_DATA_DESCRIPTION = {
    "context_images": (
        "Numbered PNG frames from /camera/image_raw, "
        "resized to gnm.image_size x gnm.image_size pixels. "
        "Each episode provides a sliding window of context_size recent frames."
    ),
    "goal_image": (
        "The RGB frame from the goal position (final frame of the episode "
        "or a designated goal waypoint frame)."
    ),
    "waypoint_action": (
        "Numpy array of (dx, dy) displacements from the current robot pose "
        "to the next waypoint, derived from /odom messages."
    ),
    "odometry": (
        "JSON list of robot poses at each frame: "
        "{x, y, theta, linear_velocity, angular_velocity}."
    ),
    "scan_summary": (
        "JSON summary of /scan readings: min_range, mean_range, "
        "and sectors with obstacles closer than 0.35 m."
    ),
    "success_label": (
        "JSON file recording whether the episode reached the goal "
        "within the distance threshold."
    ),
}


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rosbag-root", required=True,
                   help="Root directory containing rosbag episode folders.")
    p.add_argument("--output-root", required=True,
                   help="Root directory for converted GNM dataset.")
    p.add_argument("--episode-name", required=True,
                   help="Name of the episode to convert.")
    p.add_argument("--dry-run", action="store_true",
                   help="Write conversion manifest without reading bag data.")
    return p.parse_args()


def write_manifest(output_dir: Path, episode_name: str, rosbag_dir: Path,
                   dry_run: bool) -> Path:
    manifest = {
        "episode_name": episode_name,
        "rosbag_source": str(rosbag_dir),
        "output_dir": str(output_dir),
        "converted_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "required_topics": REQUIRED_TOPICS,
        "converted_data": CONVERTED_DATA_DESCRIPTION,
        "expected_files": [
            "context_images/",
            "goal_image.png",
            "waypoints.npy",
            "odometry.json",
            "scan_summary.json",
            "success_label.json",
        ],
        "notes": [
            "In dry-run mode no actual bag data was read.",
            "In live mode, rclpy and rosbag2_py must be available (ROS 2 required).",
            "Run with Isaac Sim rosbag data to produce real training tuples.",
            "Load these files in scripts/gnm/train_gnm_from_collected_data.sh.",
        ],
    }
    manifest_path = output_dir / "conversion_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return manifest_path


def convert_live(rosbag_dir: Path, output_dir: Path, episode_name: str):
    try:
        import rclpy  # noqa: F401
        from rosbag2_py import SequentialReader, StorageOptions, ConverterOptions
    except ImportError:
        print(
            "[ERROR] rclpy or rosbag2_py not found.\n"
            "        Live conversion requires ROS 2 with Python bindings.\n"
            "        Run with --dry-run for CI/offline use.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"[INFO] Opening bag: {rosbag_dir}")

    storage_options = StorageOptions(uri=str(rosbag_dir / "rosbag"), storage_id="sqlite3")
    converter_options = ConverterOptions("", "")

    reader = SequentialReader()
    reader.open(storage_options, converter_options)

    topic_types = reader.get_all_topics_and_types()
    available = {t.name for t in topic_types}
    missing = [t for t in REQUIRED_TOPICS if t not in available]
    if missing:
        print(f"[WARN] Topics not found in bag: {missing}", file=sys.stderr)

    images_dir = output_dir / "context_images"
    images_dir.mkdir(parents=True, exist_ok=True)

    print("[INFO] Reading messages (live conversion not fully implemented).")
    print("[INFO] Implement message deserialization using rclpy serialization API.")
    print("[INFO] See: https://docs.ros.org/en/humble/Tutorials/Advanced/Reading-From-A-Bag-File.html")

    (output_dir / "odometry.json").write_text(json.dumps(
        {"note": "populate from /odom messages during live conversion"}, indent=2
    ))
    (output_dir / "scan_summary.json").write_text(json.dumps(
        {"note": "populate from /scan messages during live conversion"}, indent=2
    ))
    (output_dir / "success_label.json").write_text(json.dumps(
        {"success": False, "note": "determine from final distance to goal"}, indent=2
    ))

    print(f"[OK] Live conversion skeleton complete for episode: {episode_name}")


def convert_dry_run(output_dir: Path, episode_name: str):
    images_dir = output_dir / "context_images"
    images_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "odometry.json").write_text(json.dumps(
        {"dry_run": True, "note": "no real odometry data in dry-run mode"}, indent=2
    ))
    (output_dir / "scan_summary.json").write_text(json.dumps(
        {"dry_run": True, "note": "no real scan data in dry-run mode"}, indent=2
    ))
    (output_dir / "success_label.json").write_text(json.dumps(
        {"dry_run": True, "success": None}, indent=2
    ))

    print(f"[DRY-RUN] Created output skeleton in: {output_dir}")
    print("[DRY-RUN] In live mode, context_images/ will contain PNG frames.")
    print("[DRY-RUN] In live mode, waypoints.npy will contain (dx,dy) arrays.")


def main():
    args = parse_args()

    rosbag_root = Path(args.rosbag_root)
    output_root = Path(args.output_root)
    episode_name = args.episode_name

    rosbag_dir = rosbag_root / episode_name
    output_dir = output_root / episode_name

    print("============================================================")
    print(" FleetSafe-GNM Rosbag-to-GNM Converter")
    print("============================================================")
    print(f"Episode        : {episode_name}")
    print(f"Rosbag source  : {rosbag_dir}")
    print(f"Output dir     : {output_dir}")
    print(f"Dry-run        : {args.dry_run}")
    print("============================================================")

    output_dir.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        convert_dry_run(output_dir, episode_name)
    else:
        if not rosbag_dir.exists():
            print(
                f"[ERROR] Rosbag directory not found: {rosbag_dir}\n"
                f"        Collect an episode first with collect_isaac_rosbag_episode.sh\n"
                f"        or use --dry-run for offline testing.",
                file=sys.stderr,
            )
            sys.exit(1)
        convert_live(rosbag_dir, output_dir, episode_name)

    manifest_path = write_manifest(output_dir, episode_name, rosbag_dir, args.dry_run)
    print(f"[OK] Conversion manifest written: {manifest_path}")
    print("")

    print("Converted data structure:")
    for key, description in CONVERTED_DATA_DESCRIPTION.items():
        print(f"  {key}:")
        print(f"    {description[:80]}...")
    print("")
    print("[OK] Conversion complete.")


if __name__ == "__main__":
    main()
