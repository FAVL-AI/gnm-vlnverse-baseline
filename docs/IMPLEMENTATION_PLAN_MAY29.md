# FleetSafe × GNM/ViNT — Implementation Plan (May 29 Deadline)

**Status:** Implementation complete — evaluation matrix and data collector running.  
**Supervisor questions answered below with exact code references and run commands.**

---

## 1. What is GNM?

**GNM (General Navigation Model)** is a vision-based goal-conditioned navigation
model trained on diverse outdoor and indoor datasets.  Given a sequence of
egocentric RGB images (context) and a goal image, it predicts a series of
waypoints in the robot's local coordinate frame.

```
Input:   5 RGB frames (context)  +  1 goal image
          ↓
        GNM ResNet18 encoder
          ↓
Output:  5 waypoints (dx, dy) in robot frame  +  estimated steps to goal
```

ViNT is the vision-transformer version of GNM with identical I/O format.
NoMaD replaces the waypoint head with a diffusion process (8-step horizon).

All three come from the official `visualnav-transformer` repository:
`third_party/visualnav-transformer/` (pinned commit `dca79815`).

---

## 2. How do we use the GNM code?

The FleetSafe benchmark wraps each model with a thin adapter.  No upstream
code is modified.

```
third_party/visualnav-transformer/   ← upstream (unchanged)
fleet_safe_vla/integrations/visualnav_transformer/
    gnm_adapter.py    ← wraps GNMModel
    vint_adapter.py   ← wraps ViNTModel
    nomad_adapter.py  ← wraps NoMaDModel
    fleetsafe_wrapper.py  ← CBF-QP safety layer
    isaac_obs_adapter.py  ← camera context queue
    benchmark_runner.py   ← full episode loop
```

To run GNM or ViNT:

```bash
# Quick evaluation (mock physics, real GNM/ViNT inference):
python scripts/visualnav/run_evaluation_matrix.py \
    --models gnm vint \
    --episodes 10

# With real checkpoints:
python scripts/visualnav/run_evaluation_matrix.py \
    --gnm-ckpt  third_party/visualnav-transformer/model_weights/gnm/gnm.pth \
    --vint-ckpt third_party/visualnav-transformer/model_weights/vint/vint.pth

# Baseline contract audit (25 checks, 5 seconds):
python scripts/visualnav/audit_preprocessing.py
```

---

## 3. Environment: Isaac Sim first, then real robot

**Phase 1 (May 29): Isaac Sim**

Isaac Sim is safer, faster to debug, already integrated.  The full pipeline is:

```
Isaac RGB camera → GNM/ViNT adapter → u_nom → FleetSafe CBF-QP → u_safe → Isaac robot
```

Run command:

```bash
conda activate isaac
python scripts/demo/run_supervisor_demo_isaac.py \
    --model vint \
    --scene hospital_corridor \
    --fleetsafe
```

Dashboard: http://localhost:8080/dashboard/demo

**Phase 2 (post-deadline): Real Yahboom M3Pro**

Same pipeline, camera from `/usb_cam/image_raw` via ROS2 bridge.

---

## 4. Robot

**Yahboom RosMaster M3Pro** — holonomic indoor mobile robot.

| Property | Value |
|---|---|
| Drive type | Mecanum (holonomic, vx/vy/wz) |
| Max speed | 0.5 m/s forward |
| Camera | 62° HFOV forward-facing USB camera |
| Sensors | RGB camera, odometry, IMU, lidar |
| ROS2 interface | `/cmd_vel`, `/odom`, `/usb_cam/image_raw`, `/imu/data` |
| MJCF | `fleet_safe_vla/robots/yahboom/mjcf/yahboom_x3.xml` |
| URDF | `fleet_safe_vla/robots/yahboom/urdf/yahboom_m3pro.urdf` |

Check robot topics:

```bash
bash scripts/real_robot/check_m3pro_topics.sh
```

---

## 5. Sensors

| Sensor | Used by | Topic / Source |
|---|---|---|
| Forward RGB camera | **Navigation model (GNM/ViNT)** | `/usb_cam/image_raw` |
| Odometry | FleetSafe CBF + logging | `/odom` |
| IMU | FleetSafe CBF (47-dim obs_vec) | `/imu/data` |
| Lidar/scan | FleetSafe CBF obstacle detection | `/scan` |

**Critical distinction:**

```
GNM / ViNT  receives:   camera images ONLY
FleetSafe   receives:   robot state + obstacle geometry ONLY
```

The navigation model must NOT receive sensor state or obstacle positions.
This is enforced and tested in `tests/test_baseline_contract.py`.

---

## 6. ROS2 Setup

Start ROS2 bridge (connects real robot to dashboard):

```bash
# On the M3Pro robot (Jetson):
ros2 launch yahboom_m3pro bringup.launch.py

# On workstation (backend reads /odom, /usb_cam/image_raw etc):
python command-center/backend/main.py        # starts ROS2 bridge thread automatically
```

Check topics live:

```bash
ros2 topic list
ros2 topic hz /usb_cam/image_raw   # expect ~30 Hz
ros2 topic hz /odom                # expect ~11 Hz
ros2 topic hz /imu/data            # expect ~100 Hz
```

ROS2 bridge source: `command-center/backend/services/ros2_bridge.py`

---

## 7. Data Collection

Collect training episodes (images + trajectory + actions):

```bash
# Collect 50 GNM episodes on hospital_corridor:
python scripts/visualnav/collect_episodes.py \
    --model gnm \
    --scene hospital_corridor \
    --episodes 50 \
    --fleetsafe

# Output structure:
data/training_episodes/gnm/hospital_corridor/fleetsafe/
    ep_0000/
        images/step_00000.jpg … step_00299.jpg   ← egocentric camera frames
        goal.jpg                                  ← goal image
        trajectory.csv   ← step, x, y, yaw, dist_to_goal, min_obs_dist
        actions.csv      ← step, raw_vx, raw_wz, safe_vx, safe_wz, intervened
        metrics.json     ← episode summary
        audit.json       ← perception contract proof
    ep_0001/
    …
    collection_summary.json
```

The format is compatible with the visualnav-transformer training pipeline.
Each `images/step_NNNNN.jpg` is what the navigation model saw at that step.
`actions.csv` records both `raw_vx` (what GNM wanted) and `safe_vx`
(what FleetSafe allowed), making the intervention effect explicit.

---

## 8. Retraining GNM

Once episodes are collected:

```bash
# Convert to visualnav-transformer dataset format (forthcoming):
python scripts/visualnav/convert_to_vnt_format.py \
    --input  data/training_episodes/gnm/hospital_corridor \
    --output data/gnm_hospital_dataset

# Fine-tune from official checkpoint:
cd third_party/visualnav-transformer/train
python train.py \
    --config vint_train/config/gnm.yaml \
    --data-folder ../../data/gnm_hospital_dataset \
    --eval-fraction 0.1

# Validate the fine-tuned model:
python ../../scripts/visualnav/audit_preprocessing.py --model gnm
```

Training details from upstream `gnm.yaml`:
- Image size: 85 × 64
- Context: 5 frames
- Normalisation: ImageNet mean/std
- Loss: waypoint regression + goal distance

---

## 9. Evaluation Plan

Run the 4-condition matrix:

```bash
python scripts/visualnav/run_evaluation_matrix.py \
    --models gnm vint \
    --scenes hospital_corridor cluttered_navigation \
    --episodes 20 \
    --output results/evaluation_matrix.json
```

**Output table:**

```
┌─────────────────────────────────────────────────────────────────────┐
│ Condition          │ Success │ Collide │ Interv% │ MinDist │ Infer │
├─────────────────────────────────────────────────────────────────────┤
│ GNM                │   …%    │   …%    │    —    │  …m     │  …ms  │
│ GNM + FleetSafe    │   …%    │   …%    │   …%    │  …m     │  …ms  │
│ ViNT               │   …%    │   …%    │    —    │  …m     │  …ms  │
│ ViNT + FleetSafe   │   …%    │   …%    │   …%    │  …m     │  …ms  │
└─────────────────────────────────────────────────────────────────────┘
```

**Expected result:** FleetSafe reduces collision rate and increases minimum
obstacle distance, at the cost of a small number of interventions
(modified velocity commands).  GNM and ViNT provide navigation intent;
FleetSafe provides safety correctness.

**Metrics collected per episode:**

| Metric | Description |
|---|---|
| Success rate | Reached goal without collision |
| Collision rate | Robot body contact with obstacle |
| Intervention rate | % of steps where CBF modified u_nom |
| Min obstacle dist | Closest approach to any obstacle |
| Path length | Total metres driven |
| Time to goal | Seconds from start to goal |
| Inference latency | GNM/ViNT forward pass time (ms) |
| CBF solve latency | QP solve time (ms) |
| ‖u_nom − u_safe‖ | Magnitude of FleetSafe velocity correction |

---

## 10. Timeline: Working by May 29

**What is already done:**

| Item | Status |
|---|---|
| GNM adapter (`gnm_adapter.py`) | ✅ Complete, tested |
| ViNT adapter (`vint_adapter.py`) | ✅ Complete, tested |
| NoMaD adapter (`nomad_adapter.py`) | ✅ Complete, tested |
| FleetSafe CBF-QP wrapper | ✅ Complete, tested |
| Isaac Sim demo loop | ✅ `run_supervisor_demo_isaac.py` |
| MuJoCo episode runner | ✅ `benchmark_runner.py` |
| Egocentric camera contract | ✅ Fixed + enforced |
| Baseline contract audit (25 checks) | ✅ All passing |
| Contract test suite (51 tests) | ✅ All passing |
| Evaluation matrix script | ✅ `run_evaluation_matrix.py` |
| Episode data collector | ✅ `collect_episodes.py` |
| Dashboard (demo page) | ✅ Running |
| Digital twin sync | ✅ `/api/twin/ws` |

**What to run for May 29 demonstration:**

```bash
# 1. Verify baseline contract (2 minutes):
python scripts/visualnav/audit_preprocessing.py

# 2. Run 4-condition evaluation matrix (5–15 minutes):
python scripts/visualnav/run_evaluation_matrix.py \
    --models gnm vint \
    --episodes 10 \
    --output results/may29_evaluation.json

# 3. Live Isaac Sim demo (requires conda activate isaac):
conda activate isaac
python scripts/demo/run_supervisor_demo_isaac.py --model vint --fleetsafe

# 4. Start dashboard to show camera + CBF:
cd command-center && make start
# → http://localhost:8080/dashboard/demo
```

---

## CBF-QP Safety Filter (Mathematical Formulation)

```
u_safe = argmin_{u}  ½ ‖u − u_nom‖²
subject to:
    ḣᵢ(x, u) + α·hᵢ(x) ≥ 0   for each obstacle i
    u_min ≤ u ≤ u_max
```

where `hᵢ(x) = ‖x − xᵢ‖² − d_safe²` is the barrier function for obstacle `i`.

`u_nom` comes from GNM/ViNT.  
`u_safe` is the closest safe command to `u_nom` in the 2-norm sense.  
If no safe `u` exists, an E-STOP is triggered.

**Source:** `fleet_safe_vla/fleet_safety/yahboom_cbf.py`

---

## Supervisor-ready statement

> For the GNM / ViNT integration, we start with Isaac Sim rather than the real
> robot.  Isaac Sim is safer, faster to debug, and already integrated with the
> FleetSafe dashboard.  The pipeline is: the Isaac Sim camera feeds the
> GNM or ViNT model, which predicts waypoints in robot frame.  The FleetSafe
> CBF-QP filter then modifies those waypoints to ensure obstacle safety
> constraints are satisfied before executing the command.  The navigation model
> receives only egocentric camera images; robot state and obstacle geometry
> are used exclusively by the FleetSafe safety filter.  We have verified this
> separation with 25 automated checks and 51 contract tests.  The 4-condition
> evaluation matrix (GNM/ViNT × with/without FleetSafe) can be run with a
> single command and produces a metric table showing success rate, collision
> rate, intervention rate, and path length for each condition.  Once the
> simulator pipeline is validated, the same camera-to-command loop transfers
> directly to the real Yahboom M3Pro via the existing ROS2 bridge.
