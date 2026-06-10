# GNM-VLNVerse Baseline: Implementation Walkthrough

Slide deck for Bo / Rui review meeting.
Format: plain text, one section per slide, speaker notes below each slide.

---

## Opening line

> I will answer each point by showing the implementation path: what is done, how it works, which command proves it, and what is still planned.

---

---

## Slide 1 — Title

**GNM-VLNVerse Baseline**
Reproducible Isaac Sim pipeline for visual-goal navigation.

F. Van Laarhoven — Newcastle University

---

**Speaker notes:**

Good morning. This walkthrough maps directly to the questions you raised after the last meeting. I will go through each one in order, showing what is implemented, how it works at the code level, and which command you can run to verify it yourself. Where something is still in progress I will say so explicitly.

---

---

## Slide 2 — One-slide story

**The full pipeline in one line:**

```
Isaac Sim scene
  → robot RGB camera
    → trajectory / manual drive
      → RGB frames + x/y/yaw pose
        → GNM dataset format
          → training / evaluation
            → replay dashboard + metrics
```

Every step in this chain has a corresponding script, a test, and a command you can run without a GPU.

---

**Speaker notes:**

This slide is the map for everything that follows. I want you to see that there is a complete chain from the simulation through to metrics. The parts that do not require Isaac Sim — dataset proof, dashboard export, dry-run tests — you can run locally right now. The Isaac Sim steps require the GPU machine, which I will demonstrate live.

---

---

## Slide 3 — Bo's process mapped

| Step | Status |
|------|--------|
| Start Isaac Sim | DONE |
| Import simulated scene | DONE |
| Set robot and sensor | DONE — replay proof; manual drive collects RGB + x/y/yaw |
| Follow trajectory | DONE — `traj_data.pkl` drives frame-by-frame replay |
| Collect data | DONE — RGB, pose, action log, GNM format conversion |
| Train GNM | DONE — MobileNet baseline stable; results logged |
| Evaluate | DONE — SR 20.0 %, OSR 46.7 %, NE 6.51 m |
| New scene / holdout | CONFIGURED — `kujiale_0271` split ready; full holdout pending |
| Custom scene | DONE as proof-of-method — CustomVLN-Office |

---

**Speaker notes:**

This is the direct answer to your process questions. Every row is either done or explicitly marked as pending. I am not claiming anything is complete unless I can show you the command that proves it.

---

---

## Slide 4 — Start Isaac Sim

**Status: DONE**

**Method:**

Isaac Sim is started via `SimulationApp`. The entry point parses CLI flags before calling `SimulationApp`, so proof commands (dataset validation, dashboard export) run without a GPU.

```python
# scripts/gnm/replay_gnm_demo.py, line 748
from isaacsim import SimulationApp
app = SimulationApp({"headless": False, "renderer": "RayTracedLighting"})
```

**Command (requires Isaac Sim conda environment):**

```bash
conda run -n isaac python scripts/gnm/replay_gnm_demo.py
```

**Evidence:** Isaac Sim window opens, USD scene loads, robot marker appears at start pose.

---

**Speaker notes:**

The script detects whether it is running inside Isaac Sim by trying to import `isaacsim`. If that import is not available it continues in proof mode, which is why `--prove-dataset` and `--export-live-dashboard` work on a laptop with no GPU.

---

---

## Slide 5 — Import simulated scene

**Status: DONE**

**Four Kujiale scenes indexed:**

| Scene | Train | Val |
|-------|-------|-----|
| kujiale_0092 | 62 | 4 |
| kujiale_0118 | 71 | 4 |
| kujiale_0203 | 61 | 4 |
| kujiale_0271 | 44 | 3 ← held-out |
| **Total** | **238** | **15** |

**Command (no GPU required):**

```bash
python3 scripts/gnm/replay_gnm_demo.py --list-scenes
```

**Source:** `scripts/gnm/replay_gnm_demo.py`, `discover_scenes()`.

---

**Speaker notes:**

The scene discovery walks `datasets/vlntube/train` and `datasets/vlntube/val`, counts trajectory folders per scene, and prints this table. You can run this command right now without Isaac Sim. The 238 / 15 split is the target from the VLNVerse Track A specification.

---

---

## Slide 6 — Robot and sensor setup

**Status: DONE for replay and data proof**

**What is placed in the scene:**

- `ROBOT_MARKER` USD prim — moved to each frame's `(x, y, yaw)` pose during replay.
- Three named USD cameras: `START_CAMERA`, `CURRENT_CAMERA`, `GOAL_CAMERA`.
- Each camera points in the robot heading direction.
- Custom `gnm:*` USD attributes store pose, frame index, and metric values visible in the Isaac Sim Property panel.

**State recorded per step:**

```
x (m)   y (m)   yaw (rad)
```

**Source:** `scripts/gnm/replay_gnm_demo.py`, `make_camera()`, line 842.

**Pending:** Full closed-loop ROS2 camera topic (`camera/image_raw`) — see Slide 9.

---

**Speaker notes:**

The three cameras give the reviewer three simultaneous viewpoints: where the robot started, where it is now, and where it needs to go. This is the GNM input format made visual — current frame and goal frame side by side.

---

---

## Slide 7 — Following a specific trajectory

**Status: DONE**

**Method:**

Each trajectory is stored in `traj_data.pkl`:

```python
data      = pickle.load(open(traj_dir / "traj_data.pkl", "rb"))
positions = data["position"]   # shape (T, 2)  — world-frame x, y
yaws      = data.get("yaw", np.zeros(T))       # shape (T,)
```

The replay loop reads each frame's pose and moves the `ROBOT_MARKER` prim:

```python
translate_op.Set(Gf.Vec3d(positions[idx][0], positions[idx][1], 0.0))
rotate_op.Set(math.degrees(yaws[idx]))
```

**Evidence — example trajectory:**

```
Episode:  kujiale_0092 / val / ep_000
Frames:   93
Path length: 18.5 m
```

**Source:** `scripts/gnm/replay_gnm_demo.py`, replay loop, line 1239.

---

**Speaker notes:**

The robot does not navigate autonomously in this baseline. It follows the ground-truth trajectory from the dataset. This is the standard approach for a reproducibility baseline: prove that the data is correct, prove the camera views are correct, then evaluate model predictions against that ground truth.

---

---

## Slide 8 — Data collected

**Status: DONE**

**Per-step output:**

| File | Contents |
|------|----------|
| `rgb/000000.jpg … 000N.jpg` | RGB frame from CURRENT_CAMERA |
| `traj_data.pkl` | `position (T,2)`, `yaw (T,)`, `actions`, `timestamps` |
| `actions.jsonl` | Per-step: frame index, x, y, yaw, action key, distance to goal |
| `metadata.json` | mode, scene, n_steps, path_length_m, official_benchmark_data flag |

**Local waypoint / action label derivation:**

```python
def _local_waypoint(positions, yaws, frame_idx, horizon):
    tgt = min(frame_idx + horizon, T - 1)
    wx  = positions[tgt][0] - positions[frame_idx][0]
    wy  = positions[tgt][1] - positions[frame_idx][1]
    cos_y, sin_y = math.cos(-yaws[frame_idx]), math.sin(-yaws[frame_idx])
    lx  = cos_y * wx - sin_y * wy
    ly  = sin_y * wx + cos_y * wy
    return float(lx), float(ly)
```

**Source:** `scripts/gnm/collect_custom_vln_office_data.py`, `_local_waypoint()`, line 70.

---

**Speaker notes:**

The local waypoint is the ground-truth label GNM is trained to predict. It is the position of the robot `horizon` frames ahead, expressed in the robot's current frame. This is the same formulation used in the original GNM paper.

---

---

## Slide 9 — ROS2 interface

**Status: PARTIAL / PLANNED**

**Current state:**

The pipeline is dataset- and replay-based. Isaac Sim outputs pose data to `traj_data.pkl`; the GNM model runs as an offline inference step.

**What is planned:**

```
Isaac Sim (publisher)          GNM node (subscriber / publisher)
─────────────────────          ──────────────────────────────────
camera/image_raw           →   current RGB input
odom                       →   current x/y/yaw
tf                         →   frame transforms
                           ←   cmd_vel  (waypoint command)
```

**What is not claimed:**

- ROS2 closed-loop is not implemented.
- Do not treat any demo as a closed-loop navigation result.

**Source of planned interface:** `configs/gnm/ros2_interface.yaml` (configuration stub).

---

**Speaker notes:**

I want to be direct about this. The ROS2 bridge is planned and partially designed, but it is not running. Everything I will show you today is replay-based. When I say the robot follows a trajectory, I mean the script reads poses from a file and moves the prim — it does not receive navigation commands from a live model.

---

---

## Slide 10 — GNM input / output format

**Status: DONE**

**Input to GNM at each step:**

```
current RGB image  (frame i)
goal RGB image     (last frame of episode, or manually marked goal)
```

**Output from GNM:**

```
local waypoint:  (delta_x, delta_y)  in robot frame
```

**How the input images are selected:**

```python
# scripts/gnm/replay_gnm_demo.py, line 164
start_img = str(best_traj / "0.jpg")
goal_img  = str(best_traj / f"{n_steps - 1}.jpg")
mid_img   = str(best_traj / f"{CURRENT_FRAME}.jpg")
```

**Diagram:**

```
frame_i.jpg  +  goal.jpg
      │
      ▼
  GNM encoder
      │
      ▼
  (delta_x, delta_y)   ← local waypoint prediction
```

---

**Speaker notes:**

This is the core of GNM. Two images go in — current view and goal view. A local waypoint comes out. The model does not have a map. It only sees what the camera sees right now and what the goal looks like. The training objective is to make this prediction match the ground-truth waypoint we derive from `traj_data.pkl`.

---

---

## Slide 11 — Dataset proof

**Status: DONE**

**Command (no Isaac Sim, no GPU required):**

```bash
python3 scripts/gnm/replay_gnm_demo.py --prove-dataset
```

**Expected output:**

```
Train trajectories : 238  (target: 238)  PASS
Val   trajectories :  15  (target:  15)  PASS

SR  = 3/15 = 20.0%
OSR = 7/15 = 46.7%
NE  = 6.51 m

Validation files:
  results/bo_reviewer_packet/03_success_rate_breakdown.md
  results/bo_reviewer_packet/03_success_rate_breakdown.csv
```

**Source:** `scripts/gnm/replay_gnm_demo.py`, `prove_dataset()`.

---

**Speaker notes:**

You can run this command right now on your own machine after cloning the repository and linking the dataset. It reads `traj_data.pkl` files, counts trajectories per scene, verifies the split, and reproduces the metric numbers from the CSV. No model inference happens here — it is pure data validation.

---

---

## Slide 12 — Baseline performance

**Status: DONE — reproduced baseline**

**Track A validation result:**

| Metric | Value | Definition |
|--------|-------|------------|
| SR | 20.0 % | 3 / 15 episodes, final distance ≤ 3.0 m |
| OSR | 46.7 % | 7 / 15 episodes ever within 3.0 m |
| NE | 6.51 m | Mean final distance to goal |

**Per-episode breakdown:**

```
results/bo_reviewer_packet/03_success_rate_breakdown.md
results/bo_reviewer_packet/03_success_rate_breakdown.csv
```

**Important:** This is a reproduced baseline result. It is not a final SOTA claim. The purpose is to establish a reproducible starting point.

---

**Speaker notes:**

Three out of fifteen validation episodes reach the goal. Seven have been within goal range at some point. The mean final distance is 6.51 metres. These numbers are in the breakdown file with per-episode detail. I am not claiming this is a strong result — I am claiming it is a reproducible result that we can improve from.

---

---

## Slide 13 — Training attempts and variants

**Status: DONE — ablation evidence retained**

**What was tried:**

| Variant | Outcome |
|---------|---------|
| MobileNetV2 backbone (baseline) | Stable. Current official result. |
| EfficientNet-B0 | Feature scale mismatch — distance head unstable. |
| EfficientNet with LR warmup | Collapsed in early training. |
| EMA (exponential moving average) | Tested, no consistent gain at this data scale. |
| AMP (automatic mixed precision) | Tested, stable but no accuracy improvement. |

**Conclusion:** MobileNetV2 baseline remains the official result. Ablation evidence is retained in training logs.

---

**Speaker notes:**

I tried to improve the result by changing the encoder. EfficientNet has stronger ImageNet performance, but the feature distribution it produces is different from MobileNet, and the distance head we use was tuned for MobileNet scale. Rather than re-tune everything, I stopped those runs and kept the baseline. This is not a failure — it is how ablation studies work.

---

---

## Slide 14 — Why the first training attempts failed

**Status: DONE — understood and documented**

**Simple explanation:**

GNM has two components:
1. An **image encoder** — compresses each RGB frame to a feature vector.
2. A **distance head** — takes the difference of two feature vectors and predicts the waypoint.

When we swap the encoder, the scale of the feature vectors changes. The distance head was not retrained to match the new scale. As a result:

- predictions were 10–100× too large;
- the loss exploded in the first few epochs;
- training collapsed.

**Fix applied:** Retain the MobileNet encoder. Treat any encoder change as requiring full retraining of both components.

**Source:** `scripts/gnm/04_train_gnm.py`, encoder freeze / unfreeze logic.

---

**Speaker notes:**

The lesson is that you cannot swap just one part of a jointly trained model. The encoder and the head learned together. If you change the encoder, the head must re-learn too. We did not have enough compute budget to retrain from scratch with EfficientNet, so we stayed with MobileNet.

---

---

## Slide 15 — Goal image setup

**Status: DONE**

**How the goal image is selected:**

In the VLNVerse dataset:

```python
goal_img = str(best_traj / f"{n_steps - 1}.jpg")
```

The goal is the final RGB frame of the episode — the frame captured at the goal position.

**In manual test-drive:**

```
Key G — marks the current pose and saves the current RGB frame as the goal image.
```

This is logged in `actions.jsonl` as `{"action": "mark_goal", ...}`.

**Source:** `scripts/gnm/manual_testdrive.py`, `Episode.mark_goal()`, line 118.

---

**Speaker notes:**

The goal image tells the model what the destination looks like. In the VLNVerse dataset, this is the last frame of the ground-truth trajectory. In manual collection, the user drives to approximately the desired goal, presses G, and that frame is saved. The model is never given coordinates — only images.

---

---

## Slide 16 — New scene testing

**Status: CONFIGURED — full evaluation pending**

**`kujiale_0271` is the designated held-out scene:**

```yaml
# configs/gnm/splits/scene_holdout_kujiale_0271.yaml
holdout_scene: kujiale_0271
train_scenes:
  - kujiale_0092
  - kujiale_0118
  - kujiale_0203
```

**What this means:**

- Training uses only the three non-holdout scenes.
- Evaluation on `kujiale_0271` tests generalisation to an unseen scene.
- The split is configured and the data is present (44 train / 3 val trajectories).

**Pending:** Running the full scene-holdout training and evaluation cycle.

**Command (when ready):**

```bash
python3 scripts/gnm/06_evaluate.py \
    --split configs/gnm/splits/scene_holdout_kujiale_0271.yaml
```

---

**Speaker notes:**

This is the experiment that answers: can the model navigate in a room it has never seen during training? The configuration is ready. We have not run it yet because it requires a full training cycle on the reduced split. I will have results after the next training run.

---

---

## Slide 17 — Custom scene

**Status: DONE as proof-of-method**

**What CustomVLN-Office is:**

A navigation scene built entirely from Isaac Sim primitives — no VLNVerse assets, no Kujiale USD files.

Purpose: prove that we can create our own environment and run the same data collection pipeline in it.

**What it proves:**

- We are not locked to the VLNVerse dataset.
- The pipeline (RGB capture, pose logging, GNM format conversion) is generic.
- A reviewer can run the proof without access to VLNVerse data.

**Command (no GPU required):**

```bash
python3 scripts/gnm/replay_gnm_demo.py --prove-dataset
# CustomVLN-Office section outputs independently
```

**Source:** `scripts/gnm/create_custom_vln_office_scene.py`, `scripts/gnm/collect_custom_vln_office_data.py`.

**Note:** CustomVLN-Office is not an official VLNVerse metric. It is proof-of-method only.

---

**Speaker notes:**

The custom scene was built after the question: "how do we know the pipeline works, not just the dataset?" The answer is: build a scene from scratch, collect data through the same pipeline, and show that the output format is identical. This is what CustomVLN-Office does.

---

---

## Slide 18 — Manual test-drive

**Status: DONE**

**What it does:**

A user can navigate inside Isaac Sim using keyboard controls, and the system records:

- RGB frames per step
- x, y, yaw per step
- action key pressed per step
- distance to goal per step
- marked goal pose and image

**Controls:**

| Key | Action |
|-----|--------|
| W / S | Forward / backward |
| A / D | Rotate left / right |
| Q / E | Strafe left / right |
| G | Mark current pose as goal |
| P | Save episode to disk |
| R | Reset episode |
| Esc | Exit |

**Dry-run (no Isaac Sim required):**

```bash
python3 scripts/gnm/manual_testdrive.py --dry-run
python3 scripts/gnm/replay_manual_testdrive.py --dry-run
python3 scripts/gnm/convert_manual_testdrive_to_gnm.py --dry-run
```

**Source:** `scripts/gnm/manual_testdrive.py`, `Episode` class, lines 60–160.

---

**Speaker notes:**

Manual test-drive proves that data collection is under our control. We do not depend entirely on the VLNVerse dataset. We can drive through any Isaac scene, collect data in the same format, and feed it into the same training pipeline. The dry-run commands print the full output schema so you can see exactly what would be saved.

---

---

## Slide 19 — Live dashboard proof

**Status: DONE**

**What the dashboard shows:**

```
┌──────────────┬──────────────────────┬──────────────┐
│  START VIEW  │  CURRENT LIVE VIEW   │  GOAL VIEW   │
│  frame 0     │  frame 47            │  frame 92    │
│  x=1.20      │  x=4.87              │  x=8.31      │
│  y=0.95      │  y=2.14              │  y=5.72      │
└──────────────┴──────────────────────┴──────────────┘
      dist_to_goal: 3.42 m    RUNNING
```

When `dist_to_goal ≤ 3.0 m`, status changes to `GOAL REACHED`.

**Command (no Isaac Sim, no GPU required):**

```bash
python3 scripts/gnm/replay_gnm_demo.py --export-live-dashboard
```

Output: `results/bo_reviewer_packet/live_dashboard/frame_XXXX.png` (one PNG per trajectory step).

**Source:** `scripts/gnm/replay_gnm_demo.py`, `_make_live_dashboard_frame()`.

---

**Speaker notes:**

This command produces the visual evidence for each trajectory. You see the start frame, the current frame at each step, and the goal frame side by side. The distance counter updates every frame. When it crosses the 3-metre threshold, the episode is counted as a success. You can generate all 15 validation episodes on a laptop.

---

---

## Slide 20 — What Rui should run

**Five commands to verify the baseline locally:**

**Step 1 — Bootstrap:**

```bash
bash scripts/gnm/bootstrap_demo_env.sh
source .venv/bin/activate
```

**Step 2 — Link data:**

```bash
bash scripts/gnm/link_vlntube_data.sh /path/to/vlntube
python3 scripts/gnm/check_demo_ready.py
```

**Step 3 — Proof commands:**

```bash
python3 scripts/gnm/replay_gnm_demo.py --prove-dataset
python3 scripts/gnm/replay_gnm_demo.py --export-live-dashboard
python3 scripts/gnm/manual_testdrive.py --dry-run
```

**Step 4 — Tests:**

```bash
python3 -m pytest tests/gnm -q
```

Expected result: all tests pass (torch-dependent model tests skip if PyTorch is absent).

---

**Speaker notes:**

These four steps are the complete fresh-clone verification path. No GPU, no Isaac Sim, no PyTorch required. The bootstrap script creates the virtual environment. The readiness check tells you exactly which items are present and which are missing before you run anything.

---

---

## Slide 21 — Implemented vs planned

**DONE:**

| Item | Evidence command |
|------|-----------------|
| VLNVerse dataset proof (238 train, 15 val) | `--prove-dataset` |
| Four Kujiale scenes indexed | `--list-scenes` |
| RGB frame validation | `--prove-dataset` |
| `traj_data.pkl` pose validation | `--prove-dataset` |
| GNM current/goal image input format | `--export-live-dashboard` |
| Local waypoint/action label derivation | `test_data_converter.py` |
| Live start/current/goal dashboard | `--export-live-dashboard` |
| Manual test-drive recording | `--dry-run` commands |
| Manual episode replay and GNM conversion | `--dry-run` commands |
| CustomVLN-Office scene (proof-of-method) | `test_custom_vln_office.py` |
| Baseline result: SR 20 %, OSR 46.7 %, NE 6.51 m | `03_success_rate_breakdown.md` |

**PLANNED / PENDING:**

| Item | Status |
|------|--------|
| ROS2 closed-loop Isaac-to-GNM interface | Planned |
| Zero-shot / off-the-shelf GNM formal result | Pending validation run |
| `kujiale_0271` full scene-holdout evaluation | Configured — pending training run |
| Custom fine-tuning on manual episode data | Pending |

---

**Speaker notes:**

This is the full scope table. I will not claim a planned item is done. If it is in the PLANNED row, it means the design is present but the execution has not been verified yet.

---

---

## Slide 22 — Next week plan

**Four concrete deliverables:**

| Action | Output |
|--------|--------|
| Run `kujiale_0271` holdout evaluation | SR / OSR / NE numbers for held-out scene |
| Record one manual CustomVLN-Office episode | Episode data in `datasets/manual_testdrive_custom_office/` |
| Convert manual episode to GNM format | `datasets/manual_gnm_format/` ready for training |
| Prepare ROS2 bridge interface diagram | Diagram showing Isaac Sim → ROS2 → GNM topic layout |

**Commands that will be run:**

```bash
# Scene-holdout evaluation
python3 scripts/gnm/06_evaluate.py \
    --split configs/gnm/splits/scene_holdout_kujiale_0271.yaml

# Manual episode conversion
python3 scripts/gnm/convert_manual_testdrive_to_gnm.py \
    --input  datasets/manual_testdrive_custom_office \
    --output datasets/manual_gnm_format
```

---

**Speaker notes:**

These are the four implementation targets for the next work cycle. The first target gives us a proper held-out scene result. The second and third complete the manual data-collection-to-GNM-format path. The fourth prepares the ROS2 interface work by making the Isaac Sim → ROS2 → GNM topic layout explicit before implementation.

---

---

*End of slide deck.*

*Source: `results/bo_reviewer_packet/BO_RUI_SLIDES.md`*
*Repository: `https://github.com/FAVL-AI/gnm-vlnverse-baseline`*
