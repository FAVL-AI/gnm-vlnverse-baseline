# H7R scene-identity gate log index

Generated 2026-07-18T03:18:33Z. H7r raised-mount (+0.12 m, occlusion removed) — DATASET OF RECORD.

The scene-identity gate (`hospital_scene_identity_gate.verify_hospital_scene`) runs fail-closed in the recording harness **before** `ros2 bag record` starts; on failure the harness `sys.exit(5)` and records nothing. Every bag below therefore has a PASS manifest, proving the data was recorded in the verified Isaac Sim `hospital.usd` scene (not procedural H6, and not a physical hospital).

Note: the scene gate's resolution check was **declarative only** at H7/H7R capture time (observed 640x480 vs declared 1280x720; not enforced). See `H7_H7R_CAMERA_RESOLUTION_VARIANCE_AND_H8_MITIGATION.md`. Scene identity, checksum integrity and topic presence are unaffected.

| episode_id | gate_pass | hospital.usd | prims (min) | landmark prims | front camera | res | manifest |
|---|---|---|---|---|---|---|---|
| h7r_reception_01_20260714_042711 | True | True | 1909 (1000) | 0 | `/World/M3Pro/camera_link/rgb_camera` | 640x480 | `assets/experiments/hospital_h7_scene_gate/h7r_reception_01_20260714_042711.json` |
| h7r_corridor_01_20260714_045626 | True | True | 1909 (1000) | 0 | `/World/M3Pro/camera_link/rgb_camera` | 640x480 | `assets/experiments/hospital_h7_scene_gate/h7r_corridor_01_20260714_045626.json` |
| h7r_turn_01_20260714_052544 | True | True | 1909 (1000) | 0 | `/World/M3Pro/camera_link/rgb_camera` | 640x480 | `assets/experiments/hospital_h7_scene_gate/h7r_turn_01_20260714_052544.json` |
| h7r_waiting_01_20260714_060451 | True | True | 1909 (1000) | 0 | `/World/M3Pro/camera_link/rgb_camera` | 640x480 | `assets/experiments/hospital_h7_scene_gate/h7r_waiting_01_20260714_060451.json` |
| h7r_reception_02_20260714_044133 | True | True | 1909 (1000) | 0 | `/World/M3Pro/camera_link/rgb_camera` | 640x480 | `assets/experiments/hospital_h7_scene_gate/h7r_reception_02_20260714_044133.json` |
| h7r_corridor_02_20260714_051150 | True | True | 1909 (1000) | 0 | `/World/M3Pro/camera_link/rgb_camera` | 640x480 | `assets/experiments/hospital_h7_scene_gate/h7r_corridor_02_20260714_051150.json` |
| h7r_turn_02_20260714_054954 | True | True | 1909 (1000) | 0 | `/World/M3Pro/camera_link/rgb_camera` | 640x480 | `assets/experiments/hospital_h7_scene_gate/h7r_turn_02_20260714_054954.json` |
| h7r_waiting_02_20260714_062024 | True | True | 1909 (1000) | 0 | `/World/M3Pro/camera_link/rgb_camera` | 640x480 | `assets/experiments/hospital_h7_scene_gate/h7r_waiting_02_20260714_062024.json` |
