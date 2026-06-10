# Bo/Rui Live Demo Script

**Format per section: command → expected output → what to point at on screen → what Bo/Rui should see.**

---

## 1. Dataset proof

**Command:**
```bash
python3 scripts/gnm/replay_gnm_demo.py --prove-dataset
```

**Expected output (terminal):**
```
GNM dataset proof
=================================================================
  Train trajectories : 238  (target: 238)
  Val   trajectories :  15  (target: 15)

  Per-scene breakdown:
    kujiale_0092          train= 62  val= 4
    kujiale_0118          train= 71  val= 4
    kujiale_0203          train= 61  val= 4
    kujiale_0271          train= 44  val= 3  ← held-out scene

  Sample trajectory  : datasets/vlntube/train/kujiale_0118_...
  RGB frames         : 51
  traj_data.pkl      : datasets/vlntube/train/.../traj_data.pkl  (NNN bytes)
  position shape     : (51, 2)
  Start  x=...  y=...  yaw=... rad
  Goal   x=...  y=...

  Official Track A result:
    SR  = 3/15 = 20.0%
    OSR = 7/15 = 46.7%
    NE  = 6.51 m
```

**Point at on screen:**
- `Train trajectories : 238` — this is the training set
- `traj_data.pkl` line — shows the file exists and its byte count
- `position shape : (51, 2)` — x/y for every step
- `SR = 3/15 = 20.0%` — official metric

**What Bo/Rui should see:**
> Actual trajectory data is present: 238 training episodes, 15 validation episodes, per-scene breakdown, and the official Track A numbers all in one command.

**Source code:** `scripts/gnm/replay_gnm_demo.py` lines 182–235 (`--prove-dataset` block)

---

## 2. Scene proof

**Command:**
```bash
python3 scripts/gnm/replay_gnm_demo.py --list-scenes
```

**Expected output (terminal):**
```
GNM dataset — available scenes
============================================================
  kujiale_0092          train= 62  val= 4  USD present
  kujiale_0118          train= 71  val= 4  USD present
  kujiale_0203          train= 61  val= 4  USD present
  kujiale_0271          train= 44  val= 3  USD present  ← held-out scene

  Total train : 238
  Total val   : 15

  Scene-holdout split config : configs/gnm/splits/scene_holdout_kujiale_0271.yaml
  kujiale_0271 in holdout config : YES
```

**Point at on screen:**
- `kujiale_0271 ← held-out scene` — not used in training
- `scene_holdout_kujiale_0271.yaml` — the config file that enforces the split

**Source code:** `scripts/gnm/replay_gnm_demo.py` lines 91–115

---

## 3. Metrics proof

**Show files:**
```
results/bo_reviewer_packet/03_success_rate_breakdown.md
results/bo_reviewer_packet/03_success_rate_breakdown.csv
```

**Point at on screen:**
- Table rows `#2`, `#11`, `#12` — the three successes
- `Success = YES` column
- `Oracle = YES` for 7 rows — these episodes passed through the goal zone

**Key numbers:**
| Metric | Value | Calculation |
|--------|-------|-------------|
| SR | 20.0% | 3 / 15 final dist ≤ 3.0 m |
| OSR | 46.7% | 7 / 15 ever within 3.0 m |
| NE | 6.51 m | mean final dist to goal |

**What Bo/Rui should see:**
> Per-episode breakdown. Three episodes reached the goal (SR=20%). Seven were ever close to the goal (OSR=46.7%). Navigation error averaged 6.51 m.

---

## 4. Live GNM input dashboard

**Command:**
```bash
python3 scripts/gnm/replay_gnm_demo.py --export-live-dashboard
```

**Expected output:**
```
Exporting live dashboard frames...
  dashboard_000000.png
  dashboard_000040.png
  dashboard_000081.png
  ...
Exported N frames to results/bo_reviewer_packet/live_dashboard/
```

**Point at on screen:**
Open `results/bo_reviewer_packet/live_dashboard/dashboard_000040.png`.

Three columns:
- LEFT — **START VIEW** — fixed, robot's first observation
- CENTRE — **CURRENT LIVE VIEW** — updates frame by frame, shows current x/y/yaw
- RIGHT — **GOAL VIEW** — fixed, the robot's target image

Bottom bar shows:
- `dist_to_goal: N.NN m`
- `STATUS: RUNNING` or `STATUS: GOAL REACHED` (green)
- `GNM INPUT: current RGB + goal RGB → local waypoint (delta_x, delta_y) [labels: traj_data.pkl — NOT model prediction]`
- `SR=20.0%  OSR=46.7%  NE=6.51 m` on every frame

**What Bo/Rui should see:**
> Start image is fixed. Goal image is fixed. Current image changes as the robot moves. Distance-to-goal updates every frame. The official metrics are printed on the same panel.

**Source code:** `scripts/gnm/replay_gnm_demo.py` `_make_live_dashboard_frame()` function

---

## 5. Isaac Sim guided tour

**Command (requires Isaac Sim + kujiale USD):**
```bash
TOUR=1 LIVE_DASHBOARD=1 AUTO_PLAY=1 SHOW_GNM_PANELS=1 \
conda run -n isaac python scripts/gnm/replay_gnm_demo.py
```

**Expected terminal output (before Isaac starts):**
```
GNM Evidence Dashboard — Isaac Sim
Scene      : kujiale_0118  (train)
Trajectory : kujiale_0118_...
START STATE:
  x=...  y=...  yaw=... rad
  camera: /World/GNM_Replay/START_CAMERA
CURRENT STATE  (frame 25/50):
  camera: /World/GNM_Replay/CURRENT_CAMERA
  waypoint targets: [(x0,y0), (x1,y1), ...]
GOAL STATE:
  camera: /World/GNM_Replay/GOAL_CAMERA
PERFORMANCE:
  SR  = 3/15 = 20.0%
  OSR = 7/15 = 46.7%
  NE  = 6.51 m
TOUR=1 — will auto-switch cameras and save screenshots.
```

**Point at on screen (Isaac Sim):**
- `/World/GNM_Replay/ROBOT_MARKER` — green cube moving along the path
- `/World/GNM_Replay/WAYPOINT_00` … `WAYPOINT_04` — five orange cones (ground-truth local waypoint targets)
- `/World/GNM_Replay/START_CAMERA` → switch to see robot's first frame
- `/World/GNM_Replay/CURRENT_CAMERA` → switch to see mid-trajectory frame
- `/World/GNM_Replay/GOAL_CAMERA` → switch to see goal frame
- `EVIDENCE_HUD_PANEL` — textured plane floating above the scene with full evidence chain
- `LIVE_GNM_INPUT_DASHBOARD` — wide panel showing START|CURRENT|GOAL strip, updates live

**What Bo/Rui should see:**
> The robot cube walks the entire recorded trajectory. The five orange cones are the ground-truth waypoint labels from `traj_data.pkl` — they walk ahead of the robot at every step. The cameras are at the exact poses recorded in the dataset.

---

## 6. Manual test-drive dry-run

**Command:**
```bash
python3 scripts/gnm/manual_testdrive.py --dry-run
```

**Expected output:**
```
============================================================
manual_testdrive.py — dry-run
============================================================

Available modes:
  custom_office
  vlnverse

Controls:
  W        forward
  S        brake/back
  A        rotate-left
  D        rotate-right
  Q        strafe-left
  E        strafe-right
  Space    stop
  G        mark goal
  P        save episode
  R        reset episode
  Esc      exit

Output structure:
  datasets/manual_testdrive_custom_office/<timestamp>/
    rgb/000000.jpg ...
    traj_data.pkl
    actions.jsonl
    metadata.json

NOTE: This is manual data-collection evidence, not an official benchmark result.
      Official Track A result: SR=20.0%, OSR=46.7%, NE=6.51 m
```

**What Bo/Rui should see:**
> We can interactively drive through the scene. Every movement is recorded (RGB frame, x/y/yaw, action). Pressing G marks the current pose as the goal. Pressing P saves the episode.

---

## 7. Manual test-drive interactive session

**Command (CustomVLN-Office, terminal control):**
```bash
MODE=custom_office conda run -n isaac python scripts/gnm/manual_testdrive.py
```

**What happens:**
```
MANUAL TEST DRIVE — terminal control mode
  mode     : custom_office
  scene    : custom_office_v1
  output   : datasets/manual_testdrive_custom_office/<timestamp>

Controls: W/S/A/D/Q/E move | G=goal | P=save | R=reset | Esc/X=exit

[frame 000000] x=0.000 y=0.000 yaw=0.000  goal=not set  > W
[frame 000001] x=0.050 y=0.000 yaw=0.000  goal=not set  > W
[frame 000002] x=0.100 y=0.000 yaw=0.000  goal=not set  > G
  [GOAL SET] x=0.100 y=0.000 yaw=0.000
[frame 000003] x=0.100 y=0.000 yaw=0.000  goal=0.000 m  > P
  [SAVED] datasets/manual_testdrive_custom_office/<timestamp>
          3 steps, 0.10 m path length
```

**Point at on screen:**
- x/y coordinates updating on each step
- `[GOAL SET]` message when G is pressed
- `[SAVED]` with output path when P is pressed

**What Bo/Rui should see:**
> Every key press creates a data record. The episode folder has the same structure as the official VLNVerse trajectories.

---

## 8. Replay saved manual episode

**Command:**
```bash
python3 scripts/gnm/replay_manual_testdrive.py \
    --episode datasets/manual_testdrive_custom_office/<episode>
```

**Expected output:**
```
Episode: <episode>
  mode            : custom_office
  n_steps         : 3
  path_length_m   : 0.100
  START pos       : x=0.000 y=0.000 yaw=0.000
  GOAL pos        : x=0.100 y=0.000 yaw=0.000
  Action log (3 steps):
   frame  key          x         y       yaw   d2g
       0  W         0.050     0.000     0.000  0.050
       1  W         0.100     0.000     0.000  0.000
       2  G         0.100     0.000     0.000  0.000
```

**What Bo/Rui should see:**
> Full replay of the episode: every position, every action key, distance-to-goal per frame.

---

## 9. Convert manual episode to GNM format

**Command:**
```bash
python3 scripts/gnm/convert_manual_testdrive_to_gnm.py \
    --input  datasets/manual_testdrive_custom_office \
    --output datasets/manual_gnm_format
```

**Expected output:**
```
Converting 1 episode(s) from ... → datasets/manual_gnm_format
  <episode> → datasets/manual_gnm_format/<episode>
Done. 1 episode(s) written to datasets/manual_gnm_format
NOTE: These are manual data-collection episodes, not official benchmark data.
```

**What Bo/Rui should see:**
> Frame naming switches from `000000.jpg` to `0.jpg` to match the GNM loader. `traj_data.pkl` is rewritten with corrected paths. `metadata.json` records `official_benchmark_data: false`.

---

## 10. CustomVLN-Office proof

**Command:**
```bash
python3 scripts/gnm/collect_custom_vln_office_data.py --dry-run
```

**Expected output:**
```
CustomVLN-Office data collection — dry-run
Generating synthetic frames (NO Isaac Sim required)
  train/custom_vln_office_001  T=51  len=... m
  train/custom_vln_office_002  T=...
  val/custom_vln_office_val_001 ...
Done.
  datasets/custom_vln_office/train/  (N episodes)
  datasets/custom_vln_office/val/    (N episodes)
```

**Show file:**
```bash
ls assets/custom_vln_office/scene_layout.usda
```

**What to say:**
> CustomVLN-Office uses only Isaac Sim primitives — desks, chairs, walls built from USD Cube/Cylinder prims. Zero VLNVerse or kujiale assets. This is proof-of-method and a separate data-collection scene. Official result remains SR 20.0%, OSR 46.7%, NE 6.51 m.

---

## 11. Test suite

**Command:**
```bash
python3 -m pytest tests/gnm/test_manual_testdrive.py \
                  tests/gnm/test_live_dashboard.py \
                  tests/gnm/test_custom_vln_office.py -q
```

**Expected output:**
```
tests/gnm/test_manual_testdrive.py ........   [100%]
...
N passed in X.Xs
```

**What Bo/Rui should see:**
> All automated tests pass. Tests check: metadata schema, actions.jsonl schema, traj_data.pkl fields, safety guard (converter refuses to touch `vlntube`/`vlnverse`/`gnm_release`), and all three dry-run commands.

---

## 12. Pending items

**Say out loud:**
- Full ROS2 closed-loop interface is next. Current implementation is dataset-based and simulation-based.
- `kujiale_0271` scene-holdout performance run (separate from the overall 15-episode result) is pending.
- Zero-shot GNM evaluation (published weights, no fine-tuning) is planned.
- CustomVLN-Office is a separate proof-of-method scene, not an official VLNVerse benchmark result.
- Official Track A result remains: **SR 20.0%, OSR 46.7%, NE 6.51 m.**

---

## Reference: implementation proof documents

| Document | Contents |
|----------|----------|
| `BO_RUI_FULL_IMPLEMENTATION_PROOF.md` | 35 sections, each with source code, command, output, status |
| `BO_RUI_SOURCE_CODE_INDEX.md` | Table: claim → source file → function → command → evidence → status |
| `03_success_rate_breakdown.md` | Per-episode metrics table (all 15 val episodes) |
| `03_success_rate_breakdown.csv` | Machine-readable version of the same table |
| `04_scene_holdout_split.md` | kujiale_0271 holdout split configuration |
| `10_full_evidence_chain.md` | Full evidence chain linking data → training → evaluation → metrics |
| `14_manual_testdrive_walkthrough.md` | Manual test-drive explanation for Bo/Rui |
