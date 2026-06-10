# PPO / DDS / Sim-to-Sim Deployment Architecture

## Layer map

```
┌─────────────────────────────────────────────────────────────────┐
│  Real robot (Yahboom M3Pro)  ←─── DDS / ROS2 bridge ───→  Isaac Sim  │
│                                                                  │
│  Topics: /scan  /odom  /tf  /camera/color  /cmd_vel             │
│          /fleetsafe/intervention  /fleetsafe/evidence            │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                    VisualNav policy layer
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
         GNM                 ViNT                NoMaD
      (6.4ms)              (32.9ms)             (74.2ms)
          │                    │                    │
          └────────────────────┴────────────────────┘
                               │
                        raw action (vx, wz)
                               │
                    FleetSafe safety layer
                               │
                    CBF-QP safety filter
                    (yahboom_cbf.py)
                               │
                    ┌──────────┴──────────┐
              safe cmd_vel         intervention_evidence.jsonl
                    │                    │
             Robot execution      Scene graph + causal log
                                  Counterfactual rollout
                                  Replay viewer (Isaac/GIF)
```

---

## Component roles

### DDS / ROS2 transport layer

**What it is:** The middleware that moves sensor data and commands between
physical hardware and simulation.

**Current state:** ROS2 (Humble) bridge is the intended transport.  DDS
(Data Distribution Service) is the underlying protocol ROS2 uses.

**Topics used by FleetSafe:**

| Topic | Direction | Type | Purpose |
|---|---|---|---|
| `/scan` | Robot → FleetSafe | `sensor_msgs/LaserScan` | Obstacle proximity |
| `/odom` | Robot → FleetSafe | `nav_msgs/Odometry` | Robot pose |
| `/tf` | Robot → FleetSafe | `tf2_msgs/TFMessage` | Frame transforms |
| `/camera/color/image_raw` | Robot → VNT adapter | `sensor_msgs/Image` | Policy input |
| `/cmd_vel` | FleetSafe → Robot | `geometry_msgs/Twist` | Safe command |
| `/fleetsafe/intervention` | FleetSafe → log | custom | Intervention event |
| `/fleetsafe/evidence` | FleetSafe → log | custom | Full evidence record |

**Current status:** DDS transport is not yet wired end-to-end.  The MuJoCo
benchmark backend generates synthetic sensor data internally.  Real-robot
DDS integration is a future milestone (see `REPRODUCIBILITY_CHECKLIST.md`).

---

### VisualNav policy layer (GNM / ViNT / NoMaD)

**What it is:** Pretrained visual navigation policies from the
VisualNav-Transformer suite.  They take a context of recent image observations
and a goal image, and output (x, y) waypoints or (vx, wz) commands.

**Current state:** All three checkpoints validated and running against MuJoCo:

| Model | Checkpoint | Inference latency (mean / p95) | MuJoCo collision rate |
|---|---|---|---|
| GNM | `model_weights/gnm/gnm.pth` (105MB) | 6.4ms / 6.7ms | 33% (no FS) |
| ViNT | `model_weights/vint/vint.pth` (430MB) | 32.9ms / 39.8ms | 0% (no FS) |
| NoMaD | `model_weights/nomad/nomad.pth` (76MB) | 74.2ms / 96.2ms | 0% (no FS) |

These are the **evaluation baselines**, not fine-tuned policies.  All three
use their original public weights.  Synthetic checkerboard images are used as
visual input in the current MuJoCo benchmark (no real camera images).

**Claim scope:** MuJoCo results are valid simulation benchmarks.  They do not
claim to predict real-world navigation performance (see
`docs/governance/CLAIMS_AND_LIMITATIONS.md`).

---

### FleetSafe safety layer

**What it is:** A CBF-QP (Control Barrier Function — Quadratic Program) safety
filter that wraps any VisualNav policy and enforces minimum obstacle clearance.

**Implementation:**
- `fleet_safe_vla/fleet_safety/yahboom_cbf.py` — CBF-QP solver
- `fleet_safe_vla/integrations/visualnav_transformer/fleetsafe_wrapper.py` — policy wrapper
- Parameters: `d_safe=0.30m`, `estop=0.10m`, `max_linear=0.5m/s`, `max_angular=1.0rad/s`

**What it logs:**
- `intervention_evidence.jsonl` — per-step evidence record (raw action, safe action,
  delta, scene graph, causal explanation, counterfactual)
- `safety_events.jsonl` — intervention and near-miss events
- `audit_trail.json` — run-level provenance

**MuJoCo benchmark result (cluttered_static, seeds 0,1,2):**

```
GNM  baseline:  33% collision  →  GNM  + FleetSafe:  0% collision, 26.9% intervention rate (21.5 interv/ep mean)
ViNT baseline:   0% collision  →  ViNT + FleetSafe:  0% collision,  0.9% intervention rate ( 0.8 interv/ep mean)
NoMaD baseline:  0% collision  →  NoMaD + FleetSafe: 0% collision,  0.0% intervention rate ( 0.0 interv/ep mean)
```

All results: 12 episodes × (cluttered_static, narrow_passage, clutter_forward) × seeds (0,1,2),
MuJoCo backend, `claim_scope: simulation_mujoco`.

FleetSafe's added value is proportional to the base policy's aggressiveness.

---

### PPO policy layer (future — not yet deployed)

**What it is:** A Proximal Policy Optimization agent trained inside Isaac Lab
on the FleetSafe benchmark scenes.

**Where it fits:**

```
Isaac Lab training loop
  ├── Scene: cluttered_static / narrow_passage / dynamic_obstacle
  ├── Reward: progress_to_goal - safety_cost - collision_penalty
  ├── Policy: PPO (actor-critic, MLP or CNN)
  └── Output: policy checkpoint (.pt)
          ↓
Benchmark evaluation (same protocol as GNM/ViNT/NoMaD)
  ├── PPO baseline vs PPO + FleetSafe
  ├── Same SceneSpec obstacles (frozen)
  ├── Same seeds
  └── Same metrics (SPL, collision_rate, intervention_rate)
```

**Current state:** `BACKEND_ISAACLAB` raises `NotImplementedError` in
`visualnav_runner.py`.  PPO training is blocked on:
1. Isaac Lab backend implementation (gated)
2. Physical inertial parameters for M3Pro MJCF (measured values pending)
3. USD asset validation on Isaac workstation GPU

**When PPO is ready:** It will be evaluated under the same benchmark governance
as GNM/ViNT/NoMaD — same scene set, same seed protocol, same evidence contract.
PPO results will be labeled `backend: isaaclab` and subject to the Isaac Lab
backend claim rules.

---

### Isaac Sim layer

**What it is:** NVIDIA's robotics simulation platform.  Used in FleetSafe for:

1. **Visualization and replay** (current) — The Isaac streaming viewer renders
   intervention evidence frame-by-frame.  See `docs/isaac/ISAAC_STREAMING_DASHBOARD.md`.
2. **Asset development** (current) — M3Pro USD/MJCF asset validation and
   visual inspection.  See `scripts/isaaclab/view_m3pro.sh`.
3. **Future physics backend** (gated) — Isaac Lab physics-backed benchmark
   evaluation (PPO training, sim-to-sim validation).

**Evidence boundary:**

```
MuJoCo:  generates intervention_evidence.jsonl  ← metric claims come from here
Isaac:   renders intervention_evidence.jsonl     ← visualization only, no metric claims
```

Isaac Sim does not generate any benchmark metrics in the current architecture.

---

## Sim-to-sim validation path

Before the Isaac Lab backend is enabled for metric generation, it must pass
a sim-to-sim validation loop against MuJoCo:

```
Step 1: Run N episodes on MuJoCo backend with frozen scene + seed
Step 2: Run same N episodes on Isaac Lab backend with same scene + seed
Step 3: Compare:
  - intervention_count per episode (must agree within ±2)
  - collision_count (must agree: 0 iff 0, 1 iff 1)
  - trajectory shape (Fréchet distance < 0.5m)
Step 4: If all three checks pass for ≥ 80% of episodes: Isaac backend unblocked
```

This validation is not yet run.  MuJoCo is the authoritative simulation
backend until this gate passes.

---

## Current state summary

| Component | Status | Gate |
|---|---|---|
| MuJoCo physics backend | Active — metric generation | ✓ passing |
| FleetSafe CBF-QP filter | Active — all three models | ✓ passing |
| Intervention evidence logging | Active — full JSONL per step | ✓ passing |
| GNM checkpoint + inference | Active — 6.4ms mean | ✓ PASS |
| ViNT checkpoint + inference | Active — 32.9ms mean | ✓ PASS |
| NoMaD checkpoint + inference | Active — 74.2ms mean | ✓ PASS |
| Isaac Sim visualization | Active — streaming viewer | ✓ (visualization only) |
| DDS / ROS2 integration | Not yet wired | blocked |
| PPO training | Not yet implemented | blocked on Isaac Lab backend |
| Isaac Lab physics backend | Not implemented | blocked — raises NotImplementedError |
| Real robot evaluation | Not yet supported | blocked |

---

## File pointers

| File | Role |
|---|---|
| `fleet_safe_vla/fleet_safety/yahboom_cbf.py` | CBF-QP implementation |
| `fleet_safe_vla/integrations/visualnav_transformer/fleetsafe_wrapper.py` | Policy wrapper |
| `fleet_safe_vla/benchmarks/visualnav_runner.py` | Benchmark runner (MuJoCo + mock) |
| `fleet_safe_vla/envs/mujoco/yahboom/` | MuJoCo envs (base, nav, obstacle) |
| `fleet_safe_vla/envs/isaaclab/replay/` | Isaac replay viewer modules |
| `scripts/isaaclab/replay_intervention.sh` | Isaac streaming viewer entry point |
| `scripts/visualnav/export_intervention_video.py` | Headless GIF/MP4 exporter |
| `docs/isaac/ISAAC_STREAMING_DASHBOARD.md` | Isaac streaming runbook |
| `docs/governance/CLAIMS_AND_LIMITATIONS.md` | What each backend may claim |
