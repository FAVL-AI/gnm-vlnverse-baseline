# H8-S1 Active Reason-Code Register

## Purpose

This register records the lifecycle status and deterministic regression coverage of every
reason code declared by the H8-S1 hospital dataset validation controls.

The active coverage denominator includes only codes classified as `ACTIVE_REACHABLE`.
Deprecated, deferred, and reserved declarations are excluded rather than being given artificial
execution paths.

## Classification totals

| Classification | Count |
|---|---:|
| Declared codes | 56 |
| ACTIVE_REACHABLE | 54 |
| RESERVED_NOT_ACTIVE | 0 |
| DEPRECATED_UNUSED | 1 |
| DEFERRED_TO_LATER_IMPLEMENTATION | 1 |
| Active codes with deterministic test references | 54/54 |
| Active coverage | 100.0% |

## Register

| Code | Status | Trigger | Blocking? | Deterministic test | Expected result |
|---|---|---|---|---|---|
| `H8_ACQUISITION_ENCODING_MISMATCH` | `ACTIVE_REACHABLE` | acquisition encoding mismatch | Yes | `tests/gnm/test_h8_episode_schema_v2.py::test_n33_wrong_encoding_rejected` | Fail closed with the exact code; no silent admission |
| `H8_ACQUISITION_RESOLUTION_MALFORMED` | `ACTIVE_REACHABLE` | acquisition resolution malformed | Yes | `tests/gnm/test_h8_episode_schema_v2.py::test_n14_malformed_resolution_string_rejected` | Fail closed with the exact code; no silent admission |
| `H8_ACQUISITION_RESOLUTION_MISMATCH` | `ACTIVE_REACHABLE` | acquisition resolution mismatch | Yes | `tests/gnm/test_h8_dataset_builder.py::test_builder_marks_metrics_untrusted_for_invalid_manifest`<br>`tests/gnm/test_h8_dataset_builder.py::test_historical_manifest_is_rejected_with_expected_codes`<br>`tests/gnm/test_h8_episode_schema_v2.py::test_n12_640x480_acquisition_rejected` | Fail closed with the exact code; no silent admission |
| `H8_ACQUISITION_RESOLUTION_MISSING` | `ACTIVE_REACHABLE` | acquisition resolution missing | Yes | `tests/gnm/test_h8_episode_schema_v2.py::test_n13_missing_camera_resolution_rejected` | Fail closed with the exact code; no silent admission |
| `H8_ALIGNMENT_CLOCK_RESET` | `ACTIVE_REACHABLE` | alignment clock reset | Yes | `tests/gnm/test_h8_time_alignment.py::test_all_rejection_codes_are_registered`<br>`tests/gnm/test_h8_time_alignment.py::test_f16_clock_reset_rejected` | Fail closed with the exact code; no silent admission |
| `H8_ALIGNMENT_DUPLICATE_TIMESTAMP_AMBIGUOUS` | `ACTIVE_REACHABLE` | alignment duplicate timestamp ambiguous | Yes | `tests/gnm/test_h8_time_alignment.py::test_f14_duplicate_pose_timestamp_is_ambiguous` | Fail closed with the exact code; no silent admission |
| `H8_ALIGNMENT_EXTRAPOLATION_REFUSED` | `ACTIVE_REACHABLE` | alignment extrapolation refused | Yes | `tests/gnm/test_h8_time_alignment.py::test_f10b_far_outside_series_is_extrapolation_refused`<br>`tests/gnm/test_h8_time_alignment.py::test_summarise_reports_rejections` | Fail closed with the exact code; no silent admission |
| `H8_ALIGNMENT_FRAME_MISMATCH` | `ACTIVE_REACHABLE` | alignment frame mismatch | Yes | `tests/gnm/test_h8_time_alignment.py::test_f17_frame_id_mismatch_rejected`<br>`tests/gnm/test_h8_time_alignment.py::test_f17b_child_frame_mismatch_rejected` | Fail closed with the exact code; no silent admission |
| `H8_ALIGNMENT_GAP_EXCEEDED` | `ACTIVE_REACHABLE` | alignment gap exceeded | Yes | `tests/gnm/test_h8_time_alignment.py::test_all_rejection_codes_are_registered`<br>`tests/gnm/test_h8_time_alignment.py::test_f13_gap_just_above_tolerance_rejected` | Fail closed with the exact code; no silent admission |
| `H8_ALIGNMENT_IMAGE_STAMP_MISSING` | `ACTIVE_REACHABLE` | alignment image stamp missing | Yes | `tests/gnm/test_h8_time_alignment.py::test_missing_image_stamp_rejected` | Fail closed with the exact code; no silent admission |
| `H8_ALIGNMENT_NON_FINITE` | `ACTIVE_REACHABLE` | alignment non finite | Yes | `tests/gnm/test_h8_time_alignment.py::test_all_rejection_codes_are_registered`<br>`tests/gnm/test_h8_time_alignment.py::test_f19_nan_position_rejected` | Fail closed with the exact code; no silent admission |
| `H8_ALIGNMENT_NO_BRACKETING_POSE` | `ACTIVE_REACHABLE` | alignment no bracketing pose | Yes | `tests/gnm/test_h8_time_alignment.py::test_all_rejection_codes_are_registered`<br>`tests/gnm/test_h8_time_alignment.py::test_f09_missing_earlier_pose_is_refused`<br>`tests/gnm/test_h8_time_alignment.py::test_f10_missing_later_pose_is_refused` | Fail closed with the exact code; no silent admission |
| `H8_ALIGNMENT_POSE_MISSING` | `ACTIVE_REACHABLE` | alignment pose missing | Yes | `tests/gnm/test_h8_time_alignment.py::test_empty_pose_series_rejected` | Fail closed with the exact code; no silent admission |
| `H8_ALIGNMENT_QUATERNION_INVALID` | `ACTIVE_REACHABLE` | alignment quaternion invalid | Yes | `tests/gnm/test_h8_time_alignment.py::test_all_rejection_codes_are_registered`<br>`tests/gnm/test_h8_time_alignment.py::test_f18_invalid_quaternion_rejected` | Fail closed with the exact code; no silent admission |
| `H8_ALIGNMENT_TIMESTAMP_ORDER_INVALID` | `ACTIVE_REACHABLE` | alignment timestamp order invalid | Yes | `tests/gnm/test_h8_time_alignment.py::test_f15_out_of_order_timestamps_rejected` | Fail closed with the exact code; no silent admission |
| `H8_ALIGNMENT_TRANSFORM_UNRESOLVED` | `ACTIVE_REACHABLE` | alignment transform unresolved | Yes | `tests/gnm/test_h8_time_alignment.py::test_f20_unresolved_transform_rejected` | Fail closed with the exact code; no silent admission |
| `H8_CAMERA_IDENTITY_MISSING` | `ACTIVE_REACHABLE` | camera identity missing | Yes | `tests/gnm/test_h8_episode_schema_v2.py::test_n32_missing_camera_identity_rejected` | Fail closed with the exact code; no silent admission |
| `H8_CAMERA_MOUNT_UNSUPPORTED` | `ACTIVE_REACHABLE` | camera mount unsupported | Yes | `tests/gnm/test_h8_episode_schema_v2.py::test_n29_unsupported_camera_mount_rejected` | Fail closed with the exact code; no silent admission |
| `H8_CAPTURE_AUTHORISATION_MISSING` | `ACTIVE_REACHABLE` | capture authorisation missing | Yes | `tests/gnm/test_h8_episode_schema_v2.py::test_n28_missing_capture_authorisation_rejected` | Fail closed with the exact code; no silent admission |
| `H8_CONTACT_TELEMETRY_UNAVAILABLE` | `ACTIVE_REACHABLE` | contact telemetry unavailable | Yes | `tests/gnm/test_h8_dataset_builder.py::test_historical_manifest_is_rejected_with_expected_codes`<br>`tests/gnm/test_h8_episode_schema_v2.py::test_n30_zero_collisions_without_telemetry_rejected` | Fail closed with the exact code; no silent admission |
| `H8_CONTACT_TELEMETRY_ZERO_WITHOUT_DETECTOR` | `DEFERRED_TO_LATER_IMPLEMENTATION` | contact telemetry zero without detector | N/A | `tests/gnm/test_h8_reason_code_coverage.py::test_inactive_codes_are_not_counted_as_active` | Not emitted in H8-S1R; retained for a later detector-aware control |
| `H8_CONTROLLER_CHECKPOINT_MISSING` | `ACTIVE_REACHABLE` | controller checkpoint missing | Yes | `tests/gnm/test_h8_dataset_builder.py::test_historical_manifest_is_rejected_with_expected_codes`<br>`tests/gnm/test_h8_episode_schema_v2.py::test_n10_scripted_follower_labelled_as_gnm_rejected` | Fail closed with the exact code; no silent admission |
| `H8_CONTROLLER_MODE_MISSING` | `ACTIVE_REACHABLE` | controller mode missing | Yes | `tests/gnm/test_h8_episode_schema_v2.py::test_s1r_controller_mode_missing_is_blocking` | Fail closed with the exact code; no silent admission |
| `H8_CONTROLLER_MODE_UNKNOWN` | `ACTIVE_REACHABLE` | controller mode unknown | Yes | `tests/gnm/test_h8_episode_schema_v2.py::test_n11_unknown_controller_mode_rejected` | Fail closed with the exact code; no silent admission |
| `H8_CONTROLLER_POLICY_MISMATCH` | `ACTIVE_REACHABLE` | controller policy mismatch | Yes | `tests/gnm/test_h8_dataset_builder.py::test_historical_manifest_is_rejected_with_expected_codes`<br>`tests/gnm/test_h8_episode_schema_v2.py::test_n09_closed_loop_without_policy_in_loop_rejected`<br>`tests/gnm/test_h8_episode_schema_v2.py::test_n10b_scripted_follower_claiming_policy_in_loop_rejected` | Fail closed with the exact code; no silent admission |
| `H8_GOAL_AMBIGUOUS` | `ACTIVE_REACHABLE` | goal ambiguous | Yes | `tests/gnm/test_h8_episode_schema_v2.py::test_n08_duplicate_goal_id_conflicting_content_rejected` | Fail closed with the exact code; no silent admission |
| `H8_GOAL_CAMERA_MISMATCH` | `ACTIVE_REACHABLE` | goal camera mismatch | Yes | `tests/gnm/test_h8_episode_schema_v2.py::test_s1r_goal_camera_mismatch_is_blocking` | Fail closed with the exact code; no silent admission |
| `H8_GOAL_HASH_MISMATCH` | `ACTIVE_REACHABLE` | goal hash mismatch | Yes | `tests/gnm/test_h8_episode_schema_v2.py::test_n31_goal_hash_mismatch_rejected` | Fail closed with the exact code; no silent admission |
| `H8_GOAL_HASH_MISSING` | `ACTIVE_REACHABLE` | goal hash missing | Yes | `tests/gnm/test_h8_episode_schema_v2.py::test_n04_goal_without_image_digest_rejected` | Fail closed with the exact code; no silent admission |
| `H8_GOAL_ID_MISSING` | `ACTIVE_REACHABLE` | goal id missing | Yes | `tests/gnm/test_h8_episode_schema_v2.py::test_n02_absent_goal_id_rejected` | Fail closed with the exact code; no silent admission |
| `H8_GOAL_ID_PLACEHOLDER` | `ACTIVE_REACHABLE` | goal id placeholder | Yes | `tests/gnm/test_h8_dataset_builder.py::test_builder_creates_no_output_on_rejection`<br>`tests/gnm/test_h8_dataset_builder.py::test_historical_manifest_is_rejected_with_expected_codes`<br>`tests/gnm/test_h8_episode_schema_v2.py::test_n01_placeholder_goal_id_rejected` | Fail closed with the exact code; no silent admission |
| `H8_GOAL_IMAGE_CROSS_SPLIT_REUSE` | `ACTIVE_REACHABLE` | goal image cross split reuse | Yes | `tests/gnm/test_h8_episode_schema_v2.py::test_n26_goal_image_reused_across_train_and_test_rejected` | Fail closed with the exact code; no silent admission |
| `H8_GOAL_MAP_MISMATCH` | `ACTIVE_REACHABLE` | goal map mismatch | Yes | `tests/gnm/test_h8_episode_schema_v2.py::test_n06_goal_from_another_map_version_rejected` | Fail closed with the exact code; no silent admission |
| `H8_GOAL_NOT_FOUND` | `ACTIVE_REACHABLE` | goal not found | Yes | `tests/gnm/test_h8_episode_schema_v2.py::test_n03_unresolved_goal_id_rejected` | Fail closed with the exact code; no silent admission |
| `H8_GOAL_POSE_MISMATCH` | `ACTIVE_REACHABLE` | goal pose mismatch | Yes | `tests/gnm/test_h8_episode_schema_v2.py::test_s1r_goal_pose_mismatch_is_blocking` | Fail closed with the exact code; no silent admission |
| `H8_GOAL_RESOLUTION_MISMATCH` | `ACTIVE_REACHABLE` | goal resolution mismatch | Yes | `tests/gnm/test_h8_episode_schema_v2.py::test_s1r_goal_resolution_mismatch_is_blocking` | Fail closed with the exact code; no silent admission |
| `H8_GOAL_SCENE_MISMATCH` | `ACTIVE_REACHABLE` | goal scene mismatch | Yes | `tests/gnm/test_h8_episode_schema_v2.py::test_n05_goal_from_another_scene_digest_rejected` | Fail closed with the exact code; no silent admission |
| `H8_GOAL_SPLIT_MISMATCH` | `ACTIVE_REACHABLE` | goal split mismatch | Yes | `tests/gnm/test_h8_episode_schema_v2.py::test_n07_goal_from_another_split_rejected` | Fail closed with the exact code; no silent admission |
| `H8_MANIFEST_SCHEMA_INVALID` | `ACTIVE_REACHABLE` | manifest schema invalid | Yes | `tests/gnm/test_h8_episode_schema_v2.py::test_s1r_manifest_schema_invalid_is_blocking` | Fail closed with the exact code; no silent admission |
| `H8_MANIFEST_VERSION_UNSUPPORTED` | `ACTIVE_REACHABLE` | manifest version unsupported | Yes | `tests/gnm/test_h8_episode_schema_v2.py::test_s1r_manifest_version_unsupported_is_blocking` | Fail closed with the exact code; no silent admission |
| `H8_MAP_VERSION_MISSING` | `ACTIVE_REACHABLE` | map version missing | Yes | `tests/gnm/test_h8_episode_schema_v2.py::test_n20_missing_map_version_rejected` | Fail closed with the exact code; no silent admission |
| `H8_METRIC_INPUT_UNAVAILABLE` | `DEPRECATED_UNUSED` | metric input unavailable | N/A | `tests/gnm/test_h8_reason_code_coverage.py::test_inactive_codes_are_not_counted_as_active` | Not emitted; excluded from active coverage |
| `H8_NAVMESH_VERSION_MISSING` | `ACTIVE_REACHABLE` | navmesh version missing | Yes | `tests/gnm/test_h8_dataset_builder.py::test_builder_strict_requires_navmesh`<br>`tests/gnm/test_h8_episode_schema_v2.py::test_n21_missing_navmesh_when_path_metrics_requested_rejected` | Fail closed with the exact code; no silent admission |
| `H8_RETRY_NOT_INDEPENDENT` | `ACTIVE_REACHABLE` | retry not independent | Yes | `tests/gnm/test_h8_dataset_builder.py::test_builder_detects_retry_as_non_independent`<br>`tests/gnm/test_h8_episode_schema_v2.py::test_n25_retry_not_counted_as_independent_sample` | Fail closed with the exact code; no silent admission |
| `H8_ROUTE_SPLIT_DUPLICATE` | `ACTIVE_REACHABLE` | route split duplicate | Yes | `tests/gnm/test_h8_episode_schema_v2.py::test_n24_route_instance_in_two_splits_rejected` | Fail closed with the exact code; no silent admission |
| `H8_SCENE_DIGEST_MISSING` | `ACTIVE_REACHABLE` | scene digest missing | Yes | `tests/gnm/test_h8_dataset_builder.py::test_historical_manifest_is_rejected_with_expected_codes`<br>`tests/gnm/test_h8_episode_schema_v2.py::test_n19_missing_scene_digest_rejected` | Fail closed with the exact code; no silent admission |
| `H8_SCENE_IDENTITY_FAILED` | `ACTIVE_REACHABLE` | scene identity failed | Yes | `tests/gnm/test_h8_episode_schema_v2.py::test_s1r_scene_identity_failed_is_blocking` | Fail closed with the exact code; no silent admission |
| `H8_SPLIT_UNKNOWN` | `ACTIVE_REACHABLE` | split unknown | Yes | `tests/gnm/test_h8_episode_schema_v2.py::test_n27_unknown_split_rejected` | Fail closed with the exact code; no silent admission |
| `H8_START_POSE_DECLARED_MISSING` | `ACTIVE_REACHABLE` | start pose declared missing | Yes | `tests/gnm/test_h8_dataset_builder.py::test_historical_manifest_is_rejected_with_expected_codes`<br>`tests/gnm/test_h8_episode_schema_v2.py::test_n17_missing_declared_start_pose_rejected` | Fail closed with the exact code; no silent admission |
| `H8_START_POSE_FRAME_MISMATCH` | `ACTIVE_REACHABLE` | start pose frame mismatch | Yes | `tests/gnm/test_h8_episode_schema_v2.py::test_n18_start_pose_frame_mismatch_rejected` | Fail closed with the exact code; no silent admission |
| `H8_START_POSE_OBSERVED_MISSING` | `ACTIVE_REACHABLE` | start pose observed missing | Yes | `tests/gnm/test_h8_episode_schema_v2.py::test_n16_missing_observed_start_pose_rejected` | Fail closed with the exact code; no silent admission |
| `H8_START_POSE_TOLERANCE_EXCEEDED` | `ACTIVE_REACHABLE` | start pose tolerance exceeded | Yes | `tests/gnm/test_h8_dataset_builder.py::test_historical_start_pose_error_would_be_rejected`<br>`tests/gnm/test_h8_episode_schema_v2.py::test_n15_start_pose_error_above_tolerance_rejected`<br>`tests/gnm/test_h8_episode_schema_v2.py::test_start_pose_yaw_wrap_does_not_false_trigger` | Fail closed with the exact code; no silent admission |
| `H8_SUCCESS_CRITERION_NOT_PREREGISTERED` | `ACTIVE_REACHABLE` | success criterion not preregistered | Yes | `tests/gnm/test_h8_episode_schema_v2.py::test_s1r_success_criterion_not_preregistered_is_blocking` | Fail closed with the exact code; no silent admission |
| `H8_SUCCESS_RADIUS_MISMATCH` | `ACTIVE_REACHABLE` | success radius mismatch | Yes | `tests/gnm/test_h8_episode_schema_v2.py::test_n23_success_radius_differing_from_protocol_rejected` | Fail closed with the exact code; no silent admission |
| `H8_SUCCESS_RADIUS_MISSING` | `ACTIVE_REACHABLE` | success radius missing | Yes | `tests/gnm/test_h8_episode_schema_v2.py::test_n22_missing_success_radius_rejected` | Fail closed with the exact code; no silent admission |
| `H8_TIME_DOMAIN_MISMATCH` | `ACTIVE_REACHABLE` | time domain mismatch | Yes | `tests/gnm/test_h8_time_alignment.py::test_all_rejection_codes_are_registered`<br>`tests/gnm/test_h8_time_alignment.py::test_mixed_clock_pose_series_refused`<br>`tests/gnm/test_h8_time_alignment.py::test_wall_clock_image_refused_not_converted` | Fail closed with the exact code; no silent admission |

## Inactive-code dispositions

### `H8_METRIC_INPUT_UNAVAILABLE`

Status: `DEPRECATED_UNUSED`.

The generic code is redundant with the specific `NOT_COMPUTED_*` metric-readiness states, which
identify the missing evidence precisely. It remains declared temporarily for compatibility but is
not emitted and is excluded from active coverage.

### `H8_CONTACT_TELEMETRY_ZERO_WITHOUT_DETECTOR`

Status: `DEFERRED_TO_LATER_IMPLEMENTATION`.

The current H8-S1 control rejects absent detector evidence using
`H8_CONTACT_TELEMETRY_UNAVAILABLE` and returns `NOT_COMPUTED_MISSING_CONTACTS`. The more specific
zero-without-detector code is retained for a later detector-aware schema and is not given an
artificial execution path in H8-S1R.

## Verification result

- Declared taxonomy entries: 56
- Active reachable entries: 54
- Active entries with permanent test references: 54
- Active regression coverage: 100.0%
- Undeclared reason-code literals in the H8-S1 emitters: 0
