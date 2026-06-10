"""Public API for ROS bag → GNM dataset conversion.

Delegates to scripts/data/gnm_dataset_converter.py (the full implementation)
and adds convert_run_dir() for the output format of collect_gnm_data.sh.

Conversion routes
-----------------
  ros2_bag_to_gnm()     .db3 bag or bag folder → GNM traj_NNNN/
  fleetsafe_to_gnm()    FleetSafe episode(s)   → GNM traj_NNNN/ + split manifest
  gnm_to_fleetsafe()    GNM traj_NNNN/         → FleetSafe episode directory
  validate_gnm_format() Check a directory is valid GNM format
  convert_run_dir()     collect_gnm_data.sh run_NNN/ → GNM traj_NNNN/

Usage:
    from fleetsafe_vln.data.rosbag_to_gnm import ros2_bag_to_gnm, convert_run_dir

    # Convert a ROS bag recorded with collect_gnm_data.sh
    traj = ros2_bag_to_gnm(
        bag_path="data/gnm_isaac_hospital_corridor/run_001/bag",
        output_dir="data/gnm_fleetsafe",
    )

    # Or use the convenience wrapper for a full run_NNN/ directory
    traj = convert_run_dir("data/gnm_isaac_hospital_corridor/run_001")
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional

# Make sure the repo root is importable so scripts.data resolves
_REPO = Path(__file__).parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.data.gnm_dataset_converter import (  # noqa: E402
    ros2_bag_to_gnm,
    fleetsafe_to_gnm,
    gnm_to_fleetsafe,
    validate_gnm_format,
    batch_gnm_to_fleetsafe,
)

__all__ = [
    "ros2_bag_to_gnm",
    "fleetsafe_to_gnm",
    "gnm_to_fleetsafe",
    "validate_gnm_format",
    "batch_gnm_to_fleetsafe",
    "convert_run_dir",
]


def convert_run_dir(
    run_dir: str | Path,
    output_dir: Optional[str | Path] = None,
    camera_topic: str = "/camera/image_raw",
    odom_topic: str = "/odom",
    target_hz: float = 4.0,
) -> Path:
    """Convert a collect_gnm_data.sh run_NNN/ directory to GNM format.

    The run directory must contain a bag/ subdirectory produced by
    scripts/gnm/collect_gnm_data.sh.

    Parameters
    ----------
    run_dir    : path to run_NNN/ directory
    output_dir : where to write traj_NNNN/; defaults to sibling gnm_traj/ dir
    camera_topic, odom_topic, target_hz : forwarded to ros2_bag_to_gnm()

    Returns
    -------
    Path to the created GNM trajectory directory.
    """
    run_dir = Path(run_dir).resolve()
    bag_dir = run_dir / "bag"

    if not bag_dir.exists():
        raise FileNotFoundError(
            f"bag/ directory not found in {run_dir}. "
            "Run collect_gnm_data.sh first to record a bag."
        )

    if output_dir is None:
        output_dir = run_dir.parent / "gnm_trajs"

    return ros2_bag_to_gnm(
        bag_path=bag_dir,
        output_dir=output_dir,
        camera_topic=camera_topic,
        odom_topic=odom_topic,
        target_hz=target_hz,
    )


# Allow running as a script for quick conversion
if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(
        description="Convert run_NNN/ bag to GNM traj format"
    )
    p.add_argument("run_dir", nargs="?", default=None,
                   help="Path to collect_gnm_data.sh run_NNN/ dir (positional)")
    p.add_argument("--input", default=None, dest="input_dir",
                   help="Same as run_dir (alternative flag form)")
    p.add_argument("--output", default=None, help="Output directory")
    p.add_argument("--camera-topic", default="/camera/image_raw")
    p.add_argument("--odom-topic", default="/odom")
    p.add_argument("--target-hz", type=float, default=4.0)
    args = p.parse_args()

    run_dir_arg = args.run_dir or args.input_dir
    if run_dir_arg is None:
        p.error("Provide a run directory: positional run_dir or --input")

    out = convert_run_dir(
        run_dir_arg,
        output_dir=args.output,
        camera_topic=args.camera_topic,
        odom_topic=args.odom_topic,
        target_hz=args.target_hz,
    )
    print(f"Done: {out}")


