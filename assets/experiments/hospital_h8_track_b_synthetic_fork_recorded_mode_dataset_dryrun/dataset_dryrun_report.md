# H8 Synthetic Fork — Dataset-Config DRY-RUN Report

**Status: DRY-RUN (config/schema/audit only) — `SYNTHETIC_DIAGNOSTIC_ONLY`.** No Isaac launched, no capture, no camera images, no datasets, no policy/model inference, no rollout metrics. `CL_BOUND_XY` unchanged (read-only mirror = 6.0).

- **DRY-RUN: PASS**  (25/25 checks)
- config: configs/gnm/h8_synthetic_fork_recorded_mode_dataset.yaml
- planned instances: 8  split instance counts: {'train': 4, 'val': 2, 'test': 2}
- valid-plan audit (PLAN validation only, NOT captured evidence): leakage_safe=True meets_min_scale=True audit_pass=True per_split={'train': 12, 'val': 4, 'test': 6}

## 25 dataset dry-run checks
  - [PASS]  1. config_parses  (top_keys=18)
  - [PASS]  2. claim_boundary_synthetic_only  (SYNTHETIC_DIAGNOSTIC_ONLY)
  - [PASS]  3. authorizes_capture_false
  - [PASS]  4. authorizes_training_false
  - [PASS]  5. output_dataset_only  (assets/experiments/hospital_h8_track_b_synthetic_fork_recorded_mode_dataset)
  - [PASS]  6. cl_bound_xy_6_readonly  (cfg=6.0 harness=6.0)
  - [PASS]  7. min_scale_targets  (train>=12 val>=4 test>=6 inst>=6)
  - [PASS]  8. planned_instance_count_ge_6  (listed=8)
  - [PASS]  9. split_before_training
  - [PASS] 10. no_instance_reuse_across_splits  (unique=8/8)
  - [PASS] 11. no_coordinate_reuse_across_splits  (disjoint_offsets=8/8 cross_split=0)
  - [PASS] 12. no_decision_frame_reuse_across_splits
  - [PASS] 13. no_goal_image_reuse_across_splits
  - [PASS] 14. each_instance_render_valid_required
  - [PASS] 15. each_instance_drive_valid_required
  - [PASS] 16. route_family_N_vs_W_primary
  - [PASS] 17. same_start_diff_goal_present
  - [PASS] 18. hard_negative_mismatched_goal_present
  - [PASS] 19. secondaries_marked_secondary
  - [PASS] 20. scripted_config_driven_only
  - [PASS] 21. no_policy_model_action_probe_training
  - [PASS] 22. forbidden_outputs_block_all  (missing=)
  - [PASS] 23. eight_required_artifacts_present  (8/8)
  - [PASS] 24. injected_reuse_fails_closed  (4/4 leakage + 2/2 requirement)
  - [PASS] 25. valid_plan_passes_as_plan_validation  (per_split={'train': 12, 'val': 4, 'test': 6} n_inst=8 no_images=True)

## Injected leakage failures (must fail closed)
  - dup_decision_frame_across_splits: FAIL-CLOSED (reasons=['reused_decision_frame_across_splits'])
  - dup_goal_image_across_splits: FAIL-CLOSED (reasons=['reused_goal_image_across_splits'])
  - dup_coordinate_across_splits: FAIL-CLOSED (reasons=['reused_coordinate_across_splits'])
  - single_instance_collapse: FAIL-CLOSED (reasons=['below_min_scale', 'single_instance_not_leakage_safe'])

Claim boundary: SYNTHETIC_DIAGNOSTIC_ONLY; config/schema/audit dry-run only; no capture; no images; no datasets; no policy/model inference; no training; no rollout metrics (TL/NE/SR/OSR/SPL/nDTW/CR); no action-probe; no promotion; no autonomy; not training authorization; CL_BOUND_XY unchanged.
