# Isaac Sim Camera Click Validation

**Branch:** `gnm-vlnverse-baseline`  
**Script:** `scripts/gnm/replay_gnm_demo.py`

---

## How to launch each camera view

```bash
# Start view — robot at episode start position
VIEW=START SHOW_GNM_PANELS=1 conda run -n isaac python scripts/gnm/replay_gnm_demo.py

# Current view — robot at trajectory mid-point
VIEW=CURRENT SHOW_GNM_PANELS=1 conda run -n isaac python scripts/gnm/replay_gnm_demo.py

# Goal view — robot at episode goal position
VIEW=GOAL SHOW_GNM_PANELS=1 conda run -n isaac python scripts/gnm/replay_gnm_demo.py
```

The `VIEW=` variable auto-sets the Isaac Sim viewport to the named camera.  
You can also set the viewport manually (see below).

---

## How to click a camera in Isaac Sim

1. Open the **Stage** window (Window → Stage).
2. Expand `/World/GNM_Replay/`.
3. Click one of:
   - `START_CAMERA`
   - `CURRENT_CAMERA`
   - `GOAL_CAMERA`
4. In the Isaac Sim menu choose **Camera → Look Through Selected** (or right-click → Look Through).
5. The **Property** panel on the right shows all `gnm:*` custom attributes.

---

## Expected USD attributes in the Property panel

Every camera prim exposes these attributes under the `gnm` namespace:

| Attribute | Type | Example |
|-----------|------|---------|
| `gnm:role` | string | `"start"` / `"current"` / `"goal"` |
| `gnm:scene_id` | string | `"kujiale_0118"` |
| `gnm:episode_id` | string | `"kujiale_0118_kujiale_0118_…"` |
| `gnm:x` | double | robot X position (metres) |
| `gnm:y` | double | robot Y position (metres) |
| `gnm:yaw_rad` | double | heading in radians |
| `gnm:yaw_deg` | double | heading in degrees |
| `gnm:frame_index` | int | frame number in the trajectory |
| `gnm:image_path` | string | absolute path to the JPEG frame |
| `gnm:success_rate` | double | `0.2` (= 20.0%) |
| `gnm:oracle_success_rate` | double | `0.4667` (= 46.7%) |
| `gnm:navigation_error_m` | double | `6.51` |
| `gnm:dataset_train_trajectories` | int | `238` |
| `gnm:dataset_val_trajectories` | int | `15` |

---

## Where dataset counts are validated

```
datasets/vlntube/train/   — 238 subdirectories (one per trajectory)
datasets/vlntube/val/     — 15 subdirectories
```

Quick check:

```bash
ls datasets/vlntube/train/ | wc -l   # → 238
ls datasets/vlntube/val/   | wc -l   # → 15
```

The reviewer demo also prints these counts:

```bash
bash scripts/gnm/run_reviewer_demo.sh
# Section "2. Dataset count" prints TRAIN_COUNT and VAL_COUNT
```

---

## Where SR 20.0%, OSR 46.7%, and NE 6.51 m are validated

These numbers come from `checkpoints/gnm_base/best.pt` evaluated on the 15 val episodes.

**Primary evidence file:**  
`results/bo_reviewer_packet/03_success_rate_breakdown.md`

Per-episode table (episodes 2, 11, 12 succeeded; 7 episodes achieved oracle):

| Metric | Value | Fraction |
|--------|-------|----------|
| Success Rate (SR) | **20.0%** | 3 / 15 |
| Oracle SR (OSR) | **46.7%** | 7 / 15 |
| Navigation Error (NE) | **6.51 m** | mean final distance to goal |

Reproduce from evaluation output:

```bash
python3 scripts/gnm/explain_eval_success_rate.py \
    --checkpoint checkpoints/gnm_base/best.pt \
    --output results/bo_reviewer_packet/03_success_rate_breakdown.md \
    --csv    results/bo_reviewer_packet/03_success_rate_breakdown.csv
```

**CSV source:**  
`results/bo_reviewer_packet/03_success_rate_breakdown.csv`

---

## Non-GUI panel check (no Isaac Sim required)

```bash
python3 scripts/gnm/replay_gnm_demo.py --dry-run-panels
```

Prints START/CURRENT/GOAL pose values and writes PNG panels to `results/figures/`.  
No Isaac Sim licence or display is required.
