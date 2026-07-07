# Phase 2 Requirements — Live GNM-in-Isaac Experiment Pipeline

Successor to the Phase 1 replay campaign
(`2026-07-08_isaac_hospital_stop_decision_campaign.md`). Phase 1's central
lesson drives R1: the Track A evaluation rolled out the GNM agent without
persisting trajectories, so stop *positions* were unrecoverable afterwards.

## Must-have requirements

- **R1 — Agent trajectory logging.** Every episode logs the agent's full
  rollout: per-step position, yaw, timestamp, and the stop-policy signal
  values, to `trajectory.json` (or `.npz`) alongside the episode outputs.
  No evaluation run is valid without it.
- **R2 — rosbag recording.** Automatic per-episode rosbag with at minimum
  `/camera/image_raw`, `/odom`, `/tf`, `/cmd_vel` (add `/scan` when the
  lidar publisher is wired). Start from the OmniGraph publisher stubs in
  `assets/robots/yahboom_m3_pro/yahboom_m3pro_visible_placeholder.usda`.
- **R3 — Video from the locked cameras.** Per-episode video from both
  approved views (first-person start→goal and lobby overview), same
  framing rules as Phase 1 (`docs/ISAAC_HOSPITAL_ENVIRONMENT.md`).
- **R4 — Metrics and manifest.** Per-episode `metrics.json` plus a
  campaign `run_manifest_*.json` extending the Phase 1 schema with rosbag
  topic list, duration, and bag SHA-256.
- **R5 — Multi-policy support.** `--policy {baseline,waypoint,temporal}`
  runs the same episodes with identical seeds through a shared trajectory
  logger so per-policy outcomes are directly comparable.
- **R6 — Honest artifact labelling.** Every rendered artifact states
  whether it shows a live rollout or a replay/visualisation. Slide and
  paper captions must not describe demonstration paths as executed paths.

## Acceptance criteria

1. For each episode and policy, `dist(logged_final_position, goal)` equals
   the reported `final_dist_m` within 1 cm — closing the Phase 1
   provenance gap by construction.
2. SR recomputed from the logged trajectories matches the summary CSV for
   the same split.
3. Each rosbag replays cleanly (`ros2 bag info` lists all required topics
   with nonzero message counts).

## Nice-to-have

- Photoreal or mesh-based M3Pro model to replace the primitive placeholder.
- Failure-case gallery auto-generated from logged rollouts (overshoot,
  premature stop, never-fire) — real Phase 2 counterpart of the Phase 1
  distance circles.
