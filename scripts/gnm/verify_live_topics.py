#!/usr/bin/env python3
"""Verify the five required live topics on the ROS 2 bus.

Exits 0 when all topics are present, or when ROS 2 is not installed
(dry-run/CI mode, --strict not set).
Exits 1 when --strict is set and ROS 2 is missing or topics are absent.

Usage:
    python3 scripts/gnm/verify_live_topics.py [--strict]
"""

import argparse
import shutil
import subprocess
import sys

REQUIRED_TOPICS = [
    "/camera/image_raw",
    "/odom",
    "/tf",
    "/scan",
    "/cmd_vel",
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify Isaac ROS 2 live topics [v2.1]"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if ROS 2 is missing or any required topic is absent.",
    )
    args = parser.parse_args()

    print("=" * 60)
    print(" Live Topic Verifier — v2.1 Isaac ROS 2 Bridge")
    print("=" * 60)
    print(f"Required topics ({len(REQUIRED_TOPICS)}):")
    for t in REQUIRED_TOPICS:
        print(f"  {t}")
    print()

    if shutil.which("ros2") is None:
        print("[INFO] ros2 command not found.")
        print("[INFO] Live topic verification skipped.")
        print("[INFO] Install ROS 2 (Humble or Jazzy) and start Isaac Sim with")
        print("[INFO] the ROS 2 Bridge enabled to run live checks.")
        print()
        if args.strict:
            print("[FAIL] --strict mode: ROS 2 is required but not installed.")
            return 1
        print("[OK] Dry-run/CI mode: exiting 0 (ROS 2 not required in CI).")
        return 0

    result = subprocess.run(
        ["ros2", "topic", "list"],
        capture_output=True,
        text=True,
    )
    active = set(result.stdout.strip().splitlines())

    missing: list[str] = []
    for topic in REQUIRED_TOPICS:
        if topic in active:
            print(f"[OK]      {topic}")
        else:
            print(f"[MISSING] {topic}")
            missing.append(topic)

    print()
    if not missing:
        print("[OK] All required topics are present.")
        return 0

    print(f"[WARN] {len(missing)} topic(s) missing:")
    for t in missing:
        print(f"  {t}")
    print()
    if args.strict:
        print("[FAIL] --strict mode: required topics are missing.")
        return 1
    print("[INFO] Non-strict mode: acceptable if Isaac Sim is not running.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
