# FleetSafe Real Robot Runbook
**Hardware:** Yahboom ROSMASTER-M3Pro · Jetson Orin NX · Orbbec DaBai DCW2 · Tmini-Plus×2
**Network:** RTX desktop `172.20.10.2` ↔ Robot Jetson `172.20.10.14` (hotspot) / `100.91.232.55` (Tailscale)

---

## Domain Isolation — Read This First

| Domain | Use | Command the robot? |
|--------|-----|--------------------|
| `ROS_DOMAIN_ID=30` | Live robot, real-time topics | **YES — all real traffic** |
| `ROS_DOMAIN_ID=99` + `ROS_LOCALHOST_ONLY=1` | Bag playback on RTX desktop | **NO — isolated from robot** |

**Rule:** Never replay bags on domain 30.  Never run `ros2 bag play` without `ROS_DOMAIN_ID=99 ROS_LOCALHOST_ONLY=1`.

---

## Robot Powered Off / Unreachable

**"No route to host"** or **"Connection refused"** almost always means the robot is powered off, not a software bug.

**If the robot is off:**
1. Power it on
2. Wait **60–90 seconds** for Jetson boot to complete
3. Confirm you are on the same hotspot (`172.20.10.14`) or that Tailscale is connected (`100.91.232.55`)
4. Check connection:
   ```bash
   ./scripts/robot/check_robot_connection.sh
   # or: make robot-check
   ```
5. Install tools:
   ```bash
   ./scripts/robot/install_robot_tools.sh
   # or: make robot-install
   ```

**If you need to prepare while the robot is off:**
```bash
make robot-bundle
# Creates dist/fleetsafe_robot_tools.tar.gz
# When robot is on, install manually:
scp dist/fleetsafe_robot_tools.tar.gz jetson@172.20.10.14:~/
ssh jetson@172.20.10.14
tar -xzf ~/fleetsafe_robot_tools.tar.gz -C ~/
bash ~/install.sh
```

**Connection options:**

| Network | Address |
|---------|---------|
| Hotspot | `jetson@172.20.10.14` |
| Tailscale | `jetson@100.91.232.55` |

`check_robot_connection.sh` and `install_robot_tools.sh` try both automatically.
Override with `--ip`:
```bash
./scripts/robot/install_robot_tools.sh --ip 100.91.232.55
```

---

## One-Time Setup

Install robot-side helper scripts (run once after cloning):

```bash
# From RTX desktop (robot must be on)
make robot-check    # verify reachability first
make robot-install  # or: ./scripts/robot/install_robot_tools.sh
```

This SSH-copies `~/fleetsafe_robot.env` and `~/fleetsafe_robot_tools/` to the Jetson.

---

## Daily Operation

Open four terminals.

### Terminal A — Jetson SSH: start robot stack

```bash
ssh jetson@172.20.10.14
~/fleetsafe_robot_tools/start_robot_stack.sh
```

This sources ROS2 Humble and the Yahboom workspace, stops any stale
`micro_ros_agent`, starts a fresh one on `/dev/myserial` at 2 Mbaud,
waits 5 s, then prints nodes/topics.

Check status at any time:

```bash
~/fleetsafe_robot_tools/status_robot_stack.sh
```

### Terminal B — RTX desktop: start dashboard

```bash
# Start FleetSafe command center (backend + frontend)
./launch_fleetsafe_all.sh --no-browser
```

Dashboard: `http://127.0.0.1:3000`
Backend API: `http://127.0.0.1:8000`

### Terminal C — RTX desktop: verify topics, then record a bag

Verify the robot is visible:

```bash
./scripts/live/check_robot_topics.sh
```

Expected output: nodes on domain 30, topics including `/camera/color/image_raw`,
`/odom_raw`, `/scan0`, `/scan1`, `/cmd_vel`, `/imu/data_raw`.

Record a bag (Ctrl-C to stop):

```bash
./scripts/live/record_real_robot_bag.sh
```

Bags are saved to `data/real_robot_bags/m3pro_full_motion_TIMESTAMP/`.

Inspect any bag:

```bash
./scripts/live/info_latest_bag.sh
# or
./scripts/live/info_latest_bag.sh data/real_robot_bags/m3pro_full_motion_20260525_042557
```

### Terminal D — RTX desktop: safe local playback with camera viewer

```bash
./scripts/live/play_latest_bag_camera.sh
# or pass a specific bag
./scripts/live/play_latest_bag_camera.sh data/real_robot_bags/m3pro_full_motion_20260525_042557
```

This script:
1. Sets `ROS_DOMAIN_ID=99` and `ROS_LOCALHOST_ONLY=1` — fully isolated.
2. Starts the Python camera viewer at `http://127.0.0.1:8081`.
3. Opens the browser automatically.
4. Runs `ros2 bag play --loop --rate 10.0`.
5. On Ctrl-C, kills the viewer.

---

## Confirmed Working Bag

```
data/real_robot_bags/m3pro_full_motion_20260525_042557/
```

| Field | Value |
|-------|-------|
| Messages | 513 |
| Duration | ~72.7 s |
| Topics | /camera/color/image_raw (22) · /camera/depth/image_raw (16) · /camera/color/camera_info (23) · /camera/depth/camera_info (17) · /scan0 (92) · /scan1 (57) · /odom_raw (102) · /cmd_vel (51) · /imu/data_raw (133) |

---

## Why We Use a Custom Python Camera Viewer

`web_video_server` (the standard ROS2 HTTP camera bridge) requires apt packages
(`ros-humble-web-video-server`) whose upstream apt dependencies were broken at
installation time.  Rather than fighting the apt tree, we wrote
`scripts/viewers/ros_camera_bmp_server.py` — a ~150-line stdlib-only viewer
that subscribes to `sensor_msgs/msg/Image`, encodes each frame to BMP in-process,
and serves it via Python's built-in `http.server`.  No extra packages needed.

Run directly:

```bash
source /opt/ros/humble/setup.bash
/usr/bin/python3 scripts/viewers/ros_camera_bmp_server.py \
    --topic /camera/color/image_raw --port 8081
# open http://127.0.0.1:8081
```

---

## Safety Stops

From RTX desktop (sends zero velocity on live domain 30):

```bash
./scripts/live/stop_robot_zero.sh
```

From robot (via SSH or direct):

```bash
~/fleetsafe_robot_tools/stop_robot_motion.sh
```

---

## Quick Reference

```
# Robot (on Jetson via SSH)
~/fleetsafe_robot_tools/start_robot_stack.sh
~/fleetsafe_robot_tools/status_robot_stack.sh
~/fleetsafe_robot_tools/stop_robot_motion.sh

# RTX desktop
./launch_fleetsafe_all.sh --no-browser
./scripts/live/check_robot_topics.sh
./scripts/live/record_real_robot_bag.sh
./scripts/live/info_latest_bag.sh
./scripts/live/play_latest_bag_camera.sh
./scripts/live/stop_robot_zero.sh
```
