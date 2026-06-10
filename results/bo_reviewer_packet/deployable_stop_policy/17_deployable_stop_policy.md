# Track A Deployable Stop-Policy Ablation

Checkpoint: `/home/favl/robotics/FleetSafe-VisualNav-Benchmark/checkpoints/gnm_base/best.pt`

Distance threshold: `0.15`
Waypoint-norm threshold: `0.2`

Stop decisions use only runtime GNM outputs: `dist_pred` and `action_pred`.
Oracle geometry is used only after rollout for metrics.

## Results

| Policy | Episodes | SR | OSR | NE (m) | TL (m) | Stop fired | Mean stop step |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline_dist | 15 | 20.0% | 46.7% | 6.51 | 8.08 | 0 | n/a |
| stable_dist_k3 | 15 | 20.0% | 46.7% | 6.51 | 8.08 | 0 | n/a |
| waypoint_norm_k3 | 15 | 26.7% | 26.7% | 5.34 | 1.26 | 15 | 5.7 |
| hybrid_dist_waypoint_k3 | 15 | 20.0% | 46.7% | 6.51 | 8.08 | 0 | n/a |

## Interpretation

This ablation tests whether simple runtime-only stopping gates can close part of the SR/OSR gap without oracle geometry.

If SR does not improve beyond the baseline, the next step is a calibrated or learned stop head rather than another hand-tuned threshold.
