# Camera-state dashboard — acceptance smoke record (2026-07-08)

**Core requirement met: the main panel is the 2D RGB front-facing camera
view from the Yahboom robot camera lens in Isaac Sim** (MJPEG live
stream of /camera/image_raw). No 3D/top-down spectator view is used as
evidence anywhere in the UI.

Acceptance test executed end-to-end via the dashboard API:
1. Scene: hospital (selector present; goals enumerated from
   assets/experiments/goals — 8 goals).
2. Start State: auto-captured front-RGB frame at rollout start
   (start_state.jpg, 18.6 KB).
3. Goal State: front-RGB goal image for hospital_goal_A
   (goal_state.jpg, from the same camera convention as training).
4. Current State: live camera feed (camera age tracked; snapshot
   current_state.jpg).
5. Run Policy: MobileNetV2-GNM baseline checkpoint drove a recorded
   600-step episode (dash_hospital_goal_A_214942) under the full safety
   envelope with PhysX contact reporting.
6. Recorded: full-topic rosbag + trajectory.jsonl/csv +
   episode_metadata.json (checkpoint path recorded; SHA in the
   run-card/registry manifests) — **final distance-to-goal 0.0091 m,
   0 chassis contacts (measured)**, commands zeroed at end.
7. The Start/Current/Goal strip shows the ImageNav problem from the
   robot's perspective; in this run the current view visually converged
   to the goal view.

Controls present: scene selector, goal selector, checkpoint selector,
Run Policy, Record Episode, STOP/E-STOP (zero /cmd_vel + SIGINT policy
+ stop reason), metrics strip (scene, goal, checkpoint, pose, d2g,
command, contact count, recording status, camera age).

Claim labels shown in the UI: "2D RGB camera view from the robot front
camera in Isaac Sim. Not a physical-robot camera. Not a full VLNVerse
benchmark. Collision counts shown only when measured from Isaac PhysX
contact events."

Known limits (honest): single live scene (hospital) — kujiale scenes
are top-down-camera training environments, not front-camera live demos,
so they are intentionally not offered as live scenes; one policy episode
at a time; the browser UI was exercised via its HTTP API headlessly
(HTML contains all required controls; interactive click-through pending
a display session).
