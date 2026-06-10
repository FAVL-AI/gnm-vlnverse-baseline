# Scene-Level Holdout Split

## Standard split (current official result)

| Split | Trajectories | Scenes |
|-------|-------------|--------|
| train | 238 | all 4 |
| val   | 15  | all 4 |

The validation set holds out trajectory **instances** but all four scenes appear
in both splits.

## Scene-level holdout split (stricter, run pending)

| Role | Scenes | Trajectories |
|------|--------|-------------|
| Train | `kujiale_0092`, `kujiale_0203`, `kujiale_0118` | 191 (75.5%) |
| Test (held-out scene) | `kujiale_0271` | 47 (18.6%) |

**Train/test scene overlap: NONE.**

The model trained on the three-scene split has never seen `kujiale_0271` during
training. Evaluating on `kujiale_0271` tests whether the General Navigation Model
can navigate in a completely unseen floor-plan.

## Verification

```bash
python3 scripts/gnm/check_scene_holdout_split.py \
    --data-root datasets/vlntube \
    --split-config configs/gnm/splits/scene_holdout_kujiale_0271.yaml
```

Output:
```
Train (3 scenes) : 191 trajectories (75.5%)
Holdout test     : 47 trajectories  (18.6%)
Standard val     : 15
Train / test scene overlap: NONE  ✓
PASS — scene-level holdout split is valid.
```

## Config

`configs/gnm/splits/scene_holdout_kujiale_0271.yaml`

```yaml
split:
  train_scenes: [kujiale_0092, kujiale_0203, kujiale_0118]
  test_scenes:  [kujiale_0271]
  status: config_ready_run_pending
```

## Training on the holdout split

```bash
python3 scripts/gnm/04_train_gnm.py \
    --cfg configs/gnm/gnm_base.yaml \
    --split-config configs/gnm/splits/scene_holdout_kujiale_0271.yaml \
    checkpoint.output_dir=checkpoints/gnm_scene_holdout
```

Evaluation on held-out scene:

```bash
python3 scripts/gnm/06_evaluate.py \
    --ckpt checkpoints/gnm_scene_holdout/best.pt \
    --split train \
    --split-config configs/gnm/splits/scene_holdout_kujiale_0271.yaml
```

Full training run: **pending** (requires ~50 GPU-epochs, ~2 hours on RTX 4080 SUPER).
