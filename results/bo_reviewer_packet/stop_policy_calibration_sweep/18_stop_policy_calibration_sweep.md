# Stop-Policy Calibration Sweep — Track A

This sweep tests whether the runtime-only waypoint-norm stop rule can close the gap between baseline SR and the geometry-aware oracle upper bound.

## Setup

| Item | Value |
|---|---:|
| Distance threshold | 0.15 |
| Waypoint thresholds | 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.75, 1.00 |
| Baseline SR | 20.0% |
| Geometry-aware oracle SR upper bound | 46.7% |

## Key waypoint-norm results

| WP threshold | SR | OSR | NE (m) | TL (m) | Stop fired | Mean stop step |
|---:|---:|---:|---:|---:|---:|---:|
| 0.05 | 13.3% | 40.0% | 6.46 | 7.25 | 3 | 24.0 |
| 0.10 | 13.3% | 26.7% | 6.23 | 5.15 | 13 | 26.5 |
| 0.15 | 20.0% | 26.7% | 5.27 | 2.45 | 15 | 13.4 |
| 0.20 | **26.7%** | 26.7% | 5.34 | 1.26 | 15 | 5.7 |
| 0.25 | 20.0% | 20.0% | 5.81 | 0.54 | 15 | 2.1 |
| 0.30 | 20.0% | 20.0% | 5.83 | 0.52 | 15 | 2.0 |
| 0.40 | 20.0% | 20.0% | 5.83 | 0.52 | 15 | 2.0 |
| 0.50 | 20.0% | 20.0% | 5.83 | 0.52 | 15 | 2.0 |
| 0.75 | 20.0% | 20.0% | 5.83 | 0.52 | 15 | 2.0 |
| 1.00 | 20.0% | 20.0% | 5.83 | 0.52 | 15 | 2.0 |

## Interpretation

The sweep shows that simple waypoint-norm thresholding cannot recover the geometry-aware oracle upper bound of 46.7% SR.

At low thresholds, the policy rarely stops and does not improve SR. At medium thresholds, SR improves slightly to 26.7%, but OSR collapses because the robot stops too early. At high thresholds, the policy becomes over-aggressive and stops almost immediately.

## Conclusion

The stop failure is not solved by scalar threshold tuning. A deployable hand-tuned waypoint gate can improve SR from 20.0% to 26.7%, but it cannot approach the 46.7% oracle upper bound without damaging OSR.

## Next step

The next contribution should be a calibrated or learned stop head that uses temporal evidence from distance predictions, waypoint norms, and goal-progress consistency rather than a fixed scalar threshold.
