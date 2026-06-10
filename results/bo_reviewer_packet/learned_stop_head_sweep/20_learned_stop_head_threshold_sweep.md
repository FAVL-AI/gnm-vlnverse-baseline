# Learned Stop-Head Threshold Sweep — Track A

This sweep tests whether the learned logistic stop head improves over fixed scalar stopping and hand-tuned waypoint stopping.

## Key result

| Method | SR | OSR | NE (m) | TL (m) | Stop fired | Mean stop step |
|---|---:|---:|---:|---:|---:|---:|
| Baseline distance stop | 20.0% | 46.7% | 6.51 | 8.08 | 0 | n/a |
| Best hand-tuned waypoint gate | 26.7% | 26.7% | 5.34 | 1.26 | 15 | 5.7 |
| Best learned logistic stop head, P=0.70 | **26.7%** | **46.7%** | 6.09 | 7.14 | 3 | 30.0 |
| Geometry-aware oracle upper bound | 46.7% | 46.7% | 3.79 | n/a | n/a | n/a |

## Threshold sweep

| P(stop) threshold | Stable K | SR | OSR | NE (m) | TL (m) | Stop fired | Mean stop step |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.30 | 3 | 20.0% | 20.0% | 5.83 | 0.52 | 15 | 2.0 |
| 0.40 | 3 | 20.0% | 20.0% | 5.57 | 1.17 | 15 | 6.2 |
| 0.50 | 3 | 13.3% | 20.0% | 6.15 | 2.39 | 14 | 11.9 |
| 0.60 | 3 | 13.3% | 26.7% | 6.51 | 4.38 | 10 | 14.5 |
| 0.70 | 3 | **26.7%** | **46.7%** | 6.09 | 7.14 | 3 | 30.0 |
| 0.80 | 3 | 20.0% | 46.7% | 6.51 | 8.08 | 0 | n/a |
| 0.90 | 3 | 20.0% | 46.7% | 6.51 | 8.08 | 0 | n/a |
| 0.95 | 3 | 20.0% | 46.7% | 6.51 | 8.08 | 0 | n/a |
| 0.99 | 3 | 20.0% | 46.7% | 6.51 | 8.08 | 0 | n/a |

## Interpretation

The learned logistic stop head is better behaved than the hand-tuned waypoint gate. At P=0.70 it preserves OSR at 46.7% while matching the best hand-tuned SR of 26.7%.

However, it still does not close the full gap to the geometry-aware oracle upper bound of 46.7% SR. This suggests that simple logistic calibration is useful but insufficient.

## Conclusion

The learned stop head provides a stronger runtime-only baseline than scalar waypoint thresholding because it avoids premature stopping collapse. The next method should use richer temporal supervision or a neural temporal stop head to convert more OSR episodes into final SR.
