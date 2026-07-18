# H7 scene-identity gate log index

Generated 2026-07-18T03:18:33Z. H7 baseline (fixed camera, ~38.3% lower-third occlusion).

The scene-identity gate (`hospital_scene_identity_gate.verify_hospital_scene`) runs fail-closed in the recording harness **before** `ros2 bag record` starts; on failure the harness `sys.exit(5)` and records nothing. Every bag below therefore has a PASS manifest, proving the data was recorded in the verified Isaac Sim `hospital.usd` scene (not procedural H6, and not a physical hospital).

Note: the scene gate's resolution check was **declarative only** at H7/H7R capture time (observed 640x480 vs declared 1280x720; not enforced). See `H7_H7R_CAMERA_RESOLUTION_VARIANCE_AND_H8_MITIGATION.md`. Scene identity, checksum integrity and topic presence are unaffected.

| episode_id | gate_pass | hospital.usd | prims (min) | landmark prims | front camera | res | manifest |
|---|---|---|---|---|---|---|---|
| h7_reception_01_20260714_000815 | True | True | 1909 (1000) | 0 | `/World/M3Pro/camera_link/rgb_camera` | 640x480 | `assets/experiments/hospital_h7_scene_gate/h7_reception_01_20260714_000815.json` |
| h7_corridor_01_20260714_004338 | True | True | 1909 (1000) | 0 | `/World/M3Pro/camera_link/rgb_camera` | 640x480 | `assets/experiments/hospital_h7_scene_gate/h7_corridor_01_20260714_004338.json` |
| h7_turn_01_20260714_011847 | True | True | 1909 (1000) | 0 | `/World/M3Pro/camera_link/rgb_camera` | 640x480 | `assets/experiments/hospital_h7_scene_gate/h7_turn_01_20260714_011847.json` |
| h7_waiting_01_20260714_015109 | True | True | 1909 (1000) | 0 | `/World/M3Pro/camera_link/rgb_camera` | 640x480 | `assets/experiments/hospital_h7_scene_gate/h7_waiting_01_20260714_015109.json` |
| h7_reception_02_20260714_002503 | True | True | 1909 (1000) | 0 | `/World/M3Pro/camera_link/rgb_camera` | 640x480 | `assets/experiments/hospital_h7_scene_gate/h7_reception_02_20260714_002503.json` |
| h7_corridor_02_20260714_010145 | True | True | 1909 (1000) | 0 | `/World/M3Pro/camera_link/rgb_camera` | 640x480 | `assets/experiments/hospital_h7_scene_gate/h7_corridor_02_20260714_010145.json` |
| h7_turn_02_20260714_013617 | True | True | 1909 (1000) | 0 | `/World/M3Pro/camera_link/rgb_camera` | 640x480 | `assets/experiments/hospital_h7_scene_gate/h7_turn_02_20260714_013617.json` |
| h7_waiting_02_20260714_020630 | True | True | 1909 (1000) | 0 | `/World/M3Pro/camera_link/rgb_camera` | 640x480 | `assets/experiments/hospital_h7_scene_gate/h7_waiting_02_20260714_020630.json` |
