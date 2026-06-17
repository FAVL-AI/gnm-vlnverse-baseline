#!/usr/bin/env python3
"""Verify the canonical sim-to-real topic contract for the Yahboom M3 Pro.

Defines the five canonical topic names required by the GNM + FleetSafe
pipeline and the known Yahboom hardware aliases. Checks whether canonical
or alias topics are live, if ROS 2 is available.

Exits 0 always when ROS 2 is not installed or Isaac Sim is not running.
Use --strict to exit non-zero when required topics are absent.

Usage:
    python3 scripts/gnm/check_yahboom_topic_contract.py [--strict]
"""

import argparse
import shutil
import subprocess
import sys

# ── Canonical topics ──────────────────────────────────────────────────────────
# These names are used in the GNM pipeline, the training dataset converter,
# and the v2.1 verification layer. They are standard ROS 2 names that work
# without remapping in Isaac Sim and on most real robots.
CANONICAL_TOPICS: list[dict] = [
    {
        "name": "/camera/image_raw",
        "type": "sensor_msgs/Image",
        "source": "Camera sensor (Isaac Sim OmniGraph / real robot)",
        "used_by": "GNM — primary visual input",
        "standard": True,
    },
    {
        "name": "/odom",
        "type": "nav_msgs/Odometry",
        "source": "Wheel encoders / Isaac Sim diff-drive or mecanum publisher",
        "used_by": "GNM waypoint labels, FleetSafe velocity estimate",
        "standard": True,
    },
    {
        "name": "/tf",
        "type": "tf2_msgs/TFMessage",
        "source": "Isaac Sim TF tree publisher / robot_state_publisher",
        "used_by": "Dataset converter — robot pose for waypoint labels",
        "standard": True,
    },
    {
        "name": "/scan",
        "type": "sensor_msgs/LaserScan",
        "source": "Lidar sensor (Isaac Sim / real robot)",
        "used_by": "FleetSafe CBF-QP obstacle detection",
        "standard": True,
    },
    {
        "name": "/cmd_vel",
        "type": "geometry_msgs/Twist",
        "source": "FleetSafe output (production) / manual publisher (testing)",
        "used_by": "Motor controller — drives the wheels",
        "standard": True,
    },
]

# ── Known Yahboom hardware aliases ────────────────────────────────────────────
# The real Yahboom ROSMASTER M3 Pro driver publishes some topics under
# different names. These aliases must be remapped to the canonical names
# before recording training rosbags or running the GNM pipeline.
#
# Remapping options:
#   (A) ROS 2 launch file topic_remap argument
#   (B) ros2 run --remap /alias:=/canonical
#   (C) A relay node (topic_tools/relay)
ALIASES: list[dict] = [
    {
        "alias": "/camera/color/image_raw",
        "canonical": "/camera/image_raw",
        "note": (
            "Yahboom real-robot driver publishes here. "
            "Remap to /camera/image_raw before recording GNM training data."
        ),
    },
    {
        "alias": "/m3pro/odom",
        "canonical": "/odom",
        "note": (
            "Published when the Yahboom bringup runs with the /m3pro namespace. "
            "Remap or launch without namespace for GNM compatibility."
        ),
    },
    {
        "alias": "/m3pro/cmd_vel",
        "canonical": "/cmd_vel",
        "note": (
            "Namespaced cmd_vel. Use the unnamespaced /cmd_vel for GNM + FleetSafe."
        ),
    },
]

# ── Smoke-test only topics ────────────────────────────────────────────────────
# These appeared during the Nova Carter smoke test (v2.1 bridge proof).
# They are NOT part of the Yahboom contract and must NOT appear in Yahboom
# training rosbags — they indicate the wrong robot is loaded.
NOVA_CARTER_TOPICS = [
    "/front_stereo_camera/left/image_raw",
    "/chassis/odom",
    "/front_3d_lidar/lidar_points",
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Yahboom M3 Pro sim-to-real topic contract checker [v2.2]"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if ROS 2 is missing or canonical topics are absent.",
    )
    args = parser.parse_args()

    print("=" * 60)
    print(" Yahboom M3 Pro Topic Contract  [v2.2]")
    print("=" * 60)
    print()
    print("Canonical sim-to-real topics:")
    for t in CANONICAL_TOPICS:
        std = "(standard ROS 2)" if t["standard"] else "(custom)"
        print(f"  {t['name']:<35s} {std}")
    print()
    print("Known Yahboom hardware aliases (require remapping):")
    for a in ALIASES:
        print(f"  {a['alias']:<35s} → {a['canonical']}")
    print()
    print("Nova Carter smoke-test topics (must NOT appear in Yahboom data):")
    for t in NOVA_CARTER_TOPICS:
        print(f"  {t}")
    print()

    if shutil.which("ros2") is None:
        print("[INFO] ros2 command not found.")
        print("[INFO] Live topic contract check skipped.")
        print("[INFO] Connect Isaac Sim or the physical Yahboom and re-run to")
        print("[INFO] verify topics. Use --strict to require live topics.")
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

    print(f"Active topics: {len(active)} found on bus.")
    print()

    # Check canonical topics.
    missing_canonical: list[str] = []
    for t in CANONICAL_TOPICS:
        name = t["name"]
        if name in active:
            print(f"[OK]      {name}")
        else:
            # Check if an alias is active instead.
            alias_active = [
                a["alias"] for a in ALIASES
                if a["canonical"] == name and a["alias"] in active
            ]
            if alias_active:
                print(f"[ALIAS]   {name}  (alias active: {alias_active[0]})")
                print(f"          Remap required before recording GNM training data.")
            else:
                print(f"[MISSING] {name}")
                missing_canonical.append(name)

    print()

    # Warn if Nova Carter topics are present.
    nova_active = [t for t in NOVA_CARTER_TOPICS if t in active]
    if nova_active:
        print("[WARN] Nova Carter smoke-test topics detected:")
        for t in nova_active:
            print(f"  {t}")
        print("[WARN] This means Nova Carter is loaded, not Yahboom.")
        print("[WARN] Load the Yahboom USD stage before recording training data.")
        print()

    if not missing_canonical:
        print("[OK] All canonical Yahboom topics are present.")
        return 0

    print(f"[WARN] {len(missing_canonical)} canonical topic(s) missing:")
    for t in missing_canonical:
        print(f"  {t}")
    print()

    if args.strict:
        print("[FAIL] --strict mode: canonical topics required but missing.")
        return 1

    print("[INFO] Non-strict mode: acceptable — Isaac Sim or real robot not running.")
    print("[INFO] Load the Yahboom stage in Isaac Sim and re-run with --strict")
    print("[INFO] to verify the full topic contract.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
