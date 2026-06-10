# GNM-VLNVerse Baseline — Benchmark Reference

> **Protocol version:** 1.0 — June 2026
> **Author:** F. Van Laarhoven, Newcastle University (ORCID: 0009-0006-8931-0364)

---

## Scope

This document defines the evaluation protocol for the GNM/VLNVerse Track A baseline.
It covers dataset splits, metric definitions, reproduction commands, and result claims.

---

## Dataset

| Split | Trajectories | Scenes |
|-------|-------------|--------|
| Train | 238 | kujiale_0092, kujiale_0118, kujiale_0203, kujiale_0271 |
| Val | 15 | kujiale_0092, kujiale_0118, kujiale_0203, kujiale_0271 |

**Scene-holdout split:** `kujiale_0271` is the held-out scene. Configuration:
`configs/gnm/splits/scene_holdout_kujiale_0271.yaml`

Per-scene trajectory counts:

| Scene | Train | Val | Notes |
|-------|-------|-----|-------|
| kujiale_0092 | 62 | 4 | — |
| kujiale_0118 | 71 | 4 | — |
| kujiale_0203 | 61 | 4 | — |
| kujiale_0271 | 44 | 3 | held-out |

---

## Metrics

### Navigation metrics (Anderson et al. 2018)

**Success Rate (SR)**
An episode counts as a success if the robot's final position is within `success_threshold` of the goal position.

```
SR = (number of episodes where final_dist <= success_threshold) / total_episodes
```

**Oracle Success Rate (OSR)**
An episode counts as an oracle success if the robot was ever within `success_threshold` of the goal at any step. This is an upper-bound metric.

```
OSR = (number of episodes where min_dist <= success_threshold) / total_episodes
```

**Navigation Error (NE)**
Mean Euclidean distance from the robot's final position to the goal across all episodes.

```
NE = mean(final_dist_per_episode)
```

### Evaluation parameters

| Parameter | Value |
|-----------|-------|
| Success threshold | 3.0 m |
| Stop criterion | `dist_pred < 0.15` (distance head output) |
| Episodes | 15 val |
| Checkpoint | `best.pt` (fine-tuned on 238 train trajectories) |

---

## Current Validated Result

```text
SR  = 3/15 = 20.0%
OSR = 7/15 = 46.7%
NE  = 6.51 m
```

These are the current reproduced validation metrics, not a final SOTA claim.

Per-episode breakdown: `results/bo_reviewer_packet/03_success_rate_breakdown.md`

### Note on SR vs OSR gap

SR = 20% and OSR = 46.7% differ because the GNM stop criterion uses a predicted distance-to-goal. In episodes where the distance head underestimates proximity, the robot passes through the goal zone but continues walking. This is a known limitation of the GNM stop criterion, not a trajectory quality issue.

---

## Reproduction

### Verify dataset

```bash
python3 scripts/gnm/replay_gnm_demo.py --prove-dataset
python3 scripts/gnm/replay_gnm_demo.py --list-scenes
```

### Run evaluation

```bash
python3 scripts/gnm/06_evaluate.py \
    --checkpoint checkpoints/gnm_base/best.pt \
    --val-data   datasets/vlntube/val
```

### Repository

```
https://github.com/FAVL-AI/gnm-vlnverse-baseline
```

---

## Pending items

| Item | Status |
|------|--------|
| `kujiale_0271` holdout-only result | Pending validation |
| Zero-shot GNM (no fine-tuning) | Pending |
| ROS2 closed-loop evaluation | Planned |
| CustomVLN-Office formal metrics | Planned |

---

## Citation

```bibtex
@misc{vanlaarhoven2026gnmvlnverse,
  title  = {GNM-VLNVerse Baseline: Reproducible Isaac Sim Pipeline for Visual Goal Navigation},
  author = {Van Laarhoven, F.},
  year   = {2026},
  note   = {Research implementation repository},
  url    = {https://github.com/FAVL-AI/gnm-vlnverse-baseline}
}
```
