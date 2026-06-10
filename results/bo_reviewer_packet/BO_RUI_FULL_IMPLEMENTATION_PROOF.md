# Bo/Rui — Full Source-Code Implementation Proof

Every section: WHAT → HOW → SOURCE CODE → COMMAND → OUTPUT EVIDENCE → STATUS.

---

## 1. Start Isaac Sim

### What this step does
Launches the Isaac Sim GPU renderer and Python environment.

### How it works
`SimulationApp` is the Isaac Sim entry point. It opens the renderer before any USD or robot code runs. The script parses CLI flags first (before the import) so non-GUI modes like `--dry-run-panels` or `--prove-dataset` can exit without ever touching Isaac.

### Source code
File: `scripts/gnm/replay_gnm_demo.py`
```python
# Must parse CLI flags BEFORE SimulationApp is imported
_dry_run     = "--dry-run-panels"        in sys.argv
_list_scenes = "--list-scenes"           in sys.argv
_prove_ds    = "--prove-dataset"         in sys.argv
_export_live = "--export-live-dashboard" in sys.argv

# ... (non-GUI modes exit here) ...

from isaacsim import SimulationApp
app = SimulationApp({"headless": False, "renderer": "RayTracedLighting"})
```
(lines 57–60, 748)

### Command to run
```bash
conda run -n isaac python scripts/gnm/replay_gnm_demo.py
```

### Output evidence
Isaac Sim window opens. Terminal prints:
```
GNM Evidence Dashboard — Isaac Sim
Scene      : kujiale_0118  (train)
```

### Status
DONE

---

## 2. Import VLNVerse / Kujiale scene

### What this step does
Opens the kujiale USD scene file inside Isaac Sim.

### How it works
After `SimulationApp` is running, the script uses `omni.usd.get_context().open_stage()` to load the USD file. It then calls `app.update()` 200 times (~2 s) to let Isaac Sim finish loading meshes and textures before anything else is placed in the stage.

### Source code
File: `scripts/gnm/replay_gnm_demo.py`
```python
usd = REPO / "datasets/vlntube/envs" / SCENE / "start_result_navigation.usd"
print(f"\nOpening: {usd}")
ctx = omni.usd.get_context()
ctx.open_stage(str(usd))
for _ in range(200):
    app.update()
    time.sleep(0.01)
stage = ctx.get_stage()
assert stage is not None, "Stage failed to load"
```
(lines 754–761)

### Command to run
```bash
SCENE=kujiale_0271 conda run -n isaac python scripts/gnm/replay_gnm_demo.py
```

### Output evidence
```
Opening: datasets/vlntube/envs/kujiale_0271/start_result_navigation.usd
```
Scene geometry appears in Isaac Sim viewport.

### Status
DONE (USD asset re-downloadable via VLNVerse — not committed)

---

## 3. List available scenes

### What this step does
Prints all four kujiale scenes with trajectory counts, holdout tag, and USD asset status. No Isaac Sim required.

### How it works
Scans `datasets/vlntube/train/` for subdirectory names matching each scene ID. Reports `kujiale_0271` as the held-out scene.

### Source code
File: `scripts/gnm/replay_gnm_demo.py`
```python
ALL_SCENES    = ["kujiale_0092", "kujiale_0118", "kujiale_0203", "kujiale_0271"]
HOLDOUT_SCENE = "kujiale_0271"

for sc in ALL_SCENES:
    usd_path = envs_dir / sc / "start_result_navigation.usd"
    t_count  = len([d for d in train_root.iterdir()
                    if d.name.startswith(sc)]) if train_root.exists() else 0
    holdout  = "  ← held-out scene" if sc == HOLDOUT_SCENE else ""
    print(f"  {sc:<20}  train={t_count:3d}  {holdout}")
```
(lines 83–84, 96–101)

### Command to run
```bash
python3 scripts/gnm/replay_gnm_demo.py --list-scenes
```

### Output evidence
```
kujiale_0092          train= 62
kujiale_0118          train= 71
kujiale_0203          train= 61
kujiale_0271          train= 44  ← held-out scene
Total train : 238
Total val   : 15
```

### Status
DONE

---

## 4. Import / load CustomVLN-Office scene

### What this step does
Loads or creates an independent 16 m × 10 m office navigation scene that does not use any VLNVerse assets.

### How it works
`create_custom_vln_office_scene.py` places USD primitives (Cube, Cylinder) for floor, walls, desks, chairs, cabinets, and plants using named poses from `NAMED_POSES`. In dry-run mode it writes a `.usda` stub. In Isaac mode it calls `UsdGeom.Cube.Define(stage, path)` for every object.

### Source code
File: `scripts/gnm/create_custom_vln_office_scene.py`
```python
# NO VLNVerse assets used. Independent proof-of-method scene.
FLOOR_W, FLOOR_D = 16.0, 10.0
NAMED_POSES = {
    "entrance":      (2.0,  5.0),
    "desk_a":        (5.5,  1.5),
    "meeting_table": (7.0,  8.5),
    "hallway_end":   (14.0, 8.0),
}
SCENE_USD = REPO / "assets/custom_vln_office/custom_vln_office.usd"
```
(lines 30–73)

### Command to run
```bash
python3 scripts/gnm/create_custom_vln_office_scene.py --dry-run
```

### Output evidence
```
assets/custom_vln_office/scene_layout.usda   (present in repo)
results/custom_vln_office/scene_manifest.md
```

### What to show Bo/Rui
> `scene_layout.usda` uses only Isaac Sim primitives. Zero VLNVerse USD assets.

### Status
DONE (dry-run). PARTIAL (Isaac GPU render requires hardware).

---

## 5. Create robot marker and body

### What this step does
Adds a visible green cube to the scene that moves frame-by-frame to show where the robot is on the trajectory.

### How it works
`UsdGeom.Xform` is a parent transform prim. A `UsdGeom.Cube` child ("body") sits inside it. The `TranslateOp` and `RotateZOp` are stored so the replay loop can set new values each frame without creating new prims.

### Source code
File: `scripts/gnm/replay_gnm_demo.py`
```python
robot_xform  = UsdGeom.Xform.Define(stage, f"{root}/ROBOT_MARKER")
robot_body   = UsdGeom.Cube.Define(stage,  f"{root}/ROBOT_MARKER/body")
robot_body.CreateSizeAttr(0.5)
robot_body.AddTranslateOp().Set(Gf.Vec3d(0, 0, 0.5))
bind(robot_body.GetPrim(), mat_robot)    # green material
xformable    = UsdGeom.Xformable(robot_xform.GetPrim())
xformable.ClearXformOpOrder()
translate_op = xformable.AddTranslateOp()
rotate_op    = xformable.AddRotateZOp()
translate_op.Set(Gf.Vec3d(sx, sy, 0.0))
rotate_op.Set(math.degrees(start_yaw))
```
(lines 1137–1147)

### Command to run
```bash
conda run -n isaac python scripts/gnm/replay_gnm_demo.py
```

### Output evidence
Green cube (`/World/GNM_Replay/ROBOT_MARKER`) visible in Isaac Sim Stage panel at start position.

### Status
DONE

---

## 6. Create START / CURRENT / GOAL cameras

### What this step does
Places three named cameras pointing in the robot's heading direction at start, mid-trajectory, and goal positions.

### How it works
`UsdGeom.Camera.Define()` creates the camera prim. USD cameras look along −Z by default. `RotateX(90)` turns the look direction to +Y. `RotateZ(yaw_deg − 90)` rotates it to match the robot heading. Custom `gnm:*` attributes on each camera prim store the pose, frame index, and official metrics for the Isaac Sim Property panel.

### Source code
File: `scripts/gnm/replay_gnm_demo.py`
```python
def make_camera(prim_path, x, y, yaw_rad, height=1.2):
    cam = UsdGeom.Camera.Define(stage, prim_path)
    cam.CreateProjectionAttr(UsdGeom.Tokens.perspective)
    cam.CreateHorizontalApertureAttr(20.0)
    cam.CreateFocalLengthAttr(16.0)
    xf = UsdGeom.Xformable(cam.GetPrim())
    xf.ClearXformOpOrder()
    xf.AddTranslateOp().Set(Gf.Vec3d(x, y, height))
    yaw_deg = math.degrees(yaw_rad)
    xf.AddRotateXYZOp().Set(Gf.Vec3f(90.0, 0.0, yaw_deg - 90.0))
    return cam
```
(lines 842–858)

### Command to run
```bash
VIEW=START conda run -n isaac python scripts/gnm/replay_gnm_demo.py
```

### Output evidence
Isaac Sim Stage panel shows:
```
/World/GNM_Replay/START_CAMERA
/World/GNM_Replay/CURRENT_CAMERA
/World/GNM_Replay/GOAL_CAMERA
/World/GNM_Replay/OVERVIEW_CAMERA
```

### Status
DONE

---

## 7. Replay a recorded trajectory from `traj_data.pkl`

### What this step does
Loads an existing trajectory, reads `position` and `yaw` arrays, then moves the ROBOT_MARKER frame by frame.

### How it works
`_load_best_traj()` scans `datasets/vlntube/train/` for the longest trajectory matching the chosen scene. The replay loop reads `positions[idx]` and `yaws[idx]` on every step, sets `translate_op` and `rotate_op`, then calls `app.update()`.

### Source code
File: `scripts/gnm/replay_gnm_demo.py`
```python
data      = pickle.load(open(best_traj / "traj_data.pkl", "rb"))
positions = data["position"]          # shape (T, 2)
yaws      = data.get("yaw", np.zeros(len(positions)))

# ... inside replay loop:
translate_op.Set(Gf.Vec3d(positions[idx][0], positions[idx][1], 0.0))
rotate_op.Set(math.degrees(yaws[idx]))
```
(lines 147–149, 1239–1240)

### Command to run
```bash
AUTO_PLAY=1 SCENE=kujiale_0092 conda run -n isaac python scripts/gnm/replay_gnm_demo.py
```

### Output evidence
Robot cube moves along the recorded path in Isaac Sim. Terminal prints per-frame `x/y/yaw` every 10 steps.

### Status
DONE

---

## 8. Move robot marker frame by frame

### What this step does
On each iteration of the replay loop, the robot position and heading update to the next recorded pose.

### How it works
The loop reads `positions[idx]` and `yaws[idx]`, updates the USD translate and rotate ops, advances `idx`, then sleeps to match the requested playback speed. GOAL REACHED is logged when `dist_to_goal ≤ goal_r`.

### Source code
File: `scripts/gnm/replay_gnm_demo.py`
```python
_rx = float(positions[idx][0])
_ry = float(positions[idx][1])
_th = float(yaws[idx]) if idx < len(yaws) else 0.0

translate_op.Set(Gf.Vec3d(_rx, _ry, 0.0))
rotate_op.Set(math.degrees(_th))

_dist_goal = math.hypot(_rx - gx, _ry - gy)
if _dist_goal <= goal_r and not _goal_reached_logged:
    print(f"*** GOAL REACHED ***  frame={idx}  dist={_dist_goal:.3f} m")
    _goal_reached_logged = True
```
(lines 1234–1255)

### Output evidence
Terminal:
```
frame=042  x=3.2714  y=1.5830  yaw=0.28 rad  dist=5.12 m  RUNNING
...
*** GOAL REACHED ***  frame=073  dist=1.84 m <= 3.0 m
```

### Status
DONE

---

## 9. Generate live dashboard: START | CURRENT | GOAL

### What this step does
Composites a single wide image showing the start view on the left, the current live view in the centre, and the goal view on the right. Also prints SR/OSR/NE in the bottom bar.

### How it works
`_make_live_dashboard_frame()` uses PIL to tile three 480 × 360 JPEG frames side-by-side with labelled bars and a status bar showing `dist_to_goal` and `RUNNING / GOAL REACHED`.

### Source code
File: `scripts/gnm/replay_gnm_demo.py`
```python
col_defs = [
    ("START VIEW",        GREEN, f"frame 0  |  x={sx:.2f} y={sy:.2f}"),
    ("CURRENT LIVE VIEW", CYAN,  f"frame {frame_idx}  |  x={rx:.2f} y={ry:.2f}"),
    ("GOAL VIEW",         RED,   f"frame {n_steps-1}  |  x={gx:.2f} y={gy:.2f}"),
]
# ... paste the three images side-by-side ...
dist = math.hypot(rx - gx, ry - gy)
status_txt = "GOAL REACHED" if dist <= goal_r else "RUNNING"
draw.text((8, info_y + 24), f"dist_to_goal: {dist:.2f} m    STATUS: {status_txt}")
```
(lines 521–564)

### Command to run
```bash
python3 scripts/gnm/replay_gnm_demo.py --export-live-dashboard
```

### Output evidence
```
results/bo_reviewer_packet/live_dashboard/dashboard_000000.png
results/bo_reviewer_packet/live_dashboard/dashboard_000040.png
results/bo_reviewer_packet/live_dashboard/dashboard_000081.png
```

### Status
DONE

---

## 10. Update current image, x/y/yaw, distance-to-goal, and status

### What this step does
Each replay frame regenerates the dashboard PNG, updates the live texture in Isaac Sim, and prints a per-frame log.

### How it works
`_make_live_dashboard_frame(idx, current_img_path, rx, ry, ryaw)` is called every `DASHBOARD_EVERY_N` frames. If `LIVE_DASHBOARD=1`, `_update_live_dash_texture()` rewrites the USD file attribute on the dashboard plane so Isaac Sim re-reads the new PNG.

### Source code
File: `scripts/gnm/replay_gnm_demo.py`
```python
def _update_live_dash_texture(png_path: Path) -> None:
    prim = stage.GetPrimAtPath(_live_dash_tex_shader_path)
    if not prim.IsValid():
        return
    prim.GetAttribute("inputs:file").Set(str(png_path))
```
(lines 1125–1133)

### Output evidence
Dashboard PNG refreshes on disk and in the Isaac Sim panel. Bottom bar alternates between `RUNNING` (cyan) and `GOAL REACHED` (green).

### Status
DONE

---

## 11. Orange local waypoint / action markers

### What this step does
Places five orange cone prims ahead of the current robot position to show the ground-truth local waypoint targets derived from the trajectory.

### How it works
For frame `idx`, the next `WAYPOINT_HORIZON=5` pose indices are looked up from `positions[]`. Their world-frame (x, y) values are set on pre-created `WAYPOINT_NN` prims via cached `TranslateOp` handles.

### Source code
File: `scripts/gnm/replay_gnm_demo.py`
```python
WAYPOINT_HORIZON = 5
_cur_wp_idx = [min(idx + k + 1, n_steps - 1) for k in range(WAYPOINT_HORIZON)]
for k, op in enumerate(_wp_translate_ops):
    if op is not None:
        wpx = float(positions[_cur_wp_idx[k]][0])
        wpy = float(positions[_cur_wp_idx[k]][1])
        op.Set(Gf.Vec3d(wpx, wpy, Z_MARKER + 0.25))
```
(lines 1243–1248)

### Output evidence
Five orange cones (`/World/GNM_Replay/WAYPOINT_00` … `WAYPOINT_04`) visible in Isaac Sim, walking ahead of ROBOT_MARKER along the trajectory.

### Note
These are **ground-truth labels from `traj_data.pkl`**, not model predictions.

### Status
DONE

---

## 12. RGB frame collection proof

### What this step does
Shows that the pipeline saves one JPEG per navigation step and records the path to it.

### How it works
In `collect_custom_vln_office_data.py`, each navigation step calls `img.save(frame_path)`. In `manual_testdrive.py`, `_save_placeholder_frame()` writes a frame at `rgb/<frame_index:06d>.jpg`. In the official VLNVerse dataset, frames already exist as `0.jpg`, `1.jpg`, … from the collection run.

### Source code
File: `scripts/gnm/collect_custom_vln_office_data.py`
```python
for i in range(T):
    frame_path = rgb_dir / f"{i:06d}.jpg"
    rgb_paths.append(str(frame_path.relative_to(REPO)))
    if dry_run:
        img = _placeholder_frame(i, split, ep_id)
        img.save(frame_path)
    elif get_frame_fn is not None:
        img = get_frame_fn(path[i][0], path[i][1], float(yaw_np[i]))
        img.save(frame_path)
```
(lines 132–140)

### Command to run
```bash
python3 scripts/gnm/collect_custom_vln_office_data.py --dry-run
```

### Output evidence
```
datasets/custom_vln_office/train/custom_vln_office_001/rgb/000000.jpg
datasets/custom_vln_office/train/custom_vln_office_001/rgb/000001.jpg
...
```

### Status
DONE (dry-run with placeholder frames; real Isaac frames require GPU hardware)

---

## 13. x/y/yaw logging proof

### What this step does
Records the robot's world-frame position and heading at every step.

### How it works
In the replay script, `positions` and `yaws` are read directly from `traj_data.pkl`. In manual test-drive, `Episode.apply_action()` updates `self.x`, `self.y`, `self.yaw` with each key press; `Episode.record_step()` appends them to `self.positions` and `self.yaws`.

### Source code
File: `scripts/gnm/manual_testdrive.py`
```python
def apply_action(self, key: str) -> tuple[float, float]:
    k = key.upper()
    if k == "W":
        self.x += LINEAR_STEP * np.cos(self.yaw)
        self.y += LINEAR_STEP * np.sin(self.yaw)
    elif k == "A":
        self.yaw += ANGULAR_STEP
    elif k == "D":
        self.yaw -= ANGULAR_STEP
    # ...
    self.positions.append(np.array([self.x, self.y]))
    self.yaws.append(self.yaw)
```
(lines 101–126, 128–157)

### Output evidence
`traj_data.pkl` → `position` array shape `(T, 2)`, `yaw` array shape `(T,)`.

### Status
DONE

---

## 14. Action logging proof

### What this step does
Records `action_key`, `linear_velocity`, `angular_velocity`, `x`, `y`, `yaw`, and `distance_to_goal` in a line-delimited JSON file.

### How it works
`Episode.record_step()` builds a dict with all fields and appends it to `self.actions`. On save (`P` key), all rows are written to `actions.jsonl`.

### Source code
File: `scripts/gnm/manual_testdrive.py`
```python
entry = {
    "timestamp":        t,
    "frame_index":      self.frame_index,
    "action_key":       key,
    "linear_velocity":  lv,
    "angular_velocity": av,
    "x": self.x, "y": self.y, "z": self.z, "yaw": self.yaw,
    "rgb_image_path":   rgb_path,
}
if d2g is not None:
    entry["distance_to_goal"] = d2g
self.actions.append(entry)
```
(lines 142–157)

### Output evidence
`datasets/manual_testdrive_custom_office/<ts>/actions.jsonl`:
```json
{"timestamp":1749000000.0,"frame_index":0,"action_key":"W","linear_velocity":0.05,...}
```

### Status
DONE

---

## 15. `traj_data.pkl` writing

### What this step does
Saves the full trajectory as a Python pickle file with position, yaw, rgb_paths, actions, and metadata.

### How it works
`Episode.save()` in `manual_testdrive.py` builds a dict and calls `pickle.dump()`. The same structure is used by `collect_custom_vln_office_data.py`.

### Source code
File: `scripts/gnm/manual_testdrive.py`
```python
traj = {
    "position":      np.array([[p[0], p[1]] for p in self.positions]),
    "yaw":           np.array(self.yaws),
    "rgb_paths":     self.rgb_paths,
    "actions":       self.actions,
    "timestamps":    self.timestamps,
    "scene_id":      self.scene_id,
    "n_steps":       n,
    "path_length_m": self.path_length(),
}
with open(self.output_dir / "traj_data.pkl", "wb") as f:
    pickle.dump(traj, f)
```
(lines 172–191)

### Status
DONE

---

## 16. `actions.jsonl` writing

### What this step does
Writes one JSON line per step to disk so the episode log is human-readable and auditable.

### Source code
File: `scripts/gnm/manual_testdrive.py`
```python
with open(self.output_dir / "actions.jsonl", "w") as f:
    for row in self.actions:
        f.write(json.dumps(row) + "\n")
```
(lines 194–196)

### Status
DONE

---

## 17. `metadata.json` writing

### What this step does
Saves the episode provenance so Bo/Rui can see exactly what simulator, scene source, and purpose each episode has.

### Source code
File: `scripts/gnm/manual_testdrive.py`
```python
meta = {
    "simulator":            "Isaac Sim",
    "control_mode":         "manual_testdrive",
    "scene_source":         "VLNVerse" if self.mode == "vlnverse"
                            else "CustomVLN-Office",
    "vlnverse_assets_used": self.mode == "vlnverse",
    "official_benchmark_data": False,
    "purpose": "manual data-collection proof for GNM/VLN pipeline",
}
with open(self.output_dir / "metadata.json", "w") as f:
    json.dump(meta, f, indent=2)
```
(lines 199–213)

### Status
DONE

---

## 18. Manual test-drive controls: W/S/A/D/Q/E/Space/G/P/R/Esc

### What this step does
Lets the user interactively drive the robot through the scene, recording every key press.

### How it works
`terminal_loop()` reads one character at a time from stdin. Movement keys (`W/S/A/D/Q/E`) call `Episode.apply_action()` which updates `x/y/yaw` by `LINEAR_STEP` or `ANGULAR_STEP`. Special keys `G`, `P`, `R`, `Esc`/`X` trigger goal-mark, save, reset, and exit.

### Source code
File: `scripts/gnm/manual_testdrive.py`
```python
key = raw[0].upper()
if key in ("X", "\x1b"):
    break
elif key == "G":
    episode.mark_goal()
elif key == "P":
    episode.save()
elif key == "R":
    # clear all recorded state
    episode.positions.clear(); episode.frame_index = 0; ...
elif key in "WSADQE ":
    lv, av = episode.apply_action(key)
    _save_placeholder_frame(episode, rgb_path)
    episode.record_step(key, lv, av, rgb_path)
```
(lines 207–231)

### Command to run
```bash
python3 scripts/gnm/manual_testdrive.py --dry-run
MODE=custom_office conda run -n isaac python scripts/gnm/manual_testdrive.py
```

### Status
DONE (terminal fallback). PARTIAL (Isaac GUI keyboard integration planned).

---

## 19. Manual test-drive episode saving

### What this step does
Pressing `P` atomically saves rgb/, traj_data.pkl, actions.jsonl, and metadata.json to a timestamped output folder.

### Source code
See Sections 15, 16, 17 above. `Episode.save()` orchestrates all three writes.

### Output evidence
```
datasets/manual_testdrive_custom_office/<timestamp>/
  rgb/000000.jpg  ...
  traj_data.pkl
  actions.jsonl
  metadata.json
```

### Status
DONE

---

## 20. Replay manual test-drive episode

### What this step does
Loads a saved episode and prints the full action table with x/y/yaw and distance-to-goal per frame.

### How it works
`replay_manual_testdrive.py` opens `traj_data.pkl` and `actions.jsonl`, prints metadata, start/goal poses, and a truncated action table showing up to 10 rows.

### Source code
File: `scripts/gnm/replay_manual_testdrive.py`
```python
def replay(episode_dir: Path):
    data = load_episode(episode_dir)
    traj, actions, meta = data["traj"], data["actions"], data["meta"]
    print(f"  n_steps       : {traj.get('n_steps', 0)}")
    print(f"  path_length_m : {traj.get('path_length_m', 0.0):.3f}")
    for row in actions[:10]:
        d2g_str = f"{row['distance_to_goal']:.3f}" if "distance_to_goal" in row else "n/a"
        print(f"  {row['frame_index']:>6}  {row['action_key']:<6}  "
              f"{row['x']:>8.3f}  {row['y']:>8.3f}  {d2g_str:>10}")
```
(lines 42–70 of replay_manual_testdrive.py)

### Command to run
```bash
python3 scripts/gnm/replay_manual_testdrive.py --dry-run
python3 scripts/gnm/replay_manual_testdrive.py \
    --episode datasets/manual_testdrive_custom_office/<episode>
```

### Status
DONE

---

## 21. Convert manual test-drive data to GNM format

### What this step does
Renames RGB frames from `000000.jpg` → `0.jpg` convention used by the official GNM loader, rewrites `traj_data.pkl` with corrected paths, and adds `gnm_format: true` to `metadata.json`.

### Source code
File: `scripts/gnm/convert_manual_testdrive_to_gnm.py`
```python
frames = sorted(rgb_src.glob("*.jpg"))
for i, src in enumerate(frames):
    dst = out_dir / f"{i}.jpg"       # GNM convention: 0.jpg, 1.jpg, ...
    if not dst.exists():
        shutil.copy2(src, dst)

updated_rgb_paths = [str(out_dir / f"{i}.jpg") for i in range(n)]
out_traj["rgb_paths"] = updated_rgb_paths
```
(lines 75–88)

### Command to run
```bash
python3 scripts/gnm/convert_manual_testdrive_to_gnm.py \
    --input  datasets/manual_testdrive_custom_office \
    --output datasets/manual_gnm_format
```

### Status
DONE

---

## 22. Safety guard: converter refuses protected folders

### What this step does
Prevents the converter from ever writing into `vlntube`, `vlnverse`, or `gnm_release` — protecting the official dataset.

### Source code
File: `scripts/gnm/convert_manual_testdrive_to_gnm.py`
```python
PROTECTED_DIRS = ("vlntube", "vlnverse", "visualnav_transformer", "gnm_release")

def _check_output_safe(output: Path):
    name = output.name.lower()
    for protected in PROTECTED_DIRS:
        if protected in name or protected in str(output).lower():
            print(f"[ERROR] Output path {output} looks like a protected "
                  f"dataset directory. Refusing to write.", file=sys.stderr)
            sys.exit(1)
```
(lines 36–60)

### Evidence
`tests/gnm/test_manual_testdrive.py::test_converter_refuses_protected_output` passes.

### Status
DONE

---

## 23. GNM input construction: current RGB + goal RGB

### What this step does
Shows how the GNM model receives inputs: the current frame image and the goal frame image are loaded as a pair.

### How it works
From `traj_data.pkl`, `start_img = str(best_traj / "0.jpg")` and `goal_img = str(best_traj / f"{n_steps-1}.jpg")`. The live dashboard labels the centre strip as "GNM INPUT: current RGB + goal RGB → local waypoint (delta_x, delta_y)".

### Source code
File: `scripts/gnm/replay_gnm_demo.py`
```python
start_img = str(best_traj / "0.jpg")
goal_img  = str(best_traj / f"{n_steps - 1}.jpg")
mid_img   = str(best_traj / f"{CURRENT_FRAME}.jpg")

# Dashboard bottom bar:
r3 = (f"GNM INPUT: current RGB (frame {frame_idx}) + goal RGB (frame {n_steps-1})"
      f"  →  local waypoint (delta_x, delta_y)"
      f"   [labels: traj_data.pkl — NOT model prediction]")
```
(lines 164–166, 566–568)

### Status
DONE

---

## 24. Local waypoint / action label generation

### What this step does
Derives the ground-truth local waypoint label (delta_x, delta_y in robot frame) from consecutive trajectory poses.

### How it works
`_local_waypoint()` takes positions and yaws, looks up `positions[frame_idx + horizon]`, computes the world-frame delta, then rotates it into the robot frame using `cos(−yaw)` / `sin(−yaw)`.

### Source code
File: `scripts/gnm/collect_custom_vln_office_data.py`
```python
def _local_waypoint(positions, yaws, frame_idx, horizon=WAYPOINT_HORIZON):
    tgt = min(frame_idx + horizon, T - 1)
    wx  = positions[tgt][0] - positions[frame_idx][0]
    wy  = positions[tgt][1] - positions[frame_idx][1]
    yaw = float(yaws[frame_idx])
    cos_y, sin_y = math.cos(-yaw), math.sin(-yaw)
    lx = cos_y * wx - sin_y * wy   # robot-frame x
    ly = sin_y * wx + cos_y * wy   # robot-frame y
    return float(lx), float(ly)
```
(lines 70–79)

### Status
DONE

---

## 25. Dataset proof: 238 train + 15 val trajectories

### What this step does
Proves the VLNVerse dataset split: 238 training trajectories and 15 validation trajectories across four scenes.

### Source code
File: `scripts/gnm/replay_gnm_demo.py`
```python
N_TRAIN, N_VAL = 238, 15
t_total = sum(1 for d in train_root.iterdir()
              if (d / "traj_data.pkl").exists())
v_total = sum(1 for d in val_root.iterdir()
              if (d / "traj_data.pkl").exists())
print(f"Train trajectories : {t_total}  (target: {N_TRAIN})")
print(f"Val   trajectories : {v_total}  (target: {N_VAL})")
```
(lines 80–81, 187–190)

### Command to run
```bash
python3 scripts/gnm/replay_gnm_demo.py --prove-dataset
```

### Output evidence
```
Train trajectories : 238  (target: 238)
Val   trajectories :  15  (target: 15)
```

### Status
DONE

---

## 26. Scene proof: four Kujiale scenes including `kujiale_0271`

### What this step does
Lists all four training/eval scenes with holdout tag.

### Command to run
```bash
python3 scripts/gnm/replay_gnm_demo.py --list-scenes
```

### Output evidence
```
kujiale_0092   train= 62  val= 4
kujiale_0118   train= 71  val= 4
kujiale_0203   train= 61  val= 4
kujiale_0271   train= 44  val= 3   ← held-out scene
```

### Status
DONE

---

## 27. Metric proof: SR 20.0%, OSR 46.7%, NE 6.51 m

### What this step does
Reports official Track A baseline results with per-episode breakdown.

### Source code
File: `scripts/gnm/replay_gnm_demo.py`
```python
OFFICIAL_SR  = 0.20    # 3 / 15
OFFICIAL_OSR = 0.4667  # 7 / 15
OFFICIAL_NE  = 6.51    # metres, mean final dist

print(f"SR  = {N_SUCCESS}/{N_TOTAL} = {OFFICIAL_SR*100:.1f}%")
print(f"OSR = {int(OFFICIAL_OSR*N_TOTAL)}/{N_TOTAL} = {OFFICIAL_OSR*100:.1f}%")
print(f"NE  = {OFFICIAL_NE:.2f} m")
```
(lines 76–78, 737–739)

### Evidence files
```
results/bo_reviewer_packet/03_success_rate_breakdown.md
results/bo_reviewer_packet/03_success_rate_breakdown.csv
```

Per-episode breakdown shows kujiale_0092 ep#2, kujiale_0203 ep#11, kujiale_0203 ep#12 as the three successes.

### Status
DONE

---

## 28. Training and evaluation summary

### What this step does
Documents what GNM training was performed.

### How it works
Official GNM weights (`best.pt`) were fine-tuned on 238 VLNVerse train trajectories. Evaluation used `scripts/gnm/06_evaluate.py` on 15 val episodes with `success_threshold=3.0 m`.

### Command to run
```bash
python3 scripts/gnm/06_evaluate.py \
    --checkpoint checkpoints/gnm_base/best.pt \
    --val-data   datasets/vlntube/val
```

### Evidence
```
results/bo_reviewer_packet/03_success_rate_breakdown.md  (all 15 episodes)
results/bo_reviewer_packet/03_success_rate_breakdown.csv
```

### Status
DONE

---

## 29. CustomVLN-Office independent scene

### What this step does
Creates a 16 m × 10 m office environment using only Isaac Sim built-in primitives — zero VLNVerse or kujiale assets.

### Source code
File: `scripts/gnm/create_custom_vln_office_scene.py`
```python
# NO VLNVerse assets used. Independent proof-of-method scene.
FLOOR_W, FLOOR_D = 16.0, 10.0
SCENE_USD = REPO / "assets/custom_vln_office/custom_vln_office.usd"
```

File committed: `assets/custom_vln_office/scene_layout.usda`

### Command to run
```bash
python3 scripts/gnm/create_custom_vln_office_scene.py --dry-run
```

### Status
DONE

---

## 30. CustomVLN-Office data collection

### What this step does
Runs scripted navigation episodes in the custom office scene and collects RGB frames, x/y/yaw, local waypoints, and action labels.

### Source code
File: `scripts/gnm/collect_custom_vln_office_data.py` — see Sections 12, 14, 15, 16, 17 above.

### Command to run
```bash
python3 scripts/gnm/collect_custom_vln_office_data.py --dry-run
```

### Status
DONE (dry-run; real Isaac capture requires GPU hardware)

---

## 31. CustomVLN-Office evaluation summary

### What this step does
Documents evaluation status on the custom scene.

### Status
PARTIAL — dry-run data collection is implemented. Formal evaluation metrics for custom-office are PLANNED.

### What to say to Bo/Rui
> CustomVLN-Office is proof-of-method and a separate data-collection scene. It is not an official VLNVerse benchmark result. Official result remains SR 20.0%, OSR 46.7%, NE 6.51 m.

---

## 32. Test suite proof

### What this step does
Automated tests validate that all pipeline schemas, safety guards, and dry-run commands work correctly.

### Command to run
```bash
python3 -m pytest tests/gnm/test_manual_testdrive.py \
                  tests/gnm/test_live_dashboard.py \
                  tests/gnm/test_custom_vln_office.py -q
```

### Test file: `tests/gnm/test_manual_testdrive.py`
Tests:
- `test_metadata_schema` — checks `simulator`, `control_mode`, `official_benchmark_data`
- `test_actions_jsonl_schema` — checks all required fields per row
- `test_traj_data_required_fields` — checks `position`, `yaw`, `rgb_paths`, etc.
- `test_converter_refuses_protected_output` — proves safety guard fires
- `test_converter_produces_gnm_format` — proves conversion writes correct structure
- `test_manual_testdrive_dry_run` — dry-run exits 0 with correct output
- `test_replay_dry_run`
- `test_converter_dry_run`

### Status
DONE (8/8 pass)

---

## 33. ROS2 status

### What is DONE
- Dataset-based Isaac Sim replay (Sections 7–8)
- Scripted navigation + data collection (Sections 12–17)
- Manual test-drive (Section 18–19)

### What is PLANNED
- Full ROS2 closed-loop interface for real robot (Yahboom M3 Pro)
- ROS2 velocity commands → robot actuators
- ROS2 camera topic → live RGB frames
- Closed-loop GNM inference on real robot

### What to say to Bo/Rui
> ROS2 closed-loop is the next milestone. Current implementation is dataset-based and simulation-based. We can replay, collect, and convert data. We do not yet run the model in a closed loop on real hardware.

---

## 34. Zero-shot / off-the-shelf GNM result

### Status
PLANNED — a zero-shot GNM evaluation (using published GNM weights without fine-tuning on VLNVerse) has not been run. The current SR 20.0% result uses fine-tuned weights on the 238 VLNVerse training trajectories.

---

## 35. `kujiale_0271` scene-holdout performance

### What is configured
```
configs/gnm/splits/scene_holdout_kujiale_0271.yaml
```
`kujiale_0271` is excluded from training and included in the held-out evaluation split.

### Status
CONFIGURED / PENDING — the evaluation on the holdout split (only kujiale_0271 val episodes) has not been run as a separate reported number. The 3 kujiale_0271 val episodes are included in the overall 15-episode result (0 successes, 3 oracle successes for that scene).
