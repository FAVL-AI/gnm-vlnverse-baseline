# GNM / VLNVerse Reproduction — Changelog

Branch: `gnm-vlnverse-baseline`  
Official Track A result: **SR 20.0%  OSR 46.7%  NE 6.51 m**

---

## 2026-06-09

### Live GNM Input Dashboard (`fix(gnm): add live start current goal dashboard replay`)
- Added `--export-live-dashboard` CLI mode to `replay_gnm_demo.py`
- Generates per-frame three-column PNG sequence: `START VIEW | CURRENT LIVE VIEW | GOAL VIEW`
- RUNNING / GOAL REACHED status overlay per frame; stops correctly at `dist_to_goal ≤ success_radius`
- `LIVE_DASHBOARD=1 AUTO_PLAY=1` Isaac Sim mode: `/World/GNM_Replay/LIVE_GNM_INPUT_DASHBOARD` texture plane updated each frame; orange cones repositioned per frame
- Optional `EXPORT_LIVE_VIDEO=1` mp4 export via imageio/ffmpeg
- 93-frame sequence committed to `results/bo_reviewer_packet/live_dashboard/`
- New reviewer doc: `results/bo_reviewer_packet/13_live_gnm_input_dashboard.md`
- 11 new tests in `tests/gnm/test_live_dashboard.py`; all 101 suite tests pass

### CustomVLN-Office Independent Scene (`feat(gnm): add custom Isaac asset office navigation environment`)
- Separate independent Isaac Sim office environment — no VLNVerse assets used
- Scripts: `discover_isaac_assets.py`, `create_custom_vln_office_scene.py`, `collect_custom_vln_office_data.py`, `manual_custom_vln_office_drive.py`, `replay_custom_vln_office.py`, `evaluate_custom_vln_office.py`, `run_custom_vln_office_demo.sh`
- 8 navigation episodes (6 train, 2 val) in `configs/custom_vln_office/tasks.yaml`
- 15 passing dry-run tests in `tests/gnm/test_custom_vln_office.py`
- Reviewer doc: `results/bo_reviewer_packet/12_custom_vln_office_independent_isaac_scene.md`
- **This is not an official VLNVerse result** — it is a proof-of-method

### Guided Evidence Tour and Dataset Proof (`fix(gnm): add guided evidence tour and dataset proof`)
- `TOUR=1` mode: auto-switches START/CURRENT/GOAL/OVERVIEW cameras and saves screenshots
- `EVIDENCE_HUD_PANEL`: floating plane showing full evidence chain inside Isaac Sim
- `GNM_INPUT_PANEL`: side-by-side current obs + goal image
- `SCENE=kujiale_0271` support (held-out scene)
- `--list-scenes` and `--prove-dataset` CLI modes
- Orange waypoint cones `WAYPOINT_00–04` with `gnm:type="local_waypoint_target"` and `gnm:source="derived_from_traj_data_pkl"`
- Reviewer doc: `results/bo_reviewer_packet/10_full_evidence_chain.md`

### Camera USD Attribute Metadata (`fix(gnm): expose camera validation metrics in Isaac replay`)
- `START_CAMERA`, `CURRENT_CAMERA`, `GOAL_CAMERA` prims each carry 14 `gnm:*` custom attributes visible in Isaac Sim Property panel
- Attributes include: `gnm:role`, `gnm:scene_id`, `gnm:episode_id`, `gnm:x`, `gnm:y`, `gnm:yaw_rad`, `gnm:yaw_deg`, `gnm:frame_index`, `gnm:image_path`, `gnm:success_rate`, `gnm:oracle_success_rate`, `gnm:navigation_error_m`, `gnm:dataset_train_trajectories`, `gnm:dataset_val_trajectories`
- Reviewer doc: `results/bo_reviewer_packet/09_isaac_camera_click_validation.md`

---

## Dataset summary

| Split | Trajectories | Scenes |
|-------|-------------|--------|
| Train | 238 | kujiale_0092, kujiale_0118, kujiale_0203, kujiale_0271 |
| Val   | 15  | kujiale_0092, kujiale_0118, kujiale_0203 |

kujiale_0271 is the scene-holdout scene: present in train split, not in val. Scene-holdout training/evaluation is config-ready but not yet run.

---

## Official Track A result (unchanged)

| Metric | Value |
|--------|-------|
| Success Rate (SR)       | 3/15 = 20.0% |
| Oracle Success Rate (OSR) | 7/15 = 46.7% |
| Navigation Error (NE)   | 6.51 m |

SR < OSR because the distance predictor did not trigger a stop in time on several episodes that did pass within 3 m. See `results/bo_reviewer_packet/03_success_rate_breakdown.md`.

---

## Pending

- Scene-holdout kujiale_0271 training run (config at `configs/gnm/splits/scene_holdout_kujiale_0271.yaml`)
- Scene-holdout val evaluation (cannot claim result until this is run)
- Fine-tuning GNM on CustomVLN-Office data
