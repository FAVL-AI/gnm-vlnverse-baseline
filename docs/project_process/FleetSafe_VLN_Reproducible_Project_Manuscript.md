# FleetSafe SafeVLA/VLN Reproducible Project Process Manuscript

**Project:** FleetSafe VisualNav Benchmark  
**Focus:** Voice-, text-, and camera-conditioned embodied Vision-and-Language Navigation with mathematically checked safety certificates  
**Evidence commit:** `8bef749`  
**Prepared:** 2026-05-27  
**Voice:** first-person academic project walkthrough

---

## Plain-English Summary

I built this project so that my robot is not just a path follower. I wanted it to behave like a real embodied Vision-and-Language Navigation robot: it should receive language through text or voice, use the camera and range sensors to understand the physical scene, ask a nominal visual navigation backbone for a proposed motion, and then pass that proposed motion through a safety layer before anything reaches the robot base.

The key research decision was this: **I do not trust the learned navigation model as the safety controller.** General Navigation Model (GNM), Visual Navigation Transformer (ViNT), and NoMaD are treated as nominal policies. They propose useful navigation behavior. The final authority is a Control Barrier Function Quadratic Program, abbreviated CBF-QP, that checks clearance, latency, finite commands, feasibility, and the safety margin at every instruction and timestep. This lets me combine state-of-the-art navigation with mathematical safety checking.

The project now has evidence that the robot can process a voice-conditioned command, use camera and LiDAR context, create a nominal velocity, filter it through safety, and write a JSON Lines certificate proving the safety decision for that instruction. The committed evidence package is `results/demo_evidence_voice_vln_real_robot/`, and the commit is `8bef749`.

---

## Chapter 1 — What I Was Trying to Prove

### What

I was trying to prove that FleetSafe is a serious embodied Vision-and-Language Navigation system rather than a simple “go to waypoint” robot. The robot must accept language, use visual input, reason through a navigation backbone, and still remain safe when the environment is tight or uncertain.

### Why

A basic path finder can move from point A to point B, but Vision-and-Language Navigation (VLN) is broader. VLN requires an embodied agent to interpret language such as “move forward slowly while avoiding nearby obstacles,” ground that language in the observed scene, and produce actions that respect task constraints [1]. In my project, this matters because the M3Pro robot already has real sensors and voice capability. I wanted to use those features as research advantages, not as cosmetic add-ons.

### Where

The architecture is split across two machines:

- **Jetson Orin NX on the Yahboom ROSMASTER M3Pro:** publishes robot sensors and accepts motion commands.
- **RTX desktop:** runs the heavier FleetSafe-VLN controller, logging, evidence generation, and future high-capacity model inference.

This split is deliberate. The Jetson handles embodied sensing and actuation. The RTX desktop handles reasoning, evaluation, and certificate generation.

### Who

I acted as the system integrator and researcher. The robot platform, ROS 2 graph, model backbones, safety filter, debugging scripts, and evidence logging were assembled into one reproducible pipeline.

### How

I implemented a controller that subscribes to:

- `/fleetsafe/instruction_text` for typed language instructions.
- `/fleetsafe/instruction_voice` for voice transcripts.
- `/camera/color/image_raw` for RGB camera frames.
- `/scan0` and `/scan1` for front/rear or dual LiDAR range data.
- `/odom_raw` for robot odometry.

It publishes:

- `/fleetsafe/vln/parsed_instruction` as grounded language JSON.
- `/fleetsafe/vln/subgoal` as the chosen navigation subgoal.
- `/fleetsafe/cmd_vel_nominal` as the nominal command before safety filtering.
- `/cmd_vel` as the final safe command, or zero in dry-run mode.
- `/fleetsafe/certificate` as the runtime safety certificate.

---

## Chapter 2 — Why This Is Not Just Path Planning

Path planning normally starts with a geometric start and goal. My project starts with language, sensors, and uncertainty. A command can come from text or speech. The system must parse that command, decide what it means, connect it to the current scene, and then move safely.

A path planner asks: **Where should I go?**  
A full embodied VLN robot asks: **What did the human mean, what do I see, what is safe, and what action should I take now?**

This distinction matters academically. The Room-to-Room benchmark helped define visually grounded navigation from natural language instructions [1]. Embodied AI platforms such as Habitat made it clear that navigation research is not only about maps but about agents acting from sensor observations [2]. In my system, I preserve that embodied structure by connecting language, camera, LiDAR, odometry, backbones, and certificates in one live ROS 2 graph.

---

## Chapter 3 — Full System Architecture

### Hardware

- Yahboom ROSMASTER M3Pro mobile robot.
- Jetson Orin NX onboard computer.
- Dabai/Orbbec RGB camera publishing `/camera/color/image_raw`.
- Two Tmini LiDAR scanners publishing `/scan0` and `/scan1`.
- Robot base receiving `/cmd_vel`.
- RTX desktop for heavy reasoning and evaluation.

### Software

- Ubuntu 22.04.
- ROS 2 Humble.
- Python 3 system interpreter at `/usr/bin/python3`.
- FleetSafe repository at `~/robotics/FleetSafe-VisualNav-Benchmark`.
- Makefile targets for repeatable operation.
- JSONL logs for certificates and traces.

### Architecture diagram in words

```text
Human voice/text
      │
      ▼
Instruction intake: /fleetsafe/instruction_voice or /fleetsafe/instruction_text
      │
      ▼
Language grounding: action, landmark, speed, avoid constraints, confidence
      │
      ▼
Backbone router: GNM / ViNT / NoMaD as nominal visual navigation models
      │
      ▼
u_nom = nominal command proposed by the navigation model
      │
      ▼
CBF-QP safety filter: checks LiDAR clearance, actuator limits, latency, feasibility
      │
      ▼
u_safe = closest safe command
      │
      ├──► /cmd_vel in live mode
      ├──► zero command in dry-run mode
      ├──► /fleetsafe/certificate
      └──► JSONL trace and certificate files
```

---

## Chapter 4 — The Algorithm, Step by Step

### Algorithm 1: Safe voice/text/image VLN controller

```text
Input:
  language instruction from text or voice
  latest RGB camera frame
  latest LiDAR scans scan0 and scan1
  latest odometry

Output:
  safe robot command u_safe
  parsed language record
  safety certificate
  trace evidence

1. Receive instruction on /fleetsafe/instruction_text or /fleetsafe/instruction_voice.
2. Assign an instruction_id so the command can be traced.
3. Parse the language into:
     action_type, target label, speed modifier, avoid constraints, confidence.
4. Check whether recent camera data has been received.
5. Read LiDAR scans and sanitize invalid dead-zone beams.
6. Compute effective clearance using the conservative fifth percentile.
7. Route the task to a nominal backbone: GNM, ViNT, NoMaD, or auto.
8. Produce u_nom = [linear_velocity, angular_velocity].
9. Solve the CBF-QP safety filter.
10. If the filter is feasible, compute u_safe.
11. If the filter is infeasible, set u_safe = [0, 0] and latch emergency stop.
12. Publish parsed instruction, nominal command, subgoal, and certificate.
13. Write JSONL trace and certificate to disk with immediate flushing.
14. In dry-run mode, do not move the robot, but still log the command that would have been safe.
```

The important research design is that logging happens for every outcome: success, dry-run, stale LiDAR, low confidence, CBF infeasibility, exception, or e-stop. This prevents hidden black-box failure paths.

---

## Chapter 5 — Mathematical Safety Layer

### The safety set

Let `x` be the robot state. Let `d_i(x)` be the distance from the robot to obstacle `i`. Let `d_safe` be the minimum allowed safety radius. I define a barrier function:

```text
h_i(x) = d_i(x) - d_safe
```

If `h_i(x) >= 0`, the robot is outside the forbidden zone around obstacle `i`. If `h_i(x) < 0`, the robot is too close. The safe set is:

```text
C = { x | h_i(x) >= 0 for every obstacle i }
```

### The CBF condition

The Control Barrier Function condition is:

```text
dh_i/dt + alpha * h_i >= 0
```

where:

- `dh_i/dt` means the time derivative of the barrier function.
- `alpha` is a positive constant that controls how aggressively the robot must move away from the boundary.
- `h_i >= 0` means the robot remains in the safe set.

By the comparison lemma, if the robot starts in the safe set and the CBF inequality is enforced continuously or at sufficiently fast discrete timesteps under bounded sensing latency, then the robot remains in the safe set [6].

### The Quadratic Program

The nominal model proposes `u_nom`. The safety filter solves:

```text
minimize over u:  ||u - u_nom||²
subject to:       dh_i/dt + alpha h_i >= 0 for every obstacle i
                  actuator lower bounds <= u <= actuator upper bounds
                  finite command values
```

The result is `u_safe`, the closest safe command to the model proposal. This is why I can use GNM, ViNT, and NoMaD without pretending they are formal safety controllers.

---

## Chapter 6 — Nominal Backbones and Their Roles

| Model | Expanded name | Role in this project | Safety authority? |
|---|---|---|---|
| GNM | General Navigation Model | Provides general visual-navigation behavior across robot embodiments [3] | No |
| ViNT | Visual Navigation Transformer | Provides transformer-based visual navigation features and subgoal behavior [4] | No |
| NoMaD | Goal-Masked Diffusion policy for navigation | Provides diffusion-style nominal navigation and exploration behavior [5] | No |
| CBF-QP | Control Barrier Function Quadratic Program | Converts nominal command into a formally checked safe command [6] | Yes, under assumptions |

This separation is central to the project. The learned models provide capability. The CBF-QP provides the formal safety contract.

---

## Chapter 7 — What We Built in the Repository

The project evolved into a full workflow rather than a one-off script. The main components are:

- `scripts/real_robot/run_vln_m3pro.py`: ROS 2 controller for text, voice, camera, LiDAR, odometry, nominal navigation, CBF safety, and evidence logging.
- `fleet_safe_vla/safety/lidar_sanitizer.py`: auditable LiDAR filtering for dead-zone artifacts and effective clearance.
- `scripts/live/inspect_lidar_clearance.py`: standalone live LiDAR inspector.
- `scripts/live/check_vln_stack.sh`: stack health checker for ROS domain, topics, subscriptions, and LiDAR safety status.
- `scripts/live/run_vln_desktop.sh`: reproducible RTX desktop launch wrapper.
- `scripts/live/send_vln_instruction.sh`: standard text instruction publisher.
- `scripts/live/watch_vln_outputs.sh`: parsed, nominal, and certificate watchers.
- `docs/REAL_ROBOT_VLN_OPERATION.md`: operation manual for the real robot.
- `results/demo_evidence_voice_vln_real_robot/`: committed voice-conditioned real-robot evidence.

---

## Chapter 8 — Reproducible Runbook

This is the exact day-to-day process I used.

### Set ROS domain

```bash
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=30
export ROS_LOCALHOST_ONLY=0
```

**Expected outcome:** All ROS terminals use the same domain and can discover each other.
### Start robot stack on Jetson

```bash
source /opt/ros/humble/setup.bash
source ~/yahboomcar_ws/install/setup.bash
source ~/mircoROS_agent/install/setup.bash 2>/dev/null || true
export ROS_DOMAIN_ID=30
export ROS_LOCALHOST_ONLY=0
```

**Expected outcome:** /YB_Node and robot sensor topics appear.
### Start controller on RTX desktop

```bash
cd ~/robotics/FleetSafe-VisualNav-Benchmark
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=30
export ROS_LOCALHOST_ONLY=0
make vln-desktop-radius RADIUS=0.20
```

**Expected outcome:** FleetSafe-VLN controller runs in dry-run mode.
### Check stack

```bash
SAFETY_RADIUS=0.20 make vln-check-stack
```

**Expected outcome:** Reports ROS, robot topics, FleetSafe topics, and LiDAR clearance.
### Inspect LiDAR

```bash
SAFETY_RADIUS=0.20 make vln-lidar-inspect
```

**Expected outcome:** Prints raw vs valid vs fifth-percentile clearance and CBF decision.
### Send text instruction

```bash
make vln-send TEXT="move forward slowly and keep at least half a meter from obstacles"
```

**Expected outcome:** Publishes a text instruction to /fleetsafe/instruction_text.
### Send voice transcript

```bash
ros2 topic pub --once /fleetsafe/instruction_voice std_msgs/msg/String "{data: 'move forward slowly while avoiding nearby obstacles'}"
```

**Expected outcome:** Publishes a spoken-command transcript to /fleetsafe/instruction_voice.
### Watch parsed instruction

```bash
make vln-watch-parsed
```

**Expected outcome:** Echoes GroundedGoal JSON.
### Watch nominal command

```bash
make vln-watch-nominal
```

**Expected outcome:** Echoes nominal velocity command before CBF filtering.
### Watch certificate

```bash
make vln-watch-cert
```

**Expected outcome:** Echoes the certificate JSON showing h_min, min_dist_m, qp_status, and safety decision.
### Validate latest certificate

```bash
LATEST_CERT="$(ls -td results/certificates/* | head -1)"
tail -n 1 "$LATEST_CERT"/vln_certificates_m3pro.jsonl | python3 -m json.tool
```

**Expected outcome:** Pretty-prints the latest safety certificate.
### Package evidence

```bash
mkdir -p results/demo_evidence_voice_vln_real_robot
cp "$LATEST_CERT"/vln_certificates_m3pro.jsonl results/demo_evidence_voice_vln_real_robot/
```

**Expected outcome:** Creates a compact evidence folder for reproducibility.


---

## Chapter 9 — Full Issue and Debugging Log

This chapter records the major problems one by one. I include what happened, why it mattered, the fix, the command or code path used, and how I verified that the fix worked.

### ISS-001: ROS 2 Python package rclpy was not found when launching run_vln_m3pro.py

- **When:** Early real-robot bring-up
- **Where:** RTX desktop terminal
- **Why it happened:** The controller was launched inside the conda base environment, which did not include the ROS 2 Humble Python site packages.
- **How I fixed it:** I deactivated conda and launched with /usr/bin/python3 after sourcing /opt/ros/humble/setup.bash.
- **Command or code used:**

```bash
conda deactivate 2>/dev/null || true; source /opt/ros/humble/setup.bash; /usr/bin/python3 scripts/real_robot/run_vln_m3pro.py --backbone auto --safety-radius 0.50 --trace-dir results/vln_runs --cert-dir results/certificates
```

- **Validation outcome:** The banner changed from ROS2: NOT FOUND to ROS2: available, and the FleetSafe-VLN node reported ready.
### ISS-002: git pull, make help, and run_vln_m3pro.py failed on the Jetson.

- **When:** Controller launch from wrong machine
- **Where:** Jetson ~/robotics/FleetSafe-VisualNav-Benchmark
- **Why it happened:** The Jetson directory existed but was not a real git clone and did not contain the new scripts.
- **How I fixed it:** I treated the RTX desktop as the controller host and the Jetson as the sensing/action host, then documented rsync as the later Jetson synchronization method.
- **Command or code used:**

```bash
rsync -av --exclude data/real_robot_bags --exclude logs ~/robotics/FleetSafe-VisualNav-Benchmark/ jetson@172.20.10.14:~/robotics/FleetSafe-VisualNav-Benchmark/
```

- **Validation outcome:** The desktop could see /scan0, /scan1, /odom_raw, /camera/color/image_raw, and the /fleetsafe/* topics over ROS_DOMAIN_ID=30.
### ISS-003: Publishing to /fleetsafe/instruction_text waited forever for a subscription.

- **When:** First topic publication test
- **Where:** ROS 2 graph
- **Why it happened:** The controller was either not running, running in another domain, or stopped by earlier errors.
- **How I fixed it:** I verified the subscription using ros2 topic info and then relaunched the controller in a clean terminal.
- **Command or code used:**

```bash
ros2 topic info /fleetsafe/instruction_text -v
```

- **Validation outcome:** Subscription count became 1 and the node name fleetsafe_vln_controller appeared.
### ISS-004: make vln-robot and make vln-robot-live initially did not exist locally.

- **When:** Make target rollout
- **Where:** Makefile help section
- **Why it happened:** The local repository had not pulled the commit that added the VLN targets, and the help text did not expose all targets.
- **How I fixed it:** I pulled the repository, added a VLN section to make help, and verified the help output.
- **Command or code used:**

```bash
git pull --ff-only origin main; make help | grep -A 35 "VLN"
```

- **Validation outcome:** The help output listed vln-desktop, vln-desktop-radius, vln-send, watchers, and audits.
### ISS-005: No /scan0, /scan1, /odom_raw, or /camera topics appeared at first.

- **When:** Sensor discovery
- **Where:** Jetson ROS 2 environment
- **Why it happened:** The Yahboom stack and ROS 2 workspaces were not sourced in the active shell.
- **How I fixed it:** I sourced the Yahboom workspace and confirmed /YB_Node plus sensor topics.
- **Command or code used:**

```bash
source /opt/ros/humble/setup.bash; source ~/yahboomcar_ws/install/setup.bash; export ROS_DOMAIN_ID=30; ros2 node list; ros2 topic list -t | grep -Ei "cmd_vel|odom|imu|scan|camera|image|depth"
```

- **Validation outcome:** /YB_Node, /cmd_vel, /odom_raw, /scan0, /scan1, and later /camera/color/image_raw appeared.
### ISS-006: The CBF layer latched e-stop with reason cbf_infeasible.

- **When:** Safety dry-run
- **Where:** Controller logs
- **Why it happened:** The LiDAR reported obstacles or effective clearance below the configured safety radius. This was a correct safety behavior.
- **How I fixed it:** I moved the robot/obstacles when needed, lowered the dry-run radius only for debugging, and never enabled motion while below the safety radius.
- **Command or code used:**

```bash
SAFETY_RADIUS=0.20 make vln-check-stack; make vln-desktop-radius RADIUS=0.20
```

- **Validation outcome:** When effective clearance rose to about 0.33 m with radius 0.20 m, the certificate showed safe=true and qp_status=optimal.
### ISS-007: The scans contained 0.0 m or 0.05 m readings that made the raw minimum look unsafe.

- **When:** LiDAR raw-data inspection
- **Where:** /scan0 and /scan1
- **Why it happened:** These were dead-zone or invalid beams near the scanner minimum range rather than usable obstacle clearance.
- **How I fixed it:** I added an audited LiDAR sanitizer that discards dead-zone artifacts and uses a conservative fifth-percentile effective clearance.
- **Command or code used:**

```bash
make vln-lidar-inspect; SAFETY_RADIUS=0.20 make vln-check-stack
```

- **Validation outcome:** The inspector printed raw_min, valid_min, p05, invalid count, combined effective clearance, and the CBF decision.
### ISS-008: Some early runs produced empty certificate and trace JSONL files.

- **When:** Evidence verification
- **Where:** results/certificates and results/vln_runs
- **Why it happened:** The controller returned early on e-stop or infeasible paths before writing evidence.
- **How I fixed it:** I changed the controller so every instruction goes through a single evidence-emission path before any return.
- **Command or code used:**

```bash
LATEST_CERT="$(ls -td results/certificates/* | head -1)"; tail -n 1 "$LATEST_CERT"/vln_certificates_m3pro.jsonl | python3 -m json.tool
```

- **Validation outcome:** Every instruction now creates a [VLN-EVIDENCE] console line plus non-empty JSONL certificate and trace records.
### ISS-009: make failed with missing separator.

- **When:** Makefile debugging
- **Where:** Makefile line around the VLN help section
- **Why it happened:** A quoted echo line was broken across lines without a proper tab-prefixed Makefile recipe line.
- **How I fixed it:** I rewrote the affected help line so each @echo is complete and tab-indented.
- **Command or code used:**

```bash
nl -ba Makefile | sed -n "726,740p"; make -n vln-lidar-inspect
```

- **Validation outcome:** make help and make -n vln-lidar-inspect executed again.
### ISS-010: The LiDAR inspector launched as /usr/bin//usr/bin/python3 and failed.

- **When:** Interpreter path patch
- **Where:** Makefile and live scripts
- **Why it happened:** A replacement script accidentally replaced python3 twice.
- **How I fixed it:** I normalized interpreter calls to exactly /usr/bin/python3.
- **Command or code used:**

```bash
grep -R "/usr/bin//usr/bin/python3" -n Makefile scripts/live || true; make -n vln-lidar-inspect
```

- **Validation outcome:** The dry-run target printed /usr/bin/python3 scripts/live/inspect_lidar_clearance.py.
### ISS-011: The camera topic existed but initially had no publisher or no live frame rate.

- **When:** Camera bring-up
- **Where:** /camera/color/image_raw
- **Why it happened:** The Orbbec/Dabai camera launch was not active yet, and ROS topic tools on this ROS version did not accept the attempted --qos-profile argument.
- **How I fixed it:** I launched the camera stack on the Jetson and verified publisher count and frame rate using the available ros2 topic hz command.
- **Command or code used:**

```bash
ros2 node list | grep -Ei "camera|orbbec"; ros2 topic info /camera/color/image_raw -v; timeout 10s ros2 topic hz /camera/color/image_raw
```

- **Validation outcome:** The camera publisher appeared, the controller logged first camera frame received, and certificates showed camera_seen=true.
### ISS-012: I needed to prove voice is a first-class input path, not only text.

- **When:** Voice input validation
- **Where:** /fleetsafe/instruction_voice
- **Why it happened:** A serious VLN robot must accept natural spoken instructions when the platform has a voice module.
- **How I fixed it:** I published a voice transcript to /fleetsafe/instruction_voice and recorded the resulting trace/certificate.
- **Command or code used:**

```bash
ros2 topic pub --once /fleetsafe/instruction_voice std_msgs/msg/String "{data: 'move forward slowly while avoiding nearby obstacles'}"
```

- **Validation outcome:** The certificate source field became voice, camera_seen=true, qp_status=optimal, and the trace included raw_instruction plus grounded avoid=obstacles.
### ISS-013: Watchers reported that topics did not exist.

- **When:** Topic watchers
- **Where:** make vln-watch-parsed, vln-watch-nominal, vln-watch-cert
- **Why it happened:** ROS 2 topics are not visible until the controller is running and, for some outputs, until an instruction has been processed.
- **How I fixed it:** I kept the controller terminal open and sent a test instruction before expecting latched-like data.
- **Command or code used:**

```bash
make vln-desktop-radius RADIUS=0.20; make vln-send TEXT="move forward slowly"; make vln-watch-cert
```

- **Validation outcome:** Parsed instruction, nominal Twist, and certificate JSON were printed by watcher targets.
### ISS-014: The checker displayed radius 0.30 m while the controller was launched with radius 0.20 m.

- **When:** Safety radius alignment
- **Where:** check_vln_stack.sh and Makefile
- **Why it happened:** The checker used a default rather than respecting the SAFETY_RADIUS environment variable.
- **How I fixed it:** I changed the target to pass SAFETY_RADIUS=${SAFETY_RADIUS:-default}.
- **Command or code used:**

```bash
SAFETY_RADIUS=0.20 make vln-check-stack
```

- **Validation outcome:** The health check header displayed Safety radius: 0.20 m.
### ISS-015: Many raw run directories appeared as untracked files.

- **When:** Repository hygiene
- **Where:** Git history and evidence directory
- **Why it happened:** Each dry-run creates timestamped results. Most are ephemeral evidence, not all should be committed.
- **How I fixed it:** I selected one clean evidence package and committed only results/demo_evidence_voice_vln_real_robot.
- **Command or code used:**

```bash
git add results/demo_evidence_voice_vln_real_robot/; git commit -m "evidence: add voice-conditioned real-robot VLN safety trace"; git push origin main
```

- **Validation outcome:** Commit 8bef749 contains the voice certificate, trace, pretty JSON files, and README.


---

## Chapter 10 — The Final Voice-Conditioned Real-Robot Evidence

The most important committed evidence is in:

```text
results/demo_evidence_voice_vln_real_robot/
```

The voice instruction was:

```text
move forward slowly while avoiding nearby obstacles
```

The committed certificate showed:

```json
{
  "source": "voice",
  "safe": true,
  "qp_status": "optimal",
  "h_min": 0.07155599426651008,
  "min_dist_m": 0.33399999141693115,
  "safety_radius_m": 0.2,
  "u_nominal": [0.06, 0.0],
  "u_safe": [0.04019999742507934, 0.0],
  "cbf_active": true,
  "camera_seen": true,
  "camera_frame_id": "camera_color_optical_frame"
}
```

This proves a complete dry-run chain: voice transcript in, language grounding, camera observed, LiDAR sanitized, nominal command generated, CBF safety checked, command clipped, and certificate written.

I do not claim live motion yet. I claim that the dry-run controller, real robot sensors, voice topic, camera topic, LiDAR safety, and certificate evidence are integrated and reproducible. The next step is live motion after additional clearance, e-stop readiness, and Isaac Sim/digital twin validation.

---

## Chapter 11 — Why the Camera Evidence Matters

At one point, the certificate showed `camera_seen: false`. That would have weakened the VLN claim because the system would have been acting from language and LiDAR but not from live visual evidence. I therefore verified the camera stack separately.

The controller later logged:

```text
[VLN] first camera frame received: width=640, height=480, encoding=rgb8
```

The certificate then showed:

```json
{
  "camera_seen": true,
  "camera_frame_id": "camera_color_optical_frame",
  "camera_last_age_ms": 591.4936065673828
}
```

This matters because a VLN robot must not only accept language; it must couple language to visual perception. The camera evidence is the difference between a voice-commanded robot and a vision-language navigation robot.

---

## Chapter 12 — Why the LiDAR Sanitizer Was Necessary

The raw LiDAR stream often produced zeros or minimum-range artifacts. If I used the raw minimum directly, the robot would always believe it was inside an obstacle. If I ignored the readings completely, I would create an unsafe system.

The compromise was an auditable sanitizer:

1. Keep the raw minimum for transparency.
2. Remove impossible/dead-zone values near the scanner lower bound.
3. Compute a conservative fifth-percentile valid clearance.
4. Put all of this into the certificate under `scan_audit`.

This is not hiding bad data. It is documenting how the data were cleaned. The certificate retains both raw and effective values.

---

## Chapter 13 — Verification Matrix

| Requirement | Evidence | Status |
|---|---|---|
| Text instruction input | `/fleetsafe/instruction_text` subscription and make vln-send | Verified |
| Voice instruction input | `/fleetsafe/instruction_voice` certificate source=voice | Verified |
| Camera input | camera_seen=true and camera_frame_id present | Verified |
| LiDAR input | scan0/scan1 valid_min and effective clearance in scan_audit | Verified |
| Nominal action | u_nominal present | Verified |
| Safety-filtered action | u_safe present and less aggressive than u_nominal | Verified |
| CBF activity | cbf_active=true | Verified |
| Safety certificate | JSONL certificate committed | Verified |
| Trace evidence | JSONL trace committed | Verified |
| No live motion overclaim | decision=dry_run_zero | Verified and honestly bounded |
| Future digital twin path | Isaac Sim plan documented | Planned |
| Future live motion path | e-stop and clearance checklist documented | Planned |

---

## Chapter 14 — Installation and Environment Ledger

### Core installation assumptions

```bash
# ROS 2 Humble environment
source /opt/ros/humble/setup.bash

# Yahboom workspace on Jetson
source ~/yahboomcar_ws/install/setup.bash

# Optional micro-ROS agent workspace
source ~/mircoROS_agent/install/setup.bash 2>/dev/null || true

# ROS discovery settings
export ROS_DOMAIN_ID=30
export ROS_LOCALHOST_ONLY=0
```

### Why `/usr/bin/python3` matters

ROS 2 Humble installs its Python packages into the system Python environment. Conda can hide those packages. Therefore, real ROS 2 launch commands use:

```bash
/usr/bin/python3 scripts/real_robot/run_vln_m3pro.py ...
```

This prevents `rclpy not found` errors.

---

## Chapter 15 — Dataset and Evidence Formats

### JSONL certificate

Each certificate line contains fields such as:

- `timestamp`
- `instruction_id`
- `source`
- `safe`
- `qp_status`
- `h_min`
- `min_dist_m`
- `safety_radius_m`
- `u_nominal`
- `u_safe`
- `cbf_active`
- `dry_run`
- `scan_audit`
- `camera_seen`

### JSONL trace

Each trace line contains fields such as:

- `raw_instruction`
- `parsed_instruction`
- `grounding_candidates`
- `chosen_subgoal`
- `model_name`
- `u_nom`
- `u_safe`
- `qp_status`
- `notes`

### HDF5 dataset schema

The planned dataset format groups multimodal data as:

```text
observations/
  rgb
  depth
  scan0
  scan1
  odom
actions/
  u_nom
  u_safe
  cbf_active
language/
  action_type
  label
  confidence
  constraints
safety/
  h_min
  min_dist_m
  certificate_ids
```

HDF5 is useful here because it can store synchronized arrays and metadata in one structured file [11].

---

## Chapter 16 — Planned Isaac Sim and Digital Twin Proof

The next stage is not to jump directly into live motion. I will replay the same architecture in Isaac Sim or a digital twin environment. Isaac Sim supports ROS 2 workflows and robot simulation integration [10].

The digital twin validation plan is:

1. Build or import the M3Pro-like robot body.
2. Add a simulated RGB camera and LiDAR.
3. Publish simulated `/scan0`, `/scan1`, `/odom_raw`, and camera topics.
4. Run the same FleetSafe-VLN controller from the RTX desktop.
5. Compare real dry-run certificates with simulated motion certificates.
6. Test hazard cases that should trigger e-stop.
7. Test open-space cases that should allow safe motion.
8. Only after that, enable live motion on the real robot.

This matters because simulation can test failure modes without risking hardware.

---

## Chapter 17 — Benchmark Plan for SOTA Claims

I will not claim state of the art only because the robot moves. The evaluation must separate navigation utility from safety compliance.

### Navigation metrics

- Success rate.
- Path length.
- Time to goal.
- Success weighted by path length.
- Recovery after ambiguity.
- Language grounding accuracy.
- Voice transcript robustness.

### Safety metrics

- Collision count.
- Minimum distance to obstacle.
- Minimum barrier value `h_min`.
- CBF intervention rate.
- QP infeasibility rate.
- E-stop rate.
- Sensor latency.
- Camera freshness.

### Ablations

1. GNM only.
2. ViNT only.
3. NoMaD only.
4. GNM + CBF-QP.
5. ViNT + CBF-QP.
6. NoMaD + CBF-QP.
7. Text-only instructions.
8. Voice transcript instructions.
9. Voice + camera + LiDAR certificates.

This will allow me to defend which part of the system improves navigation and which part proves safety.

---

## Chapter 18 — Acronyms and Symbols

| Acronym/Symbol | Expanded form | Meaning |
|---|---|---|
| ASR | Automatic Speech Recognition | Converts human speech into text/transcripts. |
| CBF | Control Barrier Function | A mathematical function used to keep the robot inside a safe set. |
| QP | Quadratic Program | An optimization problem used to find the closest safe command to the nominal command. |
| VLN | Vision-and-Language Navigation | Navigation where a robot follows natural-language instructions using visual perception. |
| VLA | Vision-Language-Action | A system that maps perception and language into robot actions. |
| LiDAR | Light Detection and Ranging | A range sensor that measures distances using laser scanning. |
| ROS | Robot Operating System | Middleware for robot software components. |
| QoS | Quality of Service | ROS 2 communication policy settings such as reliability and durability. |
| JSONL | JavaScript Object Notation Lines | One JSON record per line, useful for append-only logs. |
| HDF5 | Hierarchical Data Format 5 | Structured file format for large multimodal datasets. |
| u_nom | Nominal control command | The command proposed by the navigation backbone before safety filtering. |
| u_safe | Safe control command | The command after the safety filter has applied constraints. |
| h(x) | Barrier value | A safety margin. If h(x) is non-negative, the robot is inside the safe set. |
| d_safe | Safety radius | Minimum allowed clearance around the robot. |
| h_min | Minimum barrier margin | Smallest safety margin over all obstacles at a timestep. |

---

## Chapter 19 — Framework and Artifact Index

| Framework/Artifact | Expanded description | Role | Example location |
|---|---|---|---|
| ROS 2 | Robot Operating System 2 middleware | Nodes, topics, publishers, subscribers, Quality of Service | /scan0, /scan1, /odom_raw, /cmd_vel, /fleetsafe/* |
| rclpy | ROS 2 Python client library | Controller node implementation | scripts/real_robot/run_vln_m3pro.py |
| micro-ROS | ROS 2 support for microcontrollers | Bridge between embedded robot controller and ROS 2 graph | ~/mircoROS_agent/install/setup.bash |
| Yahboom ROSMASTER M3Pro | Real robot platform | Embodied sensor/action platform | Jetson Orin NX, Tmini LiDAR pair, Dabai camera |
| GNM | General Navigation Model | Nominal visual navigation backbone | Used as one candidate policy, not as safety authority |
| ViNT | Visual Navigation Transformer | Foundation visual navigation backbone | Used as a nominal model candidate |
| NoMaD | Goal-Masked Diffusion navigation model | Diffusion-style nominal navigation backbone | Used as a nominal model candidate |
| CBF-QP | Control Barrier Function Quadratic Program | Safety filter that clips nominal actions | u_nom -> u_safe |
| JSONL | JavaScript Object Notation Lines | Append-only trace and certificate evidence | vln_trace_m3pro.jsonl, vln_certificates_m3pro.jsonl |
| HDF5 | Hierarchical Data Format version 5 | Dataset format for multimodal episodes | observations/actions/language/safety groups |
| Isaac Sim | NVIDIA robotics simulation platform | Planned digital twin validation | Future simulation proof before live motion |

---

## Chapter 20 — Code Snippets That Capture the Main Fixes

### Launching with the correct Python interpreter

```bash
conda deactivate 2>/dev/null || true
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=30
export ROS_LOCALHOST_ONLY=0
/usr/bin/python3 scripts/real_robot/run_vln_m3pro.py \
  --backbone auto \
  --safety-radius 0.20 \
  --trace-dir results/vln_runs \
  --cert-dir results/certificates
```

### Checking the instruction subscription

```bash
ros2 topic info /fleetsafe/instruction_voice -v
```

Expected output includes:

```text
Subscription count: 1
Node name: fleetsafe_vln_controller
```

### Sending a voice transcript

```bash
ros2 topic pub --once /fleetsafe/instruction_voice std_msgs/msg/String \
"{data: 'move forward slowly while avoiding nearby obstacles'}"
```

### Validating the latest certificate

```bash
LATEST_CERT="$(ls -td results/certificates/* | head -1)"
tail -n 1 "$LATEST_CERT"/vln_certificates_m3pro.jsonl | python3 -m json.tool
```

### Copying the evidence package

```bash
LATEST_CERT="$(ls -td results/certificates/* | head -1)"
LATEST_TRACE="$(ls -td results/vln_runs/* | head -1)"
mkdir -p results/demo_evidence_voice_vln_real_robot
cp "$LATEST_CERT"/vln_certificates_m3pro.jsonl results/demo_evidence_voice_vln_real_robot/
cp "$LATEST_TRACE"/vln_trace_m3pro.jsonl results/demo_evidence_voice_vln_real_robot/
tail -n 1 "$LATEST_CERT"/vln_certificates_m3pro.jsonl | python3 -m json.tool > results/demo_evidence_voice_vln_real_robot/latest_voice_certificate_pretty.json
tail -n 1 "$LATEST_TRACE"/vln_trace_m3pro.jsonl | python3 -m json.tool > results/demo_evidence_voice_vln_real_robot/latest_voice_trace_pretty.json
```

---

## Chapter 21 — Honest Current Project Status

### Completed

- Real robot ROS 2 topics discovered.
- RTX desktop controller architecture established.
- Text instruction path verified.
- Voice transcript path verified.
- Camera reception verified.
- LiDAR sanitization and safety checking verified.
- CBF-QP certificate evidence verified.
- Voice-conditioned real-robot dry-run evidence committed.

### Not yet claimed

- I have not yet claimed final live-motion success.
- I have not yet claimed Isaac Sim digital twin proof.
- I have not yet claimed GNM/ViNT/NoMaD trained-from-scratch performance.
- I have not yet claimed the learned model alone is safe.

### Next steps

1. Stabilize camera frame rate.
2. Run Isaac Sim digital twin tests.
3. Run controlled live motion with physical e-stop and open clearance.
4. Record rosbag evidence.
5. Compare GNM, ViNT, and NoMaD under identical safety filters.
6. Produce final benchmark tables.

---


---

## Chapter 23 — Chronological Build Diary

This chapter records the project as a chronological story. I include it because a reproducible research project is not only a final codebase. It is a sequence of decisions under uncertainty.

### Phase 1: I separated the robot from the reasoning computer

At the beginning, it was tempting to run everything on the Jetson. That would have made the system look self-contained, but it was not the best research architecture for this stage. The Jetson already had a critical job: publish robot sensors, run the base stack, expose `/cmd_vel`, and keep the real robot connected. The RTX desktop had more compute, a full repository, a clean development environment, and enough capacity for heavier model inference and certificate logging. I therefore made the explicit decision that the Jetson would be the embodied sensor/action endpoint and the RTX desktop would be the reasoning and evaluation endpoint.

This decision mattered because it reduced moving parts. Instead of debugging missing repository files on the Jetson and ROS 2 Python problems at the same time, I kept the controller on the machine where the repository was correct. The Jetson was then tested only for the topics it must provide: scans, odometry, camera, and base command input.

### Phase 2: I made ROS 2 discovery explicit

The next problem was ROS 2 discovery. A ROS 2 graph only works if machines share the same domain and networking assumptions. I standardized every terminal with:

```bash
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=30
export ROS_LOCALHOST_ONLY=0
```

This looks simple, but it is one of the most important reproducibility steps. Without it, a topic can exist on one machine but be invisible to another. For a student building this project, this is like making sure everyone is using the same radio channel before they try to talk.

### Phase 3: I proved sensors before I trusted control

Before sending commands, I verified the robot topics. I checked `/scan0`, `/scan1`, `/odom_raw`, `/imu/data_raw`, and `/camera/color/image_raw`. I did not assume the robot was ready because a terminal said the stack had started. I used `ros2 topic list`, `ros2 node list`, and `ros2 topic hz`.

This mattered because the controller can only be as reliable as its freshest sensor inputs. If the LiDAR is stale, the safe action is zero. If the camera is missing, the project cannot honestly claim visual grounding for that instruction. If odometry is missing, later closed-loop navigation benchmarks become weaker.

### Phase 4: I treated CBF infeasibility as evidence, not failure

When the controller first reported `cbf_infeasible`, the natural reaction would be to think the code had failed. Instead, I inspected the LiDAR. The robot was near an obstacle. With a 0.30 m or 0.50 m radius, a scanner reading around 0.28 m is exactly the situation in which the safety layer should stop. This was a key intellectual turning point. I stopped treating every e-stop as a bug and started classifying e-stops into legitimate safety blocks versus software faults.

This is why the project is safety-first. The robot is not being forced to move for a demo. The certificate must agree that motion is safe.

### Phase 5: I converted debugging into reusable Make targets

The repeated shell commands became a risk. If I had to remember every `source`, every environment variable, every watcher, and every evidence command, the project would not be reproducible. I therefore converted the workflow into Makefile targets such as:

```bash
make vln-desktop-radius RADIUS=0.20
make vln-check-stack
make vln-watch-cert
make vln-send TEXT="move forward slowly"
make vln-lidar-inspect
```

The Makefile became a research instrument. It encodes the procedure so that another person can repeat the experiment without reconstructing my terminal history.

### Phase 6: I fixed evidence logging as a first-class requirement

When the trace and certificate files were empty, the problem was serious. A safety project without evidence is only a demonstration. I changed the controller so that every instruction produces trace and certificate records even when the result is an e-stop, stale sensor failure, low-confidence parse, exception, infeasible CBF, or dry-run zero decision.

The console line `[VLN-EVIDENCE]` became my live confirmation that the scientific record had been written. The JSONL files became the durable proof.

### Phase 7: I proved voice, camera, LiDAR, and CBF in one record

The strongest current evidence is the voice-conditioned certificate. It shows:

- `source: voice`
- `safe: true`
- `qp_status: optimal`
- `camera_seen: true`
- `scan_audit` present
- `u_nominal` and `u_safe` both recorded
- `dry_run: true`

This is the correct current boundary. It is not live motion yet. It is a rigorous proof that the real robot sensing stack, voice input path, visual input path, LiDAR safety logic, nominal command, and CBF safety certificate can work together.

---

## Chapter 24 — Explanation for a 14-Year-Old Builder

Imagine the robot as a careful student crossing a busy room.

The **language system** is the student listening to instructions: “move forward slowly while avoiding nearby obstacles.” The robot first turns that sentence into simpler ideas: move forward, go slowly, watch for obstacles.

The **camera** is the robot’s eyes. It tells the robot that the visual system is alive and seeing frames.

The **LiDAR** is like a measuring tape that spins around and checks how close things are. If something is too close, the robot should not move forward just because the language said “move.”

The **nominal model** is the confident friend who says, “I think we should move forward at this speed.” In this project that friend can be GNM, ViNT, or NoMaD.

The **safety filter** is the responsible adult. It says, “That speed is useful, but only if it keeps us far enough from obstacles.” If the proposed speed is too risky, the safety filter slows it down or stops it.

The **certificate** is the receipt. It proves what happened: what the robot heard, what it saw, how close obstacles were, what speed the model wanted, what speed the safety layer allowed, and whether the decision was safe.

This is why the project is powerful. It does not only make the robot move. It explains why the robot was allowed or not allowed to move.

---

## Chapter 25 — Who, What, Why, Where, When, and How Matrix

| Question | Project answer |
|---|---|
| Who built and integrated the workflow? | I did, using the FleetSafe repository, the RTX desktop, and the Yahboom M3Pro robot stack. |
| What was built? | A text/voice/camera/LiDAR Vision-and-Language Navigation controller with CBF-QP safety certificates. |
| Why was it built? | To move beyond a simple path follower and create a reproducible safety-aware embodied VLN research system. |
| Where does it run? | The robot stack runs on the Jetson; the VLN controller runs on the RTX desktop; both communicate over ROS 2 domain 30. |
| When is it safe to enable live motion? | Only after LiDAR effective clearance exceeds the safety radius, camera is live, e-stop is ready, the controller is stable, and simulation/digital twin checks pass. |
| How is safety enforced? | The nominal command is passed through a Control Barrier Function Quadratic Program before publication to `/cmd_vel`. |
| How is evidence preserved? | Every instruction writes JSONL trace and certificate files, and curated evidence is committed to Git. |
| How is the system reproduced? | Use the Makefile targets and command runbook in this package. |

---

## Chapter 26 — Source File Role-by-Role Map

### `scripts/real_robot/run_vln_m3pro.py`

This is the controller entry point. It creates the ROS 2 node, subscribes to instruction, camera, LiDAR, and odometry topics, calls the nominal backbone, applies the CBF safety filter, publishes outputs, and writes evidence. Its most important responsibility is to never let a command path bypass evidence logging.

### `fleet_safe_vla/safety/lidar_sanitizer.py`

This module turns raw scan readings into a usable safety clearance. It does not throw away accountability. It keeps raw minimum values, counts invalid readings, reports valid minimum values, and exposes an effective clearance for the CBF. The certificate then includes all of these fields.

### `scripts/live/inspect_lidar_clearance.py`

This script gives a human-readable LiDAR report. It is used when I need to know whether the robot is genuinely blocked or whether raw dead-zone readings are making the scene look worse than it is.

### `scripts/live/check_vln_stack.sh`

This is the full health checker. It verifies ROS domain, Jetson nodes, sensor topics, FleetSafe topics, and LiDAR safety status. It gives a clear pass/warn/fail summary.

### `scripts/live/run_vln_desktop.sh`

This launch wrapper prevents accidental conda Python usage, prints the operating mode, and starts the controller with the selected safety radius and backbone.

### `scripts/live/watch_vln_outputs.sh`

This script turns ROS 2 echo commands into readable watch modes for parsed instructions, nominal commands, and certificates.

### `docs/REAL_ROBOT_VLN_OPERATION.md`

This is the operations manual. It records how to start the system, what warnings mean, how to interpret the LiDAR safety radius, and how to avoid unsafe live-motion mistakes.

### `results/demo_evidence_voice_vln_real_robot/`

This is the curated proof folder. It contains the committed voice-conditioned real-robot dry-run evidence and is the current strongest reproducible artifact.

---

## Chapter 27 — Data Dictionary for the Core JSON Fields

| Field | Meaning | Why it matters |
|---|---|---|
| `timestamp` | Wall-clock time of the certificate. | Allows chronological reconstruction. |
| `instruction_id` | Short unique ID for one instruction. | Connects certificate and trace records. |
| `source` | `text` or `voice`. | Proves which input path was used. |
| `safe` | Boolean safety result. | Human-readable safety verdict. |
| `qp_status` | Status of the Quadratic Program. | Shows whether the safety optimization was feasible. |
| `h_min` | Minimum safety margin. | Positive means the robot remained outside the safety boundary. |
| `min_dist_m` | Effective obstacle clearance in meters. | Shows how far the robot was from obstacles after filtering. |
| `safety_radius_m` | Required minimum clearance. | Defines the safety threshold used in that run. |
| `u_nominal` | Proposed control from the model. | Shows what the learned/backbone system wanted to do. |
| `u_safe` | Control after safety filtering. | Shows what the safety layer allowed. |
| `cbf_active` | Whether the CBF layer was applied. | Proves safety logic was active. |
| `dry_run` | Whether the robot was prevented from actually moving. | Prevents overclaiming live motion. |
| `scan_audit` | Raw and filtered LiDAR summary. | Makes sensor preprocessing transparent. |
| `camera_seen` | Whether a camera frame was received. | Supports the VLN claim. |
| `camera_frame_id` | ROS frame ID of the latest camera frame. | Identifies the camera coordinate frame. |
| `camera_last_age_ms` | Age of latest frame in milliseconds. | Indicates camera freshness. |

---

## Chapter 28 — Additional Issues Solved After the First Evidence Pass

### ISS-016: The command `ls -td results/certificates/*` failed with no such file or directory.

- **When:** Evidence lookup after leaving the repository
- **Where:** Home directory shell
- **Why it happened:** I was in `~` rather than `~/robotics/FleetSafe-VisualNav-Benchmark`, so the relative results path was wrong.
- **How I fixed it:** I made `cd ~/robotics/FleetSafe-VisualNav-Benchmark` the first line of every evidence-inspection block.
- **Command or code used:**

```bash
cd ~/robotics/FleetSafe-VisualNav-Benchmark
LATEST_CERT="$(ls -td results/certificates/* | head -1)"
```

- **Validation outcome:** The JSON certificate printed correctly after running from the repository root.
### ISS-017: The controller reported `LiDAR stale (... > 1.0s). Emergency stop.`

- **When:** Stale LiDAR emergency stop
- **Where:** Desktop controller terminal
- **Why it happened:** The controller had not received fresh scan messages within the freshness timeout, either because the Jetson stack was not active or discovery was inconsistent.
- **How I fixed it:** I verified the Jetson scan rates and restarted the controller only after live scan data appeared.
- **Command or code used:**

```bash
timeout 5s ros2 topic hz /scan0
timeout 5s ros2 topic hz /scan1
```

- **Validation outcome:** Both scans reported roughly 7 Hz, after which stale_lidar was no longer the blocker.
### ISS-018: The robot stopped even at a 0.30 m safety radius.

- **When:** Safety radius conflict with physical scene
- **Where:** /scan1 live LiDAR
- **Why it happened:** The physical scene had objects around 0.28 m from the scanner, so the controller was correct to block motion.
- **How I fixed it:** I did not override the safety layer; I used radius 0.20 only for dry-run evidence in a tight space and kept live motion disabled.
- **Command or code used:**

```bash
make vln-desktop-radius RADIUS=0.20
```

- **Validation outcome:** The certificate changed from cbf_infeasible to safe=true only when effective clearance exceeded the active radius.
### ISS-019: The parsed/certificate watchers sometimes missed messages.

- **When:** Non-latched ROS 2 outputs
- **Where:** ROS topic watchers
- **Why it happened:** The FleetSafe output topics are volatile ROS 2 topics, not durable latched topics. A watcher that starts after the message can miss it.
- **How I fixed it:** I documented that watchers should be started before sending the instruction, and that the JSONL files are the durable evidence source.
- **Command or code used:**

```bash
make vln-watch-cert
make vln-send TEXT="move forward slowly"
```

- **Validation outcome:** The watcher displayed the certificate when active before or near the time of publication, and JSONL always preserved it.
### ISS-020: `ros2 topic hz /camera/color/image_raw --qos-profile sensor_data` failed.

- **When:** Unsupported QoS command flag
- **Where:** ROS 2 Humble CLI
- **Why it happened:** The installed ROS 2 CLI version did not support that argument for the command being used.
- **How I fixed it:** I used the supported command and verified publisher count with `ros2 topic info -v`.
- **Command or code used:**

```bash
ros2 topic info /camera/color/image_raw -v
timeout 10s ros2 topic hz /camera/color/image_raw
```

- **Validation outcome:** Publisher count became 1 and frame rate printed around 1 Hz.
### ISS-021: `make vln-desktop-radius` refused to launch because run_vln_m3pro.py was already running.

- **When:** Controller already running
- **Where:** Desktop shell
- **Why it happened:** The wrapper intentionally prevents multiple controllers from competing for the same topics.
- **How I fixed it:** I killed stale controller processes before relaunching or kept the running terminal open.
- **Command or code used:**

```bash
pkill -9 -f "run_vln_m3pro.py" 2>/dev/null || true
```

- **Validation outcome:** A clean launch produced a fresh timestamped trace and certificate directory.
### ISS-022: The decision field was `dry_run_zero` even when the safety filter produced a nonzero safe command.

- **When:** Dry-run decision looked like no motion
- **Where:** Certificate JSON
- **Why it happened:** Dry-run mode intentionally publishes zero to `/cmd_vel` while still recording the safe command that would have been sent in live mode.
- **How I fixed it:** I documented the distinction between `u_safe` and the actual dry-run output to prevent overclaiming.
- **Command or code used:**

```bash
tail -n 1 "$LATEST_CERT"/vln_certificates_m3pro.jsonl | python3 -m json.tool
```

- **Validation outcome:** The certificate showed u_safe=[0.040...,0.0], dry_run=true, decision=dry_run_zero.
### ISS-023: Once CBF infeasible occurred, later commands could be ignored or blocked.

- **When:** Emergency stop latch after infeasible CBF
- **Where:** Controller state
- **Why it happened:** A latched e-stop is safer than silently resuming after a hard safety violation.
- **How I fixed it:** I restarted the controller after moving the robot or changing the dry-run radius.
- **Command or code used:**

```bash
pkill -9 -f "run_vln_m3pro.py"; make vln-desktop-radius RADIUS=0.20
```

- **Validation outcome:** The new run created new result directories and processed a later instruction normally.
### ISS-024: Some certificates showed `camera_seen=false` or camera age null.

- **When:** Camera frame arrived after first instruction
- **Where:** Certificate camera fields
- **Why it happened:** The controller had not yet received a camera frame before the instruction was processed.
- **How I fixed it:** I waited for the first-camera-frame log before sending the evidence instruction.
- **Command or code used:**

```bash
timeout 10s ros2 topic hz /camera/color/image_raw
make vln-send TEXT="move forward slowly..."
```

- **Validation outcome:** Later certificates showed camera_seen=true and frame_id=camera_color_optical_frame.
### ISS-025: Camera rate was about 1 Hz.

- **When:** Camera rate is low for future live motion
- **Where:** Camera topic
- **Why it happened:** For dry-run evidence this proves vision connectivity, but for fast live motion it may be too slow depending on control speed and environment.
- **How I fixed it:** I bounded the current claim to dry-run evidence and listed camera-rate stabilization as a live-motion prerequisite.
- **Command or code used:**

```bash
timeout 10s ros2 topic hz /camera/color/image_raw
```

- **Validation outcome:** The rate was measured and documented rather than ignored.
### ISS-026: `git status --short` showed modified Makefile, audit logs, and untracked results.

- **When:** Local modifications present while committing evidence
- **Where:** Git working tree
- **Why it happened:** Debugging creates local changes and many timestamped run outputs.
- **How I fixed it:** I committed only the curated demo evidence folder and left incidental logs out of the evidence commit.
- **Command or code used:**

```bash
git add results/demo_evidence_voice_vln_real_robot/
git commit -m "evidence: add voice-conditioned real-robot VLN safety trace"
```

- **Validation outcome:** Commit 8bef749 contained exactly five evidence files.
### ISS-027: A JSON field such as `"camera_seen": false` was pasted as a shell command and caused `command not found`.

- **When:** Terminal copy-paste caused accidental commands
- **Where:** Shell
- **Why it happened:** Human-in-the-loop debugging with many terminals makes copy-paste errors easy.
- **How I fixed it:** I separated command blocks from output blocks in the reproducible manuscript and evidence package.
- **Command or code used:**

```bash
python3 -m json.tool results/demo_evidence_voice_vln_real_robot/latest_voice_certificate_pretty.json
```

- **Validation outcome:** Pretty JSON files prevent raw output from being confused with commands.


---

## Chapter 29 — Live Motion Readiness Checklist

Before I enable `--enable-motion`, I will require all of the following:

1. The robot must be physically lifted or placed in an open area during initial spin-up.
2. A human must be within reach of a physical or software emergency stop.
3. `SAFETY_RADIUS=0.30 make vln-check-stack` must pass or only warn with a clearly understood reason.
4. `/scan0` and `/scan1` must be live and above the intended safety radius after sanitization.
5. `/odom_raw` must be live.
6. `/camera/color/image_raw` must have a publisher and a measured rate.
7. The controller must show a first camera frame log before issuing a visual navigation command.
8. Dry-run must produce a safe certificate for the same instruction.
9. Isaac Sim or digital twin should reproduce the same safe/blocked behavior for comparable scenes.
10. The first live motion command must use low maximum velocity and a conservative radius.
11. The first live test must be short, with a single instruction and immediate certificate inspection.
12. The robot must not be commanded live if the certificate would show `cbf_infeasible`, `stale_lidar`, or `camera_seen=false` for visual claims.

This checklist is strict because the purpose of the project is not to make a risky video. The purpose is to show safety-aware state-of-the-art embodied navigation.

---

## Chapter 30 — Research Manuscript Positioning

The project can be framed academically as follows:

> I present FleetSafe-VLN, a reproducible real-robot Vision-and-Language Navigation pipeline that connects voice/text instruction intake, RGB camera observations, dual-LiDAR obstacle sensing, nominal visual-navigation backbones, and Control Barrier Function safety certificates. The system separates capability from safety: learned navigation backbones propose actions, while a CBF-QP safety filter provides the final command and logs a certificate for every instruction. Real-robot dry-run evidence demonstrates voice-conditioned instruction processing, camera-frame reception, LiDAR-sanitized effective clearance, nominal-to-safe command conversion, and append-only trace/certificate generation.

The strongest claim is not that the robot is already the best live-motion system. The strongest claim is that the project now has a reproducible safety-evidence infrastructure that can support honest benchmarking against GNM, ViNT, NoMaD, Isaac Sim, and later live-motion experiments.

---

## Chapter 31 — IEEE-Style References

[1] P. Anderson et al., "Vision-and-Language Navigation: Interpreting Visually-Grounded Navigation Instructions in Real Environments," in CVPR, 2018. URL: https://arxiv.org/abs/1711.07280
[2] M. Savva et al., "Habitat: A Platform for Embodied AI Research," in ICCV, 2019. URL: https://arxiv.org/abs/1904.01201
[3] D. Shah et al., "GNM: A General Navigation Model to Drive Any Robot," robot learning/navigation project paper and code release, 2022/2023. URL: https://general-navigation-models.github.io
[4] D. Shah et al., "ViNT: A Foundation Model for Visual Navigation," robot learning/navigation project paper, 2023. URL: https://visualnav-transformer.github.io
[5] A. Sridhar et al., "NoMaD: Goal Masked Diffusion Policies for Navigation and Exploration," arXiv, 2023. URL: https://arxiv.org/abs/2310.07896
[6] A. D. Ames, X. Xu, J. W. Grizzle, and P. Tabuada, "Control Barrier Function Based Quadratic Programs for Safety Critical Systems," IEEE Transactions on Automatic Control, 2017. DOI: 10.1109/TAC.2016.2638961
[7] S. M. LaValle, Planning Algorithms. Cambridge University Press, 2006. URL: http://planning.cs.uiuc.edu
[8] Open Robotics, "ROS 2 Humble Documentation: Topics," 2024. URL: https://docs.ros.org/en/humble/Concepts/Basic/About-Topics.html
[9] Open Robotics, "ROS 2 Humble Documentation: Quality of Service Settings," 2024. URL: https://docs.ros.org/en/humble/Concepts/Intermediate/About-Quality-of-Service-Settings.html
[10] NVIDIA, "Isaac Sim Documentation: ROS 2 Tutorials and Bridge," 2025. URL: https://docs.isaacsim.omniverse.nvidia.com/latest/ros2_tutorials/index.html
[11] The HDF Group, "Hierarchical Data Format, version 5," documentation. URL: https://www.hdfgroup.org/solutions/hdf5/
[12] J. Sturm et al., "A Benchmark for the Evaluation of RGB-D SLAM Systems," IROS, 2012. URL: https://vision.in.tum.de/data/datasets/rgbd-dataset
