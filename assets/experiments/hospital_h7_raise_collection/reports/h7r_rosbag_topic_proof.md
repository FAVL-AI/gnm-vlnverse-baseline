# H7R rosbag topic proof

Generated 2026-07-18T03:18:33Z. H7r raised-mount (+0.12 m, occlusion removed) — DATASET OF RECORD.

Each row is transcribed directly from the recorded bag's `metadata.yaml` (rosbag2 v5, sqlite3). A reviewer can independently confirm with `ros2 bag info <bag_dir>`.

Expected ImageNav topics (all must be present): `/camera/camera_info`, `/camera/image_raw`, `/clock`, `/cmd_vel`, `/odom`, `/tf`

| episode_id | storage | duration_s | total_msgs | `/camera/camera_info` | `/camera/image_raw` | `/clock` | `/cmd_vel` | `/odom` | `/tf` | all_expected |
|---|---|---|---|---|---|---|---|---|---|---|
| h7r_reception_01_20260714_042711 | sqlite3 | 608.166 | 12692 | 2117 | 2117 | 2117 | 2108 | 2116 | 2117 | PASS |
| h7r_corridor_01_20260714_045626 | sqlite3 | 657.614 | 12716 | 2122 | 2122 | 2121 | 2108 | 2121 | 2122 | PASS |
| h7r_turn_01_20260714_052544 | sqlite3 | 678.728 | 12712 | 2121 | 2121 | 2121 | 2108 | 2120 | 2121 | PASS |
| h7r_waiting_01_20260714_060451 | sqlite3 | 675.646 | 12732 | 2125 | 2124 | 2125 | 2108 | 2125 | 2125 | PASS |
| h7r_reception_02_20260714_044133 | sqlite3 | 638.756 | 12718 | 2122 | 2122 | 2122 | 2108 | 2122 | 2122 | PASS |
| h7r_corridor_02_20260714_051150 | sqlite3 | 580.271 | 12723 | 2123 | 2123 | 2123 | 2108 | 2123 | 2123 | PASS |
| h7r_turn_02_20260714_054954 | sqlite3 | 639.337 | 12714 | 2121 | 2121 | 2121 | 2108 | 2121 | 2122 | PASS |
| h7r_waiting_02_20260714_062024 | sqlite3 | 574.272 | 12713 | 2121 | 2121 | 2121 | 2108 | 2121 | 2121 | PASS |

Topic message types (from bag metadata):

- `/camera/camera_info` -> `sensor_msgs/msg/CameraInfo`
- `/camera/image_raw` -> `sensor_msgs/msg/Image`
- `/clock` -> `rosgraph_msgs/msg/Clock`
- `/cmd_vel` -> `geometry_msgs/msg/Twist`
- `/odom` -> `nav_msgs/msg/Odometry`
- `/tf` -> `tf2_msgs/msg/TFMessage`
