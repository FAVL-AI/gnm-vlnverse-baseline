# Temporal Neural Stop Head — Track A

This experiment trains a small temporal neural stop head on Track A train trajectories and evaluates it on held-out Track A validation trajectories.

Runtime decisions use only GNM outputs and derived temporal features. Ground-truth geometry is used only for training labels and final metrics.

## Best result

| Policy | Best P(stop) | Episodes | SR | OSR | NE (m) | TL (m) | Stop fired | Mean stop step |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| temporal_neural_stop_head | 0.70 | 15 | 20.0% | 46.7% | 6.38 | 7.67 | 4 | 39.2 |

## Protocol

- Train split: train
- Eval split: val
- Train episodes: 238
- Eval episodes: 15
- Training samples: 12421
- Positive stop labels: 2568
- Sequence length: 8
- Feature set: dist_only
- Feature columns: dist_pred, dist_mean, dist_trend
- Stable K: 3

## Interpretation

The temporal neural head tests whether short-term runtime history improves deployable stopping beyond scalar thresholds and the logistic stop head.
