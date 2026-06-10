# MuJoCo ↔ Isaac Sim-to-Sim Agreement Report

Generated: 20260516T190749Z  
Isaac available: no (MuJoCo-only run)  
Control Hz: 4.0  
OBS_RADIUS_M: 0.1  
NEAR_MISS_M: 0.35

**PASS=0  FAIL=3**

> **INCOMPLETE** — Isaac backend was not available. MuJoCo trajectories written but cross-backend comparison not performed. Re-run inside AppLauncher with `--with-isaac` for the full gate.

## Scenario Summary

| Scenario | Steps | RMSE (m) | FinalXY (m) | PathΔ (%) | ColAgree | NearAgree | Passed |
|---|---|---|---|---|---|---|---|
| kinematic_smoke | 21 | 0.0000 | 0.0000 | 0.00 | ✓ | 1.000 | ✗ |
| cluttered_navigation | 31 | 0.0000 | 0.0000 | 0.00 | ✓ | 1.000 | ✗ |
| forced_collision | 11 | 0.0000 | 0.0000 | 0.00 | ✓ | 1.000 | ✗ |

## Thresholds

| Metric | Threshold |
|---|---|
| final_xy_error_m | 0.25 |
| trajectory_rmse_m | 0.2 |
| path_length_delta_pct | 10.0 |
| near_violation_agreement | 0.8 |
| collision_agreement | True |

## Failures — kinematic_smoke

- Isaac backend not run — re-run with --with-isaac

## Failures — cluttered_navigation

- Isaac backend not run — re-run with --with-isaac

## Failures — forced_collision

- Isaac backend not run — re-run with --with-isaac

## Citable Status

Isaac physics results are **NOT citable** — comparison gate not run.
