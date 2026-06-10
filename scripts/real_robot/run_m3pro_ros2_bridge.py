"""
run_m3pro_ros2_bridge.py — Real Yahboom RosMaster M3Pro → FleetSafe WebSocket bridge

Subscribes to ROS2 Humble topics published by the physical M3Pro:
  /odom              nav_msgs/Odometry
  /joint_states      sensor_msgs/JointState  (fl/fr/rl/rr_wheel_joint)
  /scan              sensor_msgs/LaserScan
  /imu/data          sensor_msgs/Imu
  /fleet_safe/status fleet_safe_msgs/SafetyStatus  (optional)

Publishes:
  /cmd_vel           geometry_msgs/Twist   (from dashboard controls)
  /fleet_safe/estop  std_msgs/Bool         (from dashboard STOP button)

Streams JSON telemetry to WebSocket ws://0.0.0.0:8766 at 20 Hz.
Telemetry format mirrors the Isaac bridge (port 8765) so the dashboard
can switch sources without code changes.

Usage:
    ./scripts/real_robot/run_m3pro_ros2_bridge.sh
    # or directly (ROS2 must be sourced):
    source /opt/ros/humble/setup.bash
    python scripts/real_robot/run_m3pro_ros2_bridge.py [--ws-port 8766] [--hz 20]

Connection strategy (robot IP):
    Prefer ASK4/LAN/DHCP discovery (discover_yahboom.sh).
    Only use 192.168.8.88 in hotspot/AP mode (--hotspot).
    This bridge does NOT handle robot IP — it bridges ROS2 topics
    which are available once the ROS2 network is reachable.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import queue
import sys
import threading
import time
from pathlib import Path

# ── Argument parsing (before any ROS2 imports) ────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from fleet_safe_vla.safety.certificate_logger import SafetyCertificateLogger
    _HAS_CERT_LOGGER = True
except ImportError:
    _HAS_CERT_LOGGER = False

parser = argparse.ArgumentParser(description="M3Pro ROS2 → FleetSafe WebSocket bridge")
parser.add_argument("--ws-port", type=int, default=8766,
                    help="WebSocket port (default: 8766)")
parser.add_argument("--hz",      type=float, default=20.0,
                    help="Telemetry broadcast rate Hz (default: 20)")
parser.add_argument("--ros-domain-id", type=int, default=None,
                    help="ROS_DOMAIN_ID (overrides env var)")
parser.add_argument("--robot-ip", type=str, default=None,
                    help="Robot IP for informational display only (bridge uses ROS2 DDS, not TCP/IP)")
parser.add_argument("--cert-log", type=Path, default=None,
                    help="Write telemetry-only safety certificates to this JSONL path. "
                         "NOTE: this bridge has no CBF-QP filter; certificates are marked "
                         "telemetry-only and safe=False unless distance is verified.")
args_cli = parser.parse_args()

# ── ROS2 import (optional — bridge starts even if ROS2 is absent) ─────────────
try:
    import rclpy
    from rclpy.node import Node
    from geometry_msgs.msg import Twist
    from nav_msgs.msg import Odometry
    from sensor_msgs.msg import JointState, LaserScan, Imu
    from std_msgs.msg import Bool
    _HAS_ROS2 = True
except ImportError:
    _HAS_ROS2 = False

# websockets is available in the isaac conda env and in system Python with pip
try:
    import websockets
except ImportError:
    print("[ERROR] 'websockets' package not found.")
    print("  pip install websockets")
    sys.exit(1)


# ── Shared bridge state ───────────────────────────────────────────────────────
_state_lock = threading.Lock()
_state: dict = {
    "type":           "telemetry",
    "source":         "real_m3pro",
    "robot":          "M3Pro",
    "t":              0.0,
    "ros2_connected": False,
    "sim": {
        "status":     "OFFLINE",
        "step":       0,
        "physics_hz": args_cli.hz,
    },
    "pose": {"x": 0.0, "y": 0.0, "z": 0.0, "yaw": 0.0, "pitch": 0.0, "roll": 0.0},
    "velocity": {"vx": 0.0, "vy": 0.0, "vz": 0.0, "wx": 0.0, "wy": 0.0, "wz": 0.0},
    "joints": {
        "names":      ["fl_wheel_joint", "fr_wheel_joint", "rl_wheel_joint", "rr_wheel_joint"],
        "positions":  [0.0, 0.0, 0.0, 0.0],
        "velocities": [0.0, 0.0, 0.0, 0.0],
    },
    "cmd_vel":  {"vx": 0.0, "vy": 0.0, "wz": 0.0},
    "safety":   {"state": "NOMINAL", "is_safe": True, "estop": False,
                 "cbf_active": False, "intervention_count": 0},
    "imu":      {"ax": 0.0, "ay": 0.0, "az": 0.0, "wx": 0.0, "wy": 0.0, "wz": 0.0},
    "scan":     {"min_dist": -1.0, "angle_min": -math.pi, "angle_max": math.pi,
                 "range_count": 0},
    "topics":   {"odom": False, "joint_states": False, "scan": False,
                 "imu": False, "safety": False},
    "episode":  {"step": 0, "reset_count": 0, "contact_detected": False},
}
_cmd_queue: queue.Queue = queue.Queue()

# ── Safety certificate logger (telemetry-only) ────────────────────────────────
_cert_logger = None

# ── WebSocket server (daemon thread) ──────────────────────────────────────────
_ws_clients: set = set()


async def _ws_handler(websocket):
    _ws_clients.add(websocket)
    try:
        async for raw in websocket:
            try:
                _cmd_queue.put_nowait(json.loads(raw))
            except (json.JSONDecodeError, ValueError):
                pass
    except Exception:
        pass
    finally:
        _ws_clients.discard(websocket)


async def _broadcast_loop(hz: float):
    interval = 1.0 / hz
    while True:
        if _ws_clients:
            with _state_lock:
                payload = json.dumps(_state)
            dead = set()
            for ws in list(_ws_clients):
                try:
                    await ws.send(payload)
                except Exception:
                    dead.add(ws)
            for ws in dead:
                _ws_clients.discard(ws)
        await asyncio.sleep(interval)


def _start_ws_server(port: int, hz: float):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def _serve():
        async with websockets.serve(_ws_handler, "0.0.0.0", port):
            print(f"[Bridge] WebSocket server → ws://0.0.0.0:{port}")
            await _broadcast_loop(hz)

    loop.run_until_complete(_serve())


# ── Command dispatcher (main thread, called from ROS2 spin loop) ──────────────
_pub_cmd:   "rclpy.Publisher | None" = None   # type: ignore[name-defined]
_pub_estop: "rclpy.Publisher | None" = None   # type: ignore[name-defined]
_step = 0


def _drain_cmd_queue():
    global _step
    while not _cmd_queue.empty():
        try:
            cmd = _cmd_queue.get_nowait()
        except queue.Empty:
            break

        kind = cmd.get("type", "")
        _step += 1

        if kind == "cmd_vel" and _pub_cmd is not None:
            msg = Twist()
            msg.linear.x  = float(cmd.get("vx", 0.0))
            msg.linear.y  = float(cmd.get("vy", 0.0))
            msg.angular.z = float(cmd.get("wz", 0.0))
            _pub_cmd.publish(msg)
            with _state_lock:
                _state["cmd_vel"]["vx"] = msg.linear.x
                _state["cmd_vel"]["vy"] = msg.linear.y
                _state["cmd_vel"]["wz"] = msg.angular.z

        elif kind == "stop" and _pub_cmd is not None:
            _pub_cmd.publish(Twist())
            with _state_lock:
                _state["cmd_vel"] = {"vx": 0.0, "vy": 0.0, "wz": 0.0}

        elif kind == "estop" and _pub_estop is not None:
            msg = Bool()
            msg.data = True
            _pub_estop.publish(msg)
            with _state_lock:
                _state["safety"]["estop"] = True
                _state["safety"]["state"] = "EMERGENCY"


# ── ROS2 Node ─────────────────────────────────────────────────────────────────

class M3ProBridgeNode(Node if _HAS_ROS2 else object):  # type: ignore[misc]
    """Subscribe to M3Pro topics and update shared _state."""

    def __init__(self):
        if not _HAS_ROS2:
            return
        super().__init__("m3pro_fleetsafe_bridge")

        # Publishers
        global _pub_cmd, _pub_estop
        _pub_cmd   = self.create_publisher(Twist, "/cmd_vel",          10)
        _pub_estop = self.create_publisher(Bool,  "/fleet_safe/estop", 10)

        # Subscribers
        self.create_subscription(Odometry,  "/odom",             self._cb_odom,   10)
        self.create_subscription(JointState,"/joint_states",     self._cb_joints, 10)
        self.create_subscription(LaserScan, "/scan",             self._cb_scan,   10)
        self.create_subscription(Imu,       "/imu/data",         self._cb_imu,    10)

        # Drain cmd queue at 20 Hz
        self.create_timer(0.05, _drain_cmd_queue)

        self.get_logger().info(
            f"M3Pro bridge node ready. WS → ws://0.0.0.0:{args_cli.ws_port}"
        )
        with _state_lock:
            _state["ros2_connected"] = True
            _state["sim"]["status"]  = "LIVE"

    # ── Topic callbacks ───────────────────────────────────────────────────────

    def _cb_odom(self, msg: "Odometry"):
        p = msg.pose.pose
        v = msg.twist.twist

        # Quaternion → Euler (yaw/pitch/roll)
        qx, qy, qz, qw = p.orientation.x, p.orientation.y, p.orientation.z, p.orientation.w
        siny_cosp =  2.0 * (qw * qz + qx * qy)
        cosy_cosp =  1.0 - 2.0 * (qy * qy + qz * qz)
        yaw   = math.atan2(siny_cosp, cosy_cosp)
        sinp  = 2.0 * (qw * qy - qz * qx)
        pitch = math.asin(max(-1.0, min(1.0, sinp)))
        sinr_cosp =  2.0 * (qw * qx + qy * qz)
        cosr_cosp =  1.0 - 2.0 * (qx * qx + qy * qy)
        roll  = math.atan2(sinr_cosp, cosr_cosp)

        with _state_lock:
            _state["t"]    = time.time()
            _state["pose"] = {
                "x": p.position.x, "y": p.position.y, "z": p.position.z,
                "yaw": yaw, "pitch": pitch, "roll": roll,
            }
            _state["velocity"] = {
                "vx": v.linear.x,  "vy": v.linear.y,  "vz": v.linear.z,
                "wx": v.angular.x, "wy": v.angular.y, "wz": v.angular.z,
            }
            _state["topics"]["odom"] = True
            _state["episode"]["step"] += 1

    def _cb_joints(self, msg: "JointState"):
        # M3Pro wheels: fl/fr/rl/rr
        target = ["fl_wheel_joint", "fr_wheel_joint", "rl_wheel_joint", "rr_wheel_joint"]
        name_idx = {n: i for i, n in enumerate(msg.name)}
        positions  = []
        velocities = []
        for jname in target:
            idx = name_idx.get(jname)
            positions.append( msg.position[idx]  if idx is not None and idx < len(msg.position)  else 0.0)
            velocities.append(msg.velocity[idx]  if idx is not None and idx < len(msg.velocity)  else 0.0)

        with _state_lock:
            _state["joints"] = {
                "names":      target,
                "positions":  positions,
                "velocities": velocities,
            }
            _state["topics"]["joint_states"] = True

    def _cb_scan(self, msg: "LaserScan"):
        ranges = [r for r in msg.ranges if math.isfinite(r) and msg.range_min < r < msg.range_max]
        min_dist = min(ranges) if ranges else -1.0
        with _state_lock:
            _state["scan"] = {
                "min_dist":   round(min_dist, 3),
                "angle_min":  msg.angle_min,
                "angle_max":  msg.angle_max,
                "range_count": len(msg.ranges),
            }
            _state["topics"]["scan"] = True
            # Trigger safety warning if too close
            if 0.0 < min_dist < 0.30:
                _state["safety"]["state"] = "WARNING"
            elif min_dist < 0.15:
                _state["safety"]["state"] = "EMERGENCY"
                _state["safety"]["estop"] = True
            _cmd = _state["cmd_vel"]

        # ── Telemetry-only certificate (no CBF-QP active) ─────────────────────
        # This bridge does not run a CBF-QP filter.  Certificates are marked
        # telemetry-only so they cannot be used to make formal safety claims.
        if _cert_logger is not None and min_dist >= 0.0:
            D_SAFE = 0.5
            _h = round(min_dist ** 2 - D_SAFE ** 2, 4)
            _cert_logger.append_from_values(
                timestamp=time.time(),
                model_name="telemetry_bridge",
                u_nom=[round(_cmd.get("vx", 0.0), 4), round(_cmd.get("wz", 0.0), 4)],
                u_safe=[round(_cmd.get("vx", 0.0), 4), round(_cmd.get("wz", 0.0), 4)],
                h_min=_h,
                min_dist_m=round(min_dist, 4),
                cbf_active=False,
                qp_status="not_available",
                constraint_margin_min=0.0,
                latency_ms=0.0,
                safe=min_dist >= D_SAFE,
                notes="telemetry-only bridge; no CBF-QP safety certificate generated",
            )

    def _cb_imu(self, msg: "Imu"):
        with _state_lock:
            _state["imu"] = {
                "ax": msg.linear_acceleration.x,
                "ay": msg.linear_acceleration.y,
                "az": msg.linear_acceleration.z,
                "wx": msg.angular_velocity.x,
                "wy": msg.angular_velocity.y,
                "wz": msg.angular_velocity.z,
            }
            _state["topics"]["imu"] = True


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global _cert_logger
    if args_cli.ros_domain_id is not None:
        import os
        os.environ["ROS_DOMAIN_ID"] = str(args_cli.ros_domain_id)

    if args_cli.cert_log and _HAS_CERT_LOGGER:
        _cert_logger = SafetyCertificateLogger(args_cli.cert_log)
        print(f"[Bridge] Safety certificate log → {args_cli.cert_log}")
        print("[Bridge] NOTE: this bridge has no CBF-QP filter.")
        print("         Certificates are marked 'telemetry-only'; safe=False unless dist >= d_safe.")
    elif args_cli.cert_log and not _HAS_CERT_LOGGER:
        print("[Bridge] WARNING: --cert-log requested but fleet_safe_vla not importable; skipping.")

    print("=" * 62)
    print("  Fleet-Safe-VLA-OS  |  M3Pro ROS2 Telemetry Bridge")
    print(f"  WS Bridge : ws://localhost:{args_cli.ws_port}")
    print(f"  Dashboard : http://localhost:8080/yahboom  (source=real_m3pro)")
    print(f"  ROS2      : {'available' if _HAS_ROS2 else 'NOT FOUND — install ros-humble'}")
    if args_cli.robot_ip:
        print(f"  Robot IP  : {args_cli.robot_ip}")
    print("=" * 62)
    print()

    if not _HAS_ROS2:
        print("[WARN] rclpy not found. Bridge will run with ros2_connected=false.")
        print("  To connect to the M3Pro ROS2 topics, run:")
        print("    source /opt/ros/humble/setup.bash")
        print("  Then re-run this script.")
        print()

    # Start WebSocket server in daemon thread
    ws_thread = threading.Thread(
        target=_start_ws_server,
        args=(args_cli.ws_port, args_cli.hz),
        daemon=True,
        name="ws-server",
    )
    ws_thread.start()
    time.sleep(0.2)  # let server bind before printing

    if not _HAS_ROS2:
        print("[Bridge] Running in disconnected mode — WebSocket active, no ROS2 topics.")
        print("         Ctrl+C to exit.")
        try:
            while True:
                time.sleep(1.0)
                with _state_lock:
                    _state["t"] = time.time()
        except KeyboardInterrupt:
            pass
        return

    # ROS2 path
    rclpy.init()
    node = M3ProBridgeNode()
    print(f"[Bridge] Subscribing to /odom /joint_states /scan /imu/data")
    print(f"[Bridge] Publishing  to /cmd_vel /fleet_safe/estop")
    print(f"[Bridge] Dashboard commands accepted from ws://0.0.0.0:{args_cli.ws_port}")
    print()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        # Zero cmd_vel on exit for safety
        if _pub_cmd is not None:
            _pub_cmd.publish(Twist())
        node.destroy_node()
        rclpy.shutdown()
        print("\n[Bridge] Shutdown complete.")


if __name__ == "__main__":
    main()
