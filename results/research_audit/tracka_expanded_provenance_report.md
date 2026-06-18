# Track A Expanded Provenance Report (253 episodes)

Expanded evaluation for baseline_gnm and geometry_aware_oracle across all 253 episodes (238 train + 15 val).
Bootstrap 95% CI: 10,000 resamples, seed=42. Success radius: 3.0 m.

> **Scope limitation:** Only baseline_gnm and geometry_aware_oracle are evaluated
> on all 253 episodes. The other three methods remain at 15-episode val evaluation.
> See tracka_expanded_split_lock.json for full methodology note.

## Aggregate results

| Method | n | SR % | OSR % | NE (m) | SR 95% CI | NE 95% CI | OSR−SR gap |
|---|---:|---:|---:|---:|---|---|---:|
| baseline_gnm | 253 | 37.5 | 50.6 | 5.51 | [31.6, 43.5] | [4.99, 6.02] | 13.0 pp |
| geometry_aware_oracle | 253 | 50.6 | 50.6 | 3.55 | [44.3, 56.9] | [3.22, 3.90] | 0.0 pp |

## Per-scene results

| Method | Scene | n | SR % | OSR % | NE (m) | SR 95% CI |
|---|---|---:|---:|---:|---:|---|
| baseline_gnm | kujiale_0092 | 68 | 38.2 | 42.6 | 5.91 | [26.5, 50.0] |
| baseline_gnm | kujiale_0118 | 63 | 27.0 | 38.1 | 6.28 | [15.9, 38.1] |
| baseline_gnm | kujiale_0203 | 72 | 47.2 | 65.3 | 4.45 | [36.1, 58.3] |
| baseline_gnm | kujiale_0271 | 50 | 36.0 | 56.0 | 5.50 | [24.0, 50.0] |
| geometry_aware_oracle | kujiale_0092 | 68 | 42.6 | 42.6 | 3.93 | [30.9, 54.4] |
| geometry_aware_oracle | kujiale_0118 | 63 | 38.1 | 38.1 | 4.46 | [27.0, 50.8] |
| geometry_aware_oracle | kujiale_0203 | 72 | 65.3 | 65.3 | 2.83 | [54.2, 76.4] |
| geometry_aware_oracle | kujiale_0271 | 50 | 56.0 | 56.0 | 2.93 | [42.0, 70.0] |

## Comparison with 15-episode val results

| Method | Metric | 15-ep val | 253-ep expanded | CI width comparison |
|---|---|---:|---:|---|
| baseline_gnm | SR % | 20.0 | 37.5 | val CI [0, 40] → exp CI [31.6, 43.5] |
| baseline_gnm | NE (m) | 6.51 | 5.51 | val CI [4.71, 8.50] → exp CI [4.99, 6.02] |

## Methodology note

**Why only 2 methods on the expanded set:**

- hand_tuned_waypoint_gate: Simulating the policy from baseline trajectories
  (threshold sweep) gives SR=20%, but live Isaac Sim runs give SR=26.7%. The divergence
  occurs because stopping early changes the robot's subsequent path. Cannot reliably
  expand without new live Isaac Sim inference.
- logistic_stop_head: Trained on these exact trace features → in-distribution evaluation.
- temporal_neural_stop_head: Same training contamination.

**Why the expanded set is valid for baseline and oracle:**

- baseline_gnm: true_dist_m in traces comes from live Isaac Sim runs (no training).
  The stopping-gap claim does not depend on stop-policy evaluation.
- geometry_aware_oracle: Derived from min(true_dist_m); no training involved.
