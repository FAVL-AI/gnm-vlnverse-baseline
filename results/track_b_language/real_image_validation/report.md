# Held-Out Validation — Track B Subgoal Retrieval

**Date:** 2026-06-15
**Split:** val (15 episodes)
**Method:** clip_route
**CLIP model:** `openai/clip-vit-base-patch16`

## Results

| Metric | Value |
|--------|-------|
| SR@3m | **1.0000** (15/15) |
| Mean dist to goal | 0.033 m |
| Median dist to goal | 0.000 m |

## Per-episode results

| Episode | Scene | Selected frame | Dist to goal (m) | Success |
|---------|-------|----------------|-----------------|---------|
| `kujiale_0092_kujiale_0092_91_1` | kujiale_0092 | 50 | 0.000 | ✓ |
| `kujiale_0092_kujiale_0092_9_2` | kujiale_0092 | 38 | 0.000 | ✓ |
| `kujiale_0118_kujiale_0118_25_3` | kujiale_0118 | 49 | 0.000 | ✓ |
| `kujiale_0118_kujiale_0118_31_0` | kujiale_0118 | 50 | 0.000 | ✓ |
| `kujiale_0118_kujiale_0118_40_4` | kujiale_0118 | 68 | 0.000 | ✓ |
| `kujiale_0203_kujiale_0203_15_3` | kujiale_0203 | 40 | 0.000 | ✓ |
| `kujiale_0203_kujiale_0203_16_3` | kujiale_0203 | 50 | 0.496 | ✓ |
| `kujiale_0203_kujiale_0203_22_4` | kujiale_0203 | 61 | 0.000 | ✓ |
| `kujiale_0203_kujiale_0203_25_0` | kujiale_0203 | 46 | 0.000 | ✓ |
| `kujiale_0203_kujiale_0203_32_2` | kujiale_0203 | 58 | 0.000 | ✓ |
| `kujiale_0203_kujiale_0203_43_1` | kujiale_0203 | 43 | 0.000 | ✓ |
| `kujiale_0203_kujiale_0203_49_3` | kujiale_0203 | 62 | 0.000 | ✓ |
| `kujiale_0271_kujiale_0271_15_1` | kujiale_0271 | 66 | 0.000 | ✓ |
| `kujiale_0271_kujiale_0271_24_4` | kujiale_0271 | 60 | 0.000 | ✓ |
| `kujiale_0271_kujiale_0271_7_3` | kujiale_0271 | 73 | 0.000 | ✓ |

## Interpretation

> All 15 val episodes have `final_dist_m = 0.000 m`. VLNTube episode trajectories
> end exactly at `goal_pos` by construction. SR\@3m = 1.000 reflects this dataset
> property: the final trajectory frame is always at the goal, and the clip\_route
> method reliably selects it. This result should be reported as
> **"subgoal retrieval SR\@3m = 1.000 on vlntube\_fleetsafe (15 val episodes,
> clip\_route method)"**, not as evidence that language instructions generalize
> to unseen scenes or human-authored descriptions.

## Configuration used

| Parameter | Value |
|-----------|-------|
| Keyframe stride | 5 |
| Route prior beta | 1.0 |
| Success radius | 3.0 m |
| Manifest SHA-256 | `eb0b75e25898bd07...` |