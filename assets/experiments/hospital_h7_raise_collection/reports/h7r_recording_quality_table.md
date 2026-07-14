# H7-Hospital RAISED-MOUNT recording quality table

Generated 2026-07-14T06:33:28. 8-episode gated pilot in the real Isaac hospital.usd, front camera raised +0.12 m (level horizon).

| episode | family | split | route_completed | total_contacts | max_contact_streak | emergency_stop | stop_reason | distance_m | steps | wall_s | camera_mount_raise_m | scene_gate_pass | hospital_prims | bag_gb | image_raw_msgs | bottom_third_luma | bottom_third_black_pct |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| h7r_reception_01 | reception_to_corridor | train | True | 0 | 0 | False | None | 5.76 | 6120 | 608.6 | 0.12 | True | 1909 | 1.96 | 2117 | 77.3 | 0.0 |
| h7r_corridor_01 | corridor_straight | train | True | 0 | 0 | False | None | 3.12 | 6120 | 658.2 | 0.12 | True | 1909 | 1.96 | 2122 | 74.7 | 0.0 |
| h7r_turn_01 | turn_t_junction | train | True | 0 | 0 | False | None | 2.39 | 6120 | 679.2 | 0.12 | True | 1909 | 1.96 | 2121 | 117.6 | 0.0 |
| h7r_waiting_01 | waiting_to_doorway | train | True | 0 | 0 | False | None | 4.97 | 6120 | 676.1 | 0.12 | True | 1909 | 1.96 | 2124 | 71.9 | 0.0 |
| h7r_reception_02 | reception_to_corridor | val | True | 0 | 0 | False | None | 5.44 | 6120 | 639.2 | 0.12 | True | 1909 | 1.96 | 2122 | 75.1 | 0.0 |
| h7r_corridor_02 | corridor_straight | val | True | 0 | 0 | False | None | 3.24 | 6120 | 580.7 | 0.12 | True | 1909 | 1.96 | 2123 | 73.1 | 0.0 |
| h7r_turn_02 | turn_t_junction | test | True | 0 | 0 | False | None | 2.11 | 6120 | 639.8 | 0.12 | True | 1909 | 1.96 | 2121 | 72.3 | 0.0 |
| h7r_waiting_02 | waiting_to_doorway | test | True | 0 | 0 | False | None | 4.29 | 6120 | 574.7 | 0.12 | True | 1909 | 1.96 | 2121 | 73.7 | 0.0 |

Notes:
- `bottom_third_black_pct` ~0 confirms the raised mount REMOVES the robot-body lower-third occlusion (original H7 pilot: fixed 38.3% black band). Higher `bottom_third_luma` = near-ground floor now visible.
- Camera raised +0.12 m on `camera_link` local +Z, rotation unchanged (level horizon / same optical axis as H1–H6).
- All frames are the ACTUAL recorded /camera/image_raw stream, not re-renders.