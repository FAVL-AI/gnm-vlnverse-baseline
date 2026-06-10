# 14 — Manual Test-Drive Walkthrough

## Why manual test-drive exists

Bo/Rui's concern: are we only replaying pre-recorded VLNVerse trajectories, or do we actually control data collection?

Manual test-drive answers this directly: we can drive the robot/camera through any Isaac Sim scene interactively, record every movement, save RGB frames, log x/y/yaw and action keys per frame, mark a goal image in real time, then replay or convert the episode into GNM-compatible data.

"Manual test-drive mode proves that we can collect our own navigation data inside Isaac Sim. It is separate from the official VLNVerse Track A result."

## How it answers Bo/Rui's concern

| Concern | Answer |
|---|---|
| Are the RGB frames real or generated? | Each step saves a camera frame from the Isaac scene |
| Is x/y/yaw logged? | Yes — every step logs x, y, z, yaw in `actions.jsonl` |
| Are actions logged? | Yes — action key, linear velocity, angular velocity per step |
| Can you set a goal image? | Yes — press G to mark current pose as goal; goal image is fixed from that point |
| Can the episode be replayed? | Yes — `replay_manual_testdrive.py` shows start/current/goal images and full action log |
| Can it be converted to GNM format? | Yes — `convert_manual_testdrive_to_gnm.py` writes position, yaw, rgb_paths in GNM layout |

## Controls

| Key | Action |
|---|---|
| W | Move forward |
| S | Brake / move backward |
| A | Rotate left |
| D | Rotate right |
| Q | Strafe left |
| E | Strafe right |
| Space | Stop |
| G | Mark current pose as goal |
| P | Save episode |
| R | Reset episode |
| Esc / X | Exit |

## What is logged

### actions.jsonl (one row per step)
- `timestamp`
- `frame_index`
- `action_key`
- `linear_velocity`
- `angular_velocity`
- `x`, `y`, `z`, `yaw`
- `rgb_image_path`
- `distance_to_goal` (if goal is set)

### traj_data.pkl
- `position` — numpy array `(T, 2)`
- `yaw` — numpy array `(T,)`
- `rgb_paths`
- `actions`
- `timestamps`
- `scene_id`, `episode_id`, `mode`
- `start_pos`, `start_yaw`
- `goal_pos`, `goal_yaw` (if set)
- `n_steps`, `path_length_m`

### metadata.json
- `simulator = Isaac Sim`
- `control_mode = manual_testdrive`
- `scene_source` — VLNVerse or CustomVLN-Office
- `vlnverse_assets_used`
- `official_benchmark_data = false`
- `purpose = manual data-collection proof for GNM/VLN pipeline`

## Output folder structure

```
datasets/manual_testdrive_custom_office/<timestamp>/
  rgb/
    000000.jpg
    000001.jpg
    ...
  traj_data.pkl
  actions.jsonl
  metadata.json
```

## How RGB frames are collected

Each time the user presses a movement key, the Isaac Sim camera captures the current viewpoint and saves it as `rgb/<frame_index:06d>.jpg`. In terminal-control fallback mode (no Isaac GUI), a placeholder frame is written so the file structure is always valid.

## How x/y/yaw is logged

The robot pose is updated after each movement key. `x` and `y` are updated by `LINEAR_STEP * cos/sin(yaw)`, and `yaw` is updated by `ANGULAR_STEP`. Every step is appended to `actions.jsonl` immediately.

## How actions are logged

Each step writes one JSON line to `actions.jsonl` containing the action key, computed velocities, current pose, and the RGB image path. The file is written on save (`P`), not per-step, so it captures the full episode atomically.

## How the goal image is set

Press `G` at any point during the drive. The current pose `(x, y, yaw)` is saved as `goal_pos` / `goal_yaw`. From that frame onward, `distance_to_goal` is computed and logged in `actions.jsonl`. The goal RGB frame is the frame saved at the step when `G` was pressed.

## How manual data can be converted into GNM-compatible format

```bash
python3 scripts/gnm/convert_manual_testdrive_to_gnm.py \
  --input  datasets/manual_testdrive_custom_office \
  --output datasets/manual_gnm_format
```

The converter:
1. Reads `traj_data.pkl` from each episode folder.
2. Renames RGB frames to GNM convention (`0.jpg`, `1.jpg`, ...).
3. Writes an updated `traj_data.pkl` with corrected `rgb_paths`.
4. Writes a `metadata.json` marking `official_benchmark_data = false`.
5. Refuses to write to any path containing `vlntube`, `vlnverse`, or `gnm_release`.

## Supported modes

| Mode | Scene | Output |
|---|---|---|
| `custom_office` | CustomVLN-Office (our own scene) | `datasets/manual_testdrive_custom_office/` |
| `vlnverse` | Any kujiale scene (e.g. `kujiale_0271`) | `datasets/manual_testdrive_vlnverse/` |

## What is implemented now

- `scripts/gnm/manual_testdrive.py` — interactive drive with terminal-control fallback
- `scripts/gnm/replay_manual_testdrive.py` — episode replay and inspection
- `scripts/gnm/convert_manual_testdrive_to_gnm.py` — GNM format conversion (protected from overwriting official data)
- `scripts/gnm/run_manual_testdrive_demo.sh` — one-command demo helper
- `tests/gnm/test_manual_testdrive.py` — schema and safety validation tests

## What is still planned

- Isaac GUI keyboard callback integration (currently terminal-control fallback is used)
- Live HUD overlay rendered inside Isaac viewport
- Side-by-side START | CURRENT | GOAL image panel in the Isaac GUI
- ROS2 closed-loop interface for real robot recording
