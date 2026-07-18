# H7 rosbag topic proof

Generated 2026-07-18T03:18:33Z. H7 baseline (fixed camera, ~38.3% lower-third occlusion).

Each row is transcribed directly from the recorded bag's `metadata.yaml` (rosbag2 v5, sqlite3). A reviewer can independently confirm with `ros2 bag info <bag_dir>`.

Expected ImageNav topics (all must be present): `/camera/camera_info`, `/camera/image_raw`, `/clock`, `/cmd_vel`, `/odom`, `/tf`

| episode_id | storage | duration_s | total_msgs | `/camera/camera_info` | `/camera/image_raw` | `/clock` | `/cmd_vel` | `/odom` | `/tf` | all_expected |
|---|---|---|---|---|---|---|---|---|---|---|
| h7_reception_01_20260714_000815 | sqlite3 | 749.253 | 12648 | 2108 | 2108 | 2108 | 2108 | 2108 | 2108 | PASS |
| h7_corridor_01_20260714_004338 | sqlite3 | 831.606 | 12544 | 2090 | 2090 | 2091 | 2091 | 2091 | 2091 | PASS |
| h7_turn_01_20260714_011847 | sqlite3 | 794.874 | 12715 | 2122 | 2122 | 2121 | 2108 | 2121 | 2121 | PASS |
| h7_waiting_01_20260714_015109 | sqlite3 | 663.259 | 12651 | 2108 | 2108 | 2109 | 2108 | 2109 | 2109 | PASS |
| h7_reception_02_20260714_002503 | sqlite3 | 859.989 | 12658 | 2110 | 2110 | 2110 | 2108 | 2110 | 2110 | PASS |
| h7_corridor_02_20260714_010145 | sqlite3 | 767.885 | 12690 | 2117 | 2117 | 2116 | 2108 | 2116 | 2116 | PASS |
| h7_turn_02_20260714_013617 | sqlite3 | 635.704 | 12706 | 2119 | 2119 | 2120 | 2108 | 2120 | 2120 | PASS |
| h7_waiting_02_20260714_020630 | sqlite3 | 552.953 | 12699 | 2118 | 2119 | 2118 | 2108 | 2118 | 2118 | PASS |

Topic message types (from bag metadata):

- `/camera/camera_info` -> `sensor_msgs/msg/CameraInfo`
- `/camera/image_raw` -> `sensor_msgs/msg/Image`
- `/clock` -> `rosgraph_msgs/msg/Clock`
- `/cmd_vel` -> `geometry_msgs/msg/Twist`
- `/odom` -> `nav_msgs/msg/Odometry`
- `/tf` -> `tf2_msgs/msg/TFMessage`
