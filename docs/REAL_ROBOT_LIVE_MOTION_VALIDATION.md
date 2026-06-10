# FleetSafe-VLN: Live Motion Validation Guide

Safety protocol, startup sequence, and evidence verification for
transitioning from dry-run to live `/cmd_vel` actuation on the
Yahboom ROSMASTER-M3Pro.

---

## Why live motion must not start unless Jetson topics are publishing

The FleetSafe VLN controller on the RTX desktop is a **consumer** of Jetson
sensor topics.  If those topics are absent or stale, the controller has no
real safety signal and the CBF-QP filter operates on default/infinite
clearance values — meaning it cannot refuse an unsafe command.

The three topics that gate live motion are:

| Topic | Required Hz | Why |
|---|---|---|
| `/scan0` | ≥ 1 Hz | front LiDAR — primary CBF obstacle distance |
| `/scan1` | ≥ 1 Hz | rear LiDAR — combined effective clearance |
| `/odom_raw` | ≥ 1 Hz | odometry — confirms actuator response |

If any of these are absent, `make vln-live-preflight` will fail hard and
prevent `make vln-live-motion-proof` from running.

---

## Step 1 — Start the Jetson robot stack

The Jetson must be running two subsystems:

**a) micro_ros_agent** — bridges the STM32 MCU to ROS 2.
Provides `/odom_raw`, `/cmd_vel` subscriber on the MCU side, `/imu/data_raw`.

**b) yahboomcar bringup** — ROS 2 launch for the M3Pro.
Provides `/YB_Node`, `/scan0`, `/scan1`, `/camera/color/image_raw`.

### First time: install the tools

```bash
# From the RTX desktop (robot must be reachable):
make robot-install
```

This copies `start_robot_stack.sh`, `status_robot_stack.sh`, and
`stop_robot_motion.sh` into `~/fleetsafe_robot_tools/` on the Jetson.

### Every session: start the stack

```bash
# SSH into the Jetson and run:
make robot-start
# which executes:
#   ssh jetson@172.20.10.14 "bash ~/fleetsafe_robot_tools/start_robot_stack.sh"
```

Or manually:
```bash
ssh jetson@172.20.10.14
~/fleetsafe_robot_tools/start_robot_stack.sh
```

Expected output after ~10 seconds:
```
  [OK]  /YB_Node
  [OK]  /cmd_vel
  [OK]  /odom_raw
  [OK]  /scan0
  [OK]  /scan1
  [OK]  /camera/color/image_raw
```

If topics are missing, check the bringup logs:
```bash
make robot-status
# shows logs from micro_ros_agent and yahboomcar_bringup
```

---

## Step 2 — Start the VLN controller (DRY-RUN first)

On the RTX desktop, in a dedicated terminal:

```bash
# DRY-RUN (safe default — zero velocity published):
make vln-desktop

# Or with a custom safety radius:
make vln-desktop-radius RADIUS=0.20
```

The controller subscribes to `/fleetsafe/instruction_text`,
`/fleetsafe/instruction_voice`, and all Jetson sensor topics.

---

## Step 3 — Run the live motion preflight

```bash
make vln-live-preflight
```

This runs 9 checks (see `scripts/live/vln_live_preflight.sh`):

1. `ROS_DOMAIN_ID=30`
2. `/YB_Node` visible
3. `/scan0` Hz ≥ 1
4. `/scan1` Hz ≥ 1
5. `/odom_raw` Hz ≥ 1
6. `/camera/color/image_raw` present
7. LiDAR effective clearance ≥ safety_radius (via `lidar_sanitizer.py`)
8. `/fleetsafe/instruction_text` has ≥ 1 subscriber
9. Dry-run instruction → `camera_seen=True` in latest certificate

**Any failure exits non-zero.** Do not proceed to live motion until all 9 pass.

---

## Step 4 — Clear e-stop (if needed)

If the controller previously fired an emergency stop:

```bash
make vln-clear-estop
# publishes /fleetsafe/estop_clear
# Controller clears latch ONLY if current LiDAR clearance >= safety_radius
```

The controller logs:
```
[VLN] E-stop CLEARED. clearance=0.84 m  safety_radius=0.30 m.
# — or if still too close:
[VLN] E-stop clear REFUSED: clearance 0.10 m < safety_radius 0.30 m.
```

---

## Step 5 — Enable live motion

Restart the controller with motion enabled:

```bash
make vln-desktop-live
# which runs:
#   CONFIRM_ENABLE_MOTION=YES bash scripts/live/run_vln_desktop.sh --enable-motion
```

Or run the full end-to-end proof (kills stale controller, starts live, sends
test instruction, asserts certificate):

```bash
make vln-live-motion-proof
# Requires: CONFIRM_ENABLE_MOTION=YES environment variable
```

---

## Verifying camera, LiDAR, odometry, cmd_vel, and certificates

### LiDAR effective clearance

```bash
make vln-lidar-inspect
# Shows raw vs sanitized clearance from both scanners
# Uses 5th-percentile of valid beams — consistent with CBF filter
```

### Camera reaching the controller

```bash
make vln-camera-check
# Checks topic Hz with sensor_data QoS
# Reads camera_seen from latest certificate
# NOTE: camera_seen in the certificate is the authoritative proof
#       that frames reached the VLN pipeline
```

### Full stack health

```bash
make vln-check-stack SAFETY_RADIUS=0.20
# All-in-one: ROS domain, Jetson nodes, topics, LiDAR clearance
# Camera Hz is advisory only — see certificate for authoritative camera status
```

### Latest trace and certificate

```bash
make vln-evidence-latest
# Prints path, size, and last 3 rows of trace and certificate files

# Or view directly:
tail -n 1 results/certificates/*/vln_certificates_m3pro.jsonl | python3 -m json.tool
```

A healthy certificate row:
```json
{
  "timestamp": 1748300000.0,
  "instruction_id": "abc123",
  "source": "text",
  "safe": true,
  "qp_status": "skipped",
  "h_min": 0.34,
  "min_dist_m": 0.84,
  "safety_radius_m": 0.30,
  "camera_seen": true,
  "camera_frame_id": "camera_link",
  "camera_last_age_ms": 45.2,
  "scan_audit": {"effective_clearance_m": 0.84, ...},
  "estop_latched": false,
  "decision": "allowed"
}
```

---

## How this workflow transfers to Isaac Sim and the digital twin

The VLN controller (`run_vln_m3pro.py`) is simulator-agnostic:
it subscribes to standard ROS 2 topics and publishes to the same topics
regardless of whether those topics come from the Jetson, Isaac Sim, or Gazebo.

The trace JSONL and certificate JSONL files are written identically in all
three environments.  This means:

| Environment | What changes | What is identical |
|---|---|---|
| Real robot (Jetson) | Physical sensors, MCU latency | Certificate schema, CBF logic, evidence files |
| Isaac Sim | Simulated physics, RTX renderer | Same topics, same controller, same certificates |
| Gazebo | Simplified physics | Same topics, same controller, same certificates |

To run the controller against Isaac Sim:
1. Start Isaac Sim with the M3Pro asset publishing to domain 30
2. Run `make vln-desktop` (same command, no changes)
3. Certificates from Isaac Sim are byte-for-byte identical in schema to real-robot certs

This property — identical evidence from simulation and hardware — is what
makes FleetSafe certificates usable as formal verification artefacts across
deployment environments.

---

## Quick reference

```bash
# First time:
make robot-install                  # copy tools to Jetson

# Every session:
make robot-start                    # start Jetson robot stack
make vln-desktop                    # start controller DRY-RUN (separate terminal)
make vln-live-preflight             # run all 9 safety checks
make vln-clear-estop                # reset e-stop if latched
make vln-live-motion-proof          # end-to-end live motion test

# Monitoring:
make robot-status                   # Jetson process + topic status
make vln-check-stack                # desktop-side full health
make vln-evidence-latest            # latest trace + cert files
make vln-camera-check               # camera Hz + cert camera_seen
make vln-lidar-inspect              # live LiDAR clearance

# Safety:
make robot-stop-motion              # publish zero /cmd_vel from desktop
```
