# FleetSafe-VLN: Real Robot Operation Guide

Architecture, daily workflow, and safety reference for running the
FleetSafe VLN controller on the Yahboom ROSMASTER-M3Pro.

---

## Architecture

```
RTX Desktop (172.20.10.2)              Jetson Orin NX (172.20.10.14)
──────────────────────────────         ──────────────────────────────
FleetSafe VLN controller               micro-ROS agent
  InstructionGrounder                  Yahboom base driver (/cmd_vel)
  BackboneRouter (GNM/ViNT/NoMaD)      Orbbec DaBai DCW2 camera
  CBF-QP safety filter                 Dual Tmini-plus LiDAR
  SafetyCertificate logger             Odometry (/odom_raw)
  VLNTrace JSONL logger
  FastAPI + Next.js dashboard

ROS2 DDS (ROS_DOMAIN_ID=30, LAN)
  ←── /scan0 /scan1 /odom_raw /camera/color/image_raw
  ──→ /cmd_vel (DRY-RUN: zero; LIVE: u_safe)
  ──→ /fleetsafe/cmd_vel_nominal
  ──→ /fleetsafe/vln/parsed_instruction
  ──→ /fleetsafe/vln/subgoal
  ──→ /fleetsafe/certificate
```

**The VLN controller runs on the RTX desktop**, not on the Jetson.
The Jetson is solely responsible for sensor acquisition and low-level
actuation.  All language grounding, backbone inference, and safety
filtering happen on the desktop where compute is available.

---

## Topic reference

| Topic | Direction | Node |
|---|---|---|
| `/scan0` | Jetson → Desktop | front LiDAR |
| `/scan1` | Jetson → Desktop | rear LiDAR |
| `/odom_raw` | Jetson → Desktop | wheel odometry |
| `/camera/color/image_raw` | Jetson → Desktop | RGB frame |
| `/imu/data_raw` | Jetson → Desktop | IMU |
| `/cmd_vel` | Desktop → Jetson | u_safe (DRY-RUN: zero) |
| `/fleetsafe/instruction_text` | Desktop subscriber | typed instruction in |
| `/fleetsafe/instruction_voice` | Desktop subscriber | ASR transcript in |
| `/fleetsafe/cmd_vel_nominal` | Desktop publisher | u_nom before CBF |
| `/fleetsafe/vln/parsed_instruction` | Desktop publisher | GroundedGoal JSON |
| `/fleetsafe/vln/subgoal` | Desktop publisher | backbone subgoal |
| `/fleetsafe/certificate` | Desktop publisher | SafetyCertificate JSON |

---

## Daily workflow

```bash
# 1. Pull latest changes
cd ~/robotics/FleetSafe-VisualNav-Benchmark
git pull --ff-only

# 2. Start the VLN controller (Terminal 1 — DRY-RUN)
make vln-desktop
# or with a custom safety radius for nearby objects:
# make vln-desktop-radius RADIUS=0.20

# 3. Verify the stack (Terminal 2)
make vln-check-stack

# 4. Watch parsed output (Terminal 2 or 3)
make vln-watch-parsed

# 5. Send an instruction (Terminal 3)
make vln-send TEXT="move forward slowly and keep at least half a meter from obstacles"

# 6. Watch the certificate (Terminal 4)
make vln-watch-cert
```

---

## Live motion (when ready)

`run_vln_desktop.sh --enable-motion` now runs a sensor preflight
automatically before starting the controller.  If any sensor check
fails the launch is aborted with a clear fix message — no stale-LiDAR
e-stop cascade.

```bash
# Recommended path — preflight runs automatically:
CONFIRM_ENABLE_MOTION=YES make vln-desktop-live

# Run the sensor preflight separately (diagnose before launch):
make vln-live-preflight

# Run directly with a custom safety radius:
SAFETY_RADIUS=0.30 bash scripts/live/preflight_live_motion.sh
```

**Never enable motion** when `make vln-live-preflight` reports any
sensor check as `[FAIL]`.

---

## Live motion gate

### Why /YB_Node and active scan/odom publishers are mandatory

The CBF-QP safety filter runs on every scan callback.  If the Jetson
robot stack is not publishing `/scan0` and `/scan1`, **the controller
has no obstacle data**.  Without obstacle data:

- The `stale_lidar` timer trips (default after 1.0 s with no scan)
- The e-stop latches on the very first instruction
- Every subsequent certificate reads `decision: stale_lidar`
- The robot never moves, even if the instruction is valid

`/YB_Node` must be present because it is the entry point for the
Yahboom base driver: if `/YB_Node` is absent, the base driver is not
running and `/cmd_vel` commands will not reach the motor controller
even if the VLN controller publishes them.

`/odom_raw` must be publishing because the odometry subscriber feeds
state estimation for the backbone subgoal tracker.  Without odometry
the subgoal position cannot be updated during motion.

### `stale_lidar` in the certificate is a correct safety refusal

```json
{ "decision": "stale_lidar", "stale_lidar": true, "estop_latched": true }
```

This is **not a bug or error** — it is the safety system correctly
refusing to move when it has no obstacle data.  You will see this
pattern whenever:

- The Jetson robot stack is not running
- The `/scan0` or `/scan1` publisher crashed or was never started
- The DDS network (ROS_DOMAIN_ID) is wrong between desktop and Jetson
- The LiDAR USB cable is disconnected

**Resolution**: run `make vln-live-preflight` to identify which sensor
is missing, fix it, then relaunch with `make vln-desktop-live`.

### What the preflight gate checks

`scripts/live/preflight_live_motion.sh` (called automatically by
`run_vln_desktop.sh --enable-motion`) verifies:

| Check | Hard fail? | Fix |
|---|---|---|
| ROS_DOMAIN_ID is set | Yes | `export ROS_DOMAIN_ID=30` |
| `/YB_Node` visible | Yes | `make robot-start-yahboom` |
| `/scan0` publisher ≥ 1, data within 5 s | Yes | check LiDAR USB on Jetson |
| `/scan1` publisher ≥ 1, data within 5 s | Yes | check LiDAR USB on Jetson |
| `/odom_raw` publisher ≥ 1, data within 5 s | Yes | check micro_ros_agent |
| `/cmd_vel` subscriber ≥ 1 (base ready) | Yes | start yahboomcar base driver |
| LiDAR effective clearance ≥ SAFETY_RADIUS | Yes | move robot to open space |
| `/camera/color/image_raw` publisher | **No (advisory)** | camera affects cert only |

Camera is advisory: motion is allowed with no camera, but every
certificate will record `camera_seen: false`.

### Correct startup sequence

```bash
# 1. Start the Jetson robot stack
make robot-start-yahboom          # micro_ros_agent + yahboomcar bringup + Orbbec camera

# 2. Verify Jetson stack health (optional diagnostic)
make robot-status-yahboom         # Hz, publisher counts, tmux session names

# 3. Sensor preflight on the desktop (hard-fail gate)
make vln-live-preflight           # exits 1 if /YB_Node / scan / odom / clearance missing

# 4. Dry-run test (VLN controller without motion)
make vln-desktop                  # starts controller, DRY-RUN
make vln-send TEXT="go forward slowly"
make vln-watch-cert               # confirm camera_seen=true, estop_latched=false

# 5. Live motion — preflight runs automatically before launch
CONFIRM_ENABLE_MOTION=YES make vln-desktop-live
```

---

## CBF infeasibility — this is correct behaviour, not a bug

The CBF-QP safety filter monitors obstacle clearance at every step.
When clearance falls below the safety radius, the filter correctly
refuses the nominal command and issues an emergency stop.

**Example observed during development:**

```
/scan1 min_range ≈ 0.28 m
safety-radius    = 0.30 m   (or 0.50 m)
result: CBF infeasible → e-stop latched
```

This is **expected and correct**.  The system is refusing unsafe
motion rather than blindly obeying a language command.

### What to do

| Situation | Action |
|---|---|
| Dry-run demo, robot close to wall | Use `--safety-radius 0.20` |
| Real motion, robot close to wall | Move robot away first |
| Real motion, corridor clear | Use `--safety-radius 0.30` |
| Paper/evaluation run | Use `--safety-radius 0.50` |

### Why `estop_latched` is expected and how to clear it safely

The e-stop is a **permanent safety latch**: once tripped it blocks every
subsequent instruction until explicitly cleared.  This is intentional —
the robot should never resume motion after a collision-proximity event
without human confirmation that the environment is now safe.

#### Clearing via ROS2 topic (preferred)

The controller subscribes to `/fleetsafe/estop_clear`.  It will **only**
reset the latch if the current LiDAR effective clearance is at or above
the configured safety radius:

```bash
# From the RTX desktop (ROS2 sourced, ROS_DOMAIN_ID=30):
make vln-clear-estop

# Or directly:
ros2 topic pub --once /fleetsafe/estop_clear std_msgs/msg/String "{data: 'clear'}"
```

The controller logs one of two outcomes:

```
[VLN] E-stop CLEARED. clearance=0.84 m  safety_radius=0.30 m.
# — or —
[VLN] E-stop clear REFUSED: clearance 0.10 m < safety_radius 0.30 m.
      Move the robot away from the obstacle first.
```

If the clear is refused, move the robot to open space and try again.

#### Clearing by restarting the controller

If the controller process is restarted the latch is reset automatically:

```bash
bash scripts/live/run_vln_desktop.sh --restart
# or: Ctrl+C the existing session and rerun make vln-desktop
```

#### Verify clearance before resuming

After clearing, always confirm the robot is in open space:

```bash
make vln-lidar-inspect          # shows effective clearance vs safety radius
make vln-check-stack            # full stack health including LiDAR
```

Then send a test voice or text instruction and check the certificate:

```bash
make vln-demo-voice-proof       # sends voice cmd, asserts source=voice + camera_seen + safe
# or manually:
make vln-send TEXT="go forward slowly"
make vln-evidence-latest        # tail the latest cert and trace
```

---

## LiDAR sanitization — why raw min-range can read 0.05 m

### The problem: sensor dead-zone artifacts

Raw LiDAR minimum range is **not reliable** for safety decisions.
Many sensors (including the Tmini-Plus on the Yahboom M3Pro) set
`range_min = 0.05 m` and return exactly that value — or values within
a few millimetres — for invalid returns, body self-reflections, and
dead-zone beams.  A single such beam would drive the raw minimum to
0.05 m and trigger a CBF e-stop even when the corridor is completely
clear.

```
/scan0  raw_min=0.05 m  ← sensor artifact, NOT a real obstacle
/scan1  raw_min=0.05 m  ← same
```

Blindly trusting raw minimum would veto all robot motion indefinitely.

### The solution: LidarSanitizer (fleet_safe_vla/safety/lidar_sanitizer.py)

The sanitizer runs on every scan message inside `run_vln_m3pro.py`
**before** the CBF filter sees the clearance value.  It applies four
filtering rules in order:

| Rule | Discards |
|---|---|
| Non-finite | `inf`, `nan` |
| Dead-zone | `r ≤ range_min + epsilon`  (default epsilon = 0.02 m) |
| Out-of-range | `r > range_max` |
| Robust statistic | uses 5th-percentile of remaining beams |

**Effective clearance** = 5th-percentile of the valid beam population.
This means one or two noisy close readings do not veto motion; a real
cluster of close obstacles does.

### Safety is never weakened

- The raw minimum is **always recorded** in the audit certificate for
  full traceability.
- The `filtering_applied` flag is set whenever any beams are discarded.
- If **no beams** pass the filter, `effective_clearance_m = 0.0` and
  the CBF fires — this is the safest possible response.
- If the filtered effective clearance is still below `safety_radius`,
  the CBF fires exactly as before.

### Reading the sanitized clearance report

```bash
make vln-lidar-inspect          # one-shot live reading
make vln-check-stack            # full stack health check (includes this)
```

Example output:
```
┌──────────────────────────────────────────────────────────────────────┐
│  FleetSafe-VLN  LiDAR Sanitization Report                            │
├──────────────────────────────────────────────────────────────────────┤
│  Topic    raw_min  valid_min    p05  invalid  effective  status       │
│  ────────────────────────────────────────────────────────────        │
│  /scan0   0.05 m    0.84 m   0.82 m      12    0.82 m   OK           │
│  /scan1   0.05 m    0.76 m   0.73 m      18    0.73 m   OK           │
├──────────────────────────────────────────────────────────────────────┤
│  Combined effective clearance: 0.73 m  (safety radius: 0.30 m)       │
│  CBF decision: ALLOW motion                                           │
└──────────────────────────────────────────────────────────────────────┘
```

Column definitions:

| Column | Meaning |
|---|---|
| `raw_min` | Smallest finite value in the raw ranges array |
| `valid_min` | Smallest beam after dead-zone filtering |
| `p05` | 5th-percentile of valid beams (used for CBF) |
| `invalid` | Number of beams that were discarded |
| `effective` | Value passed to the CBF filter |
| `status` | `OK` / `WARN (close)` / `E-STOP (below radius)` |

### Certificate audit fields

Every safety certificate written to `/fleetsafe/certificate` now
includes a `scan_audit` sub-object:

```json
"scan_audit": {
  "scan0_raw_min_m":       0.05,
  "scan1_raw_min_m":       0.05,
  "scan0_valid_min_m":     0.84,
  "scan1_valid_min_m":     0.76,
  "scan0_invalid_ct":      12,
  "scan1_invalid_ct":      18,
  "effective_clearance_m": 0.73,
  "filtering_applied":     true
}
```

---

## Safety radius guidance

| Radius | Use case |
|---|---|
| 0.50 m | Paper/evaluation runs, open corridors |
| 0.30 m | Normal operation (default) |
| 0.20 m | Dry-run demo only — not for real motion |
| < 0.20 m | Never use on real robot |

The CBF guarantee is: the robot maintains distance ≥ safety_radius
from all observed LiDAR returns at every timestep, **as long as the
QP is feasible**.  If the robot starts inside the safety radius, the
QP is infeasible and the e-stop fires.

---

## Script reference

| Script | Purpose |
|---|---|
| `scripts/live/run_vln_desktop.sh` | Launch VLN controller on RTX desktop |
| `scripts/live/send_vln_instruction.sh` | Publish one text instruction |
| `scripts/live/watch_vln_outputs.sh` | Echo parsed/nominal/certificate topics |
| `scripts/live/check_vln_stack.sh` | Verify Jetson topics + VLN subscriptions |
| `scripts/robot/sync_repo_to_jetson.sh` | rsync repo to Jetson (runtime copy) |

| Make target | Equivalent command |
|---|---|
| `make vln-desktop` | `run_vln_desktop.sh` (DRY-RUN, radius=0.30) |
| `make vln-desktop-radius RADIUS=0.20` | DRY-RUN with custom radius |
| `make vln-desktop-live` | LIVE MOTION (requires CONFIRM_ENABLE_MOTION=YES) |
| `make vln-send TEXT="..."` | `send_vln_instruction.sh "..."` |
| `make vln-watch-parsed` | `watch_vln_outputs.sh parsed` |
| `make vln-watch-nominal` | `watch_vln_outputs.sh nominal` |
| `make vln-watch-cert` | `watch_vln_outputs.sh certificate` |
| `make vln-check-stack` | `check_vln_stack.sh` |
| `make robot-sync-repo` | `sync_repo_to_jetson.sh` |

---

## Jetson setup

The Jetson does **not** need a git clone.  Use `make robot-sync-repo`
to push a runtime copy of the repository:

```bash
make robot-sync-repo
```

What is synced: all Python packages, scripts, and config.
What is excluded: `.git`, `results/`, `data/real_robot_bags/`,
`node_modules/`, `__pycache__/`, `*.db3`.

After sync, the Jetson has all scripts but the VLN controller is
still meant to run on the desktop.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `check_vln_stack` fails on /YB_Node | Jetson robot stack not running | SSH to Jetson and start base driver |
| `/scan0` / `/scan1` missing | LiDAR not publishing | Check LiDAR USB power on Jetson |
| Subscription count = 0 on `/fleetsafe/instruction_text` | Controller not running | `make vln-desktop` in another terminal |
| `cbf_infeasible` / e-stop on every instruction | Robot inside safety radius | Move robot away or use `--safety-radius 0.20` |
| `stale process` error | Previous controller still running | `run_vln_desktop.sh --restart` |
| No camera feed | Camera unplugged or node crashed | `ros2 topic hz /camera/color/image_raw` |
