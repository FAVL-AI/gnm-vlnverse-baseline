# Isaac Sim live smoke evaluation — final evidence (selected baseline checkpoint)

Checkpoint: `checkpoints/ablation_mnv2_baseline/best.pt` sha256 `b7bac92ef7a9960d…`

| route | goal | start→min→final d2g (m) | path (m) | contacts | e-stop | zero residual (m) |
|---|---|---|---:|---:|---|---:|
| straight_short | hospital_goal_A | 2.0→0.002→0.988 | 2.988 | 0 | False | 0.00249 |
| straight_medium | hospital_goal_B | 4.003→0.004→0.98 | 4.983 | 0 | False | 0.00249 |
| low_curvature_safe | hospital_goal_C | 3.025→0.397→0.71 | 3.587 | 0 | False | 0.00249 |

Aggregate: NE 0.893 m | Collision Rate (episode) **0.0 — measured** | contacts 0 over 11.56 m | SR/OSR see caveat.

routes A/D-length (2-4 m) partially within/near the 3 m radius; NE and CR are the informative metrics.

physx_contact_report_base_link (wheel-floor excluded); zeros verified by prior positive control.

Visual artifact: onboard-camera mp4 extracted from the straight_medium rosbag (`assets/experiments/videos_local/livefinal_straight_medium_onboard.mp4`, gitignored; sha256 in video_manifest).
