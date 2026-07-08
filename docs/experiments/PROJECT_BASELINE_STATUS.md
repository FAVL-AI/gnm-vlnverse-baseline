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
- **Not yet valid:** live GNM inference from the simulated camera, any
  policy-navigation claim, the six-run campaign.
- **Next required work, in order:** GNM inference loop on the simulated
  camera feed — **shadow mode first** (GNM reads `/camera/image_raw` and
  logs candidate actions into the trajectory log while the scripted
  controller keeps driving; GNM gets `/cmd_vel` control only after shadow
  inference is validated) → GNM + stop head comparison → revalidate the
  campaign runs (`PHASE2_REQUIREMENTS.md`).

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
