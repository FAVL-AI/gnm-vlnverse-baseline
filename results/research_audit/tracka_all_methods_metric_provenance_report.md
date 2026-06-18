# Track A All-Methods Metric Provenance Report

Per-episode provenance for all five Track A stop-policy methods.
Bootstrap 95% CI: 10000 resamples, seed 42.

> **Small-sample note:** The validation set is 15 episodes per method. Proportions such as SR=20.0% represent 3/15 and SR=33.3% represents 5/15. Bootstrap confidence intervals below reflect this uncertainty.

## Method results

| Method | N | SR | SR 95% CI | OSR | OSR 95% CI | NE | NE 95% CI | SR–OSR gap | Match |
|---|---:|---:|---|---:|---|---:|---|---:|---|
| baseline_gnm | 15 | 20.0% | [0.0%, 40.0%] | 46.7% | [20.0%, 73.3%] | 6.51 | [4.71, 8.50] | 26.7pp [-20.0, 73.3] | **PASS** |
| hand_tuned_waypoint_gate | 15 | 26.7% | [6.7%, 53.3%] | 26.7% | [6.7%, 53.3%] | 5.34 | [4.16, 6.52] | 0.0pp [-46.7, 46.7] | **PASS** |
| logistic_stop_head | 15 | 20.0% | [0.0%, 40.0%] | 46.7% | [20.0%, 73.3%] | 6.51 | [4.71, 8.50] | 26.7pp [-20.0, 73.3] | **PASS** |
| temporal_neural_stop_head | 15 | 33.3% | [13.3%, 60.0%] | 33.3% | [13.3%, 60.0%] | 4.47 | [3.20, 6.03] | 0.0pp [-46.7, 46.7] | **PASS** |
| geometry_aware_oracle | 15 | 46.7% | [20.0%, 73.3%] | 46.7% | [20.0%, 73.3%] | 3.79 | [2.76, 5.01] | 0.0pp [-53.3, 53.3] | **PASS** |

## Formula

- success_flag: `final_distance_to_goal <= success_radius`
- oracle_success_flag: `minimum_distance_to_goal <= success_radius`
- SR: `sum(success_flag) / N * 100`
- OSR: `sum(oracle_success_flag) / N * 100`
- NE: `mean(navigation_error)`
- SR–OSR gap: `OSR − SR` (positive = more oracle than final successes)

## Statistical honesty

The validation set contains 15 episodes. Each percentage point change in SR or OSR corresponds to 1/15 ≈ 6.7 episodes. The bootstrap CIs reflect this granularity. Improvements of one episode are meaningful but should be interpreted cautiously at this sample size.
