# H7r pre-training gate — episode / split / provenance table

data_root: `datasets/isaac_hospital_h7r`  ·  counts: {'train': 4, 'val': 2, 'test': 2}

| split | episode | family | n_frames | goal_id | camera_mount_raise_m | scene_gate_pass | route_completed | total_contacts | artifacts_complete |
|---|---|---|---|---|---|---|---|---|---|
| train | h7r_corridor_01 | corridor_straight | 177 | h2_weave_J | 0.12 | True | True | 0 | True |
| train | h7r_reception_01 | reception_to_corridor | 177 | h2_weave_J | 0.12 | True | True | 0 | True |
| train | h7r_turn_01 | turn_t_junction | 177 | h2_weave_J | 0.12 | True | True | 0 | True |
| train | h7r_waiting_01 | waiting_to_doorway | 177 | h2_weave_J | 0.12 | True | True | 0 | True |
| val | h7r_corridor_02 | corridor_straight | 177 | h2_weave_J | 0.12 | True | True | 0 | True |
| val | h7r_reception_02 | reception_to_corridor | 177 | h2_weave_J | 0.12 | True | True | 0 | True |
| test | h7r_turn_02 | turn_t_junction | 177 | h2_weave_J | 0.12 | True | True | 0 | True |
| test | h7r_waiting_02 | waiting_to_doorway | 177 | h2_weave_J | 0.12 | True | True | 0 | True |

- all frames from raised-mount recorded /camera/image_raw: **True**
- camera_mount_raise_m = 0.12 for all: **True**
- scene identity = verified hospital.usd (gate PASS) for all: **True**
- artifacts complete for all: **True**
- leakage clean (episode+route disjoint): **True**
- fixed goal image: **h2_weave_J** (placeholder; imitation-fidelity, not goal-conditioning)

## GATE: PASS