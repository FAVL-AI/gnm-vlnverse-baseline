# H8 Synthetic Fork — Recorded-Mode DRY-RUN Report

**Status: DRY-RUN (schema/logic only) — `SYNTHETIC_DIAGNOSTIC_ONLY`.** No Isaac launched, no capture, no camera images, no datasets, no policy/model inference, no rollout metrics. `CL_BOUND_XY` unchanged (read-only mirror = 6.0).

- **DRY-RUN: PASS**
- config_valid: True  issues: []
- claim_boundary: SYNTHETIC_DIAGNOSTIC_ONLY
- schemas validated: manifest, example-record, action-label (via example/action fields), split-manifest (via split field), leakage-audit
- leakage-audit dry-run cases (6/6 as expected):
  - one_instance_dataset_fails: PASS (observed={'leakage_safe': False, 'meets_min_scale': False, 'audit_pass': False}, reasons=['below_min_scale', 'single_instance_not_leakage_safe'])
  - reused_decision_frame_id_fails: PASS (observed={'leakage_safe': False, 'meets_min_scale': False, 'audit_pass': False}, reasons=['below_min_scale', 'reused_decision_frame_across_splits'])
  - reused_goal_image_id_fails: PASS (observed={'leakage_safe': False, 'meets_min_scale': False, 'audit_pass': False}, reasons=['below_min_scale', 'reused_goal_image_across_splits'])
  - reused_coordinate_fails: PASS (observed={'leakage_safe': False, 'meets_min_scale': False, 'audit_pass': False}, reasons=['below_min_scale', 'reused_coordinate_across_splits'])
  - insufficient_scale_fails: PASS (observed={'leakage_safe': True, 'meets_min_scale': False, 'audit_pass': False}, reasons=['below_min_scale'])
  - valid_multi_instance_plan_passes: PASS (observed={'leakage_safe': True, 'meets_min_scale': True, 'audit_pass': True}, reasons=[])

Claim boundary: SYNTHETIC_DIAGNOSTIC_ONLY; schema/logic dry-run only; no capture; no images; no datasets; no policy/model inference; no training; no rollout metrics (TL/NE/SR/OSR/SPL/nDTW/CR); no action-probe; no promotion; no autonomy; not training authorization; CL_BOUND_XY unchanged.
