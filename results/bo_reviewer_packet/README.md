# Bo Reviewer Packet — FleetSafe Visual Navigation Benchmark

## One-click evidence demo

```bash
bash scripts/gnm/run_reviewer_demo.sh
```

This single command runs all evidence checks and prints the results to the terminal.
It verifies dataset counts, label contents, success-rate calculation, scene holdout,
generates the input-output figure, and packages a sample dataset.

---

## What is implemented (Track A — current)

| Item | Status | Evidence file |
|------|--------|---------------|
| General Navigation Model trained on VLNVerse data | Done | `checkpoints/gnm_base/best.pt` |
| Official Track A result | Done | `results/ablations.md` |
| 238 training trajectories, 15 val trajectories | Done | `results/dataset_manifest.md` |
| 4 VLNVerse scenes imported | Done | `results/scene_manifest.md` |
| Label inspection script | Done | `scripts/gnm/inspect_trajectory_labels.py` |
| Per-episode SR/OSR breakdown | Done | `03_success_rate_breakdown.md` |
| Scene-level holdout split config | Done | `04_scene_holdout_split.md` |
| Isaac Sim trajectory replay demo | Done | `scripts/gnm/replay_gnm_demo.py` |
| START/GOAL prims with gnm:* USD attributes | Done | (run replay script) |
| Image panels in Isaac Sim viewport | Done | `SHOW_GNM_PANELS=1` flag |
| GNM input-output triplet figure | Done | `05_gnm_input_output_triplet.png` |
| Custom scene from USD primitives | Done | `scripts/gnm/create_custom_gnm_scene.py` |
| Sample dataset package | Done | `scripts/gnm/package_dataset_sample.py` |
| Ablation series | Done | `results/ablations.md` |
| No-oracle-leakage statement | Done | `08_fairness_no_oracle_leakage.md` |

## What is Track A vs Track B

**Track A (done)**: visual-goal navigation.
The robot receives a stack of RGB camera frames and a goal image.
It predicts local waypoints. No language is used.

**Track B (planned)**: language-instruction navigation.
The robot receives a natural-language instruction.
A language-to-subgoal model converts the instruction into visual subgoals.
The General Navigation Model navigates to each subgoal.

---

## Official Track A result

| SR | OSR | NE | SPL | TL | nDTW | CLS |
|----|-----|----|----|-----|------|-----|
| 20.0% | 46.7% | 6.51 m | 20.0% | 8.08 m | 0.449 | 0.658 |

Checkpoint: `checkpoints/gnm_base/best.pt` (epoch 11/50, val_loss = 0.296)

**SR = 20% means 3 out of 15 validation episodes succeeded.**
Full per-episode breakdown: `03_success_rate_breakdown.md`

---

## How to reproduce each evidence item

### Labels

```bash
python3 scripts/gnm/inspect_trajectory_labels.py \
    --data-root datasets/vlntube --split val --limit 3
```

### Success-rate breakdown

```bash
python3 scripts/gnm/explain_eval_success_rate.py \
    --checkpoint checkpoints/gnm_base/best.pt \
    --output results/bo_reviewer_packet/03_success_rate_breakdown.md
```

### Scene holdout

```bash
python3 scripts/gnm/check_scene_holdout_split.py \
    --data-root datasets/vlntube \
    --split-config configs/gnm/splits/scene_holdout_kujiale_0271.yaml
```

### Input-output triplet figure

```bash
python3 scripts/gnm/make_gnm_input_output_triplet.py
```

### Dataset sample (share with Bo)

```bash
python3 scripts/gnm/package_dataset_sample.py \
    --data-root datasets/vlntube \
    --output artifacts/gnm_vlnverse_sample_dataset.tar.gz \
    --per-scene 1
```

### Isaac Sim replay

```bash
conda run -n isaac python scripts/gnm/replay_gnm_demo.py
# With image panels:
SHOW_GNM_PANELS=1 conda run -n isaac python scripts/gnm/replay_gnm_demo.py
```

### Custom office scene (no VLNVerse)

```bash
python3 scripts/gnm/create_custom_gnm_scene.py --dry-run
conda run -n isaac python scripts/gnm/create_custom_gnm_scene.py
conda run -n isaac python scripts/gnm/replay_custom_gnm_scene.py
```

---

## GitHub branch

https://github.com/FAVL-AI/FleetSafe-VisualNav-Benchmark/tree/gnm-vlnverse-baseline
