# Learned Stop Head — Track A Train/Eval Protocol

This experiment trains a lightweight logistic stop head on training trajectories and evaluates it on held-out validation trajectories.

Stop decisions use only runtime signals: `dist_pred`, waypoint norm, rolling means, and short-term trends.
Ground truth geometry is used only to create training labels and compute final metrics.

## Result

| Policy | Episodes | SR | OSR | NE (m) | TL (m) | Stop fired | Mean stop step |
|---|---:|---:|---:|---:|---:|---:|---:|
| learned_logistic_stop_head | 15 | 20.0% | 46.7% | 6.51 | 8.08 | 0 | n/a |

## Train/evaluation protocol

- Train split: train
- Eval split: val
- Train episodes: 238
- Eval episodes: 15
- Training samples: 12421
- Positive stop labels: 2568
- Label definition: simulated robot is within 3.0m of the goal.

## Interpretation

This is the first learned/calibrated stop-policy baseline. It tests whether temporal runtime evidence can improve over fixed scalar thresholding.

If it improves beyond 26.7% SR, it is evidence that learned stopping is a promising contribution. If it does not, the next step is richer stop supervision or a neural temporal head.
