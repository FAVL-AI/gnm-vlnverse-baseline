# Track A Per-Scene Breakdown

All results use success radius = 3.0 m, 15 val episodes, bootstrap 95% CI (10,000 resamples, seed=42).

> **Note:** kujiale_0092 has 2 episodes, kujiale_0118 and kujiale_0271 have 3 each, kujiale_0203 has 7. Per-scene CIs are wide given small N — use for diagnostic pattern inspection, not point-estimate reporting.

## kujiale_0092  (n=2)

| Method | SR % | OSR % | NE (m) | SR 95% CI |
|---|---:|---:|---:|---|
| baseline_gnm | 50 | 50 | 3.55 | [0, 100] |
| hand_tuned_waypoint_gate | 0 | 0 | 7.69 | [0, 0] |
| logistic_stop_head | 50 | 50 | 3.55 | [0, 100] |
| temporal_neural_stop_head | 0 | 0 | 3.85 | [0, 0] |
| geometry_aware_oracle | 50 | 50 | 3.42 | [0, 100] |

## kujiale_0118  (n=3)

| Method | SR % | OSR % | NE (m) | SR 95% CI |
|---|---:|---:|---:|---|
| baseline_gnm | 0 | 0 | 7.80 | [0, 0] |
| hand_tuned_waypoint_gate | 0 | 0 | 6.69 | [0, 0] |
| logistic_stop_head | 0 | 0 | 7.79 | [0, 0] |
| temporal_neural_stop_head | 0 | 0 | 6.58 | [0, 0] |
| geometry_aware_oracle | 0 | 0 | 5.64 | [0, 0] |

## kujiale_0203  (n=7)

| Method | SR % | OSR % | NE (m) | SR 95% CI |
|---|---:|---:|---:|---|
| baseline_gnm | 29 | 57 | 5.73 | [0, 57] |
| hand_tuned_waypoint_gate | 29 | 29 | 4.76 | [0, 57] |
| logistic_stop_head | 29 | 57 | 5.73 | [0, 57] |
| temporal_neural_stop_head | 43 | 43 | 3.89 | [14, 86] |
| geometry_aware_oracle | 57 | 57 | 3.26 | [14, 86] |

## kujiale_0271  (n=3)

| Method | SR % | OSR % | NE (m) | SR 95% CI |
|---|---:|---:|---:|---|
| baseline_gnm | 0 | 67 | 9.02 | [0, 0] |
| hand_tuned_waypoint_gate | 67 | 67 | 3.78 | [0, 100] |
| logistic_stop_head | 0 | 67 | 9.02 | [0, 0] |
| temporal_neural_stop_head | 67 | 67 | 4.13 | [0, 100] |
| geometry_aware_oracle | 67 | 67 | 3.42 | [0, 100] |

## All scenes combined (n=15)

| Method | SR % | OSR % | NE (m) | SR 95% CI |
|---|---:|---:|---:|---|
| baseline_gnm | 20 | 47 | 6.51 | [0, 40] |
| hand_tuned_waypoint_gate | 27 | 27 | 5.34 | [7, 53] |
| logistic_stop_head | 20 | 47 | 6.51 | [0, 40] |
| temporal_neural_stop_head | 33 | 33 | 4.47 | [13, 60] |
| geometry_aware_oracle | 47 | 47 | 3.79 | [20, 73] |

