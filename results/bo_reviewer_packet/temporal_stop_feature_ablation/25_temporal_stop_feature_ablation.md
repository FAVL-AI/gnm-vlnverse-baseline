# Temporal Stop-Head Feature-Set Ablation

This ablation evaluates which runtime feature group drives the temporal neural stop-head improvement.

All runs use the same train/eval protocol as v1.1:

- Train split: Track A train
- Eval split: held-out Track A validation
- Sequence length: 8
- Stable-stop confirmation window: 3
- Runtime-only inputs from GNM outputs and derived temporal features
- Ground-truth geometry is used only for training labels and final metrics

## Best result

| feature_set | feature_dim | threshold | SR | OSR | NE (m) | TL (m) | stop_fired | mean_stop_step |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| full_temporal | 6 | 0.50 | 33.3% | 33.3% | 4.47 | 4.24 | 13 | 23.6 |

## Full ablation table

| feature_set | columns | threshold | SR | OSR | NE (m) | TL (m) | stop_fired | mean_stop_step |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| full_temporal | dist_pred, wp_norm, dist_mean, wp_mean, dist_trend, wp_trend | 0.50 | 33.3% | 33.3% | 4.47 | 4.24 | 13 | 23.6 |
| dist_waypoint | dist_pred, wp_norm | 0.40 | 26.7% | 26.7% | 4.81 | 2.61 | 15 | 15.3 |
| dist_only | dist_pred, dist_mean, dist_trend | 0.70 | 20.0% | 46.7% | 6.38 | 7.67 | 4 | 39.2 |
| waypoint_only | wp_norm, wp_mean, wp_trend | 0.70 | 20.0% | 40.0% | 6.04 | 6.71 | 6 | 24.7 |

## Interpretation

This table isolates whether deployable stopping is driven primarily by distance predictions, waypoint/action magnitude, the combination of raw distance and waypoint signals, or the full temporal feature vector.

The v1.1 reference setting used the full temporal feature vector with seq_len=8 and stable_k=3.
