# Yahboom Isaac Sim → FleetSafe Frontend Telemetry Bridge

## Goal

Stream live telemetry from the Yahboom X3 Isaac Sim environment into the
existing FleetSafe web frontend (`web/robot_web_viewer/app.py`) and the ROS2
workspace, giving operators real-time visibility into simulation state.

---

## Data Channels

| Channel | Isaac Sim source | Update rate | Frontend consumer |
|---------|-----------------|-------------|-------------------|
| **Robot pose** | `robot.data.root_pos_w`, `root_quat_w` | 50 Hz | 3D scene transform |
| **Joint states** | `robot.data.joint_pos`, `joint_vel` | 50 Hz | Wheel spin animation |
| **cmd_vel** | Policy output or keyboard input | 10 Hz | Velocity overlay HUD |
| **Safety status** | Fleet safety layer (`fleet_safety/`) | 10 Hz | Status chip (NOMINAL / WARN / HALT) |
| **Episode metrics** | Step count, distance, collisions | 1 Hz | Episode stats panel |
| **Camera stream** | Isaac Sim render buffer (224×224) | 10 Hz | Camera feed widget |

---

## Architecture Options

### Option A — WebSocket / REST bridge (recommended for sim-only)

```
Isaac Sim process
  └─ TelemetryPublisher thread (asyncio + websockets)
        ├─ ws://localhost:8765/pose         50 Hz JSON
        ├─ ws://localhost:8765/joint_states 50 Hz JSON
        ├─ ws://localhost:8765/cmd_vel      10 Hz JSON
        ├─ ws://localhost:8765/safety       10 Hz JSON
        ├─ ws://localhost:8765/metrics       1 Hz JSON
        └─ ws://localhost:8765/camera       10 Hz base64 JPEG

FleetSafe FastAPI app (web/robot_web_viewer/app.py)
  └─ SimBridgeClient (asyncio consumer, port 8765)
        ├─ Updates shared _state dicts (already used by WS endpoints)
        └─ Forwards to browser via existing /ws/joint_states, /ws/camera etc.

Browser (Three.js URDF viewer)
  └─ Consumes existing WebSocket endpoints — no frontend changes needed
```

**Implementation files:**
- `fleet_safe_vla/envs/isaaclab/yahboom/telemetry_publisher.py`
  - Class `TelemetryPublisher` — spawned as a daemon thread inside the Isaac
    Sim step loop; sends JSON frames over websockets.
- `web/robot_web_viewer/sim_bridge_client.py`
  - Class `SimBridgeClient` — connects to `TelemetryPublisher`, merges data
    into the existing `_joint_state_cache` and `_safety_state_cache` dicts.
- `web/robot_web_viewer/app.py` (minor edit)
  - On startup, attempt to connect `SimBridgeClient`; fall back to dummy data
    if unavailable (existing behavior preserved).

**Pros:** No ROS2 required; works from `conda activate isaac` alone.  
**Cons:** Extra socket hop; camera frames need JPEG encoding each step.

---

### Option B — ROS2 bridge (recommended for hardware-in-the-loop)

```
Isaac Sim process
  └─ ROS2TelemetryNode (rclpy node, spun in a thread)
        ├─ /sim/yahboom/joint_states   sensor_msgs/JointState   50 Hz
        ├─ /sim/yahboom/odom           nav_msgs/Odometry        50 Hz
        ├─ /sim/yahboom/cmd_vel        geometry_msgs/Twist      echo only
        ├─ /sim/yahboom/safety_status  fleet_safe_msgs/Safety   10 Hz
        └─ /sim/yahboom/camera/image   sensor_msgs/Image        10 Hz

FleetSafe web viewer (existing --ros2 flag)
  └─ Subscribes to /sim/yahboom/joint_states (replaces /joint_states)
        └─ Browser sees live sim data via existing WebSocket endpoint
```

**Implementation files:**
- `fleet_safe_vla/envs/isaaclab/yahboom/ros2_telemetry_node.py`
  - Class `Ros2TelemetryNode(rclpy.Node)` — publishes all topics above.
  - Spawned inside the Isaac Sim step loop via `threading.Thread`.
- `scripts/isaaclab/view_yahboom.sh` (extend)
  - Add `source /opt/ros/humble/setup.bash` before launch when `--ros2` flag
    is passed.
- `web/robot_web_viewer/app.py` (minor edit)
  - Change subscription topic from `/joint_states` to `/sim/yahboom/joint_states`
    when `--sim` flag is set.

**Pros:** Reuses existing ROS2 workspace; real robot ↔ sim switching via topic
remapping; camera available as standard `sensor_msgs/Image`.  
**Cons:** Requires ROS2 Humble to be sourced in the same shell as Isaac Sim;
can complicate the conda environment.

---

## Recommended Rollout Order

1. **Phase 1 — WebSocket bridge** (`Option A`)
   - Implement `TelemetryPublisher` inside `view_yahboom.py` as an optional
     thread, gated by `--telemetry` flag.
   - Extend `web/robot_web_viewer/app.py` with `SimBridgeClient`.
   - Verify pose + joint state stream in browser with the Yahboom URDF viewer.

2. **Phase 2 — Camera feed**
   - Add an Isaac Sim camera sensor (`CameraCfg`) to `design_scene()`.
   - Encode render buffer as JPEG in the `TelemetryPublisher` camera channel.
   - Add `<img>` widget to the frontend static HTML.

3. **Phase 3 — ROS2 bridge** (`Option B`)
   - Implement `Ros2TelemetryNode` alongside `TelemetryPublisher`.
   - Add `--ros2` flag to `view_yahboom.sh` that sources Humble and enables
     the ROS2 node instead of the WebSocket publisher.

4. **Phase 4 — cmd_vel control**
   - Add keyboard or gamepad `cmd_vel` input to `view_yahboom.py`.
   - Differential-drive kinematics → wheel velocity targets sent to Isaac Sim
     articulation (same math as `YahboomMuJoCoBase.step()`).

---

## Wire Formats

### Joint state (WebSocket JSON)
```json
{
  "t": 1234567890.123,
  "names": ["left_wheel_joint", "right_wheel_joint"],
  "positions": [0.0, 0.0],
  "velocities": [0.0, 0.0],
  "efforts": [0.0, 0.0]
}
```

### Robot pose (WebSocket JSON)
```json
{
  "t": 1234567890.123,
  "pos": [0.0, 0.0, 0.048],
  "quat_wxyz": [1.0, 0.0, 0.0, 0.0],
  "lin_vel": [0.0, 0.0, 0.0],
  "ang_vel": [0.0, 0.0, 0.0]
}
```

### Safety status (WebSocket JSON)
```json
{
  "t": 1234567890.123,
  "state": "NOMINAL",
  "is_safe": true,
  "violations": [],
  "episode_step": 0
}
```

### Episode metrics (WebSocket JSON)
```json
{
  "t": 1234567890.123,
  "step": 1500,
  "distance_m": 3.21,
  "collisions": 0,
  "resets": 0,
  "avg_speed_ms": 0.14
}
```

---

## Related Files

- `web/robot_web_viewer/app.py` — existing FastAPI WS server
- `fleet_safe_vla/envs/isaaclab/yahboom/base_env.py` — Isaac Lab Yahboom env
- `fleet_safe_vla/fleet_safety/` — safety layer (CBF, risk monitor)
- `ros2_ws/src/fleet_safe_msgs/` — custom ROS2 message definitions
- `scripts/isaaclab/view_yahboom.py` — GUI viewer (Phase 1 entry point)
