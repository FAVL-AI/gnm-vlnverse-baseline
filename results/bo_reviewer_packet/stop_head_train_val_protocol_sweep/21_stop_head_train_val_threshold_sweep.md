# Stop-Head Train/Val Protocol Sweep — Track A

This experiment trains the learned logistic stop head on the Track A train split and evaluates it on the held-out Track A validation split.

## Protocol

| Item | Value |
|---|---:|
| Train split | train |
| Eval split | val |
| Train trajectories | 238 |
| Eval trajectories | 15 |
| Training samples | 12,421 |
| Positive stop labels | 2,568 |
| Stable K | 3 |

## Threshold sweep

| P(stop) threshold | SR | OSR | NE (m) | TL (m) | Stop fired | Mean stop step |
|---:|---:|---:|---:|---:|---:|---:|
| 0.10 | 20.0% | 20.0% | 5.83 | 0.52 | 15 | 2.0 |
| 0.20 | 20.0% | 20.0% | 5.83 | 0.52 | 15 | 2.0 |
| 0.30 | 20.0% | 20.0% | 5.83 | 0.52 | 15 | 2.0 |
| 0.40 | 20.0% | 20.0% | 5.76 | 0.61 | 15 | 2.5 |
| 0.50 | 13.3% | 26.7% | 5.46 | 2.96 | 15 | 16.6 |
| 0.60 | 20.0% | 40.0% | 6.01 | 6.19 | 9 | 32.6 |
| 0.70 | 20.0% | 46.7% | 6.51 | 8.08 | 0 | n/a |
| 0.80 | 20.0% | 46.7% | 6.51 | 8.08 | 0 | n/a |
| 0.90 | 20.0% | 46.7% | 6.51 | 8.08 | 0 | n/a |

## Interpretation

The held-out train/val protocol shows that the simple logistic stop head does not improve over the 20.0% baseline SR.

Low thresholds stop too early and collapse OSR to 20.0%. Medium thresholds partially recover OSR but do not improve SR. High thresholds become too conservative and fire no stops, returning to baseline behaviour.

## Conclusion

The val-trained logistic stop head was useful as a prototype, but the train-to-val protocol shows that simple logistic calibration is not sufficient for generalisable stopping.

The next method should use richer temporal supervision or a neural temporal stop head to convert OSR episodes into final SR.
