# H8-S Limited Causal Pilot — Recorded-Mode Gate Report

**Status: `LIMITED_CAUSAL_PILOT`.** Recorded-mode gate on REAL frames extracted from the committed drive-validation recordings. No new recording of H8-S, no training, no promotion, no push, no tag, no 20/5/10, no closed-loop, no H8-M sealed-room validation, `CL_BOUND_XY` unchanged. Held for review.

**Gate: PASS** for the 3-frame limited pilot (train=lobby, val=midwest_B, test=east_A).

## Not claimed (honest boundary)
Not a strong held-out visual benchmark, not multi-room generalization, not full goal-conditioned ImageNav. All goal images are the same vending alcove at different scales; strong held-out visual generalization is deferred to **H8-M** (`H8_M_SEALED_ROOM_MAP_EXTENSION_PLAN.md`).

## Real frames extracted (position-matched from recorded episodes)
| decision frame | split | role | source episode | cam idx | lower-black |
|---|---|---|---|---|---|
| h8sl_train_lobby | train | o_d | h8mx_val_lobby_20260714_223318 | 0 | 0.0 |
| h8sl_train_lobby | train | near | h8mx_val_lobby_20260714_223318 | 85 | 0.0 |
| h8sl_train_lobby | train | far | h8mx_val_lobby_20260714_223318 | 225 | 0.0 |
| h8sl_val_midwestB | val | o_d | h8mx_val_midwest_B_20260714_235324 | 0 | 0.0 |
| h8sl_val_midwestB | val | near | h8mx_val_midwest_B_20260714_235324 | 58 | 0.0 |
| h8sl_val_midwestB | val | far | h8mx_val_midwest_A_20260714_234300 | 58 | 0.0 |
| h8sl_test_eastA | test | o_d | h8mx_val_east_A_20260714_215023 | 0 | 0.0 |
| h8sl_test_eastA | test | near | h8mx_val_east_A_20260714_215023 | 43 | 0.0 |
| h8sl_test_eastA | test | far | h8mx_val_east_A_20260714_215023 | 100 | 0.0 |

All frames: real `/camera/image_raw`, camera mount raise **0.12 m**, max lower-frame black **0.0** (no occlusion).

## Gate checks
- scene_gate_pass_all_episodes: **True**
- camera_raise_0p12: **True**
- real_camera_image_raw_frames: **True**
- no_lower_frame_occlusion: **True**
- provenance_clean_per_split: **True**
- no_reused_goal_images_across_splits: **True**
- visual_distinctness_limited_only: **True**
- east_A_stop_sep_caveat_preserved: **True**
- collisions_zero_all_episodes: **True**
- no_strong_heldout_claim: **True**

## Visual distinctness (limited pilot only)
- classification: **LIMITED_PILOT_ONLY** — max cross-split goal-image aHash **0.887** (a STRONG held-out claim would need an embedding gate ≤0.60 at H8-M).
- reused goal images across splits: **none**.
- The near/far goals within a split are the same alcove at different distance; cross-split goals are that alcove at different corridor positions. Certified adequate **only** for a limited pilot.

## east_A stop-separation caveat (preserved)
- test stop separation 0.4 m < preferred 0.6 m; acceptable only for the limited pilot. Stop separations: {'h8sl_train_lobby': 1.0, 'h8sl_val_midwestB': 0.6, 'h8sl_test_eastA': 0.4}.

## Safety & scope
- scene gate PASS on all episodes; collisions zero on all episodes; `CL_BOUND_XY` unchanged.
- No recording of new H8-S data, no training, no promotion. Incumbent retained; status `DIAGNOSTIC_ONLY_NOT_PROMOTED`.

## Decision
**Recorded-mode gate PASSES for the limited pilot.** The real frames exist, are scene-gated, collision-free, occlusion-free, provenance-clean, and visually distinct enough for a LIMITED pilot (not a benchmark). Training is **not** authorised here — held for review.

## Artifacts
`assets/experiments/hospital_h8_s_limited_pilot/recorded/`: `h8sl_recorded_manifest.json`, `h8sl_recorded_acceptance_results.json`, this report, `h8sl_recorded_contact_sheet.png`, `frames/*.jpg` (9 source-linked). Extracted from committed rosbags (not re-recorded). Harness: run via the recorded-gate extractor (ROS + rosbag2).
