# Project Baseline Status — GNM-VLNVerse / FleetSafe Phase 2

**Reset date:** 2026-07-08. Older material is retained as history but is
not valid for current claims unless revalidated under the live Isaac
pipeline described below.

## Current Valid Baseline

- **Branch:** `isaac-hospital-demo` (repo `~/robotics/gnm-vlnverse-baseline`),
  commits `9436164` → `4c04bb1`, all authored by Frank Asante Van Laarhoven.
- **Milestone:** the Yahboom M3Pro drives in Isaac Sim under external
  ROS 2 `/cmd_vel` — acceptance test **PASS**: 3.44 m in 13.3 s under a
  0.3 m/s twist published by the system ROS 2 Humble CLI (~86% velocity
  tracking, no sinking, straight line).
- **Valid implementation:** articulated Yahboom import
  (`scripts/robots/import_yahboom_urdf.py`: defaultPrim fix, authored
  primitive visuals and colliders, sphere wheel colliders, PhysX contact
  offsets and solver iterations, wheel velocity drives), ROS 2 bring-up
  with Python articulation control loop
  (`scripts/robots/m3pro_ros2_bringup.py`), scrubbed-environment ROS CLI
  pattern.
- **Valid visual evidence:** the locked hospital deck captures and the
  stop-decision distance-circle renders — as *visualisations of recorded
  data only*, so captioned.
- **DDS visibility: RESOLVED (2026-07-08).** The "asymmetric visibility"
  was a stale `ros2` daemon cache (plus a too-short discovery spin in the
  test harness), not a transport problem. After `ros2 daemon stop` from a
  clean shell, `/clock`, `/odom`, `/tf`, `/cmd_vel` are all visible and
  echo live data bidirectionally.
- **First real rosbag recorded (2026-07-08):**
  `assets/experiments/rosbags/smoke_drive_20260708` (gitignored data,
  3.4 MB) — 17.6 s, 9,906 messages while the robot drove a commanded arc:
  `/odom` 3,259, `/tf` 3,257, `/clock` 3,257, `/cmd_vel` 133. No camera
  topic yet.
- **Camera publisher: PASS (2026-07-08).** RGB camera authored on the
  robot's `camera_link`; `/camera/image_raw` (640×480 `rgb8`) and
  `/camera/camera_info` both visible and echoing from a clean external
  shell. Full-topic rosbag recorded while driving a commanded arc:
  `assets/experiments/rosbags/full_topics_20260708` (gitignored, 1.2 GB;
  SHA-256 manifest in `assets/experiments/manifests/`) — 14.7 s, 6,975
  messages: image 1,376, camera_info 1,374, odom/tf/clock 1,375 each,
  cmd_vel 100; robot stable throughout (|z| < 2 µm).
- **Per-step trajectory logging: PASS (2026-07-08).** Every live episode
  now writes `assets/experiments/trajectories/<episode_id>/`
  (`trajectory.jsonl` + `.csv` + `episode_metadata.json` with git
  commit/branch, asset paths, rosbag path, command profile, aggregate
  stats). Smoke episode `manual_arc_20260708_024944`: 800 steps, 3.98 m,
  z-drift 2 µm, full-topic rosbag (all six topics non-zero, SHA-256
  manifest committed). `scripts/gnm/validate_trajectory_log.py`
  (`make validate-trajectory-log`) checks existence, required fields,
  monotonic sim_time, motion-under-command, z stability, bag/trajectory
  duration consistency, distance plausibility — **all PASS**. Note:
  headless sim runs ~4× realtime, so bag wall durations are shorter than
  sim durations; the validator compares wall-to-wall.
- **GNM shadow inference: PASS (2026-07-08).** The published Shah et al.
  CoRL 2022 GNM checkpoint (`gnm.pth`, acquired from the upstream
  release; weights gitignored) runs real forward passes on CUDA inside
  the live episode loop, reading the same rendered frames that publish
  `/camera/image_raw`. Smoke episode `manual_arc_20260708_030319`: 266
  frames received, 261/261 successful inferences, 0 failures, mean
  latency 13.1 ms (max 156.8 ms incl. first-call warmup), 782 rows with
  non-null candidate actions in `trajectory.jsonl`. The scripted
  controller retained exclusive `/cmd_vel` control on every row
  (`actual_controller: scripted_cmd_vel`, validated per-row by
  `make validate-shadow-gnm`); the shadow module has no ROS publisher by
  construction. **Honest scope:** the smoke goal image is a fixed real
  dataset frame from a kujiale interior that does not exist in the
  bring-up scene — candidates validate the inference path, not
  navigation quality.
- **GNM closed-loop smoke control: PASS (2026-07-08).** GNM held bounded
  control authority for one 8 s episode
  (`gnm_closed_loop_20260708_031730`): 161/161 successful inferences
  (14.7 ms mean), 480 applied commands all within the smoke clamps
  (|v| ≤ 0.20 m/s, |w| ≤ 0.40 rad/s; policy-intent 0.3 m/s clipped and
  logged per row), 1.593 m travelled, z-drift 2 µm, inside ±6 m bounds,
  watchdog armed throughout, explicit zeroing verified (2 s hold,
  2.6 mm residual). The applied command is mirrored to `/cmd_vel`; the
  full-topic rosbag has all six topics non-zero (manifest committed).
  `make validate-gnm-closed-loop` passes all checks. A prior run
  additionally proved the emergency-stop path live (gross-bounds guard
  fired at step 0 and froze the robot within 0.8 mm).
  **Valid claim (narrow):** GNM can consume the simulated camera stream
  and produce bounded closed-loop velocity commands in Isaac Sim while
  the M3Pro remains stable under logged safety constraints.
- **Scene-aligned goal capture: PASS (2026-07-08).** Fixed colored
  landmark pillars added to the procedural smoke stage (shared by
  capture and episodes); `make capture-scene-goal` poses the robot at a
  target pose and saves the live camera view as the goal.
  Goal `bringup_stage_goal_A`: start (0,0,0°) → goal (2.5, 0.5, 5.7°),
  2.55 m apart; `goal_image.png` + `goal_metadata.json` (poses, scene,
  frame_id, sim time, git, capture command, SHA-256) committed under
  `assets/experiments/goals/`. `make validate-scene-goal` verifies
  checksum, live-annotator provenance at live-camera resolution, sane
  start/goal pair, and that the GNM pipeline loads the image.
  Closed-loop runs accept `--goal-id` to use scene-aligned goals.
- **Goal-conditioned closed-loop smoke: PASS (2026-07-08).** Episode
  `gnm_closed_loop_20260708_043548` ran the full safety envelope with
  the scene-aligned goal `bringup_stage_goal_A`. Distance-to-goal
  telemetry (logged per row): **1.399 m → minimum 0.498 m → final
  0.573 m** — the robot drove toward the scene-aligned goal, passed its
  nearest point, and kept going because no termination mechanism exists
  yet. `make validate-goal-conditioned-gnm` passes (base closed-loop
  checks + goal identity/provenance/loadability + telemetry + status-doc
  claim guard). **Valid claim (narrow):** GNM can run a bounded
  closed-loop smoke episode in Isaac using a goal image captured from
  the same live scene.
- **Two recorded observations (evidence, not claims):** (1) the robot
  overshot its nearest-goal point — live motivation for the stop-head
  work, which is this project's core research question; (2) commanded
  angular velocity (up to 0.18 rad/s) produced almost no yaw — skid-
  steer turning authority with sphere wheel colliders needs
  investigation before any curved-path navigation claim.
- **Stop-head shadow integration: PASS (2026-07-08).** The REAL trained
  temporal stop head (Track A checkpoint, SHA-256 `5339b755…`, loaded
  with its saved normalisation/threshold/stable-k) ran online during
  episode `gnm_closed_loop_20260708_044412`, fed by the live GNM
  signals it was trained on (goal-distance and waypoint-norm
  histories). 579 probability evaluations at 0.26 ms mean latency,
  logged per row with shadow decisions, overshoot detection and
  would-have-stopped bookkeeping. Shadow only: no authority, GNM kept
  `/cmd_vel` on every row. **Valid claim:** a stop signal can be
  computed online during live GNM closed-loop execution and logged
  against the robot's actual distance-to-goal/overshoot trajectory.
- **Honest finding (measurement, not failure of the milestone):** the
  learned head never fired (probability ~0.000 throughout). Quantified
  domain gap: GNM's predicted goal-distance tracks the approach
  correctly (4.84 → minimum 3.32 exactly at the true nearest-goal
  point → rising afterwards, i.e. the overshoot pattern IS present in
  the raw signal) but stays in the 3.2–5.0 range in this synthetic
  stage, whereas training episodes reach much lower near-goal values;
  the live 20 Hz evaluation cadence also shrinks trend features
  relative to training step cadence. Follow-ups: hospital-scene
  episodes (closer to training distribution), cadence-matched
  evaluation, and/or threshold recalibration — each must be reported
  as recalibration, not improvement.
- **Still not valid:** stop-head improvement of navigation or safety,
  FleetSafe improvement, success rate, SPL, robust hospital
  navigation, goal reaching as an achievement, six-run campaign.
- **Next required work, in order:** yaw-authority investigation →
  hospital-scene episodes (stop head still in shadow, expected closer
  to its training distribution) → GNM + stop head comparison →
  revalidate the campaign runs (`PHASE2_REQUIREMENTS.md`).

## Deprecated / Superseded Evidence

Historical material below must not be cited as evidence for the current
Phase 2 pipeline. It is retained unmodified (plus a deprecation banner)
for provenance.

| Material | Status | Why |
|---|---|---|
| `docs/v2.1` – `docs/v2.4.2` Isaac ROS 2 bridge/topic/rosbag docs | Deprecated pending revalidation | Written against the *placeholder* stage before the articulated robot existed; the current bring-up shows outbound topic visibility is still unresolved, so no "five topics live" or rosbag gate can be considered passed. No rosbag file exists in the repo (verified 2026-07-08). |
| `docs/v2.8_isaac_office_stopping_demo.md`, `docs/tracka_isaac_metrics_showcase_demo.md` and related scripts/configs | Deprecated as evidence | Replay/visualisation-class material; never live policy execution. |
| Replay-only renders (deck captures, stop-decision circles) | Valid as visualisation only | Show recorded dataset trajectories and recorded offline stop outcomes; must never be captioned as executed paths or live termination behaviour. |
| Track A offline stop-policy results (`results/bo_reviewer_packet/`, expanded audit, tag `v2.7-...`) | Valid for **offline baseline evaluation only** | CI-validated per-episode offline study with a known limitation (agent rollout paths not persisted). Must not be treated as live Isaac, rosbag, camera, or real-execution evidence; live claims require re-running under Phase 2 with trajectory logging. |
| Any "six-run campaign" table, planned rosbag/camera/live-GNM claims | Never implemented | No rosbag recording, camera publishing, or live GNM inference exists yet under the current pipeline. |

**Principle:** archive old work, do not build claims on it. Current
evidence comes only from the live pipeline: real robot in Isaac, real
ROS 2 control, real camera topics, real rosbags, real trajectory logs,
then real GNM inference.
