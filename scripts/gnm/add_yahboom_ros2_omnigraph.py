#!/usr/bin/env python3
"""Create the Yahboom M3 Pro ROS 2 OmniGraph action graph in Isaac Sim.

This script must be run from Isaac Sim's Python interpreter with the
Yahboom visible placeholder stage loaded and the ROS 2 Bridge enabled.

Usage (from a terminal with Isaac Sim installed):
    ~/.local/share/ov/pkg/isaac-sim-*/python.sh \\
        scripts/gnm/add_yahboom_ros2_omnigraph.py

Or paste into Isaac Sim's Script Editor (Window → Script Editor) and run.

When Isaac Sim Python is not available (CI / standard Python), the script
prints the graph structure and exits 0.

After running this script:
    1. Press Play in Isaac Sim.
    2. In a separate terminal:
       python3 scripts/gnm/verify_yahboom_live_topics.py --strict
    3. All five topics must pass.
    4. File → Save (to persist OmniGraph nodes in the USDA).
"""

import sys

GRAPH_PATH = "/World/ROS2ActionGraph"

ROBOT_BASE = "/World/YahboomM3Pro"

# Prim paths used by each publisher node.
CAMERA_PRIM = "/World/YahboomM3Pro/camera_link/sensor"
BASE_LINK_PRIM = "/World/YahboomM3Pro/base_link"
LIDAR_PRIM = "/World/YahboomM3Pro/lidar_link"

TOPIC_MAP = {
    "ROS2PublishImage":         "/camera/image_raw",
    "ROS2PublishOdometry":      "/odom",
    "ROS2PublishTransformTree": "/tf",
    "ROS2PublishLaserScan":     "/scan",
    "ROS2SubscribeTwist":       "/cmd_vel",
}


def print_graph_plan():
    print()
    print("OmniGraph action graph plan:")
    print(f"  Graph path  : {GRAPH_PATH}")
    print(f"  Camera prim : {CAMERA_PRIM}")
    print(f"  Base link   : {BASE_LINK_PRIM}")
    print(f"  LiDAR prim  : {LIDAR_PRIM}")
    print()
    print("  Nodes:")
    print("    OnPlaybackTick          omni.graph.action.OnPlaybackTick")
    print("    ROS2Context             omni.isaac.ros2_bridge.ROS2Context")
    for name, topic in TOPIC_MAP.items():
        ns = "omni.isaac.ros2_bridge"
        print(f"    {name:<27s} {ns}.{name}  → {topic}")
    print()
    print("  Connections:")
    print("    OnPlaybackTick.outputs:tick → ROS2Context.inputs:execIn")
    for name in TOPIC_MAP:
        print(
            f"    ROS2Context.outputs:execOut → {name}.inputs:execIn"
        )
    print()


def create_graph_via_omni():
    """Create the OmniGraph using Isaac Sim's omni.graph.core API."""
    import omni.graph.core as og  # type: ignore

    keys = og.Controller.Keys

    (graph, nodes, _, _) = og.Controller.edit(
        {
            "graph_path": GRAPH_PATH,
            "evaluator_name": "execution",
            "pipeline_stage": og.GraphPipelineStage.GRAPH_PIPELINE_STAGE_SIMULATION,
        },
        {
            keys.CREATE_NODES: [
                ("OnPlaybackTick", "omni.graph.action.OnPlaybackTick"),
                ("ROS2Context", "omni.isaac.ros2_bridge.ROS2Context"),
                ("ROS2PublishImage", "omni.isaac.ros2_bridge.ROS2PublishImage"),
                ("ROS2PublishOdometry", "omni.isaac.ros2_bridge.ROS2PublishOdometry"),
                ("ROS2PublishTransformTree", "omni.isaac.ros2_bridge.ROS2PublishTransformTree"),
                ("ROS2PublishLaserScan", "omni.isaac.ros2_bridge.ROS2PublishLaserScan"),
                ("ROS2SubscribeTwist", "omni.isaac.ros2_bridge.ROS2SubscribeTwist"),
            ],
            keys.SET_VALUES: [
                ("ROS2PublishImage.inputs:topicName", "/camera/image_raw"),
                ("ROS2PublishImage.inputs:cameraPrim", CAMERA_PRIM),
                ("ROS2PublishOdometry.inputs:topicName", "/odom"),
                ("ROS2PublishOdometry.inputs:chassisPrim", [BASE_LINK_PRIM]),
                ("ROS2PublishTransformTree.inputs:topicName", "/tf"),
                ("ROS2PublishTransformTree.inputs:targetPrims", [ROBOT_BASE]),
                ("ROS2PublishLaserScan.inputs:topicName", "/scan"),
                ("ROS2PublishLaserScan.inputs:lidarPrim", LIDAR_PRIM),
                ("ROS2SubscribeTwist.inputs:topicName", "/cmd_vel"),
            ],
            keys.CONNECT: [
                ("OnPlaybackTick.outputs:tick", "ROS2Context.inputs:execIn"),
                ("ROS2Context.outputs:execOut", "ROS2PublishImage.inputs:execIn"),
                ("ROS2Context.outputs:execOut", "ROS2PublishOdometry.inputs:execIn"),
                ("ROS2Context.outputs:execOut", "ROS2PublishTransformTree.inputs:execIn"),
                ("ROS2Context.outputs:execOut", "ROS2PublishLaserScan.inputs:execIn"),
                ("ROS2Context.outputs:execOut", "ROS2SubscribeTwist.inputs:execIn"),
            ],
        },
    )

    return graph


def main() -> int:
    print("=" * 60)
    print(" Yahboom M3 Pro ROS 2 OmniGraph Creator  [v2.4.2]")
    print("=" * 60)
    print()

    print_graph_plan()

    try:
        import omni.graph.core  # type: ignore
        omni_available = True
    except ImportError:
        omni_available = False

    if not omni_available:
        print("[INFO] omni.graph.core not found.")
        print("[INFO] This script must run inside Isaac Sim's Python interpreter.")
        print("[INFO] Run it with:")
        print(f"  ~/.local/share/ov/pkg/isaac-sim-*/python.sh {__file__}")
        print()
        print("[INFO] Or paste the script into Isaac Sim's Script Editor:")
        print("  Window → Script Editor → paste → Run")
        print()
        print("[INFO] Pre-conditions:")
        print(f"  1. Stage loaded: assets/robots/yahboom_m3_pro/yahboom_m3pro_visible_placeholder.usda")
        print("  2. ROS 2 Bridge extension enabled (Window → Extensions → ROS2 Bridge)")
        print("  3. Stage NOT in Play mode yet (add graph before pressing Play)")
        print()
        print("[OK] Dry-run complete (omni.graph.core not available).")
        return 0

    print("[INFO] omni.graph.core available — creating OmniGraph...")
    print()

    try:
        graph = create_graph_via_omni()
        print(f"[OK] Graph created: {GRAPH_PATH}")
        print()
        print("Next steps:")
        print("  1. Press Play in Isaac Sim.")
        print("  2. In a terminal:")
        print("     python3 scripts/gnm/verify_yahboom_live_topics.py --strict")
        print("  3. All five topics must pass.")
        print("  4. File → Save to persist the graph in the USDA.")
        return 0
    except Exception as exc:
        print(f"[FAIL] Failed to create OmniGraph: {exc}")
        print()
        print("[HINT] Common causes:")
        print("  - Stage not loaded (File → Open the USDA first)")
        print("  - ROS 2 Bridge extension not enabled")
        print("  - Graph path already exists — delete /World/ROS2ActionGraph and retry")
        print("  - Isaac Sim version mismatch — check node type names in the GUI")
        return 1


if __name__ == "__main__":
    sys.exit(main())
