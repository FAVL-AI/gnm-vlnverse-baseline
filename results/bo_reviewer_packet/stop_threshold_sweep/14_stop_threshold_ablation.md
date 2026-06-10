# Stop-Threshold Ablation — Track A

This ablation varies the GNM distance-head stop threshold while keeping the same checkpoint, validation split, evaluator, and 3.0 m success radius.

| Stop threshold | SR (%) | OSR (%) | NE (m) | Successes | Oracle | Episodes |
|---:|---:|---:|---:|---:|---:|---:|
| 0.05 | 20.0 | 46.7 | 6.51 | 3 | 7 | 15 |
| 0.10 | 20.0 | 46.7 | 6.51 | 3 | 7 | 15 |
| 0.15 | 20.0 | 46.7 | 6.51 | 3 | 7 | 15 |
| 0.20 | 20.0 | 46.7 | 6.51 | 3 | 7 | 15 |
| 0.25 | 13.3 | 33.3 | 6.35 | 2 | 5 | 15 |
| 0.30 | 13.3 | 20.0 | 6.58 | 2 | 3 | 15 |
| 0.40 | 20.0 | 20.0 | 5.99 | 3 | 3 | 15 |
| 0.50 | 20.0 | 20.0 | 6.01 | 3 | 3 | 15 |
| 0.75 | 20.0 | 20.0 | 6.01 | 3 | 3 | 15 |
| 1.00 | 20.0 | 20.0 | 6.01 | 3 | 3 | 15 |

Baseline threshold is 0.15. This experiment tests whether the SR/OSR gap is caused by stopping calibration rather than pure navigation failure.

Baseline reference: SR 20.0%, OSR 46.7%, NE 6.51 m.
