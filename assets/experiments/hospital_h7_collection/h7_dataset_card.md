# Dataset Card — H7-Hospital Front-RGB ImageNav (pilot)

| field | value |
|---|---|
| Dataset | H7-Hospital Front-RGB ImageNav (pilot) |
| Status | **dataset-quality gate — NOT trained, NOT promoted** |
| Scene | Real Isaac Sim 5.1 `hospital.usd` (S3 asset, ~1909 prims, RTX ray-traced) |
| Episodes | 8 (train 4 / val 2 / test 2) |
| Route families | reception→corridor, corridor straight, turn/T-junction, waiting→doorway (×2 variants) |
| Sensor | Yahboom M3Pro front RGB `camera_link/rgb_camera`, 640×480 |
| Recorded topics | `/camera/image_raw`, `/camera/camera_info`, `/odom`, `/tf`, `/clock`, `/cmd_vel` |
| Per-episode data | rosbag (~2 GB) + trajectory.jsonl/csv (pose/action/contact) + episode_metadata.json + scene-identity manifest |
| Expert | scripted holonomic route-follower (not a learned policy) |
| Goal | fixed `h2_weave_J` image (see caveat) |

## Provenance & integrity
- Every episode passed a **fail-closed scene-identity gate before recording**
  (`--scene hospital --scene-gate`): hospital.usd referenced, ≥1000 prims (observed
  1909), scene mode = hospital, no procedural landmark cubes, front RGB camera present.
- Recording harness: `scripts/robots/m3pro_ros2_bringup.py`; campaign orchestrator:
  `scripts/gnm/hospital_h7_record_campaign.sh` (disk guard, per-episode timeout,
  clean-DDS before/after, systemic-abort on non-zero exit).

## Quality (this pilot)
- **Route completion: 8/8.** **Total contacts: 0.** No emergency stop, no XY-bound stop.
- Scene gate: **8/8 PASS.** Artifact completeness: **8/8.** Excluded episodes: **0.**
- Contact sheets are the **actual recorded `/camera/image_raw` frames** (not re-renders).
- **Limitation:** recorded frame's lower ~third is occluded (robot near-field/body);
  usable hospital content is the upper ~2/3 (same sensor as H1–H6).

## Splits (leakage)
- train: reception_01, corridor_01, turn_01, waiting_01
- val: reception_02, corridor_02
- test: turn_02, waiting_02
- **Episode- and route-disjoint** across splits. Families are shared by **design**
  (a/b instance-disjoint): eval = unseen route *instances* of trained families (the H6
  route-instance generalization protocol). Goal image fixed across all → not
  goal-conditioning.

## Intended use
Candidate **diagnostic** training/eval data for hospital-scene ImageNav — **only after
Frank approves these artifacts.** Not for promotion, not real-robot evidence, not SOTA.

## Artifacts
`assets/experiments/hospital_h7_collection/` — `routes/`, `navmap/`, `reports/`
(quality table, split manifest, scene-identity index, artifact completeness,
collision/contact, leakage, excluded-episode), `exports/` (contact sheets),
`h7_claim_boundary.md`, this card. Scene-gate manifests:
`assets/experiments/hospital_h7_scene_gate/`.
