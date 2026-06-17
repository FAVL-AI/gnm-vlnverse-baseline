# Yahboom M3 Pro to FleetSafe-GNM Topic Mapping

## Purpose

The Yahboom ROSMASTER M3 Pro hardware driver publishes topics under
hardware-specific names that differ from the canonical names used by GNM and
FleetSafe. This document specifies the complete remap between them and explains
where each remap must be applied.

---

## Canonical Topic Contract

GNM and FleetSafe are written against exactly these five topic names. Neither
component reads from any hardware-specific name.

| Topic | Type | Used by |
|---|---|---|
| `/camera/image_raw` | `sensor_msgs/msg/Image` | GNM visual input (context and goal frames) |
| `/odom` | `nav_msgs/msg/Odometry` | GNM waypoint labels, FleetSafe velocity estimate |
| `/tf` | `tf2_msgs/msg/TFMessage` | Dataset converter robot pose, FleetSafe frame lookup |
| `/scan` | `sensor_msgs/msg/LaserScan` | FleetSafe obstacle detection and CBF-QP constraint |
| `/cmd_vel` | `geometry_msgs/msg/Twist` | Final safe motion command output from FleetSafe |

---

## Remap Table

| Canonical name | Yahboom hardware name | Remap needed? | Notes |
|---|---|---|---|
| `/camera/image_raw` | `/camera/color/image_raw` | Yes | Yahboom depth camera driver publishes under the RealSense-style name |
| `/odom` | `/m3pro/odom` | Yes | Yahboom chassis driver namespaces odometry under the robot prefix |
| `/tf` | `/tf` | No | Standard TF broadcast — no remap needed |
| `/scan` | `/scan` | No | Yahboom LiDAR driver uses the standard laser scan name |
| `/cmd_vel` | `/m3pro/cmd_vel` | Yes | Yahboom chassis driver subscribes under the robot prefix |

**Note:** Topic names on the real hardware must be confirmed by running
`ros2 topic list` on the physical M3 Pro before the first live recording. The
table above reflects the names documented in the Yahboom driver source and our
`scripts/gnm/check_yahboom_topic_contract.py`.

---

## Where to Apply the Remaps

### Isaac Sim (simulation)

In Isaac Sim, the OmniGraph nodes are configured with the canonical topic names
directly. No remap is needed because Isaac Sim publishes to exactly:

- `/camera/image_raw`
- `/odom`
- `/tf`
- `/scan`

And subscribes to `/cmd_vel`. This is set in the OmniGraph node `topic_name`
fields during the Step 6–10 setup described in
`docs/v2.3_yahboom_isaac_import_topic_verification.md`.

### Real robot ROS 2 launch file

When connecting to the physical Yahboom M3 Pro, the remap is applied in the
launch file that starts GNM and FleetSafe:

```python
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        Node(
            package="gnm_runner",
            executable="gnm_node",
            name="gnm",
            remappings=[
                ("/camera/color/image_raw", "/camera/image_raw"),
                ("/m3pro/odom", "/odom"),
                ("/cmd_vel", "/m3pro/cmd_vel"),
            ],
        ),
        Node(
            package="fleet_safe",
            executable="fleetsafe_node",
            name="fleetsafe",
            remappings=[
                ("/m3pro/odom", "/odom"),
                ("/cmd_vel", "/m3pro/cmd_vel"),
            ],
        ),
    ])
```

This keeps the GNM and FleetSafe source code free of any hardware-specific name.
All hardware specifics are isolated to the launch file.

### Recorded rosbag episodes

When recording a rosbag2 episode from the real robot, record the canonical
topic names only. Start the hardware driver, apply the remap in the launch
file, confirm canonical topics are live with `verify_yahboom_live_topics.py --strict`,
then record:

```bash
ros2 bag record /camera/image_raw /odom /tf /scan /cmd_vel \
  --output datasets/gnm_fleetsafe_rosbags/episode_001/rosbag
```

Do not record from the hardware-specific names. A bag recorded with
`/camera/color/image_raw` instead of `/camera/image_raw` cannot be fed directly
to the GNM dataset converter.

---

## TF Frame Name Contract

These frame names must be consistent across Isaac Sim, rosbag recording, and
real robot deployment:

| Frame | Meaning | Source |
|---|---|---|
| `base_footprint` | Robot footprint on the ground plane | Chassis driver |
| `base_link` | Robot body at wheel-axle height | URDF |
| `camera_link` | Camera sensor position relative to base | URDF |
| `lidar_link` | LiDAR sensor position relative to base | URDF |
| `odom` | Odometry world frame | Chassis odometry publisher |
| `map` | SLAM map frame (used if SLAM is running) | SLAM node |

The GNM dataset converter uses `base_link → odom` TF to compute the robot's
pose at each timestep. If `base_link` is missing from the TF tree, pose
computation fails and the episode cannot be converted.

---

## Mecanum Wheel Command Format

The `/cmd_vel` message type is `geometry_msgs/msg/Twist`. For the Yahboom M3 Pro
mecanum drive, the relevant fields are:

| Field | Meaning | Units | Range |
|---|---|---|---|
| `linear.x` | Forward/backward speed | m/s | −0.30 to +0.30 |
| `linear.y` | Sideways speed (holonomic) | m/s | −0.20 to +0.20 |
| `angular.z` | Rotation speed | rad/s | −0.70 to +0.70 |

FleetSafe reads the GNM raw command on `/gnm/cmd_vel_raw`, applies the CBF-QP
safety constraint using `/odom` and `/scan`, and publishes the safe command
to `/cmd_vel`. The Yahboom chassis driver subscribes to `/m3pro/cmd_vel` which
is remapped from `/cmd_vel` by the launch file.

The mecanum inverse kinematics applied inside the Yahboom chassis driver converts
the three-component Twist into individual wheel speeds:

```
fl = (vx − vy − (lx + ly) × wz) / r
fr = (vx + vy + (lx + ly) × wz) / r
rl = (vx + vy − (lx + ly) × wz) / r
rr = (vx − vy + (lx + ly) × wz) / r
```

Where lx = 0.0775 m (half wheelbase), ly = 0.0850 m (half track width),
r = 0.048 m (wheel radius).

---

## Verification Command

After the physical M3 Pro is booted and running:

```bash
ros2 topic list
```

Expected hardware-native topics (before remap):
```
/camera/color/image_raw
/m3pro/odom
/tf
/scan
/m3pro/cmd_vel
```

After starting the GNM/FleetSafe launch file with remaps:
```bash
python3 scripts/gnm/verify_yahboom_live_topics.py --strict
```

All five canonical topics must pass before recording begins.
