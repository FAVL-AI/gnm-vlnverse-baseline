# Temporal Neural Stop Head — Track A

This experiment trains a small temporal neural stop head on Track A train trajectories and evaluates it on held-out Track A validation trajectories.

Runtime decisions use only GNM outputs and derived temporal features. Ground-truth geometry is used only for training labels and final metrics.

## Best result

| Policy | Best P(stop) | Episodes | SR | OSR | NE (m) | TL (m) | Stop fired | Mean stop step |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| temporal_neural_stop_head | 0.40 | 15 | 26.7% | 40.0% | 4.85 | 5.09 | 10 | 28.0 |

## Protocol

- Train split: train
- Eval split: val
- Train episodes: 238
- Eval episodes: 15
- Training samples: 12421
- Positive stop labels: 2568
- Sequence length: 8
- Stable K: 5

## Interpretation

The temporal neural head tests whether short-term runtime history improves deployable stopping beyond scalar thresholds and the logistic stop head.
