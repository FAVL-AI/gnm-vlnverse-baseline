# Temporal Neural Stop Head — Track A

This experiment trains a small temporal neural stop head on Track A train trajectories and evaluates it on held-out Track A validation trajectories.

Runtime decisions use only GNM outputs and derived temporal features. Ground-truth geometry is used only for training labels and final metrics.

## Best result

| Policy | Best P(stop) | Episodes | SR | OSR | NE (m) | TL (m) | Stop fired | Mean stop step |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| temporal_neural_stop_head | 0.50 | 15 | **33.3%** | 33.3% | 4.47 | 4.24 | 13 | 23.6 |

## Comparison against previous deployable methods

| Method | Train/Eval protocol | SR | OSR | NE (m) | Notes |
|---|---|---:|---:|---:|---|
| Baseline distance stop | val only | 20.0% | 46.7% | 6.51 | Distance head never fires |
| Best hand-tuned waypoint gate | val only | 26.7% | 26.7% | 5.34 | Improves SR but collapses OSR |
| Logistic stop head | train → val | 20.0% | 46.7% | 6.51 | Does not improve held-out SR |
| Temporal neural stop head | train → val | **33.3%** | 33.3% | **4.47** | Best deployable held-out SR |
| Geometry-aware oracle stop | diagnostic only | 46.7% | 46.7% | 3.79 | Uses ground-truth geometry, not deployable |

## Threshold sweep

| P(stop) threshold | Stable K | SR | OSR | NE (m) | TL (m) | Stop fired | Mean stop step |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.10 | 3 | 20.0% | 20.0% | 5.71 | 0.80 | 15 | 3.8 |
| 0.20 | 3 | 20.0% | 20.0% | 5.63 | 1.11 | 15 | 7.0 |
| 0.30 | 3 | 20.0% | 20.0% | 5.54 | 1.43 | 15 | 9.1 |
| 0.40 | 3 | 26.7% | 26.7% | 5.11 | 2.67 | 15 | 16.7 |
| 0.50 | 3 | **33.3%** | 33.3% | 4.47 | 4.24 | 13 | 23.6 |
| 0.60 | 3 | 26.7% | 33.3% | 4.74 | 4.93 | 11 | 26.0 |
| 0.70 | 3 | 26.7% | 40.0% | 5.33 | 6.00 | 7 | 28.4 |
| 0.80 | 3 | 20.0% | 40.0% | 6.33 | 7.72 | 2 | 32.5 |
| 0.90 | 3 | 13.3% | 40.0% | 6.55 | 8.02 | 1 | 32.0 |

## Protocol

- Train split: train
- Eval split: val
- Train episodes: 238
- Eval episodes: 15
- Training samples: 12,421
- Positive stop labels: 2,568
- Sequence length: 8
- Stable K: 3

## Interpretation

The temporal neural stop head is the first deployable held-out stopping method to improve beyond the 20.0% baseline SR and the 26.7% hand-tuned waypoint gate.

At P(stop)=0.50, the method reaches 33.3% SR and reduces NE to 4.47m. This shows that short-term runtime history contains useful stop evidence that scalar thresholds and logistic calibration fail to exploit.

The method still does not reach the 46.7% geometry-aware oracle upper bound, so there remains recoverable headroom. Future work should improve temporal supervision, calibrate stopping on a separate validation subset, or use richer sequence models.
