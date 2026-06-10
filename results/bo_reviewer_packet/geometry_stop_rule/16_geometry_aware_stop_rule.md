# Geometry-Aware Stop Rule Diagnostic — Track A

This diagnostic asks whether the SR/OSR gap can be explained by stopping failure rather than navigation failure.

It uses the existing Track A evaluation trajectory table and applies an oracle geometry-aware rule: if the robot ever enters the 3.0 m goal region, it is counted as if it stopped there.

## Result

| Metric | Value |
|---|---:|
| Episodes | 15 |
| Success radius | 3.0 m |
| Baseline successes | 3/15 |
| Baseline SR | 20.0% |
| Geometry-aware oracle successes | 7/15 |
| Geometry-aware oracle SR | **46.7%** |
| Baseline NE | 6.51 m |
| Oracle-stop NE proxy | 3.79 m |

## Interpretation

The geometry-aware oracle stop rule recovers the OSR upper bound. This confirms that several failed SR episodes are not pure navigation failures: the robot entered the goal region but did not stop there.

## Important limitation

This is a diagnostic oracle rule, not a deployable VLN policy yet. It uses evaluation geometry to quantify the stopping bottleneck.

## Next deployable direction

Replace the unreliable learned distance-head stop trigger with a calibrated stop policy, for example: distance-head calibration, goal-progress consistency, temporal smoothing, or a geometry-aware proxy when pose/goal estimates are available.
