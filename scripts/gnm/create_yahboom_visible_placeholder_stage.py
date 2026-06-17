#!/usr/bin/env python3
"""Generate the Yahboom M3 Pro visible placeholder USD stage as a portable USDA file.

The generated file contains cube/cylinder primitive geometry for all key robot
links, a Camera sensor prim under camera_link, and OmniGraph action graph stubs
for the five canonical ROS 2 publisher/subscriber nodes.

The OmniGraph stubs define the graph structure but are NOT automatically wired
until add_yahboom_ros2_omnigraph.py is run inside Isaac Sim.

Outputs:
    assets/robots/yahboom_m3_pro/yahboom_m3pro_visible_placeholder.usda

The script exits 0 always. It does not require Isaac Sim or ROS 2.

Usage:
    python3 scripts/gnm/create_yahboom_visible_placeholder_stage.py [--dry-run]

Flags:
    --dry-run   Print the USDA content to stdout; do not write to disk.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT_PATH = ROOT / "assets" / "robots" / "yahboom_m3_pro" / "yahboom_m3pro_visible_placeholder.usda"

# Robot geometry based on Yahboom ROSMASTER M3 Pro product specification.
# Units: metres. Coordinates: X = forward, Y = left, Z = up.
#
# All measurements are engineering approximations for placeholder geometry.
# This is not a physics-accurate or photo-realistic model.
USDA_CONTENT = """\
#usda 1.0
(
    defaultPrim = "World"
    doc = "Yahboom ROSMASTER M3 Pro visible placeholder stage [v2.4.2]"
    metersPerUnit = 1
    upAxis = "Z"
)

# ============================================================
# Yahboom ROSMASTER M3 Pro — Visible Placeholder Stage
#
# This stage contains primitive geometry for engineering validation.
# It is NOT photo-realistic. It has NO physics or collision.
#
# Robot prim path : /World/YahboomM3Pro
# Camera sensor   : /World/YahboomM3Pro/camera_link/sensor
# Ground prim path: /World/Ground
# OmniGraph path  : /World/ROS2ActionGraph
#
# ROS 2 OmniGraph publisher/subscriber nodes (stubs — wire via
# add_yahboom_ros2_omnigraph.py or Isaac Sim GUI):
#   ROS2PublishImage          camera_link/sensor  -> /camera/image_raw
#   ROS2PublishOdometry       base_link           -> /odom
#   ROS2PublishTransformTree  YahboomM3Pro tree   -> /tf
#   ROS2PublishLaserScan      lidar_link          -> /scan
#   ROS2SubscribeTwist        /cmd_vel            <- wheel joints
#
# See docs/v2.4.2_yahboom_omnigraph_publishers.md for wiring instructions.
# ============================================================

def Xform "World"
{
    def Xform "YahboomM3Pro"
    {
        # Chassis body: 0.75 m long, 0.45 m wide, 0.18 m tall.
        # Raised to z=0.25 m so wheels sit at ground level.
        def Cube "base_link"
        {
            double size = 1
            float3 xformOp:scale = (0.75, 0.45, 0.18)
            double3 xformOp:translate = (0, 0, 0.25)
            uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:scale"]
        }

        # Top mounting deck: 0.55 m long, 0.35 m wide, 0.06 m tall.
        def Cube "top_deck"
        {
            double size = 1
            float3 xformOp:scale = (0.55, 0.35, 0.06)
            double3 xformOp:translate = (0, 0, 0.47)
            uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:scale"]
        }

        # Camera mount block: 0.10 m wide, 0.16 m tall, 0.10 m deep.
        # Contains a Camera sensor prim used by ROS2PublishImage.
        def Xform "camera_link"
        {
            double3 xformOp:translate = (0.38, 0, 0.62)
            uniform token[] xformOpOrder = ["xformOp:translate"]

            def Cube "mount"
            {
                double size = 1
                float3 xformOp:scale = (0.1, 0.16, 0.1)
                uniform token[] xformOpOrder = ["xformOp:scale"]
            }

            # Camera sensor prim.
            # ROS2PublishImage input: cameraPrim = /World/YahboomM3Pro/camera_link/sensor
            def Camera "sensor"
            {
                float2 clippingRange = (0.1, 10000)
                float focalLength = 24
                float focusDistance = 400
                float fStop = 0
                float horizontalAperture = 20.955
                token projection = "perspective"
                uniform token purpose = "default"
                float verticalAperture = 15.2908
                float3 xformOp:rotateXYZ = (0, 0, 0)
                double3 xformOp:translate = (0, 0, 0)
                uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateXYZ"]
            }
        }

        # LiDAR sensor mount: cylinder, r=0.16 m, h=0.08 m.
        # Positioned on top of the deck.
        # ROS2PublishLaserScan input: lidarPrim = /World/YahboomM3Pro/lidar_link
        def Cylinder "lidar_link"
        {
            double height = 0.08
            double radius = 0.16
            double3 xformOp:translate = (0, 0, 0.7)
            uniform token[] xformOpOrder = ["xformOp:translate"]
        }

        # Four mecanum wheels: cylinder r=0.11 m, h=0.08 m.
        # Rotated 90 degrees around X so the flat face points outward.
        # wheel_1 = front-right (+x, -y)
        def Cylinder "wheel_1"
        {
            double height = 0.08
            double radius = 0.11
            float3 xformOp:rotateXYZ = (90, 0, 0)
            double3 xformOp:translate = (0.32, 0.27, 0.16)
            uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateXYZ"]
        }

        # wheel_2 = front-left (+x, +y)
        def Cylinder "wheel_2"
        {
            double height = 0.08
            double radius = 0.11
            float3 xformOp:rotateXYZ = (90, 0, 0)
            double3 xformOp:translate = (0.32, -0.27, 0.16)
            uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateXYZ"]
        }

        # wheel_3 = rear-right (-x, -y)
        def Cylinder "wheel_3"
        {
            double height = 0.08
            double radius = 0.11
            float3 xformOp:rotateXYZ = (90, 0, 0)
            double3 xformOp:translate = (-0.32, 0.27, 0.16)
            uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateXYZ"]
        }

        # wheel_4 = rear-left (-x, +y)
        def Cylinder "wheel_4"
        {
            double height = 0.08
            double radius = 0.11
            float3 xformOp:rotateXYZ = (90, 0, 0)
            double3 xformOp:translate = (-0.32, -0.27, 0.16)
            uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateXYZ"]
        }
    }

    # Ground plane: 3 m x 3 m, 0.03 m thick.
    # Centred at origin, top surface at z=0.
    def Cube "Ground"
    {
        double size = 1
        float3 xformOp:scale = (3, 3, 0.03)
        double3 xformOp:translate = (0, 0, -0.03)
        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:scale"]
    }

    # ============================================================
    # OmniGraph Action Graph stubs [v2.4.2]
    #
    # This block defines the graph structure. The nodes will be
    # created and wired by add_yahboom_ros2_omnigraph.py when run
    # inside Isaac Sim. Until then, the graph exists as a named
    # Xform placeholder so the prim path is reserved.
    #
    # To activate: run add_yahboom_ros2_omnigraph.py inside Isaac Sim
    # then press Play and verify with verify_yahboom_live_topics.py --strict
    # ============================================================
    def Xform "ROS2ActionGraph" (
        doc = "Pending: replace with OmniGraph via add_yahboom_ros2_omnigraph.py"
    )
    {
        # Node stubs — for reference; actual OmniGraph nodes are
        # created by add_yahboom_ros2_omnigraph.py at runtime.
        #
        # OnPlaybackTick          -> ROS2Context
        # ROS2Context             -> ROS2PublishImage         /camera/image_raw
        # ROS2Context             -> ROS2PublishOdometry      /odom
        # ROS2Context             -> ROS2PublishTransformTree /tf
        # ROS2Context             -> ROS2PublishLaserScan     /scan
        # ROS2Context             -> ROS2SubscribeTwist       /cmd_vel
    }
}
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate Yahboom M3 Pro visible placeholder USDA stage [v2.4.1]"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the USDA content to stdout; do not write to disk.",
    )
    args = parser.parse_args()

    print("=" * 60)
    print(" Yahboom Visible Placeholder Stage Generator  [v2.4.1]")
    print("=" * 60)
    print()
    print("This generates a geometry-only placeholder USD stage.")
    print("It does NOT require Isaac Sim or ROS 2.")
    print()
    print("NOT photo-realistic. NO physics. NO ROS 2 publishers.")
    print("See docs/v2.4.1_yahboom_visible_stage_ros2_scaffold.md")
    print()

    if args.dry_run:
        print("[DRY-RUN] USDA content (not written to disk):")
        print("-" * 60)
        print(USDA_CONTENT)
        print("-" * 60)
        print()
        print(f"[DRY-RUN] Would write to: {OUT_PATH.relative_to(ROOT)}")
        print("[OK] Dry-run complete.")
        return 0

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(USDA_CONTENT)

    print(f"[OK] Written: {OUT_PATH.relative_to(ROOT)}")
    print()
    print("Next steps:")
    print("  1. Load this USDA in Isaac Sim.")
    print("  2. Enable the ROS 2 Bridge extension.")
    print("  3. Add OmniGraph action graphs (see doc for 5-node scaffold).")
    print("  4. Press Play.")
    print("  5. python3 scripts/gnm/verify_yahboom_live_topics.py --strict")
    return 0


if __name__ == "__main__":
    sys.exit(main())
