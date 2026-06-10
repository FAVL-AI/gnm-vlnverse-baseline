# Full Evidence Chain — GNM / VLNVerse Baseline

**Branch:** `gnm-vlnverse-baseline`  
**Date verified:** 2026-06-09

---

## 1. Validate 238 train + 15 val trajectories

```bash
ls datasets/vlntube/train/ | wc -l   # → 238
ls datasets/vlntube/val/   | wc -l   # → 15
```

Or via the demo script (no Isaac Sim required):

```bash
python3 scripts/gnm/replay_gnm_demo.py --prove-dataset
```

The reviewer demo also prints counts in section "2. Dataset count":

```bash
bash scripts/gnm/run_reviewer_demo.sh
```

---

## 2. Validate four Kujiale scenes

```bash
python3 scripts/gnm/replay_gnm_demo.py --list-scenes
```

Output shows per-scene trajectory counts for all four scenes:
- `kujiale_0092`
- `kujiale_0118`
- `kujiale_0203`
- `kujiale_0271`  ← held-out scene

USD scene assets are under `datasets/vlntube/envs/` (not committed; re-downloadable from VLNVerse).

---

## 3. Validate kujiale_0271 as held-out scene

Scene-holdout split config:

```
configs/gnm/splits/scene_holdout_kujiale_0271.yaml
```

This config designates `kujiale_0271` as a test-only scene — entirely absent from the training split. Verified by:

```bash
python3 scripts/gnm/check_scene_holdout_split.py \
    --data-root datasets/vlntube \
    --split-config configs/gnm/splits/scene_holdout_kujiale_0271.yaml
```

Output confirms: **Train/test scenes: NO OVERLAP**.

Detailed breakdown: `results/bo_reviewer_packet/04_scene_holdout_split.md`

> **Note:** The full scene-holdout training run (training on only kujiale_0092/0118/0203,
> evaluating on kujiale_0271) is **config-ready but run pending** as of 2026-06-09.
> The official Track A result (SR 20.0%) uses the standard split.

---

## 4. Validate RGB data collection

The robot camera images are JPEG files inside each trajectory folder:

```
datasets/vlntube/train/kujiale_0118_kujiale_0118_X_Y/0.jpg
datasets/vlntube/train/kujiale_0118_kujiale_0118_X_Y/1.jpg
...
```

Each `.jpg` is a 480×360 RGB frame recorded from the forward-facing camera in Isaac Sim / VLNVerse.

To inspect one trajectory:

```bash
python3 scripts/gnm/inspect_trajectory_labels.py \
    --data-root datasets/vlntube --split val --limit 1
```

To see the dataset proof with frame counts:

```bash
python3 scripts/gnm/replay_gnm_demo.py --prove-dataset
```

---

## 5. Validate labels (waypoints / actions)

Labels are **derived at training time** from the trajectory data, not pre-computed files.

- `traj_data.pkl` stores `position` (world-frame x, y) and `yaw` for every frame
- `GNMDataset` (in the training code) computes: `waypoint = positions[obs + horizon] − positions[obs]`, rotated into the robot frame
- This is standard GNM practice: no separate action file is needed

The `--prove-dataset` flag explains this:

```bash
python3 scripts/gnm/replay_gnm_demo.py --prove-dataset
```

In Isaac Sim, orange cone markers show the **ground-truth waypoint targets** from the current frame (derived from `traj_data.pkl`). These are labelled:

```
WAYPOINT_00 … WAYPOINT_04  (orange cones, next 5 frames)
Label in USD: gnm:type = "local_waypoint_target"
              gnm:source = "derived_from_traj_data_pkl"
```

---

## 6. Validate GNM training checkpoint

Checkpoint location: `checkpoints/gnm_base/best.pt`

Training was run with:

```bash
python3 scripts/gnm/04_train_gnm.py   # or train_gnm.sh
```

The checkpoint is evaluated on 15 val episodes by `explain_eval_success_rate.py`.

---

## 7. Validate SR 20.0%, OSR 46.7%, NE 6.51 m

Primary evidence: `results/bo_reviewer_packet/03_success_rate_breakdown.md`

Per-episode table shows which 3 episodes succeeded (episodes 2, 11, 12) and which 7 achieved oracle success.

Reproduce from checkpoint:

```bash
python3 scripts/gnm/explain_eval_success_rate.py \
    --checkpoint checkpoints/gnm_base/best.pt \
    --output results/bo_reviewer_packet/03_success_rate_breakdown.md \
    --csv    results/bo_reviewer_packet/03_success_rate_breakdown.csv
```

Full reviewer demo (includes all validation steps):

```bash
bash scripts/gnm/run_reviewer_demo.sh
```

---

## 8. How to run Isaac Sim demo

### Single camera view

```bash
# Start pose
VIEW=START   SHOW_GNM_PANELS=1 conda run -n isaac python scripts/gnm/replay_gnm_demo.py

# Mid-trajectory
VIEW=CURRENT SHOW_GNM_PANELS=1 conda run -n isaac python scripts/gnm/replay_gnm_demo.py

# Goal pose
VIEW=GOAL    SHOW_GNM_PANELS=1 conda run -n isaac python scripts/gnm/replay_gnm_demo.py

# Top-down overview
VIEW=OVERVIEW SHOW_GNM_PANELS=1 conda run -n isaac python scripts/gnm/replay_gnm_demo.py
```

### Held-out scene (kujiale_0271)

```bash
SCENE=kujiale_0271 SHOW_GNM_PANELS=1 conda run -n isaac python scripts/gnm/replay_gnm_demo.py
```

### Guided evidence tour (auto-switches cameras + saves screenshots)

```bash
SCENE=kujiale_0271 TOUR=1 SHOW_GNM_PANELS=1 conda run -n isaac python scripts/gnm/replay_gnm_demo.py
```

Screenshots saved to: `results/bo_reviewer_packet/screenshots/`

| File | Content |
|------|---------|
| `01_start_camera.png` | Robot start pose viewpoint |
| `02_current_camera.png` | Mid-trajectory viewpoint |
| `03_goal_camera.png` | Goal pose viewpoint |
| `04_overview_path.png` | Top-down path overview with all markers |

### Click cameras in Isaac Sim Property panel

In Isaac Sim Stage window, expand `/World/GNM_Replay/` and click:
- `START_CAMERA` → Property panel shows `gnm:role="start"`, position, SR/OSR/NE, dataset counts
- `CURRENT_CAMERA` → same with `gnm:role="current"`, frame index, image path
- `GOAL_CAMERA` → same with `gnm:role="goal"`
- `WAYPOINT_00` … `WAYPOINT_04` → shows `gnm:source="derived_from_traj_data_pkl"`, frame index

---

## 9. What to say in the Rui/Bo meeting

**What we built:**
- Collected 238 training + 15 validation RGB trajectories across 4 indoor scenes in Isaac Sim/VLNVerse
- Fine-tuned/trained a GNM (MobileNet backbone) on this data
- Evaluated on 15 val episodes: SR 20.0%, OSR 46.7%, NE 6.51 m

**What the numbers mean:**
- SR 20.0% = 3/15 episodes where the robot stopped within 3 m of goal
- OSR 46.7% = 7/15 episodes where the robot was ever within 3 m (but sometimes overshot)
- Gap SR < OSR is because `dist_pred` did not trigger stop in time — a known GNM limitation

**What the Isaac Sim demo shows:**
- Real RGB frames from the training data (not rendered-on-the-fly)
- Ground-truth waypoint targets as orange cones (derived from trajectory positions)
- GNM input = current RGB + goal RGB (shown in GNM_INPUT_PANEL)
- Official metrics in PERFORMANCE_PANEL and on every camera prim

**What is NOT yet done:**
- Scene-holdout evaluation on kujiale_0271 (config ready, run pending)
- Do not claim kujiale_0271 scene-holdout performance numbers until the training run completes

---

## Quick non-GUI validation checklist

```bash
# List scenes + counts
python3 scripts/gnm/replay_gnm_demo.py --list-scenes

# Dataset proof
python3 scripts/gnm/replay_gnm_demo.py --prove-dataset

# Generate panels (no Isaac Sim)
python3 scripts/gnm/replay_gnm_demo.py --dry-run-panels

# Full reviewer demo
bash scripts/gnm/run_reviewer_demo.sh
```
