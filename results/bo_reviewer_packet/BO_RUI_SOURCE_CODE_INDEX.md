# Bo/Rui — Source Code Index

Every implementation claim with its source file, function, command, evidence, and status.

| # | Claim | Source file | Function / class | Command | Evidence | Status |
|---|-------|-------------|-----------------|---------|----------|--------|
| 1 | Start Isaac Sim | `scripts/gnm/replay_gnm_demo.py` | module-level (line 748) | `conda run -n isaac python scripts/gnm/replay_gnm_demo.py` | Isaac Sim window opens | DONE |
| 2 | Import VLNVerse/Kujiale scene | `scripts/gnm/replay_gnm_demo.py` | module-level (line 754) | `SCENE=kujiale_0271 conda run -n isaac python scripts/gnm/replay_gnm_demo.py` | Scene geometry in viewport | DONE |
| 3 | List available scenes | `scripts/gnm/replay_gnm_demo.py` | `--list-scenes` block (line 91) | `python3 scripts/gnm/replay_gnm_demo.py --list-scenes` | 4 scenes, counts, holdout tag | DONE |
| 4 | Load CustomVLN-Office scene | `scripts/gnm/create_custom_vln_office_scene.py` | `_write_usda_stub()` (line 76) | `python3 scripts/gnm/create_custom_vln_office_scene.py --dry-run` | `assets/custom_vln_office/scene_layout.usda` | DONE (dry-run) |
| 5 | Create robot marker / body | `scripts/gnm/replay_gnm_demo.py` | module-level (line 1137) | same as #1 | `/World/GNM_Replay/ROBOT_MARKER` in Stage | DONE |
| 6 | Create START/CURRENT/GOAL cameras | `scripts/gnm/replay_gnm_demo.py` | `make_camera()` (line 842) | `VIEW=START conda run -n isaac python scripts/gnm/replay_gnm_demo.py` | 4 camera prims in Stage | DONE |
| 7 | Replay trajectory from `traj_data.pkl` | `scripts/gnm/replay_gnm_demo.py` | `_load_best_traj()` (line 118) | `AUTO_PLAY=1 conda run -n isaac python scripts/gnm/replay_gnm_demo.py` | Robot moves, per-frame terminal log | DONE |
| 8 | Move robot marker frame by frame | `scripts/gnm/replay_gnm_demo.py` | replay loop (line 1233) | same as #7 | `translate_op.Set(Gf.Vec3d(...))` each frame | DONE |
| 9 | Live START\|CURRENT\|GOAL dashboard | `scripts/gnm/replay_gnm_demo.py` | `_make_live_dashboard_frame()` (line ~490) | `python3 scripts/gnm/replay_gnm_demo.py --export-live-dashboard` | `live_dashboard/dashboard_NNNNNN.png` | DONE |
| 10 | Update current image + status | `scripts/gnm/replay_gnm_demo.py` | `_update_live_dash_texture()` (line 1125) | same as #9 | Dashboard PNG refreshes; RUNNING/GOAL REACHED alternates | DONE |
| 11 | Orange waypoint markers | `scripts/gnm/replay_gnm_demo.py` | replay loop (line 1243) | same as #7 | 5 orange cones ahead of ROBOT_MARKER | DONE |
| 12 | RGB frame saving | `scripts/gnm/collect_custom_vln_office_data.py` | `_save_episode()` (line 107) | `python3 scripts/gnm/collect_custom_vln_office_data.py --dry-run` | `datasets/custom_vln_office/*/rgb/*.jpg` | DONE |
| 13 | x/y/yaw logging | `scripts/gnm/manual_testdrive.py` | `Episode.apply_action()` (line 101) | `python3 scripts/gnm/manual_testdrive.py --dry-run` | `traj_data.pkl` → `position (T,2)`, `yaw (T,)` | DONE |
| 14 | Action logging | `scripts/gnm/manual_testdrive.py` | `Episode.record_step()` (line 128) | same as #13 | `actions.jsonl` one row per step | DONE |
| 15 | `traj_data.pkl` writing | `scripts/gnm/manual_testdrive.py` | `Episode.save()` (line 165) | same as #13 | `traj_data.pkl` with all required fields | DONE |
| 16 | `actions.jsonl` writing | `scripts/gnm/manual_testdrive.py` | `Episode.save()` (line 193) | same as #13 | `actions.jsonl` with all required fields | DONE |
| 17 | `metadata.json` writing | `scripts/gnm/manual_testdrive.py` | `Episode.save()` (line 198) | same as #13 | `metadata.json` with provenance flags | DONE |
| 18 | Manual test-drive controls | `scripts/gnm/manual_testdrive.py` | `terminal_loop()` (line 203) | `python3 scripts/gnm/manual_testdrive.py --dry-run` | Controls list printed; dry-run exits 0 | DONE |
| 19 | Manual episode saving | `scripts/gnm/manual_testdrive.py` | `Episode.save()` (line 165) | `MODE=custom_office ... python scripts/gnm/manual_testdrive.py` | rgb/ + 3 data files in output dir | DONE |
| 20 | Replay manual episode | `scripts/gnm/replay_manual_testdrive.py` | `replay()` (line 42) | `python3 scripts/gnm/replay_manual_testdrive.py --dry-run` | Action table printed | DONE |
| 21 | Convert to GNM format | `scripts/gnm/convert_manual_testdrive_to_gnm.py` | `convert_episode()` (line 63) | `python3 scripts/gnm/convert_manual_testdrive_to_gnm.py --dry-run` | `datasets/manual_gnm_format/<ep>/0.jpg ...` | DONE |
| 22 | Safety guard (no overwrite official data) | `scripts/gnm/convert_manual_testdrive_to_gnm.py` | `_check_output_safe()` (line 45) | `pytest tests/gnm/test_manual_testdrive.py::test_converter_refuses_protected_output` | Test passes; sys.exit(1) on protected path | DONE |
| 23 | GNM input: current RGB + goal RGB | `scripts/gnm/replay_gnm_demo.py` | lines 164–166 | `python3 scripts/gnm/replay_gnm_demo.py --prove-dataset` | Dashboard bottom bar explanation | DONE |
| 24 | Local waypoint label generation | `scripts/gnm/collect_custom_vln_office_data.py` | `_local_waypoint()` (line 70) | `python3 scripts/gnm/collect_custom_vln_office_data.py --dry-run` | `traj_data.pkl` → `local_waypoints` list | DONE |
| 25 | Dataset proof: 238 train + 15 val | `scripts/gnm/replay_gnm_demo.py` | `--prove-dataset` block (line 182) | `python3 scripts/gnm/replay_gnm_demo.py --prove-dataset` | Counts + per-scene breakdown printed | DONE |
| 26 | Scene proof: 4 Kujiale scenes | `scripts/gnm/replay_gnm_demo.py` | `--list-scenes` block (line 91) | `python3 scripts/gnm/replay_gnm_demo.py --list-scenes` | All 4 scenes listed with counts | DONE |
| 27 | Metrics: SR 20.0%, OSR 46.7%, NE 6.51 m | `scripts/gnm/replay_gnm_demo.py` + evidence files | lines 76–78 | `python3 scripts/gnm/replay_gnm_demo.py --prove-dataset` | `results/bo_reviewer_packet/03_success_rate_breakdown.md` | DONE |
| 28 | GNM training + evaluation | `scripts/gnm/04_train_gnm.py`, `scripts/gnm/06_evaluate.py` | — | `python3 scripts/gnm/06_evaluate.py --checkpoint checkpoints/gnm_base/best.pt` | 15-episode breakdown in `03_success_rate_breakdown.md` | DONE |
| 29 | CustomVLN-Office scene | `scripts/gnm/create_custom_vln_office_scene.py` | `_write_usda_stub()` | `python3 scripts/gnm/create_custom_vln_office_scene.py --dry-run` | `assets/custom_vln_office/scene_layout.usda` | DONE |
| 30 | CustomVLN-Office data collection | `scripts/gnm/collect_custom_vln_office_data.py` | `_save_episode()` | `python3 scripts/gnm/collect_custom_vln_office_data.py --dry-run` | `datasets/custom_vln_office/` | DONE (dry-run) |
| 31 | CustomVLN-Office evaluation | — | — | — | — | PARTIAL / PLANNED |
| 32 | Test suite | `tests/gnm/test_manual_testdrive.py` | all 8 tests | `pytest tests/gnm/test_manual_testdrive.py -q` | 8 passed | DONE |
| 33 | ROS2 closed-loop | — | — | — | — | PLANNED |
| 34 | Zero-shot GNM (no fine-tune) | — | — | — | — | PLANNED |
| 35 | kujiale_0271 holdout split eval | `configs/gnm/splits/scene_holdout_kujiale_0271.yaml` | — | — | Config exists; separate metric run pending | CONFIGURED / PENDING |
