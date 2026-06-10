# Learned Stop Head — Track A

This experiment trains a lightweight logistic stop head from runtime GNM traces.

Stop decisions use only runtime signals: `dist_pred`, waypoint norm, rolling means, and short-term trends.
Ground truth geometry is used only to create training labels and compute final metrics.

## Result

| Policy | Episodes | SR | OSR | NE (m) | TL (m) | Stop fired | Mean stop step |
|---|---:|---:|---:|---:|---:|---:|---:|
| learned_logistic_stop_head | 15 | 13.3% | 20.0% | 6.15 | 2.39 | 14 | 11.9 |

## Training labels

- Training samples: 817
- Positive stop labels: 140
- Label definition: simulated robot is within 3.0m of the goal.

## Interpretation

This is the first learned/calibrated stop-policy baseline. It tests whether temporal runtime evidence can improve over fixed scalar thresholding.

If it improves beyond 26.7% SR, it is evidence that learned stopping is a promising contribution. If it does not, the next step is richer stop supervision or a neural temporal head.
