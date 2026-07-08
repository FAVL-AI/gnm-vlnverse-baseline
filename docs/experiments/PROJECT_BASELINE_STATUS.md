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
- **Yaw-authority investigation: COMPLETE (2026-07-08) — honest
  characterization, capability FAIL/PASS-WEAK.** Scripted harness
  (`--yaw-test`, `make validate-yaw-authority`) measured
  `yaw_tracking_ratio = measured_yaw_rate / commanded_yaw_rate` across
  pure rotations, arcs and a friction sweep:

  | wheel μ | pure rot 0.4 (L/R) | arc 0.3 (L/R) | pure rot 1.0 |
  |---|---|---|---|
  | default | 0.026 / 0.073 | 0.011 / 0.011 | 0.226 |
  | 0.35 | 0.066 / 0.118 | 0.016 / 0.019 | 0.256 |
  | 0.15 | 0.126 / 0.154 | 0.035 / 0.042 | 0.274 |

  Signs always correct; zeroing always clean; straight-line traction
  unaffected (probe 1.19 m in all runs). **Mechanism identified:** the
  sublinear response to friction proves a *geometric* moment balance —
  with plain sphere wheel colliders at wheelbase/track 0.155/0.17,
  lateral grip cancels the skid-steer yaw moment; the real M3Pro's
  mecanum rollers shed exactly this lateral load. Committed default:
  wheel μ 0.35 (balanced). **Ranked next fixes:** (1) model mecanum
  rollers properly (high fidelity, significant effort); (2) explicit
  sim-side lateral-compliance aid, clearly labelled as a simulation
  control aid; (3) constrain near-term studies to straight/low-
  curvature paths, which the stop-head research does not need turning
  for. **Scientific separation (for the paper):** hospital-scene
  failures on curved paths would be partly execution-layer control
  failures, not policy or stop-head failures — this characterization
  is the evidence that separates them.
- **Hospital-scene shadow episodes: PASS (2026-07-08).** Three
  GNM-controlled straight/low-curvature episodes in the hospital lobby
  (scene-aligned hospital goals A/B/C captured with full provenance;
  spawn via the articulation API after discovering USD parent-prim
  transforms do not survive articulation init). Stop head shadow-only
  on every row; net yaw ≤ 0.002 rad (inside the weak-yaw guard);
  clamps, stability, full-topic bags and manifests all verified by
  `make validate-hospital-shadow-episodes`.

  | episode | route | d2g start→min→final | stop head |
  |---|---|---|---|
  | `hospital_straight_short_A` | straight 2 m | 2.000→0.002→0.390 | **FIRED** @step 525, d2g 0.258 m, prob→1.000 |
  | `hospital_straight_medium_B` | straight 4 m | 4.003→0.001→0.981 | did not fire (max prob 0.000) |
  | `hospital_low_curvature_C` | low-curv 3 m | 3.025→0.394→0.708 | did not fire (max prob 0.000) |

  **Key measurement (shadow, not improvement):** in episode A, GNM's
  predicted goal distance entered its trained near-goal regime
  (9.1→1.2) and the stop head signalled STOP at 0.258 m *while still
  approaching*, before the 2 mm nearest pass; the no-authority robot
  ended at 0.390 m — the would-have-stopped analysis shows stop-at-
  signal ends 0.133 m closer than no-stop did. Episodes B/C expose a
  sharp firing boundary (GNM dist_pred floors 2.2/4.4 → no fire): the
  head fires only when GNM's own distance prediction bottoms out
  near 1, a threshold-calibration observation for the recalibration
  study, reported as recalibration, not deficiency or improvement.
  **Valid claim:** the live pipeline can evaluate stop-head shadow
  behaviour during GNM-controlled hospital-scene straight/low-
  curvature episodes.
- **Firing-boundary recalibration study: VALID (2026-07-08).** Offline
  analysis of the three live shadow episodes
  (`assets/experiments/recalibration/stop_head_boundary_20260708/`,
  `make validate-stop-boundary-study`). Boundary characterized: the
  learned head fires only when GNM's predicted goal-distance enters
  its trained near-goal regime (episode A: min 1.23; B/C floors
  2.19/4.37 → no fire), and in episode B the prediction's minimum
  occurs *early* (at-nearest value 5.45), so probability-threshold
  sweeps cannot recover B/C (still 1/3). Candidate sweep across 12
  rules (probability, predicted-distance gates, trend-reversal,
  hybrids) with measured trade-offs: **recommended recalibration
  candidate `dist_pred<=4.5, k=3` fires 3/3 with zero false stops
  (mean true stop distance 0.576 m, overshoot avoided in all three,
  max late-stop 0.655 m)**; early trend-reversal rules carry a
  measured false-stop (fires at true d2g ≈ 2.8 m in B). **Caveats
  stated:** n=3 episodes, one lobby, threshold selected in-sample —
  the candidate must be validated on held-out goals/routes before
  authority use. Notable honest observation: live, a simple
  predicted-distance gate is currently more robust than the learned
  head under this input-distribution shift (offline the learned head
  won) — a distribution-shift finding, not an improvement claim.
  **Valid claim:** live hospital shadow data identifies a calibratable
  firing boundary for the stop head. **Authority not yet tested;
  improvement not yet valid.**
- **Held-out stop-authority A/B comparison: VALID (2026-07-08) — and
  the candidate gate was REJECTED out-of-sample.** Two held-out
  start/goal pairs on the reverse lobby route (goals
  `hospital_holdout_short_D` 2.5 m, `hospital_holdout_medium_E`
  3.5 m), paired baseline vs authority episodes under identical
  envelopes (`make validate-stop-authority-comparison`, summary in
  `assets/experiments/comparisons/stop_authority_ab_20260708/`).

  | pair | baseline min→final d2g | authority stop@ (true) | authority final | Δ (auth − base) |
  |---|---|---|---|---|
  | D | 0.003→0.485 | 1.479 (early) | 1.477 | **+0.992 (worse)** |
  | E | 0.004→0.493 | 1.103 (early) | 1.100 | **+0.608 (worse)** |

  The authority *machinery* worked exactly as designed: both goal-stops
  fired via the recalibrated gate (never watchdog/e-stop), commands
  zeroed, residual motion 2.8/3.0 mm, stop types cleanly separated.
  But the in-sample threshold (dist_pred ≤ 4.5, chosen against
  calibration episode C's floor of 4.37) fired **early** on the
  held-out route, where GNM's predicted-distance profile crosses 4.5
  well before the goal — ending farther from the goal than the
  no-stop baseline in both pairs. **Finding:** GNM dist_pred scale is
  route/view-dependent; absolute-threshold gates do not transfer.
  Next recalibration directions: signals relative to the episode's
  running prediction minimum, normalized/trend-based triggers, or
  live-domain retraining of the learned head. **Valid claim:** a
  recalibrated stop gate can be given bounded authority in live Isaac
  episodes and compared against a no-stop GNM baseline on held-out
  start/goal pairs. **The improvement claim was NOT earned: on
  held-out pairs this candidate increased final distance-to-goal.**
- **Still not valid:** stop-head improvement (the tested candidate
  made it worse out-of-sample), FleetSafe improvement, success rate,
  SPL, robust hospital navigation, goal reaching as an achievement,
  curved-path navigation claims, six-run campaign.
- **Route-invariant stop recalibration study: VALID (2026-07-08).**
  Offline, no authority; tuned on A/B/C only, validated untouched on
  the held-out D/E baseline logs
  (`assets/experiments/recalibration/route_invariant_stop_20260708/`,
  `make validate-route-invariant-stop-study`). Absolute gate stays
  REJECTED on record. Two families (rel-min margin, hybrid) died in
  tuning and are recorded as such; the live-domain learned fit is
  deferred as exploratory (3 independent tuning episodes is noise).
  Three rules transfer to held-out routes (fire 2/2, zero false
  stops): trend-reversal (early: 1.41/2.40 m), the privileged
  ground-truth-d2g diagnostic (also early — true distance has local
  reversals during heading corrections, so single-scalar
  "passed-closest-approach" detection is intrinsically noisy), and
  **normalized_pred (pred ≤ 0.5 × initial, k=3): held-out D stop at
  0.173 m (retrospectively better than the 0.485 m no-stop final and
  inside a success radius), held-out E early at 1.02 m.** Preferred
  candidate for the authority rerun: `normalized_pred`, with the E
  early-stop explicitly on record. Interpretation caveat recorded:
  fixed-length baseline finals understate real overshoot, so these
  counterfactuals are conservative toward stop rules. **Valid claim:**
  existing live logs identify route-invariant stop candidates that
  avoid the failure mode of absolute predicted-distance thresholding.
  **The authority rerun is pending; improvement remains not valid.**
- **Fresh held-out normalized_pred authority rerun: VALID — candidate
  REJECTED (2026-07-08).** Two fresh pairs on a never-used westward
  route (goals `hospital_fresh_short_F` 2.0 m,
  `hospital_fresh_medium_G` 3.5 m), identical envelopes, per-episode
  self-scaling threshold verified (initial predictions 6.22/10.09
  captured live; both stops fired at normalized ratios 0.46/0.48).
  `make validate-normalized-stop-authority-comparison`; summary with
  pre-registered classification in
  `assets/experiments/comparisons/stop_authority_normalized_ab_20260708/`.

  | pair | baseline final d2g | authority stop @ (true) | authority final | Δ |
  |---|---|---|---|---|
  | F | 0.988 | 1.056 (early) | 1.053 | +0.065 (worse) |
  | G | 0.486 | 1.449 (early) | 1.447 | +0.961 (worse) |

  **Classification: REJECTED** per the pre-registered rule (early stops
  on both pairs; final distance worsened). Zeroing clean (2.7/3.0 mm
  residuals); no watchdog/e-stop contamination.
- **Cumulative finding (two falsifications):** neither absolute nor
  initial-normalized predicted-distance thresholds transfer across
  routes — GNM's predicted goal-distance maps to true progress
  differently per route/view, so the whole simple-threshold family on
  this signal appears unsuitable for termination authority. This
  directly supports the thesis position that reliable termination
  requires in-domain learned temporal stop heads (retrained on live
  episodes) or richer multi-signal rules — with held-out validation
  gating any authority, as these two rejections demonstrate.
- **Still not valid:** any stop-rule improvement (both tested
  candidates rejected), FleetSafe improvement, SR/SPL, robust hospital
  navigation, goal reaching as an achievement, curved-path claims,
  six-run campaign.
- **MobileNetV2 + EMA training ablation: COMPLETE (2026-07-08), two
  stages, baseline KEPT.** Stage 1 (offline VLN evaluation, held-out
  15-episode split): baseline SR 13.3/OSR 46.7/NE 6.14/SPL 0.133 (live
  weights); EMA 0.9999 degenerate (undertrained shadow, TL 0.13 m — its
  nominal SR 20.0 is a start-inside-radius artifact); EMA 0.999 (decay-
  horizon sanity ablation) SR 6.7/NE 6.93 despite best val loss.
  Offline Collision Rate: N/A — the offline evaluator has no physics
  contact signal. Decision per pre-registered rule: keep the original
  MobileNetV2 baseline; EMA reported as completed ablation; decay must
  match training horizon. Stage 2 (Isaac physics smoke evaluation,
  `make validate-isaac-physics-eval`): 3 straight-route episodes per
  checkpoint under the full safety envelope; **Collision Rate measured
  from PhysX chassis-contact events = 0.00 for both checkpoints (0
  contacts over 17.9 m), verified by a positive-control episode that
  logged 27 contacts against the reception desk**; SR/OSR trivially
  saturated (routes shorter than the 3 m radius — NE 0.82 m and CR are
  the informative metrics); both checkpoints saturate the safety clamp
  so executed trajectories converge. Full package:
  `assets/experiments/training_ablation/mnv2_ema_20260708/` (professor
  summary, reviewer notes C1–C5, EfficientNet appendix) and
  `assets/experiments/isaac_physics_eval/isaac_physics_smoke_20260708/`.
  Offline metrics and Isaac physics metrics are reported in separate
  tables and never mixed.
- **Next required work, in order:** grow the live episode corpus
  (more routes/goals) to enable in-domain retraining of the temporal
  stop head with scene-level holdout → held-out authority test of the
  retrained head → revalidate the campaign runs
  (`PHASE2_REQUIREMENTS.md`). Separate queued workstream: the
  MobileNetV2 + EMA training ablation (offline GNM training), to be
  run as its own controlled session.

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
