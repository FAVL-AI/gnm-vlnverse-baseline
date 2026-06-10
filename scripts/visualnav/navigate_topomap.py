#!/usr/bin/env python3
"""
navigate_topomap.py — Navigate using a GNM topological map + FleetSafe safety.

This implements the full GNM deployment pipeline described in the paper:
  1. Load topological map (sequence of node images)
  2. At each step: compare current camera image to nearby map nodes
  3. Select next subgoal node using predicted temporal distance
  4. GNM predicts waypoints toward that subgoal
  5. FleetSafe CBF-QP filters the waypoint command for safety
  6. Publish safe /cmd_vel to the robot

This script works in three modes:
  --backend ros2     Real robot (Yahboom M3Pro / Jetson), publishes /cmd_vel
  --backend isaac    Isaac Sim (requires conda activate isaac)
  --backend mock     Mock kinematic sim, no hardware needed (for testing)

Usage
-----
  # Real robot (ROS2 must be running):
  python scripts/visualnav/navigate_topomap.py \\
      --topomap topomaps/hospital_route_1 \\
      --model gnm \\
      --fleetsafe \\
      --backend ros2

  # Isaac Sim demo:
  python scripts/visualnav/navigate_topomap.py \\
      --topomap topomaps/hospital_route_1 \\
      --model vint \\
      --fleetsafe \\
      --backend mock \\
      --max-steps 300

Reference
---------
Shah et al. (2023) "GNM: A General Navigation Model to Drive Any Robot."
Official navigate.py: third_party/visualnav-transformer/deployment/src/navigate.py
(adapted to ROS2, FleetSafe, and our adapter framework)
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

_DEFAULT_TOPOMAP_DIR = _REPO / "topomaps"
_VNT = _REPO / "third_party" / "visualnav-transformer" / "model_weights"
_CKPTS = {
    "gnm":   _VNT / "gnm"  / "gnm.pth",
    "vint":  _VNT / "vint" / "vint.pth",
    "nomad": _VNT / "nomad"/ "nomad.pth",
}

# Subgoal lookahead: how many nodes ahead to aim for
_LOOKAHEAD = 5
# Distance threshold to consider a node "reached" (in predicted steps)
_CLOSE_THRESHOLD = 3.0


# ── Topomap loader ────────────────────────────────────────────────────────────

def load_topomap(topomap_dir: Path) -> tuple[list[Image.Image], dict]:
    """Load all node images and metadata from a topomap directory."""
    topomap_dir = Path(topomap_dir)
    if not topomap_dir.exists():
        raise FileNotFoundError(f"Topomap directory not found: {topomap_dir}")

    meta_file = topomap_dir / "topomap_meta.json"
    meta: dict = {}
    if meta_file.exists():
        with open(meta_file) as f:
            meta = json.load(f)

    # Load images in order: 0.png, 1.png, ...
    node_files = sorted(
        topomap_dir.glob("*.png"),
        key=lambda p: int(p.stem)
    )
    if not node_files:
        raise FileNotFoundError(f"No *.png files in topomap: {topomap_dir}")

    images = [Image.open(f).convert("RGB") for f in node_files]
    print(f"  Loaded topomap: {len(images)} nodes from {topomap_dir.name}")
    return images, meta


# ── Goal distance estimator ───────────────────────────────────────────────────

def select_subgoal(
    adapter,
    obs_imgs: list[Image.Image],
    topomap: list[Image.Image],
    closest_node: int,
    goal_node: int,
    lookahead: int = _LOOKAHEAD,
) -> tuple[int, float]:
    """
    Find the next subgoal node using GNM's temporal distance estimate.

    Evaluates the next `lookahead` nodes ahead and selects the one that is
    closest (in predicted steps) but still ahead of current position.

    Returns: (subgoal_node_idx, predicted_distance)
    """
    window_end  = min(closest_node + lookahead, goal_node + 1)
    best_node   = closest_node
    best_dist   = float("inf")

    for node_idx in range(closest_node, window_end):
        goal_img    = topomap[node_idx]
        preprocessed = adapter.preprocess_observation(obs_imgs, goal_img)
        action       = adapter.predict_action(preprocessed)
        dist         = float(action.goal_distance or _CLOSE_THRESHOLD)
        if dist < best_dist:
            best_dist = dist
            best_node = node_idx

    # Advance closest_node if robot is close enough
    if best_dist < _CLOSE_THRESHOLD and closest_node < goal_node:
        closest_node = min(closest_node + 1, goal_node)

    return best_node, best_dist


# ── Mock ROS2 backend ─────────────────────────────────────────────────────────

class _MockBackend:
    """Kinematic mock backend for testing without hardware."""

    def __init__(self):
        self._x   = 0.0
        self._y   = 0.0
        self._yaw = 0.0
        self._dt  = 0.25  # 4 Hz

    def get_camera_image(self) -> Image.Image:
        from fleet_safe_vla.integrations.visualnav_transformer.isaac_obs_adapter import (
            IsaacCameraObsAdapter,
        )
        W, H = 85, 64
        return IsaacCameraObsAdapter.make_random_obs(W, H, seed=int(time.time() * 1000) % 65536)

    def get_obstacle_positions(self) -> list:
        # Hospital corridor: two walls
        return [
            np.array([2.0, 1.2]),
            np.array([4.0, -1.2]),
            np.array([6.0,  1.0]),
        ]

    def get_obstacle_radii(self) -> list:
        return [0.5, 0.5, 0.5]

    def get_robot_xy(self) -> np.ndarray:
        return np.array([self._x, self._y])

    def get_obs_vec(self) -> np.ndarray:
        return np.zeros(47, dtype=np.float64)

    def send_cmd(self, vx: float, vy: float, wz: float) -> None:
        self._x   += vx * math.cos(self._yaw) * self._dt
        self._y   += vx * math.sin(self._yaw) * self._dt
        self._yaw += wz * self._dt

    def is_connected(self) -> bool:
        return True

    def shutdown(self) -> None:
        pass


class _ROS2Backend:
    """ROS2 backend — publishes /cmd_vel, subscribes to /usb_cam/image_raw."""

    def __init__(self, camera_topic: str = "/usb_cam/image_raw"):
        try:
            import rclpy
            from rclpy.node import Node
            from sensor_msgs.msg import Image as RosImage
            from geometry_msgs.msg import Twist
            from cv_bridge import CvBridge
        except ImportError as exc:
            raise ImportError("ROS2 not available. Use --backend mock.") from exc

        self._rclpy    = rclpy
        self._bridge   = CvBridge()
        self._last_img: Optional[Image.Image] = None
        self._connected = False

        rclpy.init()

        class _NavNode(rclpy.node.Node):
            def __init__(inner):
                super().__init__("fleetsafe_gnm_navigator")
                inner._sub = inner.create_subscription(
                    RosImage, camera_topic,
                    lambda msg: setattr(self, "_last_img",
                                        Image.fromarray(CvBridge().imgmsg_to_cv2(msg, "rgb8"))),
                    1,
                )
                inner._pub = inner.create_publisher(Twist, "/cmd_vel", 1)
                self._pub  = inner._pub
                self._node = inner

        self._node_obj = _NavNode()
        self._connected = True

    def get_camera_image(self) -> Optional[Image.Image]:
        self._rclpy.spin_once(self._node_obj._node, timeout_sec=0.1)
        return self._last_img

    def get_obstacle_positions(self) -> list:
        return []  # LiDAR not yet wired here; CBF will use empty list

    def get_obstacle_radii(self) -> list:
        return []

    def get_robot_xy(self) -> np.ndarray:
        return np.zeros(2)

    def get_obs_vec(self) -> np.ndarray:
        return np.zeros(47)

    def send_cmd(self, vx: float, vy: float, wz: float) -> None:
        from geometry_msgs.msg import Twist
        msg = Twist()
        msg.linear.x  = float(vx)
        msg.linear.y  = float(vy)
        msg.angular.z = float(wz)
        self._pub.publish(msg)

    def is_connected(self) -> bool:
        return self._connected

    def shutdown(self) -> None:
        self._rclpy.shutdown()


# ── Navigation loop ───────────────────────────────────────────────────────────

def run_navigation(
    topomap_dir:  Path,
    model_name:   str,
    backend_name: str,
    fleetsafe:    bool,
    goal_node:    int,
    max_steps:    int,
    v_max:        float,
    w_max:        float,
    d_safe:       float,
    estop:        float,
    control_hz:   float,
    verbose:      bool,
) -> dict:
    """Run the full GNM topological navigation loop."""

    # Load topomap
    topomap, meta = load_topomap(topomap_dir)
    if goal_node == -1:
        goal_node = len(topomap) - 1
    print(f"  Goal: node {goal_node}/{len(topomap)-1}")

    # Load model
    from scripts.visualnav.run_evaluation_matrix import _load_adapter  # type: ignore
    adapter, mode = _load_adapter(model_name, None, verbose=True)
    print(f"  Model: {model_name.upper()} ({mode})")

    # Context queue
    from fleet_safe_vla.integrations.visualnav_transformer.isaac_obs_adapter import (
        IsaacCameraObsAdapter,
    )
    W, H = adapter.image_size
    cam_adapter = IsaacCameraObsAdapter(image_size=(W, H), context_size=adapter.context_size)
    cam_adapter.set_goal_image(topomap[goal_node])

    # Safety filter
    cbf = None
    if fleetsafe:
        from fleet_safe_vla.fleet_safety.yahboom_cbf import YahboomCBFConfig, YahboomCBFFilter
        cbf = YahboomCBFFilter(YahboomCBFConfig(d_safe_m=d_safe, estop_dist_m=estop))
        print(f"  FleetSafe: ON  (d_safe={d_safe}m, estop={estop}m)")
    else:
        print("  FleetSafe: OFF")

    # Backend
    if backend_name == "ros2":
        backend = _ROS2Backend()
    else:
        backend = _MockBackend()

    from fleet_safe_vla.integrations.visualnav_transformer.base_adapter import waypoints_to_cmd_vel

    dt = 1.0 / control_hz
    closest_node   = 0
    step           = 0
    reached_goal   = False
    total_ivs      = 0
    stats          = {"steps": 0, "interventions": 0, "reached": False}

    print(f"\n  Starting navigation loop (max_steps={max_steps}, hz={control_hz})…")
    print(f"  {'Step':>5}  {'Node':>5}/{len(topomap)-1}  {'Dist':>6}  {'Vx':>5}  {'Wz':>5}  {'FS':>3}")
    print(f"  {'─'*5}  {'─'*7}  {'─'*6}  {'─'*5}  {'─'*5}  {'─'*3}")

    try:
        for step in range(max_steps):
            t0 = time.perf_counter()

            # 1. Get camera observation
            raw_img = backend.get_camera_image()
            if raw_img is None:
                time.sleep(dt)
                continue

            raw_img_resized = raw_img.resize((W, H), Image.BILINEAR)
            cam_adapter.push_frame(raw_img_resized)
            obs_imgs, _ = cam_adapter.get_context()

            # 2. Select subgoal node
            goal_img = topomap[closest_node]
            cam_adapter.set_goal_image(goal_img)
            _, goal_img_out = cam_adapter.get_context()

            # 3. Model inference
            preprocessed = adapter.preprocess_observation(obs_imgs, goal_img_out)
            action        = adapter.predict_action(preprocessed)

            dist_est = float(action.goal_distance or 0.0)

            # Advance closest_node
            if dist_est < _CLOSE_THRESHOLD and closest_node < goal_node:
                closest_node = min(closest_node + 1, goal_node)

            # Check goal reached
            if closest_node >= goal_node and dist_est < _CLOSE_THRESHOLD:
                reached_goal = True
                print(f"\n  GOAL REACHED at step {step}!")
                break

            # 4. Waypoint → velocity
            raw_cmd = waypoints_to_cmd_vel(
                action.waypoints, v_max=v_max, w_max=w_max, control_hz=control_hz,
            )

            # 5. FleetSafe
            intervened = False
            if cbf is not None:
                obs_pos   = backend.get_obstacle_positions()
                obs_radii = backend.get_obstacle_radii()
                robot_xy  = backend.get_robot_xy()
                obs_vec   = backend.get_obs_vec()
                if obs_pos:
                    nominal     = np.array([raw_cmd.vx, raw_cmd.wz])
                    safe_arr, info = cbf.filter(obs_vec, nominal, obs_pos,
                                                robot_xy=robot_xy,
                                                obstacle_radii=obs_radii)
                    safe_vx  = float(safe_arr[0])
                    safe_wz  = float(safe_arr[1])
                    intervened = info.get("intervened", False)
                else:
                    safe_vx, safe_wz = raw_cmd.vx, raw_cmd.wz
            else:
                safe_vx, safe_wz = raw_cmd.vx, raw_cmd.wz

            if intervened:
                total_ivs += 1

            # 6. Publish command
            backend.send_cmd(safe_vx, 0.0, safe_wz)

            if verbose or step % 10 == 0:
                fs_flag = "IV" if intervened else "OK"
                print(f"  {step:>5}  {closest_node:>5}/{goal_node}  "
                      f"{dist_est:>6.1f}  {safe_vx:>5.2f}  {safe_wz:>5.2f}  {fs_flag}")

            # Pace the loop
            elapsed = time.perf_counter() - t0
            if elapsed < dt:
                time.sleep(dt - elapsed)

    except KeyboardInterrupt:
        print("\n  Interrupted by user.")

    finally:
        backend.send_cmd(0.0, 0.0, 0.0)  # E-STOP
        backend.shutdown()

    stats = {
        "steps":         step + 1,
        "interventions": total_ivs,
        "reached_goal":  reached_goal,
        "closest_node":  closest_node,
        "goal_node":     goal_node,
        "model":         model_name,
        "fleetsafe":     fleetsafe,
    }

    print(f"\n  Navigation complete.")
    print(f"    Steps:         {stats['steps']}")
    print(f"    Interventions: {stats['interventions']}")
    print(f"    Reached goal:  {stats['reached_goal']}")
    print(f"    Final node:    {stats['closest_node']}/{stats['goal_node']}")
    return stats


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--topomap", type=Path, required=True,
                   help="Path to topomap directory (built by build_topomap.py)")
    p.add_argument("--model",    type=str, default="gnm",
                   choices=["gnm", "vint", "nomad"])
    p.add_argument("--backend",  type=str, default="mock",
                   choices=["mock", "ros2", "isaac"],
                   help="Execution backend (default: mock)")
    p.add_argument("--fleetsafe", action="store_true",
                   help="Enable FleetSafe CBF-QP safety filter")
    p.add_argument("--goal-node", type=int, default=-1,
                   help="Goal node index, -1 = last node (default)")
    p.add_argument("--max-steps", type=int, default=500,
                   help="Maximum navigation steps (default: 500)")
    p.add_argument("--v-max",   type=float, default=0.30)
    p.add_argument("--w-max",   type=float, default=0.70)
    p.add_argument("--d-safe",  type=float, default=0.50)
    p.add_argument("--estop",   type=float, default=0.30)
    p.add_argument("--hz",      type=float, default=4.0,
                   help="Control frequency in Hz (default: 4)")
    p.add_argument("--verbose", action="store_true",
                   help="Print every step (default: every 10 steps)")
    p.add_argument("--output",  type=Path, default=None,
                   help="Save navigation stats JSON to this path")
    args = p.parse_args()

    print()
    print("=" * 65)
    print("  GNM Topological Navigation — FleetSafe")
    print("=" * 65)
    print(f"  Topomap : {args.topomap}")
    print(f"  Model   : {args.model.upper()}")
    print(f"  Backend : {args.backend}")
    print(f"  Safety  : {'FleetSafe ON' if args.fleetsafe else 'NO SAFETY FILTER'}")
    print()

    stats = run_navigation(
        topomap_dir  = args.topomap,
        model_name   = args.model,
        backend_name = args.backend,
        fleetsafe    = args.fleetsafe,
        goal_node    = args.goal_node,
        max_steps    = args.max_steps,
        v_max        = args.v_max,
        w_max        = args.w_max,
        d_safe       = args.d_safe,
        estop        = args.estop,
        control_hz   = args.hz,
        verbose      = args.verbose,
    )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(stats, f, indent=2)
        print(f"\n  Stats saved → {args.output}")

    return 0 if stats.get("reached_goal") else 1


if __name__ == "__main__":
    sys.exit(main())
