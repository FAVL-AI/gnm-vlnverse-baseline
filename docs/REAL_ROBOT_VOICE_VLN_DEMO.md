# FleetSafe-VLN: Real Robot + Voice Demo Guide

Step-by-step instructions for running the full voice-conditioned VLN pipeline
on the Yahboom ROSMASTER-M3Pro and showing it to a professor or reviewer.

---

## Prerequisites

| Item | Check |
|---|---|
| Yahboom M3Pro powered on and on the same network | `ping 172.20.10.14` |
| ROS2 Humble sourced | `ros2 topic list` works |
| `ROS_DOMAIN_ID=30` set | `echo $ROS_DOMAIN_ID` → `30` |
| FleetSafe repo installed | `python3 -c "import fleet_safe_vla"` |
| Orbbec camera streaming | `ros2 topic hz /camera/color/image_raw` |
| LiDAR streaming | `ros2 topic hz /scan0` |

---

## Step 1 — Verify robot topics

```bash
bash scripts/live/check_robot_topics.sh
```

Expected output (green lines):
```
[OK] /camera/color/image_raw     — 29 Hz
[OK] /camera/depth/image_raw     — 29 Hz
[OK] /scan0                      — 20 Hz
[OK] /odom_raw                   — 50 Hz
```

---

## Step 2 — Start the VLN controller (dry-run first)

On the **desktop** (or via SSH on the Jetson):

```bash
source /opt/ros/humble/setup.bash
python3 scripts/real_robot/run_vln_m3pro.py \
    --backbone auto \
    --safety-radius 0.50
```

Or via Makefile:

```bash
make vln-demo-dry TEXT="go to the nurse station and avoid people"
```

Expected banner:
```
══════════════════════════════════════════════════════════════════════
  FleetSafe-VLN  |  M3Pro Real Robot Controller
  Motion   : DRY-RUN (no motion)
  Backbone : auto
  d_safe   : 0.50 m
  Trace    : results/vln_runs/20260526_143000/vln_trace_m3pro.jsonl
  Certs    : results/certificates/20260526_143000/vln_certificates_m3pro.jsonl
══════════════════════════════════════════════════════════════════════

  Listening on:
    /fleetsafe/instruction_text   — typed text instructions
    /fleetsafe/instruction_voice  — voice ASR transcripts
```

---

## Step 3 — Send a text instruction

In a **second terminal**:

```bash
source /opt/ros/humble/setup.bash
make vln-send TEXT="go to the nurse station and avoid people"
```

Or directly:

```bash
ros2 topic pub --once /fleetsafe/instruction_text std_msgs/msg/String \
    "{data: 'go to the nurse station and avoid people'}"
```

Expected controller output:
```
[DRY-RUN] vx=0.100  wz=0.000  backbone=gnm  h_min=0.2304  latency=3.1ms
```

---

## Step 4 — Inspect the VLN trace

```bash
cat results/vln_runs/*/vln_trace_*.jsonl | python3 -m json.tool | head -60
```

Key fields in one trace record:
```json
{
  "raw_instruction": "go to the nurse station and avoid people",
  "parsed_instruction": {
    "action_type": "navigate",
    "label": "station",
    "confidence": 1.0
  },
  "u_nom": [0.1, 0.0],
  "u_safe": [0.1, 0.0],
  "cbf_active": false,
  "qp_status": "skipped",
  "h_min": 0.2304,
  "min_dist_m": 0.98,
  "latency_ms": 3.1
}
```

---

## Step 5 — Test the safety constraint extraction

```bash
make vln-send TEXT="move forward and avoid obstacles"
```

Observe in the controller log:
```
action=navigate  constraints=['obstacles']  confidence=1.00
```

---

## Step 6 — Test the stop override

```bash
make vln-send TEXT="stop"
```

Controller log must show:
```
[STOP] Instruction: 'stop' → immediate zero velocity.
```

No motion command is published under any circumstances.

---

## Step 7 — Verify safety certificates

```bash
make formal-check
```

Or manually:
```bash
python3 scripts/eval/check_certificates.py \
    results/certificates/*/vln_certificates_m3pro.jsonl
```

Every row with `h_min >= 0` is formally certified safe.

---

## Step 8 — Enable real motion (when ready)

Only when the area around the robot is clear:

```bash
python3 scripts/real_robot/run_vln_m3pro.py \
    --enable-motion \
    --backbone auto \
    --safety-radius 0.50
```

Then send instructions via `make vln-send TEXT="..."`.

The robot will move at maximum 0.12 m/s forward and 0.35 rad/s yaw.
The CBF-QP filter guarantees obstacle distance ≥ 0.50 m at every step.

---

## Step 9 — Voice instructions

If the Yahboom A-MIC is publishing ASR transcripts:

```bash
bash scripts/robot/start_voice_listener.sh
```

The listener bridges `/fleetsafe/instruction_voice` to the VLN controller.
No separate configuration is needed — the controller already subscribes to
both `/fleetsafe/instruction_text` and `/fleetsafe/instruction_voice`.

To check which voice topics the robot exposes:

```bash
bash scripts/robot/check_voice_module.sh
```

To simulate a voice instruction (testing only):

```bash
ros2 topic pub --once /fleetsafe/instruction_voice std_msgs/msg/String \
    "{data: 'follow the corridor and avoid people'}"
```

---

## Step 10 — Open the dashboard

```bash
make dev          # starts FastAPI backend + Next.js frontend
```

Open: `http://localhost:3000/dashboard/vln`

The VLN panel shows:
- Current instruction and parsed action
- u_nom vs u_safe comparison
- CBF status (active / skipped / estop)
- Live safety certificate status
- Recent VLN decision timeline

---

## Step 11 — Record a bag for post-hoc evaluation

```bash
make vln-record
```

This records all FleetSafe topics plus camera, scan, and odometry to a
ROS2 bag file in `results/bags/`. The bag can be replayed for offline
certificate verification or dataset generation.

---

## Professor demonstration sequence (10 minutes)

| Time | Action | Expected result |
|---|---|---|
| 0:00 | `check_robot_topics.sh` | All topics green |
| 0:30 | Start controller in dry-run | Banner printed, no motion |
| 1:00 | `make vln-send TEXT="go to the nurse station"` | navigate, label=station |
| 1:30 | `make vln-send TEXT="stop"` | Immediate zero velocity |
| 2:00 | `make vln-send TEXT="avoid obstacles and move forward"` | navigate + constraints=['obstacles'] |
| 3:00 | `cat results/vln_runs/*/vln_trace_*.jsonl \| python3 -m json.tool \| head -40` | Trace visible |
| 4:00 | `make formal-check` | All h_min ≥ 0, certified safe |
| 5:00 | Enable motion, send `"go to the nurse station"` | Robot moves slowly |
| 7:00 | Walk toward robot (decrease d) | CBF intervenes, robot slows |
| 8:30 | `make vln-send TEXT="halt"` | Robot stops immediately |
| 9:00 | Open dashboard `http://localhost:3000/dashboard/vln` | Live trace + certs |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `rclpy not found` | ROS2 not sourced | `source /opt/ros/humble/setup.bash` |
| No `/scan0` messages | LiDAR not running | `ros2 launch ... lidar_bringup.launch.py` |
| `LiDAR stale` emergency stop | Scan not updating | Check LiDAR USB/power |
| `confidence < 0.30` | Unknown instruction | Use supported keywords (go, turn, avoid, stop) |
| CBF always active | Too close to wall | Back robot away from wall; increase `--safety-radius` |
| Dashboard 404 | Backend not running | `make dev` or `make backend` |

---

## Safety checklist before enabling motion

- [ ] Area around robot is clear (≥ 1.5 m in all directions)
- [ ] E-stop button (hardware) within reach
- [ ] `--safety-radius 0.50` or larger
- [ ] LiDAR topics streaming at ≥ 10 Hz (`ros2 topic hz /scan0`)
- [ ] Camera topics streaming (`ros2 topic hz /camera/color/image_raw`)
- [ ] Dry-run test passes (at least 3 instructions processed correctly)
