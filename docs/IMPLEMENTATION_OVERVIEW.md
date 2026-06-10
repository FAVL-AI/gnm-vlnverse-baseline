# Implementation Overview

Step-by-step explanation of the GNM/VLNVerse baseline pipeline.

---

## Step 1: Start Isaac Sim

Isaac Sim is launched via the `SimulationApp` entry point. CLI flags are parsed before `SimulationApp` is imported, so non-GPU modes (`--prove-dataset`, `--list-scenes`, `--export-live-dashboard`) can run without a GPU.

```python
from isaacsim import SimulationApp
app = SimulationApp({"headless": False, "renderer": "RayTracedLighting"})
```

Source: `scripts/gnm/replay_gnm_demo.py`, line 748.

---

## Step 2: Load scene

The kujiale USD scene is opened via the Isaac Sim USD context. The script waits 200 render updates (~2 s) for meshes and textures to finish loading.

```python
usd = REPO / "datasets/vlntube/envs" / SCENE / "start_result_navigation.usd"
ctx = omni.usd.get_context()
ctx.open_stage(str(usd))
for _ in range(200):
    app.update(); time.sleep(0.01)
stage = ctx.get_stage()
```

Source: `scripts/gnm/replay_gnm_demo.py`, line 754.

---

## Step 3: Place cameras

Three named USD cameras are placed at the robot's start, mid-trajectory, and goal poses. Each camera points in the robot heading direction. Custom `gnm:*` attributes store pose, frame index, and metric values on each prim for the Isaac Sim Property panel.

```python
cam = UsdGeom.Camera.Define(stage, prim_path)
xf.AddTranslateOp().Set(Gf.Vec3d(x, y, height))
xf.AddRotateXYZOp().Set(Gf.Vec3f(90.0, 0.0, yaw_deg - 90.0))
```

Source: `scripts/gnm/replay_gnm_demo.py`, `make_camera()`, line 842.

---

## Step 4: Load trajectory from `traj_data.pkl`

The trajectory data is loaded from the dataset. `position` is a (T, 2) array of world-frame (x, y) coordinates. `yaw` is a (T,) array of robot headings in radians.

```python
data      = pickle.load(open(best_traj / "traj_data.pkl", "rb"))
positions = data["position"]   # shape (T, 2)
yaws      = data.get("yaw", np.zeros(len(positions)))
```

Source: `scripts/gnm/replay_gnm_demo.py`, line 147.

---

## Step 5: Replay trajectory

The replay loop reads each frame's pose from `positions[idx]` and `yaws[idx]`, moves the ROBOT_MARKER USD prim, and updates orange waypoint cone positions to show the next five lookahead targets.

```python
translate_op.Set(Gf.Vec3d(positions[idx][0], positions[idx][1], 0.0))
rotate_op.Set(math.degrees(yaws[idx]))
```

Source: `scripts/gnm/replay_gnm_demo.py`, line 1239.

---

## Step 6: Save RGB frames and pose

For each navigation step, the RGB image from the Isaac camera is saved as a JPEG. The pose (x, y, yaw) is appended to the trajectory arrays.

In the manual test-drive, each key press calls `Episode.apply_action()` which updates x/y/yaw, then `Episode.record_step()` which appends to the trajectory and writes an entry to `actions.jsonl`.

Source: `scripts/gnm/manual_testdrive.py`, `Episode.apply_action()` and `Episode.record_step()`, lines 101–157.

---

## Step 7: Build GNM input

The GNM model receives two images: the current RGB frame (frame `i`) and the goal RGB frame (last frame of the episode). These are read from disk by path.

```python
start_img = str(best_traj / "0.jpg")
goal_img  = str(best_traj / f"{n_steps - 1}.jpg")
mid_img   = str(best_traj / f"{CURRENT_FRAME}.jpg")
```

Source: `scripts/gnm/replay_gnm_demo.py`, line 164.

---

## Step 8: Derive local waypoint label

The ground-truth local waypoint label for frame `i` is the position `horizon` frames ahead, rotated from world frame into robot frame using the current heading.

```python
def _local_waypoint(positions, yaws, frame_idx, horizon):
    tgt = min(frame_idx + horizon, T - 1)
    wx  = positions[tgt][0] - positions[frame_idx][0]
    wy  = positions[tgt][1] - positions[frame_idx][1]
    cos_y, sin_y = math.cos(-yaws[frame_idx]), math.sin(-yaws[frame_idx])
    lx = cos_y * wx - sin_y * wy
    ly = sin_y * wx + cos_y * wy
    return float(lx), float(ly)
```

Source: `scripts/gnm/collect_custom_vln_office_data.py`, `_local_waypoint()`, line 70.

These labels are derived from trajectory poses. They are **not** model predictions.

---

## Step 9: Evaluate

The evaluation script loads the fine-tuned GNM checkpoint and runs inference on the 15 validation episodes. For each episode, it computes final distance to goal, minimum distance to goal, and path length. Success is determined by `final_dist <= success_threshold (3.0 m)`.

Current result: SR 20.0%, OSR 46.7%, NE 6.51 m.

Source: `scripts/gnm/06_evaluate.py`.

---

## Step 10: Export replay dashboard

The live dashboard composites three image columns (START VIEW, CURRENT LIVE VIEW, GOAL VIEW) side by side using PIL, with a status bar showing distance-to-goal, RUNNING/GOAL REACHED status, and the official metrics.

```python
col_defs = [
    ("START VIEW",        GREEN, f"frame 0  |  x={sx:.2f} y={sy:.2f}"),
    ("CURRENT LIVE VIEW", CYAN,  f"frame {frame_idx}  |  x={rx:.2f} y={ry:.2f}"),
    ("GOAL VIEW",         RED,   f"frame {n_steps-1}  |  x={gx:.2f} y={gy:.2f}"),
]
```

Source: `scripts/gnm/replay_gnm_demo.py`, `_make_live_dashboard_frame()`, line ~490.

Command (no Isaac required):

```bash
python3 scripts/gnm/replay_gnm_demo.py --export-live-dashboard
```

---

## Step 11: Manual test-drive

The manual test-drive allows a user to drive the robot interactively and collect data. Key presses update x/y/yaw and log an entry to `actions.jsonl`. Pressing G marks the current pose as the goal. Pressing P saves the episode to disk.

Source: `scripts/gnm/manual_testdrive.py`, `terminal_loop()` and `Episode.save()`.

Command (dry-run, no Isaac required):

```bash
python3 scripts/gnm/manual_testdrive.py --dry-run
```

---

## Step 12: Convert to GNM format

Saved manual episodes are converted to GNM dataset format by renaming RGB frames from `000000.jpg` to `0.jpg`, rewriting `traj_data.pkl` with corrected paths, and marking `metadata.json` with `official_benchmark_data: false`.

The converter refuses to write into any path containing `vlntube`, `vlnverse`, or `gnm_release`.

Source: `scripts/gnm/convert_manual_testdrive_to_gnm.py`, `convert_episode()` and `_check_output_safe()`.
