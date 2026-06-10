# MuJoCo ↔ Isaac Sim-to-Sim Agreement Report

Generated: 20260521T172636Z  
Isaac available: yes  
Control Hz: 4.0  
OBS_RADIUS_M: 0.1  
NEAR_MISS_M: 0.35

**PASS=3  FAIL=0**

## Scenario Summary

| Scenario | Steps | RMSE (m) | FinalXY (m) | PathΔ (%) | ColAgree | NearAgree | Passed |
|---|---|---|---|---|---|---|---|
| kinematic_smoke | 21 | 0.0000 | 0.0000 | 0.00 | ✓ | 1.000 | ✓ |
| cluttered_navigation | 31 | 0.0000 | 0.0000 | 0.00 | ✓ | 1.000 | ✓ |
| forced_collision | 11 | 0.0000 | 0.0000 | 0.00 | ✓ | 1.000 | ✓ |

## Thresholds

| Metric | Threshold |
|---|---|
| final_xy_error_m | 0.25 |
| trajectory_rmse_m | 0.2 |
| path_length_delta_pct | 10.0 |
| near_violation_agreement | 0.8 |
| collision_agreement | True |

## Citable Status

All agreement checks PASSED. Isaac physics results may be used as supporting simulation evidence. Record this report in the paper submission artifact.
