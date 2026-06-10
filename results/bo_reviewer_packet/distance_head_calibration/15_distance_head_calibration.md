# Distance-Head Calibration Probe — Track A

This probe checks whether the GNM distance head predicts goal proximity reliably on real VLNVerse validation samples.

## Result

| Metric | Value |
|---|---:|
| Checkpoint | `best.pt` |
| Global step | 1067 |
| Best validation loss | 0.5022 |
| Distance prediction mean | 0.3555 |
| Distance prediction std | 0.0651 |
| Distance prediction range | [0.2095, 0.6147] |
| Distance target mean | 0.4680 |
| Distance target range | [0.0500, 1.0000] |
| Prediction-target correlation | **+0.0229** |
| Healthy correlation reference | > 0.3 |
| Stop threshold | 0.15 |
| Collapse count below threshold | 0/64 |

## Interpretation

The distance head is not collapsed in the sense of always predicting below the stop threshold. Instead, it is poorly calibrated: the predicted distance-to-goal has almost no correlation with the true distance-to-goal.

This explains the Track A evaluation gap: the robot can often enter the goal region, as shown by OSR, but the learned distance head does not reliably recognise goal proximity and trigger stopping.

## Conclusion

The bottleneck is not the scalar stop threshold alone. The bottleneck is distance-head calibration and stop-policy reliability.

## Evidence chain

- Baseline Track A: SR 20.0%, OSR 46.7%, NE 6.51 m.
- Stop-threshold sweep: simple threshold tuning did not improve SR beyond 20.0%.
- Distance-head probe: prediction-target correlation is only +0.0229.

## Next step

Test a geometry-aware stop rule or calibrate the distance head using validation-set temperature/isotonic calibration before retraining.
