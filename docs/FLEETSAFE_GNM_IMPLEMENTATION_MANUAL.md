# FleetSafe-GNM Isaac ROS 2 Implementation Manual

## What this manual covers

This manual explains the full plan for deploying a safe, ROS 2-based visual navigation system on a real robot (Yahboom ROSMASTER M3 Pro), using Isaac Sim as the safe testing environment first.

The system has four main parts:

- **GNM** — the navigation brain. It reads camera images and a goal image, then produces velocity commands to move toward the goal.
- **FleetSafe** — the safety shield. It sits between GNM and the robot and blocks any command that would cause a collision or violate a safety certificate.
- **Isaac Sim** — a physics-accurate 3D simulator where you test the system safely before touching the real robot.
- **ROS 2** — the communication system that connects all parts using standard topics.

---

## Beginner questions

### What is ROS 2?

ROS 2 (Robot Operating System 2) is a software framework for building robot applications. It is not an operating system in the traditional sense. It provides a publish/subscribe message-passing system where different programs (called **nodes**) communicate through named channels called **topics**.

For example, the camera node publishes images on `/camera/image_raw`. The GNM node subscribes to that topic, reads the image, and publishes a velocity command on `/gnm/cmd_vel_raw`. The FleetSafe node subscribes to that velocity command, checks it, and publishes a safe command on `/fleetsafe/cmd_vel_safe`. Finally, the robot driver subscribes to `/cmd_vel` and moves the wheels.

ROS 2 runs on Ubuntu and is the standard communication layer for modern robotics research.

### What is TF?

TF (Transform) is the ROS 2 system for tracking the position and orientation of every part of the robot relative to every other part, and relative to the world.

For example, TF knows where the camera is relative to the robot base, and where the robot base is in the room. When GNM needs to know where the robot is in the map, it queries TF. When the safety system needs to check the distance to a wall, it uses TF to transform the laser scan reading into the robot's frame of reference.

The `/tf` topic carries these transforms continuously. Without correct TF data, navigation and safety checks cannot work reliably.

### What is Isaac Sim?

Isaac Sim is NVIDIA's physics simulator for robotics. It renders realistic camera images, simulates wheel odometry, laser scans, and IMU data, and applies physical forces to the robot model.

We use Isaac Sim as the safe test world because:

- It gives us realistic sensor data without risk of damaging a real robot.
- We can reset the scene instantly after a collision.
- We can collect large amounts of training data quickly.
- It produces ROS 2 topics that look identical to what a real robot would produce, so the GNM and FleetSafe code does not need to change when we move to the real robot.

### What is a Python virtual environment?

A Python virtual environment is an isolated folder that contains a specific version of Python and specific Python packages. It prevents different projects from interfering with each other's dependencies.

To create and use one:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

All GNM training and evaluation in this repository runs inside a Python virtual environment.

### What is an Isaac virtual environment?

Isaac Sim ships with its own Python environment (sometimes called the Isaac Python or the `isaac` conda environment). It includes NVIDIA-specific packages for GPU simulation that cannot be installed into a standard Python virtual environment.

You activate it with:

```bash
conda activate isaac
```

Isaac Sim simulation scripts must run inside this environment. GNM training and evaluation scripts run in the regular `.venv` environment. The two environments are kept separate.

### What is LoRA?

LoRA (Low-Rank Adaptation) is a technique for fine-tuning large neural networks efficiently. Instead of updating all the weights in the network, LoRA adds a small number of trainable parameters alongside the frozen original weights.

For GNM fine-tuning, LoRA lets us adapt the pre-trained public GNM checkpoint to our specific robot, environment, and sensor configuration without retraining from scratch. This saves GPU memory and training time.

The alternative is head tuning: keeping all GNM backbone weights frozen and only training the final output layer. Head tuning is faster but less flexible than LoRA.

### What data does GNM need?

GNM needs pairs of observations: a **current RGB image** and a **goal RGB image**, plus a **waypoint label** that tells the model where to move next.

From rosbag2 data, each training tuple contains:

- `context_images`: a short sequence of recent camera images (e.g. the last 5 frames)
- `goal_image`: the RGB image from the goal position
- `waypoint`: the (dx, dy) displacement from the current position to the next waypoint
- `distance_to_goal`: the remaining distance in metres
- `odometry`: the robot pose at each frame

GNM does not use laser scans or maps during inference. It operates purely from RGB images and relative goal position.

### What data does FleetSafe need?

FleetSafe needs real-time sensor data to compute its safety certificate and enforce the Control Barrier Function (CBF) constraint:

- `/scan`: laser scan readings to detect obstacles
- `/odom`: robot velocity and position
- `/tf`: current robot pose in the map frame

FleetSafe does not need camera images or goal information. It only needs to know the current robot state and the surrounding obstacle geometry.

### Why do we start in simulation?

Starting in simulation avoids hardware risk. The first time GNM runs on a new scene, it will make mistakes. In Isaac Sim, a navigation error means the simulated robot bumps into a simulated wall. On the real Yahboom robot, a navigation error means physical damage, wheel slip, or a fallen robot.

Simulation also lets us collect data faster than real-world operation. We can run episodes overnight in simulation, then use that data to fine-tune GNM before the first real-robot test.

### Why does safety sit before /cmd_vel?

The `/cmd_vel` topic is the final command that moves the robot wheels. Any node that publishes to `/cmd_vel` directly controls the robot.

FleetSafe sits in the path between GNM and `/cmd_vel` so that GNM's raw command is checked before it reaches the wheels. If GNM produces a command that would cause a collision, FleetSafe replaces it with a safe alternative (typically a reduced speed or a stop). The robot never sees the unsafe command.

This design means FleetSafe works with any navigation policy, not just GNM. You can swap GNM for a different model and FleetSafe continues to protect the robot.

---

## System architecture

```
Isaac camera / robot sensors
          ↓
     ROS 2 topics
          ↓
  GNM reads camera / goal
          ↓
   GNM produces raw command
          ↓
   FleetSafe checks command
          ↓
  safe command goes to robot
          ↓
     Isaac robot moves
```

### Command path through ROS 2 topics

```
GNM raw command
      ↓
/gnm/cmd_vel_raw
      ↓
FleetSafe CBF-QP shield
      ↓
/fleetsafe/cmd_vel_safe
      ↓
/cmd_vel
      ↓
Isaac robot
```

---

## Required ROS 2 topics

| Topic | Type | Publisher | Subscriber |
|---|---|---|---|
| `/camera/image_raw` | `sensor_msgs/Image` | Isaac bridge | GNM node |
| `/odom` | `nav_msgs/Odometry` | Isaac bridge | GNM node, FleetSafe node |
| `/tf` | `tf2_msgs/TFMessage` | Isaac bridge, robot state publisher | GNM node, FleetSafe node |
| `/scan` | `sensor_msgs/LaserScan` | Isaac bridge | FleetSafe node |
| `/gnm/cmd_vel_raw` | `geometry_msgs/Twist` | GNM node | FleetSafe node |
| `/fleetsafe/cmd_vel_safe` | `geometry_msgs/Twist` | FleetSafe node | logger |
| `/cmd_vel` | `geometry_msgs/Twist` | FleetSafe node | Isaac robot driver |

---

## Phased implementation plan

### Phase 0 — Environment setup

1. Install ROS 2 (Humble or Jazzy) on Ubuntu 22.04 or 24.04.
2. Install Isaac Sim 4.x with the ROS 2 bridge enabled.
3. Create the `.venv` Python environment: `bash scripts/gnm/bootstrap_demo_env.sh`
4. Activate the isaac conda environment: `conda activate isaac`
5. Verify ROS 2 topics are available: `bash scripts/gnm/check_ros2_topics.sh`

### Phase 1 — Isaac scene setup

1. Open Isaac Sim and load an office scene or a simple flat world.
2. Import or place the Yahboom ROSMASTER M3 Pro robot model (USD or URDF → USD).
3. Enable the ROS 2 bridge in the Isaac Sim extension manager.
4. Verify that the following topics appear: `/camera/image_raw`, `/odom`, `/tf`, `/scan`
5. Run the topic checker: `bash scripts/gnm/check_ros2_topics.sh --strict`

**Expected output at this stage:**
- Isaac scene loads without error.
- Yahboom robot model (or placeholder robot) is visible in the viewport.
- Camera, odom, TF, scan, and cmd_vel topics are visible in `ros2 topic list`.

### Phase 2 — Data collection

1. Start Isaac Sim with the scene and robot running.
2. Run the rosbag collection wrapper:
   ```bash
   bash scripts/gnm/collect_isaac_rosbag_episode.sh episode_001
   ```
3. Drive the robot manually through the scene (or run a random exploration policy).
4. Stop the bag recording when the episode is complete.
5. The bag will be saved to `datasets/gnm_fleetsafe_rosbags/episode_001/`.

**Expected output at this stage:**
- A rosbag2 directory `datasets/gnm_fleetsafe_rosbags/episode_001/` exists.
- An episode metadata JSON file `episode_metadata.json` records the episode details.

### Phase 3 — Data conversion

1. Convert the rosbag episode to GNM dataset format:
   ```bash
   python3 scripts/gnm/convert_rosbag_to_gnm_dataset.py \
     --rosbag-root datasets/gnm_fleetsafe_rosbags \
     --output-root datasets/gnm_fleetsafe_converted \
     --episode-name episode_001
   ```
2. Verify the conversion manifest is created.

**Expected output at this stage:**
- `datasets/gnm_fleetsafe_converted/episode_001/` contains:
  - `context_images/` — numbered PNG frames
  - `goal_image.png` — the goal frame
  - `waypoints.npy` — (dx, dy) waypoint labels
  - `odometry.json` — robot pose at each frame
  - `scan_summary.json` — obstacle proximity summary
  - `success_label.json` — whether the episode reached the goal
- A `conversion_manifest.json` records what was converted.

### Phase 4 — GNM fine-tuning

1. Place a public GNM checkpoint in `checkpoints/gnm_public_or_finetuned.pt`.
   Download from the official GNM release or use the VisualNav Foundation Models repository.
2. Run the fine-tuning wrapper:
   ```bash
   bash scripts/gnm/train_gnm_from_collected_data.sh --dry-run
   ```
   In dry-run mode this writes a training manifest without running GPU training.
3. For actual training, remove `--dry-run` and set `CUDA_VISIBLE_DEVICES` appropriately.

Fine-tuning strategy:
- Default: head tuning only (fast, low GPU memory).
- Optional: LoRA on the GNM encoder (better adaptation, requires more VRAM).
- Do not train from random initialization; always start from the public checkpoint.

**Expected output at this stage:**
- `results/gnm_fleetsafe_v2/training_manifest.json` is created.
- In live mode: a fine-tuned checkpoint appears in `checkpoints/gnm_fleetsafe_finetuned.pt`.

### Phase 5 — Evaluation

1. Run the evaluation wrapper:
   ```bash
   bash scripts/gnm/eval_gnm_vs_fleetsafe.sh --dry-run
   ```
   This compares GNM-only against GNM-plus-FleetSafe and writes results.

**Expected output at this stage:**
- `results/gnm_fleetsafe_v2/eval_results.csv` — per-episode metrics.
- `results/gnm_fleetsafe_v2/eval_summary.md` — Markdown summary table.

Metrics reported:
- `success_rate` — fraction of episodes reaching the goal
- `path_efficiency` — ratio of shortest path length to actual path length
- `navigation_error` — mean final distance to goal in metres
- `collision_rate` — fraction of episodes with at least one collision
- `min_clearance` — minimum obstacle clearance in metres across all steps
- `intervention_count` — number of times FleetSafe overrode GNM's command
- `intervention_magnitude` — mean magnitude of FleetSafe's correction
- `certificate_validity_rate` — fraction of steps where the CBF certificate held

### Phase 6 — Real robot deployment

After simulation evaluation is satisfactory:

1. Deploy the same ROS 2 nodes on the Yahboom ROSMASTER M3 Pro.
2. Replace the Isaac bridge topics with real sensor topics.
3. No code changes are required in the GNM or FleetSafe nodes; only the launch file changes.
4. Start with low maximum velocities and increase gradually.
5. Keep the safety parameters conservative (`min_clearance_m: 0.35`, `max_linear_velocity: 0.25 m/s`).

---

## Nodes in the ROS 2 launch file

The launch file `launch/gnm_fleetsafe_isaac.launch.py` starts four groups of nodes:

1. **Isaac bridge** — the NVIDIA-provided ROS 2 bridge that publishes sensor topics from Isaac Sim.
2. **GNM policy node** — subscribes to `/camera/image_raw`, `/odom`, `/tf`, and a goal topic; publishes to `/gnm/cmd_vel_raw`.
3. **FleetSafe shield node** — subscribes to `/gnm/cmd_vel_raw`, `/scan`, `/odom`, `/tf`; publishes to `/fleetsafe/cmd_vel_safe` and `/cmd_vel`.
4. **Logger / dashboard** (optional) — subscribes to all topics and records a structured log for post-hoc analysis.

---

## Configuration

All parameters are in `configs/gnm_fleetsafe_isaac.yaml`. Key parameters:

- `gnm.checkpoint` — path to the GNM checkpoint file.
- `gnm.fine_tuning_mode` — `head_or_lora` selects between head-only and LoRA fine-tuning.
- `gnm.dry_run` — set to `true` to run scripts without GPU computation.
- `fleetsafe.min_clearance_m` — minimum obstacle clearance the safety shield enforces.
- `fleetsafe.max_linear_velocity` — maximum forward speed the shield allows.
- `data_collection.output_root` — where rosbag episodes are saved.

---

## Dry-run verification commands

These commands complete without ROS 2 or Isaac Sim installed:

```bash
bash scripts/gnm/check_ros2_topics.sh
bash scripts/gnm/collect_isaac_rosbag_episode.sh demo_episode --dry-run
python3 scripts/gnm/convert_rosbag_to_gnm_dataset.py \
  --rosbag-root datasets/gnm_fleetsafe_rosbags \
  --output-root datasets/gnm_fleetsafe_converted \
  --episode-name demo_episode --dry-run
bash scripts/gnm/train_gnm_from_collected_data.sh --dry-run
bash scripts/gnm/eval_gnm_vs_fleetsafe.sh --dry-run
```

---

## Next live implementation steps

1. Install ROS 2 Humble or Jazzy on the workstation.
2. Build the Isaac ROS 2 bridge workspace.
3. Import the Yahboom M3 Pro URDF into Isaac Sim and convert to USD.
4. Record real Isaac Sim episodes and convert them to GNM format.
5. Fine-tune GNM on the Isaac Sim data.
6. Run the GNM-only vs GNM-plus-FleetSafe evaluation in simulation.
7. Deploy on the real Yahboom robot with conservative safety parameters.
