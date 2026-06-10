"""certify_rosbag_run.py — Generate posthoc safety certificates from a ROS2 bag.

For each /cmd_vel message in the bag, this script:
  1. Finds the most recent /scan0 (and optionally /scan1) message.
  2. Computes min_dist_m = min non-zero range reading.
  3. Computes h_min = min_dist_m² - d_safe².
  4. Emits a SafetyCertificate with qp_status="posthoc_observation".

These are WEAKER than runtime certificates — they verify the robot was never
closer than d_safe to an obstacle, but do NOT verify the original QP solve.

Requirements:
    source /opt/ros/humble/setup.bash
    pip install rosbag2_py  (or installed via ROS2)

Usage:
    python3 certify_rosbag_run.py --bag data/real_robot_bags/m3pro_full_motion_20260525_042557
    python3 certify_rosbag_run.py --bag <path> --output results/certificates/posthoc.jsonl --d-safe 0.5
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Allow running without installing the package
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from fleet_safe_vla.safety.certificate import SafetyCertificate
    from fleet_safe_vla.safety.certificate_logger import SafetyCertificateLogger
    _HAS_CERT = True
except ImportError:
    _HAS_CERT = False

# ---------------------------------------------------------------------------
# ROS2 bag reading
# ---------------------------------------------------------------------------
try:
    import rclpy
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    import rosbag2_py
    _HAS_ROS = True
except ImportError:
    _HAS_ROS = False


def _open_reader(bag_path: str):
    """Return a rosbag2_py SequentialReader opened on bag_path."""
    reader = rosbag2_py.SequentialReader()
    storage_opts = rosbag2_py.StorageOptions(uri=bag_path, storage_id="sqlite3")
    converter_opts = rosbag2_py.ConverterOptions(
        input_serialization_format="cdr",
        output_serialization_format="cdr",
    )
    reader.open(storage_opts, converter_opts)
    return reader


def _topic_type_map(reader) -> dict[str, str]:
    """Return {topic_name: type_string} from the bag metadata."""
    return {
        meta.name: meta.type
        for meta in reader.get_all_topics_and_types()
    }


def _min_range_from_scan(msg) -> float:
    """Return the minimum valid (non-zero, finite) range from a LaserScan message."""
    valid = [
        r for r in msg.ranges
        if math.isfinite(r) and r > 0.0 and r < msg.range_max
    ]
    if not valid:
        return float("inf")
    return min(valid)


# ---------------------------------------------------------------------------
# Core certification logic
# ---------------------------------------------------------------------------

def certify_bag(
    bag_path: str,
    output_path: str,
    d_safe: float = 0.5,
    scan_topics: list[str] | None = None,
    cmd_topic: str = "/cmd_vel",
    verbose: bool = False,
) -> int:
    """Read bag, emit one posthoc certificate per cmd_vel message.

    Returns the number of certificates written.
    """
    if scan_topics is None:
        scan_topics = ["/scan0", "/scan1"]

    if not _HAS_ROS:
        print("ERROR: rosbag2_py / rclpy not available.", file=sys.stderr)
        print("       Run: source /opt/ros/humble/setup.bash", file=sys.stderr)
        sys.exit(2)

    if not _HAS_CERT:
        print("ERROR: fleet_safe_vla not importable.", file=sys.stderr)
        sys.exit(2)

    bag_path = str(bag_path)
    if not Path(bag_path).exists():
        print(f"ERROR: bag not found: {bag_path}", file=sys.stderr)
        sys.exit(2)

    reader = _open_reader(bag_path)
    type_map = _topic_type_map(reader)

    wanted_topics = set(scan_topics) | {cmd_topic}
    available = set(type_map.keys())
    found_scans = [t for t in scan_topics if t in available]
    has_cmd = cmd_topic in available

    if verbose:
        print(f"[certify] Bag: {bag_path}")
        print(f"[certify] Topics in bag: {sorted(available)}")
        print(f"[certify] Scan topics found: {found_scans}")
        print(f"[certify] cmd_vel found: {has_cmd}")

    if not found_scans:
        print(
            f"WARNING: No scan topics ({scan_topics}) found in bag. "
            "Certificates will use min_dist_m=inf (no obstacle data).",
            file=sys.stderr,
        )
    if not has_cmd:
        print(
            f"WARNING: {cmd_topic} not found in bag. No certificates will be written.",
            file=sys.stderr,
        )
        return 0

    # Filter the reader to wanted topics only
    filter_ = rosbag2_py.StorageFilter(topics=list(wanted_topics & available))
    reader.set_filter(filter_)

    # Deserialise helpers keyed by topic
    msg_types: dict[str, type] = {}
    for topic in wanted_topics & available:
        ros_type = type_map[topic].replace("/", "/msg/", 1)
        try:
            msg_types[topic] = get_message(ros_type)
        except Exception:
            # Some type strings are already in the right form
            try:
                msg_types[topic] = get_message(type_map[topic])
            except Exception as exc:
                print(f"WARNING: cannot load message type for {topic}: {exc}", file=sys.stderr)

    # State: latest scan reading per topic
    latest_scan: dict[str, float] = {}   # topic → min_dist_m
    count = 0

    with SafetyCertificateLogger(output_path) as logger:
        while reader.has_next():
            topic, raw_data, stamp_ns = reader.read_next()
            stamp_s = stamp_ns * 1e-9

            if topic not in msg_types:
                continue

            try:
                msg = deserialize_message(raw_data, msg_types[topic])
            except Exception as exc:
                if verbose:
                    print(f"WARNING: deserialize failed on {topic}: {exc}", file=sys.stderr)
                continue

            if topic in scan_topics:
                latest_scan[topic] = _min_range_from_scan(msg)
                continue

            if topic == cmd_topic:
                # Aggregate scans: take the minimum across all available scan topics
                if latest_scan:
                    min_dist_m = min(latest_scan.values())
                else:
                    min_dist_m = float("inf")

                h_min = min_dist_m ** 2 - d_safe ** 2 if math.isfinite(min_dist_m) else float("inf")
                safe = min_dist_m >= d_safe

                # Extract cmd_vel components
                try:
                    vx = float(msg.linear.x)
                    wz = float(msg.angular.z)
                except AttributeError:
                    vx, wz = 0.0, 0.0

                logger.append_from_values(
                    timestamp=stamp_s,
                    model_name="posthoc_bag",
                    u_nom=[vx, wz],
                    u_safe=[vx, wz],
                    h_min=h_min if math.isfinite(h_min) else 0.0,
                    min_dist_m=min_dist_m if math.isfinite(min_dist_m) else 0.0,
                    cbf_active=False,
                    qp_status="posthoc_observation",
                    constraint_margin_min=h_min if math.isfinite(h_min) else 0.0,
                    latency_ms=0.0,
                    safe=safe,
                    notes=(
                        "posthoc certificate from recorded bag; "
                        "verifies observed safety distance, not original QP solve"
                    ),
                )
                count += 1

    return count


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _print_summary(output_path: str, d_safe: float) -> None:
    """Print a brief pass/fail summary from the written JSONL."""
    from fleet_safe_vla.safety.certificate import SafetyCertificate

    path = Path(output_path)
    if not path.exists() or path.stat().st_size == 0:
        print("[certify] No certificates written.")
        return

    certs = []
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                certs.append(SafetyCertificate.from_json(line))

    n = len(certs)
    violations = [c for c in certs if not c.safe]
    min_dist_all = [c.min_dist_m for c in certs if c.min_dist_m > 0]
    min_dist_overall = min(min_dist_all) if min_dist_all else float("nan")

    print()
    print("=" * 60)
    print("  POSTHOC CERTIFICATION SUMMARY")
    print("=" * 60)
    print(f"  Certificates:   {n}")
    print(f"  d_safe:         {d_safe:.2f} m")
    print(f"  Min observed:   {min_dist_overall:.3f} m")
    print(f"  Violations:     {len(violations)}")
    print(f"  Output:         {output_path}")
    if violations:
        print()
        print("  FAIL — robot came closer than d_safe in the recorded run.")
        print("  NOTE: posthoc certificates reflect observations, not a formal safety proof.")
    else:
        print()
        print("  PASS — robot maintained >= d_safe clearance throughout the run.")
        print("  NOTE: posthoc certificates reflect observations, not a formal safety proof.")
    print("=" * 60)
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args():
    p = argparse.ArgumentParser(
        description="Generate posthoc safety certificates from a ROS2 bag.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--bag", required=True,
        help="Path to the ROS2 bag directory (containing *.db3 + metadata.yaml).",
    )
    p.add_argument(
        "--output", default=None,
        help="Output JSONL path. Default: results/certificates/posthoc_<bag_name>.jsonl",
    )
    p.add_argument(
        "--d-safe", type=float, default=0.5,
        help="Safety clearance threshold in metres (default: 0.5).",
    )
    p.add_argument(
        "--scan-topics", nargs="+", default=["/scan0", "/scan1"],
        help="Scan topics to use for distance measurement (default: /scan0 /scan1).",
    )
    p.add_argument(
        "--cmd-topic", default="/cmd_vel",
        help="Command velocity topic (default: /cmd_vel).",
    )
    p.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print extra debug info.",
    )
    return p.parse_args()


def main():
    args = _parse_args()

    bag_name = Path(args.bag).name
    if args.output is None:
        out = Path("results/certificates") / f"posthoc_{bag_name}.jsonl"
    else:
        out = Path(args.output)

    print(f"[certify] Bag:    {args.bag}")
    print(f"[certify] Output: {out}")
    print(f"[certify] d_safe: {args.d_safe} m")

    n = certify_bag(
        bag_path=args.bag,
        output_path=str(out),
        d_safe=args.d_safe,
        scan_topics=args.scan_topics,
        cmd_topic=args.cmd_topic,
        verbose=args.verbose,
    )

    print(f"[certify] Wrote {n} posthoc certificates.")
    _print_summary(str(out), args.d_safe)


if __name__ == "__main__":
    main()
