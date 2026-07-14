# H7-Hospital recording quality table

Generated 2026-07-14T02:50:49. 8-episode gated pilot in the real Isaac hospital.usd.

| episode | family | split | route_completed | total_contacts | max_contact_streak | emergency_stop | stop_reason | distance_m | steps | wall_s | scene_gate_pass | hospital_prims | bag_gb | image_raw_msgs | bottom_third_luma |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| h7_reception_01 | reception_to_corridor | train | True | 0 | 0 | False | None | 5.76 | 6120 | 749.8 | True | 1909 | 1.95 | 2108 | 0.0 |
| h7_corridor_01 | corridor_straight | train | True | 0 | 0 | False | None | 3.12 | 6120 | 832.4 | True | 1909 | 1.93 | 2090 | 0.1 |
| h7_turn_01 | turn_t_junction | train | True | 0 | 0 | False | None | 2.39 | 6120 | 795.3 | True | 1909 | 1.96 | 2122 | 0.2 |
| h7_waiting_01 | waiting_to_doorway | train | True | 0 | 0 | False | None | 4.97 | 6120 | 663.8 | True | 1909 | 1.95 | 2108 | 0.1 |
| h7_reception_02 | reception_to_corridor | val | True | 0 | 0 | False | None | 5.44 | 6120 | 860.6 | True | 1909 | 1.95 | 2110 | 0.0 |
| h7_corridor_02 | corridor_straight | val | True | 0 | 0 | False | None | 3.24 | 6120 | 768.4 | True | 1909 | 1.96 | 2117 | 0.1 |
| h7_turn_02 | turn_t_junction | test | True | 0 | 0 | False | None | 2.11 | 6120 | 638.6 | True | 1909 | 1.96 | 2119 | 0.1 |
| h7_waiting_02 | waiting_to_doorway | test | True | 0 | 0 | False | None | 4.29 | 6120 | 553.4 | True | 1909 | 1.96 | 2119 | 0.1 |

Notes:
- `bottom_third_luma` ~0 = recorded front-camera lower third is occluded (robot near-field/body); upper ~2/3 shows the hospital scene. Same `camera_link/rgb_camera` sensor used across H1–H6 (consistent, not a new defect).
- All frames are the ACTUAL recorded /camera/image_raw stream, not re-renders.