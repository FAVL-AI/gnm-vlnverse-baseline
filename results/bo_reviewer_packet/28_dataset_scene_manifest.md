# Dataset and Scene Manifest — GNM-VLNVerse Track A

This document records the local dataset and scene evidence used by the GNM-VLNVerse Track A study.

The purpose is to answer supervisor/reviewer questions about which trajectories, scenes, labels, and local files are used.

## Upstream sources

- VLNVerse data on Hugging Face: https://huggingface.co/datasets/Eyz/VLNVerse_data
- VLNVerse paper: https://arxiv.org/abs/2512.19021

## Local dataset roots

- Train root: `datasets/vlntube/train`
- Validation root: `datasets/vlntube/val`
- Environment root: `datasets/vlntube/envs`

## Local split summary

- Train trajectory files: 238
- Validation trajectory files: 15
- Local environment scenes detected: 4

## Scene-level manifest

| Scene ID | Train trajectories | Validation trajectories | Env asset present |
|---|---:|---:|---:|
| kujiale_0092 | 66 | 2 | yes |
| kujiale_0118 | 60 | 3 | yes |
| kujiale_0203 | 65 | 7 | yes |
| kujiale_0271 | 47 | 3 | yes |

## Environment asset inventory

| Scene ID | Local path | Type | File count | Suffix counts |
|---|---|---|---:|---|
| kujiale_0092 | `datasets/vlntube/envs/kujiale_0092` | directory | 1136 | .hdr: 1, .jpeg: 2, .json: 3, .mdl: 11, .png: 457, .usd: 662 |
| kujiale_0118 | `datasets/vlntube/envs/kujiale_0118` | directory | 707 | .jpeg: 1, .json: 3, .mdl: 11, .png: 234, .usd: 458 |
| kujiale_0203 | `datasets/vlntube/envs/kujiale_0203` | directory | 1210 | .hdr: 1, .jpeg: 1, .json: 3, .mdl: 11, .png: 607, .usd: 587 |
| kujiale_0271 | `datasets/vlntube/envs/kujiale_0271` | directory | 1202 | .jpeg: 1, .json: 3, .mdl: 11, .png: 521, .usd: 666 |

## Example train trajectory structures

### datasets/vlntube/train/kujiale_0092_kujiale_0092_0_3/traj_data.pkl

- Readable: True
- Keys/shapes:
  - `position`: `48x2`
  - `yaw`: `48`

### datasets/vlntube/train/kujiale_0092_kujiale_0092_100_4/traj_data.pkl

- Readable: True
- Keys/shapes:
  - `position`: `40x2`
  - `yaw`: `40`

### datasets/vlntube/train/kujiale_0092_kujiale_0092_102_1/traj_data.pkl

- Readable: True
- Keys/shapes:
  - `position`: `86x2`
  - `yaw`: `86`

### datasets/vlntube/train/kujiale_0092_kujiale_0092_102_2/traj_data.pkl

- Readable: True
- Keys/shapes:
  - `position`: `30x2`
  - `yaw`: `30`

### datasets/vlntube/train/kujiale_0092_kujiale_0092_103_1/traj_data.pkl

- Readable: True
- Keys/shapes:
  - `position`: `95x2`
  - `yaw`: `95`

## Example validation trajectory structures

### datasets/vlntube/val/kujiale_0092_kujiale_0092_91_1/traj_data.pkl

- Readable: True
- Keys/shapes:
  - `position`: `51x2`
  - `yaw`: `51`

### datasets/vlntube/val/kujiale_0092_kujiale_0092_9_2/traj_data.pkl

- Readable: True
- Keys/shapes:
  - `position`: `39x2`
  - `yaw`: `39`

### datasets/vlntube/val/kujiale_0118_kujiale_0118_25_3/traj_data.pkl

- Readable: True
- Keys/shapes:
  - `position`: `50x2`
  - `yaw`: `50`

### datasets/vlntube/val/kujiale_0118_kujiale_0118_31_0/traj_data.pkl

- Readable: True
- Keys/shapes:
  - `position`: `51x2`
  - `yaw`: `51`

### datasets/vlntube/val/kujiale_0118_kujiale_0118_40_4/traj_data.pkl

- Readable: True
- Keys/shapes:
  - `position`: `69x2`
  - `yaw`: `69`

## Shareable evidence commands

The following commands can be used to show the dataset layout without exposing the full image/asset contents:

```bash
find datasets/vlntube -maxdepth 3 -type f | head -80
find datasets/vlntube/train -maxdepth 2 -type f | head -40
find datasets/vlntube/val -maxdepth 2 -type f | head -40
find datasets/vlntube/envs -maxdepth 3 -type f | head -80
```

The stable Isaac live trajectory demo can be run with:

```bash
conda activate isaac
python scripts/gnm/isaac_live_trajectory_demo.py
```

## Interpretation

This manifest confirms the concrete local files used for training, validation, scene lookup, and live Isaac trajectory replay.

The source-code release packages the scripts and evidence summaries. Full image trajectories and scene assets should be shared separately if a supervisor requests the dataset payload itself, because those assets may be large.
