# Yahboom ROSMASTER M3 Pro — Upstream Integration

## Purpose

This document explains how the official Yahboom ROSMASTER M3 Pro repository
fits into the FleetSafe-GNM research architecture, why we treat it as an
external dependency rather than vendoring it, and what specific components
we extract from it.

---

## The Two-Layer Architecture

```
Yahboom official repo
= robot drivers, ROS 2 launch files, chassis control, sensor topics,
  URDF/Xacro descriptions, OpenClaw demos, navigation tutorials

Our gnm-vlnverse-baseline repo
= GNM visual navigation, FleetSafe safety filter, Track A/Track B evidence,
  Isaac Sim pipeline, rosbag conversion, training, evaluation, release docs
```

These two layers connect at exactly one boundary: the canonical ROS 2 topic set.

```
Yahboom robot hardware/software
        ↓
/camera/image_raw  /odom  /tf  /scan
        ↓
GNM visual navigation brain
        ↓
FleetSafe execution-time safety shield
        ↓
safe /cmd_vel
        ↓
real Yahboom robot
```

Neither layer knows or cares about the internals of the other. GNM and FleetSafe
do not read Yahboom source code. Yahboom hardware does not know about GNM. They
communicate only through the five canonical ROS 2 topics. This is the correct
sim-to-real integration boundary.

---

## Why the Official Repo Matters

The official Yahboom repository for the ROSMASTER M3 Pro is:

```
https://github.com/YahboomTechnology/ROSMASTER-M3PRO
```

It is the authoritative source for:

1. **URDF / Xacro robot description** — the physical model of the robot used by
   Isaac Sim and any ROS 2 simulator. Our own URDF (in
   `assets/robots/yahboom_m3_pro/`) was derived from the product specification;
   the upstream URDF confirms joint names, link geometry, sensor mounts.

2. **ROS 2 chassis control** — launch files and controllers for the mecanum drive.
   These define the exact `/cmd_vel` format the hardware expects.

3. **Sensor topic names** — the canonical names published by the hardware driver.
   These differ from our internal canonical names; a remap layer bridges them.
   See `docs/yahboom_to_fleetsafe_topic_mapping.md`.

4. **TF frame names** — `base_link`, `base_footprint`, `camera_link`, `lidar_link`.
   These must match Isaac Sim and the GNM dataset converter.

5. **Navigation and SLAM examples** — upstream tutorials that show how the
   hardware behaves in real deployments. SLAM (Simultaneous Localisation and
   Mapping) means the robot builds a map while locating itself within it.

6. **Real robot startup procedure** — the exact boot sequence required before
   any ROS 2 topic is available on the physical M3 Pro.

---

## What We Do NOT Take from the Yahboom Repo

- We do not copy the entire upstream repo into our research repo.
- We do not vendor Yahboom's navigation stack (it uses a different planner).
- We do not use Yahboom's camera pipeline directly — we remap to canonical names.
- We do not modify Yahboom's drivers or hardware code.
- We do not replace GNM with any Yahboom navigation demo.
- We do not replace FleetSafe with any Yahboom safety feature.

The correct clone path is:

```
external/yahboom/ROSMASTER-M3PRO
```

This directory is listed in `.gitignore` and is never committed to our research
repo. It is a local reference only.

---

## OpenClaw

OpenClaw is Yahboom's higher-level AI-agent and task demonstration layer. It
appears in the ROSMASTER M3 Pro package alongside the core ROS 2 stack and
includes demonstrations such as:

- Multi-point navigation
- Scene understanding
- SLAM and road-network planning
- Intelligent information collection
- Robotic arm and gripping demonstrations
- Voice interaction and vision recognition

**OpenClaw is treated as an optional upstream demo layer.** It does not replace
GNM, FleetSafe, or the Track B language grounding pipeline. The correct
architectural relationship is:

```
OpenClaw / instruction interface    ← optional upstream demo/task layer
        ↓
Track B language grounding          ← instruction understanding (our research)
        ↓
GNM                                 ← visual navigation brain (our research)
        ↓
FleetSafe                           ← execution-time safety shield (our research)
        ↓
/cmd_vel                            ← safe robot motion command
        ↓
Yahboom ROSMASTER M3 Pro            ← simulation first, real robot later
```

OpenClaw may be useful later as a high-level command interface that passes
instructions to Track B. It will not be integrated until the GNM+FleetSafe
simulation pipeline is complete and validated.

---

## What the ROSMASTER M3 Pro Package Includes

From Yahboom's official repository and product materials, the ROSMASTER M3 Pro
package supports:

| Feature | Relevant to FleetSafe-GNM? |
|---|---|
| ROS 2 Humble base | Yes — all our ROS 2 work targets Humble |
| Mecanum wheel chassis control | Yes — `/cmd_vel` format and kinematics |
| RGB depth camera | Yes — `/camera/color/image_raw` source |
| Dual TOF LiDAR | Yes — `/scan` source for FleetSafe obstacle detection |
| Odometry publisher | Yes — `/odom` source for GNM waypoint labels |
| TF tree | Yes — `base_link`, `camera_link`, `lidar_link` frames |
| SLAM mapping | Reference — useful for future map-based navigation |
| Autonomous navigation | Reference — existing planner we do not replace |
| Path planning | Reference — we use GNM instead |
| Obstacle avoidance | Reference — FleetSafe replaces this at execution time |
| OpenClaw AI-agent layer | Optional — future Track B command interface |
| ROS 2 tutorials / source | Reference — startup procedure and topic inspection |

---

## How This Supports Sim-to-Real

The sim-to-real gap is reduced when training and deployment use the same robot
model and sensor configuration.

Step 1 — Isaac Sim uses our Yahboom URDF (derived from product spec, confirmed
against upstream URDF). The physics, joint names, and sensor positions match the
physical robot as closely as possible.

Step 2 — The five canonical topics published by Isaac Sim match the five topics
published by the real robot (after remapping). The GNM dataset converter and
FleetSafe see identical topic names regardless of whether the source is Isaac Sim
or the physical M3 Pro.

Step 3 — A recorded rosbag2 episode from Isaac Sim can be converted to GNM
format, and the trained model can be deployed on the real robot without changing
the inference code.

The full remap specification is in `docs/yahboom_to_fleetsafe_topic_mapping.md`.

---

## How to Clone the Upstream Repo

```bash
bash scripts/setup/clone_yahboom_rosmaster_m3pro.sh
```

This will clone the official repo into `external/yahboom/ROSMASTER-M3PRO`.
The directory is gitignored and will not be committed.

After cloning, inspect the upstream content:

```bash
python3 scripts/gnm/inspect_yahboom_upstream.py
```

This writes an inventory of URDF, Xacro, launch, sensor, and topic references
found in the cloned repo.

---

## Claim Boundary

| Item | Status |
|---|---|
| Official Yahboom repo identified and documented | Yes |
| Clone/setup script added | Yes |
| Topic mapping documented | Yes |
| Upstream inspection script added | Yes |
| Upstream repo actually cloned locally | Pending — run `clone_yahboom_rosmaster_m3pro.sh` |
| Upstream URDF confirmed against our URDF | Pending — requires clone |
| Real robot topics confirmed on physical M3 Pro | Pending — v2.8 |
| FleetSafe-GNM running on real Yahboom | Pending — v2.8 |
| OpenClaw integration | Not started — optional future milestone |
