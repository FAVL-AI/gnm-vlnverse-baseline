"""
run_yahboom_bridge.py — Isaac Sim → FleetSafe telemetry bridge

Runs Isaac Sim in headless mode (default) as the simulation backend,
streams robot state over WebSocket port 8765, and accepts commands from
the FleetSafe operator dashboard at http://localhost:8080/yahboom.

Architecture:
  Isaac Sim (main thread, headless)
    └─ Articulation step loop  100 Hz physics
         ├─ Extracts pose / velocity / joints / safety
         └─ Writes to thread-safe _state dict

  WebSocket server (daemon thread, asyncio)
    ├─ ws://0.0.0.0:8765  → broadcast _state JSON at 10 Hz
    └─ Receives cmd_vel / reset / stop / pause commands from browser

Usage:
    ./scripts/isaaclab/run_yahboom_bridge.sh          # headless (default)
    ./scripts/isaaclab/run_yahboom_bridge.sh --gui    # with Isaac Sim GUI
    ./scripts/isaaclab/run_yahboom_bridge.sh --robot m3pro  (URDF pending)
"""
from __future__ import annotations

import argparse
import math
import queue
import sys
import threading
import time
from pathlib import Path

# ── Step 1: AppLauncher FIRST ──────────────────────────────────────────────────
try:
    from isaaclab.app import AppLauncher
except ModuleNotFoundError:
    print(
        "[ERROR] 'isaaclab' not found.\n"
        "  Activate the isaac conda environment:\n"
        "    conda activate isaac"
    )
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parents[2]

_ROBOTS = {
    "x3": {
        "label": "RosMaster X3",
        "urdf": REPO_ROOT / "fleet_safe_vla/robots/yahboom/urdf/yahboom_x3.urdf",
        "usd_cache": REPO_ROOT / "data/usd_cache/yahboom_x3",
        "prim": "/World/Yahboom",
        "wheel_joints": ["left_wheel_joint", "right_wheel_joint"],
        "wheelbase_m": 0.160,
        "wheel_radius_m": 0.048,
        "max_vx_ms": 0.5,
        "max_wz_rs": 1.0,
    },
    "m3pro": {
        "label": "RosMaster M3Pro",
        "urdf": REPO_ROOT / "fleet_safe_vla/robots/yahboom/urdf/yahboom_m3pro.urdf",
        "usd_cache": REPO_ROOT / "data/usd_cache/yahboom_m3pro",
        "prim": "/World/Yahboom",
        "wheel_joints": ["fl_wheel_joint", "fr_wheel_joint", "rl_wheel_joint", "rr_wheel_joint"],
        "wheelbase_m": 0.155,
        "wheel_radius_m": 0.048,
        "max_vx_ms": 0.5,
        "max_wz_rs": 1.0,
    },
}

parser = argparse.ArgumentParser(description="Yahboom Isaac Sim telemetry bridge")
parser.add_argument("--robot",    type=str, default="x3", choices=list(_ROBOTS))
parser.add_argument("--ws-port",  type=int, default=8765, help="WebSocket port (default 8765)")
parser.add_argument("--gui",      action="store_true",   help="Enable Isaac Sim GUI window")
parser.add_argument("--physics-hz", type=float, default=100.0, help="Physics Hz (default 100)")
parser.add_argument("--tele-hz",    type=float, default=10.0,  help="Telemetry broadcast Hz")
parser.add_argument("--sync-real-robot", action="store_true",
                    help="Subscribe to /odom and mirror real robot pose into Isaac Sim (digital twin mode)")
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()

# Bridge mode is headless by default; --gui overrides
if not args_cli.gui:
    args_cli.headless = True

app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

# ── Step 2: ALL Isaac Lab / omni imports AFTER AppLauncher ────────────────────
import json  # noqa: E402

import torch  # noqa: E402
import websockets  # noqa: E402
import asyncio  # noqa: E402

import isaaclab.sim as sim_utils  # noqa: E402
from isaaclab.actuators import ImplicitActuatorCfg  # noqa: E402
from isaaclab.assets import Articulation, ArticulationCfg  # noqa: E402
from isaaclab.sim import SimulationContext  # noqa: E402
from isaaclab.sim.converters import UrdfConverterCfg  # noqa: E402
from isaaclab.sim.spawners.from_files import UrdfFileCfg  # noqa: E402


# ── Shared bridge state ───────────────────────────────────────────────────────
_state_lock   = threading.Lock()
_state: dict  = {
    "type": "telemetry",
    "t": 0.0,
    "sim":    {"status": "STARTING", "step": 0, "physics_hz": args_cli.physics_hz},
    "pose":   {"x": 0.0, "y": 0.0, "z": 0.0, "yaw": 0.0, "pitch": 0.0, "roll": 0.0},
    "velocity": {"vx": 0.0, "vy": 0.0, "vz": 0.0, "wx": 0.0, "wy": 0.0, "wz": 0.0},
    "joints": {"names": [], "positions": [], "velocities": []},
    "cmd_vel": {"vx": 0.0, "wz": 0.0},
    "safety": {"state": "NOMINAL", "is_safe": True, "cbf_active": False, "intervention_count": 0},
    "episode": {"step": 0, "reset_count": 0, "contact_detected": False},
    # Real robot digital twin sync (populated when --sync-real-robot is set)
    "real_robot": {
        "live":         False,
        "x":            0.0,
        "y":            0.0,
        "yaw":          0.0,
        "ts":           0.0,
        "divergence_m": 0.0,   # |isaac_pos - real_pos| in metres
    },
}
_cmd_queue: queue.Queue = queue.Queue()

# ── Real robot pose (written by ROS2 thread, read by main sim loop) ───────────
_real_pose_lock = threading.Lock()
_real_pose: dict | None = None   # {x, y, yaw} or None

# ── WebSocket bridge (daemon thread) ──────────────────────────────────────────
_ws_clients: set = set()


async def _ws_handler(websocket):
    """Accept a client and queue any incoming command messages."""
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
    """Broadcast current _state to all connected clients at `hz` Hz."""
    interval = 1.0 / hz
    while True:
        if _ws_clients:
            with _state_lock:
                payload = json.dumps(_state)
            dead_clients = set()
            for ws in list(_ws_clients):
                try:
                    await ws.send(payload)
                except Exception:
                    dead_clients.add(ws)
            for ws in dead_clients:
                _ws_clients.discard(ws)
        await asyncio.sleep(interval)


def _start_ws_server(port: int, tele_hz: float):
    """Entry point for the daemon WebSocket thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def main():
        async with websockets.serve(_ws_handler, "0.0.0.0", port):
            print(f"[Bridge] WebSocket server → ws://0.0.0.0:{port}")
            await _broadcast_loop(tele_hz)

    loop.run_until_complete(main())


# ── Kinematics ────────────────────────────────────────────────────────────────
def _cmd_vel_to_wheels(vx: float, wz: float, rdef: dict) -> tuple[float, float]:
    """Differential-drive cmd_vel → (left_rad_s, right_rad_s)."""
    L, r = rdef["wheelbase_m"], rdef["wheel_radius_m"]
    left  = (vx - wz * L / 2.0) / r
    right = (vx + wz * L / 2.0) / r
    return float(left), float(right)


def _quat_to_euler(qw: float, qx: float, qy: float, qz: float) -> tuple[float, float, float]:
    """Quaternion (w,x,y,z) → (roll, pitch, yaw) in radians."""
    roll  = math.atan2(2*(qw*qx + qy*qz), 1 - 2*(qx*qx + qy*qy))
    sinp  = 2*(qw*qy - qz*qx)
    pitch = math.asin(max(-1.0, min(1.0, sinp)))
    yaw   = math.atan2(2*(qw*qz + qx*qy), 1 - 2*(qy*qy + qz*qz))
    return roll, pitch, yaw


# ── Scene ─────────────────────────────────────────────────────────────────────
def _build_cfg(rdef: dict) -> ArticulationCfg:
    rdef["usd_cache"].mkdir(parents=True, exist_ok=True)
    return ArticulationCfg(
        prim_path=rdef["prim"],
        spawn=UrdfFileCfg(
            asset_path=str(rdef["urdf"]),
            usd_dir=str(rdef["usd_cache"]),
            fix_base=False,
            merge_fixed_joints=True,
            self_collision=False,
            joint_drive=UrdfConverterCfg.JointDriveCfg(
                target_type="velocity",
                gains=UrdfConverterCfg.JointDriveCfg.PDGainsCfg(stiffness=0.0, damping=2.0),
            ),
        ),
        init_state=ArticulationCfg.InitialStateCfg(
            pos=(0.0, 0.0, 0.0),
            joint_pos={j: 0.0 for j in rdef["wheel_joints"]},
        ),
        actuators={
            "wheels": ImplicitActuatorCfg(
                joint_names_expr=[".*wheel.*"],
                effort_limit_sim=1.0,
                velocity_limit_sim=20.0,
                stiffness=0.0,
                damping=0.1,
            )
        },
    )


def _design_scene(rdef: dict) -> Articulation:
    sim_utils.GroundPlaneCfg().func("/World/GroundPlane", sim_utils.GroundPlaneCfg())
    sim_utils.DomeLightCfg(intensity=2000.0, color=(0.9, 0.9, 1.0)).func("/World/Light", sim_utils.DomeLightCfg(intensity=2000.0, color=(0.9, 0.9, 1.0)))
    return Articulation(cfg=_build_cfg(rdef))


# ── Robot reset ───────────────────────────────────────────────────────────────
def _reset_robot(robot: Articulation, device: str):
    root = robot.data.default_root_state.clone()
    root[0, :3] = torch.zeros(3, device=device)
    robot.write_root_pose_to_sim(root[:, :7])
    robot.write_root_velocity_to_sim(root[:, 7:])
    jp = robot.data.default_joint_pos.clone()
    jv = robot.data.default_joint_vel.clone()
    robot.write_joint_state_to_sim(jp, jv)
    robot.reset()


# ── Real robot → Isaac Sim pose sync (digital twin) ──────────────────────────

def _start_ros2_sync() -> None:
    """
    Subscribe to /odom (nav_msgs/Odometry) and /odom_raw (std_msgs/String JSON)
    from the real Yahboom M3Pro.  Updates _real_pose so the main sim loop can
    mirror the real robot position into Isaac Sim.

    Run as a daemon thread.  If rclpy is not installed this is a silent no-op.
    """
    global _real_pose
    try:
        import rclpy
        from rclpy.node import Node
        from nav_msgs.msg import Odometry
        from std_msgs.msg import String as RosStr
    except ImportError:
        print("[Bridge/twin] rclpy not installed — real robot sync disabled")
        return

    try:
        rclpy.init(args=[])
    except Exception as exc:
        print(f"[Bridge/twin] rclpy init failed: {exc}")
        return

    node = rclpy.create_node("fleetsafe_twin_sync")

    def _apply(x: float, y: float, yaw: float) -> None:
        global _real_pose
        with _real_pose_lock:
            _real_pose = {"x": x, "y": y, "yaw": yaw}
        with _state_lock:
            rr = _state["real_robot"]
            rr["live"] = True
            rr["x"]    = round(x, 4)
            rr["y"]    = round(y, 4)
            rr["yaw"]  = round(yaw, 4)
            rr["ts"]   = time.time()
            # Divergence from current Isaac sim pose
            sx = _state["pose"]["x"]
            sy = _state["pose"]["y"]
            rr["divergence_m"] = round(math.hypot(x - sx, y - sy), 4)

    def _odom_cb(msg: "Odometry") -> None:
        pos = msg.pose.pose.position
        q   = msg.pose.pose.orientation
        yaw = math.atan2(
            2.0 * (q.w * q.z + q.x * q.y),
            1.0 - 2.0 * (q.y * q.y + q.z * q.z),
        )
        _apply(pos.x, pos.y, yaw)

    def _odom_str_cb(msg: "RosStr") -> None:
        try:
            import json as _json
            d = _json.loads(msg.data)
            _apply(
                float(d.get("x", 0.0)),
                float(d.get("y", 0.0)),
                float(d.get("heading", 0.0)),
            )
        except Exception:
            pass

    try:
        node.create_subscription(Odometry, "/odom",     _odom_cb,     10)
        node.create_subscription(RosStr,   "/odom_raw", _odom_str_cb, 10)
        print("[Bridge/twin] ROS2 sync node started — /odom + /odom_raw")
        rclpy.spin(node)
    except Exception as exc:
        print(f"[Bridge/twin] ROS2 sync error: {exc}")
    finally:
        node.destroy_node()
        try:
            rclpy.shutdown()
        except Exception:
            pass


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    rdef = _ROBOTS[args_cli.robot]

    if not rdef["urdf"].exists():
        print(f"\n[ERROR] URDF not found: {rdef['urdf']}")
        if args_cli.robot == "m3pro":
            print("  M3Pro URDF not yet created. See:")
            print(f"  {REPO_ROOT}/fleet_safe_vla/robots/yahboom/config/robot_contract_m3pro.yaml")
        simulation_app.close()
        sys.exit(1)

    print(f"\n[Bridge] Robot  : {rdef['label']}")
    print(f"[Bridge] URDF   : {rdef['urdf']}")
    print(f"[Bridge] Port   : ws://0.0.0.0:{args_cli.ws_port}")
    print(f"[Bridge] Headless: {not args_cli.gui}\n")

    # Start WebSocket server in daemon thread
    ws_thread = threading.Thread(
        target=_start_ws_server,
        args=(args_cli.ws_port, args_cli.tele_hz),
        daemon=True,
    )
    ws_thread.start()

    # Start real robot ROS2 pose sync thread (digital twin mode)
    if args_cli.sync_real_robot:
        sync_thread = threading.Thread(target=_start_ros2_sync, daemon=True, name="ros2_twin_sync")
        sync_thread.start()
        print("[Bridge] Digital twin mode — mirroring /odom → Isaac Sim pose")

    # Build scene
    physics_dt = 1.0 / args_cli.physics_hz
    sim_cfg = sim_utils.SimulationCfg(dt=physics_dt, device=args_cli.device)
    sim = SimulationContext(sim_cfg)

    if args_cli.gui:
        sim.set_camera_view(eye=[1.0, -0.8, 0.6], target=[0.0, 0.0, 0.1])

    robot = _design_scene(rdef)
    sim.reset()

    # Resolve wheel joint indices once
    wheel_ids: list[int] = []
    for jname in rdef["wheel_joints"]:
        ids, _ = robot.find_joints(jname)
        wheel_ids.extend(ids)

    # Update shared state to RUNNING
    with _state_lock:
        _state["sim"]["status"] = "RUNNING"
        _state["joints"]["names"] = rdef["wheel_joints"]

    print("[Bridge] Simulation running. Connect FleetSafe dashboard at:")
    print("[Bridge]   http://localhost:8080/yahboom\n")
    print("[Bridge] Isaac Sim GUI debug mode:")
    print("[Bridge]   ./scripts/isaaclab/view_yahboom.sh --robot x3\n")

    sim_dt   = sim.get_physics_dt()
    tele_interval = max(1, int(round(args_cli.physics_hz / args_cli.tele_hz)))

    step       = 0
    reset_count = 0
    cmd_vx     = 0.0
    cmd_wz     = 0.0
    vel_target = torch.zeros(1, len(wheel_ids), device=args_cli.device)
    paused     = False

    while simulation_app.is_running():
        # ── Process commands ──────────────────────────────────────────────────
        while not _cmd_queue.empty():
            cmd = _cmd_queue.get_nowait()
            ctype = cmd.get("type", "")

            if ctype == "cmd_vel":
                raw_vx = float(cmd.get("vx", 0.0))
                raw_wz = float(cmd.get("wz", 0.0))
                cmd_vx = max(-rdef["max_vx_ms"], min(rdef["max_vx_ms"], raw_vx))
                cmd_wz = max(-rdef["max_wz_rs"], min(rdef["max_wz_rs"], raw_wz))

            elif ctype == "stop":
                cmd_vx = 0.0
                cmd_wz = 0.0

            elif ctype == "pause":
                paused = True
                with _state_lock:
                    _state["sim"]["status"] = "PAUSED"

            elif ctype == "resume":
                paused = False
                with _state_lock:
                    _state["sim"]["status"] = "RUNNING"

            elif ctype == "reset":
                _reset_robot(robot, args_cli.device)
                cmd_vx = 0.0
                cmd_wz = 0.0
                reset_count += 1
                step = 0
                with _state_lock:
                    _state["episode"]["reset_count"] = reset_count

        if paused:
            time.sleep(0.05)
            continue

        # ── Apply wheel velocity targets ──────────────────────────────────────
        if wheel_ids:
            left_rad, right_rad = _cmd_vel_to_wheels(cmd_vx, cmd_wz, rdef)
            # For 2-wheel X3: [left, right]. For 4-wheel M3Pro: all same speed (simplified)
            if len(wheel_ids) == 2:
                vel_target[0, 0] = left_rad
                vel_target[0, 1] = right_rad
            else:
                # Mecanum simplified: same pattern as diff-drive until M3Pro kinematics is implemented
                vel_target[0, :] = torch.tensor(
                    [left_rad, right_rad, left_rad, right_rad], device=args_cli.device
                )
            robot.set_joint_velocity_target(vel_target, joint_ids=wheel_ids)

        # ── Digital twin: apply real robot pose to Isaac Sim ──────────────────
        if args_cli.sync_real_robot:
            with _real_pose_lock:
                rp = _real_pose
            if rp is not None:
                x, y, yaw = rp["x"], rp["y"], rp["yaw"]
                half = yaw / 2.0
                qw, qz = math.cos(half), math.sin(half)
                root = robot.data.default_root_state.clone()
                root[0, 0] = x
                root[0, 1] = y
                root[0, 2] = rdef["wheel_radius_m"]
                # quat order in IsaacLab root_state: w, x, y, z
                root[0, 3] = qw
                root[0, 4] = 0.0
                root[0, 5] = 0.0
                root[0, 6] = qz
                robot.write_root_pose_to_sim(root[:, :7])

        robot.write_data_to_sim()
        sim.step()
        step += 1
        robot.update(sim_dt)

        # ── Update telemetry (at tele_hz rate) ────────────────────────────────
        if step % tele_interval == 0:
            pos  = robot.data.root_pos_w[0]
            quat = robot.data.root_quat_w[0]   # w, x, y, z
            lvel = robot.data.root_lin_vel_w[0]
            avel = robot.data.root_ang_vel_w[0]
            jpos = robot.data.joint_pos[0]
            jvel = robot.data.joint_vel[0]

            qw, qx, qy, qz = float(quat[0]), float(quat[1]), float(quat[2]), float(quat[3])
            roll, pitch, yaw = _quat_to_euler(qw, qx, qy, qz)

            # Simple contact heuristic: z-velocity strongly negative → likely contact/fall
            contact = bool(float(lvel[2]) < -0.5)

            with _state_lock:
                _state["t"]                       = time.time()
                _state["sim"]["step"]             = step
                _state["pose"]["x"]               = round(float(pos[0]), 4)
                _state["pose"]["y"]               = round(float(pos[1]), 4)
                _state["pose"]["z"]               = round(float(pos[2]), 4)
                _state["pose"]["yaw"]             = round(yaw, 4)
                _state["pose"]["pitch"]           = round(pitch, 4)
                _state["pose"]["roll"]            = round(roll, 4)
                _state["velocity"]["vx"]          = round(float(lvel[0]), 4)
                _state["velocity"]["vy"]          = round(float(lvel[1]), 4)
                _state["velocity"]["vz"]          = round(float(lvel[2]), 4)
                _state["velocity"]["wx"]          = round(float(avel[0]), 4)
                _state["velocity"]["wy"]          = round(float(avel[1]), 4)
                _state["velocity"]["wz"]          = round(float(avel[2]), 4)
                _state["joints"]["positions"]     = [round(float(v), 4) for v in jpos]
                _state["joints"]["velocities"]    = [round(float(v), 4) for v in jvel]
                _state["cmd_vel"]["vx"]           = round(cmd_vx, 4)
                _state["cmd_vel"]["wz"]           = round(cmd_wz, 4)
                _state["episode"]["step"]         = step
                _state["episode"]["contact_detected"] = contact

                # Safety: clamp check
                speed = math.hypot(float(lvel[0]), float(lvel[1]))
                over  = speed > rdef["max_vx_ms"] * 1.2
                _state["safety"]["is_safe"]  = not over and not contact
                _state["safety"]["state"]    = "NOMINAL" if not over else "WARNING"


if __name__ == "__main__":
    main()
    simulation_app.close()
