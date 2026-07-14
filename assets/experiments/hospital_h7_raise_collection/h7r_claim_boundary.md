# H7-Hospital (raised-mount) — claim boundary

**H7-Hospital Front-RGB ImageNav (raised-mount pilot)** is a re-record of the 8-route
hospital pilot in the verified Isaac Sim 5.1 `hospital.usd`, with the front camera
raised **+0.12 m (level horizon)** to remove the robot-body lower-third occlusion. It is
deliberately **distinct from procedural-stage H6** and must not be merged with it.

## What this pilot IS
- 8 scripted-expert episodes recorded in the **real hospital.usd** (1909 prims, RTX).
- Each episode passed a **fail-closed scene-identity gate BEFORE recording**
  (hospital.usd referenced, prim count ≥ threshold, scene mode = hospital, no
  procedural landmark cubes, front RGB camera present).
- Per-episode **rosbag** (`/camera/image_raw`, `/odom`, `/tf`, `/clock`, `/cmd_vel`)
  + synchronized trajectory (pose / action / contact) + episode metadata (incl.
  `camera_mount_raise_m = 0.12`) + scene-gate manifest.
- **Route completion 8/8, total contacts 0, no emergency stop, no XY-bound stop.**
- **Recorded lower-third black band 0.0 % (mean, all 8)** — occlusion removed vs the
  original pilot's fixed 38.3 %. Visual evidence = the **actual recorded front-RGB
  camera stream**, not re-renders.

## What this pilot is NOT
- **NOT trained, promoted, pushed, tagged, or committed** — pending Frank's review of
  these dataset-quality artifacts.
- **NOT goal-conditioning evidence** — a single fixed goal image (`h2_weave_J`) across
  all episodes; imitation-fidelity data, not goal-image conditioning.
- **NOT real-robot evidence** — Isaac simulation only.
- **NOT a state-of-the-art or navigation-quality claim.**
- **NOT the procedural-stage H6 data.**

## Camera change (auditable, non-destructive)
- Applied via opt-in `--camera-raise 0.12`: a local +Z translate on
  `camera_link/rgb_camera`; **rotation unchanged** → level horizon and the same optical
  axis as the H1–H6 sensor. Default (`0.0`) leaves the prior sensor untouched, so H1–H6
  reproducibility is preserved.
- The original 38.3 %-occluded H7 pilot remains committed (`8b43e7a`) as camera-baseline
  evidence; the camera-view review that motivated this change is committed (`53720e7`).

## Scope
8 episodes, 4 route families × 2 instance variants, one scripted expert, one seed,
offline. A dataset-quality test — **not** yet a training run.
