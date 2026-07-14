# H7-Hospital — claim boundary

**H7-Hospital Front-RGB ImageNav** is a pilot of **real recorded hospital-scene
trajectories** in the verified Isaac Sim 5.1 `hospital.usd`. It is deliberately
**distinct from procedural-stage H6** and must not be merged with it.

## What H7 IS
- 8 scripted-expert episodes recorded in the **real hospital.usd** (1909 prims, RTX).
- Each episode passed a **fail-closed scene-identity gate BEFORE recording**
  (hospital.usd referenced, prim count ≥ threshold, scene mode = hospital, no
  procedural landmark cubes, front RGB camera present).
- Per-episode **rosbag** (`/camera/image_raw`, `/odom`, `/tf`, `/clock`, `/cmd_vel`)
  + synchronized trajectory (pose / action / contact) + episode metadata + scene-gate
  manifest.
- **Route completion 8/8, total contacts 0, no emergency stop, no XY-bound stop.**
- Visual evidence = the **actual recorded front-RGB camera stream**, not re-renders.

## What H7 is NOT
- **NOT trained, promoted, pushed, tagged, or committed** — pending Frank's review of
  these dataset-quality artifacts.
- **NOT goal-conditioning evidence** — a single fixed goal image (`h2_weave_J`) is used
  across all episodes; this is imitation-fidelity data, not goal-image conditioning.
- **NOT real-robot evidence** — Isaac simulation only.
- **NOT a state-of-the-art or navigation-quality claim.**
- **NOT the procedural-stage H6 data.** Static hospital renders (deck visuals) are
  visual proof only; H7 rosbags are the training-grade data.

## Known limitation (recorded sensor)
The recorded front-camera frame's **lower ~third is occluded** (robot near-field /
body), so usable hospital scene content is the upper ~2/3. This is the established
`camera_link/rgb_camera` sensor used across H1–H6 (consistent characteristic, not a
new defect). Flagged for Frank's decision on whether a camera pitch/mount change is
wanted before any larger (20/5/10) collection.

## Scope
8 episodes, 4 route families × 2 instance variants, one scripted expert, one seed,
offline. A dataset-quality test — **not** yet a training run.
