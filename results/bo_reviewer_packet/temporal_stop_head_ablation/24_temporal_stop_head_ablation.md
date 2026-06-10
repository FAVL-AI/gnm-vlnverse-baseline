# Temporal Stop-Head Ablation

This ablation evaluates the temporal neural stop head across sequence length and stable-stop confirmation window.

Runtime decisions use only GNM outputs and derived temporal features. Ground-truth geometry is used only for training labels and final metrics.

## Best result

| seq_len | stable_k | threshold | SR | OSR | NE (m) | TL (m) | stop_fired | mean_stop_step |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 8 | 2 | 0.80 | 33.3% | 40.0% | 5.18 | 6.28 | 7 | 32.0 |

## Full ablation table

| seq_len | stable_k | threshold | SR | OSR | NE (m) | TL (m) | stop_fired | mean_stop_step |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 8 | 2 | 0.80 | 33.3% | 40.0% | 5.18 | 6.28 | 7 | 32.0 |
| 8 | 3 | 0.50 | 33.3% | 33.3% | 4.47 | 4.24 | 13 | 23.6 |
| 16 | 5 | 0.10 | 33.3% | 33.3% | 4.59 | 3.42 | 15 | 20.4 |
| 4 | 5 | 0.50 | 33.3% | 33.3% | 4.74 | 3.94 | 11 | 17.3 |
| 8 | 1 | 0.90 | 33.3% | 33.3% | 4.92 | 5.39 | 10 | 25.4 |
| 8 | 5 | 0.40 | 26.7% | 40.0% | 4.85 | 5.09 | 10 | 28.0 |
| 12 | 2 | 0.40 | 26.7% | 26.7% | 4.69 | 2.83 | 15 | 17.2 |
| 12 | 3 | 0.30 | 26.7% | 26.7% | 4.72 | 2.83 | 15 | 17.0 |
| 16 | 2 | 0.40 | 26.7% | 26.7% | 4.73 | 3.23 | 15 | 19.3 |
| 12 | 1 | 0.60 | 26.7% | 26.7% | 4.74 | 2.76 | 15 | 16.0 |
| 4 | 2 | 0.60 | 26.7% | 26.7% | 4.76 | 2.77 | 15 | 17.0 |
| 16 | 1 | 0.70 | 26.7% | 26.7% | 4.80 | 2.94 | 15 | 17.1 |
| 16 | 3 | 0.20 | 26.7% | 26.7% | 4.83 | 2.53 | 15 | 14.6 |
| 4 | 1 | 0.70 | 26.7% | 26.7% | 5.06 | 2.30 | 15 | 13.6 |
| 12 | 5 | 0.10 | 26.7% | 26.7% | 5.10 | 3.16 | 14 | 16.7 |
| 4 | 3 | 0.80 | 20.0% | 46.7% | 6.50 | 8.08 | 1 | 64.0 |

## Interpretation

This table tests whether the temporal stop-head result is sensitive to the history length and the number of consecutive positive stop predictions required before stopping.

The v1.0 reference setting is seq_len=8 and stable_k=3, which reached 33.3% held-out SR.
