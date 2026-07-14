# Dataset Card — H7-Hospital Front-RGB ImageNav (raised-mount pilot)

| field | value |
|---|---|
| Dataset | H7-Hospital Front-RGB ImageNav — **raised-mount** pilot |
| Status | **dataset-quality gate — NOT trained, NOT promoted** |
| Scene | Real Isaac Sim 5.1 `hospital.usd` (S3 asset, 1909 prims, RTX ray-traced) |
| Episodes | 8 (train 4 / val 2 / test 2) |
| Route families | reception→corridor, corridor straight, turn/T-junction, waiting→doorway (×2 variants) |
| Sensor | Yahboom M3Pro front RGB `camera_link/rgb_camera`, 640×480, **raised +0.12 m (level horizon)** |
| Recorded topics | `/camera/image_raw`, `/camera/camera_info`, `/odom`, `/tf`, `/clock`, `/cmd_vel` |
| Per-episode data | rosbag (~1.96 GB) + trajectory.jsonl/csv (pose/action/contact) + episode_metadata.json + scene-identity manifest |
| Expert | scripted holonomic route-follower (not a learned policy) |
| Goal | fixed `h2_weave_J` image (see caveat) |

## Why this pilot exists (supersedes the original H7 pilot for training)
The original H7 pilot (commit `8b43e7a`) had a fixed **38.3 %** pure-black lower-third
in every recorded frame (robot-body near-field occlusion). The camera-view review
(commit `53720e7`) compared three settings and recommended raising the mount **+0.12 m**
(level horizon kept). This pilot re-records the **same 8 routes, same split, same gate,
same collision reporting** with that camera. Measured result: **bottom-third black = 0.0 %**
on all 8 episodes (floor + near-field now visible), same optical axis as H1–H6.

## Provenance & integrity
- Every episode passed a **fail-closed scene-identity gate before recording**
  (`--scene hospital --scene-gate`): hospital.usd referenced, ≥1000 prims (observed
  1909), scene mode = hospital, no procedural landmark cubes, front RGB camera present.
- Camera raise applied via `--camera-raise 0.12` (bringup authors a local +Z translate on
  `camera_link/rgb_camera`, rotation unchanged); value recorded in each
  `episode_metadata.json` (`camera_mount_raise_m`) and the campaign ledger.
- Recording harness: `scripts/robots/m3pro_ros2_bringup.py`; campaign orchestrator:
  `scripts/gnm/hospital_h7_raise_record_campaign.sh` (disk guard ≥100 G, per-episode
  timeout, clean-DDS before/after with exact-PID orphan-recorder cleanup, systemic-abort
  on non-zero exit). Episode prefix `h7r_` keeps bags/manifests/trajectories separate
  from the committed original H7 pilot (nothing overwritten).

## Quality (this pilot)
- **Route completion: 8/8.** **Total contacts: 0.** No emergency stop, no XY-bound stop.
- Scene gate: **8/8 PASS.** Artifact completeness: **8/8.** Excluded episodes: **0.**
- **Recorded lower-third black band: 0.0 % (mean, all 8)** — occlusion removed
  (original pilot: 38.3 %). Contact sheets are the **actual recorded
  `/camera/image_raw` frames** (not re-renders).
- ~2117–2124 image messages per episode; bags 1.96 GB each.

## Splits (leakage)
- train: h7r_reception_01, h7r_corridor_01, h7r_turn_01, h7r_waiting_01
- val: h7r_reception_02, h7r_corridor_02
- test: h7r_turn_02, h7r_waiting_02
- **Episode- and route-disjoint** across splits. Families are shared by **design**
  (a/b instance-disjoint): eval = unseen route *instances* of trained families (the H6
  route-instance generalization protocol). Goal image fixed across all → not
  goal-conditioning.

## Intended use
Candidate **diagnostic** training/eval data for hospital-scene ImageNav — **only after
Frank approves these artifacts.** Not for promotion, not real-robot evidence, not SOTA.

## Relationship to prior data
- **Supersedes** the original 38.3 %-occluded H7 pilot as the training candidate; the
  original stays committed as camera-baseline evidence, not merged.
- **Not** the procedural-stage H6 data. Static hospital renders are visual proof only;
  these rosbags are the training-grade data.

## Artifacts
`assets/experiments/hospital_h7_raise_collection/` — `reports/` (quality table, split
manifest, scene-identity index, artifact completeness, collision/contact, leakage,
excluded-episode, campaign ledger), `exports/` (recorded-frame contact sheets +
start/current/goal), `h7r_claim_boundary.md`, this card. Scene-gate manifests:
`assets/experiments/hospital_h7_scene_gate/` (`h7r_*`).
