#!/usr/bin/env python3
"""Gate verifier for the five canonical Yahboom M3 Pro ROS 2 topics.

This is the recording gate: all five canonical topics must pass before any
rosbag2 episode recording begins. If any canonical topic is missing, the
recording will be incomplete and the GNM dataset conversion will fail.

In non-strict mode (default), exits 0 even if ROS 2 is not installed or
topics are missing. Use this for dry-run and CI.

In strict mode (--strict), exits non-zero if ROS 2 is absent or any
canonical topic is missing. Use this with Isaac Sim running and the
Yahboom stage loaded.

Also reports known Yahboom hardware aliases and detects Nova Carter
smoke-test topics — which must NOT appear in Yahboom recordings.

Usage:
    python3 scripts/gnm/verify_yahboom_live_topics.py [--strict]
"""

import argparse
import shutil
import subprocess
import sys

CANONICAL_TOPICS = [
    {
        "name": "/camera/image_raw",
        "type": "sensor_msgs/Image",
        "used_by": "GNM visual input",
    },
    {
        "name": "/odom",
        "type": "nav_msgs/Odometry",
        "used_by": "GNM waypoint labels, FleetSafe velocity",
    },
    {
        "name": "/tf",
        "type": "tf2_msgs/TFMessage",
        "used_by": "Dataset converter robot pose",
    },
    {
        "name": "/scan",
        "type": "sensor_msgs/LaserScan",
        "used_by": "FleetSafe obstacle detection",
    },
    {
        "name": "/cmd_vel",
        "type": "geometry_msgs/Twist",
        "used_by": "Motor controller (FleetSafe output)",
    },
]

# Known Yahboom hardware driver topic names that differ from canonical.
# These are published by the physical Yahboom M3 Pro driver.
# A topic remap must be applied before recording GNM training data.
ALIASES = {
    "/camera/image_raw": "/camera/color/image_raw",
    "/odom": "/m3pro/odom",
    "/cmd_vel": "/m3pro/cmd_vel",
}

# Nova Carter topics that must NOT appear in Yahboom recordings.
# Seeing these means Isaac Sim has Nova Carter loaded, not Yahboom.
NOVA_CARTER_TOPICS = {
    "/front_stereo_camera/left/image_raw",
    "/chassis/odom",
    "/front_3d_lidar/lidar_points",
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Yahboom M3 Pro live topic gate verifier [v2.3]"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Exit non-zero if ROS 2 is absent or any canonical topic is missing. "
            "Use when Isaac Sim is running with the Yahboom stage loaded."
        ),
    )
    args = parser.parse_args()

    print("=" * 60)
    print(" Yahboom M3 Pro Topic Gate Verifier  [v2.3]")
    print("=" * 60)
    print()
    print("Recording gate: all five topics must pass before rosbag2 recording.")
    print()

    for t in CANONICAL_TOPICS:
        alias = ALIASES.get(t["name"], "")
        alias_str = f"  (hardware alias: {alias})" if alias else ""
        print(f"  {t['name']:<35s} {t['used_by']}{alias_str}")

    print()

    if shutil.which("ros2") is None:
        print("[INFO] ros2 command not found.")
        print("[INFO] Live topic gate check skipped.")
        print("[INFO] To run live: install ROS 2 Humble or Jazzy, start Isaac Sim,")
        print("[INFO] load the Yahboom M3 Pro USD stage, enable the ROS 2 Bridge,")
        print("[INFO] press Play, then re-run with --strict.")
        print()
        if args.strict:
            print("[FAIL] --strict mode: ROS 2 is required but not installed.")
            return 1
        print("[OK] Dry-run/CI mode: exiting 0.")
        return 0

    result = subprocess.run(
        ["ros2", "topic", "list"],
        capture_output=True,
        text=True,
    )
    active = set(result.stdout.strip().splitlines())

    print(f"Active topics on bus: {len(active)}")
    print()

    # Detect Nova Carter (wrong robot loaded).
    nova_active = NOVA_CARTER_TOPICS & active
    if nova_active:
        print("[WARN] Nova Carter smoke-test topics detected:")
        for t in sorted(nova_active):
            print(f"  {t}")
        print("[WARN] Nova Carter is loaded in Isaac Sim — not Yahboom M3 Pro.")
        print("[WARN] Load the Yahboom USD stage before recording training data.")
        print()

    missing: list[str] = []
    alias_only: list[tuple[str, str]] = []

    for t in CANONICAL_TOPICS:
        name = t["name"]
        if name in active:
            print(f"[OK]      {name}")
        else:
            hw_alias = ALIASES.get(name, "")
            if hw_alias and hw_alias in active:
                print(f"[ALIAS]   {name}")
                print(f"          Hardware alias active: {hw_alias}")
                print(f"          Add remap: (\"{hw_alias}\", \"{name}\")")
                alias_only.append((name, hw_alias))
            else:
                print(f"[MISSING] {name}")
                missing.append(name)

    print()

    if not missing and not alias_only:
        print("[OK] All canonical topics present. Recording gate is open.")
        return 0

    if alias_only and not missing:
        print(f"[WARN] {len(alias_only)} topic(s) available via alias only.")
        print("[WARN] Remapping required before recording GNM training data.")
        if args.strict:
            print("[FAIL] --strict mode: canonical names required (not aliases).")
            return 1
        print("[INFO] Non-strict mode: aliases acceptable for connection testing.")
        return 0

    print(f"[WARN] {len(missing)} canonical topic(s) missing:")
    for t in missing:
        print(f"  {t}")
    print()

    if nova_active:
        print("[HINT] Detected Nova Carter topics — load the Yahboom USD stage.")
    else:
        print("[HINT] Isaac Sim may not be playing, or OmniGraph nodes not connected.")
        print("[HINT] Complete all steps in:")
        print("[HINT]   results/gnm_fleetsafe_v2_3/yahboom_isaac_import_plan.md")

    if args.strict:
        print()
        print("[FAIL] --strict mode: recording gate not open.")
        return 1

    print()
    print("[INFO] Non-strict mode: acceptable if Isaac Sim is not running.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
