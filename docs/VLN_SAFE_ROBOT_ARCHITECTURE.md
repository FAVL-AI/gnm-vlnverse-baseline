# FleetSafe-VLN: Safe Robot Architecture

## System overview

FleetSafe-VLN is a voice/text/image-conditioned embodied navigation system
for the Yahboom ROSMASTER-M3Pro. It adds a language grounding layer on top
of existing GNM/ViNT/NoMaD visual navigation backbones and wraps every
issued command with a formally certified CBF-QP safety filter.

```
┌─────────────────────────────────────────────────────────────┐
│           Instruction Layer (language input)                │
│  Voice (A-MIC) | Text | Image-goal | Typed stdin           │
│  fleet_safe_vla/vln/instruction_intake.py                   │
└──────────────────────────┬──────────────────────────────────┘
                           │ VLNInstruction
┌──────────────────────────▼──────────────────────────────────┐
│           Grounding Layer                                   │
│  fleet_safe_vla/vln/grounding.py                            │
│  Deterministic rule-based parser:                           │
│    action intent + landmarks + safety constraints           │
│  → GroundedGoal (actionable / clarification_needed)        │
└──────────────────────────┬──────────────────────────────────┘
                           │ GroundedGoal
┌──────────────────────────▼──────────────────────────────────┐
│           Backbone Router                                   │
│  fleet_safe_vla/vln/backbone_router.py                      │
│  Choose: GNM | ViNT | NoMaD | Auto                         │
│  Run nominal policy → u_nom                                 │
│  Falls back to rule-based mock if checkpoint unavailable    │
└──────────────────────────┬──────────────────────────────────┘
                           │ u_nom = [vx, wz]
┌──────────────────────────▼──────────────────────────────────┐
│           FleetSafe CBF-QP Safety Filter                    │
│  h_i(x) = d_i² − d_safe²                                   │
│  QP: min ½‖u−u_nom‖²  s.t. ḣ_i + α·h_i ≥ 0              │
│  Emits: u_safe + SafetyCertificate (JSONL)                  │
│  Emergency stop if QP infeasible                            │
└──────────────────────────┬──────────────────────────────────┘
                           │ u_safe = [vx, wz]
┌──────────────────────────▼──────────────────────────────────┐
│           Robot Actuation                                   │
│  /cmd_vel → Yahboom M3Pro (DRY-RUN by default)              │
│  Holonomic drive: vx (forward), wz (yaw)                    │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│           Audit Logs                                        │
│  VLNTrace JSONL (every decision)                            │
│  SafetyCertificate JSONL (every command)                    │
│  ROS2 bag (RGB + depth + scan + odom + /cmd_vel)            │
└─────────────────────────────────────────────────────────────┘
```

---

## Real robot topics

| Topic | Direction | Content |
|---|---|---|
| `/camera/color/image_raw` | In | RGB frame (Orbbec DaBai DCW2) |
| `/camera/depth/image_raw` | In | Depth frame |
| `/odom_raw` | In | Odometry |
| `/imu/data_raw` | In | IMU (9-DoF) |
| `/scan0`, `/scan1` | In | LiDAR (Tmini-plus ×2) |
| `/fleetsafe/instruction_text` | In | Typed language instruction |
| `/fleetsafe/instruction_voice` | In | Voice transcript |
| `/fleetsafe/vln/parsed_instruction` | Out | GroundedGoal JSON |
| `/fleetsafe/vln/subgoal` | Out | Selected subgoal |
| `/fleetsafe/cmd_vel_nominal` | Out | u_nom (before CBF) |
| `/cmd_vel` | Out | u_safe (after CBF, DRY-RUN default) |
| `/fleetsafe/certificate` | Out | Latest certificate JSON |

---

## Safety rules (never bypass)

1. **DRY-RUN by default.** No motion without `--enable-motion` flag.
2. **Unknown commands → zero velocity.** Confidence < threshold → stop.
3. **Stale camera or scan → stop.** Safety filter needs fresh sensor data.
4. **CBF-QP infeasible → emergency stop.** Zero velocity, latch e-stop.
5. **"stop" / "halt" / "freeze" → immediate zero.** Overrides all other logic.
6. **No direct /cmd_vel from language layer.** All motion through CBF filter.

---

## Professor demo sequence

```bash
# 1. Start robot and verify topics
bash scripts/live/check_robot_topics.sh

# 2. Send a dry-run instruction (no motion)
make vln-demo-dry TEXT="go to the nurse station and avoid people"

# 3. Inspect the trace log
cat results/vln_runs/*/vln_trace_*.jsonl | python3 -m json.tool | head -80

# 4. Verify certificates
make formal-check

# 5. Open dashboard
# http://localhost:3000/dashboard/vln

# 6. Record a live bag with instructions
make vln-record

# 7. Generate formal report
make vln-formal-report
```

Output seen by professor:
```
VLN Decision Trace
  instruction   : 'go to the nurse station and avoid people'
  source        : text
  action        : navigate  confidence=0.78
  label         : station
  constraints   : ['people']
  backbone      : gnm
  u_nom         : vx=0.100  wz=0.000
  u_safe  [CBF] : vx=0.100  wz=0.000  (skipped)
  h_min         : 0.9600  safe=YES
  latency       : 4.2 ms
```
