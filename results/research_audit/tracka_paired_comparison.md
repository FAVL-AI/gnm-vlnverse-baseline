# Track A Paired Comparison: baseline_gnm vs temporal_neural_stop_head

Paired on 15 val episodes. Metric: final distance to goal (m), lower is better.

## Summary

| Metric | baseline_gnm | temporal_neural_stop_head |
|---|---|---|
| SR % | 20 [0, 40] | 33 [13, 60] |
| NE (m) | 6.51 [4.71, 8.50] | 4.47 [3.20, 6.03] |

## Statistical tests (NE improvement: temporal − baseline distance, positive = temporal closer)

- **Wilcoxon signed-rank (two-sided):** T+=95.0, z=1.988, p≈0.0468 (normal approx, n=15)
- **Sign test (two-sided):** pos=11, neg=4, ties=0, p=0.1185 (exact binomial)

> Small-sample caution: n=15 gives limited power. These tests report observed
> effect direction and magnitude, not a claim of statistical significance.

## Per-episode direction

| Episode | baseline NE | temporal NE | diff (b−t) | direction |
|---|---:|---:|---:|---|
| kujiale_0092_kujiale_0092_91_1 | 4.28 | 4.06 | +0.22 | temporal↓ |
| kujiale_0092_kujiale_0092_9_2 | 2.82 | 3.64 | -0.82 | baseline↓ |
| kujiale_0118_kujiale_0118_25_3 | 7.29 | 3.66 | +3.63 | temporal↓ |
| kujiale_0118_kujiale_0118_31_0 | 3.52 | 3.52 | +0.00 | temporal↓ |
| kujiale_0118_kujiale_0118_40_4 | 12.58 | 12.58 | +0.00 | temporal↓ |
| kujiale_0203_kujiale_0203_15_3 | 5.64 | 5.60 | +0.04 | temporal↓ |
| kujiale_0203_kujiale_0203_16_3 | 12.09 | 6.39 | +5.70 | temporal↓ |
| kujiale_0203_kujiale_0203_22_4 | 7.83 | 5.76 | +2.07 | temporal↓ |
| kujiale_0203_kujiale_0203_25_0 | 4.55 | 1.40 | +3.15 | temporal↓ |
| kujiale_0203_kujiale_0203_32_2 | 5.74 | 2.42 | +3.32 | temporal↓ |
| kujiale_0203_kujiale_0203_43_1 | 2.26 | 2.30 | -0.04 | baseline↓ |
| kujiale_0203_kujiale_0203_49_3 | 2.00 | 3.33 | -1.33 | baseline↓ |
| kujiale_0271_kujiale_0271_15_1 | 5.45 | 1.70 | +3.75 | temporal↓ |
| kujiale_0271_kujiale_0271_24_4 | 7.12 | 8.25 | -1.13 | baseline↓ |
| kujiale_0271_kujiale_0271_7_3 | 14.48 | 2.44 | +12.04 | temporal↓ |

## Honest scope of this comparison

- The temporal stop head was **trained** on the 238-episode train split. The 15 val episodes are held out from training.
- The logistic stop head never fires on val (stop threshold not met), so its NE = baseline NE.
- The geometry_aware_oracle is a diagnostic upper bound, not a deployable method.
- No global superiority claim is made. This comparison is within the Track A audit scope.
